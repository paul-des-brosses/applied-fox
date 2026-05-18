"""
Agent Rapporteur — Synthèse finale + production des ValidatedSuggestion.

Stratégie volontairement majoritairement DÉTERMINISTE :
    - Le format détaillé de chaque suggestion est généré par templating Python
      depuis les Finding + IntegrationVerdict + JudgeVerdict, sans LLM.
    - La déduplication thématique est faite par groupage déterministe
      (par couple component_concerned × angle).
    - Le LLM n'intervient QUE pour la "Synthèse en une ligne" en tête de rapport
      (1 seul appel total, pas 1 par finding).

Pourquoi déterministe : sur un LLM 7B avec 100+ findings à digérer, un appel
LLM par section produit des rendus inconsistants en ton/structure. Le
templating garantit un rapport au format strict défini dans ARCHITECTURE.md,
auditable, et reproductible.

Trois sections produites :
    1. À considérer maintenant — déduplication par thème, max 10 items détaillés
    2. À noter pour plus tard — format condensé
    3. Rejetés — format ultra-condensé avec raison

Produit en sortie :
    - rapport Markdown (passé à src/reporting/ pour conversion HTML)
    - liste de ValidatedSuggestion (utilisée par l'Interviewer mode integrate)

Implémentation : Jalon 5c.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import (
    Finding,
    IntegrationVerdict,
    JudgeVerdict,
    ProjectModel,
    ValidatedSuggestion,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Groupage / déduplication thématique
# ─────────────────────────────────────────────────────────────


def _group_by_theme(
    findings: list[Finding],
    judge_verdicts: dict[str, JudgeVerdict],
    integration_verdicts: dict[str, IntegrationVerdict],
    relevance_filter: tuple[str, ...] = ("high", "medium"),
    timing_filter: tuple[str, ...] = ("now",),
) -> dict[tuple[str, str], list[Finding]]:
    """
    Groupe les findings par (component_concerned, angle) après filtre relevance/timing.

    L'objectif est la déduplication thématique : si 5 findings parlent tous
    de "Module LoRa SX1276 + angle perf", on les groupe pour produire UN
    seul item de rapport au lieu de 5 doublons.

    Returns:
        Dict (component, angle) → list de findings du même thème.
    """
    groups: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for f in findings:
        jv = judge_verdicts.get(f.id)
        if jv is None:
            continue
        if jv.relevance not in relevance_filter:
            continue
        if jv.timing_recommendation not in timing_filter:
            continue
        if f.id not in integration_verdicts:
            continue
        key = (f.component_concerned, f.angle)
        groups[key].append(f)
    return groups


def _select_top_per_group(
    groups: dict[tuple[str, str], list[Finding]],
    judge_verdicts: dict[str, JudgeVerdict],
    integration_verdicts: dict[str, IntegrationVerdict],
    max_items: int = 10,
) -> list[Finding]:
    """
    Pour chaque groupe thématique, sélectionne le meilleur représentant :
        - Critère 1 : relevance Juge (high > medium)
        - Critère 2 : confidence Intégrateur (high > medium > low)
        - Critère 3 : effort Intégrateur (trivial > minor > moderate)

    Limite ensuite à max_items au global (priorise les high relevance).
    """
    rel_score = {"high": 0, "medium": 1, "low": 2, "reject": 3}
    conf_score = {"high": 0, "medium": 1, "low": 2}
    eff_score = {"trivial": 0, "minor": 1, "moderate": 2, "major": 3, "blocking": 4}

    representatives: list[Finding] = []
    for theme, theme_findings in groups.items():
        best = min(
            theme_findings,
            key=lambda f: (
                rel_score.get(judge_verdicts[f.id].relevance, 9),
                conf_score.get(integration_verdicts[f.id].confidence, 9),
                eff_score.get(integration_verdicts[f.id].effort_level, 9),
            ),
        )
        representatives.append(best)

    # Tri global par (relevance, confidence, effort) et cap au max
    representatives.sort(
        key=lambda f: (
            rel_score.get(judge_verdicts[f.id].relevance, 9),
            conf_score.get(integration_verdicts[f.id].confidence, 9),
            eff_score.get(integration_verdicts[f.id].effort_level, 9),
        ),
    )
    return representatives[:max_items]


# ─────────────────────────────────────────────────────────────
# Rendu d'une section détaillée — déterministe
# ─────────────────────────────────────────────────────────────


def _render_consider_now_item(
    finding: Finding,
    iv: IntegrationVerdict,
    jv: JudgeVerdict,
    group_findings: list[Finding],
) -> str:
    """
    Rend un seul item détaillé pour la section "À considérer maintenant".
    Format exact : cf. docs/ARCHITECTURE.md.
    """
    timing_label = {
        "now": "Maintenant",
        "next_iteration": "Prochaine itération",
        "noted_for_future": "À noter pour plus tard",
    }.get(jv.timing_recommendation, "À noter")

    lines: list[str] = []
    lines.append(f"### {finding.title}")
    lines.append(f"**Angle** : {finding.angle}")
    lines.append(f"**Source** : [{finding.source_type}]({finding.source_url})")
    lines.append("")
    lines.append(f"**Ce qui change** : {jv.real_gain_summary}")
    lines.append("")
    lines.append("**Impact pour ton projet** :")
    lines.append(f"- Gain : {jv.real_gain_summary}")
    lines.append(f"- Effort d'intégration : **{iv.effort_level}**")
    if iv.required_changes:
        lines.append("- Modifications nécessaires :")
        for c in iv.required_changes:
            lines.append(f"  - {c}")
    if iv.risks:
        lines.append("- Risques identifiés :")
        for r in iv.risks:
            lines.append(f"  - {r}")
    if iv.uncertainties:
        lines.append("- Incertitudes :")
        for u in iv.uncertainties:
            lines.append(f"  - {u}")
    lines.append("")
    lines.append(f"**Recommandation** : {timing_label}")

    # Si plusieurs findings dans le groupe thématique, on liste les sources additionnelles.
    other_sources = [f for f in group_findings if f.id != finding.id]
    if other_sources:
        lines.append("")
        lines.append(f"<em>Sources additionnelles ({len(other_sources)}) :</em>")
        for o in other_sources[:5]:  # limite pour ne pas surcharger
            lines.append(f"- [{o.source_type}]({o.source_url}) — {o.title[:80]}")

    lines.append("")
    return "\n".join(lines)


def _render_later_section(
    findings: list[Finding],
    judge_verdicts: dict[str, JudgeVerdict],
) -> str:
    """
    Section "À noter pour plus tard" — format condensé une ligne par finding.

    Ne contient que les findings `noted_for_future` (les `next_iteration` sont
    remontés en section principale comme suggestions actionnables).
    """
    later = [
        (f, judge_verdicts[f.id])
        for f in findings
        if f.id in judge_verdicts
        and judge_verdicts[f.id].timing_recommendation == "noted_for_future"
    ]
    if not later:
        return "_Aucun finding à noter pour plus tard._\n"

    # Tri par relevance (high d'abord)
    rel_score = {"high": 0, "medium": 1, "low": 2, "reject": 3}
    later.sort(key=lambda fv: rel_score.get(fv[1].relevance, 9))

    lines: list[str] = []
    for f, jv in later:
        timing = jv.timing_recommendation.replace("_", " ")
        lines.append(
            f"- **{f.title[:90]}** — {jv.real_gain_summary[:120]} "
            f"_(timing : {timing} · angle : {f.angle})_"
        )
    return "\n".join(lines) + "\n"


def _render_rejected_section(
    findings: list[Finding],
    judge_verdicts: dict[str, JudgeVerdict],
    integration_verdicts: dict[str, IntegrationVerdict],
) -> str:
    """
    Section "Rejetés" — ultra condensé. Inclut deux types :
        1. Findings jugés "reject" par le Juge
        2. Findings non intégrables (integrable=False), donc jamais passés au Juge
    """
    rejected: list[tuple[Finding, str]] = []

    for f in findings:
        jv = judge_verdicts.get(f.id)
        iv = integration_verdicts.get(f.id)
        if jv and jv.relevance == "reject":
            rejected.append((f, f"Jugé non pertinent : {jv.rationale[:100]}"))
        elif iv and not iv.integrable:
            rejected.append((f, f"Non intégrable ({iv.effort_level}) : {iv.rationale[:100]}"))

    if not rejected:
        return "_Aucun finding rejeté._\n"

    lines: list[str] = []
    for f, reason in rejected[:30]:  # cap visuel
        lines.append(f"- **{f.title[:80]}** — {reason}")
    if len(rejected) > 30:
        lines.append(f"- _... et {len(rejected) - 30} autres rejets (voir 02/03_*_reasoning.md)_")
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────
# Synthèse en une ligne (seul appel LLM du Rapporteur)
# ─────────────────────────────────────────────────────────────


def _generate_synthesis_line(
    project: ProjectModel,
    top_findings: list[Finding],
    judge_verdicts: dict[str, JudgeVerdict],
    config: dict,
) -> str:
    """
    Demande au LLM une phrase de synthèse en tête de rapport.

    UN seul appel LLM dans tout le Rapporteur. Si le LLM échoue ou est down,
    fallback déterministe sur un message générique.
    """
    if not top_findings:
        return (
            "Aucune suggestion prioritaire identifiée dans ce run. "
            "Voir les sections suivantes pour les findings en arrière-plan."
        )

    try:
        from langchain_core.messages import HumanMessage

        from src.llm import get_llm

        # Liste compacte des top findings pour le prompt
        top_lines = []
        for f in top_findings[:5]:
            jv = judge_verdicts.get(f.id)
            gain = jv.real_gain_summary[:100] if jv else "?"
            top_lines.append(f"- [{f.angle}] {f.component_concerned} : {gain}")

        prompt = (
            f"Tu es le Rapporteur d'Applied Fox. Tâche : écrire UNE seule phrase "
            f"de synthèse pour le rapport de veille du projet \"{project.nom_projet}\".\n\n"
            f"Cette phrase doit résumer le thème principal des suggestions prioritaires "
            f"ci-dessous, en français, sans formule rituelle, sans liste, en 25-35 mots.\n\n"
            f"Suggestions prioritaires :\n" + "\n".join(top_lines) + "\n\n"
            "Réponds UNIQUEMENT par la phrase de synthèse, sans guillemets, "
            "sans préfixe \"Voici\" ou similaire. Une seule phrase."
        )

        llm = get_llm("rapporteur", config)
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        synthesis = content.strip().split("\n")[0].strip()
        # Retire les guillemets éventuels
        if synthesis.startswith('"') and synthesis.endswith('"'):
            synthesis = synthesis[1:-1].strip()
        if synthesis:
            return synthesis

    except Exception as exc:  # noqa: BLE001
        logger.warning("Synthèse Rapporteur a échoué : %s — fallback déterministe.", exc)

    # Fallback déterministe
    return (
        f"{len(top_findings)} suggestions actionnables identifiées pour {project.nom_projet}, "
        f"principalement autour des objectifs d'autonomie et d'optimisation des composants critiques."
    )


# ─────────────────────────────────────────────────────────────
# Construction des ValidatedSuggestion (déterministe)
# ─────────────────────────────────────────────────────────────


def _build_suggestion(
    finding: Finding,
    iv: IntegrationVerdict,
    jv: JudgeVerdict,
) -> ValidatedSuggestion:
    """
    Construit une ValidatedSuggestion depuis finding + verdicts, sans LLM.

    Les champs du modèle se mappent naturellement sur les artefacts existants :
        - title                  ← finding.title
        - changes_summary        ← jv.real_gain_summary
        - components_affected    ← [finding.component_concerned]
        - integration_notes      ← iv.rationale
        - open_questions         ← iv.uncertainties (questions à clarifier
                                    par l'Interviewer en mode integrate)
        - interactions_changes   ← iv.required_changes
        - new_components         ← [] (extraction LLM hors MVP)
        - constraints_impact     ← {} (idem)
    """
    return ValidatedSuggestion(
        title=finding.title[:200],
        changes_summary=jv.real_gain_summary[:500],
        components_affected=[finding.component_concerned] if finding.component_concerned else [],
        new_components=[],
        interactions_changes=iv.required_changes or [],
        constraints_impact={},
        integration_notes=iv.rationale[:500],
        open_questions=iv.uncertainties or [],
    )


# ─────────────────────────────────────────────────────────────
# Rendu du rapport complet
# ─────────────────────────────────────────────────────────────


def _render_metadata_section(
    project: ProjectModel,
    findings: list[Finding],
    integration_verdicts: dict,
    judge_verdicts: dict,
    suggestions: list[ValidatedSuggestion],
    run_dir: Optional[Path],
) -> str:
    """Section finale du rapport : métadonnées du run."""
    lines = [
        f"- Date du run : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Findings bruts collectés : {len(findings)}",
        f"- Verdicts d'intégration : {len(integration_verdicts)}",
        f"- Verdicts du Juge : {len(judge_verdicts)}",
        f"- Suggestions finales retenues : {len(suggestions)}",
    ]
    if run_dir is not None:
        lines.append(f"- Artefacts détaillés : `{run_dir}`")
    return "\n".join(lines) + "\n"


def _count_sources(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for f in findings:
        counts[f.source_type] += 1
    return dict(counts)


def _build_full_report(
    project: ProjectModel,
    findings: list[Finding],
    integration_verdicts: dict[str, IntegrationVerdict],
    judge_verdicts: dict[str, JudgeVerdict],
    consider_now_groups: dict[tuple[str, str], list[Finding]],
    consider_now_top: list[Finding],
    suggestions: list[ValidatedSuggestion],
    synthesis_line: str,
    run_dir: Optional[Path],
) -> str:
    """Assemble le rapport Markdown complet."""
    today = datetime.now().strftime("%Y-%m-%d")
    n_kept_priority = len(consider_now_top)
    n_total_priority = sum(len(g) for g in consider_now_groups.values())

    parts: list[str] = []
    parts.append(f"# Rapport de veille — {project.nom_projet}")
    parts.append(
        f"*Généré le {today}, {len(findings)} findings analysés, "
        f"{n_kept_priority} suggestions retenues "
        f"(déduplication thématique sur {n_total_priority} findings prioritaires).*"
    )
    parts.append("")

    parts.append("## Synthèse en une ligne")
    parts.append(synthesis_line)
    parts.append("")

    parts.append("## À considérer maintenant")
    if consider_now_top:
        for f in consider_now_top:
            iv = integration_verdicts[f.id]
            jv = judge_verdicts[f.id]
            group_findings = consider_now_groups.get((f.component_concerned, f.angle), [f])
            parts.append(_render_consider_now_item(f, iv, jv, group_findings))
    else:
        parts.append("_Aucune suggestion prioritaire identifiée dans ce run._")
        parts.append("")

    parts.append("## À noter pour plus tard")
    parts.append(_render_later_section(findings, judge_verdicts))

    parts.append("## Rejetés (avec raison)")
    parts.append(_render_rejected_section(findings, judge_verdicts, integration_verdicts))

    parts.append("## Sources consultées")
    counts = _count_sources(findings)
    if counts:
        for src_type, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            parts.append(f"- **{src_type}** : {n} findings bruts")
    else:
        parts.append("_Aucune source._")
    parts.append("")

    parts.append("## Métadonnées du run")
    parts.append(_render_metadata_section(
        project, findings, integration_verdicts, judge_verdicts, suggestions, run_dir,
    ))

    parts.append("---")
    parts.append("*Généré par Applied Fox — pipeline multi-agent local.*")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────


def run(
    findings: list[Finding],
    integration_verdicts: dict[str, IntegrationVerdict],
    judge_verdicts: dict[str, JudgeVerdict],
    project: ProjectModel,
    config: dict,
    run_dir: Optional[Path] = None,
    max_priority_items: int = 10,
) -> tuple[str, list[ValidatedSuggestion]]:
    """
    Génère le rapport Markdown final et la liste de ValidatedSuggestion.

    Le rapport suit le format strict décrit dans docs/ARCHITECTURE.md.
    La déduplication thématique réduit potentiellement 40+ findings high+now
    à ~10 suggestions distinctes.

    Args:
        findings:             Tous les findings de l'Éclaireur.
        integration_verdicts: Dict finding_id → IntegrationVerdict.
        judge_verdicts:       Dict finding_id → JudgeVerdict.
        project:              ProjectModel parsé (utilisé pour la synthèse).
        config:               Config globale (passé à get_llm pour la synthèse).
        run_dir:              Dossier où sauvegarder le rapport. None → pas de sauvegarde.
        max_priority_items:   Cap sur le nombre d'items détaillés "À considérer".

    Returns:
        Tuple (rapport_markdown, list[ValidatedSuggestion]).
    """
    logger.info(
        "Rapporteur : démarrage (%d findings, %d verdicts int, %d verdicts juge)",
        len(findings), len(integration_verdicts), len(judge_verdicts),
    )

    # 1. Groupage et déduplication
    # Les findings classés "now" et "next_iteration" sont tous deux retenus comme
    # suggestions actionnables — la différence est l'urgence, pas la pertinence.
    # Seuls les "noted_for_future" partent dans la section condensée du rapport.
    consider_now_groups = _group_by_theme(
        findings, judge_verdicts, integration_verdicts,
        relevance_filter=("high", "medium"),
        timing_filter=("now", "next_iteration"),
    )
    consider_now_top = _select_top_per_group(
        consider_now_groups, judge_verdicts, integration_verdicts,
        max_items=max_priority_items,
    )
    logger.info(
        "Rapporteur : %d groupes thématiques → %d suggestions retenues",
        len(consider_now_groups), len(consider_now_top),
    )

    # 2. ValidatedSuggestion pour chaque représentant (déterministe)
    suggestions = [
        _build_suggestion(f, integration_verdicts[f.id], judge_verdicts[f.id])
        for f in consider_now_top
    ]

    # 3. Synthèse LLM (1 seul appel)
    synthesis_line = _generate_synthesis_line(
        project, consider_now_top, judge_verdicts, config,
    )

    # 4. Construction du rapport Markdown complet
    report_md = _build_full_report(
        project, findings, integration_verdicts, judge_verdicts,
        consider_now_groups, consider_now_top, suggestions,
        synthesis_line, run_dir,
    )

    # 5. Sauvegarde des artefacts
    if run_dir is not None:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        md_path = run_dir / "04_rapport.md"
        md_path.write_text(report_md, encoding="utf-8")

        # ValidatedSuggestion → JSON pour utilisation Jalon 6 (Interview integrate)
        import json
        suggestions_path = run_dir / "04_validated_suggestions.json"
        suggestions_path.write_text(
            json.dumps(
                [s.model_dump() for s in suggestions],
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # HTML pour ouverture navigateur
        try:
            from src.reporting import save_html_report
            html_path = save_html_report(
                report_md,
                run_dir / "04_rapport.html",
                project_name=project.nom_projet,
            )
            logger.info("Rapport HTML écrit : %s", html_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Conversion HTML a échoué (mistune ?) : %s", exc)

    return report_md, suggestions
