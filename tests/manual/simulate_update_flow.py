"""
Simulation d'une session `applied-fox interview update` complète.

Joue un scénario réaliste sur une copie du .md ESP32 :
    1. Ouvre le menu, choisit "Composants" (5).
    2. Ajoute la passerelle LoRaWAN identifiée comme manquante par l'éval Opus 4.7.
    3. Revient au menu, choisit "Identité" (1), passe la phase en pré-production.
    4. Choisit "Description" (2), tape "skip" pour conserver.
    5. Quitte le menu (0).
    6. Confirme l'application des modifications.
    7. Confirme la couche 3 (validation humaine).

Tout tourne pour de vrai SAUF :
    - Les `Prompt.ask` / `Confirm.ask` (mockés depuis une queue d'inputs).
    - `_try_requestion` (mocké pour retourner None — on teste le flow, pas le LLM).

Le reste tourne réellement :
    - Parsing structurel (couche 1)
    - Test de transmission (couche 2) avec un vrai appel Ollama
    - Génération du .md
    - Écriture sur disque
    - Préservation de l'historique des Changements

Lancement :
    python tests/manual/simulate_update_flow.py

Le script vérifie en sortie que le .md modifié :
    - Contient le nouveau composant.
    - A la phase pré-production.
    - A une nouvelle ligne dans Changements.
    - Passe toujours `parse_and_validate`.
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# UTF-8 stdout sur Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────
# Scénario joué (queue d'inputs)
# ─────────────────────────────────────────────────────────────

PROMPT_INPUTS = [
    # ── Menu : Composants ────────────────────────────────────
    "5",
    # ── Sous-menu Composants : ajouter ───────────────────────
    "a",
    "Passerelle LoRaWAN Dragino LPS8",                                  # nom
    "Réception trames LoRaWAN classe A, transit Ethernet vers backend Mosquitto local",  # rôle (via _ask_with_requestion)
    "en évaluation",                                                    # statut décisionnel
    "critique",                                                         # rôle pipeline
    "r",                                                                # retour menu principal

    # ── Menu : Identité ──────────────────────────────────────
    "1",
    "pré-production",   # nouvelle phase (_choose)
    "hybride",          # domaine inchangé (default)

    # ── Menu : Description ───────────────────────────────────
    "2",
    "skip",             # conserver la description actuelle

    # ── Quitter ──────────────────────────────────────────────
    "0",
]

CONFIRM_INPUTS = [
    True,   # "Appliquer ces modifications ?" (récap update)
    True,   # "Cette fiche est-elle correcte ?" (couche 3 validation humaine)
]


# ─────────────────────────────────────────────────────────────
# Mocks
# ─────────────────────────────────────────────────────────────

_prompt_iter = iter(PROMPT_INPUTS)
_confirm_iter = iter(CONFIRM_INPUTS)


def mocked_prompt_ask(prompt_text="", *args, default=None, choices=None, **kwargs):
    try:
        val = next(_prompt_iter)
    except StopIteration:
        val = default if default is not None else ""
        print(f"[SIM] PROMPT EXHAUSTED ({prompt_text!r}) -> default {val!r}")
        return val

    # Affiche pour traçage
    label = (prompt_text or "<no-label>").replace("\n", " ")[:60]
    print(f"[SIM] PROMPT {label!r} -> {val!r}")
    return val


def mocked_confirm_ask(prompt_text="", *args, default=False, **kwargs):
    try:
        val = next(_confirm_iter)
    except StopIteration:
        val = default
        print(f"[SIM] CONFIRM EXHAUSTED ({prompt_text!r}) -> default {val!r}")
        return val

    label = (prompt_text or "<no-label>").replace("\n", " ")[:60]
    print(f"[SIM] CONFIRM {label!r} -> {val!r}")
    return val


def mocked_try_requestion(*args, **kwargs):
    """Désactive le check LLM — on teste le flow, pas la qualité du LLM."""
    return None


# ─────────────────────────────────────────────────────────────
# Setup et exécution
# ─────────────────────────────────────────────────────────────


def main() -> int:
    src_path = PROJECT_ROOT / "projects" / "esp32_weather_station.md"
    if not src_path.exists():
        print(f"[FAIL] Fichier source absent : {src_path}")
        return 1

    # Copie le .md dans un fichier temporaire (pour ne pas toucher l'original)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(src_path.read_text(encoding="utf-8"))
        tmp_path = Path(tmp.name)

    print(f"[SIM] Fichier de test : {tmp_path}")
    print(f"[SIM] Contenu original : {len(tmp_path.read_text(encoding='utf-8'))} chars")

    # Snapshot avant
    from src.validation.structural import parse_and_validate
    md_before = tmp_path.read_text(encoding="utf-8")
    project_before, errors_before = parse_and_validate(md_before)
    if project_before is None:
        print(f"[FAIL] .md initial invalide : {errors_before}")
        return 1
    print(f"[SIM] AVANT : phase={project_before.identite.phase} | "
          f"composants={len(project_before.composants)} | "
          f"changements={len(project_before.changements)}")

    config = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "num_ctx": 4096,
            "timeout": 60,
            "models": {"interviewer": "mistral-nemo:latest"},
        },
        "profile": "small",
    }

    from src.agents import interviewer

    print()
    print("=" * 70)
    print("  DÉBUT SIMULATION")
    print("=" * 70)

    # Patches : on intercepte uniquement les inputs utilisateur et le LLM check
    with patch("rich.prompt.Prompt.ask", side_effect=mocked_prompt_ask), \
         patch("rich.prompt.Confirm.ask", side_effect=mocked_confirm_ask), \
         patch("src.interview.create._try_requestion",
               side_effect=mocked_try_requestion):
        try:
            project_after = interviewer.run_update(tmp_path, config)
        except SystemExit as e:
            print(f"[FAIL] run_update a fait sys.exit({e.code})")
            return 1
        except Exception as e:
            import traceback
            print(f"[FAIL] Exception : {type(e).__name__} : {e}")
            traceback.print_exc()
            return 1

    print()
    print("=" * 70)
    print("  FIN SIMULATION — VÉRIFICATIONS")
    print("=" * 70)

    # Vérifs
    md_after = tmp_path.read_text(encoding="utf-8")
    project_check, errors_check = parse_and_validate(md_after)
    if project_check is None:
        print(f"[FAIL] .md final invalide : {errors_check}")
        return 1

    n_pass = n_fail = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal n_pass, n_fail
        if cond:
            print(f"  [PASS] {label}" + (f" — {detail}" if detail else ""))
            n_pass += 1
        else:
            print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))
            n_fail += 1

    # 1. Composants : +1
    check(
        "Composant ajouté",
        len(project_check.composants) == len(project_before.composants) + 1,
        f"{len(project_before.composants)} -> {len(project_check.composants)}",
    )

    # 2. Composant ajouté contient le nom attendu
    has_lpwan = any(
        "Dragino" in c.nom or "LPS8" in c.nom for c in project_check.composants
    )
    check("Composant 'Dragino LPS8' présent", has_lpwan)

    # 3. Phase passée à pré-production
    check(
        "Phase changée en pré-production",
        project_check.identite.phase == "pré-production",
        f"{project_before.identite.phase} -> {project_check.identite.phase}",
    )

    # 4. Domaine inchangé
    check(
        "Domaine inchangé",
        project_check.identite.domaine == project_before.identite.domaine,
    )

    # 5. Description inchangée (skip)
    check(
        "Description inchangée (skip)",
        project_check.description == project_before.description,
    )

    # 6. Historique : +1 entrée
    check(
        "Historique Changements +1",
        len(project_check.changements) == len(project_before.changements) + 1,
        f"{len(project_before.changements)} -> {len(project_check.changements)}",
    )

    # 7. La nouvelle entrée mentionne les changements
    if project_check.changements:
        latest = project_check.changements[-1]
        resume_lower = latest.resume.lower()
        check(
            "Résumé mentionne 'composant'",
            "composant" in resume_lower,
            latest.resume[:80],
        )
        check(
            "Résumé mentionne 'phase'",
            "phase" in resume_lower,
            latest.resume[:80],
        )

    # 8. Existing components et changements préservés
    nom_orig = {c.nom for c in project_before.composants}
    nom_new = {c.nom for c in project_check.composants}
    check(
        "Tous les composants originaux préservés",
        nom_orig.issubset(nom_new),
        f"manquants : {nom_orig - nom_new}",
    )

    print()
    print("=" * 70)
    print(f"  BILAN : {n_pass} PASS, {n_fail} FAIL")
    print(f"  Fichier final : {tmp_path}")
    print("=" * 70)

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
