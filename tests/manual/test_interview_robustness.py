"""
Harnais de test de robustesse — système hybride de re-questionnement Interview.

Lance un corpus large de cas (réponses bonnes, mauvaises, edge cases) à travers
le système hybride (pré-checks déterministes + LLM). Mesure :
    - taux de bons verdicts global et par catégorie
    - cas que le pré-check rate (faux-négatif déterministe → le LLM doit rattraper)
    - cas où le LLM hallucine (faux-positif ou faux-négatif LLM)
    - identification claire des sections les plus difficiles

NE TOURNE PAS DANS pytest. À lancer manuellement :
    python tests/manual/test_interview_robustness.py [--model nom_modele]

Le modèle par défaut est celui configuré pour `interviewer` dans la config par défaut.
On peut tester plusieurs modèles avec :
    python tests/manual/test_interview_robustness.py --model mistral-nemo:latest
    python tests/manual/test_interview_robustness.py --model qwen2.5:14b-instruct-q4_K_M
"""

from __future__ import annotations

import argparse
import sys
import io
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Permet l'import de `src.*` quand on lance le script directement
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Force UTF-8 stdout sur Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


@dataclass
class TestCase:
    label: str
    section: str
    answer: str
    expected: str  # 'OK' ou 'FOLLOWUP'
    category: str  # 'concrete', 'tbd', 'generic', 'paraphrase', 'offtopic', 'edge'
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# CORPUS DE TESTS — 60+ cas variés
# ─────────────────────────────────────────────────────────────────────────────

