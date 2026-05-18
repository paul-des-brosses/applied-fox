"""
Schémas Pydantic partagés entre tous les agents et modules du pipeline.

Ces types définissent le contrat de communication interne du système.
Tout échange de données entre agents passe par ces structures — jamais par
du texte Markdown libre (sauf la sortie finale du Rapporteur destinée à l'utilisateur).

Pourquoi Pydantic ? Il valide automatiquement les types au moment de la création
de l'objet, et lève une erreur claire si un champ est manquant ou mal typé.
C'est la protection contre les hallucinations de structure des LLMs.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Schémas du pipeline de veille
# ─────────────────────────────────────────────────────────────


class ComponentClassification(BaseModel):
    """
    Classification déterministe des références composants dans un finding.

    Produite par l'Éclaireur en post-structuration. Permet aux agents en aval
    (Intégrateur, Juge) de distinguer immédiatement les composants connus du
    projet de ceux introduits par le finding — sans rejouer l'extraction et
    sans risquer d'halluciner sur des références opaques.

    Champ ajouté Niveau 2 (cf. docs/evaluations) pour résoudre les
    hallucinations sur composants nouveaux (ex: BQ25616, MAX-M10S).
    """

    in_project: list[str] = Field(default_factory=list)
    """Références composants détectées qui matchent un composant du projet."""

    new_mentioned: list[str] = Field(default_factory=list)
    """Références composants détectées qui ne matchent aucun composant du projet."""


class Finding(BaseModel):
    """
    Un finding est une découverte brute produite par l'Éclaireur.
    Il représente une information potentiellement pertinente sur
    un composant ou une technologie du projet.
    """

    id: str  # hash stable : sha256(component_concerned + title + source_url)[:12]
    title: str
    component_concerned: str
    angle: Literal["perf", "price", "supply", "energy", "regulation", "obsolescence"]
    description: str
    source_url: str
    source_type: Literal["manufacturer", "community", "marketplace", "paper", "news"]
    raw_data: dict = Field(default_factory=dict)  # specs brutes extraites de la source
    component_classification: Optional[ComponentClassification] = None
    """Classification des composants mentionnés (None = artefact pré-Niveau 2)."""


class IntegrationVerdict(BaseModel):
    """
    Verdict de l'Intégrateur sur la faisabilité d'intégration d'un finding.
    Répond à : "Est-ce intégrable dans ce projet, et à quel prix ?"
    """

    finding_id: str
    integrable: bool
    effort_level: Literal["trivial", "minor", "moderate", "major", "blocking"]
    required_changes: list[str]
    risks: list[str]
    uncertainties: list[str]
    confidence: Literal["high", "medium", "low"]
    rationale: str  # raisonnement en clair, extrait dans 02_integrateur_reasoning.md


class JudgeVerdict(BaseModel):
    """
    Verdict du Juge sur la pertinence d'un finding pour les objectifs actifs du projet.
    Répond à : "Ce finding vaut-il la peine d'être présenté à l'utilisateur, et quand ?"
    """

    finding_id: str
    relevance: Literal["high", "medium", "low", "reject"]
    real_gain_summary: str
    timing_recommendation: Literal["now", "next_iteration", "noted_for_future", "reject"]
    rationale: str  # extrait dans 03_juge_reasoning.md


class ValidatedSuggestion(BaseModel):
    """
    Suggestion structurée produite par le Rapporteur pour chaque finding retenu.
    Transmise à l'Interviewer en mode 'integrate' après validation utilisateur.
    Contient tout ce dont l'Interviewer a besoin pour modifier le .md projet.
    """

    title: str
    changes_summary: str
    components_affected: list[str]
    new_components: list[dict] = Field(default_factory=list)
    interactions_changes: list[str] = Field(default_factory=list)
    constraints_impact: dict = Field(default_factory=dict)
    integration_notes: str
    open_questions: list[str] = Field(default_factory=list)  # clarifiés par l'Interviewer


# ─────────────────────────────────────────────────────────────
# Schéma du fichier projet .md (ProjectModel)
# Spec complète : docs/MD_SCHEMA.md
# ─────────────────────────────────────────────────────────────

from datetime import date


PhaseType = Literal["exploration", "prototype", "pré-production", "déployé"]
DomaineType = Literal["hardware", "software", "hybride"]
StatutDecisionnelType = Literal["figé", "validé", "en évaluation"]
RolePipelineType = Literal["critique", "support", "accessoire"]
NatureRenduType = Literal["démo", "livraison client", "soutenance", "release", "N/A"]


class Identite(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    phase: PhaseType
    domaine: DomaineType
    derniere_mise_a_jour: date


class ProchainRendu(BaseModel):
    # "date" entre en collision avec le type importé sous from __future__ import annotations
    # → on utilise "date_prevue" pour éviter l'ambiguïté à la résolution des annotations.
    date_prevue: Optional[date] = None  # None représente "N/A"
    nature: NatureRenduType
    contenu_attendu: str


class Composant(BaseModel):
    nom: str
    role: str
    statut_decisionnel: StatutDecisionnelType
    role_pipeline: RolePipelineType


class StackItem(BaseModel):
    outil: str
    role: str
    version: str
    statut_decisionnel: StatutDecisionnelType


class Interaction(BaseModel):
    source: str
    target: str
    nature: str
    format: Optional[str] = None
    volume: Optional[str] = None


class CritereContrainte(BaseModel):
    nom: str
    valeur: str  # valeur définie, "N/A", ou "TBD : justification"


class SousSectionContraintes(BaseModel):
    titre: str
    criteres: list[CritereContrainte]


class Changement(BaseModel):
    date_changement: date
    resume: str


class ProjectModel(BaseModel):
    """
    Représentation Python du fichier .md projet.
    Produit par le parser Markdown du module validation/structural.py.
    Consommé par tous les agents du pipeline de veille.
    """

    nom_projet: str
    identite: Identite
    description: str = Field(min_length=50, max_length=500)
    objectifs_actifs: list[str] = Field(min_length=1)
    prochain_rendu: ProchainRendu
    composants: list[Composant] = Field(min_length=1)
    stack_software: list[StackItem] = Field(min_length=1)
    interactions: list[Interaction] = Field(min_length=1)
    contraintes: list[SousSectionContraintes] = Field(min_length=1)
    contraintes_non_negociables: list[str] = Field(min_length=1)
    changements: list[Changement] = Field(min_length=1)
