"""
Source Reddit — Retours communautaires sur les composants et technologies.

Utilise les endpoints JSON publics de Reddit (pas d'auth, pas de PRAW).
    URL pattern : https://www.reddit.com/r/{sub}/search.json?q=...&sort=relevance&t=year

Pourquoi pas PRAW ?
    Depuis fin 2025, Reddit a restreint la création de nouvelles applications
    self-service pour accéder à son API OAuth. Les endpoints JSON publics restent
    accessibles sans credentials, avec une limite ~10 req/min couverte par notre
    cache 12h (on ne fait en réalité qu'une passe par projet toutes les 12h).

    Avantage portfolio : aucun secret à configurer, 100 % reproductible.

Le cache requests-cache intercepte tous les appels HTTP avec un TTL configurable
(par défaut 12h, cf. docs/CONFIG_SCHEMA.md).

Config : sources.reddit dans config.yaml.

Implémentation : Jalon 3.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.sources.common import RawFinding, install_cache_once

logger = logging.getLogger(__name__)

# Re-export pour compat ascendante (eclaireur.py importait RawFinding depuis ici)
__all__ = ["RawFinding", "search", "DEFAULT_SUBREDDITS"]


# Subreddits par défaut quand aucun n'est passé en argument.
# Choix calibré post-éval Jalon 8 (cf. jalon8_pertinence_multi_projets) :
# on retire AskElectronics et PrintedCircuitBoard qui dominaient 71% des
# hallucinations — ce sont des forums de review PCB DIY et Q&A beginner,
# pas une source de veille technologique alignée.
DEFAULT_SUBREDDITS = [
    "embedded",            # ingénierie embarquée, retours d'expérience
    "esp32",               # chipset-spécifique, projets matures
    "ECE",                 # engineering général
    "ElectricalEngineering",  # discussions techniques
    "arduino",             # capteurs/périphériques (à surveiller, peut être noisy)
    "AskEngineers",        # ingénierie tous domaines
]

# Headers requis par Reddit pour les endpoints publics.
# Ils exigent un User-Agent non-vide pour ne pas bloquer les requêtes.
_HEADERS = {
    "User-Agent": "applied-fox-agent-ia/0.1 (portfolio project, read-only)",
    "Accept": "application/json",
}

# Intervalle minimum entre deux requêtes (politesse, ~10 req/min).
_MIN_INTERVAL_S = 6.0

_last_request_time: float = 0.0


# Le cache HTTP est maintenant géré par src.sources.common.install_cache_once
# (partagé entre toutes les sources qui utilisent `requests`).


# ─────────────────────────────────────────────────────────────
# Appel réseau
# ─────────────────────────────────────────────────────────────


def _get_json(url: str, params: dict) -> dict:
    """
    GET JSON avec rate-limiting poli et gestion d'erreurs.

    Le rate-limiting est bypassé si requests-cache est actif et que la
    réponse provient du cache (pas de vrai appel réseau).

    Returns:
        Le JSON parsé, ou {} en cas d'erreur.
    """
    global _last_request_time

    import requests  # import différé : message clair si absent

    # Pause polie entre deux vraies requêtes réseau.
    now = time.monotonic()
    wait = _MIN_INTERVAL_S - (now - _last_request_time)
    if wait > 0:
        # Vérifie si on a requests-cache et si la réponse sera en cache.
        # Si pas de cache installé, on attend vraiment.
        time.sleep(wait)

    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=10)
        # Ne mettre à jour le timer que si c'est un vrai appel (pas du cache).
        from_cache = getattr(resp, "from_cache", False)
        if not from_cache:
            _last_request_time = time.monotonic()

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning("Rate-limited par Reddit, attente %ds", retry_after)
            time.sleep(retry_after)
            return {}

        resp.raise_for_status()
        return resp.json()

    except Exception as exc:
        logger.warning("Échec requête %s : %s", url, exc)
        return {}


# ─────────────────────────────────────────────────────────────
# Recherche
# ─────────────────────────────────────────────────────────────


def search(
    query: str,
    subreddits: Optional[list[str]] = None,
    min_score: int = 5,
    max_age_days: int = 365,
    limit: int = 25,
    user_agent: str = "applied-fox-agent-ia/0.1",  # conservé pour compatibilité signature
    cache_dir: Optional[Path] = None,
    cache_ttl_hours: int = 12,
    component_hint: str = "",
) -> list[RawFinding]:
    """
    Recherche des posts Reddit pertinents pour une requête donnée.

    Utilise l'endpoint public /search.json — aucun credential requis.

    Filtre déterministe appliqué dès la couche source :
        - score Reddit ≥ min_score
        - post pas plus ancien que max_age_days

    Note : c'est un *premier* niveau de filtrage propre à la source.
    Le filtrage déterministe complet (alignement composants, etc.) est
    appliqué plus tard dans l'Éclaireur.

    Args:
        query:           Terme de recherche (ex. "BME280 alternative 2025").
        subreddits:      Subreddits à interroger. None → DEFAULT_SUBREDDITS.
        min_score:       Score minimum (filtre dur ici).
        max_age_days:    Âge maximum en jours.
        limit:           Nombre maximum de résultats bruts par subreddit.
        user_agent:      Ignoré (conservé pour compatibilité de signature).
        cache_dir:       Dossier où stocker le cache HTTP. None → pas de cache.
        cache_ttl_hours: Durée de vie du cache.
        component_hint:  Composant qui a inspiré la requête (pour traçabilité).

    Returns:
        Liste de RawFinding ayant passé les filtres de score et de fraîcheur.
        Liste vide si l'API échoue ou si aucun résultat.
    """
    if cache_dir is not None:
        install_cache_once(cache_dir, cache_ttl_hours)

    target_subreddits = subreddits if subreddits else DEFAULT_SUBREDDITS
    subreddit_str = "+".join(target_subreddits)

    # Endpoint JSON public Reddit.
    url = f"https://www.reddit.com/r/{subreddit_str}/search.json"
    params = {
        "q": query,
        "sort": "relevance",
        "t": "year",          # posts de l'année écoulée
        "limit": min(limit, 100),
        "restrict_sr": "true",  # restreint aux subreddits listés
    }

    data = _get_json(url, params)
    if not data:
        return []

    now_utc = datetime.now(timezone.utc).timestamp()
    age_cutoff = now_utc - (max_age_days * 86400)

    findings: list[RawFinding] = []

    try:
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            if not post:
                continue

            score = int(post.get("score", 0))
            created = float(post.get("created_utc", 0))

            # Filtres durs au niveau source.
            if score < min_score:
                continue
            if created < age_cutoff:
                continue

            permalink = post.get("permalink", "")
            full_url = f"https://www.reddit.com{permalink}" if permalink else post.get("url", "")

            findings.append(
                RawFinding(
                    title=post.get("title", "") or "",
                    body=(post.get("selftext", "") or "")[:2000],
                    url=full_url,
                    score=score,
                    created_utc=created,
                    subreddit=post.get("subreddit", ""),
                    source_type="community",
                    query=query,
                    component_hint=component_hint,
                    extra={
                        "num_comments": int(post.get("num_comments", 0)),
                        "upvote_ratio": float(post.get("upvote_ratio", 0.0)),
                    },
                )
            )

    except Exception as exc:
        logger.warning("Parsing réponse Reddit pour '%s' : %s", query, exc)
        return []

    logger.debug(
        "Reddit search '%s' → %d résultats bruts, %d après filtres source",
        query,
        len(children) if "children" in locals() else 0,
        len(findings),
    )
    return findings
