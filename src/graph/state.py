"""
État partagé du graphe LangGraph.

TechWatchState est le "tableau blanc" du pipeline. Chaque nœud du graphe
le lit et l'écrit. LangGraph garantit la cohérence des mises à jour.

C'est un TypedDict (dict typé Python standard) — LangGraph l'exige.
La validation des contenus est assurée par les schémas Pydantic de src/models.py.
"""

from __future__ import annotations

from typing import TypedDict

from src.models import Finding, IntegrationVerdict, JudgeVerdict, ValidatedSuggestion


class TechWatchState(TypedDict):
    """
    État partagé entre tous les nœuds du graphe LangGraph.

    Champs :
        project_md:          Contenu brut du fichier .md projet (string Markdown).
        findings:            Findings produits par l'Éclaireur.
        integration_verdicts: Dict finding.id → IntegrationVerdict (Intégrateur).
        judge_verdicts:      Dict finding.id → JudgeVerdict (Juge).
        validated_suggestions: Suggestions structurées pour les findings retenus.
        final_report:        Rapport Markdown final (Rapporteur).
        errors:              Erreurs non fatales accumulées au fil du pipeline.
    """

    project_md: str
    findings: list[Finding]
    integration_verdicts: dict[str, IntegrationVerdict]
    judge_verdicts: dict[str, JudgeVerdict]
    validated_suggestions: list[ValidatedSuggestion]
    final_report: str
    errors: list[str]
