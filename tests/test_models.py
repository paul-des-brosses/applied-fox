"""
Tests des schémas Pydantic de src/models.py.

Ces tests sont purement déterministes — ils ne nécessitent aucun LLM.
Ils vérifient que les schémas acceptent les entrées valides et rejettent les invalides.

Lancement : pytest tests/test_models.py -v
"""

import pytest
from datetime import date
from pydantic import ValidationError

from src.models import (
    Finding,
    IntegrationVerdict,
    JudgeVerdict,
    ValidatedSuggestion,
    ProjectModel,
    Identite,
    ProchainRendu,
    Composant,
    StackItem,
    Interaction,
    SousSectionContraintes,
    CritereContrainte,
    Changement,
)


# ─────────────────────────────────────────────────────────────
# Fixtures — données de base valides
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def valid_finding():
    return Finding(
        id="abc123def456",
        title="BME680 : successeur du BME280 avec qualité d'air",
        component_concerned="BME280",
        angle="perf",
        description="Le BME680 ajoute la mesure de qualité d'air (VOC) au BME280 standard.",
        source_url="https://reddit.com/r/embedded/comments/example",
        source_type="community",
    )


@pytest.fixture
def valid_integration_verdict():
    return IntegrationVerdict(
        finding_id="abc123def456",
        integrable=True,
        effort_level="minor",
        required_changes=["Remplacer le driver BME280 par le driver BME680", "Mettre à jour les interactions I2C"],
        risks=["Disponibilité du BME680 à vérifier"],
        uncertainties=["Impact sur la consommation énergétique non mesuré"],
        confidence="medium",
        rationale="Le BME680 est compatible pinout avec le BME280, la migration est simple.",
    )


@pytest.fixture
def valid_judge_verdict():
    return JudgeVerdict(
        finding_id="abc123def456",
        relevance="high",
        real_gain_summary="Ajout de mesure VOC sans refonte matérielle.",
        timing_recommendation="next_iteration",
        rationale="Gain réel mais non critique pour le prochain rendu.",
    )


# ─────────────────────────────────────────────────────────────
# Tests Finding
# ─────────────────────────────────────────────────────────────

class TestFinding:
    def test_valid_finding(self, valid_finding):
        assert valid_finding.id == "abc123def456"
        assert valid_finding.angle == "perf"
        assert valid_finding.source_type == "community"

    def test_invalid_angle(self):
        with pytest.raises(ValidationError):
            Finding(
                id="x",
                title="Test",
                component_concerned="ESP32",
                angle="inconnu",  # valeur hors enum
                description="...",
                source_url="https://example.com",
                source_type="community",
            )

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            Finding(
                id="x",
                title="Test",
                component_concerned="ESP32",
                angle="perf",
                description="...",
                source_url="https://example.com",
                source_type="blog",  # valeur hors enum
            )

    def test_raw_data_defaults_empty(self, valid_finding):
        assert valid_finding.raw_data == {}


# ─────────────────────────────────────────────────────────────
# Tests IntegrationVerdict
# ─────────────────────────────────────────────────────────────

class TestIntegrationVerdict:
    def test_valid(self, valid_integration_verdict):
        assert valid_integration_verdict.integrable is True
        assert valid_integration_verdict.effort_level == "minor"

    def test_invalid_effort_level(self):
        with pytest.raises(ValidationError):
            IntegrationVerdict(
                finding_id="x",
                integrable=True,
                effort_level="huge",  # hors enum
                required_changes=[],
                risks=[],
                uncertainties=[],
                confidence="high",
                rationale="...",
            )

    def test_not_integrable(self):
        v = IntegrationVerdict(
            finding_id="y",
            integrable=False,
            effort_level="blocking",
            required_changes=["Refonte complète de l'alimentation"],
            risks=["Risque de court-circuit"],
            uncertainties=[],
            confidence="high",
            rationale="Incompatibilité de tension.",
        )
        assert v.integrable is False
        assert v.effort_level == "blocking"


# ─────────────────────────────────────────────────────────────
# Tests JudgeVerdict
# ─────────────────────────────────────────────────────────────

