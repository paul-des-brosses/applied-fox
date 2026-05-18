"""
Menu interactif multi-projets (Jalon 7).

Flow utilisateur :
    1. `applied-fox` (sans argument) → TUI Rich liste les projets de
       `~/.applied-fox/projects/`.
    2. Sélection d'un projet OU "+" pour en créer un.
    3. Menu d'actions sur le projet : run / consulter runs / valider /
       intégrer / update / retour.
    4. Pour `run` : pipeline en thread, barre de progression réelle alimentée
       par le polling des artefacts JSON écrits par chaque agent.
    5. Après un run réussi : proposition d'enchaîner directement
       sur validate puis integrate (chaînage automatique avec confirmations).

Choix architecturaux :
    - Pipeline lancé dans un thread de fond + polling des fichiers `0X_*.json`
      pour mettre à jour la TUI. Non-invasif (les agents ne sont pas modifiés).
    - Action "consulter runs passés" : ouvre le `04_rapport.html` du run
      sélectionné via `webbrowser.open` — pas de tentative d'intégration
      dans le terminal (le HTML produit par le Rapporteur est riche).
    - Toutes les actions retournent au menu projet après exécution, sauf
      "quitter" qui sort proprement.

Non-objectifs du Jalon 7 :
    - Pas de comparaison entre runs (Jalon 8+ s'il y a lieu).
    - Pas de batch multi-projets (un projet à la fois).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.models import ProjectModel

console = Console()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Découverte des projets et runs
# ─────────────────────────────────────────────────────────────


@dataclass
class ProjectEntry:
    """Une fiche projet listable dans le menu."""
    path: Path
    name: str  # nom_projet du ProjectModel si parsable, sinon stem du fichier
    phase: str = "?"
    derniere_maj: str = "?"
    valid: bool = True
    error: str = ""
    run_status: str = ""  # état du dernier run : "", "à valider", "à intégrer", "à jour"

    @property
    def slug(self) -> str:
        """Identifiant utilisé dans les noms de run_dir : <timestamp>_<slug>."""
        return self.path.stem


def _parse_project_safely(md_path: Path) -> ProjectEntry:
    """Tente de parser un .md. Si invalide, on garde une entrée dégradée."""
    from src.validation.structural import parse_and_validate
    try:
        md = md_path.read_text(encoding="utf-8")
        project, errors = parse_and_validate(md)
        if project is None:
            return ProjectEntry(
                path=md_path, name=md_path.stem,
                valid=False, error="; ".join(errors[:2]),
            )
        return ProjectEntry(
            path=md_path,
            name=project.nom_projet,
            phase=project.identite.phase,
            derniere_maj=str(project.identite.derniere_mise_a_jour),
            valid=True,
        )
    except Exception as exc:  # noqa: BLE001
        return ProjectEntry(
            path=md_path, name=md_path.stem,
            valid=False, error=f"{type(exc).__name__}: {exc}",
        )


def _run_status_for_project(runs_root: Path, slug: str) -> str:
    """
    Retourne une courte étiquette décrivant l'état du dernier run :
    - "à valider"   : run terminé mais 05_user_validated.json absent
    - "à intégrer"  : validations OK mais au moins un 'accept' non encore intégré
                      (détecté par comparaison dernière_maj fiche vs run)
    - "à jour"      : dernier run déjà traité
    - ""            : aucun run
    """
    runs = find_runs_for_project(runs_root, slug)
    if not runs:
        return ""
    latest = runs[0]
    suggestions_file = latest.run_dir / "04_validated_suggestions.json"
    validated_file = latest.run_dir / "05_user_validated.json"

    if not suggestions_file.exists() or latest.suggestions_count == 0:
        return "à jour"  # run sans suggestions (filtré ou cache)

    if not validated_file.exists():
        return "à valider"

    # Vérifie s'il reste des 'accept' non intégrés
    try:
        import json as _json
        data = _json.loads(validated_file.read_text(encoding="utf-8"))
        n_accepted = sum(1 for d in data if d.get("decision") == "accept")
        if n_accepted > 0:
            return "à intégrer"
    except Exception:  # noqa: BLE001
        pass
    return "à jour"


def list_projects(projects_dir: Path, runs_root: Optional[Path] = None) -> list[ProjectEntry]:
    """Liste toutes les fiches .md d'un dossier. Tri par dernière màj desc."""
    if not projects_dir.exists():
        return []
    md_files = sorted(projects_dir.glob("*.md"))
    entries = [_parse_project_safely(p) for p in md_files]
    if runs_root is not None:
        for e in entries:
            if e.valid:
                e.run_status = _run_status_for_project(runs_root, e.slug)
    # Tri : valides en premier, puis par derniere_maj desc, puis par nom
    valid_sorted = sorted(
        [e for e in entries if e.valid],
        key=lambda e: e.derniere_maj, reverse=True,
    )
    invalid = [e for e in entries if not e.valid]
    return valid_sorted + invalid


