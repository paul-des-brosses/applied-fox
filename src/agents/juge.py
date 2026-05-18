"""
Agent Juge — Verdict de pertinence et de timing pour les findings intégrables.

Responsabilité :
    Pour chaque finding marqué intégrable par l'Intégrateur, décider s'il
    mérite d'être présenté à l'utilisateur ET quand.

Répond à la question : "Ce finding vaut-il la peine d'être présenté maintenant
compte tenu des objectifs actifs et de la phase du projet ?"

Différence vs Intégrateur :
    - Intégrateur : "peut-on intégrer techniquement ?" (faisabilité)
    - Juge        : "vaut-il la peine d'être présenté ?" (pertinence projet)

Deux niveaux de filtrage produits :
    - relevance : high / medium / low / reject
    - timing_recommendation : now / next_iteration / noted_for_future / reject

Skip automatique des findings non intégrables (court-circuit interne).
Le branchement conditionnel LangGraph skip aussi le Juge entier si aucun
finding n'est intégrable (défensif).

Implémentation : Jalon 5b.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from src.agents._anchoring import (
    is_specific_anchor,
    normalize_component_name,
    project_strong_anchors,
    tokenize,
)
from src.models import Finding, IntegrationVerdict, JudgeVerdict, ProjectModel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Sérialisation du projet pour le prompt Juge
# ─────────────────────────────────────────────────────────────


def _build_judge_context(project: ProjectModel) -> str:
    """
    Contexte focalisé sur ce que le Juge doit savoir : objectifs, phase, prochain rendu.

    Différence vs `_build_project_context` de l'Intégrateur : on n'a pas besoin
    de tout le détail des composants/interactions. Le Juge raisonne au niveau
    des objectifs et de la phase, pas de l'architecture.
    """
    lines: list[str] = []
    lines.append(f"Projet : {project.nom_projet}")
    lines.append(f"Phase : {project.identite.phase}")
    lines.append(f"Domaine : {project.identite.domaine}")
    lines.append("")

    lines.append("Objectifs actifs (CRITÈRES DE PERTINENCE) :")
    for o in project.objectifs_actifs:
        lines.append(f"  - {o}")
    lines.append("")

    rendu = project.prochain_rendu
    if rendu and rendu.date_prevue:
        lines.append("Prochain rendu :")
        lines.append(f"  Date : {rendu.date_prevue}")
        lines.append(f"  Nature : {rendu.nature}")
        lines.append(f"  Contenu attendu : {rendu.contenu_attendu}")
        lines.append("")

    lines.append("Contraintes non négociables (filets de sécurité) :")
    for cnn in project.contraintes_non_negociables:
        lines.append(f"  - {cnn}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Prompt Juge
# ─────────────────────────────────────────────────────────────


_JUDGE_PROMPT = """Tu es le Juge, agent qui décide si une trouvaille technique mérite d'être présentée à l'utilisateur — et quand.

═══ PROJET (objectifs et timing) ═══
{judge_context}

═══ FINDING À ARBITRER ═══
Titre : {title}
Composant concerné : {component}
Angle (de l'Éclaireur) : {angle}
Description : {description}

═══ VERDICT D'INTÉGRATION (de l'Intégrateur, garanti integrable=true) ═══
Effort estimé : {effort_level}
Confidence Intégrateur : {iv_confidence}
Changements requis : {required_changes}
Risques techniques : {risks}
Incertitudes : {uncertainties}
Raisonnement Intégrateur : {iv_rationale}

═══ TÂCHE ═══

Produis un JSON STRICT avec EXACTEMENT ces 4 clés :

{{
  "relevance": "high" | "medium" | "low" | "reject",
  "real_gain_summary": "gain concret pour l'utilisateur en 1-2 phrases",
  "timing_recommendation": "now" | "next_iteration" | "noted_for_future" | "reject",
  "rationale": "raisonnement court 2-4 phrases"
}}

═══ RÈGLES IMPÉRATIVES ═══

1. ALIGNEMENT OBJECTIFS — La relevance dépend du lien DIRECT avec un objectif actif :
   - high   : fait avancer un objectif actif de manière significative et chiffrable
   - medium : améliore le projet sans toucher directement un objectif critique
   - low    : marginalement utile, intéressant à noter mais pas critique
   - reject : hors-sujet, redondant, ou trop spéculatif