class TestJudgeVerdict:
    def test_valid(self, valid_judge_verdict):
        assert valid_judge_verdict.relevance == "high"
        assert valid_judge_verdict.timing_recommendation == "next_iteration"

    def test_reject(self):
        v = JudgeVerdict(
            finding_id="z",
            relevance="reject",
            real_gain_summary="Aucun gain aligné avec les objectifs actifs.",
            timing_recommendation="reject",
            rationale="Le finding concerne une fonctionnalité hors scope.",
        )
        assert v.relevance == "reject"


# ─────────────────────────────────────────────────────────────
# Tests ValidatedSuggestion
# ─────────────────────────────────────────────────────────────

class TestValidatedSuggestion:
    def test_valid_minimal(self):
        s = ValidatedSuggestion(
            title="Remplacer BME280 par BME680",
            changes_summary="Mise à niveau du capteur pour ajouter mesure VOC.",
            components_affected=["BME280"],
            integration_notes="Driver disponible, compatible I2C.",
        )
        assert s.new_components == []
        assert s.open_questions == []

    def test_with_open_questions(self):
        s = ValidatedSuggestion(
            title="Ajouter module LoRa",
            changes_summary="Ajout d'un module LoRa SX1276.",
            components_affected=["ESP32"],
            integration_notes="Connexion SPI disponible.",
            open_questions=["Quelle antenne prévoir ?", "Budget alloué ?"],
        )
        assert len(s.open_questions) == 2


# ─────────────────────────────────────────────────────────────
# Tests ProjectModel — structure de base
# ─────────────────────────────────────────────────────────────

def _make_valid_project() -> ProjectModel:
    """Construit un ProjectModel minimal mais valide pour les tests."""
    return ProjectModel(
        nom_projet="Station Météo ESP32",
        identite=Identite(
            nom="Station Météo ESP32",
            phase="prototype",
            domaine="hybride",
            derniere_mise_a_jour=date(2026, 5, 4),
        ),
        description=(
            "Station météo autonome basée ESP32 mesurant température, humidité et pression. "
            "Transmission LoRaWAN, alimentation solaire."
        ),
        objectifs_actifs=["Tenir 6 mois d'autonomie sur batterie LiPo 2000 mAh + solaire 5W"],
        prochain_rendu=ProchainRendu(
            date_prevue=date(2026, 9, 15),
            nature="soutenance",
            contenu_attendu="Prototype fonctionnel avec 1 mois de données collectées.",
        ),
        composants=[
            Composant(
                nom="ESP32",
                role="Microcontrôleur principal",
                statut_decisionnel="validé",
                role_pipeline="critique",
            )
        ],
        stack_software=[
            StackItem(
                outil="ESP-IDF",
                role="Framework principal",
                version="5.x",
                statut_decisionnel="validé",
            )
        ],
        interactions=[
            Interaction(
                source="BME280",
                target="ESP32",
                nature="mesures T°/humidité/pression",
                format="I2C",
                volume="1 lecture/15 min",
            )
        ],
        contraintes=[
            SousSectionContraintes(
                titre="Énergie",
                criteres=[
                    CritereContrainte(nom="Autonomie cible", valeur="6 mois sans intervention"),
                ],
            )
        ],
        contraintes_non_negociables=["Pas de cloud commercial pour les données"],
        changements=[Changement(date_changement=date(2026, 5, 4), resume="Création initiale")],
    )


class TestProjectModel:
    def test_valid_project(self):
        p = _make_valid_project()
        assert p.nom_projet == "Station Météo ESP32"
        assert p.identite.phase == "prototype"
        assert len(p.composants) == 1

    def test_description_too_short(self):
        with pytest.raises(ValidationError):
            p = _make_valid_project()
            ProjectModel(**{**p.model_dump(), "description": "Court."})

    def test_invalid_phase(self):
        with pytest.raises(ValidationError):
            p = _make_valid_project()
            data = p.model_dump()
            data["identite"]["phase"] = "phase_inconnue"
            ProjectModel(**data)

    def test_objectifs_actifs_not_empty(self):
        with pytest.raises(ValidationError):
            p = _make_valid_project()
            ProjectModel(**{**p.model_dump(), "objectifs_actifs": []})
