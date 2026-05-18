"""
Simulateur déterministe pour évaluer les filtres post-Juge candidats.

Charge les artefacts de runs existants (findings + verdicts Juge + suggestions
retenues), applique des filtres déterministes simulés, et compare au verdict
OPUS humain pour calculer precision/recall.

Pas de LLM. Pas de pipeline rejoué. Itération en quelques secondes.

Usage :
    python scripts/eval_filters.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.agents.eclaireur import _GENERIC_DENY_AS_ANCHOR, _MIN_TOKEN_LEN
from src.models import Finding, IntegrationVerdict, JudgeVerdict, ProjectModel
from src.validation.structural import parse_and_validate


# ─────────────────────────────────────────────────────────────
# VERDICTS OPUS — labellisation manuelle des 16 suggestions
# ─────────────────────────────────────────────────────────────

# Labels : "high" (vraiment aligné) | "partial" | "non_aligned"
# Matching par début de titre pour robustesse.
OPUS_LABELS: dict[str, str] = {
    # Greenhouse — 5 suggestions
    "UPDATED LEARN GUIDE: Adafruit VCNL4030": "non_aligned",
    "Schematic review ESP32-S3 custom module": "partial",
    "I spent 3 months avoiding cloud APIs": "partial",
    "SoilMoisureLogger": "high",
    "Adafruit_CircuitPython_SHT31D": "high",

    # Tracker LoRa — 4 suggestions
    "Tell your war stories about the last time": "non_aligned",
    "Running an STM32 Forever on Indoor Light": "high",
    "DevoMultiX": "non_aligned",
    "RAK3172": "partial",

    # BMS DIY — 7 suggestions
    "Is this a good method to protect accidental battery overcharging": "high",
    "Electrical Engineering Iceberg": "non_aligned",
    "Please go all the way down, RX": "non_aligned",
    "ina219": "high",
    "Fuel Gauge, a nighttime story": "partial",
    "INA219_WE": "high",
    "BluePill-Plus": "high",
}


def _opus_label(title: str) -> str | None:
    """Trouve le label OPUS pour un titre par préfixe."""
    for prefix, label in OPUS_LABELS.items():
        if title.startswith(prefix) or title.lower().startswith(prefix.lower()):
            return label
    return None


# ─────────────────────────────────────────────────────────────
# Utilitaires de normalisation
# ─────────────────────────────────────────────────────────────


def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _tokenize(text: str) -> set[str]:
    """Tokens alphanumériques minuscules de longueur >= _MIN_TOKEN_LEN."""
    if not text:
        return set()
    normalized = _strip_accents(text.lower())
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return {t for t in tokens if len(t) >= _MIN_TOKEN_LEN}


def _normalize_component(name: str) -> str:
    """ESP32-S3 → esp32s3, SHT31-D → sht31d, MH-Z19B → mhz19b."""
    n = _strip_accents(name.lower())
    return re.sub(r"[^a-z0-9]", "", n)


# ─────────────────────────────────────────────────────────────
# Bilinguisme FR/EN — concepts d'électronique embarquée
# ─────────────────────────────────────────────────────────────
#
# Les fiches projet sont en français, les sources Reddit/GitHub/RSS sont
# majoritairement en anglais. Sans dictionnaire de traduction, le filtre
# d'ancrage rejette des findings parfaitement alignés.
#
# Liste volontairement courte et limitée aux concepts d'embarqué structurants.
# Pas de mots génériques ("sensor", "module", "system") qui ramèneraient du bruit.

_FR_EN_PAIRS: dict[str, list[str]] = {
    "batterie": ["battery"],
    "batteries": ["batteries"],
    "pile": ["cell"],
    "piles": ["cells"],
    "cellule": ["cell"],
    "cellules": ["cells"],
    "autonomie": ["autonomy", "lifetime", "runtime"],
    "consommation": ["consumption"],
    "portee": ["range"],  # forme sans accent (anchors sont normalisés)
    "poids": ["weight"],
    "humidite": ["humidity", "moisture"],
    "temperature": ["temperature"],  # même mot mais formes plurielles
    "pression": ["pressure"],
    "surcharge": ["overcharge", "overcharging"],
    "decharge": ["discharge", "discharging"],
    "surchauffe": ["overheat", "overheating"],
    "surintensite": ["overcurrent"],
    "coupure": ["shutoff", "disconnect", "shutdown", "cutoff"],
    "precision": ["accuracy", "precision"],
    "equilibrage": ["balancing"],
    "arrosage": ["watering", "irrigation"],
    "boitier": ["enclosure", "housing"],
    "etancheite": ["waterproof", "watertight"],
    "antenne": ["antenna"],
    "alimentation": ["powersupply"],  # collé pour matcher tokens
}


def _expand_anchors_with_translations(anchors: set[str]) -> set[str]:
    """Ajoute les traductions EN aux anchors FR détectés. Non destructif."""
    extensions = set()
    for fr, en_list in _FR_EN_PAIRS.items():
        if fr in anchors:
            extensions.update(en_list)
    return anchors | extensions


# ─────────────────────────────────────────────────────────────
# Construction des strong_anchors d'un projet
# ─────────────────────────────────────────────────────────────


def project_strong_anchors(project: ProjectModel) -> set[str]:
    """
    Tokens spécifiques au projet, hors deny-list.

    Versions étendues vs `eclaireur._project_strong_anchors` :
    - Ajoute la forme normalisée (sht31d en plus de sht31)
    - Inclut les contraintes non négociables
    - Strip accents
    """
    anchors: set[str] = set()

    for c in project.composants:
        anchors |= _tokenize(c.nom)
        normalized = _normalize_component(c.nom)
        if len(normalized) >= 4:
            anchors.add(normalized)

    for s in project.stack_software:
        anchors |= _tokenize(s.outil)
        normalized = _normalize_component(s.outil)
        if len(normalized) >= 4:
            anchors.add(normalized)

    for obj in project.objectifs_actifs:
        anchors |= _tokenize(obj)

    for cnn in project.contraintes_non_negociables:
        anchors |= _tokenize(cnn)

    # Inclut aussi la description (souvent riche en termes techniques)
    if project.description:
        anchors |= _tokenize(project.description)

    # Et les noms d'interactions (souvent les protocoles : I2C, UART, etc.)
    for inter in project.interactions:
        anchors |= _tokenize(inter.nature or "")
        anchors |= _tokenize(inter.format or "")

    # Retire les tokens trop génériques
    strong = {a for a in anchors if a not in _GENERIC_DENY_AS_ANCHOR}
    if not strong:
        strong = anchors
    # Ajout des traductions EN pour concepts FR détectés
    return _expand_anchors_with_translations(strong)


def project_component_names(project: ProjectModel) -> list[str]:
    """Liste des noms de composants pour le détecteur de migration."""
    return [c.nom for c in project.composants]


def project_specific_numbers(project: ProjectModel) -> set[str]:
    """
    Extrait les chiffres + unités spécifiques au projet depuis les objectifs
    et CNN. Utilisé pour le détecteur anti-plaque.

    Ex: "40%", "18 mois", "12 mois", "< 60€", "< 80g".
    """
    numbers: set[str] = set()
    pattern = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(%|mois|ans?|jours?|h|min|s|"
        r"mA|µA|uA|A|mV|V|kV|W|kW|°C|°F|hPa|kPa|Pa|Hz|kHz|MHz|GHz|"
        r"km|m|cm|mm|€|\$|dB|dBm|bps|Mbps|Mo|Go|Ko|g|kg|RPM|fps|"
        r"ppm|RH|mAh|Wh)\b",
        re.IGNORECASE,
    )
    for source_text in (
        project.objectifs_actifs
        + project.contraintes_non_negociables
        + [c.nom for c in project.composants]
    ):
        for m in pattern.finditer(source_text):
            num = m.group(1)
            unit = m.group(2).lower()
            numbers.add(f"{num}{unit}")
            numbers.add(f"{num} {unit}")
    return numbers


# ─────────────────────────────────────────────────────────────
# FILTRE A — Grounding du Juge (règle 1bis déterministe)
# ─────────────────────────────────────────────────────────────


def _camel_split(text: str) -> str:
    """Insère un espace aux frontières CamelCase pour aider la tokenisation.
    "SoilMoisureLogger" → "Soil Moisure Logger"
    Utile pour les noms de repos GitHub sans séparateur.
    """
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)


def _is_specific_anchor(anchor: str) -> bool:
    """Un anchor est 'spécifique' s'il contient un chiffre OU fait >=7 caractères.
    Filtre les ancrages génériques type 'sensor', 'system', 'module', 'board'.
    """
    return bool(re.search(r'\d', anchor)) or len(anchor) >= 7


def filter_a_grounding(
    finding: Finding,
    project: ProjectModel,
    mode: str = "strict",
) -> tuple[bool, str]:
    """
    Vérifie que le finding contient au moins un ancrage du projet.
    Implémente règle 1bis du prompt Juge en déterministe.

    Modes :
        "loose"   : ≥1 anchor quelconque (anchors strong déjà filtrés)
        "strict"  : ≥1 anchor SPÉCIFIQUE (chiffres ou ≥7 chars)
        "density" : ≥1 spécifique OR ≥2 distincts

    Returns (passes_filter, reason_if_rejected).
    """
    anchors = project_strong_anchors(project)
    text = _camel_split(finding.title) + " " + _camel_split(finding.description)
    tokens = _tokenize(text)
    matches = tokens & anchors

    if mode == "loose":
        ok = len(matches) >= 1
    elif mode == "strict":
        ok = any(_is_specific_anchor(m) for m in matches)
    elif mode == "density":
        has_specific = any(_is_specific_anchor(m) for m in matches)
        ok = has_specific or len(matches) >= 2
    else:
        raise ValueError(f"mode inconnu: {mode}")

    if ok:
        return True, ""
    reason = (
        f"[{mode}] {len(matches)} ancrage(s) trouvé(s) : {sorted(matches)} — "
        f"aucun spécifique (chiffres ou ≥7 chars)" if matches else
        f"[{mode}] 0 ancrage projet dans titre+description"
    )
    return False, reason


# ─────────────────────────────────────────────────────────────
# FILTRE B — Détecteur de migration X→Y
# ─────────────────────────────────────────────────────────────


def filter_b_migration(
    finding: Finding,
    verdict: JudgeVerdict,
    project: ProjectModel,
) -> tuple[bool, str]:
    """
    Si real_gain_summary mentionne "X→Y", "X to Y", "Migration X", "passage X",
    "remplacer X par Y", alors X DOIT être dans les composants du projet.

    Returns (passes_filter, reason_if_failed).
    """
    summary = verdict.real_gain_summary
    # Préserve la flèche avant le strip d'accents (sinon "→" devient "")
    summary_with_arrow = summary.replace("→", " -> ").replace("→", " -> ")
    summary_norm = _strip_accents(summary_with_arrow.lower())

    component_names = project_component_names(project)
    # Pour matcher "SX1276" dans le composant "Module LoRa SX1276", on tokenize
    project_component_tokens = set()
    for cn in component_names:
        project_component_tokens |= _tokenize(cn)
        project_component_tokens.add(_normalize_component(cn))

    # Patterns de migration
    patterns = [
        r"migration\s+([a-z0-9\-]+)\s*(?:->|→|to|vers|en)\s*([a-z0-9\-]+)",
        r"\b([a-z0-9]{2,}\d+[a-z0-9\-]*)\s*(?:->|→|to|vers)\s*([a-z0-9]{2,}\d+[a-z0-9\-]*)",
        r"remplacer\s+(?:le\s+)?(?:module\s+|composant\s+)?([a-z0-9\-]+)\s+par\s+(?:un\s+)?([a-z0-9\-]+)",
        r"passage\s+(?:du\s+|de\s+)?([a-z0-9\-]+)\s+(?:au|à|vers)\s+(?:un\s+)?([a-z0-9\-]+)",
    ]

    for pat in patterns:
        for m in re.finditer(pat, summary_norm, re.IGNORECASE):
            source = m.group(1).strip().lower()
            source_norm = re.sub(r"[^a-z0-9]", "", source)
            # Ignore les sources trop courtes ou génériques
            if len(source_norm) < 4:
                continue
            if source_norm in _GENERIC_DENY_AS_ANCHOR:
                continue
            # Le source doit matcher un composant projet
            in_project = (
                source in project_component_tokens
                or source_norm in project_component_tokens
                or any(source_norm in pc or pc in source_norm
                       for pc in project_component_tokens if len(pc) >= 4)
            )
            if not in_project:
                return False, (
                    f"Migration '{source}' → autre chose, mais '{source}' "
                    f"n'est pas un composant du projet"
                )

    return True, ""


# ─────────────────────────────────────────────────────────────
# FILTRE C — Anti-plaque (chiffres projet absents du finding)
# ─────────────────────────────────────────────────────────────


def filter_c_anti_plaque(
    finding: Finding,
    verdict: JudgeVerdict,
    project: ProjectModel,
) -> tuple[bool, str]:
    """
    Si real_gain_summary contient un chiffre+unité spécifique du projet
    (40%, 18 mois, 60€, ISO 13849), ce chiffre/standard doit aussi apparaître
    dans finding.description ou finding.title.

    Returns (passes_filter, reason_if_failed).
    """
    summary = verdict.real_gain_summary
    summary_norm = _strip_accents(summary.lower())
    finding_text = _strip_accents((finding.title + " " + finding.description).lower())

    project_numbers = project_specific_numbers(project)

    for num_str in project_numbers:
        num_norm = _strip_accents(num_str.lower())
        if num_norm not in summary_norm:
            continue
        # Le chiffre projet est dans le summary — vérifier qu'il est dans le finding
        # Normalisation : "18 mois" vs "18mois"
        num_compact = re.sub(r"\s+", "", num_norm)
        if num_norm in finding_text or num_compact in re.sub(r"\s+", "", finding_text):
            continue
        # Mention spécifique au projet, absente du finding → plaque
        return False, f"Chiffre projet '{num_str}' mentionné dans summary mais absent du finding source"

    # Détecte aussi les standards spécifiques (ISO 13849, IP67, ERC 70-03)
    standards_in_project = re.findall(
        r"\b(?:iso\s*\d+|ip\d{2}|erc\s*\d+(?:[-\s]\d+)?|ce|fcc|rohs)\b",
        _strip_accents(" ".join(
            project.objectifs_actifs
            + project.contraintes_non_negociables
        ).lower()),
    )
    for std in standards_in_project:
        std_norm = re.sub(r"\s+", "", std.lower())
        if std_norm in re.sub(r"\s+", "", summary_norm):
            if std_norm not in re.sub(r"\s+", "", finding_text):
                return False, f"Standard projet '{std}' mentionné dans summary mais absent du finding"

    return True, ""


# ─────────────────────────────────────────────────────────────
# Chargement d'un run
# ─────────────────────────────────────────────────────────────


def load_run(run_dir: Path, project_slug: str) -> dict:
    """Charge tous les artefacts pertinents pour un run."""
    findings_raw = json.loads(
        (run_dir / "01_eclaireur_findings.json").read_text(encoding="utf-8")
    )
    findings = {f["id"]: Finding(**f) for f in findings_raw}

    integ_raw = json.loads(
        (run_dir / "02_integrateur_verdicts.json").read_text(encoding="utf-8")
    )
    integ_verdicts = {
        fid: IntegrationVerdict(**v) for fid, v in integ_raw.items()
    }

    juge_raw = json.loads(
        (run_dir / "03_juge_verdicts.json").read_text(encoding="utf-8")
    )
    juge_verdicts = {
        fid: JudgeVerdict(**v) for fid, v in juge_raw.items()
    }

    project_md_path = _repo_root / "projects" / f"{project_slug}.md"
    md_content = project_md_path.read_text(encoding="utf-8")
    project, _ = parse_and_validate(md_content)
    assert project is not None

    return {
        "run_dir": run_dir,
        "project_slug": project_slug,
        "project": project,
        "findings": findings,
        "integ_verdicts": integ_verdicts,
        "juge_verdicts": juge_verdicts,
    }


# ─────────────────────────────────────────────────────────────
# Identifier les "suggestions retenues" du Rapporteur
# ─────────────────────────────────────────────────────────────


def find_retained_suggestions(data: dict) -> list[Finding]:
    """
    Les suggestions retenues sont celles avec :
    - integration_verdict.integrable = True
    - juge_verdict.relevance ∈ {high, medium}
    - juge_verdict.timing ∈ {now, next_iteration}

    (Mêmes critères que `_group_by_theme` du Rapporteur, avant déduplication.)
    """
    retained = []
    for fid, jv in data["juge_verdicts"].items():
        if jv.relevance not in ("high", "medium"):
            continue
        if jv.timing_recommendation not in ("now", "next_iteration"):
            continue
        iv = data["integ_verdicts"].get(fid)
        if iv is None or not iv.integrable:
            continue
        if fid not in data["findings"]:
            continue
        retained.append(data["findings"][fid])
    return retained


# ─────────────────────────────────────────────────────────────
# Évaluation d'une combinaison de filtres
# ─────────────────────────────────────────────────────────────


def evaluate_filter_combo(
    runs: list[dict],
    use_a: bool,
    use_b: bool,
    use_c: bool,
    a_mode: str = "strict",
    bc_mode: str = "reject",  # "reject" | "downgrade"
    verbose: bool = False,
) -> dict:
    """
    Applique une combinaison de filtres aux suggestions retenues de tous les runs.
    Compare au label OPUS pour calculer la matrice de confusion.

    Returns un dict avec :
    - kept: nombre conservé
    - rejected: nombre rejeté
    - tp (true positive): non_aligné rejeté ← BON
    - fp (false positive): high/partial rejeté ← MAUVAIS (overfitting)
    - tn (true negative): high/partial gardé ← BON
    - fn (false negative): non_aligné gardé ← MAUVAIS
    - high_kept: high conservés
    - high_total: high totaux
    - non_aligned_kept: non_aligned conservés
    - non_aligned_total: non_aligned totaux
    """
    confusion = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    by_label = defaultdict(lambda: {"kept": 0, "total": 0})
    details = []

    for data in runs:
        retained = find_retained_suggestions(data)
        project = data["project"]

        # Déduplication thématique (mêmes critères que Rapporteur)
        by_theme = defaultdict(list)
        for f in retained:
            key = (f.component_concerned, f.angle)
            by_theme[key].append(f)

        # Sélection du best représentant par groupe (logique exacte rapporteur)
        rel_score = {"high": 0, "medium": 1, "low": 2, "reject": 3}
        conf_score = {"high": 0, "medium": 1, "low": 2}
        eff_score = {"trivial": 0, "minor": 1, "moderate": 2, "major": 3, "blocking": 4}

        for theme, theme_findings in by_theme.items():
            best = min(
                theme_findings,
                key=lambda f: (
                    rel_score.get(data["juge_verdicts"][f.id].relevance, 9),
                    conf_score.get(data["integ_verdicts"][f.id].confidence, 9),
                    eff_score.get(data["integ_verdicts"][f.id].effort_level, 9),
                ),
            )

            label = _opus_label(best.title)
            if label is None:
                continue  # pas labellisé

            jv = data["juge_verdicts"][best.id]
            iv = data["integ_verdicts"][best.id]

            rejected = False
            reason = ""

            downgraded = False

            if use_a:
                ok, r = filter_a_grounding(best, project, mode=a_mode)
                if not ok:
                    # A est toujours strict (rejet) — règle d'ancrage fondamentale
                    rejected = True
                    reason = f"[A:grounding] {r}"

            if not rejected and use_b:
                ok, r = filter_b_migration(best, jv, project)
                if not ok:
                    if bc_mode == "reject":
                        rejected = True
                    else:
                        downgraded = True
                    reason = f"[B:migration] {r}"

            if not rejected and use_c:
                ok, r = filter_c_anti_plaque(best, jv, project)
                if not ok:
                    if bc_mode == "reject":
                        rejected = True
                    else:
                        downgraded = True
                    reason = (reason + " | " if reason else "") + f"[C:antiplaque] {r}"

            kept = not rejected
            by_label[label]["total"] += 1
            if kept:
                by_label[label]["kept"] += 1

            if label == "non_aligned":
                if rejected:
                    confusion["tp"] += 1
                else:
                    confusion["fn"] += 1
            else:  # high or partial
                if rejected:
                    confusion["fp"] += 1
                else:
                    confusion["tn"] += 1

            details.append({
                "project": data["project_slug"],
                "title": best.title[:60],
                "label_opus": label,
                "kept": kept,
                "downgraded": downgraded,
                "reason": reason,
            })

    # Calcul du score qualité
    total = sum(c["total"] for c in by_label.values())
    high_kept = by_label["high"]["kept"]
    high_total = by_label["high"]["total"]
    aligned_kept = by_label["high"]["kept"] + by_label["partial"]["kept"]
    aligned_total = by_label["high"]["total"] + by_label["partial"]["total"]
    non_aligned_kept = by_label["non_aligned"]["kept"]
    non_aligned_total = by_label["non_aligned"]["total"]
    kept_total = sum(c["kept"] for c in by_label.values())

    strict_align_ratio = high_kept / kept_total if kept_total else 0.0
    aligned_ratio = aligned_kept / kept_total if kept_total else 0.0

    return {
        "combo": f"A={use_a} B={use_b} C={use_c}",
        "kept": kept_total,
        "rejected": total - kept_total,
        "total": total,
        "high_kept": high_kept,
        "high_total": high_total,
        "high_loss": high_total - high_kept,  # FAUX POSITIFS = overfitting
        "partial_kept": by_label["partial"]["kept"],
        "partial_total": by_label["partial"]["total"],
        "non_aligned_kept": non_aligned_kept,
        "non_aligned_total": non_aligned_total,
        "non_aligned_rejected": non_aligned_total - non_aligned_kept,  # VRAIS POSITIFS
        "strict_align_pct": round(100 * strict_align_ratio, 1),
        "aligned_pct": round(100 * aligned_ratio, 1),
        "confusion": confusion,
        "details": details,
    }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main():
    runs_root = Path.home() / ".applied-fox" / "runs"

    # Runs les plus récents par projet (13/05/2026 13h32)
    run_specs = [
        ("20260513_132329_smart_greenhouse", "smart_greenhouse"),
        ("20260513_132513_wildlife_lora_tracker", "wildlife_lora_tracker"),
        ("20260513_132703_ebike_bms_diy", "ebike_bms_diy"),
    ]

    print("Chargement des 3 runs récents (multi-source actif)...")
    runs = []
    for run_name, project_slug in run_specs:
        run_dir = runs_root / run_name
        try:
            data = load_run(run_dir, project_slug)
            runs.append(data)
            print(f"  OK {project_slug}: {len(data['findings'])} findings, "
                  f"{len(data['juge_verdicts'])} verdicts Juge")
        except Exception as e:
            print(f"  ERR {project_slug}: {e}")
            return 1

    print()
    print("Anchors par projet :")
    for r in runs:
        anchors = project_strong_anchors(r["project"])
        print(f"  {r['project_slug']:30} {len(anchors)} anchors : "
              f"{sorted(anchors)[:10]}... (+{len(anchors)-10})")
    print()

    # ─── Évaluation de toutes les combinaisons de filtres ───
    print("=" * 100)
    print("ÉVALUATION DES COMBINAISONS DE FILTRES (sur 16 suggestions labellisées OPUS)")
    print("=" * 100)
    print()

    header = (
        f"{'Combo':<24} {'Kept':>5} {'Rej':>4} {'High%':>6} {'Align%':>7} "
        f"{'NA_rej':>7} {'High_lost':>10}"
    )
    print(header)
    print("-" * len(header))

    combos = [
        # (use_a, use_b, use_c, a_mode, bc_mode, label)
        (False, False, False, "strict",  "reject",    "baseline"),
        (True,  False, False, "loose",   "reject",    "A_loose"),
        (True,  False, False, "strict",  "reject",    "A_strict"),
        (True,  False, False, "density", "reject",    "A_density"),
        (False, True,  False, "strict",  "reject",    "B reject"),
        (False, False, True,  "strict",  "reject",    "C reject"),
        (False, True,  True,  "strict",  "reject",    "B+C reject"),
        (False, True,  True,  "strict",  "downgrade", "B+C downgrade"),
        (True,  True,  True,  "loose",   "reject",    "A_loose+B+C rej"),
        (True,  True,  True,  "strict",  "reject",    "A_strict+B+C rej"),
        (True,  True,  True,  "strict",  "downgrade", "A_strict+B+C dwn"),
        (True,  True,  True,  "density", "downgrade", "A_density+B+C dwn"),
    ]

    all_results = []
    for a, b, c, mode, bcmode, label in combos:
        result = evaluate_filter_combo(runs, a, b, c, a_mode=mode, bc_mode=bcmode)
        result["label"] = label
        all_results.append(result)
        print(
            f"{label:<22} {result['kept']:>5} {result['rejected']:>4} "
            f"{result['strict_align_pct']:>5.1f}% {result['aligned_pct']:>6.1f}% "
            f"{result['non_aligned_rejected']:>3}/{result['non_aligned_total']:<3} "
            f"{result['high_loss']:>3}/{result['high_total']:<3}"
        )

    print()
    print("Lecture :")
    print("  High%    = parmi les retenus, % réellement aligné (cible: maximiser)")
    print("  Align%   = parmi les retenus, % high OR partial (cible: maximiser)")
    print("  NA_rej   = non-alignés correctement rejetés / total non-alignés (cible: maximiser)")
    print("  High_lost = high correctement alignés MAIS rejetés à tort (overfitting — cible: minimiser)")
    print()

    # ─── Détail des 3 options finales ───
    print("=" * 100)
    print("DÉTAIL — Combinaison A_strict + B + C (mode downgrade)")
    print("=" * 100)
    abc = next(r for r in all_results if r["label"] == "A_strict+B+C dwn")
    for d in abc["details"]:
        if d["kept"] and d.get("downgraded"):
            status = "DWNG"
        elif d["kept"]:
            status = "KEEP"
        else:
            status = "REJ "
        emoji = {
            "high": "+",
            "partial": "~",
            "non_aligned": "x",
        }.get(d["label_opus"], "?")
        print(f"  {status}  [{emoji} {d['label_opus']:<11}] {d['project']:<22} "
              f"{d['title']}")
        if d["reason"]:
            print(f"        -> {d['reason']}")

    print()
    print("=" * 100)
    print("RÉSUMÉ")
    print("=" * 100)
    baseline = all_results[0]
    print(f"Baseline (aucun filtre) : "
          f"{baseline['strict_align_pct']:>4.1f}% strict | "
          f"{baseline['aligned_pct']:>4.1f}% aligned | "
          f"{baseline['non_aligned_kept']} NA laissés | "
          f"high gardés: {baseline['high_kept']}/{baseline['high_total']}")
    for r in all_results[1:]:
        delta_strict = r["strict_align_pct"] - baseline["strict_align_pct"]
        delta_align = r["aligned_pct"] - baseline["aligned_pct"]
        overfit_risk = "OVERFITTING" if r["high_loss"] > 0 else "safe"
        print(f"{r['label']:<22} : "
              f"{r['strict_align_pct']:>4.1f}% strict ({delta_strict:+.1f}) | "
              f"{r['aligned_pct']:>4.1f}% aligned ({delta_align:+.1f}) | "
              f"{r['non_aligned_kept']} NA laissés | "
              f"high: {r['high_kept']}/{r['high_total']} | {overfit_risk}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