@dataclass
class RunEntry:
    """Un run passé pour un projet donné."""
    run_dir: Path
    timestamp: str  # YYYYMMDD_HHMMSS
    findings_count: int = 0
    suggestions_count: int = 0
    has_html: bool = False

    @property
    def pretty_date(self) -> str:
        try:
            dt = datetime.strptime(self.timestamp, "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.timestamp


def find_runs_for_project(runs_root: Path, slug: str) -> list[RunEntry]:
    """Trouve tous les run_dir d'un projet, triés du plus récent au plus ancien."""
    if not runs_root.exists():
        return []
    candidates = sorted(runs_root.glob(f"*_{slug}"), reverse=True)
    entries: list[RunEntry] = []
    for d in candidates:
        if not d.is_dir():
            continue
        # Extraction du timestamp : suffixe avant `_{slug}`
        name = d.name
        ts_part = name[: -(len(slug) + 1)] if name.endswith(f"_{slug}") else name
        # Compte findings / suggestions si dispos
        f_count = _count_json_items(d / "01_eclaireur_findings.json")
        s_count = _count_json_items(d / "04_validated_suggestions.json")
        entries.append(RunEntry(
            run_dir=d,
            timestamp=ts_part,
            findings_count=f_count,
            suggestions_count=s_count,
            has_html=(d / "04_rapport.html").exists(),
        ))
    return entries


def _count_json_items(p: Path) -> int:
    """Compte les items d'un JSON liste. 0 si introuvable ou erreur."""
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else 0
    except Exception:  # noqa: BLE001
        return 0


# ─────────────────────────────────────────────────────────────
# Sélection projet
# ─────────────────────────────────────────────────────────────


_RUN_STATUS_STYLE = {
    "à valider":  "[yellow]● à valider[/yellow]",
    "à intégrer": "[cyan]● à intégrer[/cyan]",
    "à jour":     "[green]✓ à jour[/green]",
    "":           "[dim]—[/dim]",
}


def _render_projects_table(entries: list[ProjectEntry]) -> Table:
    table = Table(
        title="[bold green]Projets disponibles[/bold green]",
        border_style="cyan",
    )
    table.add_column("#", style="cyan", width=4, no_wrap=True)
    table.add_column("Nom", style="bold")
    table.add_column("Phase", style="magenta")
    table.add_column("Dernière màj", style="dim")
    table.add_column("Dernier run", no_wrap=True)
    for i, e in enumerate(entries, start=1):
        if e.valid:
            status_cell = _RUN_STATUS_STYLE.get(e.run_status, e.run_status)
            table.add_row(str(i), e.name, e.phase, e.derniere_maj, status_cell)
        else:
            table.add_row(
                str(i), e.name, "-", "-",
                f"[red]invalide[/red] [dim]({e.error[:40]})[/dim]",
            )
    return table


def select_project(entries: list[ProjectEntry]) -> Optional[str]:
    """
    Affiche la liste des projets et demande une sélection.

    Returns:
        "new" → l'utilisateur veut créer une fiche
        "quit" → sortir du menu
        "<index>" → ProjectEntry index (1-based) à utiliser
        None → choix invalide (la boucle redemande)
    """
    if not entries:
        console.print(
            "[yellow]Aucune fiche projet trouvée dans ~/.applied-fox/projects/.[/yellow]"
        )
    else:
        console.print(_render_projects_table(entries))

    console.print(
        "\n[bold]Actions :[/bold] "
        "[cyan]<n>[/cyan] choisir le projet n · "
        "[cyan]n[/cyan] nouvelle fiche · "
        "[cyan]q[/cyan] quitter"
    )
    choice = Prompt.ask("→", default="q").strip().lower()
    if choice in ("q", "quit", "exit"):
        return "quit"
    if choice in ("n", "new"):
        return "new"
    if choice.isdigit() and 1 <= int(choice) <= len(entries):
        e = entries[int(choice) - 1]
        if not e.valid:
            console.print(
                f"[red]Le projet '{e.name}' est invalide, on ne peut pas l'ouvrir.[/red]"
            )
            return None
        return choice
    console.print("[red]Choix non reconnu.[/red]")
    return None


# ─────────────────────────────────────────────────────────────
# Pipeline avec barre de progression
# ─────────────────────────────────────────────────────────────


# Étapes du pipeline + artefacts qui marquent leur fin + estimations indicatives.
# Les estimations sont calibrées sur RTX 3070 + profil small (cf. eval Jalon 5).
_PIPELINE_STAGES = [
    ("Éclaireur — collecte + filtres",       "01_eclaireur_findings.json",     1080),
    ("Intégrateur — verdicts d'intégration", "02_integrateur_verdicts.json",    300),
    ("Juge — pertinence + timing",           "03_juge_verdicts.json",           150),
    ("Rapporteur — synthèse + rapport",      "04_validated_suggestions.json",    60),
]


def _run_pipeline_thread(
    project_model: ProjectModel,
    md_content: str,
    config: dict,
    run_dir: Path,
    result_holder: dict,
) -> None:
    """Lance le pipeline LangGraph dans un thread. Stocke état final dans result_holder."""
    from src.graph.pipeline import build_graph, initial_state
    try:
        graph = build_graph(project_model, config, run_dir=run_dir)
        final_state = graph.invoke(initial_state(md_content))
        result_holder["state"] = final_state
        result_holder["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline crashed in background thread")
        result_holder["status"] = "error"
        result_holder["error"] = f"{type(exc).__name__}: {exc}"


def run_pipeline_with_progress(
    project: ProjectEntry, config: dict
) -> Optional[Path]:
    """
    Lance le pipeline en thread + affiche une Rich Progress alimentée par
    le polling des artefacts JSON.

    Returns:
        Le run_dir si succès, None si échec.
    """
    from src.validation.structural import parse_and_validate

    md_content = project.path.read_text(encoding="utf-8")
    project_model, messages = parse_and_validate(md_content)
    if project_model is None:
        console.print(f"[red]Fiche invalide :[/red] {project.path.name}")
        for err in messages:
            console.print(f"  [red]x[/red] {err}")
        console.print(
            "[dim]-> Corrige via le menu : option [bold]5[/bold] (Mettre à jour la fiche)[/dim]"
        )
        return None
    elif messages:
        for w in messages:
            console.print(f"  [yellow]![/yellow] {w}")

    runs_root = Path(
        str(config.get("paths", {}).get("runs_dir", "~/.applied-fox/runs"))
    ).expanduser()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_root / f"{timestamp}_{project.slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"\n[bold green]Lancement du pipeline[/bold green] sur "
        f"[cyan]{project.name}[/cyan]"
    )
    console.print(f"[dim]Artefacts : {run_dir}[/dim]\n")

    # ── Démarrage du thread ──────────────────────────────────
    result: dict = {"status": "running"}
    th = threading.Thread(
        target=_run_pipeline_thread,
        args=(project_model, md_content, config, run_dir, result),
        daemon=True,
    )
    th.start()

    total_estimate = sum(eta for _, _, eta in _PIPELINE_STAGES)

    # ── Polling + barre de progression ───────────────────────
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}", justify="left"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("• [dim]ETA ~{task.fields[eta]}[/dim]"),
        console=console,
        transient=False,
    ) as progress:
        tasks = []
        for label, _, eta in _PIPELINE_STAGES:
            t = progress.add_task(
                label, total=eta,
                eta=_format_seconds(eta),
            )
            tasks.append(t)

        start = time.time()
        finished_artifacts: set[str] = set()

        while result["status"] == "running":
            elapsed = time.time() - start
            cumulative = 0
            for (label, artifact, eta), task_id in zip(_PIPELINE_STAGES, tasks):
                stage_path = run_dir / artifact
                if artifact in finished_artifacts:
                    progress.update(task_id, completed=eta)
                elif stage_path.exists():
                    finished_artifacts.add(artifact)
                    progress.update(task_id, completed=eta)
                    n = _count_json_items(stage_path)
                    if n > 0:
                        progress.update(
                            task_id,
                            description=f"{label} [green]✓ {n} items[/green]",
                        )
                else:
                    stage_elapsed = max(0, elapsed - cumulative)
                    completed = min(stage_elapsed, eta * 0.95)
                    progress.update(task_id, completed=completed)
                    # ETA dynamique : recalcul à partir de 10 % d'avancement
                    if stage_elapsed > eta * 0.1 and stage_elapsed > 5:
                        speed = stage_elapsed / max(completed, 1)
                        remaining = max(0, (eta - completed) * speed)
                        progress.update(task_id, eta=_format_seconds(int(remaining)))
                    cumulative += eta
                    break
                cumulative += eta

            time.sleep(0.5)

        # Finalisation : marque toutes les étapes terminées si OK
        if result["status"] == "ok":
            for (label, artifact, eta), task_id in zip(_PIPELINE_STAGES, tasks):
                progress.update(task_id, completed=eta)

    th.join(timeout=2)

    # ── Résultat ─────────────────────────────────────────────
    if result["status"] != "ok":
        console.print(
            f"\n[red]Pipeline en erreur :[/red] {result.get('error', 'inconnue')}"
        )
        return None

    final_state = result["state"]
    findings = final_state.get("findings", [])
    verdicts = final_state.get("integration_verdicts", {})
    judge_verdicts = final_state.get("judge_verdicts", {})
    suggestions = final_state.get("validated_suggestions", [])

    console.print()
    console.print(
        Panel.fit(
            f"[green]✓ Veille terminée[/green]\n\n"
            f"Findings collectés    : [cyan]{len(findings)}[/cyan]\n"
            f"Verdicts Intégrateur : [cyan]{len(verdicts)}[/cyan]\n"
            f"Verdicts Juge         : [cyan]{len(judge_verdicts)}[/cyan]\n"
            f"[bold]Suggestions finales : [green]{len(suggestions)}[/green][/bold]\n\n"
            f"[dim]Rapport HTML : {run_dir / '04_rapport.html'}[/dim]",
            border_style="green",
            title="[bold]Résultat[/bold]",
        )
    )
    return run_dir


