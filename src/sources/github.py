"""
Source GitHub — Écosystème open-source autour des composants et technologies.

Utilise PyGithub pour interroger l'API GitHub Search.

Stratégie au MVP : on cherche des REPOS liés à un composant ou un pattern
technique (driver, library, exemple d'intégration). Les repos avec beaucoup
d'étoiles et activité récente sont les plus pertinents.

Requiert : GITHUB_TOKEN dans les variables d'env.
    Sans token : rate limit 10 req/min (inutilisable pour 40 queries).
    Avec token : 30 req/min (suffisant avec cache 24h).

Dégradation gracieuse : si GITHUB_TOKEN est absent OU si la lib PyGithub
plante (rate limit, réseau), la source retourne [] et le pipeline continue
avec les autres sources.

Implémentation : Jalon 4.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.sources.common import RawFinding, install_cache_once

logger = logging.getLogger(__name__)

# GitHub Search API : 30 req/min en authentifié. On laisse 2.5s entre vraies requêtes.
_MIN_INTERVAL_S = 2.5
_last_request_time: float = 0.0

# Suffixes Reddit-style qui tuent le match GitHub (très littéral).
# Diagnostic Jalon 4 : "Module LoRa SX1276 alternative" → 0 repos,
# alors que "Module LoRa SX1276" → plusieurs repos. GitHub veut des
# queries courtes et factuelles.
_NOISE_SUFFIXES = {
    "alternative", "review", "issue", "issues",
    "vs", "comparison", "tips", "best", "practices",
}

# Limite empirique : GitHub Search fait du AND littéral entre tous les termes.
# Au-delà de 3 mots, la probabilité de matcher un repo s'effondre.
# Diagnostic Jalon 4 : "deep sleep optimization battery" → 0 repos,
# "deep sleep optimization" → 5+ repos. 3 mots = sweet spot empirique.
_MAX_QUERY_WORDS = 3


def _strip_readme_noise(content: str) -> str:
    """
    Nettoie un README en retirant les éléments markdown bruyants
    (badges, HTML, liens d'image, séparateurs purs) qui n'apportent
    rien factuellement au LLM.
    """
    cleaned_lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Badges Markdown : ![alt](url) ou [![alt](url)](href)
        if line.startswith("![") or line.startswith("[!"):
            continue
        # Balises HTML brutes en début de ligne
        if line.startswith("<") and line.endswith(">"):
            continue
        # Séparateurs purs
        if set(line) <= set("=-_~`*#|"):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _build_rich_body(repo, max_chars: int = 1500) -> str:
    """
    Construit un body riche pour un repo GitHub à partir de :
      - description du repo
      - topics (tags)
      - langage principal
      - extrait du README si la description est trop courte (< 200 chars cumulés)

    Le but est de donner au LLM Éclaireur assez de matière FACTUELLE pour
    qu'il n'ait pas à inventer. Sans cet enrichissement, beaucoup de findings
    GitHub (description repo souvent vide ou < 100 chars) deviennent des
    hallucinations LLM qui plaquent le contexte projet sur n'importe quel repo.

    Tous les appels API supplémentaires (get_topics, get_readme) sont absorbés
    par requests-cache si configuré (TTL 24h par défaut sur GitHub).
    """
    parts: list[str] = []

    description = (repo.description or "").strip()
    if description:
        parts.append(f"Description: {description}")

    try:
        topics = list(repo.get_topics() or [])
        if topics:
            parts.append(f"Topics: {', '.join(topics[:10])}")
    except Exception:  # noqa: BLE001
        pass  # repos privés ou erreur API → on continue sans topics

    language = (repo.language or "").strip()
    if language:
        parts.append(f"Language: {language}")

    current_body = "\n".join(parts)

    # Fetch du README si le body cumulé est encore pauvre.
    if len(current_body) < 200:
        try:
            readme = repo.get_readme()
            raw_content = readme.decoded_content.decode("utf-8", errors="replace")
            cleaned = _strip_readme_noise(raw_content)
            # Premier chunk significatif du README, suffisant pour qualifier le projet.
            excerpt = cleaned[:1000].strip()
            if excerpt:
                parts.append(f"README excerpt:\n{excerpt}")
        except Exception:  # noqa: BLE001
            # README absent ou erreur réseau → on garde ce qu'on a.
            pass

    return "\n".join(parts)[:max_chars]


def _simplify_query_for_github(q: str) -> str:
    """
    Adapte une query Éclaireur pour le moteur de recherche GitHub.

    Retire les suffixes Reddit-style et tronque à 4 mots. GitHub Search
    fait du AND littéral entre tous les termes — moins de termes = plus
    de matches, à condition de garder les termes discriminants.

    Exemples :
        "Module LoRa SX1276 alternative" → "Module LoRa SX1276"
        "deep sleep optimization battery life" → "deep sleep optimization battery"
        "LoRaWAN class A power consumption" → "LoRaWAN class A power"
    """
    words = q.split()
    cleaned = [w for w in words if w.lower().rstrip("?.,;:") not in _NOISE_SUFFIXES]
    return " ".join(cleaned[:_MAX_QUERY_WORDS])


def _build_client():
    """
    Construit un client PyGithub à partir de GITHUB_TOKEN.

    Returns:
        Une instance github.Github authentifiée, ou None si token absent
        / lib manquante. La source dégrade gracieusement dans ce cas.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        logger.warning(
            "GITHUB_TOKEN absent — source GitHub désactivée. "
            "Pour activer : créer un Personal Access Token sur "
            "https://github.com/settings/tokens (scope 'public_repo' suffit)."
        )
        return None

    try:
        from github import Auth, Github
    except ImportError:
        logger.warning("PyGithub non installé — source GitHub désactivée.")
        return None

    try:
        return Github(auth=Auth.Token(token), per_page=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Construction du client GitHub a échoué : %s", exc)
        return None


def search(
    query: str,
    min_stars: int = 5,
    max_age_days: int = 365,
    limit: int = 10,
    cache_dir: Optional[Path] = None,
    cache_ttl_hours: int = 24,
    component_hint: str = "",
    **_kwargs,  # accepte les kwargs spécifiques aux autres sources
) -> list[RawFinding]:
    """
    Recherche des repos GitHub liés à une query.

    Filtres appliqués côté serveur GitHub :
        - étoiles ≥ min_stars
        - dernier push dans les max_age_days derniers jours
        - tri par étoiles décroissantes

    Args:
        query:           Terme de recherche (ex. "BME280 driver", "deep sleep ESP32").
        min_stars:       Filtre dur sur la popularité du repo.
        max_age_days:    Filtre dur sur l'activité récente (basé sur 'pushed').
        limit:           Nombre maximum de résultats à retourner.
        cache_dir:       Cache HTTP partagé entre sources.
        cache_ttl_hours: TTL du cache.
        component_hint:  Composant qui a inspiré la requête (traçabilité).

    Returns:
        Liste de RawFinding (score = stars, source_type = "community").
        Liste vide en cas d'absence de token, erreur réseau, ou rate limit.
    """
    global _last_request_time

    if cache_dir is not None:
        install_cache_once(cache_dir, cache_ttl_hours)

    g = _build_client()
    if g is None:
        return []

    # Politesse — pause minimale entre requêtes vraies (le cache absorbe le reste).
    now = time.monotonic()
    wait = _MIN_INTERVAL_S - (now - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.monotonic()

    # Adaptation de la query pour GitHub Search (suppression suffixes, troncature).
    github_query = _simplify_query_for_github(query)
    if not github_query.strip():
        return []  # query devenue vide après nettoyage → rien à chercher

    # Construction de la query GitHub avec filtres serveur.
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    full_query = f"{github_query} stars:>={min_stars} pushed:>={cutoff_date}"

    findings: list[RawFinding] = []

    try:
        results = g.search_repositories(query=full_query, sort="stars", order="desc")
        count = 0
        for repo in results:
            if count >= limit:
                break
            count += 1

            try:
                # Body enrichi : description + topics + langage + extrait README si trop court.
                # Évite que le LLM Éclaireur hallucine sur les repos à description vide.
                body = _build_rich_body(repo)
                pushed_ts = repo.pushed_at.timestamp() if repo.pushed_at else 0.0
                findings.append(
                    RawFinding(
                        title=repo.name or repo.full_name,
                        body=body,
                        url=repo.html_url,
                        score=int(repo.stargazers_count or 0),
                        created_utc=float(pushed_ts),
                        # On utilise le champ "subreddit" comme sous-source générique :
                        # ici, le nom complet owner/repo permet de retracer l'origine.
                        subreddit=repo.full_name,
                        source_type="community",
                        query=query,
                        component_hint=component_hint,
                        extra={
                            "language": repo.language or "",
                            "forks": int(repo.forks_count or 0),
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # Un repo qui pète ne casse pas la query entière.
                logger.debug("Repo skippé (parsing) : %s", exc)
                continue

    except Exception as exc:  # noqa: BLE001
        # Couvre les rate limits, erreurs réseau, query invalide.
        logger.warning("GitHub search '%s' a échoué : %s", query, exc)
        return []

    logger.debug("GitHub search '%s' → %d repos", query, len(findings))
    return findings