CASES: list[TestCase] = [

    # ── BONNES RÉPONSES (devraient passer) ───────────────────────────────
    TestCase("Obj quantif chiffre+unité", "Objectifs actifs",
             "Tenir 6 mois d'autonomie sur batterie LiPo 2000 mAh + solaire 5W", "OK", "concrete"),
    TestCase("Obj précision capteur", "Objectifs actifs",
             "Précision température ±0.5°C en plage -10°C / +50°C", "OK", "concrete"),
    TestCase("Obj coût matériel", "Objectifs actifs",
             "Coût matériel < 80€ par station", "OK", "concrete"),
    TestCase("Obj conformité norme", "Objectifs actifs",
             "Conforme à la norme IP65 minimum pour outdoor", "OK", "concrete"),
    TestCase("Obj latence réseau", "Objectifs actifs",
             "Latence réseau < 200 ms en 95e percentile", "OK", "concrete"),
    TestCase("Obj capacité concurrence", "Objectifs actifs",
             "Supporter 1000 utilisateurs concurrents avec p99 < 500ms", "OK", "concrete"),
    TestCase("Obj uptime SLA", "Objectifs actifs",
             "Uptime 99.5% sur 30 jours glissants", "OK", "concrete"),

    TestCase("Desc projet IoT complète", "Description",
             "Station météo autonome ESP32 mesurant T°/humidité/pression, transmission LoRaWAN vers passerelle locale, déploiement outdoor 6 mois sans intervention.", "OK", "concrete"),
    TestCase("Desc projet web", "Description",
             "Application web React+FastAPI pour gérer les stocks pharmaceutiques d'une chaîne de 20 officines, déploiement on-premise avec sync nocturne.", "OK", "concrete"),
    TestCase("Desc projet mobile", "Description",
             "App Android scannant codes-barres pour catalogage numismatique, chiffrement local AES-256, usage hors ligne 24h, target Android 8+.", "OK", "concrete"),
    TestCase("Desc sans chiffre mais spécifique", "Description",
             "Plugin Figma qui automatise la génération d'icônes SVG vectoriels selon une grille de design system imposée, intégration OAuth GitHub.", "OK", "concrete"),
    TestCase("Desc projet artistique", "Description",
             "Installation interactive Forest of Senses utilisant capteurs Kinect et projection mappée pour une exposition itinérante en galerie d'art.", "OK", "concrete"),

    TestCase("Critère < 50 µA", "Critère de contrainte / valeur", "< 50 µA", "OK", "concrete"),
    TestCase("Critère IP65", "Critère de contrainte / valeur", "IP65 minimum", "OK", "concrete"),
    TestCase("Critère portée 5 km", "Critère de contrainte / valeur", "5 km en zone semi-rurale", "OK", "concrete"),
    TestCase("Critère plage temp", "Critère de contrainte / valeur", "-10°C à +50°C", "OK", "concrete"),
    TestCase("Critère prix", "Critère de contrainte / valeur", "< 80€ par unité", "OK", "concrete"),
    TestCase("Critère licence", "Critère de contrainte / valeur", "Open-source MIT obligatoire", "OK", "concrete"),
    TestCase("Critère N/A", "Critère de contrainte / valeur", "N/A", "OK", "edge"),
    TestCase("Critère N/A point", "Critère de contrainte / valeur", "N.A.", "OK", "edge"),
    TestCase("Critère TBD justifié", "Critère de contrainte / valeur",
             "TBD : à arbitrer selon impact consommation", "OK", "tbd"),
    TestCase("Critère TBD justifié 2", "Critère de contrainte / valeur",
             "TBD : dépend du choix final du module LoRa", "OK", "tbd"),

    TestCase("Comp role tech", "Composant / rôle",
             "Microcontrôleur principal + transmission LoRa", "OK", "concrete"),
    TestCase("Comp role capteur", "Composant / rôle",
             "Capteur T°/humidité/pression I2C", "OK", "concrete"),
    TestCase("Comp role alim", "Composant / rôle",
             "Stockage énergie principal pour mode nuit", "OK", "concrete"),

    TestCase("Interaction nature mesure", "Interaction / nature",
             "mesures T°/humidité/pression", "OK", "concrete"),
    TestCase("Interaction nature trame", "Interaction / nature",
             "trames NMEA position GPS", "OK", "concrete"),
    TestCase("Interaction nature alim", "Interaction / nature",
             "alimentation 3.3V régulée", "OK", "concrete"),

    TestCase("CNN client", "Contrainte non négociable",
             "Pas de cloud commercial — passerelle LoRaWAN locale obligatoire (exigence client)", "OK", "concrete"),
    TestCase("CNN soutenance", "Contrainte non négociable",
             "Code open-source MIT pour la soutenance ESILV", "OK", "concrete"),
    TestCase("CNN certif", "Contrainte non négociable",
             "Certification CE obligatoire avant mise sur le marché européen", "OK", "concrete"),

    TestCase("Rendu prototype", "Contenu attendu rendu",
             "Prototype fonctionnel + 1 mois de données collectées et visualisées sur Grafana", "OK", "concrete"),
    TestCase("Rendu démo", "Contenu attendu rendu",
             "Démo live de 3 minutes avec 2 cas d'usage (lecture mesure, gestion erreur transmission)", "OK", "concrete"),

    # ── MAUVAISES RÉPONSES — TBD nu ──────────────────────────────────────
    TestCase("TBD nu", "Critère de contrainte / valeur", "TBD", "FOLLOWUP", "tbd"),
    TestCase("TBD lowercase", "Critère de contrainte / valeur", "tbd", "FOLLOWUP", "tbd"),
    TestCase("à voir", "Critère de contrainte / valeur", "à voir", "FOLLOWUP", "tbd"),
    TestCase("a voir sans accent", "Critère de contrainte / valeur", "a voir", "FOLLOWUP", "tbd"),
    TestCase("je sais pas", "Critère de contrainte / valeur", "je sais pas", "FOLLOWUP", "tbd"),
    TestCase("inconnu", "Critère de contrainte / valeur", "inconnu", "FOLLOWUP", "tbd"),
    TestCase("? interrogation", "Critère de contrainte / valeur", "?", "FOLLOWUP", "tbd"),
    TestCase("??? multiples", "Critère de contrainte / valeur", "???", "FOLLOWUP", "tbd"),
    TestCase("à définir", "Critère de contrainte / valeur", "à définir", "FOLLOWUP", "tbd"),
    TestCase("TBD avec :", "Critère de contrainte / valeur", "TBD :", "FOLLOWUP", "tbd",
             "TBD avec deux-points mais sans raison"),

    # ── MAUVAISES RÉPONSES — phrases génériques ──────────────────────────
    TestCase("Obj améliorer perf", "Objectifs actifs",
             "améliorer les performances", "FOLLOWUP", "generic"),
    TestCase("Obj être robuste", "Objectifs actifs", "être robuste", "FOLLOWUP", "generic"),
    TestCase("Obj être fiable", "Objectifs actifs", "être fiable", "FOLLOWUP", "generic"),
    TestCase("Obj qualité haute", "Objectifs actifs", "qualité haute", "FOLLOWUP", "generic"),
    TestCase("Obj sécurité maximale", "Objectifs actifs", "sécurité maximale", "FOLLOWUP", "generic"),
    TestCase("Desc verbeuse vide", "Description",
             "Système qui collecte des données de manière fiable et performante.", "FOLLOWUP", "generic"),
    TestCase("Desc collection auto", "Description",
             "Une solution moderne et innovante pour répondre aux besoins du marché.", "FOLLOWUP", "generic"),
    TestCase("Desc tech-buzz", "Description",
             "Une plateforme distribuée scalable basée sur le cloud avec une approche data-driven.", "FOLLOWUP", "generic",
             "Verbeux, technique-sonnant, mais aucune info concrète"),
    TestCase("Critère élevé", "Critère de contrainte / valeur", "élevé", "FOLLOWUP", "generic"),
    TestCase("Critère faible", "Critère de contrainte / valeur", "faible", "FOLLOWUP", "generic"),
    TestCase("Critère optimal", "Critère de contrainte / valeur", "optimal", "FOLLOWUP", "generic"),
    TestCase("Comp role cerveau", "Composant / rôle",
             "le cerveau du système", "FOLLOWUP", "generic"),
    TestCase("Comp role principal", "Composant / rôle",
             "composant principal", "FOLLOWUP", "generic"),
    TestCase("Interaction nature données", "Interaction / nature",
             "données", "FOLLOWUP", "generic"),
    TestCase("Interaction nature lien", "Interaction / nature",
             "lien", "FOLLOWUP", "generic"),
    TestCase("Interaction nature comm", "Interaction / nature",
             "communication", "FOLLOWUP", "generic"),
    TestCase("CNN préférence", "Contrainte non négociable",
             "on aimerait que ce soit rapide", "FOLLOWUP", "generic",
             "Préférence, pas contrainte non négociable"),

    # ── MAUVAISES RÉPONSES — paraphrases / triviales ─────────────────────
    TestCase("Paraphrase obj", "Objectifs actifs", "avoir un objectif", "FOLLOWUP", "paraphrase"),
    TestCase("Paraphrase desc", "Description", "décrire le projet", "FOLLOWUP", "paraphrase"),
    TestCase("rien", "Critère de contrainte / valeur", "rien", "FOLLOWUP", "paraphrase"),
    TestCase("ouais", "Critère de contrainte / valeur", "ouais", "FOLLOWUP", "paraphrase"),
    TestCase("desc trop courte", "Description", "Une appli mobile.", "FOLLOWUP", "paraphrase"),
    TestCase("desc 1 mot", "Description", "App.", "FOLLOWUP", "paraphrase"),

    # ── MAUVAISES RÉPONSES — listes de mots-clés ─────────────────────────
    TestCase("Obj liste mots", "Objectifs actifs",
             "autonomie, prix, performance", "FOLLOWUP", "generic",
             "Liste de catégories sans valeurs"),
    TestCase("Obj liste mots 2", "Objectifs actifs",
             "fiabilité robustesse efficacité", "FOLLOWUP", "generic"),

    # ── EDGE CASES — qui doivent passer ──────────────────────────────────
    TestCase("Comp role courte mais tech", "Composant / rôle",
             "Recharge MPPT", "OK", "edge",
             "2 mots mais terme technique précis"),
    TestCase("Comp role acronyme", "Composant / rôle",
             "GPU compute kernel", "OK", "edge"),
    TestCase("Critère valeur range", "Critère de contrainte / valeur",
             "16-64 GB RAM", "OK", "edge"),
    TestCase("Critère valeur range mois", "Critère de contrainte / valeur",
             "6-12 mois selon scénario", "OK", "edge"),
    TestCase("Interaction nature courte", "Interaction / nature",
             "PWM", "OK", "edge",
             "Sigle technique seul, mais explicite"),
    TestCase("Interaction nature 2 mots", "Interaction / nature",
             "alimentation continue", "OK", "edge"),
    TestCase("CNN avec ref ext", "Contrainte non négociable",
             "RGPD : pas de stockage de données personnelles hors UE", "OK", "edge"),

    # ── EDGE CASES — qui doivent rejeter ─────────────────────────────────
    TestCase("Long mais aucune info", "Description",
             "Le projet vise à résoudre un problème important pour les utilisateurs en proposant une solution innovante adaptée à leurs besoins quotidiens dans une démarche centrée utilisateur.", "FOLLOWUP", "generic",
             "Long, syntaxiquement correct, mais aucune info technique extractable"),
    TestCase("Long technique-sonnant vide", "Description",
             "Une architecture event-driven microservices avec un backend distribué et une approche cloud-native pour servir des cas d'usage variés.", "FOLLOWUP", "generic",
             "Buzzwords sans le projet concret"),
    TestCase("Mots techniques mais hors-sujet", "Objectifs actifs",
             "I2C sera utilisé", "FOLLOWUP", "offtopic",
             "Contient un sigle mais c'est un fait technique, pas un objectif"),
    TestCase("Description en anglais OK", "Description",
             "Embedded weather station based on ESP32 measuring T°/humidity/pressure, LoRaWAN transmission, 6 months outdoor autonomy on solar+LiPo.", "OK", "edge",
             "Réponse en anglais — doit être acceptée si technique"),

    # ── HALLUCINATIONS POSSIBLES ─────────────────────────────────────────
    TestCase("Fausse précision unité",  "Critère de contrainte / valeur",
             "très très petit", "FOLLOWUP", "generic"),
    TestCase("Nombre sans unité", "Critère de contrainte / valeur",
             "5", "FOLLOWUP", "generic",
             "Chiffre seul sans unité — devrait être rejeté"),
    TestCase("Pourcentage sans contexte", "Objectifs actifs",
             "augmenter de 50%", "FOLLOWUP", "generic",
             "Chiffre+unité mais pas d'objet de mesure"),
]


