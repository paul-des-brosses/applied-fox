"""
Couche d'abstraction provider LLM.

Point d'entrée unique : `get_llm(role, config)` → BaseChatModel

Pourquoi cette couche existe :
    Aucun agent ne doit importer directement ChatOllama, ChatAnthropic, etc.
    Tout passe par get_llm(). Ainsi, changer de modèle ou de provider ne
    nécessite qu'une modification de config.yaml, pas de code.
    C'est ce qu'on appelle "hot-swappable" — voir docs/DECISIONS.md §2.

Modèles par défaut (mai 2026, calibré RTX 3070 8 GB) :
    interviewer  → mistral 7B Q4 (contrainte CLAUDE.md règle 3)
    eclaireur    → plus de LLM (déterministe)
    integrateur  → mistral 7B Q4 (tâche mécanique)
    juge         → qwen3:8B (méta-raisonnement, le seul rôle qui en a besoin)
    rapporteur   → mistral 7B Q4

Le Juge peut être basculé sur mistral 7B si le hardware ne tient pas qwen3:8B,
au prix d'un risque d'hallucination significativement plus élevé (cf. éval
modeles_perf_2026-05-13.md).

Historique :
    L'abstraction "profile" (small/medium/large) a été supprimée en v1.4
    après éval Jalon 8 — cf. docs/evaluations/modeles_perf_2026-05-13.md.
    En pratique le bon design est "1 modèle par agent selon la tâche", pas
    "1 profil pour tout le hardware". Override par agent via
    `ollama.models.<role>` dans config.yaml.

Contrainte non négociable :
    Le rôle "interviewer" retourne TOUJOURS un modèle Ollama local 7B.
    Ce mapping ne peut pas être outrepassé par la config.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Modèles par défaut par rôle.
# Calibrés post-éval Jalon 8 v1.4 sur RTX 3070 8 GB.
# Voir docs/HARDWARE.md pour les recommandations selon ton matériel.
_DEFAULT_MODELS: dict[str, str] = {
    "interviewer": "mistral:7b-instruct-q4_K_M",
    "eclaireur":   "mistral:7b-instruct-q4_K_M",  # legacy ; n'est plus invoqué (déterministe)
    "integrateur": "mistral:7b-instruct-q4_K_M",  # tâche mécanique, 7B suffit
    "juge":        "qwen3:8B",                    # méta-raisonnement → modèle plus capable
    "rapporteur":  "mistral:7b-instruct-q4_K_M",
}

# Contrainte non négociable : l'Interviewer reste TOUJOURS local 7B Q4.
# CLAUDE.md règle 3 — Tout en local par défaut au MVP.
_INTERVIEWER_FORCED_MODEL = "mistral:7b-instruct-q4_K_M"

_VALID_ROLES = set(_DEFAULT_MODELS.keys())


# ─────────────────────────────────────────────────────────────
# Registre des modèles testés (mai 2026)
#
# Source de vérité pour la commande `applied-fox models` et pour le warning
# émis quand l'utilisateur configure un modèle qui n'a pas été validé sur ce
# rôle. NE PAS confondre "non testé" avec "mauvais" — un modèle non listé ici
# peut très bien marcher, on ne l'a juste pas mesuré.
#
# Verdicts possibles :
#   "tested"      : validé par éval Opus 4.7 sur 3 projets (cf. modeles_perf_2026-05-13.md)
#   "rejected: X" : testé et écarté, avec raison
#
# Pour ajouter un modèle : éditer ce dict + lancer scripts/eval_juge.py + push.
# ─────────────────────────────────────────────────────────────
_TESTED_MODELS: dict[str, dict[str, str]] = {
    "interviewer": {
        "mistral:7b-instruct-q4_K_M": "tested",
        # L'Interviewer est hardcodé en 7B local — voir _INTERVIEWER_FORCED_MODEL.
    },
    "integrateur": {
        "mistral:7b-instruct-q4_K_M": "tested",
    },
    "juge": {
        "qwen3:8B": "tested",
        # mistral:7b non recommandé pour le Juge (0 rejets sur 18 findings en éval,
        # accepte trop) mais reste utilisable comme fallback si qwen3:8B ne tient
        # pas en VRAM. Le risque d'hallucination est alors significativement plus
        # élevé — l'utilisateur le valide via la TUI humaine.
        "mistral:7b-instruct-q4_K_M": "tested",
        "qwen3.5:9b": "rejected: offload CPU 26% sur 8GB VRAM + thinking buggy",
        "mistral-nemo:latest": "rejected: classe 89% en 'medium · next', refuse de trancher",
    },
    "rapporteur": {
        "mistral:7b-instruct-q4_K_M": "tested",
    },
}


def is_tested(role: str, model: str) -> tuple[bool, str]:
    """
    Retourne (is_tested_ok, verdict).

    - (True, "tested") si le modèle est validé pour ce rôle.
    - (False, "rejected: ...") si testé et écarté.
    - (False, "non testé") si jamais évalué.
    """
    verdict = _TESTED_MODELS.get(role, {}).get(model)
    if verdict == "tested":
        return True, "tested"
    if verdict and verdict.startswith("rejected"):
        return False, verdict
    return False, "non testé"


def list_tested_models(role: str) -> dict[str, str]:
    """Retourne le dict {model: verdict} pour un rôle donné, ou {} si rôle inconnu."""
    return dict(_TESTED_MODELS.get(role, {}))


# Cache de warnings : on ne loggue qu'une fois par (rôle, modèle) par process.
_WARNED: set[tuple[str, str]] = set()


def _wrap_with_cache(base_llm, role: str, config: dict):
    """
    Wrap un LLM avec le cache disk-based si activé dans la config.

    Le cache est ACTIVÉ par défaut (économie majeure en dev et démo).
    Pour le désactiver : `cache.llm_enabled: false` dans config.yaml.

    Le cache est stocké dans `paths.cache_dir/llm_cache.sqlite`.
    """
    from pathlib import Path

    cache_cfg = config.get("cache", {})
    if not cache_cfg.get("llm_enabled", True):
        return base_llm

    cache_dir_str = config.get("paths", {}).get("cache_dir", "~/.applied-fox/cache")
    cache_dir = Path(cache_dir_str).expanduser()

    # Import différé — évite le coût SQLite au démarrage si l'utilisateur
    # ne fait que de l'introspection (--help, etc.).
    from src.llm.cache import CachedLLM
    return CachedLLM(base_llm, role=role, db_path=cache_dir / "llm_cache.sqlite")


def get_llm(role: str, config: dict):
    """
    Retourne un LLM configuré pour le rôle donné, avec cache disque activé par défaut.

    Args:
        role:   Identifiant du module appelant. Valeurs valides :
                "interviewer", "eclaireur", "integrateur", "juge", "rapporteur".
        config: Dictionnaire de configuration (contenu de config.yaml parsé).
                Peut être vide {} — les valeurs par défaut s'appliquent.

    Returns:
        Une instance LLM (ChatOllama wrappé par CachedLLM si cache activé).
        Le wrapper expose la même API .invoke() que ChatOllama.

    Override par rôle dans config.yaml :
        ollama:
          models:
            juge: qwen3:14b              # exemple d'override
            integrateur: llama3.3:8b     # autre exemple

    Raises:
        ValueError: Si le rôle est inconnu.
        ImportError: Si langchain-ollama n'est pas installé.
    """
    if role not in _VALID_ROLES:
        raise ValueError(
            f"Rôle '{role}' inconnu. Valeurs acceptées : {sorted(_VALID_ROLES)}"
        )

    from langchain_ollama import ChatOllama  # import différé pour des messages d'erreur clairs

    ollama_cfg: dict = config.get("ollama", {})
    base_url: str = ollama_cfg.get("base_url", "http://localhost:11434")
    num_ctx: int = ollama_cfg.get("num_ctx", 8192)
    timeout: int = ollama_cfg.get("timeout_seconds", 120)
    models_cfg: dict = ollama_cfg.get("models", {})

    # ── Contrainte non négociable ──────────────────────────────────────────
    # L'Interviewer est toujours local, toujours 7B.
    # Ce bloc ne peut pas être outrepassé par la config.
    if role == "interviewer":
        model = _INTERVIEWER_FORCED_MODEL
    else:
        # Override par rôle si présent en config, sinon défaut codé.
        model = models_cfg.get(role, _DEFAULT_MODELS[role])

    # ── Warning si modèle non-testé sur ce rôle ──────────────────────────
    ok, verdict = is_tested(role, model)
    if not ok and (role, model) not in _WARNED:
        _WARNED.add((role, model))
        if verdict.startswith("rejected"):
            logger.warning(
                "Modèle '%s' utilisé pour le rôle '%s' — testé et REJETÉ (%s). "
                "Risque de qualité dégradée. Voir docs/HARDWARE.md.",
                model, role, verdict[len("rejected:"):].strip(),
            )
        else:
            logger.warning(
                "Modèle '%s' utilisé pour le rôle '%s' — non testé. "
                "La qualité n'est pas garantie. Voir docs/HARDWARE.md et "
                "docs/evaluations/modeles_perf_2026-05-13.md.",
                model, role,
            )

    base = ChatOllama(model=model, base_url=base_url, num_ctx=num_ctx, timeout=timeout)
    return _wrap_with_cache(base, role, config)
