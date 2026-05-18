"""
Types partagés entre toutes les sources de veille.

Toutes les sources (Reddit, RSS, GitHub) retournent des `RawFinding`
avec le même format. L'Éclaireur agrège puis filtre/structure.

Quand Octopart sera réintroduit (V2 backlog), son contenu (prix, dispo,
EOL) ne se mappera pas naturellement sur le schéma RawFinding générique
et nécessitera un convertisseur dédié.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RawFinding:
    """Trouvaille brute avant structuration par l'Éclaireur."""
    title: str
    body: str
    url: str
    score: int
    created_utc: float
    subreddit: str  # nom de la "sous-source" : nom du subreddit, du flux RSS, ou du repo GitHub
    source_type: str = "community"  # community | news | marketplace
    # Contexte de la requête qui a produit ce finding (pour l'alignement composants).
    query: str = ""
    component_hint: str = ""
    extra: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Cache HTTP (requests-cache) — partagé entre toutes les sources
# ─────────────────────────────────────────────────────────────

_cache_installed = False


def install_cache_once(cache_dir: Path, ttl_hours: int) -> None:
    """
    Installe requests-cache globalement la première fois qu'on en a besoin.

    requests-cache intercepte les appels GET de toutes les sources qui
    utilisent la lib `requests` (Reddit JSON, GitHub via PyGithub, RSS via
    feedparser fallback). Idempotent — appelable plusieurs fois sans effet
    de bord.
    """
    global _cache_installed
    if _cache_installed:
        return

    try:
        import requests_cache
    except ImportError:
        logger.warning("requests-cache non installé, cache désactivé.")
        return

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "requests_cache"

    requests_cache.install_cache(
        str(cache_path),
        backend="sqlite",
        expire_after=ttl_hours * 3600,
        allowable_codes=(200,),
    )
    _cache_installed = True
    logger.info("Cache HTTP installé : %s (TTL %dh)", cache_path, ttl_hours)
