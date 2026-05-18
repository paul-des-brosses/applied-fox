"""
Agent Éclaireur — Recherche et filtrage des findings.

Responsabilités :
    1. Dériver des requêtes ciblées à partir de la fiche projet (.md).
    2. Interroger les sources actives (au Jalon 3 : Reddit uniquement).
    3. Appliquer le filtre déterministe en amont du LLM (règle non négociable).
    4. Filtrer les findings déjà vus (mode incrémental).
    5. Structurer les findings survivants en objets Finding (JSON Pydantic).

Le filtre déterministe élimine 60-70 % du bruit AVANT d'appeler le LLM.
Critères : alignement composants/objectifs actifs, fraîcheur, score communautaire,
déduplication par hash, findings déjà présentés.

Implémentation : Jalon 3 (Reddit seul) → Jalon 4 (toutes les sources).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from src.agents._anchoring import (
    GENERIC_DENY_AS_ANCHOR,
    MIN_TOKEN_LEN,
    classify_components,
    project_alignment_tokens,
    project_strong_anchors,
    tokenize,
)
from src.models import ComponentClassification, Finding, ProjectModel
from src.sources import reddit as reddit_source
from src.sources.reddit import RawFinding

# Alias rétro-compatibles pour les tests et le simulateur de filtres qui
# importent ces noms en privé. Toute la logique vit désormais dans _anchoring.
_GENERIC_DENY_AS_ANCHOR = GENERIC_DENY_AS_ANCHOR
_MIN_TOKEN_LEN = MIN_TOKEN_LEN
_tokenize = tokenize
_project_alignment_tokens = project_alignment_tokens
_project_strong_anchors = project_strong_anchors

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

# Angles d'analyse acceptés (alignés avec le Literal de models.Finding).
_VALID_ANGLES = {"perf", "price", "supply", "energy", "regulation", "obsolescence"}

# Tokens minimaux pour le matching d'alignement composants.
# On exige au moins 3 caractères pour éviter les faux positifs ("3D" → "D" trop court).
_MIN_TOKEN_LEN = 3


# ─────────────────────────────────────────────────────────────
# Génération de requêtes
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Patterns d'extraction pour requêtes par objectif / contrainte
# ─────────────────────────────────────────────────────────────
# Chaque pattern regex (FR + EN) déclenche une liste de queries en anglais
# (langue dominante des sources Reddit/GitHub/RSS).
# Le but : capturer les *patterns techniques transverses* que le générateur
# composant-centrique manque ("deep sleep optimization", "IP65 enclosure", etc.).

_OBJECTIVE_PATTERNS: list[tuple[str, list[str]]] = [
    # Autonomie / durée de vie batterie
    (r"\b(autonomi|autonomy|battery\s+life|durée\s+de\s+vie)\w*\b", [
        "deep sleep optimization battery life",
        "low power MCU long battery autonomy",
        "ultra low power embedded design",
    ]),
    # Consommation / low power
    (r"\b(low\s+power|faible\s+consomm|basse\s+consomm|µa|microa\w*|deep\s+sleep)\b", [
        "deep sleep current consumption microamps",
        "RTC memory wifi fast reconnect",
        "ESP32 low power tips",
    ]),
    # Solaire / panneau
    (r"\b(solaire|solar\s+pan|photovoltaï|photovoltaic)\w*\b", [
        "solar panel MPPT charging IoT",
        "solar powered weather station design",
    ]),
    # LoRa / LoRaWAN (recherche transverse au-delà du module spécifique)
    (r"\b(loraw?an?)\b", [
        "LoRaWAN class A power consumption",
        "LoRa duty cycle regulation europe",
        "SX1262 vs SX1276 comparison",
    ]),
    # Outdoor / extérieur / IP rating
    (r"\b(outdoor|extéri|IP\d{2}|enclosure|boîtier|boitier)\w*\b", [
        "outdoor weather enclosure IP rated",
        "IP65 IP67 housing 3D printed embedded",
    ]),
    # GPS / GNSS
    (r"\b(gps|gnss)\b", [
        "low power GPS module embedded",
        "GPS module hot start cold start",
    ]),
    # Précision / accuracy
    (r"\b(précision|accuracy|precision|calibrat)\w*\b", [
        "sensor calibration accuracy embedded",
    ]),
    # Transmission longue distance
    (r"\b(transmission|longue\s+distance|range|portée|portee)\b", [
        "long range wireless IoT low power",
    ]),
]


def _extract_pattern_queries(
    text: str,
    project: ProjectModel,
    seen_queries: set[str],
) -> list[tuple[str, str]]:
    """
    Extrait des requêtes techniques transverses depuis un texte d'objectif
    ou de contrainte, en cherchant les patterns techniques connus.

    Le hint utilisé pointe vers le composant critique le plus mentionné dans
    le texte, à défaut le premier composant critique du projet (l'alignement
    filtre ensuite ce qui n'est pas pertinent).

    Args:
        text:         Texte libre (objectif ou contrainte).
        project:      ProjectModel pour résoudre les composants mentionnés.
        seen_queries: Set partagé entre appels pour éviter les doublons.

    Returns:
        Liste de tuples (query, component_hint) nouvellement ajoutés.
    """
    text_lower = text.lower()

    # Hint : nom du composant cité dans le texte, sinon 1er composant critique.
    hint = ""
    for c in project.composants:
        if c.nom and c.nom.lower() in text_lower:
            hint = c.nom
            break
    if not hint:
        for c in project.composants:
            if c.role_pipeline == "critique" and c.nom:
                hint = c.nom
                break
    if not hint and project.composants:
        hint = project.composants[0].nom or ""

    extracted: list[tuple[str, str]] = []
    for pattern, query_list in _OBJECTIVE_PATTERNS:
        if re.search(pattern, text_lower):
            for q in query_list:
                key = q.lower()
                if key not in seen_queries:
                    seen_queries.add(key)
                    extracted.append((q, hint))
    return extracted


def _generate_queries(project: ProjectModel) -> list[tuple[str, str]]:
    """
    Génère des requêtes ciblées à partir de la fiche projet.

    Trois familles de requêtes :
      1. Par composant : {composant} alternative/review/issue/vs
         → couvre la veille produit (EOL, retours, alternatives)
      2. Par objectif actif : extraction de patterns techniques transverses
         → couvre les questions "comment faire X" (deep sleep, autonomie...)
      3. Par contrainte non négociable : extraction de patterns techniques
         → couvre les exigences imposées (IP65, certifications...)

    La famille 1 reste majoritaire en volume. Les familles 2 et 3 corrigent
    la cécité du Jalon 3 sur les patterns techniques transverses (cf.
    docs/evaluations/jalon4_rss_reddit_eval_2026-05-11.md).

    Returns:
        Liste de tuples (query, component_hint). Le hint sert à tracer
        quelle requête a produit quel finding pour l'alignement ultérieur.
    """
    queries: list[tuple[str, str]] = []
    seen: set[str] = set()  # déduplication globale (case-insensitive)

    # 1. Par composant
    suffixes = ["alternative", "review", "issue", "vs"]
    for c in project.composants:
        if not c.nom or len(c.nom) < _MIN_TOKEN_LEN:
            continue
        for suffix in suffixes:
            q = f"{c.nom} {suffix}"
            key = q.lower()
            if key not in seen:
                seen.add(key)
                queries.append((q, c.nom))

    # 2. Par objectif actif
    for obj in project.objectifs_actifs:
        queries.extend(_extract_pattern_queries(obj, project, seen))

    # 3. Par contrainte non négociable
    for cnn in project.contraintes_non_negociables:
        queries.extend(_extract_pattern_queries(cnn, project, seen))

    return queries


# ─────────────────────────────────────────────────────────────
# Hash stable d'un finding (pour mode incrémental + dédup)
# ─────────────────────────────────────────────────────────────


def finding_hash(component: str, title: str, source_url: str) -> str:
    """
    Hash stable d'un finding sur 12 caractères hexadécimaux.

    Utilisé pour :
        - le champ Finding.id (contrat models.Finding) ;
        - la déduplication cross-query ;
        - le mode incrémental (`[projet]_seen.json`).

    Le format est inscrit dans models.Finding et docs/DECISIONS.md §9.
    """
    raw = f"{component}|{title}|{source_url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────
# Filtres déterministes
# ─────────────────────────────────────────────────────────────
#
# La tokenisation, la liste deny et la construction des anchors ont été
# extraites dans `src/agents/_anchoring.py` pour partage avec le Juge.
# Les fonctions de filtrage ci-dessous utilisent ces utilitaires partagés.


def filter_alignment(
    findings: list[RawFinding], project: ProjectModel
) -> tuple[list[RawFinding], int]:
    """
    Garde uniquement les findings dont le titre OU le component_hint
    partage au moins un token SPÉCIFIQUE avec le projet (composants/stack/objectifs).

    Un token spécifique = présent dans la fiche projet ET pas dans la liste
    déterministe `_GENERIC_DENY_AS_ANCHOR` (esp32, mosfet, lora, etc.). Cela
    évite que "NeoPixel Clock ESP32" passe juste parce qu'il contient "esp32".

    Calibré post-éval Jalon 8 — cf. `jalon8_pertinence_multi_projets`.

    Returns:
        (findings_kept, count_rejected)
    """
    strong_anchors = _project_strong_anchors(project)
    kept: list[RawFinding] = []
    rejected = 0
    for f in findings:
        finding_tokens = _tokenize(f.title) | _tokenize(f.component_hint)
        if finding_tokens & strong_anchors:
            kept.append(f)
        else:
            rejected += 1
    return kept, rejected


def filter_freshness(
    findings: list[RawFinding], max_age_days: int
) -> tuple[list[RawFinding], int]:
    """Rejette les findings plus anciens que max_age_days."""
    now_utc = datetime.now(timezone.utc).timestamp()
    cutoff = now_utc - (max_age_days * 86400)
    kept = [f for f in findings if f.created_utc >= cutoff]
    return kept, len(findings) - len(kept)


def filter_score(
    findings: list[RawFinding], min_score: int
) -> tuple[list[RawFinding], int]:
    """
    Rejette les findings communautaires dont le score est < min_score.

    Note : le filtre de score ne s'applique PAS aux sources éditoriales
    (source_type="news", "marketplace") car elles n'ont pas de score
    communautaire — leur curation est faite à la source.
    """
    kept = [
        f for f in findings
        if f.source_type != "community" or f.score >= min_score
    ]
    return kept, len(findings) - len(kept)


def filter_dedup(
    findings: list[RawFinding],
) -> tuple[list[RawFinding], int]:
    """
    Déduplication par hash (component_hint + title + url).
    Conserve la première occurrence rencontrée.
    """
    seen: set[str] = set()
    kept: list[RawFinding] = []
    for f in findings:
        h = finding_hash(f.component_hint or f.title, f.title, f.url)
        if h in seen:
            continue
        seen.add(h)
        kept.append(f)
    return kept, len(findings) - len(kept)


# ─────────────────────────────────────────────────────────────
# Mode incrémental : state file
# ─────────────────────────────────────────────────────────────


def _state_file(project_name: str, state_dir: Path) -> Path:
    """Chemin du fichier de state pour un projet donné."""
    slug = re.sub(r"[^a-z0-9]+", "_", project_name.lower()).strip("_") or "project"
    return state_dir / f"{slug}_seen.json"


def load_seen(project_name: str, state_dir: Path) -> set[str]:
    """Charge l'ensemble des hashs de findings déjà présentés à l'utilisateur."""
    path = _state_file(project_name, state_dir)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict):
            return set(data.get("seen_hashes", []))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("State file illisible (%s) : %s", path, exc)
    return set()


def save_seen(
    project_name: str,
    state_dir: Path,
    seen_hashes: set[str],
) -> None:
    """Persiste l'ensemble des hashs vus (atomique : write to tmp then rename)."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_file(project_name, state_dir)
    payload = {
        "project": project_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "seen_hashes": sorted(seen_hashes),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def filter_incremental(
    findings: list[RawFinding], seen_hashes: set[str]
) -> tuple[list[RawFinding], int]:
    """Rejette les findings dont le hash est déjà dans seen_hashes."""
    kept: list[RawFinding] = []
    rejected = 0
    for f in findings:
        h = finding_hash(f.component_hint or f.title, f.title, f.url)
        if h in seen_hashes:
            rejected += 1
        else:
            kept.append(f)
    return kept, rejected


# ─────────────────────────────────────────────────────────────
# Pipeline déterministe complet
# ─────────────────────────────────────────────────────────────


def _cap_findings_by_source(
    findings: list[RawFinding], max_total: int
) -> tuple[list[RawFinding], int]:
    """
    Limite le nombre total de findings tout en préservant l'équilibre entre sources.

    Stratégie :
        1. Si len(findings) <= max_total, ne fait rien.
        2. Sinon, répartit le budget entre les source_type présents (community,
           news, marketplace), proportionnellement à leur représentation initiale.
        3. Au sein de chaque source_type, trie par score décroissant et garde
           les top N. Pour les sources sans score (RSS, source_type=news),
           ordre stable préservé.
        4. Si une source a moins de findings que son budget, le reliquat est
           redistribué aux autres sources (best score d'abord).

    Returns:
        (findings_kept, n_rejected_by_cap)
    """
    if len(findings) <= max_total:
        return findings, 0

    from collections import defaultdict

    by_source: dict[str, list[RawFinding]] = defaultdict(list)
    for f in findings:
        by_source[f.source_type].append(f)

    # Budget proportionnel à la distribution initiale
    total = len(findings)
    budgets: dict[str, int] = {}
    for src, src_findings in by_source.items():
        share = len(src_findings) / total
        budgets[src] = max(1, int(round(share * max_total)))

    # Sélection par source (tri par score desc — stable pour les score=0)
    selected: list[RawFinding] = []
    leftover: list[RawFinding] = []
    for src, src_findings in by_source.items():
        sorted_src = sorted(src_findings, key=lambda f: f.score, reverse=True)
        cap = budgets[src]
        selected.extend(sorted_src[:cap])
        leftover.extend(sorted_src[cap:])

    # Si on est sous max_total à cause des arrondis, on remplit avec le best reliquat
    if len(selected) < max_total and leftover:
        leftover.sort(key=lambda f: f.score, reverse=True)
        gap = max_total - len(selected)
        selected.extend(leftover[:gap])

    # Si on est au-dessus (arrondis), on coupe au global par score desc
    if len(selected) > max_total:
        selected.sort(key=lambda f: f.score, reverse=True)
        selected = selected[:max_total]

    rejected = len(findings) - len(selected)
    return selected, rejected


def apply_deterministic_filter(
    raw_findings: list[RawFinding],
    project: ProjectModel,
    config: dict,
    seen_hashes: set[str],
) -> tuple[list[RawFinding], dict]:
    """
    Applique tous les filtres déterministes dans l'ordre.

    Returns:
        (findings_kept, stats) où stats contient les comptes par étape de rejet.
    """
    filters_cfg: dict = config.get("filters", {})
    sources_cfg: dict = config.get("sources", {})
    reddit_cfg: dict = sources_cfg.get("reddit", {})
    reddit_filters: dict = reddit_cfg.get("filters", {})

    initial = len(raw_findings)
    stats = {
        "initial": initial,
        "rejected_alignment": 0,
        "rejected_freshness": 0,
        "rejected_score": 0,
        "rejected_dedup": 0,
        "rejected_incremental": 0,
        "rejected_cap": 0,
        "kept": 0,
    }
    current = raw_findings

    # 1. Score (premier filtre, le moins coûteux)
    min_score = int(reddit_filters.get("min_score", 5))
    current, n = filter_score(current, min_score)
    stats["rejected_score"] = n

    # 2. Fraîcheur
    if filters_cfg.get("enable_freshness_check", True):
        max_age = int(reddit_filters.get("max_age_days", 365))
        current, n = filter_freshness(current, max_age)
        stats["rejected_freshness"] = n

    # 3. Alignement composants/objectifs (non négociable, cf. CLAUDE.md règle 5)
    if filters_cfg.get("enable_alignment_check", True):
        current, n = filter_alignment(current, project)
        stats["rejected_alignment"] = n

    # 4. Déduplication
    if filters_cfg.get("enable_dedup", True):
        current, n = filter_dedup(current)
        stats["rejected_dedup"] = n

    # 5. Mode incrémental
    if filters_cfg.get("enable_incremental_mode", True):
        current, n = filter_incremental(current, seen_hashes)
        stats["rejected_incremental"] = n

    # 6. Cap final pour borner le temps LLM en aval (Éclaireur structuration
    # + Intégrateur + Juge). Préserve l'équilibre entre sources.
    # Désactivé si max_after_filter est 0, None, ou absent.
    max_after = filters_cfg.get("max_after_filter")
    if max_after and max_after > 0:
        current, n = _cap_findings_by_source(current, int(max_after))
        stats["rejected_cap"] = n

    stats["kept"] = len(current)
    if initial > 0:
        stats["filter_ratio"] = round(1 - len(current) / initial, 3)
    else:
        stats["filter_ratio"] = 0.0

    return current, stats


# ─────────────────────────────────────────────────────────────
# Structuration LLM (RawFinding → Finding)
# ─────────────────────────────────────────────────────────────


_STRUCTURE_PROMPT = """Tu es l'Éclaireur, un agent de veille technologique.
Tâche : produire une fiche structurée JSON à partir d'un post brut, pour aider l'ingénieur sur son projet.

═══ PROJET (contexte seulement, ne pas plaquer sur le post) ═══
Nom : {project_name}
Objectifs actifs :
{objectifs}
Composant ciblé par la requête : {component}

═══ POST BRUT ═══
Source : {source_label} (type : {source_type})
Titre : {title}
Contenu : {body}

═══ RÈGLES STRICTES ═══

1. ANCRAGE FACTUEL — Ta description s'appuie UNIQUEMENT sur ce que dit CE post.
   - N'invente PAS de faits techniques (EOL, prix, perfs, support) que le post ne mentionne pas.
   - N'utilise PAS tes connaissances générales pour spéculer sur le composant.
   - N'affirme PAS qu'un composant est obsolète, déprécié ou non supporté
     SAUF si le post le dit explicitement.
   - **NE PLAQUE PAS le contexte projet sur le post.** Si le projet vise
     "6 mois d'autonomie sur batterie LiPo + solaire" et que le post parle
     d'un repo GitHub sans lien avec l'autonomie, NE dis JAMAIS que ce repo
     "supporte 6 mois d'autonomie" ou "fonctionne avec LiPo + solaire" —
     c'est de la projection, pas un fait du post.
   - Décris UNIQUEMENT ce qui est DANS le post (titre, description, README excerpt
     pour GitHub). Le projet est là pour le CONTEXTE seulement, jamais pour
     enrichir la description du post.

2. INCERTITUDE — Si le post est trop pauvre, hors-sujet, ou que tu n'arrives pas à en
   extraire un fait utile pour le projet, écris EXACTEMENT :
     "description": "Aucun apport pertinent."
   C'est PRÉFÉRABLE à inventer une description.

3. CHOIX D'ANGLE — Un seul angle parmi cette liste (utilise la définition pour choisir) :
   - perf         : amélioration de performance technique (précision, vitesse, fonctionnalités)
   - energy       : consommation, autonomie, gestion d'énergie, deep sleep
   - obsolescence : EOL, NRND, support discontinué — UNIQUEMENT si le post le mentionne explicitement
   - regulation   : norme, certification, conformité, sécurité réglementaire
   - supply       : disponibilité, pénurie, distributeur, sourcing
   - price        : prix, coût, alternative moins chère

4. FORMAT — JSON strict, exactement deux clés :
   {{"angle": "...", "description": "..."}}
   - Aucun markdown, aucun commentaire, aucun préfixe.
   - Description max 2 lignes, factuelle, ancrée dans CE post.
   - Pas de paraphrase du titre. Apporte l'information utile au-delà du titre.

═══ EXEMPLES ═══

BON exemple :
  Titre : "[Review Request] STM32U073 + E22 (SX1262)"
  → {{"angle": "perf", "description": "Design d'exemple utilisant le module LoRa SX1262 à la place du SX1276, montrant une approche basse-consommation moderne."}}

BON exemple (post pauvre) :
  Titre : "Help with my project"
  Contenu : "Hey guys, can someone help?"
  → {{"angle": "perf", "description": "Aucun apport pertinent."}}

MAUVAIS exemple à éviter (invention de fait) :
  Titre : "Flight Computer HELP" (mentionne BME280 dans le body)
  → Ne PAS écrire {{"angle": "obsolescence", "description": "BME280 may no longer be supported"}}
     si le post ne dit JAMAIS que le BME280 est obsolète. C'est une hallucination.

MAUVAIS exemple à éviter (plaquage du contexte projet) :
  Projet : Station Météo ESP32, objectif "6 mois d'autonomie sur batterie LiPo + solaire"
  Post GitHub : "Repo: awesome-embedded-software. Description: Curated list of embedded libraries.
                  Topics: embedded, awesome, list. README excerpt: A curated list of awesome embedded
                  resources..."
  → Ne PAS écrire {{"angle": "energy", "description": "Cette ressource dispose d'une batterie LiPo 2000 mAh
     et d'un panneau solaire 5W qui fournit une autonomie de 6 mois"}}
     C'est une projection du projet sur le repo. Le repo est une liste de liens, point.
  → Écrire plutôt {{"angle": "perf", "description": "Liste curatée de bibliothèques embedded — peut
     contenir des références utiles pour la stack du projet."}}
     OU si tu ne vois aucun apport spécifique : {{"angle": "perf", "description": "Aucun apport pertinent."}}
"""


def _extract_json_object(text: str) -> Optional[dict]:
    """
    Extrait un objet JSON depuis la sortie LLM, tolérant aux préfixes/suffixes.
    Retourne None si rien n'est trouvable.
    """
    if not text:
        return None
    # Cherche la première { ... } équilibrée.
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


# ─── Heuristique déterministe de mapping d'angle ──────────────────────
# Calibré post-éval Jalon 8 v1.3 : on ne demande plus au LLM 7B Q4 de
# choisir l'angle (il halluciné). Ces mots-clés sont triés par priorité
# descendante. Au pire on retombe sur "perf" qui est l'angle par défaut.
_ANGLE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("obsolescence", ["eol", "nrnd", "end of life", "discontinued",
                      "deprecated", "obsolete", "end-of-life", "no longer",
                      "last time buy", "ltb"]),
    ("regulation",   ["certification", "iso ", "iec ", "ce mark", "ce marquage",
                      "fcc", "iso13849", "iso 13849", "rohs ", "regulation",
                      "norme", "safety functional", "safety-rated"]),
    ("supply",       ["supply", "shortage", "stock out", "out of stock",
                      "distributor", "lead time", "disponibilit",
                      "approvisionnement"]),
    ("price",        ["price", "cost", "cheap", "$", "€", "euros", "dollar",
                      "prix", "coût", "budget", "low cost", "low-cost"]),
    ("energy",       ["battery", "low power", "low-power", "sleep mode",
                      "deep sleep", "autonomy", "autonomie", "consommation",
                      "energy", "énergie", "uw", "µa", "lifetime", "coin cell",
                      "solar", "harvest", "lipo", "lifepo4"]),
]


def _infer_angle(text: str) -> str:
    """
    Inférence déterministe de l'angle par mots-clés sur le contenu brut.
    Ordre de priorité dans `_ANGLE_KEYWORDS`. Fallback "perf" (le plus neutre).
    """
    t = text.lower()
    for angle, keywords in _ANGLE_KEYWORDS:
        if any(kw in t for kw in keywords):
            return angle
    return "perf"


def _truncate_description(body: str, max_len: int = 320) -> str:
    """
    Tronque proprement un body de post à la fin d'une phrase si possible.
    Si le body est vide, retourne chaîne vide (le caller fera le fallback).
    """
    if not body:
        return ""
    cleaned = re.sub(r"\s+", " ", body.strip())
    if len(cleaned) <= max_len:
        return cleaned
    snippet = cleaned[:max_len]
    last_dot = snippet.rfind(".")
    # Si on trouve une fin de phrase au-delà de la moitié, on coupe là.
    if last_dot > max_len // 2:
        return snippet[: last_dot + 1]
    return snippet.rstrip() + "…"


def _structure_one(
    raw: RawFinding,
    project: ProjectModel,
    config: dict,
    max_retries: int = 2,
) -> Optional[Finding]:
    """
    Structuration RawFinding → Finding.

    Mode par défaut : déterministe (post-éval Jalon 8 v1.3, cf.
    `docs/evaluations/jalon8_pertinence_iterations`). Le LLM 7B Q4
    halluciné systématiquement à cette étape (description plaquant les
    objectifs du projet sur n'importe quel post), polluant tous les
    agents en aval.

    Bascule possible via config `sources.eclaireur.structuration_mode: llm`
    pour utiliser l'ancien comportement LLM (utile pour comparaison ou
    si on passe à un modèle plus gros qui suit vraiment le prompt).

    Returns:
        Le Finding structuré, ou None si rejet (body vide, etc.).
    """
    mode = (
        config.get("sources", {})
        .get("eclaireur", {})
        .get("structuration_mode", "deterministic")
    )

    if mode == "deterministic":
        return _structure_one_deterministic(raw, project)

    return _structure_one_llm(raw, project, config, max_retries)


def _structure_one_deterministic(
    raw: RawFinding,
    project: ProjectModel,
) -> Optional[Finding]:
    """
    Structuration sans appel LLM.

    - angle : inféré par mots-clés sur title+body (cf. `_infer_angle`).
    - description : body tronqué à la fin d'une phrase (cf. `_truncate_description`),
      avec fallback sur le title si le body est vide.
    - component_concerned : raw.component_hint (déjà déterministe en amont).

    Pas de risque d'hallucination : le LLM n'invente plus de "Migration X
    réduit conso d'eau de 40%" — la description est le contenu brut du post.
    """
    component = raw.component_hint or "?"
    body = raw.body or ""
    text_for_angle = f"{raw.title}\n{body}"
    angle = _infer_angle(text_for_angle)
    description = _truncate_description(body)
    if not description:
        # Fallback : titre seul (mieux que de jeter le finding).
        description = raw.title

    # Préserve le vrai source_type du raw (community/news/marketplace), ne pas
    # forcer "community" comme l'ancien code.
    valid_types = {"manufacturer", "community", "marketplace", "paper", "news"}
    source_type = raw.source_type if raw.source_type in valid_types else "community"

    # Classification déterministe des composants mentionnés (Niveau 2).
    # Permet aux agents en aval de distinguer composants connus vs nouveaux
    # sans rejouer l'extraction et sans risquer d'halluciner sur des
    # références opaques (BQ25616, MAX-M10S, etc.).
    in_proj, new_mentioned = classify_components(f"{raw.title}\n{body}", project)
    classification = ComponentClassification(
        in_project=in_proj,
        new_mentioned=new_mentioned,
    )

    return Finding(
        id=finding_hash(component, raw.title, raw.url),
        title=raw.title,
        component_concerned=component,
        angle=angle,  # type: ignore[arg-type]
        description=description,
        source_url=raw.url,
        source_type=source_type,  # type: ignore[arg-type]
        raw_data={
            "subreddit": raw.subreddit,
            "score": raw.score,
            "created_utc": raw.created_utc,
            "query": raw.query,
            **raw.extra,
        },
        component_classification=classification,
    )


def _structure_one_llm(
    raw: RawFinding,
    project: ProjectModel,
    config: dict,
    max_retries: int = 2,
) -> Optional[Finding]:
    """
    Ancienne structuration LLM. Conservée pour comparaison via config
    `sources.eclaireur.structuration_mode: llm`. Source d'hallucinations
    sur 7B Q4 — cf. eval v1.3.
    """
    from src.llm import get_llm

    component = raw.component_hint or "?"
    # Label source contextuel : "r/embedded (score 42)" pour Reddit, "Hackaday" pour RSS, etc.
    if raw.source_type == "community":
        source_label = f"r/{raw.subreddit} (score {raw.score})"
    elif raw.source_type == "news":
        source_label = raw.subreddit  # nom du flux RSS
    else:
        source_label = raw.subreddit or raw.source_type

    prompt = _STRUCTURE_PROMPT.format(
        project_name=project.nom_projet,
        objectifs="\n".join(f"- {o}" for o in project.objectifs_actifs),
        component=component,
        title=raw.title,
        body=(raw.body or "")[:1000],
        source_label=source_label,
        source_type=raw.source_type,
    )

    llm = get_llm("eclaireur", config)

    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            full_prompt = prompt
            if attempt > 0 and last_error:
                full_prompt += (
                    f"\n\nTa réponse précédente était invalide : {last_error}\n"
                    f"Réponds STRICTEMENT en JSON valide cette fois."
                )
            response = llm.invoke(full_prompt)
            content = getattr(response, "content", str(response))

            data = _extract_json_object(content)
            if not data:
                last_error = "JSON introuvable dans la réponse"
                continue

            angle = (data.get("angle") or "").strip().lower()
            description = (data.get("description") or "").strip()

            if angle not in _VALID_ANGLES:
                last_error = f"angle '{angle}' invalide"
                continue
            if not description:
                last_error = "description vide"
                continue

            # Si le LLM a explicitement signalé l'absence d'apport, on rejette.
            if "aucun apport" in description.lower():
                return None

            # Classification déterministe des composants (Niveau 2),
            # symétrique au mode déterministe.
            in_proj, new_mentioned = classify_components(
                f"{raw.title}\n{description}", project
            )
            classification = ComponentClassification(
                in_project=in_proj,
                new_mentioned=new_mentioned,
            )

            finding = Finding(
                id=finding_hash(component, raw.title, raw.url),
                title=raw.title,
                component_concerned=component,
                angle=angle,  # type: ignore[arg-type]
                description=description,
                source_url=raw.url,
                source_type="community",
                raw_data={
                    "subreddit": raw.subreddit,
                    "score": raw.score,
                    "created_utc": raw.created_utc,
                    "query": raw.query,
                    **raw.extra,
                },
                component_classification=classification,
            )
            return finding

        except ValidationError as exc:
            last_error = f"validation Pydantic : {exc.errors()[0]['msg']}"
            continue
        except Exception as exc:  # noqa: BLE001 — on veut rattraper toute erreur LLM
            logger.warning("LLM échec sur '%s' : %s", raw.title[:60], exc)
            last_error = str(exc)
            continue

    logger.warning(
        "Structuration abandonnée après %d essais (%s) : %s",
        max_retries + 1,
        last_error,
        raw.title[:80],
    )
    return None


# ─────────────────────────────────────────────────────────────
# Orchestration : run()
# ─────────────────────────────────────────────────────────────


def _resolve_path(value: str | Path) -> Path:
    """Résout les ~ et variables d'env dans un chemin de config."""
    return Path(str(value)).expanduser()


def run(
    project: ProjectModel,
    config: dict,
    run_dir: Optional[Path] = None,
) -> list[Finding]:
    """
    Exécute la phase de recherche et de filtrage pour un projet donné.

    Étapes :
        1. Génère des requêtes par composant.
        2. Interroge Reddit pour chaque requête.
        3. Applique le filtre déterministe (alignement, fraîcheur, score, dedup, incrémental).
        4. Pour chaque finding survivant : appelle le LLM pour produire un Finding structuré.
        5. Persiste l'état incrémental (hashs vus).
        6. Sauvegarde les artefacts (01_eclaireur_findings.json, 01_eclaireur_sources.json).

    Args:
        project: Fiche projet parsée.
        config:  Config globale (sources, filtres, modèle).
        run_dir: Dossier où écrire les artefacts. None → pas de sauvegarde sur disque.

    Returns:
        Liste de Finding structurés, prêts pour les agents en aval.
    """
    paths_cfg: dict = config.get("paths", {})
    state_dir = _resolve_path(paths_cfg.get("state_dir", "~/.applied-fox/state"))
    cache_dir = _resolve_path(paths_cfg.get("cache_dir", "~/.applied-fox/cache"))

    sources_cfg: dict = config.get("sources", {})

    # ── 1. Génération des requêtes ────────────────────────────
    queries = _generate_queries(project)
    logger.info("Éclaireur : %d requêtes générées", len(queries))

    # ── 2. Collecte multi-sources ─────────────────────────────
    # Pattern : chaque source est appelée si activée dans config.sources.<name>.
    # Dégradation gracieuse : un échec sur une source ne stoppe pas le pipeline.
    # Deux types de sources :
    #   - "queryable" (Reddit, GitHub) : on les interroge query par query.
    #   - "global"    (RSS)            : un seul fetch, pas de notion de query.
    raw_findings: list[RawFinding] = []
    queries_executed: list[str] = []
    per_source_stats: dict[str, int] = {}

    # 2a. Sources queryable
    reddit_cfg: dict = sources_cfg.get("reddit", {})
    if reddit_cfg.get("enabled", True):
        n_before = len(raw_findings)
        reddit_filters = reddit_cfg.get("filters", {})
        for query, hint in queries:
            try:
                results = reddit_source.search(
                    query=query,
                    subreddits=None,
                    min_score=int(reddit_filters.get("min_score", 5)),
                    max_age_days=int(reddit_filters.get("max_age_days", 365)),
                    limit=int(reddit_cfg.get("limit_per_query", 15)),
                    user_agent=reddit_cfg.get("user_agent", "applied-fox-agent-ia/0.1"),
                    cache_dir=cache_dir,
                    cache_ttl_hours=int(reddit_cfg.get("cache_ttl_hours", 12)),
                    component_hint=hint,
                )
                raw_findings.extend(results)
                queries_executed.append(f"reddit:{query}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Source reddit a échoué sur '%s' : %s", query, exc)
        per_source_stats["reddit"] = len(raw_findings) - n_before
        logger.info("Source reddit : %d findings bruts", per_source_stats["reddit"])

    github_cfg: dict = sources_cfg.get("github", {})
    if github_cfg.get("enabled", False):
        n_before = len(raw_findings)
        try:
            from src.sources import github as github_source
        except ImportError as exc:
            logger.warning("Source github indisponible (import) : %s", exc)
            github_source = None
        if github_source is not None:
            github_filters = github_cfg.get("filters", {})
            for query, hint in queries:
                try:
                    results = github_source.search(
                        query=query,
                        min_stars=int(github_filters.get("min_stars", 5)),
                        max_age_days=int(github_filters.get("max_age_days", 365)),
                        limit=int(github_cfg.get("limit_per_query", 5)),
                        cache_dir=cache_dir,
                        cache_ttl_hours=int(github_cfg.get("cache_ttl_hours", 24)),
                        component_hint=hint,
                    )
                    raw_findings.extend(results)
                    queries_executed.append(f"github:{query}")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Source github a échoué sur '%s' : %s", query, exc)
        per_source_stats["github"] = len(raw_findings) - n_before
        logger.info("Source github : %d findings bruts", per_source_stats["github"])

    # 2b. Sources global fetch
    rss_cfg: dict = sources_cfg.get("rss", {})
    if rss_cfg.get("enabled", False):
        n_before = len(raw_findings)
        try:
            from src.sources import rss as rss_source
            rss_filters = rss_cfg.get("filters", {})
            results = rss_source.search(
                feeds=rss_cfg.get("feeds"),
                max_age_days=int(rss_filters.get("max_age_days", 90)),
                cache_dir=cache_dir,
                cache_ttl_hours=int(rss_cfg.get("cache_ttl_hours", 24)),
            )
            raw_findings.extend(results)
            queries_executed.append("rss:global_fetch")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Source rss a échoué : %s", exc)
        per_source_stats["rss"] = len(raw_findings) - n_before
        logger.info("Source rss : %d findings bruts", per_source_stats["rss"])

    logger.info(
        "Éclaireur : %d findings bruts cumulés sur %d source(s) active(s)",
        len(raw_findings), len(per_source_stats),
    )

    # ── 3. Filtre déterministe ────────────────────────────────
    seen_hashes = load_seen(project.nom_projet, state_dir)
    kept_raw, stats = apply_deterministic_filter(
        raw_findings, project, config, seen_hashes
    )
    logger.info(
        "Éclaireur : %d findings retenus après filtre (ratio rejet %.0f%%)",
        len(kept_raw),
        stats["filter_ratio"] * 100,
    )

    # ── 4. Structuration LLM ──────────────────────────────────
    structured: list[Finding] = []
    structured_failed = 0
    for raw in kept_raw:
        finding = _structure_one(raw, project, config)
        if finding is None:
            structured_failed += 1
            continue
        structured.append(finding)

    stats["structured_success"] = len(structured)
    stats["structured_failed"] = structured_failed

    # ── 5. Mise à jour de l'état incrémental ──────────────────
    new_hashes = {f.id for f in structured}
    save_seen(project.nom_projet, state_dir, seen_hashes | new_hashes)

    # ── 6. Sauvegarde des artefacts ───────────────────────────
    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)

        findings_path = run_dir / "01_eclaireur_findings.json"
        findings_path.write_text(
            json.dumps(
                [f.model_dump(mode="json") for f in structured],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        sources_path = run_dir / "01_eclaireur_sources.json"
        sources_path.write_text(
            json.dumps(
                {
                    "project": project.nom_projet,
                    "queries_executed": queries_executed,
                    "per_source_stats": per_source_stats,
                    "filter_stats": stats,
                    "raw_findings": [
                        {
                            "title": r.title,
                            "url": r.url,
                            "score": r.score,
                            "subreddit": r.subreddit,
                            "source_type": r.source_type,
                            "query": r.query,
                            "component_hint": r.component_hint,
                            "created_utc": r.created_utc,
                        }
                        for r in raw_findings
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    return structured
