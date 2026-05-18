"""
Point d'entrée CLI — commande `applied-fox`.

Sous-commandes disponibles au MVP :
    applied-fox run --project <path>       Lance la veille sur un projet.
    applied-fox interview create           Crée une nouvelle fiche projet.
    applied-fox interview update --project Lance la mise à jour d'une fiche existante.

La commande `applied-fox` sans argument ouvre le menu interactif TUI Rich
qui scanne ~/.applied-fox/projects/ et liste les projets disponibles (Jalon 7).

Typer est utilisé pour la CLI. C'est une bibliothèque moderne basée sur Click
qui exploite les type hints Python — pas besoin de décrire chaque argument manuellement.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

# Chargement automatique d'un éventuel `.env` à la racine du projet.
# Permet aux variables d'env (GITHUB_TOKEN, REDDIT_CLIENT_ID, etc.) d'être lues
# sans configuration système. Sans effet si le fichier .env n'existe pas.
# `override=False` : les variables système existantes prévalent sur le .env.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass  # python-dotenv non installé → on continue avec les vars système seules

console = Console()
app = typer.Typer(
    name="applied-fox",
    help="Veille technologique multi-agent, 100 % locale.",
    add_completion=False,
)

# Sous-groupe pour les commandes 'interview'
interview_app = typer.Typer(help="Gestion des fiches projet (.md).")
app.add_typer(interview_app, name="interview")

# Sous-groupe pour les commandes 'models' (hot-swap LLM par rôle)
models_app = typer.Typer(help="Inspecter et changer les modèles LLM par rôle.")
app.add_typer(models_app, name="models")


# ─────────────────────────────────────────────────────────────
# Commande : applied-fox run
# ─────────────────────────────────────────────────────────────

@app.command()
def run(
    project: Path = typer.Option(
        ...,
        "--project", "-p",
        help="Chemin vers la fiche projet .md.",
        exists=True,
        readable=True,
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
        help="Chemin vers config.yaml (défaut : ~/.applied-fox/config.yaml).",
    ),
) -> None:
    """Lance le pipeline de veille pour un projet (Jalon 3 : Éclaireur seul)."""
    import json
    import logging
    from datetime import datetime

    import yaml

    from src.graph.pipeline import build_graph, initial_state
    from src.validation.structural import parse_and_validate

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    console.print(
        f"[bold green]Applied Fox[/bold green] — veille sur [cyan]{project.name}[/cyan]"
    )

    # ── Charger la config ─────────────────────────────────────
    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        console.print(
            f"[yellow]Config non trouvée ({config_path}), paramètres par défaut.[/yellow]"
        )

    # ── Charger et valider la fiche projet ────────────────────
    md_content = project.read_text(encoding="utf-8")
    project_model, messages = parse_and_validate(md_content)
    if project_model is None:
        console.print(f"[red]Fiche invalide : {project.name}[/red]")
        for err in messages:
            console.print(f"  [red]x[/red] {err}")
    elif messages:
        # Fiche valide mais des lignes ont été ignorées (ex. interactions mal formatées)
        for w in messages:
            console.print(f"  [yellow]![/yellow] {w}")
    if project_model is None:
        console.print(
            f"\n[dim]Pour corriger la fiche :[/dim]\n"
            f"[cyan]applied-fox interview update --project {project}[/cyan]"
        )
        raise typer.Exit(code=1)

    # ── Préparer le run dir ───────────────────────────────────
    runs_root = Path(
        str(config.get("paths", {}).get("runs_dir", "~/.applied-fox/runs"))
    ).expanduser()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_slug = project.stem
    run_dir = runs_root / f"{timestamp}_{project_slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[dim]Artefacts dans : {run_dir}[/dim]")

    # ── Lancer le graphe ──────────────────────────────────────
    graph = build_graph(project_model, config, run_dir=run_dir)
    final_state = graph.invoke(initial_state(md_content))

    findings = final_state.get("findings", [])
    verdicts = final_state.get("integration_verdicts", {})
    judge_verdicts = final_state.get("judge_verdicts", {})
    suggestions = final_state.get("validated_suggestions", [])
    errors = final_state.get("errors", [])

    console.print(
        f"\n[bold green]Veille terminée :[/bold green] "
        f"[cyan]{len(findings)}[/cyan] findings · "
        f"[cyan]{len(verdicts)}[/cyan] verdicts intégration · "
        f"[cyan]{len(judge_verdicts)}[/cyan] verdicts juge · "
        f"[bold cyan]{len(suggestions)}[/bold cyan] suggestions finales."
    )
    if errors:
        console.print("[yellow]Erreurs non fatales :[/yellow]")
        for e in errors:
            console.print(f"  - {e}")

    # ── Récap Intégrateur — distribution effort + confiance ─────
    if verdicts:
        from collections import Counter
        eff = Counter(v.effort_level for v in verdicts.values())
        conf = Counter(v.confidence for v in verdicts.values())
        integrable_count = sum(1 for v in verdicts.values() if v.integrable)
        console.print(
            f"\n[bold]Intégrateur :[/bold] "
            f"[cyan]{integrable_count}[/cyan] intégrables sur {len(verdicts)}"
        )
        console.print(
            f"  Effort : "
            + " | ".join(f"{k}={eff[k]}" for k in
                ["trivial", "minor", "moderate", "major", "blocking"] if eff[k])
        )
        console.print(
            f"  Confiance : "
            + " | ".join(f"{k}={conf[k]}" for k in ["high", "medium", "low"] if conf[k])
        )

    # ── Récap Juge — priorisation finale ─────────────────────────
    if judge_verdicts:
        from collections import Counter
        rel = Counter(v.relevance for v in judge_verdicts.values())
        tim = Counter(v.timing_recommendation for v in judge_verdicts.values())
        console.print(
            f"\n[bold]Juge :[/bold] "
            + " | ".join(f"{k}={rel[k]}" for k in ["high", "medium", "low", "reject"] if rel[k])
        )
        console.print(
            f"  Timing : "
            + " | ".join(f"{k}={tim[k]}" for k in
                ["now", "next_iteration", "noted_for_future", "reject"] if tim[k])
        )

        # Top suggestions pour l'utilisateur : relevance high/medium + timing now
        rel_order = {"high": 0, "medium": 1, "low": 2, "reject": 3}
        tim_order = {"now": 0, "next_iteration": 1, "noted_for_future": 2, "reject": 3}
        top = sorted(
            (v for v in judge_verdicts.values()
             if v.relevance in ("high", "medium") and v.timing_recommendation == "now"),
            key=lambda v: (rel_order[v.relevance], tim_order[v.timing_recommendation]),
        )[:5]
        if top:
            console.print("\n[bold green]À considérer maintenant (top 5) :[/bold green]")
            findings_by_id = {f.id: f for f in findings}
            for v in top:
                f = findings_by_id.get(v.finding_id)
                title = f.title if f else v.finding_id
                console.print(
                    f"  [{v.relevance}] [cyan]{f.component_concerned if f else '?'}[/cyan] — "
                    f"{title[:60]}"
                )
                console.print(f"    [dim]-> {v.real_gain_summary[:130]}[/dim]")
        else:
            console.print(
                "\n[yellow]Aucun finding 'high/medium . now' — "
                "consulte 03_juge_reasoning.md pour le detail.[/yellow]"
            )
    elif findings:
        # Fallback si l'Intégrateur a échoué — au moins montrer les findings bruts.
        console.print("\n[bold]Aperçu findings (5 premiers) :[/bold]")
        for f in findings[:5]:
            console.print(
                f"  [cyan]{f.angle}[/cyan] "
                f"[dim]{f.component_concerned}[/dim] — {f.title[:80]}"
            )

    # ── Chemin du rapport final ──────────────────────────────────
    html_report = run_dir / "04_rapport.html"
    md_report = run_dir / "04_rapport.md"
    if html_report.exists():
        console.print(
            f"\n[bold green]Rapport HTML :[/bold green] [cyan]{html_report}[/cyan]"
        )
        console.print(
            f"[dim]Ouvre-le dans ton navigateur, ou regarde la version Markdown : "
            f"{md_report.name}[/dim]"
        )
    elif md_report.exists():
        console.print(
            f"\n[bold green]Rapport Markdown :[/bold green] [cyan]{md_report}[/cyan]"
        )

    raise typer.Exit(code=0)


# ─────────────────────────────────────────────────────────────
# Commandes : applied-fox interview create / update
# ─────────────────────────────────────────────────────────────

@interview_app.command("create")
def interview_create(
    output_dir: Path = typer.Option(
        Path.home() / ".applied-fox" / "projects",
        "--output", "-o",
        help="Dossier où sauvegarder la fiche .md produite.",
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
        help="Chemin vers config.yaml.",
    ),
) -> None:
    """Lance le questionnaire guidé pour créer une nouvelle fiche projet .md."""
    import yaml
    from src.agents import interviewer

    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        console.print(
            f"[yellow]Config non trouvée ({config_path}), paramètres par défaut utilisés.[/yellow]"
        )

    interviewer.run_create(output_dir, config)
    raise typer.Exit(code=0)


@interview_app.command("skeleton")
def interview_skeleton(
    output_dir: Path = typer.Option(
        Path.home() / ".applied-fox" / "projects",
        "--output", "-o",
        help="Dossier où sauvegarder la fiche .md générée.",
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
        help="Chemin vers config.yaml.",
    ),
) -> None:
    """Génère un squelette .md pré-structuré à remplir dans ton éditeur."""
    import yaml
    from src.interview.skeleton import run_skeleton

    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    run_skeleton(output_dir, config)
    raise typer.Exit(code=0)


@interview_app.command("update")
def interview_update(
    project: Path = typer.Option(
        ...,
        "--project", "-p",
        help="Chemin vers la fiche .md à mettre à jour.",
        exists=True,
        readable=True,
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
        help="Chemin vers config.yaml.",
    ),
) -> None:
    """Met à jour une fiche projet .md existante via dialogue."""
    import yaml
    from src.agents import interviewer

    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        console.print(
            f"[yellow]Config non trouvée ({config_path}), paramètres par défaut utilisés.[/yellow]"
        )

    console.print(
        f"[bold green]Interview — mode update[/bold green] sur [cyan]{project.name}[/cyan]"
    )
    interviewer.run_update(project, config)
    raise typer.Exit(code=0)


# ─────────────────────────────────────────────────────────────
# Commandes : applied-fox models (hot-swap LLM par rôle)
# ─────────────────────────────────────────────────────────────

@models_app.command("list")
def models_list(
    role: str = typer.Argument(
        None,
        help="Filtre par rôle : interviewer | integrateur | juge | rapporteur. "
             "Si absent, liste tous les rôles.",
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
    ),
) -> None:
    """Liste les modèles testés et le modèle actuellement configuré par rôle."""
    import yaml
    from rich.table import Table
    from src.llm import _DEFAULT_MODELS, _TESTED_MODELS, _VALID_ROLES

    cfg: dict = {}
    if config_path.exists():
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    models_cfg = cfg.get("ollama", {}).get("models", {})

    roles = [role] if role else sorted(r for r in _VALID_ROLES if r != "eclaireur")
    for r in roles:
        if r not in _VALID_ROLES:
            console.print(f"[red]Rôle inconnu : {r}[/red]")
            raise typer.Exit(code=1)

        current = models_cfg.get(r, _DEFAULT_MODELS[r])
        default = _DEFAULT_MODELS[r]

        table = Table(
            title=f"[bold]Modèles pour rôle [cyan]{r}[/cyan][/bold]",
            border_style="cyan",
            show_lines=False,
        )
        table.add_column("Statut", style="bold", width=12)
        table.add_column("Modèle Ollama", style="white")
        table.add_column("Commentaire", style="dim")

        tested = _TESTED_MODELS.get(r, {})
        for model, verdict in tested.items():
            is_current = model == current
            marker = "▶ ACTUEL" if is_current else ("✓ tested" if verdict == "tested" else "✗ rejected")
            color = "green" if verdict == "tested" else "red"
            if is_current:
                color = "yellow"
            table.add_row(
                f"[{color}]{marker}[/{color}]",
                model + (f"  [dim](défaut)[/dim]" if model == default else ""),
                verdict if verdict != "tested" else "",
            )

        # Modèle actuel s'il n'est pas dans le registre testé
        if current not in tested:
            table.add_row(
                "[yellow]▶ ACTUEL[/yellow]",
                current,
                "[yellow]non testé — qualité non garantie[/yellow]",
            )

        console.print(table)
        console.print()

    console.print(
        "[dim]Pour changer un modèle : "
        "[cyan]applied-fox models set <rôle> <modèle>[/cyan][/dim]"
    )
    raise typer.Exit(code=0)


@models_app.command("set")
def models_set(
    role: str = typer.Argument(..., help="Rôle : integrateur | juge | rapporteur"),
    model: str = typer.Argument(..., help="Tag Ollama, ex: qwen3:14b ou mistral:7b-instruct-q4_K_M"),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Force même si le modèle est dans la liste 'rejected'.",
    ),
) -> None:
    """
    Change le modèle LLM utilisé pour un rôle donné.

    L'interviewer ne peut pas être modifié (hardcodé en local 7B Q4 par
    contrainte CLAUDE.md règle 3 — tout en local par défaut au MVP).

    Si tu choisis un modèle non testé, un warning sera émis à chaque appel.
    Pour ré-évaluer un modèle, utiliser scripts/eval_juge.py.
    """
    import yaml
    from src.llm import _VALID_ROLES, is_tested

    if role == "interviewer":
        console.print(
            "[red]L'interviewer ne peut pas être modifié.[/red]\n"
            "Contrainte CLAUDE.md règle 3 : tout en local 7B Q4 par défaut au MVP."
        )
        raise typer.Exit(code=1)
    if role not in _VALID_ROLES:
        console.print(
            f"[red]Rôle inconnu : {role}[/red]\n"
            f"Rôles valides : {sorted(r for r in _VALID_ROLES if r != 'interviewer')}"
        )
        raise typer.Exit(code=1)

    # Lecture / création de la config
    cfg: dict = {}
    if config_path.exists():
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("ollama", {}).setdefault("models", {})

    # Check si le modèle est rejected
    ok, verdict = is_tested(role, model)
    if not ok and verdict.startswith("rejected") and not force:
        console.print(
            f"[red]Modèle '{model}' a été testé et REJETÉ pour le rôle '{role}' :[/red]\n"
            f"  → {verdict[len('rejected:'):].strip()}\n\n"
            f"Pour forcer quand même : [cyan]--force[/cyan]"
        )
        raise typer.Exit(code=1)
    if not ok and not verdict.startswith("rejected"):
        console.print(
            f"[yellow]⚠ Modèle '{model}' non testé pour le rôle '{role}'.[/yellow]\n"
            f"  Risque de qualité dégradée. Voir docs/HARDWARE.md pour le protocole "
            f"de ré-évaluation.\n"
        )

    # Sauvegarde
    previous = cfg["ollama"]["models"].get(role, "(défaut)")
    cfg["ollama"]["models"][role] = model
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

    console.print(
        f"[green]✓[/green] Rôle [cyan]{role}[/cyan] : "
        f"[dim]{previous}[/dim] → [bold]{model}[/bold]\n"
        f"[dim]Config mise à jour : {config_path}[/dim]"
    )
    if not ok and not verdict.startswith("rejected"):
        console.print(
            f"\n[dim]N'oublie pas : "
            f"[cyan]ollama pull {model}[/cyan] avant de lancer la veille.[/dim]"
        )
    raise typer.Exit(code=0)


@models_app.command("reset")
def models_reset(
    role: str = typer.Argument(
        None,
        help="Rôle à réinitialiser, ou rien pour tous les rôles.",
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
    ),
) -> None:
    """Réinitialise les modèles aux valeurs par défaut testées."""
    import yaml
    from src.llm import _DEFAULT_MODELS, _VALID_ROLES

    cfg: dict = {}
    if config_path.exists():
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    models_cfg = cfg.setdefault("ollama", {}).setdefault("models", {})

    if role:
        if role not in _VALID_ROLES or role == "interviewer":
            console.print(f"[red]Rôle invalide : {role}[/red]")
            raise typer.Exit(code=1)
        models_cfg.pop(role, None)
        console.print(f"[green]✓[/green] Rôle [cyan]{role}[/cyan] réinitialisé à : "
                      f"[bold]{_DEFAULT_MODELS[role]}[/bold]")
    else:
        # Reset all (sauf interviewer qui est hardcodé)
        for r in _VALID_ROLES:
            models_cfg.pop(r, None)
        console.print(
            f"[green]✓[/green] Tous les modèles réinitialisés aux défauts testés."
        )

    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    raise typer.Exit(code=0)


# ─────────────────────────────────────────────────────────────
# Commande : applied-fox validate (Jalon 6)
# ─────────────────────────────────────────────────────────────

@app.command()
def validate(
    run_dir: Path = typer.Option(
        ...,
        "--run", "-r",
        help="Dossier du run dont les suggestions doivent être validées "
             "(contient 04_validated_suggestions.json).",
        exists=True,
        readable=True,
        file_okay=False,
    ),
) -> None:
    """
    Lance la TUI Rich de validation des suggestions produites par un run.

    Lit `<run_dir>/04_validated_suggestions.json`, ouvre la TUI, écrit
    `<run_dir>/05_user_validated.json` avec les décisions accept/reject/defer.
    """
    from src.validation.tui import (
        load_suggestions,
        save_decisions,
        validate_suggestions_tui,
    )

    suggestions_path = run_dir / "04_validated_suggestions.json"
    if not suggestions_path.exists():
        console.print(
            f"[red]Fichier introuvable : {suggestions_path}[/red]\n"
            "[yellow]Lance d'abord `applied-fox run` pour produire les suggestions.[/yellow]"
        )
        raise typer.Exit(code=1)

    suggestions = load_suggestions(suggestions_path)
    console.print(
        f"[bold green]Applied Fox[/bold green] — "
        f"validation de [cyan]{len(suggestions)}[/cyan] suggestion(s)"
    )

    report_path = run_dir / "04_rapport.html"
    decisions = validate_suggestions_tui(
        suggestions,
        report_path=report_path if report_path.exists() else None,
    )
    if decisions is None:
        console.print("[yellow]Validation annulée.[/yellow]")
        raise typer.Exit(code=0)

    output_path = run_dir / "05_user_validated.json"
    save_decisions(decisions, output_path)

    n_accept = sum(1 for d in decisions if d.decision == "accept")
    console.print(
        f"\n[bold green]Décisions sauvegardées :[/bold green] {output_path}"
    )
    if n_accept > 0:
        console.print(
            f"\n[dim]Étape suivante : applique les {n_accept} suggestion(s) "
            f"acceptée(s) à la fiche projet :[/dim]\n"
            f"[cyan]applied-fox interview integrate "
            f"--project <ta_fiche.md> --validated {output_path}[/cyan]"
        )
    else:
        console.print("[yellow]Aucune suggestion acceptée — rien à intégrer.[/yellow]")

    raise typer.Exit(code=0)


# ─────────────────────────────────────────────────────────────
# Commande : applied-fox interview integrate (Jalon 6)
# ─────────────────────────────────────────────────────────────

@interview_app.command("integrate")
def interview_integrate(
    project: Path = typer.Option(
        ...,
        "--project", "-p",
        help="Chemin vers la fiche .md à modifier.",
        exists=True,
        readable=True,
    ),
    validated: Path = typer.Option(
        ...,
        "--validated", "-v",
        help="Chemin vers 05_user_validated.json produit par `applied-fox validate`.",
        exists=True,
        readable=True,
    ),
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
        help="Chemin vers config.yaml.",
    ),
) -> None:
    """
    Applique en lot les suggestions ACCEPTÉES à la fiche projet.

    Lit `05_user_validated.json`, filtre les suggestions `decision == "accept"`,
    et appelle l'Interviewer en mode integrate pour chacune (dialogue
    open_questions + 3 couches de validation par suggestion).
    """
    import yaml

    from src.agents.interviewer import run_integrate_batch
    from src.validation.tui import load_decisions

    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    decisions = load_decisions(validated)
    accepted = [d.suggestion for d in decisions if d.decision == "accept"]

    if not accepted:
        console.print(
            "[yellow]Aucune suggestion acceptée dans le fichier de décisions.[/yellow]"
        )
        raise typer.Exit(code=0)

    console.print(
        f"[bold green]Applied Fox[/bold green] — intégration de "
        f"[cyan]{len(accepted)}[/cyan] suggestion(s) dans "
        f"[cyan]{project.name}[/cyan]"
    )

    n_applied, n_skipped, n_failed = run_integrate_batch(project, accepted, config)

    if n_failed > 0:
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


# ─────────────────────────────────────────────────────────────
# Commande principale sans argument → menu interactif (Jalon 7)
# ─────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    config_path: Path = typer.Option(
        Path.home() / ".applied-fox" / "config.yaml",
        "--config", "-c",
        help="Chemin vers config.yaml (utilisé par le menu interactif).",
    ),
) -> None:
    """
    Sans sous-commande, ouvre le menu interactif multi-projets (Jalon 7).
    Scanne ~/.applied-fox/projects/, propose run / validate / integrate / update.
    """
    if ctx.invoked_subcommand is not None:
        return

    import yaml
    from src.menu import run_menu

    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    try:
        run_menu(config)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrompu.[/dim]")
        raise typer.Exit(code=0)