def run_corpus(llm, model_name: str) -> dict:
    """Exécute le corpus complet et retourne les statistiques."""
    from src.interview.create import (
        _deterministic_verdict,
        _try_requestion,
        _SECTION_GUIDES,
    )

    by_category: dict[str, list[tuple[TestCase, str, str, float]]] = defaultdict(list)
    failures: list[tuple[TestCase, str, str, str]] = []  # (case, actual, source, llm_followup)

    print(f"\n{'═' * 80}")
    print(f"  TEST DE ROBUSTESSE — modèle : {model_name}")
    print(f"  {len(CASES)} cas | sections variées | catégories : "
          f"{', '.join(sorted({c.category for c in CASES}))}")
    print(f"{'═' * 80}\n")

    t_global_start = time.time()
    for i, case in enumerate(CASES, 1):
        expectations = _SECTION_GUIDES.get(case.section, "")
        t_start = time.time()

        # Étage 1 : pré-check déterministe
        det = _deterministic_verdict(case.section, case.answer)
        if det is not None:
            actual, source, llm_response = "FOLLOWUP", "DET", det
        else:
            # Étage 2 : LLM
            result = _try_requestion(
                llm, "TestProject", case.section, "Q", case.answer, expectations
            )
            actual = "OK" if result is None else "FOLLOWUP"
            source = "LLM"
            llm_response = "OK" if result is None else result

        elapsed = time.time() - t_start
        ok = actual == case.expected
        by_category[case.category].append((case, actual, source, elapsed))
        if not ok:
            failures.append((case, actual, source, llm_response))

        sym = "OK" if ok else "KO"
        print(f"  [{i:2d}/{len(CASES)}] {sym} [{source}] {case.label:35s} "
              f"| {case.expected:8s} -> {actual:8s} ({elapsed:.1f}s)", flush=True)
        if not ok:
            print(f"          | Reponse : {case.answer[:70]}", flush=True)
            if source == "LLM":
                print(f"          | LLM a dit : {llm_response[:90]}", flush=True)

    t_total = time.time() - t_global_start

    # ── Statistiques ─────────────────────────────────────────────────────
    print(f"\n{'═' * 80}")
    print(f"  STATS PAR CATÉGORIE")
    print(f"{'═' * 80}")
    for cat in sorted(by_category):
        results = by_category[cat]
        n_total = len(results)
        n_pass = sum(1 for c, a, _, _ in results if a == c.expected)
        det_count = sum(1 for _, _, s, _ in results if s == "DET")
        avg_time = sum(t for _, _, _, t in results) / n_total
        print(f"  {cat:12s} : {n_pass:2d}/{n_total:2d} ({100*n_pass/n_total:5.1f}%) "
              f"| {det_count:2d} det / {n_total - det_count:2d} llm | {avg_time:.1f}s/cas moy.")

    n_pass_total = sum(
        1 for c, a, _, _ in
        [(c, a, s, t) for cat in by_category for c, a, s, t in by_category[cat]]
        if a == c.expected
    )
    print(f"\n  GLOBAL : {n_pass_total}/{len(CASES)} ({100*n_pass_total/len(CASES):.1f}%)")
    print(f"  Temps total : {t_total:.0f}s ({t_total/len(CASES):.1f}s/cas moy.)")

    # ── Échecs détaillés ─────────────────────────────────────────────────
    if failures:
        print(f"\n{'═' * 80}")
        print(f"  ÉCHECS — {len(failures)}")
        print(f"{'═' * 80}")
        for case, actual, source, llm_resp in failures:
            print(f"\n  [{source}] {case.label}")
            print(f"    Section  : {case.section}")
            print(f"    Réponse  : {case.answer[:100]}")
            print(f"    Attendu  : {case.expected}")
            print(f"    Obtenu   : {actual}")
            if source == "LLM" and actual == "FOLLOWUP":
                print(f"    Question : {llm_resp[:120]}")
            if case.notes:
                print(f"    Note     : {case.notes}")

    return {
        "model": model_name,
        "total": len(CASES),
        "passed": n_pass_total,
        "failures": failures,
        "by_category": {
            cat: (
                sum(1 for c, a, _, _ in by_category[cat] if a == c.expected),
                len(by_category[cat]),
            )
            for cat in by_category
        },
        "time_total": t_total,
    }


