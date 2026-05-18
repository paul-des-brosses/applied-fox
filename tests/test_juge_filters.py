"""
Tests pour les 3 filtres déterministes du Juge (Option C — v1.5).

Couvre :
- Filtre A : grounding strict (pré-LLM, reject si pas d'ancrage spécifique)
- Filtre B : migration validator (post-LLM, downgrade si X→Y et X hors projet)
- Filtre C : anti-plaque (post-LLM, downgrade si chiffre projet absent du finding)

Inclut un test de régression pour le bug regex `\b` après `%` découvert
en production v1.5 (cf. docs/evaluations/post_mvp_filtres_juge_2026-05-13.md).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agents.juge import (
    _check_anti_plaque,
    _check_grounding,
    _check_migration,
)
from src.models import (
    Changement,
    Composant,
    Finding,
    Identite,
    Interaction,
    ProchainRendu,
    ProjectModel,
    SousSectionContraintes,
    StackItem,
)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def project_greenhouse() -> ProjectModel:
    """Projet serre : ESP32-S3, SHT31-D, MH-Z19B, objectif -40% eau."""
    return ProjectModel(
        nom_projet="Serre Test",
        identite=Identite(
            nom="Serre Test", phase="prototype", domaine="hybride",
            derniere_mise_a_jour=date.today(),
        ),
        description=(
            "Système d'irrigation automatique pour serre 10 m². Capteurs "
            "T°/humidité/CO2 connectés à un ESP32 qui pilote pompe et "
            "ventilation. Objectif -40% consommation d'eau."
        ),
        objectifs_actifs=[
            "Réduire la consommation d'eau de 40% vs arrosage manuel",
            "Tenir 12 mois sans intervention sur capteurs",
        ],
        prochain_rendu=ProchainRendu(
            date_prevue=None, nature="N/A", contenu_attendu="N/A"
        ),
        composants=[
            Composant(nom="ESP32-S3 DevKitC", role="MCU",
                      statut_decisionnel="validé", role_pipeline="critique"),
            Composant(nom="SHT31-D", role="Capteur T/H",
                      statut_decisionnel="validé", role_pipeline="critique"),
            Composant(nom="MH-Z19B", role="Capteur CO2",
                      statut_decisionnel="validé", role_pipeline="critique"),
        ],
        stack_software=[
            StackItem(outil="ESP-IDF", role="Framework", version="5.x",
                      statut_decisionnel="validé"),
        ],
        interactions=[
            Interaction(source="SHT31-D", target="ESP32-S3 DevKitC", nature="I2C"),
        ],
        contraintes=[SousSectionContraintes(titre="X", criteres=[])],
        contraintes_non_negociables=["Open-source MIT"],
        changements=[Changement(date_changement=date.today(), resume="Création")],
    )


def _make_finding(title: str, description: str = "") -> Finding:
    return Finding(
        id="test123",
        title=title,
        component_concerned="test",
        angle="perf",
        description=description,
        source_url="https://example.com",
        source_type="community",
    )


# ─────────────────────────────────────────────────────────────
# Filtre A — Grounding strict
# ─────────────────────────────────────────────────────────────


class TestGrounding:
    def test_passes_with_specific_anchor_in_title(self, project_greenhouse):
        f = _make_finding("Adafruit SHT31D driver library")
        ok, reason = _check_grounding(f, project_greenhouse)
        assert ok, f"Should pass with SHT31D anchor: {reason}"

    def test_passes_with_anchor_in_description(self, project_greenhouse):
        f = _make_finding("Generic title", description="A capacitive moisture sensor for plants")
        ok, _ = _check_grounding(f, project_greenhouse)
        assert ok

    def test_rejects_generic_title_no_anchor(self, project_greenhouse):
        f = _make_finding("Tell your war stories")
        ok, reason = _check_grounding(f, project_greenhouse)
        assert not ok
        assert "Aucun anchor" in reason or "ancrage" in reason

    def test_rejects_finding_without_project_anchor(self, project_greenhouse):
        # VCNL4030 n'est pas dans le projet, le reste est trop générique
        f = _make_finding("VCNL4030 Proximity and Lux Sensor")
        ok, reason = _check_grounding(f, project_greenhouse)
        assert not ok
        # Soit "Aucun anchor" (zéro match), soit "spécifique" (que des matches faibles).
        # Les deux indiquent un rejet correct par filtre A.


# ─────────────────────────────────────────────────────────────
# Filtre B — Migration validator
# ─────────────────────────────────────────────────────────────


class TestMigration:
    def test_passes_when_no_migration_mentioned(self, project_greenhouse):
        verdict = {"real_gain_summary": "Useful library for the project."}
        ok, _ = _check_migration(verdict, project_greenhouse)
        assert ok

    def test_passes_migration_from_project_component(self, project_greenhouse):
        verdict = {"real_gain_summary": "Migration SHT31D vers SHT45 améliore la précision."}
        ok, _ = _check_migration(verdict, project_greenhouse)
        assert ok  # SHT31D est dans le projet

    def test_rejects_migration_from_unknown_component(self, project_greenhouse):
        # SX1276 n'est PAS dans le projet greenhouse
        verdict = {"real_gain_summary": "Migration SX1276 -> SX1262 améliore l'efficacité."}
        ok, reason = _check_migration(verdict, project_greenhouse)
        assert not ok
        assert "sx1276" in reason.lower()


# ─────────────────────────────────────────────────────────────
# Filtre C — Anti-plaque
# ─────────────────────────────────────────────────────────────


class TestAntiPlaque:
    def test_passes_when_no_project_number_in_summary(self, project_greenhouse):
        verdict = {"real_gain_summary": "Une lib utile sans chiffre."}
        finding = _make_finding("Test", description="Generic")
        ok, _ = _check_anti_plaque(finding, verdict, project_greenhouse)
        assert ok

    def test_passes_when_finding_contains_the_number(self, project_greenhouse):
        # Si le finding mentionne aussi le chiffre, pas de plaque
        verdict = {"real_gain_summary": "Réduction de 40% de la consommation"}
        finding = _make_finding(
            "Smart irrigation reducing water 40%",
            description="Tests show 40% reduction in water consumption."
        )
        ok, _ = _check_anti_plaque(finding, verdict, project_greenhouse)
        assert ok

    def test_rejects_when_project_number_only_in_summary(self, project_greenhouse):
        # Plaque : 40% dans summary, jamais dans finding
        verdict = {"real_gain_summary": "Contribue directement à la réduction de 40% de l'eau"}
        finding = _make_finding(
            "I spent 3 months on a DIY waterer",
            description="ESP32 plant waterer with portal dashboard."
        )
        ok, reason = _check_anti_plaque(finding, verdict, project_greenhouse)
        assert not ok
        assert "40%" in reason or "plaque" in reason.lower()

    def test_regression_percent_followed_by_space(self, project_greenhouse):
        """Régression du bug regex `\\b` après `%` — découvert en prod v1.5.

        Avant fix : le regex `(\\d+)\\s*(%)\\b` ne matchait pas "40% vs"
        car `\\b` ne matche pas entre deux non-word chars (% et espace).
        Du coup project_numbers ne contenait pas "40%" → plaque non détectée.

        Après fix : `(?=\\W|$)` matche correctement.
        """
        # L'objectif projet est "40% vs arrosage manuel" — % suivi d'espace
        verdict = {
            "real_gain_summary": "Réduction de 40% sur la consommation"
        }
        finding = _make_finding(
            "DIY watering project",
            description="A simple plant watering setup."  # pas de 40%
        )
        ok, reason = _check_anti_plaque(finding, verdict, project_greenhouse)
        # Doit détecter la plaque
        assert not ok, "Bug regression : filtre C devrait détecter '40%' plaqué"
        assert "40%" in reason
