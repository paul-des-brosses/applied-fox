"""
Module integrate — application d'un ValidatedSuggestion sur un .md projet.

Le mode `integrate` est appelé depuis le pipeline de veille (Jalon 6) :
le Rapporteur a produit un objet ValidatedSuggestion (voir src/models.py),
l'utilisateur l'a validé, et on doit l'appliquer sur la fiche projet.

Pour Jalon 2, on implémente la logique principale et on la teste avec un
ValidatedSuggestion construit à la main. Au Jalon 6, ce module sera invoqué
automatiquement par la boucle rapport → validation → modification.

Processus :
    1. Affichage de la suggestion à l'utilisateur (récap clair).
    2. Dialogue sur les open_questions (si présentes).
    3. Application des changements au dict data :
       - new_components → ajout dans data["composants"]
       - components_affected → marqués comme à revoir (statut "en évaluation")
       - interactions_changes → ajout / suppression de relations
       - constraints_impact → ajout dans la sous-section "Impacts veille"
    4. Append à la section Changements (résumé : suggestion.title).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from src.interview.create import _SECTION_GUIDES, _ask_with_enrichment
from src.interview.update import existing_changements_to_list, project_to_data
from src.models import ProjectModel, ValidatedSuggestion

console = Console()


def _show_suggestion(suggestion: ValidatedSuggestion) -> None:
    """Affiche un récap clair de la suggestion à appliquer."""
    console.print()
    console.print(
        Panel.fit(
            f"[bold]{suggestion.title}[/bold]\n\n"
            f"{suggestion.changes_summary}",
            border_style="cyan",
            title="[bold green]Suggestion à intégrer[/bold green]",
        )
    )

    if suggestion.components_affected:
        console.print(
            f"\n[bold]Composants impactés :[/bold] "
            f"{', '.join(suggestion.components_affected)}"
        )
    if suggestion.new_components:
        console.print(f"[bold]Nouveaux composants proposés :[/bold] {len(suggestion.new_components)}")
        for nc in suggestion.new_components:
            console.print(f"  • {nc.get('nom', '?')} — {nc.get('role', '?')}")
    if suggestion.interactions_changes:
        console.print(f"[bold]Changements d'interactions :[/bold]")
        for ic in suggestion.interactions_changes:
            console.print(f"  • {ic}")
    if suggestion.constraints_impact:
        console.print(f"[bold]Impact contraintes :[/bold] {suggestion.constraints_impact}")
    if suggestion.integration_notes:
        console.print(f"\n[italic]Note d'intégration :[/italic] {suggestion.integration_notes}")


def _resolve_open_questions(
    suggestion: ValidatedSuggestion, project_name: str, llm
) -> dict[str, str]:
    """Pose chaque open_question à l'utilisateur. Retourne un dict {question: réponse}."""
    if not suggestion.open_questions:
        return {}

    console.print()
    console.print(
        f"[bold yellow]Cette suggestion soulève {len(suggestion.open_questions)} "
        f"question(s) à clarifier :[/bold yellow]"
    )
    answers: dict[str, str] = {}
    for q in suggestion.open_questions:
        ans = _ask_with_enrichment(
            llm,
            project_name,
            section="Réponse à open_question",
            question=q,
            expectations=(
                "Réponse concrète : un choix arbitré, un chiffre, un nom technique, "
                "ou 'TBD : raison'."
            ),
        )
        answers[q] = ans
    return answers