# Sous-ensemble de 20 cas "discriminants" — un par mode d'échec critique.
# Permet une itération rapide (~30-60 sec) pendant le tuning du prompt.
QUICK_CASE_LABELS = {
    # Bonnes réponses variées (5)
    "Obj quantif chiffre+unité",
    "Desc projet IoT complète",
    "Critère IP65",
    "Critère TBD justifié",
    "Comp role tech",
    # Mauvaises — TBD/triviaux (3)
    "TBD nu",
    "à voir",
    "rien",
    # Mauvaises — phrases génériques (4)
    "Obj améliorer perf",
    "Obj être robuste",
    "Desc verbeuse vide",
    "Comp role cerveau",
    # Mauvaises — paraphrase / list (2)
    "Paraphrase obj",
    "Obj liste mots",
    # Edge cases qui doivent passer (3)
    "Comp role courte mais tech",
    "Critère N/A",
    "CNN avec ref ext",
    # Edge cases qui doivent rejeter (3)
    "Long technique-sonnant vide",
    "Mots techniques mais hors-sujet",
    "Nombre sans unité",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mistral-nemo:latest", help="Nom du modèle Ollama")
    parser.add_argument("--quick", action="store_true",
                        help="Utilise un sous-ensemble de ~20 cas discriminants pour itérer vite")
    args = parser.parse_args()

    from src.llm import get_llm

    config = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "num_ctx": 8192,
            "timeout": 180,
            "models": {"interviewer": args.model},
        },
        "profile": "small",
    }
    llm = get_llm("interviewer", config)

    # Filtrage si --quick
    global CASES
    if args.quick:
        original = CASES
        CASES = [c for c in CASES if c.label in QUICK_CASE_LABELS]
        missing = QUICK_CASE_LABELS - {c.label for c in CASES}
        if missing:
            print(f"[WARN] Labels manquants : {missing}", flush=True)

    run_corpus(llm, args.model)


if __name__ == "__main__":
    main()
