"""
Agent Interviewer — Module Interview.

Seul module autorisé à créer ou modifier un fichier .md projet.
Tourne TOUJOURS en local via Ollama 7B Q4, quel que soit le mode global.

Modes :
    create   — questionnaire guidé section par section pour produire un .md neuf.
    update   — charge un .md existant, propose des révisions ciblées.
    integrate — applique un objet ValidatedSuggestion au .md (Jalon 2).

Pipeline de validation (couches 1, 2, 3) appliqué à chaque mode avant écriture.
Implémentation complète : Jalon 1 (create) et Jalon 2 (update + integrate).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from src.models import ProjectModel, ValidatedSuggestion

console = Console()

_MAX_RETRIES = 3


def run_create(output_dir: Path, config: dict) -> ProjectModel:
    """
    Mode create : dialogue guidé avec l'utilisateur pour produire un .md neuf.

    Processus :
        1. Questionnaire section par section via TUI Rich.
        2. Re-questionnement si réponse floue ou trop courte.
        3. Validation couche 1 (Pydantic + parsers Markdown).
        4. Validation couche 2 (test de transmission par LLM tiers).
        5. Validation couche 3 (relecture + confirmation humaine).
        6. Écriture du .md sur disque si toutes les couches passent.

    Args:
        output_dir: Dossier où écrire le .md produit (nom dérivé du projet).
        config:     Config globale (pour get_llm).

    Returns:
        Le ProjectModel validé.
    """
    from src.interview.create import generate_md, run_questionnaire
    from src.validation.human import validate_human
    from src.validation.structural import parse_and_validate
    from src.validation.transmission import validate_transmission

    for attempt in range(_MAX_RETRIES):
        # ── 1. Questionnaire ─────────────────────────────────────
        data = run_questionnaire(config)

        # ── 2. Génération du .md ─────────────────────────────────
        md_content = generate_md(data)

        # ── 3. Couche 1 — validation structurelle ────────────────
        project, errors = parse_and_validate(md_content)
        if project is None:
            console.print("\n[red]Couche 1 : validation structurelle échouée.[/red]")
            for err in errors:
                console.print(f"  [red]x[/red] {err}")
            if attempt < _MAX_RETRIES - 1:
                if not Confirm.ask(
                    "Recommencer le questionnaire pour corriger ?", default=True
                ):
                    sys.exit(1)
            continue

        # ── 4. Couche 2 — test de transmission (non-bloquant) ────
        passed, _, failed_checks = validate_transmission(md_content, project, config)
        if not passed:
            console.print(
                "[yellow]Test de transmission partiel — vérification humaine recommandée.[/yellow]"
            )

        # ── 5. Couche 3 — validation humaine ─────────────────────
        if validate_human(project, md_content):
            # ── 6. Écriture sur disque ───────────────────────────
            nom_slug = re.sub(r"[^a-z0-9]", "_", data["nom_projet"].lower())
            nom_slug = re.sub(r"_+", "_", nom_slug).strip("_")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{nom_slug}.md"
            output_path.write_text(md_content, encoding="utf-8")
            console.print(
                f"\n[bold green]Fiche sauvegardee :[/bold green] {output_path}"
            )
            return project

        # Utilisateur a dit non → on recommence
        if attempt < _MAX_RETRIES - 1:
            console.print("\n[yellow]On recommence le questionnaire.[/yellow]")
        else:
            console.print(
                "\n[red]Nombre maximum de tentatives atteint. Abandon.[/red]"
            )
            sys.exit(1)

    sys.exit(1)  # unreachable but satisfies type checker


def _run_validation_layers(
    md_content: str, project: ProjectModel, config: dict
) -> bool:
    """
    Réapplique les 3 couches de validation sur un .md modifié.
    Retourne True si toutes les couches passent (ou si l'utilisateur valide
    malgré une couche 2 incomplète), False si l'utilisateur refuse.
    """
    from src.validation.human import validate_human
    from src.validation.transmission import validate_transmission

    # Couche 2 — non bloquant
    passed, _, failed = validate_transmission(md_content, project, config)
    if not passed:
        console.print(
            "[yellow]Test de transmission partiel — vérification humaine recommandée.[/yellow]"
        )

    # Couche 3 — bloquant
    return validate_human(project, md_content)


def run_update(project_path: Path, config: dict) -> ProjectModel:
    """
    Mode update : charge un .md existant et propose des révisions ciblées.

    Processus :
        1. Charge et valide (couche 1) le .md existant.
        2. Lance le dialogue de modification (`update.run_update_dialog`).
        3. Re-génère le .md avec les modifications + historique préservé.
        4. Re-valide les 3 couches sur le .md modifié (symétrie avec create).
        5. Sauvegarde si validé.

    Args:
        project_path: Chemin vers le .md à mettre à jour.
        config:       Config globale.

    Returns:
        Le ProjectModel mis à jour et validé.

    Raises:
        SystemExit en cas d'abandon ou d'échec de validation après retries.
    """
    from src.interview.create import generate_md
    from src.interview.update import run_update_dialog
    from src.validation.structural import parse_and_validate

    # ── 1. Charger et valider le .md existant ────────────────
    if not project_path.exists():
        console.print(f"[red]Fichier introuvable : {project_path}[/red]")
        sys.exit(1)

    md_original = project_path.read_text(encoding="utf-8")
    project, errors = parse_and_validate(md_original)
    if project is None:
        console.print(f"\n[red]Le fichier {project_path.name} est invalide :[/red]")
        for err in errors:
            console.print(f"  [red]x[/red] {err}")
        console.print(
            "\n[yellow]Corrige le fichier manuellement avant d'utiliser update.[/yellow]"
        )
        sys.exit(1)

    console.print(
        f"\n[bold green]Fiche chargée :[/bold green] [cyan]{project_path.name}[/cyan]"
    )

    for attempt in range(_MAX_RETRIES):
        # ── 2. Dialogue de modification ──────────────────────
        result = run_update_dialog(project, config)
        if result is None or result[0] is None:
            console.print("[yellow]Aucune modification appliquée. Abandon.[/yellow]")
            sys.exit(0)
        data, historique, changes_resumes = result

        # ── 3. Génération du .md modifié ─────────────────────
        md_new = generate_md(data, changements=historique)

        # ── 4. Couche 1 sur le .md modifié ───────────────────
        project_new, errors = parse_and_validate(md_new)
        if project_new is None:
            console.print("\n[red]Couche 1 : la modification a invalidé le .md.[/red]")
            for err in errors:
                console.print(f"  [red]x[/red] {err}")
            if attempt < _MAX_RETRIES - 1:
                if not Confirm.ask(
                    "Reprendre le dialogue de modification ?", default=True
                ):
                    sys.exit(1)
            continue

        # ── 5. Couches 2 et 3 ────────────────────────────────
        if _run_validation_layers(md_new, project_new, config):
            # ── 6. Écriture sur disque ───────────────────────
            project_path.write_text(md_new, encoding="utf-8")
            console.print(
                f"\n[bold green]Fiche mise à jour :[/bold green] {project_path}"
            )
            console.print(
                f"[dim]Changements appliqués : {len(changes_resumes)}[/dim]"
            )
            return project_new

        if attempt < _MAX_RETRIES - 1:
            console.print("\n[yellow]Reprise du dialogue de modification.[/yellow]")
        else:
            console.print(
                "\n[red]Nombre maximum de tentatives atteint. Abandon.[/red]"
            )
            sys.exit(1)

    sys.exit(1)


def run_integrate(
    project_path: Path,
    suggestion: ValidatedSuggestion,
    config: dict,
) -> ProjectModel:
    """
    Mode integrate : applique une ValidatedSuggestion au .md projet.

    Processus :
        1. Charge le .md existant.
        2. Affiche la suggestion, dialogue sur les open_questions.
        3. Applique les changements via `integrate.apply_suggestion`.
        4. Re-génère le .md, repasse les 3 couches.
        5. Sauvegarde si validé.

    Args:
        project_path: Chemin vers le .md à modifier.
        suggestion:   Objet ValidatedSuggestion issu du Rapporteur.
        config:       Config globale.

    Returns:
        Le ProjectModel mis à jour et validé.
    """
    from src.interview.create import generate_md
    from src.interview.integrate import apply_suggestion
    from src.validation.structural import parse_and_validate

    # ── 1. Charger et valider le .md existant ────────────────
    if not project_path.exists():
        console.print(f"[red]Fichier introuvable : {project_path}[/red]")
        sys.exit(1)

    md_original = project_path.read_text(encoding="utf-8")
    project, errors = parse_and_validate(md_original)
    if project is None:
        console.print(f"\n[red]Le fichier {project_path.name} est invalide.[/red]")
        for err in errors:
            console.print(f"  [red]x[/red] {err}")
        sys.exit(1)

    # ── 2-3. Application de la suggestion ────────────────────
    result = apply_suggestion(project, suggestion, config)
    if result is None:
        console.print("[yellow]Suggestion non appliquée. Abandon.[/yellow]")
        sys.exit(0)
    data, historique, changes_resumes = result

    # ── 4. Génération + couches 1/2/3 ────────────────────────
    md_new = generate_md(data, changements=historique)
    project_new, errors = parse_and_validate(md_new)
    if project_new is None:
        console.print("\n[red]La suggestion produit un .md invalide :[/red]")
        for err in errors:
            console.print(f"  [red]x[/red] {err}")
        sys.exit(1)

    if not _run_validation_layers(md_new, project_new, config):
        console.print("[yellow]Validation humaine refusée. Suggestion non appliquée.[/yellow]")
        sys.exit(0)

    # ── 5. Écriture ──────────────────────────────────────────
    project_path.write_text(md_new, encoding="utf-8")
    console.print(
        f"\n[bold green]Suggestion intégrée :[/bold green] {project_path}"
    )
    console.print(f"[dim]Changements appliqués : {len(changes_resumes)}[/dim]")
    return project_new


def run_integrate_batch(
    project_path: Path,
    suggestions: list[ValidatedSuggestion],
    config: dict,
) -> tuple[int, int, int]:
    """
    Version batch de `run_integrate` : applique séquentiellement plusieurs
    ValidatedSuggestion à un même .md, sans `sys.exit` (utilisée par Jalon 6).

    Stratégie séquentielle :
        Pour chaque suggestion, on recharge le .md à jour, on applique, on
        repasse les 3 couches, on écrit. Si une suggestion échoue ou est
        refusée par l'utilisateur, on continue avec les suivantes — l'état
        sur disque reste cohérent (la suggestion précédente était déjà écrite).

    Pourquoi séquentiel et pas tout-en-un ?
        - Plus simple : pas de gestion de conflit entre suggestions qui touchent
          au même composant.
        - Auditabilité : chaque suggestion produit son propre item d'historique
          dans la section Changements.
        - Reprise : si on plante au milieu, ce qui a déjà été écrit est sauf.

    Args:
        project_path: Chemin vers le .md à modifier.
        suggestions: Liste de ValidatedSuggestion acceptées par l'utilisateur.
        config:       Config globale.

    Returns:
        Tuple (n_applied, n_skipped, n_failed).
    """
    from src.interview.create import generate_md
    from src.interview.integrate import apply_suggestion
    from src.validation.structural import parse_and_validate

    if not project_path.exists():
        console.print(f"[red]Fichier introuvable : {project_path}[/red]")
        return (0, 0, len(suggestions))

    n_applied = 0
    n_skipped = 0
    n_failed = 0

    for i, suggestion in enumerate(suggestions, start=1):
        console.print()
        console.print(
            f"[bold cyan]── Suggestion {i}/{len(suggestions)} ──[/bold cyan]"
        )

        # Recharge à chaque tour : capture l'état après la suggestion précédente.
        md_original = project_path.read_text(encoding="utf-8")
        project, errors = parse_and_validate(md_original)
        if project is None:
            console.print(
                f"[red]La fiche est devenue invalide après la suggestion précédente — "
                f"abandon du batch.[/red]"
            )
            for err in errors:
                console.print(f"  [red]x[/red] {err}")
            n_failed += len(suggestions) - i + 1
            break

        # Application + dialogue open_questions
        result = apply_suggestion(project, suggestion, config)
        if result is None:
            console.print("[yellow]Suggestion sautée par l'utilisateur.[/yellow]")
            n_skipped += 1
            continue
        data, historique, changes_resumes = result

        # Re-génération + 3 couches
        md_new = generate_md(data, changements=historique)
        project_new, errors = parse_and_validate(md_new)
        if project_new is None:
            console.print(
                "[red]Cette suggestion produit un .md invalide — sautée.[/red]"
            )
            for err in errors[:5]:
                console.print(f"  [red]x[/red] {err}")
            n_failed += 1
            continue

        if not _run_validation_layers(md_new, project_new, config):
            console.print(
                "[yellow]Validation humaine refusée pour cette suggestion. "
                "Passage à la suivante.[/yellow]"
            )
            n_skipped += 1
            continue

        # Écriture (la prochaine itération rechargera ce contenu)
        project_path.write_text(md_new, encoding="utf-8")
        console.print(
            f"[bold green]✓ Suggestion intégrée[/bold green] "
            f"[dim]({len(changes_resumes)} changements écrits)[/dim]"
        )
        n_applied += 1

    console.print()
    console.print(
        f"[bold]Batch terminé :[/bold] "
        f"[green]{n_applied} intégrée(s)[/green] · "
        f"[yellow]{n_skipped} sautée(s)[/yellow] · "
        f"[red]{n_failed} échec(s)[/red]"
    )
    return (n_applied, n_skipped, n_failed)
