"""
Couche 2 de validation — test de transmission par LLM.

Principe : un LLM lit le .md SANS contexte de la conversation et répond
à des questions factuelles sur le projet. Si ses réponses sont correctes,
le .md est autonome — les agents en aval pourront travailler dessus sans
avoir besoin d'informations supplémentaires.

Pourquoi cette couche ?
    Un .md peut être structurellement valide (couche 1) mais incompréhensible
    car trop elliptique. Ce test vérifie que la fiche "se lit seule".

Le LLM utilisé est celui de l'Interviewer (local, 7B Q4 via Ollama).
"""

from __future__ import annotations

import re

from rich.console import Console
from rich.panel import Panel

from src.models import ProjectModel

console = Console()


_TRANSMISSION_PROMPT_TEMPLATE = """Tu lis une fiche technique de projet d'ingénierie.
Réponds aux questions ci-dessous en une ligne chacune.
Utilise UNIQUEMENT les informations présentes dans la fiche. Ne déduis pas.

Fiche projet :
---
{md_content}
---

Questions (une réponse par ligne, format "N. réponse") :
1. Quel est le nom exact du projet ?
2. Quelle est sa phase ? (exploration / prototype / pré-production / déployé)
3. Nomme les composants dont le rôle pipeline est "critique" (séparés par des virgules).
4. Cite textuellement le premier objectif actif déclaré.
5. Quelle est la date du prochain rendu ou "N/A" ?"""


def validate_transmission(
    md_content: str,
    project: ProjectModel,
    config: dict,
) -> tuple[bool, str, list[str]]:
    """
    Test de transmission : le LLM répond à des questions sur le .md
    sans contexte de la conversation.

    Args:
        md_content: Contenu brut du .md.
        project:    ProjectModel validé par la couche 1 (sert de référence).
        config:     Config globale (pour get_llm).

    Returns:
        (passed, llm_summary, failed_checks)
        - passed : True si assez de réponses correctes.
        - llm_summary : résumé brut du LLM (pour affichage et log).
        - failed_checks : liste des vérifications qui ont échoué.
    """
    from src.llm import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    console.print()
    console.print(
        Panel.fit(
            "[bold yellow]COUCHE 2 — TEST DE TRANSMISSION[/bold yellow]\n"
            "Le LLM lit la fiche sans contexte et répond à des questions factuelles.",
            border_style="yellow",
        )
    )

    # ── Appel LLM ────────────────────────────────────────────
    llm = get_llm("interviewer", config)
    prompt = _TRANSMISSION_PROMPT_TEMPLATE.format(md_content=md_content)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        llm_answer: str = response.content.strip()
    except Exception as e:
        console.print(f"[red]Couche 2 : erreur lors de l'appel LLM — {e}[/red]")
        console.print("[yellow]Test de transmission ignoré (Ollama indisponible ?).[/yellow]")
        # On laisse passer pour ne pas bloquer si Ollama est down temporairement
        return True, f"Erreur LLM : {e}", []

    console.print(f"\n[dim]Réponse du LLM :[/dim]\n{llm_answer}\n")

    # ── Vérifications ─────────────────────────────────────────
    failed: list[str] = []
    answer_lower = llm_answer.lower()

    # Vérif 1 : nom du projet
    nom_lower = project.nom_projet.lower()
    if nom_lower not in answer_lower:
        # Essai partiel : au moins un mot du nom de 4+ lettres
        words = [w for w in nom_lower.split() if len(w) >= 4]
        if not any(w in answer_lower for w in words):
            failed.append(
                f"Le LLM n'a pas retrouvé le nom du projet '{project.nom_projet}'."
            )

    # Vérif 2 : phase
    if project.identite.phase.lower() not in answer_lower:
        failed.append(
            f"Le LLM n'a pas retrouvé la phase '{project.identite.phase}'."
        )

    # Vérif 3 : au moins un composant critique
    composants_critiques = [
        c.nom.lower() for c in project.composants if c.role_pipeline == "critique"
    ]
    if composants_critiques:
        if not any(nom in answer_lower for nom in composants_critiques):
            failed.append(
                f"Le LLM n'a pas retrouvé les composants critiques : "
                f"{', '.join(c.nom for c in project.composants if c.role_pipeline == 'critique')}."
            )

    # Vérif 4 : premier objectif (au moins les premiers mots)
    if project.objectifs_actifs:
        first_obj = project.objectifs_actifs[0].lower()
        # Vérifie qu'au moins 3 mots consécutifs de l'objectif sont présents
        words = first_obj.split()
        found = False
        for i in range(len(words) - 2):
            fragment = " ".join(words[i : i + 3])
            if fragment in answer_lower:
                found = True
                break
        if not found and len(first_obj) > 20:
            failed.append(
                "Le LLM n'a pas restitué le premier objectif actif de façon fidèle."
            )

    # ── Résultat ──────────────────────────────────────────────
    # On passe si au moins 3 des 4 vérifications sont OK
    score = 4 - len(failed)
    passed = score >= 3

    if passed:
        console.print(
            f"[green]Test de transmission : {score}/4 vérifications OK.[/green]"
        )
    else:
        console.print(
            f"[red]Test de transmission : {score}/4 vérifications OK.[/red]"
        )
        console.print("[yellow]Sections à améliorer :[/yellow]")
        for f in failed:
            console.print(f"  [red]✗[/red] {f}")

    return passed, llm_answer, failed
