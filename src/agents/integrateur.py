"""
Agent Intégrateur — Verdict de faisabilité d'intégration par finding.

Responsabilité :
    Pour chaque Finding produit par l'Éclaireur, évaluer si l'idée/composant
    suggéré peut s'intégrer dans le projet existant, et à quel coût.

Répond à la question : "Est-ce que ça rentre, et est-ce que ça casse
quelque chose ?". Il connaît les composants, la stack, les contraintes,
les interactions.

Trois fonctions principales :
    - run() : orchestration sur la liste complète des findings
    - _build_project_context() : sérialisation du projet pour le prompt
    - _evaluate_one() : appel LLM unique pour un finding, avec retry Pydantic

Diffère de l'Éclaireur sur un point clé : l'Intégrateur reçoit le CONTEXTE
projet complet (composants, stack, contraintes, interactions). C'est nécessaire
pour évaluer la faisabilité. Le risque de plaquage est faible car la tâche
est différente (évaluation d'intégration, pas description du finding).

Implémentation : Jalon 5a.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from src.models import Finding, IntegrationVerdict, ProjectModel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Filtre déterministe MCU-family
#
# Avant tout appel LLM, on vérifie que la famille de microcontrôleur
# mentionnée dans le finding est compatible avec celle du projet.
#
# Exemple prototypique : finding "STM32 clock slow down" → rejet immédiat
# pour un projet ESP32-S3. Le 7B rate souvent ce cas (il interprète
# "microcontroleur" comme un sous-système générique du projet).
#
# Règle conservatrice :
#   - Si le finding mentionne UNE SEULE famille MCU absente du projet → rejet.
#   - Si le finding mentionne plusieurs familles (post comparatif) → LLM décide.
#   - Si aucun token MCU dans le finding → pas de filtre.
#   - Si le projet n'a aucun MCU identifié → filtre désactivé (sécurité).
# ─────────────────────────────────────────────────────────────

_MCU_FAMILY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ESP32 — toutes variantes + écosystème
    (re.compile(r"\besp32(?:[-\s]?(?:s3|s2|c3|c6|h2|h4|p4))?\b", re.IGNORECASE), "esp32"),
    (re.compile(r"\besp8266\b", re.IGNORECASE), "esp32"),
    (re.compile(r"\besp-idf\b", re.IGNORECASE), "esp32"),
    (re.compile(r"\besphome\b", re.IGNORECASE), "esp32"),
    # STM32
    (re.compile(r"\bstm32[a-z]?\d*\b", re.IGNORECASE), "stm32"),
    # RP2040 / RP2350 (Raspberry Pi Pico — "pico" seul trop générique)
    (re.compile(r"\brp2040\b", re.IGNORECASE), "rp2040"),
    (re.compile(r"\brp2350\b", re.IGNORECASE), "rp2040"),
    (re.compile(r"\braspberry\s+pi\s+pico\b", re.IGNORECASE), "rp2040"),
    # AVR (Arduino Mega / Uno / Nano → sous-famille atmel)
    (re.compile(r"\batmega\d+\b", re.IGNORECASE), "avr"),
    (re.compile(r"\battiny\d+\b", re.IGNORECASE), "avr"),
    # Nordic
    (re.compile(r"\bnrf5[12]\d*\b", re.IGNORECASE), "nordic"),
    (re.compile(r"\bnrf5340\b", re.IGNORECASE), "nordic"),
    (re.compile(r"\bnrf9160\b", re.IGNORECASE), "nordic"),
    # TI MSP430
    (re.compile(r"\bmsp430\b", re.IGNORECASE), "msp430"),
    # Microchip PIC32 / dsPIC
    (re.compile(r"\bpic32\w*\b", re.IGNORECASE), "pic"),
    (re.compile(r"\bdspic\w*\b", re.IGNORECASE), "pic"),
    # SAMD (Microchip ARM)
    (re.compile(r"\bsamd[25]1\b", re.IGNORECASE), "samd"),
    # GigaDevice GD32
    (re.compile(r"\bgd32\w*\b", re.IGNORECASE), "gd32"),
]


def _detect_mcu_families(text: str) -> set[str]:
    """Retourne l'ensemble des familles MCU identifiées dans un texte."""
    return {family for pattern, family in _MCU_FAMILY_PATTERNS if pattern.search(text)}


