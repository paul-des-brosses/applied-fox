"""
Tests des filtres déterministes de l'Éclaireur.

Ces tests sont purement déterministes — aucun appel LLM, aucun appel réseau.
Ils couvrent :
    - le hash stable (réutilisé pour finding.id et le mode incrémental) ;
    - les 5 filtres en isolation (alignment, freshness, score, dedup, incremental) ;
    - leur composition dans apply_deterministic_filter ;
    - le persistence load_seen / save_seen.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.agents.eclaireur import (
    apply_deterministic_filter,
    filter_alignment,
    filter_dedup,
    filter_freshness,
    filter_incremental,
    filter_score,
    finding_hash,
    load_seen,
    save_seen,
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
from src.sources.reddit import RawFinding


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _raw(
    title: str = "BME280 alternative",
    body: str = "",
    url: str = "https://reddit.com/r/embedded/comments/x1",
    score: int = 10,
    age_days: int = 30,
    subreddit: str = "embedded",
    component_hint: str = "BME280",
) -> RawFinding:
    return RawFinding(
        title=title,
        body=body,
        url=url,
        score=score,
        created_utc=_now() - age_days * 86400,
        subreddit=subreddit,
        source_type="community",
        query=f"{component_hint} alternative",
        component_hint=component_hint,
    )


@pytest.fixture
def project() -> ProjectModel:
    return ProjectModel(
        nom_projet="Station Test",
        identite=Identite(
            nom="Station Test",
            phase="prototype",
            domaine="hybride",
            derniere_mise_a_jour=date.today(),
        ),
        description=(
            "Projet test pour valider l'Éclaireur. Mesure de température, "
            "humidité et pression avec un microcontrôleur basse consommation."
        ),
        objectifs_actifs=["Tenir 6 mois d'autonomie"],
        prochain_rendu=ProchainRendu(
            date_prevue=None, nature="N/A", contenu_attendu="N/A"
        ),
        composants=[
            Composant(
                nom="ESP32-WROOM-32E",
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
            StackItem(
                outil="ESP-IDF", role="Framework", version="5.x", statut_decisionnel="validé"
            )
        ],
        interactions=[
            Interaction(source="BME280", target="ESP32-WROOM-32E", nature="I2C")
        ],
        contraintes=[
            SousSectionContraintes(titre="Énergie", criteres=[])
        ],
        contraintes_non_negociables=["Open-source uniquement"],
        changements=[Changement(date_changement=date.today(), resume="Création de la fiche")],
    )


# ─────────────────────────────────────────────────────────────
# Hash
# ─────────────────────────────────────────────────────────────


class TestFindingHash:
    def test_hash_is_12_hex(self):
        h = finding_hash("BME280", "Some title", "https://x.com/a")
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_stable(self):
        h1 = finding_hash("BME280", "Title", "url")
        h2 = finding_hash("BME280", "Title", "url")
        assert h1 == h2

    def test_hash_changes_with_input(self):
        h1 = finding_hash("BME280", "Title", "url")
        h2 = finding_hash("BME280", "Title", "url2")
        h3 = finding_hash("BME680", "Title", "url")
        assert h1 != h2
        assert h1 != h3


# ─────────────────────────────────────────────────────────────
# Filtres unitaires
# ─────────────────────────────────────────────────────────────


class TestFilterScore:
    def test_keeps_above_threshold(self):
        rf = [_raw(score=10), _raw(score=2), _raw(score=5)]
        kept, rejected = filter_score(rf, min_score=5)
        assert len(kept) == 2
        assert rejected == 1

    def test_all_rejected(self):
        rf = [_raw(score=1), _raw(score=2)]
        kept, rejected = filter_score(rf, min_score=10)
        assert kept == []
        assert rejected == 2


class TestFilterFreshness:
    def test_keeps_recent(self):
        rf = [_raw(age_days=10), _raw(age_days=400)]
        kept, rejected = filter_freshness(rf, max_age_days=365)
        assert len(kept) == 1
        assert rejected == 1


class TestFilterAlignment:
    def test_keeps_matching_component(self, project):
        rf = [_raw(title="BME280 review", component_hint="BME280")]
        kept, rejected = filter_alignment(rf, project)
        assert len(kept) == 1
        assert rejected == 0

    def test_rejects_unrelated(self, project):
        rf = [_raw(title="Cooking pasta tips", component_hint="pasta")]
        kept, rejected = filter_alignment(rf, project)
        assert kept == []
        assert rejected == 1

    def test_matches_via_title_alone(self, project):
        # Le component_hint ne match pas mais le titre cite un anchor SPÉCIFIQUE
        # du projet (BME280). "ESP32" seul ne marcherait pas — c'est dans la
        # deny list (trop générique en embarqué).
        rf = [_raw(title="BME280 deep sleep weirdness", component_hint="random")]
        kept, _ = filter_alignment(rf, project)
        assert len(kept) == 1


class TestFilterDedup:
    def test_removes_duplicates(self):
        # Même hint + titre + url → même hash → dédup.
        rf = [
            _raw(title="X", url="u1", component_hint="C"),
            _raw(title="X", url="u1", component_hint="C"),
            _raw(title="X", url="u2", component_hint="C"),
        ]
        kept, rejected = filter_dedup(rf)
        assert len(kept) == 2
        assert rejected == 1


class TestFilterIncremental:
    def test_rejects_seen(self):
        rf = _raw(title="X", url="u1", component_hint="C")
        h = finding_hash("C", "X", "u1")
        kept, rejected = filter_incremental([rf], {h})
        assert kept == []
        assert rejected == 1

    def test_keeps_unseen(self):
        rf = _raw()
        kept, rejected = filter_incremental([rf], set())
        assert len(kept) == 1
        assert rejected == 0


# ─────────────────────────────────────────────────────────────
# Pipeline déterministe complet
# ─────────────────────────────────────────────────────────────


class TestApplyDeterministicFilter:
    def test_meets_50pct_rejection(self, project):
        """Validation Jalon 3 : > 50% de rejet sur findings bruts."""
        rf = [
            _raw(title="BME280 review", score=10),                # garde
            _raw(title="ESP32 deep sleep", score=8),              # garde
            _raw(title="Cooking pasta", score=20, component_hint="pasta"),  # rejet alignement
            _raw(title="BME280 review", score=2),                 # rejet score
            _raw(title="ESP32 boot", score=10, age_days=400),     # rejet fraîcheur
            _raw(title="BME280 review", score=10, url="u-dup"),
            _raw(title="BME280 review", score=10, url="u-dup"),   # rejet dedup
        ]
        config = {
            "filters": {
                "enable_alignment_check": True,
                "enable_freshness_check": True,
                "enable_dedup": True,
                "enable_incremental_mode": True,
            },
            "sources": {"reddit": {"filters": {"min_score": 5, "max_age_days": 365}}},
        }
        kept, stats = apply_deterministic_filter(rf, project, config, set())
        assert stats["initial"] == 7
        assert stats["filter_ratio"] >= 0.5
        # Les rejets attendus.
        assert stats["rejected_score"] == 1
        assert stats["rejected_freshness"] == 1
        assert stats["rejected_alignment"] == 1
        assert stats["rejected_dedup"] == 1
        # Au moins 1 finding survit.
        assert len(kept) >= 1

    def test_incremental_returns_zero_on_seen(self, project):
        rf = [_raw(title="BME280 review", score=10)]
        config = {"filters": {}, "sources": {"reddit": {"filters": {}}}}
        h = finding_hash("BME280", "BME280 review", rf[0].url)
        kept, stats = apply_deterministic_filter(rf, project, config, {h})
        assert kept == []
        assert stats["rejected_incremental"] == 1


# ─────────────────────────────────────────────────────────────
# Persistance du state incrémental
# ─────────────────────────────────────────────────────────────


class TestStatePersistence:
    def test_round_trip(self, tmp_path):
        save_seen("MonProjet", tmp_path, {"abc123", "def456"})
        loaded = load_seen("MonProjet", tmp_path)
        assert loaded == {"abc123", "def456"}

    def test_load_missing_returns_empty(self, tmp_path):
        assert load_seen("Inexistant", tmp_path) == set()

    def test_slug_normalization(self, tmp_path):
        save_seen("Mon Projet ! éé", tmp_path, {"x"})
        # On retrouve via le même nom non normalisé.
        assert load_seen("Mon Projet ! éé", tmp_path) == {"x"}
