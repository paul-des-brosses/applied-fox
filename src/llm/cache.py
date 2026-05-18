"""
Cache disque pour les appels LLM.

Met en cache les réponses LLM dans une SQLite indexée par hash(role + modèle + prompt).
Bénéfice principal pour le dev : relancer un pipeline après modification d'un seul agent
ne refait pas les appels LLM des agents non modifiés (ceux dont le prompt n'a pas changé).

Invalidation automatique :
    - Si le prompt change (texte différent → hash différent) → cache miss → re-appel.
    - Si le modèle change → hash différent → re-appel.
    - Si le rôle change → hash différent → re-appel.

Vider manuellement :
    rm ~/.applied-fox/cache/llm_cache.sqlite

Concurrence :
    Une connexion SQLite par appel pour éviter les verrous longs. SQLite gère
    le journaling, et nos appels LLM sont séquentiels au MVP.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Stub de réponse pour les cache hits
# ─────────────────────────────────────────────────────────────


class _CachedResponse:
    """
    Stub minimal d'objet de réponse LLM pour les cache hits.

    Les agents lisent uniquement `.content` sur la réponse, donc cette classe
    suffit. Ne PAS hériter de `AIMessage` ou autre type LangChain — on n'en
    a pas besoin et ça créerait une dépendance fragile.
    """

    __slots__ = ("content",)

    def __init__(self, content: str):
        self.content = content

    def __repr__(self) -> str:  # pragma: no cover - debug only
        snippet = (self.content or "")[:50]
        return f"<_CachedResponse content={snippet!r}>"


# ─────────────────────────────────────────────────────────────
# SQLite — schéma minimal
# ─────────────────────────────────────────────────────────────


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Ouvre (et crée si besoin) la base SQLite avec le schéma cache."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_cache (
            key        TEXT PRIMARY KEY,
            role       TEXT NOT NULL,
            model      TEXT NOT NULL,
            response   TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────
# Hash d'un appel LLM
# ─────────────────────────────────────────────────────────────


def _hash_messages(role: str, model: str, messages) -> str:
    """
    Calcule un hash SHA256 stable d'un appel LLM, basé sur :
        - le rôle (eclaireur / integrateur / juge / rapporteur / interviewer)
        - le nom du modèle Ollama (ex. mistral:7b-instruct-q4_K_M)
        - le contenu sérialisé de tous les messages

    Le hash sert de clé primaire dans la SQLite cache.
    """
    serialized: list[dict] = []
    for m in messages:
        # langchain_core.messages.HumanMessage / SystemMessage / etc.
        if hasattr(m, "content"):
            content = m.content
            mtype = getattr(m, "type", None) or type(m).__name__
        elif isinstance(m, dict):
            content = m.get("content", "")
            mtype = m.get("type", "dict")
        else:
            content = str(m)
            mtype = "raw"
        serialized.append({"type": str(mtype), "content": str(content)})

    payload = json.dumps(
        {"role": role, "model": model, "messages": serialized},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────
# Wrapper LLM avec cache transparent
# ─────────────────────────────────────────────────────────────


class CachedLLM:
    """
    Wrapper autour d'un LLM LangChain qui met en cache disque les réponses.

    Comportement :
        - Calcule la clé hash(role, model, messages)
        - Cache hit  → retourne un `_CachedResponse(content)` sans appeler le LLM
        - Cache miss → appelle le LLM réel, sauvegarde le résultat, retourne la réponse originale

    Les autres méthodes du LLM (stream, batch, etc.) sont déléguées via __getattr__
    SANS cache — au MVP les agents n'utilisent que `.invoke()`.

    Le wrapper expose `model` pour compat avec le code qui inspecte ce champ.
    """

    def __init__(self, inner_llm, role: str, db_path: Path) -> None:
        self._inner = inner_llm
        self._role = role
        self._db_path = db_path
        self.model = getattr(inner_llm, "model", "unknown")

    def invoke(self, messages, **kwargs):
        """
        Appel LLM avec cache. La signature accepte **kwargs pour compat
        avec les options LangChain mais elles ne sont PAS hashées dans la
        clé — au MVP nos appels n'utilisent pas d'options par appel.
        """
        key = _hash_messages(self._role, self.model, messages)
        try:
            conn = _open_db(self._db_path)
        except Exception as exc:  # noqa: BLE001
            # Si la SQLite est inaccessible, on dégrade en mode no-cache plutôt
            # que de planter — l'utilisateur a un disque plein ou un autre souci.
            logger.warning("Cache LLM indisponible (%s) — appel direct.", exc)
            return self._inner.invoke(messages, **kwargs)

        try:
            cur = conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is not None:
                logger.debug(
                    "LLM cache HIT (role=%s, model=%s, key=%s)",
                    self._role, self.model, key[:12],
                )
                return _CachedResponse(row[0])

            # Cache miss → appel réel
            response = self._inner.invoke(messages, **kwargs)
            content = response.content if hasattr(response, "content") else str(response)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO llm_cache (key, role, model, response) "
                    "VALUES (?, ?, ?, ?)",
                    (key, self._role, self.model, content),
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache LLM : échec d'écriture (%s)", exc)
            logger.debug(
                "LLM cache MISS (role=%s, model=%s, key=%s)",
                self._role, self.model, key[:12],
            )
            return response
        finally:
            conn.close()

    def __getattr__(self, name: str):
        """Délègue toute autre méthode au LLM sous-jacent."""
        # Les attributs commençant par _ sont gérés directement par __init__
        # et n'arrivent jamais ici (les attributs présents court-circuitent __getattr__).
        return getattr(self._inner, name)


# ─────────────────────────────────────────────────────────────
# Statistiques (utilitaire — pas utilisé dans le pipeline)
# ─────────────────────────────────────────────────────────────


def cache_stats(db_path: Path) -> dict:
    """Retourne quelques stats sur le cache (utile pour audit/debug)."""
    if not db_path.exists():
        return {"entries": 0, "size_bytes": 0}
    conn = sqlite3.connect(str(db_path))
    try:
        n = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
        by_role = dict(conn.execute(
            "SELECT role, COUNT(*) FROM llm_cache GROUP BY role"
        ).fetchall())
        return {
            "entries": n,
            "by_role": by_role,
            "size_bytes": db_path.stat().st_size,
        }
    finally:
        conn.close()