1bis. ANCRAGE OBLIGATOIRE AU TITRE DU FINDING — Avant de produire un
     real_gain_summary, vérifie que le SUJET du finding (visible dans son TITRE)
     traite explicitement de l'un des éléments suivants :
       (a) un composant listé dans la fiche projet, OU
       (b) une technologie nommée dans les objectifs actifs, OU
       (c) un sous-système clairement identifié du projet.
     Si AUCUN des trois n'est rempli → relevance="reject" obligatoire,
     real_gain_summary="Aucun lien explicite avec le projet (titre du finding
     hors-sujet)." Cette règle prime sur toutes les autres.

   Exemples d'application :
   - Projet BMS 13S, finding "Self-balancing cube control board" → REJECT
     (cube ≠ BMS, balancing motor ≠ cell balancing).
   - Projet greenhouse, finding "ESP32 SPI Display" → REJECT
     (le projet n'a pas de display).
   - Projet LoRa tracker, finding "Motorsport GNSS 25 Hz logger" → REJECT
     (logger sport haute fréq ≠ tracker basse conso 30 min).

2. FILET DE SÉCURITÉ ANTI-HALLUCINATION — Si Confidence Intégrateur est "low",
   relevance maximale autorisée = "medium". Tu NE PEUX PAS mettre "high"
   sur un finding peu fiable, même si le sujet semble parfait.

2bis. INTERDICTION D'INVENTER UN CHIFFRE — Dans real_gain_summary, tu ne
     mentionnes un pourcentage, un nombre de mois, une réduction de coût,
     ou toute autre métrique CHIFFRÉE que si cette métrique apparaît
     EXPLICITEMENT dans le titre ou la description du finding. Si tu ne
     trouves pas de chiffre dans la source, formule en termes qualitatifs
     ("amélioration potentielle de l'autonomie", pas "+75% d'autonomie").

3. TIMING — Calibre selon la phase et le prochain rendu :
   - now              : à intégrer dans le rapport courant en priorité haute
   - next_iteration   : utile mais peut attendre la prochaine veille
   - noted_for_future : intéressant à long terme, à archiver pour mémoire
   - reject           : ne pas montrer

4. CALIBRAGE EFFORT × GAIN :
   - effort=major + relevance=high → timing=next_iteration (gros chantier, planifier)
   - effort=trivial/minor + relevance=high → timing=now (gain immédiat à effort faible)
   - effort=blocking → ne devrait jamais arriver ici (déjà filtré par Intégrateur)

5. PRÉSERVE L'ATTENTION DE L'UTILISATEUR — Si tu hésites entre "low" et "reject",
   choisis REJECT. Mieux vaut moins de findings mais pertinents que beaucoup
   de bruit.

6. real_gain_summary doit être CONCRET (quel chiffre s'améliore, quelle
   contrainte est mieux respectée). PAS de formules creuses comme "améliore
   le projet".

7. FORMAT — JSON strict, aucun markdown, aucun préfixe.

═══ EXEMPLES ═══

BON exemple (high relevance, now) :
{{
  "relevance": "high",
  "real_gain_summary": "Migration SX1276→SX1262 augmente l'autonomie batterie de ~75% selon mesures terrain, ce qui sert directement l'objectif 6 mois.",
  "timing_recommendation": "now",
  "rationale": "Le finding touche l'objectif n°1 (autonomie 6 mois) avec un gain chiffré. L'effort moderate est acceptable vu le bénéfice. À traiter dans le rapport courant."
}}

BON exemple (low relevance, noted_for_future) :
{{
  "relevance": "low",
  "real_gain_summary": "Lib open-source pour debugger des bus I2C — utile mais pas critique pour la phase prototype actuelle.",
  "timing_recommendation": "noted_for_future",
  "rationale": "Outil de dev intéressant mais ne touche aucun objectif actif. À garder en mémoire pour quand l'équipe industrialisera."
}}

BON exemple (reject) :
{{
  "relevance": "reject",
  "real_gain_summary": "Aucun gain identifiable pour les objectifs du projet.",
  "timing_recommendation": "reject",
  "rationale": "Finding hors-sujet : repo de jeu vidéo sur ESP32 qui ne touche ni les capteurs, ni l'autonomie, ni LoRa. À écarter."
}}
"""


# ─────────────────────────────────────────────────────────────
# Parsing JSON tolérant (même utilitaire que l'Intégrateur)
# ─────────────────────────────────────────────────────────────


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_json_object(text: str) -> Optional[dict]:
    """
    Extrait le premier objet JSON équilibré depuis la sortie LLM.

    Tolérant à :
    - Mode 'thinking' (Qwen3.x, DeepSeek-R1) : on retire les blocs
      <think>...</think> avant de chercher.
    - Markdown code fences : on extrait le contenu de ```json ...```
      en priorité avant de tomber sur le scan {...}.
    - Préfixes/suffixes texte avant/après le JSON.
    """
    if not text:
        return None

    # 1. Supprime les blocs de raisonnement Qwen3 / DeepSeek-R1
    cleaned = _THINK_RE.sub("", text)

    # 2. Si le modèle a wrappé en markdown, on extrait le contenu
    fence_match = _FENCE_RE.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1)

    # 3. Scan d'un objet JSON équilibré
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Tenter de continuer la recherche pour le cas où plusieurs
                    # objets se suivent et le premier est mal formé.
                    next_brace = cleaned.find("{", i + 1)
                    if next_brace < 0:
                        return None
                    start = next_brace
                    depth = 0
                    i = next_brace - 1
                    continue
    return None


# ─────────────────────────────────────────────────────────────
# Filtres déterministes (Option C — règles 1bis et 2bis du prompt)
# ─────────────────────────────────────────────────────────────
#
# Trois filtres complémentaires qui enforcent déterministement les règles
# déjà présentes dans le prompt Juge :
#
#   Filtre A — Grounding (règle 1bis) : avant l'appel LLM, rejet si le finding
#       ne contient aucun ancrage projet "spécifique" dans son titre + sa
#       description. Économise l'appel LLM sur les findings sans signal.
#
#   Filtre B — Migration X→Y (règle 1bis) : après l'appel LLM, downgrade
#       timing à noted_for_future si le summary propose une migration depuis
#       un composant absent du projet.
#
#   Filtre C — Anti-plaque (règle 2bis) : après l'appel LLM, downgrade si le
#       summary mentionne un chiffre/standard spécifique du projet (40 %, 18
#       mois, ISO 13849) qui n'apparaît pas dans le finding source.


def _check_grounding(
    finding: Finding,
    project: ProjectModel,
) -> tuple[bool, str]:
    """
    Filtre A — Grounding strict.

    Le finding doit contenir au moins UN anchor projet "spécifique" (chiffres
    ou ≥7 caractères) dans son titre OU sa description. Empêche les findings
    au titre générique ("Tell your war stories", "Electrical Engineering
    Iceberg") d'arriver au Juge — le 7B/8B Q4 plaque sinon les chiffres du
    projet dessus.

    Returns (passes, reason_if_rejected).
    """
    anchors = project_strong_anchors(project)
    tokens = tokenize(f"{finding.title} {finding.description}")
    matches = tokens & anchors
    specific = [m for m in matches if is_specific_anchor(m)]
    if specific:
        return True, ""
    if matches:
        return False, (
            f"Aucun anchor projet spécifique (digits ou ≥7 chars) dans "
            f"titre+description. Anchors faibles trouvés : {sorted(matches)[:3]}"
        )
    return False, "Aucun anchor projet dans titre+description"


def _check_migration(
    verdict_data: dict,
    project: ProjectModel,
) -> tuple[bool, str]:
    """
    Filtre B — Migration validator.

    Si real_gain_summary mentionne "X→Y", "Migration X", "remplacer X par Y",
    alors X DOIT être un composant du projet. Sinon, le Juge propose une
    migration absurde (ex: "Migration SX1276→SX1262" alors que le projet
    utilise déjà un module RAK3172 qui contient un SX1262).

    Returns (passes, reason_if_failed).
    """
    summary = verdict_data.get("real_gain_summary", "")
    if not summary:
        return True, ""

    # Préserve la flèche unicode → avant le strip d'accents (qui la mange).
    summary_with_arrow = summary.replace("→", " -> ").replace("→", " -> ")
    summary_norm = (
        unicodedata.normalize("NFD", summary_with_arrow.lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    # Ensemble normalisé des composants projet (et leurs tokens).
    project_tokens: set[str] = set()
    for c in project.composants:
        project_tokens |= tokenize(c.nom)
        project_tokens.add(normalize_component_name(c.nom))

    patterns = [
        r"migration\s+([a-z0-9\-]+)\s*(?:->|to|vers|en)\s*([a-z0-9\-]+)",
        r"\b([a-z0-9]{2,}\d+[a-z0-9\-]*)\s*(?:->|to|vers)\s*([a-z0-9]{2,}\d+[a-z0-9\-]*)",
        r"remplacer\s+(?:le\s+)?(?:module\s+|composant\s+)?([a-z0-9\-]+)\s+par\s+(?:un\s+)?([a-z0-9\-]+)",
        r"passage\s+(?:du\s+|de\s+)?([a-z0-9\-]+)\s+(?:au|a|vers)\s+(?:un\s+)?([a-z0-9\-]+)",
    ]

    from src.agents._anchoring import GENERIC_DENY_AS_ANCHOR

    for pat in patterns:
        for m in re.finditer(pat, summary_norm, re.IGNORECASE):
            source = m.group(1).strip().lower()
            source_norm = re.sub(r"[^a-z0-9]", "", source)
            if len(source_norm) < 4:
                continue
            if source_norm in GENERIC_DENY_AS_ANCHOR:
                continue
            in_project = (
                source in project_tokens
                or source_norm in project_tokens
                or any(source_norm in pt or pt in source_norm
                       for pt in project_tokens if len(pt) >= 4)
            )
            if not in_project:
                return False, (
                    f"Migration '{source}' → autre, mais '{source}' n'est "
                    f"pas un composant du projet"
                )

    return True, ""


def _check_anti_plaque(
    finding: Finding,
    verdict_data: dict,
    project: ProjectModel,
) -> tuple[bool, str]:
    """
    Filtre C — Anti-plaque.

    Si real_gain_summary contient un chiffre+unité spécifique du projet
    (40%, 18 mois, < 60 €, ISO 13849, IP67), ce chiffre/standard DOIT
    aussi apparaître dans la description ou le titre du finding source.
    Sinon, le Juge a plaqué l'objectif du projet sur un finding qui ne
    le mentionne pas.

    Returns (passes, reason_if_failed).
    """
    summary = verdict_data.get("real_gain_summary", "")
    if not summary:
        return True, ""

    def _strip(s: str) -> str:
        return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode("ascii")

    summary_norm = _strip(summary)
    finding_text = _strip(f"{finding.title} {finding.description}")
    finding_compact = re.sub(r"\s+", "", finding_text)

    # Extraction des chiffres+unités spécifiques au projet.
    # Note : on utilise (?=\W|$) plutôt que \b car \b ne matche pas après les
    # symboles non-word comme % ou °. "40% vs" doit matcher.
    unit_pattern = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(%|mois|ans?|jours?|h|min|s|"
        r"ma|ua|a|mv|v|kv|w|kw|c|f|hpa|kpa|pa|hz|khz|mhz|ghz|"
        r"km|m|cm|mm|eur|usd|db|dbm|bps|mbps|mo|go|ko|g|kg|rpm|fps|"
        r"ppm|rh|mah|wh)(?=\W|$)"
    )
    project_numbers: set[str] = set()
    sources_text = " ".join(
        project.objectifs_actifs
        + project.contraintes_non_negociables
        + [c.nom for c in project.composants]
    )
    for m in unit_pattern.finditer(_strip(sources_text)):
        num = m.group(1)
        unit = m.group(2)
        project_numbers.add(f"{num}{unit}")
        project_numbers.add(f"{num} {unit}")

    for num_str in project_numbers:
        if num_str not in summary_norm:
            continue
        # Le chiffre projet est cité dans le summary — vérifier qu'il vient du finding.
        num_compact = re.sub(r"\s+", "", num_str)
        if num_str in finding_text or num_compact in finding_compact:
            continue
        return False, (
            f"Chiffre projet '{num_str}' cité dans summary mais absent du "
            f"finding source — plaque détectée"
        )

    # Standards explicites (ISO 13849, IP65, IP67, ERC 70-03, CE, FCC, RoHS)
    standard_pattern = re.compile(
        r"\b(iso\s*\d+(?:[-\s]\d+)*|ip\d{2}|erc\s*\d+(?:[-\s]\d+)*|"
        r"fcc|rohs|reach)\b"
    )
    cnn_text = _strip(
        " ".join(project.objectifs_actifs + project.contraintes_non_negociables)
    )
    for m in standard_pattern.finditer(cnn_text):
        std = m.group(0)
        std_compact = re.sub(r"\s+", "", std)
        if std_compact not in re.sub(r"\s+", "", summary_norm):
            continue
        if std_compact not in re.sub(r"\s+", "", finding_text):
            return False, (
                f"Standard projet '{std}' cité dans summary mais absent du "
                f"finding source — plaque détectée"
            )

    return True, ""


# ─────────────────────────────────────────────────────────────
# Évaluation d'un finding
# ─────────────────────────────────────────────────────────────


def _evaluate_one(
    finding: Finding,
    integration_verdict: IntegrationVerdict,
    judge_context: str,
    project: ProjectModel,
    config: dict,
    max_retries: int = 2,
) -> Optional[JudgeVerdict]:
    """
    Évalue un finding via 3 filtres déterministes + appel LLM.

    Pipeline :
        1. Filtre A (grounding) — si échec : skip LLM, retourne verdict reject.
        2. Appel LLM Juge (mistral/qwen selon config).
        3. Cap relevance si confidence Intégrateur low (règle existante).
        4. Filtres B (migration) et C (anti-plaque) — si échec :
           downgrade timing à noted_for_future (conserve le verdict, le déplace
           hors de la section "À considérer maintenant" du rapport).

    Retourne None après épuisement des retries LLM.
    """
    from src.llm import get_llm

    # ── Filtre A : grounding strict en pré-LLM ─────────────────
    grounding_ok, grounding_reason = _check_grounding(finding, project)
    if not grounding_ok:
        logger.debug("Juge : finding '%s' rejeté pré-LLM (grounding) : %s",
                     finding.id, grounding_reason)
        return JudgeVerdict(
            finding_id=finding.id,
            relevance="reject",
            real_gain_summary=f"Rejet déterministe : {grounding_reason}",
            timing_recommendation="reject",
            rationale=(
                "Le finding ne contient aucun ancrage spécifique du projet "
                "dans son titre ou sa description. Rejeté sans appel LLM "
                "(règle 1bis enforcée déterministement)."
            ),
        )

    prompt = _JUDGE_PROMPT.format(
        judge_context=judge_context,
        title=finding.title,
        component=finding.component_concerned,
        angle=finding.angle,
        description=finding.description,
        effort_level=integration_verdict.effort_level,
        iv_confidence=integration_verdict.confidence,
        required_changes=integration_verdict.required_changes or [],
        risks=integration_verdict.risks or [],
        uncertainties=integration_verdict.uncertainties or [],
        iv_rationale=integration_verdict.rationale,
    )

    llm = get_llm("juge", config)
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
                last_error = "Aucun objet JSON parsable."
                continue

            # finding_id n'est pas demandé au LLM, on l'ajoute ici
            data["finding_id"] = finding.id

            # Filet de sécurité hardcodé : si Intégrateur low confidence,
            # cap relevance à medium même si le LLM Juge a écrit "high".
            if integration_verdict.confidence == "low" and data.get("relevance") == "high":
                logger.debug("Cap relevance high → medium (Intégrateur low confidence) sur %s", finding.id)
                data["relevance"] = "medium"

            # ── Filtre B : migration validator (post-LLM, downgrade) ────
            mig_ok, mig_reason = _check_migration(data, project)
            if not mig_ok:
                logger.debug("Juge : downgrade timing (migration foireuse) sur %s : %s",
                             finding.id, mig_reason)
                data["timing_recommendation"] = "noted_for_future"
                data["rationale"] = (
                    f"[Filtre déterministe B] {mig_reason}. "
                    f"Verdict original : {data.get('rationale', '')[:200]}"
                )

            # ── Filtre C : anti-plaque (post-LLM, downgrade) ────────────
            plaque_ok, plaque_reason = _check_anti_plaque(finding, data, project)
            if not plaque_ok:
                logger.debug("Juge : downgrade timing (plaque chiffre) sur %s : %s",
                             finding.id, plaque_reason)
                data["timing_recommendation"] = "noted_for_future"
                data["rationale"] = (
                    f"[Filtre déterministe C] {plaque_reason}. "
                    f"Verdict original : {data.get('rationale', '')[:200]}"
                )

            verdict = JudgeVerdict(**data)
            return verdict

        except ValidationError as exc:
            last_error = f"Validation Pydantic : {exc.errors()[:2]}"
            logger.debug("Validation échouée tentative %d : %s", attempt, last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.debug("Exception tentative %d : %s", attempt, last_error)

    logger.warning(
        "Juge : échec après %d tentatives sur finding '%s' (%s)",
        max_retries + 1, finding.id, last_error,
    )
    return None


# ─────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────


def run(
    project: ProjectModel,
    findings: list[Finding],
    integration_verdicts: dict[str, IntegrationVerdict],
    config: dict,
    run_dir: Optional[Path] = None,
) -> dict[str, JudgeVerdict]:
    """
    Pour chaque finding intégrable, produit un JudgeVerdict (pertinence + timing).

    Court-circuit interne : les findings dont l'Intégrateur a dit
    integrable=False (ou absents des verdicts) sont skipés sans appel LLM.

    Args:
        project:              ProjectModel parsé.
        findings:             Liste des findings (toute la liste).
        integration_verdicts: Dict finding_id → IntegrationVerdict.
        config:               Config globale (passe-plat vers get_llm).
        run_dir:              Dossier pour les artefacts. None = pas de sauvegarde.

    Returns:
        Dict finding.id → JudgeVerdict. Skipped + échecs absents du dict.
    """
    judge_context = _build_judge_context(project)

    verdicts: dict[str, JudgeVerdict] = {}
    skipped_not_integrable = 0
    skipped_no_verdict = 0
    failed_ids: list[str] = []

    # Compte d'abord ce qu'on va vraiment évaluer pour le log de progression
    to_evaluate = [
        f for f in findings
        if (iv := integration_verdicts.get(f.id)) is not None and iv.integrable
    ]
    logger.info(
        "Juge : %d findings à arbitrer (sur %d total, %d non intégrables ignorés)",
        len(to_evaluate), len(findings),
        sum(1 for f in findings
            if (iv := integration_verdicts.get(f.id)) is None or not iv.integrable),
    )

    for i, finding in enumerate(findings, 1):
        iv = integration_verdicts.get(finding.id)
        if iv is None:
            skipped_no_verdict += 1
            continue
        if not iv.integrable:
            skipped_not_integrable += 1
            continue

        if i % 20 == 0:
            logger.info("Juge : progression %d/%d findings", i, len(findings))

        verdict = _evaluate_one(finding, iv, judge_context, project, config)
        if verdict is None:
            failed_ids.append(finding.id)
            continue
        verdicts[finding.id] = verdict

    # Statistiques agrégées
    by_relevance = {"high": 0, "medium": 0, "low": 0, "reject": 0}
    by_timing = {"now": 0, "next_iteration": 0, "noted_for_future": 0, "reject": 0}
    for v in verdicts.values():
        by_relevance[v.relevance] = by_relevance.get(v.relevance, 0) + 1
        by_timing[v.timing_recommendation] = by_timing.get(v.timing_recommendation, 0) + 1

    logger.info(
        "Juge : %d verdicts produits | relevance %s | timing %s | %d échecs",
        len(verdicts), dict(by_relevance), dict(by_timing), len(failed_ids),
    )

    # ── Sauvegarde des artefacts ───────────────────────────────
    if run_dir is not None:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        verdicts_path = run_dir / "03_juge_verdicts.json"
        verdicts_path.write_text(
            json.dumps(
                {fid: v.model_dump() for fid, v in verdicts.items()},
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Reasoning concaténé en Markdown, trié par relevance puis timing
        reasoning_path = run_dir / "03_juge_reasoning.md"
        rel_order = {"high": 0, "medium": 1, "low": 2, "reject": 3}
        timing_order = {"now": 0, "next_iteration": 1, "noted_for_future": 2, "reject": 3}
        ordered = sorted(
            verdicts.items(),
            key=lambda kv: (
                rel_order.get(kv[1].relevance, 4),
                timing_order.get(kv[1].timing_recommendation, 4),
                kv[0],
            ),
        )

        lines: list[str] = [
            f"# Raisonnement Juge — {project.nom_projet}",
            "",
            f"Findings totaux : {len(findings)}",
            f"Non intégrables (skipped) : {skipped_not_integrable}",
            f"Verdicts produits : {len(verdicts)}",
            f"Échecs : {len(failed_ids)}",
            "",
            f"Distribution relevance : {dict(by_relevance)}",
            f"Distribution timing : {dict(by_timing)}",
            "",
            "---",
            "",
        ]
        for fid, v in ordered:
            f = next((f for f in findings if f.id == fid), None)
            title = f.title if f else "?"
            component = f.component_concerned if f else "?"
            lines += [
                f"## [{v.relevance}/{v.timing_recommendation}] {title}",
                f"- ID : `{fid}` | Composant : {component}",
                f"- Gain réel : {v.real_gain_summary}",
                f"- Raisonnement : {v.rationale}",
                "",
            ]
        reasoning_path.write_text("\n".join(lines), encoding="utf-8")

    return verdicts
