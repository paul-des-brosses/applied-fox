"""
Source RSS — Presse technique et annonces fabricants.

Utilise feedparser pour parser les flux RSS/Atom.
Aucune authentification requise.

Flux par défaut au MVP :
    - Hackaday (https://hackaday.com/feed/) — projets DIY embarqué
    - CNX-Software (https://www.cnx-software.com/feed/) — actu hardware embarqué
    - Adafruit Blog (https://blog.adafruit.com/feed/) — produits + tutoriels
    - Electronics Weekly (https://www.electronicsweekly.com/feed/)
    - EE Times (https://www.eetimes.com/feed/)

Pourquoi ces flux : couvrent à la fois les annonces fabricants (composants,
chipsets, EOL) et les retours d'expérience projets/tutoriels DIY. Diversité
suffisante pour qu'au moins l'un d'eux remonte des infos pertinentes par run.

Dégradation gracieuse : si un flux est down ou retourne du HTML d'erreur,
on log un warning et on continue avec les autres.

Implémentation : Jalon 4.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.sources.common import RawFinding, install_cache_once

logger = logging.getLogger(__name__)

# Flux par défaut quand aucun n'est passé en config.
DEFAULT_FEEDS = [
    {"name": "Hackaday",          "url": "https://hackaday.com/feed/"},
    {"name": "CNX-Software",      "url": "https://www.cnx-software.com/feed/"},
    {"name": "Adafruit Blog",     "url": "https://blog.adafruit.com/feed/"},
    {"name": "Electronics Weekly", "url": "https://www.electronicsweekly.com/feed/"},
    {"name": "EE Times",          "url": "https://www.eetimes.com/feed/"},
]

# Politesse : pause entre fetchs de flux différents.
_MIN_INTERVAL_S = 1.0
_last_fetch_time: float = 0.0


def _parse_published_date(entry: dict) -> Optional[float]:
    """
    Extrait la date de publication d'une entrée RSS, retourne un timestamp UTC.

    feedparser parse les dates dans `published_parsed` (struct_time) si possible,
    avec fallback sur `updated_parsed`. Retourne None si rien d'exploitable.
    """
    for key in ("published_parsed", "updated_parsed"):
        ts_struct = entry.get(key)
        if ts_struct:
            try:
                return time.mktime(ts_struct)
            except (TypeError, ValueError):
                continue
    return None


def _entry_to_raw_finding(
    entry: dict,
    feed_name: str,
    query: str,
    component_hint: str,
) -> Optional[RawFinding]:
    """Convertit une entrée feedparser en RawFinding. Retourne None si invalide."""
    title = (entry.get("title") or "").strip()
    if not title:
        return None

    # Le résumé peut être dans summary ou description selon le format RSS/Atom.
    body = (entry.get("summary") or entry.get("description") or "").strip()
    # Tronque pour limiter la consommation tokens en aval.
    body = body[:2000]

    url = (entry.get("link") or "").strip()
    if not url:
        return None

    created_utc = _parse_published_date(entry)
    if created_utc is None:
        # Sans date, on ne peut pas filtrer la fraîcheur — on rejette.
        return None

    return RawFinding(
        title=title,
        body=body,
        url=url,
        score=0,  # RSS n'a pas de score communautaire — sera ignoré côté filtre via min_score=0
        created_utc=created_utc,
        subreddit=feed_name,  # le champ "subreddit" sert de "sous-source" générique
        source_type="news",
        query=query,
        component_hint=component_hint,
    )


def _fetch_one_feed(
    feed_url: str,
    feed_name: str,
    max_age_days: int,
) -> list[RawFinding]:
    """
    Récupère et parse UN flux RSS, applique le filtre de fraîcheur.

    Returns:
        Liste de RawFinding ayant passé le filtre âge max.
        Liste vide si le flux est down ou parsing échoue (dégradation gracieuse).
    """
    global _last_fetch_time

    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser non installé — source RSS désactivée.")
        return []

    # Politesse minimale entre fetchs (le cache absorbe la majorité des appels).
    now = time.monotonic()
    wait = _MIN_INTERVAL_S - (now - _last_fetch_time)
    if wait > 0:
        time.sleep(wait)
    _last_fetch_time = time.monotonic()

    try:
        # feedparser.parse() accepte une URL ; il utilise urllib en interne,
        # donc requests-cache n'intercepte PAS ces appels. Pour le MVP on
        # accepte ce trade-off — feedparser gère son propre etag/modified.
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.warning("Échec parse flux %s : %s", feed_url, exc)
        return []

    if parsed.bozo and not parsed.entries:
        # bozo=True signifie que feedparser a détecté un problème (HTML d'erreur, malformé...).
        # On tolère bozo si on a quand même des entries (cas fréquent d'avertissements bénins).
        logger.warning("Flux %s mal-formé : %s", feed_url, getattr(parsed, "bozo_exception", ""))
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
    findings: list[RawFinding] = []

    for entry in parsed.entries:
        rf = _entry_to_raw_finding(entry, feed_name, query="", component_hint="")
        if rf is None:
            continue
        if rf.created_utc < cutoff:
            continue
        findings.append(rf)

    logger.debug("Flux %s : %d entries → %d après filtre âge", feed_name, len(parsed.entries), len(findings))
    return findings


def search(
    query: str = "",
    feeds: Optional[list[dict]] = None,
    max_age_days: int = 90,
    cache_dir: Optional[Path] = None,
    cache_ttl_hours: int = 24,
    component_hint: str = "",
    **_kwargs,
) -> list[RawFinding]:
    """
    Recherche dans les flux RSS configurés.

    Contrairement à Reddit, RSS n'a pas de "recherche" côté serveur — on
    récupère TOUTES les entrées récentes des flux et on laisse le filtre
    déterministe en aval (alignement composants) faire le tri.

    Args:
        query:           Conservé pour compat avec l'interface des autres sources.
                         Ignoré ici (RSS n'a pas de search).
        feeds:           Liste de dicts {"name": ..., "url": ...}. None → DEFAULT_FEEDS.
        max_age_days:    Articles plus anciens que cette valeur sont ignorés.
        cache_dir:       Dossier où stocker le cache HTTP (partagé entre sources).
        cache_ttl_hours: Durée de vie du cache.
        component_hint:  Conservé pour compat. Renseigné depuis l'Éclaireur si la
                         requête est centrée sur un composant.

    Returns:
        Liste agrégée de RawFinding venant de tous les flux, filtrés par fraîcheur.
        Liste vide si tous les flux sont indisponibles (dégradation gracieuse).
    """
    if cache_dir is not None:
        install_cache_once(cache_dir, cache_ttl_hours)

    target_feeds = feeds if feeds else DEFAULT_FEEDS
    all_findings: list[RawFinding] = []

    for feed_cfg in target_feeds:
        name = feed_cfg.get("name", "?")
        url = feed_cfg.get("url", "")
        if not url:
            continue

        feed_findings = _fetch_one_feed(url, name, max_age_days)
        # On rétro-injecte la query et le component_hint pour la traçabilité aval.
        for rf in feed_findings:
            rf.query = query
            rf.component_hint = component_hint
        all_findings.extend(feed_findings)

    logger.debug("RSS search → %d findings cumulés sur %d flux", len(all_findings), len(target_feeds))
    return all_findings
