"""
Test d'intégration du pipeline Éclaireur avec Reddit et le LLM mockés.

Vérifie l'enchaînement complet :
    queries → reddit.search (mock) → filtres → LLM (mock) → Finding(s) écrits sur disque.

Aucun appel réseau, aucun LLM réel — sûr en CI.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from src.agents import eclaireur
from src.graph.pipeline import build_graph, initial_state
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
from src.sources.reddit import RawFinding


@pytest.fixture
def project() -> ProjectModel:
    return ProjectModel(
        nom_projet="Test Project",
        identite=Identite(
            nom="Test Project",
            phase="prototype",
            domaine="hybride",
            derniere_mise_a_jour=date.today(),
        ),
        description=(
            "Projet test pour pipeline Éclaireur de bout en bout. "
            "Vérifie le bon enchaînement source → filtres → LLM."
        ),
        objectifs_actifs=["Validation pipeline Jalon 3"],
        prochain_rendu=ProchainRendu(date_prevue=None, nature="N/A", contenu_attendu="N/A"),
        composants=[
            Composant(
                nom="ESP32",
                role="MCU",
                statut_decisionnel="validé",
                role_pipeline="critique",
            ),
            Composant(
                nom="BME280",
                role="Capteur",
                statut_decisionnel="validé",
                role_pipeline="critique",
            ),
        ],
        stack_software=[
            StackItem(outil="ESP-IDF", role="FW", version="5.x", statut_decisionnel="validé")
        ],
        interactions=[Interaction(source="BME280", target="ESP32", nature="I2C")],
        contraintes=[SousSectionContraintes(titre="Énergie", criteres=[])],
        contraintes_non_negociables=["Open-source"],
        changements=[Changement(date_changement=date.today(), resume="Création de la fiche")],
    )


def _fake_raw(title: str, hint: str, score: int = 10) -> RawFinding:
    return RawFinding(
        title=title,
        body="lorem ipsum",
        url=f"https://reddit.com/r/embedded/comments/{hint}_{title[:5]}",
        score=score,
        created_utc=datetime.now(timezone.utc).timestamp() - 86400,
        subreddit="embedded",
        source_type="community",
        query=f"{hint} review",
        component_hint=hint,
    )


class _FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    """Stand-in pour ChatOllama. Renvoie toujours un JSON valide."""

    def invoke(self, prompt: str) -> _FakeLLMResponse:
        return _FakeLLMResponse(
            '{"angle": "perf", "description": "Le composant offre un gain mesurable."}'
        )


def test_graph_runs_end_to_end(project, tmp_path, monkeypatch):
    """Le graphe LangGraph doit s'exécuter sans erreur et produire des findings."""
    fake_raws = [
        _fake_raw("BME280 alternative review", "BME280", score=20),
        _fake_raw("ESP32 deep sleep tips", "ESP32", score=15),
        _fake_raw("Unrelated cooking post", "pasta", score=50),  # rejet alignement
        _fake_raw("BME280 short", "BME280", score=2),  # rejet score
    ]

    # Mock de la source Reddit : ignore les arguments, renvoie nos fakes.
    def fake_search(*args, **kwargs):
        return list(fake_raws)

    monkeypatch.setattr(eclaireur.reddit_source, "search", fake_search)
    monkeypatch.setattr(eclaireur, "get_llm", lambda role, config: _FakeLLM(), raising=False)
    # get_llm est importé localement dans _structure_one — on patch via l'import.
    import src.llm as llm_module
    monkeypatch.setattr(llm_module, "get_llm", lambda role, config: _FakeLLM())

    config = {
        "paths": {"state_dir": str(tmp_path / "state"), "cache_dir": str(tmp_path / "cache")},
        "sources": {"reddit": {"enabled": True, "filters": {"min_score": 5, "max_age_days": 365}}},
        "filters": {
            "enable_alignment_check": True,
            "enable_freshness_check": True,
            "enable_dedup": True,
            "enable_incremental_mode": True,
        },
    }

    run_dir = tmp_path / "run"
    graph = build_graph(project, config, run_dir=run_dir)
    final = graph.invoke(initial_state("# Test\n## Identité"))

    findings = final["findings"]
    # Au moins 1 finding structuré, et pas tous (les rejetés ne passent pas).
    assert len(findings) >= 1
    assert all(f.angle == "perf" for f in findings)
    assert all(f.id and len(f.id) == 12 for f in findings)

    # Artefacts écrits.
    findings_file = run_dir / "01_eclaireur_findings.json"
    sources_file = run_dir / "01_eclaireur_sources.json"
    assert findings_file.exists()
    assert sources_file.exists()

    sources_data = json.loads(sources_file.read_text(encoding="utf-8"))
    assert sources_data["filter_stats"]["initial"] > 0
    assert "filter_ratio" in sources_data["filter_stats"]


def test_incremental_skips_seen_on_second_run(project, tmp_path, monkeypatch):
    """Validation Jalon 3 : second run sans changement → 0 nouveau finding."""
    fake_raws = [_fake_raw("BME280 alternative review", "BME280", score=20)]

    monkeypatch.setattr(eclaireur.reddit_source, "search", lambda *a, **kw: list(fake_raws))
    import src.llm as llm_module
    monkeypatch.setattr(llm_module, "get_llm", lambda role, config: _FakeLLM())

    state_dir = tmp_path / "state"
    config = {
        "paths": {"state_dir": str(state_dir), "cache_dir": str(tmp_path / "cache")},
        "sources": {"reddit": {"enabled": True, "filters": {"min_score": 5, "max_age_days": 365}}},
        "filters": {
            "enable_alignment_check": True,
            "enable_freshness_check": True,
            "enable_dedup": True,
            "enable_incremental_mode": True,
        },
    }

    # Premier run : produit ≥ 1 finding et persiste les hashs.
    first = eclaireur.run(project, config)
    assert len(first) >= 1

    # Second run avec exactement les mêmes données : 0 nouveau finding.
    second = eclaireur.run(project, config)
    assert second == []