def _format_seconds(s: int) -> str:
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}min{sec:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}min"


# ─────────────────────────────────────────────────────────────
# Consultation des runs passés
# ─────────────────────────────────────────────────────────────


def view_past_runs(project: ProjectEntry, runs_root: Path) -> None:
    """Liste les runs passés du projet, propose d'ouvrir le rapport HTML."""
    runs = find_runs_for_project(runs_root, project.slug)
    if not runs:
        console.print(f"[yellow]Aucun run passé pour '{project.name}'.[/yellow]")
        return

    table = Table(
        title=f"[bold]Runs passés — {project.name}[/bold]",
        border_style="cyan",
    )
    table.add_column("#", style="cyan", width=4)
    table.add_column("Date", style="bold")
    table.add_column("Findings", justify="right")
    table.add_column("Suggestions", justify="right")
    table.add_column("Rapport", style="dim")
    for i, r in enumerate(runs, start=1):
        table.add_row(
            str(i), r.pretty_date,
            str(r.findings_count), str(r.suggestions_count),
            "[green]HTML[/green]" if r.has_html else "[dim]md only[/dim]",
        )
    console.print()
    console.print(table)

    console.print(
        "\n[bold]Actions :[/bold] "
        "[cyan]<n>[/cyan] ouvrir le rapport du run n · "
        "[cyan]r[/cyan] retour"
    )
    while True:
        choice = Prompt.ask("→", default="r").strip().lower()
        if choice in ("r", "retour", "", "back"):
            return
        if choice.isdigit() and 1 <= int(choice) <= len(runs):
            run = runs[int(choice) - 1]
            html = run.run_dir / "04_rapport.html"
            md = run.run_dir / "04_rapport.md"
            target = html if html.exists() else md
            if not target.exists():
                console.print("[yellow]Aucun rapport disponible dans ce run.[/yellow]")
                continue
            try:
                webbrowser.open(target.as_uri())
                console.print(f"[green]Ouvert :[/green] {target}")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Échec de l'ouverture :[/red] {exc}")
                console.print(f"[dim]Chemin direct : {target}[/dim]")
            return
        console.print("[red]Choix non reconnu.[/red]")