def _project_mcu_families(project: ProjectModel) -> set[str]:
    """
    Extrait les familles MCU présentes dans la liste des composants du projet.

    Analyse les noms de composants. Si aucune famille n'est détectée (projet
    sans MCU, ou MCU exotique hors référentiel), retourne un ensemble vide ce
    qui désactive le filtre pour ce projet.
    """
    composite = " ".join(c.nom for c in project.composants)
    return _detect_mcu_families(composite)


def _check_mcu_family_mismatch(
    finding: Finding,
    project_families: set[str],
) -> Optional[str]:
    """
    Détecte un mismatch de famille MCU entre finding et projet.

    Retourne un rationale de rejet si mismatch confirmé, None sinon.
    """
    if not project_families:
        return None  # projet sans MCU identifié → filtre désactivé

    # Zone de recherche : titre + 200 premiers caractères de la description.
    search_text = f"{finding.title} {(finding.description or '')[:200]}"
    finding_families = _detect_mcu_families(search_text)

    if not finding_families:
        return None  # pas de MCU nommé dans le finding → on laisse au LLM

    if len(finding_families) > 1:
        return None  # post comparatif multi-plateformes → cas ambigu, LLM décide

    # Un seul token MCU dans le finding — est-il dans le projet ?
    if finding_families & project_families:
        return None  # même famille → compatible, on laisse au LLM

    mismatch_family = next(iter(finding_families))
    project_str = ", ".join(sorted(project_families))
    return (
        f"Famille MCU du finding ({mismatch_family}) absente du projet "
        f"({project_str}). Rejet déterministe sans appel LLM."
    )


# ─────────────────────────────────────────────────────────────
# Sérialisation du projet pour le prompt
# ─────────────────────────────────────────────────────────────