def _apply_suggestion_to_data(
    data: dict, suggestion: ValidatedSuggestion, answers: dict[str, str]
) -> list[str]:
    """
    Applique la suggestion au dict data en place. Retourne la liste des changements
    pour le log Changements.
    """
    changes: list[str] = []

    # Nouveaux composants
    for nc in suggestion.new_components:
        nom = nc.get("nom", "Composant inconnu")
        role = nc.get("role", "rôle non spécifié")
        statut = nc.get("statut_decisionnel", "en évaluation")
        role_pipeline = nc.get("role_pipeline", "support")
        data["composants"].append(
            {
                "nom": nom,
                "role": role,
                "statut_decisionnel": statut,
                "role_pipeline": role_pipeline,
            }
        )
        changes.append(f"Ajout composant (suggestion '{suggestion.title[:40]}') : {nom}")

    # Composants affectés → on bascule leur statut à "en évaluation"
    if suggestion.components_affected:
        for c in data["composants"]:
            if c["nom"] in suggestion.components_affected:
                if c["statut_decisionnel"] != "en évaluation":
                    old = c["statut_decisionnel"]
                    c["statut_decisionnel"] = "en évaluation"
                    changes.append(
                        f"Composant {c['nom']} : statut {old} → en évaluation "
                        f"(suite à suggestion '{suggestion.title[:40]}')"
                    )

    # Changements d'interactions — pour Jalon 2, on les note dans le log
    # (l'application précise sera affinée au Jalon 6 avec un format normalisé)
    for ic in suggestion.interactions_changes:
        changes.append(f"Interaction à revoir : {ic[:80]}")

    # Impact contraintes : on ajoute une sous-section "Impacts veille" si non existante
    if suggestion.constraints_impact:
        impact_section = next(
            (s for s in data["contraintes"] if s["titre"] == "Impacts veille"), None
        )
        if impact_section is None:
            impact_section = {"titre": "Impacts veille", "criteres": []}
            data["contraintes"].append(impact_section)
        for k, v in suggestion.constraints_impact.items():
            impact_section["criteres"].append(
                {"nom": f"{suggestion.title[:30]} — {k}", "valeur": str(v)[:200]}
            )
            changes.append(f"Impact contrainte : {k} = {str(v)[:60]}")

    # Réponses aux open_questions → ajoutées dans les Changements pour traçabilité
    for q, a in answers.items():
        changes.append(f"Q&R : {q[:60]} → {a[:60]}")

    return changes


def apply_suggestion(
    project: ProjectModel, suggestion: ValidatedSuggestion, config: dict
) -> Optional[tuple[dict, list[dict], list[str]]]:
    """
    Applique un ValidatedSuggestion sur un ProjectModel.

    Args:
        project:    ProjectModel chargé depuis le .md existant.
        suggestion: ValidatedSuggestion à appliquer.
        config:     Config globale (pour get_llm).

    Returns:
        Tuple (data, changements_complets, changements_resumes) si l'utilisateur
        a confirmé l'application. None si annulé.
    """
    from src.llm import get_llm

    llm = None
    try:
        llm = get_llm("interviewer", config)
        from langchain_core.messages import HumanMessage as _HM
        _ = llm.invoke([_HM(content="Réponds OK.")])
    except Exception:
        llm = None  # dégradation gracieuse

    _show_suggestion(suggestion)

    if not Confirm.ask(
        "\n[bold]Veux-tu intégrer cette suggestion à la fiche projet ?[/bold]",
        default=True,
    ):
        return None

    # Résolution des open_questions
    answers = _resolve_open_questions(suggestion, project.nom_projet, llm)

    # Conversion ProjectModel → dict mutable
    data = project_to_data(project)
    historique = existing_changements_to_list(project)

    # Application
    changes = _apply_suggestion_to_data(data, suggestion, answers)

    if not changes:
        console.print("[yellow]La suggestion n'a produit aucun changement effectif.[/yellow]")
        return None

    # Récap
    console.print()
    console.print("[bold green]Modifications appliquées :[/bold green]")
    for c in changes:
        console.print(f"  • {c}")

    if not Confirm.ask(
        "\n[bold]Confirmer ?[/bold] (Y = continuer vers les 3 couches de validation)",
        default=True,
    ):
        return None

    # Append à l'historique des Changements
    today = date.today().isoformat()
    resume = f"Intégration suggestion '{suggestion.title[:80]}' : " + " ; ".join(changes)
    historique.append({"date_changement": today, "resume": resume[:500]})

    return data, historique, changes
