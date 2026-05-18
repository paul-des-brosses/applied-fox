"""
Couche 3 de validation — confirmation humaine via TUI Rich.

Affiche un récap structuré de la fiche projet et demande à l'utilisateur
de valider explicitement avant toute écriture sur disque.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from src.models import ProjectModel

console = Console()


def validate_human(project: ProjectModel, md_content: str) -> bool:
    """
    Affiche un récap de la fiche projet et demande confirmation.

    Args:
        project:    Le ProjectModel validé (couches 1 et 2 déjà passées).
        md_content: Le contenu brut du .md (proposé pour affichage optionnel).

    Returns:
        True si l'utilisateur confirme, False sinon.
    """
    console.print()
    console.print(
        Panel.fit(
            f"[bold green]COUCHE 3 — VALIDATION HUMAINE[/bold green]\n"
            f"Voici le récap de la fiche. Vérifie que tout est correct.",
            border_style="green",
        )
    )
    console.print()

    # ── Identité ──────────────────────────────────────────────
    console.print(f"[bold]Projet :[/bold] {project.nom_projet}")
    console.print(f"[bold]Phase :[/bold] {project.identite.phase}")
    console.print(f"[bold]Domaine :[/bold] {project.identite.domaine}")
    console.print(f"[bold]Dernière mise à jour :[/bold] {project.identite.derniere_mise_a_jour}")
    console.print()

    # ── Description ───────────────────────────────────────────
    console.print(
        Panel(
            project.description,
            title="[bold]Description[/bold]",
            border_style="dim",
        )
    )
    console.print()

    # ── Objectifs actifs ──────────────────────────────────────
    console.print("[bold]Objectifs actifs :[/bold]")
    for obj in project.objectifs_actifs:
        console.print(f"  • {obj}")
    console.print()

    # ── Prochain rendu ────────────────────────────────────────
    date_str = (
        str(project.prochain_rendu.date_prevue)
        if project.prochain_rendu.date_prevue
        else "N/A"
    )
    console.print(
        f"[bold]Prochain rendu :[/bold] {project.prochain_rendu.nature} "
        f"le {date_str}"
    )
    console.print()

    # ── Composants (table) ────────────────────────────────────
    comp_table = Table(title="Composants", show_header=True, header_style="bold cyan")
    comp_table.add_column("Composant")
    comp_table.add_column("Rôle")
    comp_table.add_column("Statut")
    comp_table.add_column("Pipeline")
    for c in project.composants:
        style = "bold red" if c.role_pipeline == "critique" else ""
        comp_table.add_row(
            c.nom, c.role, c.statut_decisionnel, c.role_pipeline, style=style
        )
    console.print(comp_table)
    console.print()

    # ── Stack software ────────────────────────────────────────
    stack_table = Table(title="Stack software", show_header=True, header_style="bold cyan")
    stack_table.add_column("Outil")
    stack_table.add_column("Rôle")
    stack_table.add_column("Version")
    stack_table.add_column("Statut")
    for s in project.stack_software:
        stack_table.add_row(s.outil, s.role, s.version, s.statut_decisionnel)
    console.print(stack_table)
    console.print()

    # ── Interactions ──────────────────────────────────────────
    console.print("[bold]Interactions :[/bold]")
    for i in project.interactions:
        parts = [f"{i.source} → {i.target} : {i.nature}"]
        if i.format:
            parts.append(f"| {i.format}")
        if i.volume:
            parts.append(f"| {i.volume}")
        console.print(f"  • {' '.join(parts)}")
    console.print()

    # ── Contraintes non négociables ───────────────────────────
    console.print("[bold]Contraintes non négociables :[/bold]")
    for cnn in project.contraintes_non_negociables:
        console.print(f"  • {cnn}")
    console.print()

    # ── Confirmation ──────────────────────────────────────────
    return Confirm.ask(
        "[bold green]Cette fiche est-elle correcte ?[/bold green] "
        "(O = sauvegarder, N = recommencer)",
        default=True,
    )
