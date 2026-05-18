"""
Définition du graphe LangGraph du pipeline de veille.

Au Jalon 3, le graphe est minimal : un seul nœud (Éclaireur), pas de branchement.
Aux jalons suivants, on ajoutera Intégrateur, Juge, Rapporteur + le branchement
conditionnel sur IntegrationVerdict.integrable.

Pourquoi LangGraph dès le Jalon 3 alors qu'on a un seul nœud ?
    Cf. docs/DECISIONS.md §6 — c'est l'architecture cible et ça coûte rien
    de la mettre en place dès maintenant. Le câblage est trivial avec un nœud,
    et on évite un refactor au Jalon 5.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.graph.state import TechWatchState
from src.models import ProjectModel

logger = logging.getLogger(__name__)


def _eclaireur_node_factory(project: ProjectModel, config: dict, run_dir: Optional[Path]):
    """
    Construit le nœud LangGraph de l'Éclaireur.

    Le nœud lit project_md (informationnel) et écrit findings dans l'état.
    Les erreurs non fatales sont accumulées dans state.errors.
    """
    from src.agents import eclaireur

    def node(state: TechWatchState) -> dict:
        try:
            findings = eclaireur.run(project, config, run_dir=run_dir)
            return {"findings": findings}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Éclaireur a échoué")
            errors = list(state.get("errors", []))
            errors.append(f"eclaireur: {exc}")
            return {"findings": [], "errors": errors}

    return node


def _integrateur_node_factory(project: ProjectModel, config: dict, run_dir: Optional[Path]):
    """
    Construit le nœud LangGraph de l'Intégrateur.

    Le nœud lit state["findings"] et écrit state["integration_verdicts"].
    Comme pour l'Éclaireur, les erreurs non fatales sont accumulées dans
    state.errors et n'arrêtent pas le pipeline.
    """
    from src.agents import integrateur

    def node(state: TechWatchState) -> dict:
        findings = state.get("findings", [])
        if not findings:
            logger.info("Intégrateur : aucun finding à évaluer, skip.")
            return {"integration_verdicts": {}}
        try:
            verdicts = integrateur.run(project, findings, config, run_dir=run_dir)
            return {"integration_verdicts": verdicts}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Intégrateur a échoué")
            errors = list(state.get("errors", []))
            errors.append(f"integrateur: {exc}")
            return {"integration_verdicts": {}, "errors": errors}

    return node


def _juge_node_factory(project: ProjectModel, config: dict, run_dir: Optional[Path]):
    """
    Construit le nœud LangGraph du Juge.

    Lit state["findings"] + state["integration_verdicts"], écrit state["judge_verdicts"].
    Le filtrage par finding (integrable=True) est fait dans juge.run.
    """
    from src.agents import juge

    def node(state: TechWatchState) -> dict:
        findings = state.get("findings", [])
        integration_verdicts = state.get("integration_verdicts", {})
        if not findings or not integration_verdicts:
            logger.info("Juge : pas de findings ou verdicts en amont, skip.")
            return {"judge_verdicts": {}}
        try:
            verdicts = juge.run(project, findings, integration_verdicts, config, run_dir=run_dir)
            return {"judge_verdicts": verdicts}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Juge a échoué")
            errors = list(state.get("errors", []))
            errors.append(f"juge: {exc}")
            return {"judge_verdicts": {}, "errors": errors}

    return node


def _rapporteur_node_factory(project: ProjectModel, config: dict, run_dir: Optional[Path]):
    """
    Construit le nœud LangGraph du Rapporteur.

    Lit findings + integration_verdicts + judge_verdicts.
    Écrit final_report (Markdown) et validated_suggestions (list[ValidatedSuggestion]).
    Sauvegarde le rapport HTML sur disque via src.reporting (artefact 04_rapport.html).
    """
    from src.agents import rapporteur

    def node(state: TechWatchState) -> dict:
        findings = state.get("findings", [])
        integration_verdicts = state.get("integration_verdicts", {})
        judge_verdicts = state.get("judge_verdicts", {})
        if not findings:
            logger.info("Rapporteur : aucun finding, skip.")
            return {"final_report": "", "validated_suggestions": []}
        try:
            report_md, suggestions = rapporteur.run(
                findings, integration_verdicts, judge_verdicts,
                project, config, run_dir=run_dir,
            )
            return {
                "final_report": report_md,
                "validated_suggestions": suggestions,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Rapporteur a échoué")
            errors = list(state.get("errors", []))
            errors.append(f"rapporteur: {exc}")
            return {
                "final_report": "",
                "validated_suggestions": [],
                "errors": errors,
            }

    return node


def _route_after_integrateur(state: TechWatchState) -> str:
    """
    Routage conditionnel après l'Intégrateur :
        - s'il y a au moins un finding intégrable → on continue vers le Juge.
        - sinon (tous bloquants ou aucun verdict) → on saute directement à END.

    Économise l'appel LLM Juge sur des runs sans candidat actionnable.
    """
    verdicts = state.get("integration_verdicts", {})
    has_integrable = any(getattr(v, "integrable", False) for v in verdicts.values())
    if has_integrable:
        return "juge"
    logger.info("Aucun finding intégrable — court-circuit du Juge.")
    return "skip_juge"


def build_graph(
    project: ProjectModel,
    config: dict,
    run_dir: Optional[Path] = None,
):
    """
    Construit et compile le graphe LangGraph.

    Jalon 5b : Éclaireur → Intégrateur → [conditionnel] → Juge → END.
    Si aucun finding n'est intégrable, on court-circuite le Juge.

    Returns:
        Un graphe compilé prêt à être invoqué via .invoke(initial_state).
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(TechWatchState)
    graph.add_node("eclaireur", _eclaireur_node_factory(project, config, run_dir))
    graph.add_node("integrateur", _integrateur_node_factory(project, config, run_dir))
    graph.add_node("juge", _juge_node_factory(project, config, run_dir))
    graph.add_node("rapporteur", _rapporteur_node_factory(project, config, run_dir))

    graph.add_edge(START, "eclaireur")
    graph.add_edge("eclaireur", "integrateur")
    # Branchement conditionnel : si aucun finding intégrable, on saute le Juge
    # mais on passe quand même au Rapporteur (qui produira la section "Rejetés").
    graph.add_conditional_edges(
        "integrateur",
        _route_after_integrateur,
        {"juge": "juge", "skip_juge": "rapporteur"},
    )
    graph.add_edge("juge", "rapporteur")
    graph.add_edge("rapporteur", END)
    return graph.compile()


def initial_state(project_md: str) -> TechWatchState:
    """
    Construit l'état initial à passer au graphe.
    Tous les champs aval sont vides — chaque nœud les remplira à son tour.
    """
    return TechWatchState(
        project_md=project_md,
        findings=[],
        integration_verdicts={},
        judge_verdicts={},
        validated_suggestions=[],
        final_report="",
        errors=[],
    )
