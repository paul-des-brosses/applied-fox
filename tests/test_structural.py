"""
Tests du parseur Markdown — src/validation/structural.py.

Tous les tests sont déterministes (aucun LLM requis).
Lancement : pytest tests/test_structural.py -v
"""

import textwrap

import pytest

from src.validation.structural import parse_and_validate

# ─────────────────────────────────────────────────────────────
# Fixture : .md de référence complet et valide
# ─────────────────────────────────────────────────────────────

_VALID_MD = textwrap.dedent("""\
    # Station Météo ESP32

    ## Identité
    - Nom : Station Météo ESP32
    - Phase : prototype
    - Domaine : hybride
    - Dernière mise à jour : 2026-05-04

    ## Description
    Station météo autonome basée ESP32 mesurant température, humidité et pression. Transmission LoRaWAN, alimentation solaire. Déploiement outdoor 6 mois sans intervention.

    ## Objectifs actifs
    - Tenir 6 mois d'autonomie sur batterie LiPo 2000 mAh + solaire 5W

    ## Prochain rendu
    - Date : 2026-09-15
    - Nature : soutenance
    - Contenu attendu : prototype fonctionnel avec 1 mois de données collectées

    ## Composants
    | Composant | Rôle | Statut décisionnel | Rôle pipeline |
    |-----------|------|--------------------|---------------|
    | ESP32 | Microcontrôleur principal | validé | critique |
    | BME280 | Capteur T°/humidité/pression | validé | critique |

    ## Stack software
    | Outil | Rôle | Version | Statut décisionnel |
    |-------|------|---------|--------------------|
    | ESP-IDF | Framework principal | 5.x | validé |

    ## Interactions
    - BME280 → ESP32 : mesures T°/humidité/pression | I2C | 1 lecture/15 min

    ## Contraintes

    ### Énergie
    - Autonomie cible : 6 mois sans intervention

    ## Contraintes non négociables
    - Pas de cloud commercial pour les données

    ## Changements
    - 2026-05-04 : Création initiale de la fiche projet
""")


def _md_with(**overrides: str) -> str:
    """Remplace une section dans le .md de référence."""
    md = _VALID_MD
    for section, content in overrides.items():
        md = md.replace(section, content)
    return md


# ─────────────────────────────────────────────────────────────
# Cas passants
# ─────────────────────────────────────────────────────────────

class TestValidMd:
    def test_valid_md_produces_project(self):
        project, errors = parse_and_validate(_VALID_MD)
        assert project is not None
        assert errors == []

    def test_project_name_correct(self):
        project, _ = parse_and_validate(_VALID_MD)
        assert project.nom_projet == "Station Météo ESP32"

    def test_phase_parsed(self):
        project, _ = parse_and_validate(_VALID_MD)
        assert project.identite.phase == "prototype"

    def test_composants_count(self):
        project, _ = parse_and_validate(_VALID_MD)
        assert len(project.composants) == 2

    def test_critical_component_flag(self):
        project, _ = parse_and_validate(_VALID_MD)
        critiques = [c for c in project.composants if c.role_pipeline == "critique"]
        assert len(critiques) == 2

    def test_date_prevue_parsed(self):
        from datetime import date
        project, _ = parse_and_validate(_VALID_MD)
        assert project.prochain_rendu.date_prevue == date(2026, 9, 15)

    def test_objectifs_not_empty(self):
        project, _ = parse_and_validate(_VALID_MD)
        assert len(project.objectifs_actifs) >= 1

    def test_interactions_parsed(self):
        project, _ = parse_and_validate(_VALID_MD)
        assert len(project.interactions) == 1
        i = project.interactions[0]
        assert i.source == "BME280"
        assert i.target == "ESP32"

    def test_changements_parsed(self):
        project, _ = parse_and_validate(_VALID_MD)
        assert len(project.changements) == 1

    def test_aucun_changement_placeholder(self):
        """Le placeholder 'Aucun changement' ne doit pas bloquer la validation."""
        md = _VALID_MD.replace(
            "- 2026-05-04 : Création initiale de la fiche projet",
            "Aucun changement",
        )
        project, errors = parse_and_validate(md)
        assert project is not None, f"Errors: {errors}"

    def test_prochain_rendu_na(self):
        """Une date N/A dans prochain rendu est acceptée."""
        md = (
            _VALID_MD
            .replace("- Date : 2026-09-15", "- Date : N/A")
            .replace("- Nature : soutenance", "- Nature : N/A")
        )
        project, errors = parse_and_validate(md)
        assert project is not None, f"Errors: {errors}"
        assert project.prochain_rendu.date_prevue is None

    def test_esp32_demo_file(self):
        """Le fichier de démo ESP32 passe la couche 1 sans erreur."""
        from pathlib import Path
        demo_path = (
            Path(__file__).parent.parent / "projects" / "esp32_weather_station.md"
        )
        if not demo_path.exists():
            pytest.skip("Fichier de démo absent")
        md = demo_path.read_text(encoding="utf-8")
        project, errors = parse_and_validate(md)
        assert project is not None, f"Errors: {errors}"