# ─────────────────────────────────────────────────────────────
# Actions composites : validate + integrate
# ─────────────────────────────────────────────────────────────


def _action_validate(project: ProjectEntry, run_dir: Path) -> Optional[Path]:
    """Lance la TUI de validation sur le run donné. Retourne le path de
    `05_user_validated.json` si écrit, None sinon."""
    from src.validation.tui import (
        load_suggestions, save_decisions, validate_suggestions_tui,
    )
    suggestions_path = run_dir / "04_validated_suggestions.json"
    if not suggestions_path.exists():
        console.print(
            f"[yellow]Pas de suggestions à valider dans ce run "
            f"({suggestions_path.name} manquant).[/yellow]"
        )
        return None
    suggestions = load_suggestions(suggestions_path)
    report_path = run_dir / "04_rapport.html"
    if not report_path.exists():
        report_path = None
    decisions = validate_suggestions_tui(suggestions, report_path=report_path)
    if decisions is None:
        return None
    out = run_dir / "05_user_validated.json"
    save_decisions(decisions, out)
    return out


def _action_integrate(project: ProjectEntry, validated_path: Path, config: dict) -> None:
    """Applique en lot les suggestions acceptées."""
    from src.agents.interviewer import run_integrate_batch
    from src.validation.tui import load_decisions
    decisions = load_decisions(validated_path)
    accepted = [d.suggestion for d in decisions if d.decision == "accept"]
    if not accepted:
        console.print("[yellow]Aucune suggestion acceptée — rien à intégrer.[/yellow]")
        return
    run_integrate_batch(project.path, accepted, config)


