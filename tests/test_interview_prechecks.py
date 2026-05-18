"""
Tests des pré-checks déterministes du module Interview.

Ces tests vérifient le filet de sécurité regex qui rejette les réponses
manifestement insuffisantes AVANT tout appel LLM. Ils sont 100% déterministes
et tournent sans Ollama.

Lancement : pytest tests/test_interview_prechecks.py -v
"""

import pytest

from src.interview.create import (
    _deterministic_accept,
    _has_concrete_indicator,
    _is_pure_tbd,
    _is_trivial,
    _is_valid_placeholder,
    _word_count,
)


# ─────────────────────────────────────────────────────────────
# _has_concrete_indicator
# ─────────────────────────────────────────────────────────────

class TestConcreteIndicator:
    @pytest.mark.parametrize("text", [
        "5 mA en moyenne",
        "6 mois d'autonomie",
        "< 80€",
        "±0.5°C",
        "5 km",
        "50 µA",
        "2000 mAh",
        "ESP32 et BME280",
        "transmission LoRaWAN via I2C",
        "boîtier IP65",
        "license MIT",
        "module GP-20U7",
        "antenne 868 MHz",
        "1 lecture/15 min",
    ])
    def test_concrete_detected(self, text):
        assert _has_concrete_indicator(text), f"devrait être détecté : {text}"

    @pytest.mark.parametrize("text", [
        "améliorer les performances",
        "rendre le système plus robuste",
        "le cerveau du système",
        "système fiable et performant",
        "à voir plus tard",
        "simple et efficace",
    ])
    def test_no_concrete_detected(self, text):
        assert not _has_concrete_indicator(text), f"ne devrait pas être détecté : {text}"


# ─────────────────────────────────────────────────────────────
# _is_pure_tbd
# ─────────────────────────────────────────────────────────────

class TestPureTbd:
    @pytest.mark.parametrize("text", [
        "TBD",
        "tbd",
        "TBD ",
        "  tbd  ",
        "à voir",
        "à  voir",
        "a voir",
        "à définir",
        "a definir",
        "je sais pas",
        "je ne sais pas",
        "sais pas",
        "?",
        "???",
        "inconnu",
        "inconnue",
    ])
    def test_pure_tbd_detected(self, text):
        assert _is_pure_tbd(text), f"devrait être détecté comme TBD seul : '{text}'"

    @pytest.mark.parametrize("text", [
        "TBD : utile en mode debug",
        "TBD: à arbitrer selon impact conso",
        "à voir : selon disponibilité du fournisseur",
        "5 mA",
        "non",
    ])
    def test_not_pure_tbd(self, text):
        assert not _is_pure_tbd(text), f"ne devrait pas être détecté comme TBD seul : '{text}'"


# ─────────────────────────────────────────────────────────────
# _is_valid_placeholder
# ─────────────────────────────────────────────────────────────

class TestValidPlaceholder:
    @pytest.mark.parametrize("text", [
        "N/A",
        "n/a",
        "NA",
        "na",
        "N/A.",
        "TBD : utile en mode debug",
        "TBD: arbitrage selon impact consommation",
        "à voir : selon disponibilité fournisseur",
        "a voir : selon stock 2026",
    ])
    def test_valid_placeholder(self, text):
        assert _is_valid_placeholder(text), f"devrait être un placeholder valide : '{text}'"

    @pytest.mark.parametrize("text", [
        "TBD",
        "à voir",
        "TBD :",
        "TBD : x",  # raison trop courte (< 4 chars)
        "5 mA",
        "Aucune",
    ])
    def test_invalid_placeholder(self, text):
        assert not _is_valid_placeholder(text), f"ne devrait PAS être placeholder valide : '{text}'"


# ─────────────────────────────────────────────────────────────
# _is_trivial
# ─────────────────────────────────────────────────────────────

class TestTrivial:
    @pytest.mark.parametrize("text", [
        "rien",
        "Rien",
        "aucune idée",
        "aucune idee",
        "bof",
        "ouais",
        "oui",
        "non",
        "...",
        "---",
        "peut-être",
        "peut etre",
    ])
    def test_trivial_detected(self, text):
        assert _is_trivial(text), f"devrait être détecté comme trivial : '{text}'"

    @pytest.mark.parametrize("text", [
        "5 mA en moyenne",
        "ESP32",
        "Aucune contrainte non négociable",  # phrase complète, pas trivial
    ])
    def test_not_trivial(self, text):
        assert not _is_trivial(text), f"ne devrait pas être trivial : '{text}'"


# ─────────────────────────────────────────────────────────────
# _word_count
# ─────────────────────────────────────────────────────────────

class TestWordCount:
    def test_simple_phrase(self):
        assert _word_count("le cerveau du systeme") == 4

    def test_with_numbers(self):
        assert _word_count("5 mA en moyenne") == 4

    def test_punctuation_ignored(self):
        assert _word_count("oui... non !") == 2

    def test_empty(self):
        assert _word_count("") == 0


# ─────────────────────────────────────────────────────────────
# _deterministic_accept — court-circuit positif (True si pré-check accepte
# la réponse sans appeler le LLM d'enrichissement)
#
# Note v1.x : l'API a évolué de `_deterministic_verdict(...) -> Optional[str]`
# (renvoyait la raison du rejet) vers `_deterministic_accept(...) -> bool`
# (cohérent avec l'approche "enrichissement assisté plutôt que validateur
# strict" — cf. DECISIONS.md §19). Le LLM reste responsable de proposer une
# question de précision ; les pré-checks n'ont qu'à dire si on peut le sauter.
# ─────────────────────────────────────────────────────────────


class TestDeterministicAccept:

    # Cas où le pré-check court-circuite (True = pas besoin de LLM)
    @pytest.mark.parametrize("section,answer", [
        ("Description", "Station météo autonome ESP32 mesurant T°/humidité/pression, transmission LoRaWAN, déploiement outdoor 6 mois."),
        ("Objectifs actifs", "Tenir 6 mois d'autonomie sur batterie LiPo 2000 mAh + solaire 5W"),
        ("Critère de contrainte / valeur", "< 50 µA"),
        ("Critère de contrainte / valeur", "IP65 minimum"),
        ("Critère de contrainte / valeur", "N/A"),
        ("Critère de contrainte / valeur", "TBD : à arbitrer selon impact consommation"),
        ("Composant / rôle", "Microcontrôleur principal + transmission LoRa"),
    ])
    def test_pass_through(self, section, answer):
        assert _deterministic_accept(section, answer) is True, (
            f"devrait être accepté en court-circuit : '{answer}' sur '{section}'"
        )

    # Cas où le pré-check ne court-circuite PAS (le LLM tranchera)
    @pytest.mark.parametrize("section,answer,reason", [
        ("Critère de contrainte / valeur", "TBD", "TBD seul sans contexte"),
        ("Critère de contrainte / valeur", "à voir", "trop vague"),
        ("Objectifs actifs", "améliorer les performances", "trop générique"),
        ("Objectifs actifs", "être robuste", "trop générique"),
        ("Description", "Une appli mobile.", "trop courte"),
        ("Contrainte non négociable", "important", "trop générique"),
    ])
    def test_not_short_circuited(self, section, answer, reason):
        # Pas un échec — juste un signal "le LLM doit regarder".
        assert _deterministic_accept(section, answer) is False, (
            f"devrait nécessiter le LLM ({reason}) : '{answer}'"
        )