def _build_project_context(project: ProjectModel) -> str:
    """
    Sérialise les champs du projet pertinents pour évaluer une intégration.

    Inclut composants, stack, interactions, contraintes — pas la section
    Changements ni la description longue (informations narratives moins utiles
    pour le raisonnement Intégrateur).
    """
    lines: list[str] = []

    lines.append(f"Projet : {project.nom_projet}")
    lines.append(f"Phase : {project.identite.phase}")
    lines.append(f"Domaine : {project.identite.domaine}")
    lines.append("")

    lines.append("Objectifs actifs :")
    for o in project.objectifs_actifs:
        lines.append(f"  - {o}")
    lines.append("")

    lines.append("Composants :")
    for c in project.composants:
        lines.append(
            f"  - {c.nom} ({c.role}) | statut: {c.statut_decisionnel} | "
            f"pipeline: {c.role_pipeline}"
        )
    lines.append("")

    lines.append("Stack logicielle :")
    for s in project.stack_software:
        lines.append(
            f"  - {s.outil} ({s.role}) | version: {s.version} | "
            f"statut: {s.statut_decisionnel}"
        )
    lines.append("")

    lines.append("Interactions :")
    for i in project.interactions:
        line = f"  - {i.source} → {i.target} : {i.nature}"
        if getattr(i, "format", None):
            line += f" | {i.format}"
        if getattr(i, "volume", None):
            line += f" | {i.volume}"
        lines.append(line)
    lines.append("")

    lines.append("Contraintes par sous-section :")
    for section in project.contraintes:
        lines.append(f"  [{section.titre}]")
        for crit in section.criteres:
            lines.append(f"    {crit.nom} : {crit.valeur}")
    lines.append("")

    lines.append("Contraintes non négociables :")
    for cnn in project.contraintes_non_negociables:
        lines.append(f"  - {cnn}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Prompt système Intégrateur
# ─────────────────────────────────────────────────────────────


_INTEGRATION_PROMPT = """Tu es l'Intégrateur, un agent qui évalue la faisabilité technique d'intégrer une nouveauté dans un projet existant.

═══ PROJET EXISTANT ═══
{project_context}

═══ FINDING À ÉVALUER ═══
Titre : {title}
Composant concerné : {component}
Angle (perspective de l'Éclaireur) : {angle}
Description : {description}
Source : {source_url}
Type de source : {source_type}
{component_classification_block}
═══ TÂCHE ═══

Évalue si cette information peut être intégrée dans le projet (changement
de composant, modification d'architecture, prise en compte d'une contrainte
nouvelle, etc.). Produis un JSON STRICT avec EXACTEMENT ces 7 clés :

{{
  "integrable": true ou false,
  "effort_level": "trivial" | "minor" | "moderate" | "major" | "blocking",
  "required_changes": [liste de changements concrets, max 5],
  "risks": [liste de risques techniques, max 5],
  "uncertainties": [liste d'informations manquantes pour décider, max 5],
  "confidence": "high" | "medium" | "low",
  "rationale": "raisonnement court 2-4 phrases"
}}

═══ RÈGLES IMPÉRATIVES ═══

1. ANCRAGE FACTUEL — Tu te bases UNIQUEMENT sur ce que dit le finding
   et le projet décrit ci-dessus. Tu n'inventes pas de spec produit, ni
   de chiffre, ni de fait sur les composants.

1bis. CHECK SUJET DU FINDING (PRIORITAIRE) — Avant tout, regarde le
     TITRE et la DESCRIPTION du finding. Le sujet réel du finding doit
     mentionner explicitement au moins l'un de ces éléments :
       (a) un composant nommé dans la liste Composants du projet, OU
       (b) une technologie/standard cité dans les objectifs actifs
           (ex. LoRa, BMS 13S, étanchéité IP65, ISO 13849), OU
       (c) un sous-système du projet (alimentation, capteur, transmission, etc.).
     Si AUCUN des trois n'est rempli, retourne integrable=false,
     effort_level="blocking", confidence="low" avec rationale="Sujet du
     finding hors-périmètre du projet : <pourquoi>." NE PAS chercher à
     forcer un lien artificiel.

     Exemples :
     - Projet BMS, finding "Self-balancing cube" → integrable=false (cube ≠ BMS).
     - Projet serre, finding "SPI Display" → integrable=false (pas de display).
     - Projet LoRa tracker, finding "Motorsport logger 25 Hz" → integrable=false.

2. SCEPTICISME SUR LES FINDINGS — Le finding peut contenir des affirmations
   incorrectes (hallucinations LLM amont). Si la description du finding
   semble plaquée sur le projet ou contient des chiffres "trop convenants"
   par rapport au projet, mets confidence="low" et signale-le dans
   uncertainties : ["Affirmations du finding non vérifiables"].

2bis. INTERDICTION D'INVENTER UN CHIFFRE — Dans required_changes et
     rationale, ne mentionne un pourcentage, un nombre de mois, une
     réduction de coût ou toute autre métrique CHIFFRÉE que si cette
     métrique apparaît EXPLICITEMENT dans le titre ou la description du
     finding. Sinon, formule en termes qualitatifs.

2ter. COMPOSANTS NOUVEAUX — Si la liste "Composants NOUVEAUX mentionnés"
     ci-dessus est non vide, ces références (ex. BQ25616, MAX-M10S) ne sont
     PAS dans la fiche projet. Pour chacune :
       - Si la DESCRIPTION du finding explique ce que le composant fait
         (fonction, specs minimales) → tu peux raisonner dessus.
       - Si la DESCRIPTION ne donne aucun contexte sur ce composant →
         confidence="low" obligatoire ET ajoute dans uncertainties :
         "Composant <Nom> mentionné sans contexte technique suffisant
         dans le finding".
     N'INVENTE JAMAIS les specs d'un composant inconnu à partir de tes
     connaissances générales. Le finding est la seule source de vérité.

3. INTÉGRABLE vs NON-INTÉGRABLE :
   - integrable=true : le changement est techniquement possible dans le projet
     en l'état (peut-être avec effort, mais pas une réécriture totale).
   - integrable=false : incompatible avec une contrainte non négociable,
     ou demande de jeter l'architecture actuelle.

4. EFFORT_LEVEL :
   - trivial  : pull-request d'une ligne, swap de modèle direct.
   - minor    : quelques heures de dev, pas de revue d'archi.
   - moderate : 1-3 jours de dev, revue d'un module.
   - major    : plusieurs semaines, refonte d'un sous-système.
   - blocking : impossible sans casser une contrainte non négociable.

5. CONFIDENCE :
   - high   : le finding est factuel, l'évaluation s'appuie sur des éléments clairs du projet.
   - medium : un ou deux uncertainties, mais la direction est claire.
   - low    : finding peu fiable, ou impact difficile à estimer sans plus d'info.

6. RATIONALE — Court, factuel, sans formule rituelle. Explique POURQUOI tu
   tranches comme ça en t'appuyant sur le projet ET le finding.

7. FORMAT — JSON strict, parsable directement. Aucun markdown, aucun
   commentaire hors du JSON, aucun préfixe type "Voici la réponse :".

═══ EXEMPLES ═══

BON exemple (finding factuel pertinent, intégrable) :
{{
  "integrable": true,
  "effort_level": "moderate",
  "required_changes": [
    "Remplacer le module LoRa SX1276 par un E22-900M22S basé SX1262",
    "Adapter le driver LoRa côté firmware",
    "Refaire le BOM/PCB pour le nouveau footprint"
  ],
  "risks": [
    "Disponibilité du module E22-900M22S à vérifier chez les distributeurs"
  ],
  "uncertainties": [
    "Compatibilité broche-à-broche non vérifiée",
    "Gain réel d'autonomie non chiffré dans le post"
  ],
  "confidence": "medium",
  "rationale": "Le SX1262 a un mode RX plus efficace que le SX1276, ce qui sert directement l'objectif d'autonomie 6 mois. Migration possible mais demande revue PCB."
}}

BON exemple (finding douteux, low confidence) :
{{
  "integrable": false,
  "effort_level": "blocking",
  "required_changes": [],
  "risks": [
    "Le finding affirme des spécifications produit (autonomie 6 mois sur ce repo) qui semblent plaquées du contexte projet"
  ],
  "uncertainties": [
    "Affirmations du finding non vérifiables sans lecture du repo source",
    "Pas de lien clair entre ce repo et l'architecture du projet"
  ],
  "confidence": "low",
  "rationale": "Le finding semble être une hallucination LLM amont. La description plaque les objectifs du projet sur un repo générique sans lien avéré. À écarter sans vérification humaine."
}}
"""


# ─────────────────────────────────────────────────────────────
# Parsing JSON tolérant
# ─────────────────────────────────────────────────────────────


def _extract_json_object(text: str) -> Optional[dict]:
    """Extrait le premier objet JSON équilibré depuis la sortie LLM."""
    if not text:
        return None
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


# ─────────────────────────────────────────────────────────────
# Évaluation d'un finding
# ─────────────────────────────────────────────────────────────


def _evaluate_one(
    finding: Finding,
    project_context: str,
    config: dict,
    max_retries: int = 2,
    project_mcu_families: Optional[set[str]] = None,
) -> Optional[IntegrationVerdict]:
    """
    Appelle le LLM pour évaluer un Finding, retourne un IntegrationVerdict.

    Deux court-circuits déterministes avant l'appel LLM :
    1. Description "Aucun apport pertinent." → skip direct (Éclaireur inutile).
    2. Mismatch de famille MCU → rejet si le finding nomme une famille
       absente du projet (ex. STM32 pour un projet ESP32-S3).

    Retry jusqu'à max_retries en cas d'échec de parsing JSON ou de
    validation Pydantic. Retourne None après épuisement des tentatives.
    """
    # ── Court-circuit 1 : finding sans apport ──────────────────
    desc_norm = (finding.description or "").strip().rstrip(".").lower()
    if desc_norm in {"aucun apport pertinent", ""}:
        return IntegrationVerdict(
            finding_id=finding.id,
            integrable=False,
            effort_level="blocking",
            required_changes=[],
            risks=[],
            uncertainties=[
                "Éclaireur a marqué ce finding comme sans apport pertinent — "
                "court-circuit déterministe sans appel LLM."
            ],
            confidence="low",
            rationale=(
                "Skip déterministe : description du finding marquée comme "
                "'Aucun apport pertinent.' par l'Éclaireur. Pas d'évaluation LLM."
            ),
        )

    # ── Court-circuit 2 : mismatch famille MCU ─────────────────
    if project_mcu_families is not None:
        mcu_rationale = _check_mcu_family_mismatch(finding, project_mcu_families)
        if mcu_rationale:
            logger.info(
                "Intégrateur MCU-filter : rejet déterministe de '%s'", finding.title
            )
            return IntegrationVerdict(
                finding_id=finding.id,
                integrable=False,
                effort_level="blocking",
                required_changes=[],
                risks=[],
                uncertainties=[],
                confidence="high",
                rationale=mcu_rationale,
            )

    from src.llm import get_llm

    # ── Niveau 2 : classification des composants mentionnés ─────
    # Si l'Éclaireur a produit la classification, on injecte la liste des
    # composants nouveaux pour forcer l'Intégrateur à déclarer son
    # incertitude au lieu d'halluciner sur des références opaques.
    classification_block = ""
    if finding.component_classification is not None:
        cc = finding.component_classification
        if cc.new_mentioned or cc.in_project:
            lines = ["", "═══ CLASSIFICATION COMPOSANTS (déterministe) ═══"]
            if cc.in_project:
                lines.append(
                    f"Composants du projet cités dans ce finding : "
                    f"{', '.join(cc.in_project)}"
                )
            if cc.new_mentioned:
                lines.append(
                    f"Composants NOUVEAUX mentionnés (PAS dans le projet) : "
                    f"{', '.join(cc.new_mentioned)}"
                )
                lines.append(
                    "  → Pour chacun, vérifie que la description du finding "
                    "explique sa fonction. Sinon : confidence='low' obligatoire."
                )
            lines.append("")
            classification_block = "\n".join(lines)

    prompt = _INTEGRATION_PROMPT.format(
        project_context=project_context,
        title=finding.title,
        component=finding.component_concerned,
        angle=finding.angle,
        description=finding.description,
        source_url=finding.source_url,
        source_type=finding.source_type,
        component_classification_block=classification_block,
    )

    llm = get_llm("integrateur", config)
    last_error = ""

    for attempt in range(max_retries + 1):
        try:
            full_prompt = prompt
            if attempt > 0 and last_error:
                full_prompt += (
                    f"\n\n[RETRY {attempt}] Erreur précédente : {last_error}\n"
                    "Produis cette fois un JSON valide qui respecte EXACTEMENT le schéma."
                )

            response = llm.invoke([HumanMessage(content=full_prompt)])
            content = response.content if hasattr(response, "content") else str(response)

            data = _extract_json_object(content)
            if data is None:
                last_error = "Aucun objet JSON parsable trouvé dans la réponse."
                continue

            # Validation Pydantic — le finding_id est ajouté ici (pas demandé au LLM).
            data["finding_id"] = finding.id
            verdict = IntegrationVerdict(**data)
            return verdict

        except ValidationError as exc:
            last_error = f"Validation Pydantic : {exc.errors()[:2]}"
            logger.debug("Validation échouée tentative %d : %s", attempt, last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.debug("Exception tentative %d : %s", attempt, last_error)

    logger.warning(
        "Intégrateur : échec après %d tentatives sur finding '%s' (%s)",
        max_retries + 1, finding.id, last_error,
    )
    return None


# ─────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────


def run(
    project: ProjectModel,
    findings: list[Finding],
    config: dict,
    run_dir: Optional[Path] = None,
) -> dict[str, IntegrationVerdict]:
    """
    Évalue tous les findings et produit un dict finding_id → IntegrationVerdict.

    Args:
        project: ProjectModel parsé (donne le contexte d'évaluation).
        findings: Liste des findings produits par l'Éclaireur.
        config: Config globale (passe-plat vers get_llm).
        run_dir: Dossier où sauvegarder les artefacts. None → pas de sauvegarde.

    Returns:
        Dict finding.id → IntegrationVerdict. Les findings dont le LLM a
        échoué sont absents du dict (graceful degradation).
    """
    project_context = _build_project_context(project)
    mcu_families = _project_mcu_families(project)
    if mcu_families:
        logger.info(
            "Intégrateur : familles MCU détectées dans le projet : %s",
            ", ".join(sorted(mcu_families)),
        )
    else:
        logger.debug("Intégrateur : aucune famille MCU identifiée — filtre MCU désactivé.")

    verdicts: dict[str, IntegrationVerdict] = {}
    failed_ids: list[str] = []
    mcu_rejected: list[str] = []

    logger.info("Intégrateur : évaluation de %d findings", len(findings))
    for i, finding in enumerate(findings, 1):
        if i % 10 == 0:
            logger.info("Intégrateur : %d/%d findings évalués", i, len(findings))
        verdict = _evaluate_one(
            finding, project_context, config,
            project_mcu_families=mcu_families,
        )
        if verdict is None:
            failed_ids.append(finding.id)
            continue
        # Traçage des rejets MCU-filter pour les stats
        if (
            not verdict.integrable
            and verdict.confidence == "high"
            and verdict.rationale.startswith("Famille MCU")
        ):
            mcu_rejected.append(finding.id)
        verdicts[finding.id] = verdict

    # Statistiques agrégées
    integrable_count = sum(1 for v in verdicts.values() if v.integrable)
    blocking_count = sum(1 for v in verdicts.values() if v.effort_level == "blocking")
    high_conf = sum(1 for v in verdicts.values() if v.confidence == "high")
    logger.info(
        "Intégrateur : %d verdicts | %d intégrables | %d blocking | "
        "%d high-conf | %d rejetés MCU-filter | %d échecs",
        len(verdicts), integrable_count, blocking_count,
        high_conf, len(mcu_rejected), len(failed_ids),
    )

    # ── Sauvegarde des artefacts ───────────────────────────────
    if run_dir is not None:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        verdicts_path = run_dir / "02_integrateur_verdicts.json"
        verdicts_path.write_text(
            json.dumps(
                {fid: v.model_dump() for fid, v in verdicts.items()},
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Reasoning concaténé en Markdown pour relecture humaine
        reasoning_path = run_dir / "02_integrateur_reasoning.md"
        reasoning_lines: list[str] = [
            f"# Raisonnement Intégrateur — {project.nom_projet}",
            "",
            f"Total findings évalués : {len(findings)}",
            f"Verdicts produits : {len(verdicts)}",
            f"Échecs : {len(failed_ids)}",
            "",
        ]
        # Tri par confidence puis par finding.id pour stabilité
        ordered = sorted(
            verdicts.items(),
            key=lambda kv: (
                {"high": 0, "medium": 1, "low": 2}.get(kv[1].confidence, 3),
                kv[0],
            ),
        )
        for fid, v in ordered:
            finding = next((f for f in findings if f.id == fid), None)
            title = finding.title if finding else "?"
            component = finding.component_concerned if finding else "?"
            reasoning_lines += [
                f"## [{v.confidence}] {title}",
                f"- ID : `{fid}` | Composant : {component}",
                f"- Intégrable : **{v.integrable}** | Effort : **{v.effort_level}**",
                f"- Raisonnement : {v.rationale}",
            ]
            if v.required_changes:
                reasoning_lines.append("- Changements requis :")
                reasoning_lines += [f"  - {c}" for c in v.required_changes]
            if v.risks:
                reasoning_lines.append("- Risques :")
                reasoning_lines += [f"  - {r}" for r in v.risks]
            if v.uncertainties:
                reasoning_lines.append("- Incertitudes :")
                reasoning_lines += [f"  - {u}" for u in v.uncertainties]
            reasoning_lines.append("")
        reasoning_path.write_text("\n".join(reasoning_lines), encoding="utf-8")

    return verdicts
