"""
Tests déterministes du mode update et integrate (Jalon 2).

Couvrent :
- La conversion ProjectModel → dict (project_to_data).
- La préservation de l'historique des Changements.
- Le round-trip parse → modify → generate → re-parse.
- L'application d'un ValidatedSuggestion sur un dict (sans dialogue interactif).

Aucun LLM n'est sollicité — les tests sont 100% déterministes.

Lancement : pytest tests/test_update_integrate.py -v
"""

from datetime import date

import pytest

from src.interview.create import generate_md
from src.interview.integrate import _apply_suggestion_to_data
from src.interview.update import (
    existing_changements_to_list,
    project_to_data,
)
from src.models import ValidatedSuggestion
from src.validation.structural import parse_and_validate


# ─────────────────────────────────────────────────────────────
# Fixture : un .md valide servant de base aux tests
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def valid_project():
    """Charge le projet ESP32 démo et retourne le ProjectModel."""
    from pathlib import Path
    md = (
        Path(__file__).parent.parent / "projects" / "esp32_weather_station.md"
    ).read_text(encoding="utf-8")
    project, errors = parse_and_validate(md)
    assert project is not None, f"fixture invalide : {errors}"
    return project


# ─────────────────────────────────────────────────────────────
# project_to_data
# ─────────────────────────────────────────────────────────────


class TestProjectToData:
    def test_basic_fields(self, valid_project):
        data = project_to_data(valid_project)
        assert data["nom_projet"] == valid_project.nom_projet
        assert data["phase"] == valid_project.identite.phase
        assert data["domaine"] == valid_project.identite.domaine
        assert data["description"] == valid_project.description

    def test_composants_count(self, valid_project):
        data = project_to_data(valid_project)
        assert len(data["composants"]) == len(valid_project.composants)

    def test_composants_fields(self, valid_project):
        data = project_to_data(valid_project)
        for d_comp, p_comp in zip(data["composants"], valid_project.composants):
            assert d_comp["nom"] == p_comp.nom
            assert d_comp["role"] == p_comp.role
            assert d_comp["statut_decisionnel"] == p_comp.statut_decisionnel
            assert d_comp["role_pipeline"] == p_comp.role_pipeline

    def test_interactions_optional_fields(self, valid_project):
        data = project_to_data(valid_project)
        for d, p in zip(data["interactions"], valid_project.interactions):
            assert d["source"] == p.source
            assert d["target"] == p.target
            assert d["nature"] == p.nature

    def test_prochain_rendu_with_date(self, valid_project):
        data = project_to_data(valid_project)
        assert data["prochain_rendu"]["nature"] == valid_project.prochain_rendu.nature
        if valid_project.prochain_rendu.date_prevue:
            assert data["prochain_rendu"]["date"] == str(valid_project.prochain_rendu.date_prevue)


# ─────────────────────────────────────────────────────────────
# Round-trip : parse → data → generate_md → parse
# ─────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_round_trip_preserves_project(self, valid_project):
        """Sans modification, le round-trip doit produire un ProjectModel équivalent."""
        data = project_to_data(valid_project)
        historique = existing_changements_to_list(valid_project)
        md2 = generate_md(data, changements=historique)
        project2, errors = parse_and_validate(md2)
        assert project2 is not None, errors

        assert project2.nom_projet == valid_project.nom_projet
        assert project2.identite.phase == valid_project.identite.phase
        assert len(project2.composants) == len(valid_project.composants)
        assert len(project2.interactions) == len(valid_project.interactions)
        assert len(project2.changements) == len(valid_project.changements)

    def test_round_trip_preserves_changements_history(self, valid_project):
        """L'historique des Changements doit être préservé tel quel."""
        data = project_to_data(valid_project)
        historique = existing_changements_to_list(valid_project)
        md2 = generate_md(data, changements=historique)
        project2, _ = parse_and_validate(md2)

        for orig, new in zip(valid_project.changements, project2.changements):
            assert str(orig.date_changement) == str(new.date_changement)
            assert orig.resume == new.resume


# ─────────────────────────────────────────────────────────────
# Modification d'un composant (simulation update)
# ─────────────────────────────────────────────────────────────


