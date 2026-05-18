"""
TUI Rich pour la validation utilisateur des ValidatedSuggestion (Jalon 6).

Flow :
    1. Charge `04_validated_suggestions.json` produit par le Rapporteur.
    2. Affiche un tableau récapitulatif (#, titre, composants impactés).
    3. Pour chaque suggestion, affiche le détail (panel) et demande
       une décision : accept / reject / defer (+ raison libre).
    4. À la fin, récap des décisions, confirmation, sauvegarde dans
       `05_user_validated.json`.

Décisions :
    - accept : la suggestion sera passée à `interview integrate` pour modifier
               la fiche projet.
    - reject : la suggestion est définitivement écartée (consignée avec raison).
    - defer  : remise à plus tard, non intégrée maintenant, conservée pour
               un futur run éventuel.

Pourquoi pas un full-screen TUI keyboard-driven ? Le pattern prompt séquentiel
est plus simple à maintenir, plus accessible (SSH, terminaux limités), et
laisse l'utilisateur lire chaque suggestion à son rythme. Cohérent avec le
reste de l'UX `interview create/update`.
"""

from __future__ import annotations

import json
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.models import ValidatedSuggestion

console = Console()

Decision = Literal["accept", "reject", "defer"]


@dataclass
class UserDecision:
    """Décision utilisateur sur une suggestion."""
    suggestion: ValidatedSuggestion
    decision: Decision
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "suggestion": self.suggestion.model_dump(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserDecision":
        return cls(
            suggestion=ValidatedSuggestion(**d["suggestion"]),
            decision=d["decision"],
            reason=d.get("reason", ""),
        )


# ─────────────────────────────────────────────────────────────
# Affichage
# ─────────────────────────────────────────────────────────────


def _render_summary_table(suggestions: list[ValidatedSuggestion]) -> Table:
    """Tableau récap : #, titre tronqué, composants impactés."""
    table = Table(
        title="[bold green]Suggestions à valider[/bold green]",
        show_lines=False,
        border_style="cyan",
    )
    table.add_column("#", style="cyan", no_wrap=True, width=3)
    table.add_column("Titre", style="bold")
    table.add_column("Composants", style="dim")
    for i, s in enumerate(suggestions, start=1):
        comps = ", ".join(s.components_affected) if s.components_affected else "-"
        table.add_row(str(i), s.title[:80], comps[:40])
    return table


def _render_suggestion_detail(idx: int, total: int, s: ValidatedSuggestion) -> Panel:
    """Panel détaillé d'une suggestion."""
    lines: list[str] = []
    lines.append(f"[bold]{s.title}[/bold]")
    lines.append("")
    lines.append(f"[dim]Ce qui change :[/dim]")
    lines.append(s.changes_summary)
    lines.append("")
    if s.components_affected:
        lines.append(f"[dim]Composants impactés :[/dim] {', '.join(s.components_affected)}")
    if s.new_components:
        lines.append(f"[dim]Nouveaux composants proposés :[/dim] {len(s.new_components)}")
        for nc in s.new_components:
            lines.append(f"  • {nc.get('nom', '?')} — {nc.get('role', '?')}")
    if s.interactions_changes:
        lines.append("[dim]Changements d'interactions :[/dim]")
        for ic in s.interactions_changes[:5]:
            lines.append(f"  • {ic}")
        if len(s.interactions_changes) > 5:
            lines.append(f"  [dim]... et {len(s.interactions_changes) - 5} autres[/dim]")
    if s.constraints_impact:
        lines.append(f"[dim]Impact contraintes :[/dim] {s.constraints_impact}")
    if s.open_questions:
        lines.append("")
        lines.append(
            f"[yellow]Questions ouvertes ({len(s.open_questions)}) — "
            f"résolues à l'étape `interview integrate` :[/yellow]"
        )
        for q in s.open_questions[:3]:
            lines.append(f"  ? {q}")
        if len(s.open_questions) > 3:
            lines.append(f"  [dim]... et {len(s.open_questions) - 3} autres[/dim]")
    if s.integration_notes:
        lines.append("")
        lines.append(f"[dim italic]{s.integration_notes[:300]}[/dim italic]")

    return Panel(
        "\n".join(lines),
        title=f"[bold]Suggestion {idx}/{total}[/bold]",
        border_style="cyan",
    )


def _render_decisions_summary(decisions: list[UserDecision]) -> Table:
    """Tableau récap final des décisions."""
    table = Table(
        title="[bold]Récap des décisions[/bold]",
        border_style="green",
    )
    table.add_column("#", style="cyan", width=3)
    table.add_column("Décision", style="bold", width=10)
    table.add_column("Titre")
    table.add_column("Raison", style="dim")
    for i, d in enumerate(decisions, start=1):
        color = {"accept": "green", "reject": "red", "defer": "yellow"}[d.decision]
        table.add_row(
            str(i),
            f"[{color}]{d.decision}[/{color}]",
            d.suggestion.title[:60],
            d.reason[:40] if d.reason else "-",
        )
    return table


# ─────────────────────────────────────────────────────────────
# Logique de validation
# ─────────────────────────────────────────────────────────────


class _BackRequested(Exception):
    """Levée quand l'utilisateur demande à revenir à la suggestion précédente."""


def _ask_decision(
    idx: int,
    total: int,
    report_path: Optional[Path] = None,
) -> tuple[Decision, str]:
    """
    Demande la décision sur une suggestion.

    Returns (decision, raison), ou lève _BackRequested si l'utilisateur
    tape 'b' pour revenir à la suggestion précédente.
    """
    _report_path = report_path
    back_hint = " · [dim]b=revenir[/dim]" if idx > 1 else ""
    report_hint = " · [dim]v=voir rapport[/dim]" if _report_path else ""
    console.print(
        f"\n[bold]Action[/bold] [dim]({idx}/{total})[/dim] : "
        "[green]a[/green]=accept · [red]r[/red]=reject · "
        f"[yellow]d[/yellow]=defer · [cyan]p[/cyan]=passer{back_hint}{report_hint}",
    )
    choices = ["a", "r", "d", "p"]
    if idx > 1:
        choices.append("b")
    if _report_path:
        choices.append("v")
    while True:
        action = Prompt.ask("→", choices=choices, default="p").lower()
        if action == "b":
            raise _BackRequested()
        if action == "v":
            try:
                webbrowser.open(_report_path.as_uri())
                console.print(f"[dim]Rapport ouvert : {_report_path}[/dim]")
            except Exception:  # noqa: BLE001
                console.print(f"[dim]Ouvre manuellement : {_report_path}[/dim]")
            continue  # redemande la décision
        if action == "p":
            return "defer", "Passé sans décision explicite"
        decision: Decision = {"a": "accept", "r": "reject", "d": "defer"}[action]
        if decision == "reject":
            reason = Prompt.ask(
                "[dim]Raison du rejet (entrée pour laisser vide)[/dim]",
                default="",
            )
        elif decision == "defer":
            reason = Prompt.ask(
                "[dim]Pourquoi reporter ? (entrée pour vide)[/dim]",
                default="",
            )
        else:  # accept
            reason = ""
        return decision, reason


def validate_suggestions_tui(
    suggestions: list[ValidatedSuggestion],
    report_path: Optional[Path] = None,
) -> Optional[list[UserDecision]]:
    """
    Lance la TUI de validation sur une liste de suggestions.

    Returns:
        Liste de UserDecision (1 par suggestion), ou None si l'utilisateur abandonne.
    """
    if not suggestions:
        console.print("[yellow]Aucune suggestion à valider.[/yellow]")
        return []

    console.print()
    console.print(
        Panel.fit(
            f"[bold green]VALIDATION DES SUGGESTIONS[/bold green]\n"
            f"{len(suggestions)} suggestion(s) à examiner. "
            "Pour chacune : accept / reject / defer.\n"
            "Les acceptées seront passées à [cyan]interview integrate[/cyan] "
            "pour modifier la fiche projet.",
            border_style="green",
        )
    )

    console.print()
    console.print(_render_summary_table(suggestions))

    if not Confirm.ask(
        "\n[bold]Démarrer la revue ?[/bold]",
        default=True,
    ):
        return None

    decisions: list[UserDecision] = []
    i = 0
    while i < len(suggestions):
        s = suggestions[i]
        console.print()
        console.print(_render_suggestion_detail(i + 1, len(suggestions), s))
        try:
            decision, reason = _ask_decision(i + 1, len(suggestions), report_path)
        except _BackRequested:
            # Revenir à la suggestion précédente (i > 0 garanti par _ask_decision)
            decisions.pop()
            i -= 1
            console.print("[dim]Retour à la suggestion précédente.[/dim]")
            continue
        decisions.append(UserDecision(suggestion=s, decision=decision, reason=reason))
        i += 1

    # Récap final
    console.print()
    console.print(_render_decisions_summary(decisions))

    n_accept = sum(1 for d in decisions if d.decision == "accept")
    n_reject = sum(1 for d in decisions if d.decision == "reject")
    n_defer = sum(1 for d in decisions if d.decision == "defer")
    console.print(
        f"\n[bold]Total :[/bold] "
        f"[green]{n_accept} acceptée(s)[/green] · "
        f"[red]{n_reject} rejetée(s)[/red] · "
        f"[yellow]{n_defer} reportée(s)[/yellow]"
    )

    if not Confirm.ask(
        "\n[bold]Sauvegarder ces décisions ?[/bold] "
        "[dim](les acceptées seront prêtes pour `interview integrate`)[/dim]",
        default=True,
    ):
        console.print("[yellow]Décisions non sauvegardées.[/yellow]")
        return None

    return decisions


# ─────────────────────────────────────────────────────────────
# Persistance disque
# ─────────────────────────────────────────────────────────────


def load_suggestions(path: Path) -> list[ValidatedSuggestion]:
    """Charge `04_validated_suggestions.json` produit par le Rapporteur."""
    if not path.exists():
        raise FileNotFoundError(f"Fichier suggestions introuvable : {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ValidatedSuggestion(**item) for item in raw]


def save_decisions(decisions: list[UserDecision], path: Path) -> None:
    """Sauvegarde les décisions utilisateur dans `05_user_validated.json`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [d.to_dict() for d in decisions]
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_decisions(path: Path) -> list[UserDecision]:
    """Recharge les décisions utilisateur depuis disque (pour `interview integrate`)."""
    if not path.exists():
        raise FileNotFoundError(f"Fichier décisions introuvable : {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [UserDecision.from_dict(item) for item in raw]