# ─────────────────────────────────────────────────────────────
# Sections manquantes
# ─────────────────────────────────────────────────────────────

class TestMissingSections:
    def test_missing_description(self):
        md = "\n".join(
            line for line in _VALID_MD.splitlines()
            if "## Description" not in line and "Station météo" not in line
        )
        project, errors = parse_and_validate(md)
        assert project is None
        assert any("description" in e.lower() for e in errors)

    def test_missing_composants(self):
        lines = _VALID_MD.splitlines()
        # Remove from ## Composants to ## Stack software
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Composants")
        end = next(i for i, l in enumerate(lines) if l.strip() == "## Stack software")
        md = "\n".join(lines[:start] + lines[end:])
        project, errors = parse_and_validate(md)
        assert project is None
        assert any("composant" in e.lower() for e in errors)

    def test_missing_interactions(self):
        lines = _VALID_MD.splitlines()
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Interactions")
        end = next(i for i, l in enumerate(lines) if l.strip() == "## Contraintes")
        md = "\n".join(lines[:start] + lines[end:])
        project, errors = parse_and_validate(md)
        assert project is None


# ─────────────────────────────────────────────────────────────
# Valeurs énumérées invalides
# ─────────────────────────────────────────────────────────────

class TestInvalidEnumValues:
    def test_invalid_phase(self):
        md = _VALID_MD.replace("- Phase : prototype", "- Phase : beta")
        project, errors = parse_and_validate(md)
        assert project is None
        assert any("phase" in e.lower() for e in errors)

    def test_invalid_domaine(self):
        md = _VALID_MD.replace("- Domaine : hybride", "- Domaine : inconnu")
        project, errors = parse_and_validate(md)
        assert project is None
        assert any("domaine" in e.lower() for e in errors)

    def test_invalid_statut_decisionnel_composant(self):
        md = _VALID_MD.replace(
            "| ESP32 | Microcontrôleur principal | validé | critique |",
            "| ESP32 | Microcontrôleur principal | approuvé | critique |",
        )
        project, errors = parse_and_validate(md)
        assert project is None

    def test_invalid_role_pipeline(self):
        md = _VALID_MD.replace(
            "| ESP32 | Microcontrôleur principal | validé | critique |",
            "| ESP32 | Microcontrôleur principal | validé | principal |",
        )
        project, errors = parse_and_validate(md)
        assert project is None

    def test_invalid_nature_rendu(self):
        md = _VALID_MD.replace("- Nature : soutenance", "- Nature : présentation")
        project, errors = parse_and_validate(md)
        assert project is None


# ─────────────────────────────────────────────────────────────
# Validation description
# ─────────────────────────────────────────────────────────────

class TestDescriptionValidation:
    def test_description_too_short(self):
        lines = _VALID_MD.splitlines()
        idx = next(
            i for i, l in enumerate(lines)
            if "Station météo autonome" in l
        )
        lines[idx] = "Court."
        project, errors = parse_and_validate("\n".join(lines))
        assert project is None
        assert any("description" in e.lower() for e in errors)


# ─────────────────────────────────────────────────────────────
# Validation sémantique — couche 3
# ─────────────────────────────────────────────────────────────

class TestSemanticValidation:
    def test_interaction_unknown_source(self):
        """Une interaction avec une source inconnue doit générer une erreur."""
        md = _VALID_MD.replace(
            "- BME280 → ESP32 : mesures T°/humidité/pression | I2C | 1 lecture/15 min",
            "- CapteurInconnu → ESP32 : données | I2C | 1 lecture/15 min",
        )
        project, errors = parse_and_validate(md)
        # La couche 3 produit des warnings mais ne bloque pas nécessairement
        # Selon l'implémentation : vérifier que l'erreur est signalée
        if project is not None:
            # Si non bloquant, l'erreur doit quand même être listée
            assert any("capteurinconnu" in e.lower() or "inconnu" in e.lower() for e in errors)