class TestUpdateModifications:
    def test_add_composant(self, valid_project):
        data = project_to_data(valid_project)
        n_orig = len(data["composants"])
        data["composants"].append(
            {
                "nom": "Passerelle LoRaWAN Dragino LPS8",
                "role": "Réception trames LoRaWAN, transit vers le backend",
                "statut_decisionnel": "en évaluation",
                "role_pipeline": "critique",
            }
        )
        # Append au historique
        historique = existing_changements_to_list(valid_project)
        historique.append(
            {
                "date_changement": "2026-05-05",
                "resume": "Ajout composant : Passerelle LoRaWAN Dragino LPS8",
            }
        )
        md = generate_md(data, changements=historique)
        project, errors = parse_and_validate(md)
        assert project is not None, errors
        assert len(project.composants) == n_orig + 1
        assert any(c.nom == "Passerelle LoRaWAN Dragino LPS8" for c in project.composants)
        # L'historique a 2 entrées maintenant
        assert len(project.changements) == len(valid_project.changements) + 1

    def test_modify_phase(self, valid_project):
        data = project_to_data(valid_project)
        old_phase = data["phase"]
        data["phase"] = "pré-production"
        historique = existing_changements_to_list(valid_project)
        historique.append(
            {
                "date_changement": "2026-05-05",
                "resume": f"Phase : {old_phase} → pré-production",
            }
        )
        md = generate_md(data, changements=historique)
        project, errors = parse_and_validate(md)
        assert project is not None, errors
        assert project.identite.phase == "pré-production"

    def test_remove_objectif(self, valid_project):
        data = project_to_data(valid_project)
        n_orig = len(data["objectifs"])
        if n_orig <= 1:
            pytest.skip("Test nécessite >= 2 objectifs dans la fixture")
        removed = data["objectifs"].pop()
        historique = existing_changements_to_list(valid_project)
        historique.append(
            {"date_changement": "2026-05-05", "resume": f"Suppression objectif : {removed[:60]}"}
        )
        md = generate_md(data, changements=historique)
        project, errors = parse_and_validate(md)
        assert project is not None, errors
        assert len(project.objectifs_actifs) == n_orig - 1
        assert removed not in project.objectifs_actifs

    def test_modify_critere(self, valid_project):
        data = project_to_data(valid_project)
        # Modifier le premier critère de la première sous-section
        if not data["contraintes"]:
            pytest.skip("Test nécessite au moins une sous-section de contraintes")
        sec = data["contraintes"][0]
        if not sec["criteres"]:
            pytest.skip("Test nécessite au moins un critère")
        old_val = sec["criteres"][0]["valeur"]
        sec["criteres"][0]["valeur"] = "nouvelle valeur 42 unités"
        historique = existing_changements_to_list(valid_project)
        historique.append(
            {
                "date_changement": "2026-05-05",
                "resume": f"Modification critère : {sec['titre']} / {sec['criteres'][0]['nom']}",
            }
        )
        md = generate_md(data, changements=historique)
        project, errors = parse_and_validate(md)
        assert project is not None, errors
        assert project.contraintes[0].criteres[0].valeur == "nouvelle valeur 42 unités"
        assert project.contraintes[0].criteres[0].valeur != old_val


# ─────────────────────────────────────────────────────────────
# Application d'un ValidatedSuggestion (mode integrate)
# ─────────────────────────────────────────────────────────────


class TestIntegrateApply:
    def test_apply_adds_new_component(self, valid_project):
        data = project_to_data(valid_project)
        n_orig = len(data["composants"])

        suggestion = ValidatedSuggestion(
            title="Ajout passerelle LoRaWAN",
            changes_summary="Ajout d'une passerelle Dragino LPS8 pour la réception des trames.",
            components_affected=[],
            new_components=[
                {
                    "nom": "Dragino LPS8",
                    "role": "Passerelle LoRaWAN locale",
                    "statut_decisionnel": "en évaluation",
                    "role_pipeline": "critique",
                }
            ],
            integration_notes="À installer en hauteur pour optimiser portée.",
        )

        changes = _apply_suggestion_to_data(data, suggestion, answers={})

        assert len(data["composants"]) == n_orig + 1
        assert any(c["nom"] == "Dragino LPS8" for c in data["composants"])
        assert any("Dragino LPS8" in c for c in changes)

    def test_apply_marks_affected_as_evaluation(self, valid_project):
        data = project_to_data(valid_project)
        # Prend le nom du premier composant validé
        first_validated = next(
            (c for c in data["composants"] if c["statut_decisionnel"] == "validé"), None
        )
        if first_validated is None:
            pytest.skip("Test nécessite au moins un composant 'validé'")
        nom = first_validated["nom"]

        suggestion = ValidatedSuggestion(
            title="Substitution potentielle",
            changes_summary=f"Le composant {nom} pourrait être remplacé.",
            components_affected=[nom],
            integration_notes="Statut basculé pour évaluation.",
        )

        _apply_suggestion_to_data(data, suggestion, answers={})

        affected = next(c for c in data["composants"] if c["nom"] == nom)
        assert affected["statut_decisionnel"] == "en évaluation"

    def test_apply_creates_impacts_section(self, valid_project):
        data = project_to_data(valid_project)
        n_sections_orig = len(data["contraintes"])

        suggestion = ValidatedSuggestion(
            title="Impact contrainte énergétique",
            changes_summary="La nouvelle alimentation augmente la consommation moyenne.",
            components_affected=[],
            integration_notes="Note d'intégration",
            constraints_impact={"Conso moyenne": "passe de 5 mA à 7 mA"},
        )

        _apply_suggestion_to_data(data, suggestion, answers={})

        # Une nouvelle sous-section "Impacts veille" a été créée
        impacts = next(
            (s for s in data["contraintes"] if s["titre"] == "Impacts veille"), None
        )
        assert impacts is not None
        assert len(impacts["criteres"]) >= 1
        assert any("Conso moyenne" in c["nom"] for c in impacts["criteres"])

    def test_apply_full_round_trip(self, valid_project):
        """Application + génération + parsing = .md valide."""
        data = project_to_data(valid_project)
        historique = existing_changements_to_list(valid_project)

        suggestion = ValidatedSuggestion(
            title="Test intégration full round-trip",
            changes_summary="Ajout d'un composant et impact contrainte.",
            components_affected=[],
            new_components=[
                {
                    "nom": "Module Test 42",
                    "role": "Test integration",
                    "statut_decisionnel": "en évaluation",
                    "role_pipeline": "support",
                }
            ],
            integration_notes="Test",
            constraints_impact={"Critère test": "valeur test 5V"},
        )

        changes = _apply_suggestion_to_data(data, suggestion, answers={})
        historique.append(
            {
                "date_changement": "2026-05-05",
                "resume": f"Intégration suggestion : {' ; '.join(changes[:3])}",
            }
        )

        md = generate_md(data, changements=historique)
        project, errors = parse_and_validate(md)
        assert project is not None, errors
        assert any(c.nom == "Module Test 42" for c in project.composants)
        assert any(s.titre == "Impacts veille" for s in project.contraintes)
