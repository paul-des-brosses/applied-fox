"""
Tests unitaires pour `src/agents/_anchoring.py`.

Couvre :
- Tokenisation (camelCase, accents)
- Construction des strong_anchors d'un projet
- Extraction de composants (Niveau 2)
- Classification in_project vs new_mentioned
- Détection d'anchor spécifique vs générique
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agents._anchoring import (
    GENERIC_DENY_AS_ANCHOR,
    camel_split,
    classify_components,
    extract_mentioned_components,
    is_specific_anchor,
    normalize_component_name,
    project_strong_anchors,
    strip_accents,
    tokenize,
)
from src.models import (
    Changement,
    Composant,
    Identite,
    Interaction,
    ProchainRendu,
    ProjectModel,
    SousSectionContraintes,
    StackItem,
)


# ─────────────────────────────────────────────────────────────
# Tokenisation
# ─────────────────────────────────────────────────────────────


class TestTokenize:
    def test_basic(self):
        assert tokenize("Hello World") == {"hello", "world"}

    def test_min_length(self):
        # Filtre len < 3
        assert tokenize("a bb ccc dddd") == {"ccc", "dddd"}

    def test_strips_accents(self):
        # "précision" → "precision"
        assert "precision" in tokenize("précision haute")

    def test_camel_case(self):
        # "SoilMoisureLogger" → {"soil", "moisure", "logger"}
        result = tokenize("SoilMoisureLogger")
        assert "soil" in result
        assert "moisure" in result
        assert "logger" in result

    def test_empty(self):
        assert tokenize("") == set()
        assert tokenize(None) == set()  # type: ignore


class TestCamelSplit:
    def test_splits_camel(self):
        assert camel_split("SoilMoisureLogger") == "Soil Moisure Logger"

    def test_preserves_lowercase(self):
        assert camel_split("foo bar") == "foo bar"

    def test_preserves_uppercase_sequence(self):
        # "SHT31D" : pas de minuscule→majuscule, donc rien à splitter
        assert camel_split("SHT31D") == "SHT31D"


class TestStripAccents:
    def test_french_accents(self):
        assert strip_accents("précision") == "precision"
        assert strip_accents("humidité") == "humidite"

    def test_preserves_ascii(self):
        assert strip_accents("hello") == "hello"


class TestNormalizeComponent:
    def test_strips_separators(self):
        assert normalize_component_name("ESP32-S3") == "esp32s3"
        assert normalize_component_name("SHT31-D") == "sht31d"
        assert normalize_component_name("MH-Z19B") == "mhz19b"

    def test_strips_accents_too(self):
        assert normalize_component_name("Périphérique-1") == "peripherique1"


# ─────────────────────────────────────────────────────────────
# Anchor spécifique vs générique
# ─────────────────────────────────────────────────────────────


class TestIsSpecificAnchor:
    def test_with_digit(self):
        assert is_specific_anchor("sht31")
        assert is_specific_anchor("bme280")
        assert is_specific_anchor("rak3172")

    def test_long_enough(self):
        assert is_specific_anchor("capacitive")  # 10 chars
        assert is_specific_anchor("battery")  # 7 chars

    def test_too_short_no_digit(self):
        # "sensor" : 6 chars, no digit → generic
        assert not is_specific_anchor("sensor")
        assert not is_specific_anchor("module")
        assert not is_specific_anchor("system")


# ─────────────────────────────────────────────────────────────
# Extraction de composants (Niveau 2)
# ─────────────────────────────────────────────────────────────


class TestExtractMentionedComponents:
    def test_basic_references(self):
        text = "Replacing the BME280 with a SHT31-D for better accuracy"
        result = extract_mentioned_components(text)
        assert "BME280" in result
        assert "SHT31" in result or "SHT31-D" in result  # selon regex

    def test_no_components(self):
        assert extract_mentioned_components("Just a generic post") == []
        assert extract_mentioned_components("") == []

    def test_dedup(self):
        text = "BME280 review. BME280 alternatives. BME280 issues."
        result = extract_mentioned_components(text)
        assert result.count("BME280") == 1


# ─────────────────────────────────────────────────────────────
# Classification composants
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def project_bms() -> ProjectModel:
    return ProjectModel(
        nom_projet="BMS Test",
        identite=Identite(
            nom="BMS Test", phase="prototype", domaine="hardware",
            derniere_mise_a_jour=date.today(),
        ),
        description=(
            "Système de gestion de batterie pour vélo électrique 48V avec "
            "cellules INR21700 Samsung. Surveillance individuelle, équilibrage "
            "passif, protection surintensité."
        ),
        objectifs_actifs=["Conforme ISO 13849-1 cat. B"],
        prochain_rendu=ProchainRendu(
            date_prevue=None, nature="N/A", contenu_attendu="N/A"
        ),
        composants=[
            Composant(nom="STM32F103C8T6", role="MCU",
                      statut_decisionnel="validé", role_pipeline="critique"),
            Composant(nom="BQ76940", role="AFE Battery",
                      statut_decisionnel="validé", role_pipeline="critique"),
            Composant(nom="INA219", role="Mesure courant",
                      statut_decisionnel="validé", role_pipeline="critique"),
        ],
        stack_software=[
            StackItem(outil="FreeRTOS", role="OS", version="10",
                      statut_decisionnel="validé"),
        ],
        interactions=[
            Interaction(source="BQ76940", target="STM32F103C8T6", nature="I2C"),
        ],
        contraintes=[SousSectionContraintes(titre="X", criteres=[])],
        contraintes_non_negociables=["Open-source"],
        changements=[Changement(date_changement=date.today(), resume="Création")],
    )


class TestClassifyComponents:
    def test_in_project_match(self, project_bms):
        text = "BQ76940 driver issues with INA219 measurements"
        in_p, new = classify_components(text, project_bms)
        assert "BQ76940" in in_p
        assert "INA219" in in_p
        assert new == []

    def test_new_component_flagged(self, project_bms):
        text = "Using BQ25616 charger to replace traditional supply"
        in_p, new = classify_components(text, project_bms)
        assert "BQ25616" in new
        assert in_p == []

    def test_mixed(self, project_bms):
        text = "INA219 paired with BQ25616 instead of MAX17048"
        in_p, new = classify_components(text, project_bms)
        assert "INA219" in in_p
        assert "BQ25616" in new
        assert "MAX17048" in new

    def test_no_components(self, project_bms):
        in_p, new = classify_components("just text", project_bms)
        assert in_p == []
        assert new == []


# ─────────────────────────────────────────────────────────────
# Strong anchors d'un projet
# ─────────────────────────────────────────────────────────────


class TestProjectStrongAnchors:
    def test_includes_components(self, project_bms):
        anchors = project_strong_anchors(project_bms)
        assert "stm32f103c8t6" in anchors
        assert "bq76940" in anchors
        assert "ina219" in anchors

    def test_excludes_generic(self, project_bms):
        anchors = project_strong_anchors(project_bms)
        # "esp32" est dans deny — ne doit jamais apparaître
        assert "esp32" not in anchors
        assert "stm32" not in anchors  # générique aussi

    def test_includes_objective_tokens(self, project_bms):
        anchors = project_strong_anchors(project_bms)
        # "iso", "13849" sont issus de l'objectif
        assert "13849" in anchors

    def test_fr_en_expansion(self, project_bms):
        # La description contient "cellules" → "cells" doit être ajouté
        anchors = project_strong_anchors(project_bms)
        assert "cellules" in anchors
        assert "cells" in anchors  # via FR_EN_PAIRS