def _action_run_chain(project: ProjectEntry, config: dict) -> None:
    """Chaînage automatique : run → validate → integrate (avec confirmations)."""
    run_dir = run_pipeline_with_progress(project, config)
    if run_dir is None:
        return

    if not Confirm.ask(
        "\n[bold]Valider les suggestions maintenant ?[/bold]",
        default=True,
    ):
        return
    validated = _action_validate(project, run_dir)
    if validated is None:
        return

    if not Confirm.ask(
        "\n[bold]Intégrer les suggestions acceptées dans la fiche projet ?[/bold]",
        default=True,
    ):
        return
    _action_integrate(project, validated, config)


def _action_validate_latest(project: ProjectEntry, runs_root: Path) -> None:
    runs = find_runs_for_project(runs_root, project.slug)
    if not runs:
        console.print("[yellow]Pas de run à valider — lance d'abord une veille.[/yellow]")
        return
    latest = runs[0]
    console.print(f"[dim]Run sélectionné : {latest.pretty_date}[/dim]")
    _action_validate(project, latest.run_dir)


def _action_integrate_latest(project: ProjectEntry, runs_root: Path, config: dict) -> None:
    runs = find_runs_for_project(runs_root, project.slug)
    if not runs:
        console.print("[yellow]Pas de run dont intégrer les suggestions.[/yellow]")
        return
    latest = runs[0]
    validated = latest.run_dir / "05_user_validated.json"
    if not validated.exists():
        console.print(
            f"[yellow]Pas de décisions de validation pour le run du "
            f"{latest.pretty_date} — passe d'abord par 'valider'.[/yellow]"
        )
        return
    _action_integrate(project, validated, config)


def _action_update(project: ProjectEntry, config: dict) -> None:
    from src.agents.interviewer import run_update
    try:
        run_update(project.path, config)
    except SystemExit:
        # run_update fait sys.exit(0) si l'utilisateur abandonne — ce n'est pas
        # une erreur dans le contexte d'un menu, on revient juste à l'accueil.
        pass


# ─────────────────────────────────────────────────────────────
# Menu d'actions sur un projet
# ─────────────────────────────────────────────────────────────


def _render_action_menu(project: ProjectEntry, runs_root: Path) -> None:
    runs = find_runs_for_project(runs_root, project.slug)
    last = runs[0].pretty_date if runs else "aucun"
    console.print()
    console.print(
        Panel.fit(
            f"[bold]{project.name}[/bold] "
            f"[dim]({project.phase} · màj {project.derniere_maj} · "
            f"{len(runs)} run(s), dernier : {last})[/dim]",
            border_style="green",
        )
    )
    console.print("[bold]Que veux-tu faire ?[/bold]")
    console.print("  [cyan]1[/cyan]. Lancer un nouveau run (puis valider + intégrer)")
    console.print("  [cyan]2[/cyan]. Consulter les runs passés")
    console.print("  [cyan]3[/cyan]. Valider les suggestions du dernier run")
    console.print("  [cyan]4[/cyan]. Intégrer les acceptées du dernier run")
    console.print("  [cyan]5[/cyan]. Mettre à jour la fiche manuellement")
    console.print("  [cyan]r[/cyan]. Retour à la liste des projets")


def project_action_loop(project: ProjectEntry, runs_root: Path, config: dict) -> None:
    while True:
        _render_action_menu(project, runs_root)
        choice = Prompt.ask(
            "→",
            choices=["1", "2", "3", "4", "5", "r"],
            default="r",
        ).strip().lower()
        if choice == "r":
            return
        if choice == "1":
            _action_run_chain(project, config)
        elif choice == "2":
            view_past_runs(project, runs_root)
        elif choice == "3":
            _action_validate_latest(project, runs_root)
        elif choice == "4":
            _action_integrate_latest(project, runs_root, config)
        elif choice == "5":
            _action_update(project, config)


# ─────────────────────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────────────────────


def run_menu(config: dict) -> None:
    """Boucle principale du menu interactif."""
    paths_cfg = config.get("paths", {})
    projects_dir = Path(
        str(paths_cfg.get("projects_dir", "~/.applied-fox/projects"))
    ).expanduser()
    runs_root = Path(
        str(paths_cfg.get("runs_dir", "~/.applied-fox/runs"))
    ).expanduser()

    # Premier lancement : crée les dossiers attendus pour éviter "FileNotFoundError"
    # quand l'utilisateur choisit "nouvelle fiche" alors que la maison est vide.
    try:
        projects_dir.mkdir(parents=True, exist_ok=True)
        runs_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Si on ne peut pas créer (droits, disque plein), on n'arrête pas le menu —
        # on continuera avec 0 projet, l'utilisateur verra le warning.
        logger.warning("Impossible de créer les dossiers de travail : %s", exc)

    console.print()
    console.print(
        Panel.fit(
            "[bold green]Applied Fox[/bold green] — veille technologique multi-agent",
            border_style="green",
        )
    )

    while True:
        entries = list_projects(projects_dir, runs_root=runs_root)
        choice = select_project(entries)
        if choice is None:
            continue
        if choice == "quit":
            console.print("\n[dim]À bientôt.[/dim]")
            return
        if choice == "new":
            from src.agents import interviewer
            try:
                interviewer.run_create(projects_dir, config)
            except SystemExit:
                pass
            continue

        # Index numérique
        entry = entries[int(choice) - 1]
        project_action_loop(entry, runs_root, config)
