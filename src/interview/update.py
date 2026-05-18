"""
Module update — modification d'un fichier .md projet existant via dialogue.

Principe :
    Charge un ProjectModel existant (déjà validé couche 1), affiche un menu
    section par section, permet d'ajouter / modifier / supprimer des entrées
    selon la nature de la section. Track les changements pour les append à
    la section "Changements" du .md.

Réutilise massivement les briques de `create.py` :
    - questions, choix, en-têtes de section
    - re-questionnement hybride (pré-checks déterministes + LLM)
    - guides de section pour calibrer le LLM
    - generate_md (avec injection de l'historique des changements)

Sections supportées :
    Identité (phase, domaine), Description, Objectifs actifs, Prochain rendu,
    Composants, Stack software, Interactions, Contraintes, Contraintes non
    négociables.

La section "Changements" n'est PAS éditable directement — elle est mise à jour
automatiquement par ce module.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.interview.create import (
    _SECTION_GUIDES,
    _ask,
    _ask_with_enrichment,
    _choose,
    _section_header,
    generate_md,
)
from src.models import ProjectModel

console = Console()


# ─────────────────────────────────────────────────────────────
# Conversion ProjectModel ↔ dict (pour generate_md)
# ─────────────────────────────────────────────────────────────


def project_to_data(project: ProjectModel) -> dict:
    """Convertit un ProjectModel en dict utilisable par generate_md."""
    return {
        "nom_projet": project.nom_projet,
        "phase": project.identite.phase,
        "domaine": project.identite.domaine,
        "description": project.description,
        "objectifs": list(project.objectifs_actifs),
        "prochain_rendu": {
            "date": (
                str(project.prochain_rendu.date_prevue)
                if project.prochain_rendu.date_prevue
                else "N/A"
            ),
            "nature": project.prochain_rendu.nature,
            "contenu_attendu": project.prochain_rendu.contenu_attendu,
        },
        "composants": [
            {
                "nom": c.nom,
                "role": c.role,
                "statut_decisionnel": c.statut_decisionnel,
                "role_pipeline": c.role_pipeline,
            }
            for c in project.composants
        ],
        "stack": [
            {
                "outil": s.outil,
                "role": s.role,
                "version": s.version,
                "statut_decisionnel": s.statut_decisionnel,
            }
            for s in project.stack_software
        ],
        "interactions": [
            {
                "source": i.source,
                "target": i.target,
                "nature": i.nature,
                "format": i.format,
                "volume": i.volume,
            }
            for i in project.interactions
        ],
        "contraintes": [
            {
                "titre": s.titre,
                "criteres": [{"nom": c.nom, "valeur": c.valeur} for c in s.criteres],
            }
            for s in project.contraintes
        ],
        "contraintes_non_negociables": list(project.contraintes_non_negociables),
    }


def existing_changements_to_list(project: ProjectModel) -> list[dict]:
    """Convertit l'historique des changements en list[dict] pour generate_md."""
    return [
        {"date_changement": str(c.date_changement), "resume": c.resume}
        for c in project.changements
    ]


# ─────────────────────────────────────────────────────────────
# Helpers d'affichage
# ─────────────────────────────────────────────────────────────


def _show_summary(project: ProjectModel) -> None:
    """Affiche un récap court du projet pour orienter l'utilisateur."""
    console.print()
    console.print(
        Panel.fit(
            f"[bold]{project.nom_projet}[/bold] | "
            f"phase [cyan]{project.identite.phase}[/cyan] | "
            f"domaine [cyan]{project.identite.domaine}[/cyan]\n"
            f"{len(project.composants)} composants | "
            f"{len(project.stack_software)} outils | "
            f"{len(project.interactions)} interactions | "
            f"{len(project.objectifs_actifs)} objectifs | "
            f"{len(project.contraintes)} sous-sections de contraintes",
            border_style="cyan",
            title="[bold]Fiche actuelle[/bold]",
        )
    )


def _menu_principal(data: dict) -> str:
    """Affiche le menu principal et retourne la section choisie."""
    n_obj = len(data["objectifs"])
    n_comp = len(data["composants"])
    n_stack = len(data["stack"])
    n_inter = len(data["interactions"])
    n_contr = len(data["contraintes"])
    n_cnn = len(data["contraintes_non_negociables"])

    console.print()
    console.print("[bold]Quelle section veux-tu modifier ?[/bold]")
    options = [
        ("1", f"Identité (phase = {data['phase']}, domaine = {data['domaine']})"),
        ("2", "Description"),
        ("3", f"Objectifs actifs ({n_obj})"),
        ("4", f"Prochain rendu ({data['prochain_rendu']['date']})"),
        ("5", f"Composants ({n_comp})"),
        ("6", f"Stack software ({n_stack})"),
        ("7", f"Interactions ({n_inter})"),
        ("8", f"Contraintes ({n_contr} sous-section{'s' if n_contr > 1 else ''})"),
        ("9", f"Contraintes non négociables ({n_cnn})"),
        ("0", "Terminer (sauvegarder)"),
    ]
    for code, label in options:
        console.print(f"  [cyan]{code}[/cyan]. {label}")
    return Prompt.ask("→", choices=[c for c, _ in options], default="0")


# ─────────────────────────────────────────────────────────────
# Sections atomiques (champ unique)
# ─────────────────────────────────────────────────────────────


def _update_identite(data: dict, llm, changes: list[str]) -> None:
    _section_header("MODIFIER IDENTITÉ", f"Phase actuelle : {data['phase']} | Domaine : {data['domaine']}")
    new_phase = _choose(
        f"Nouvelle phase (laisser '{data['phase']}' inchangé en confirmant)",
        ["exploration", "prototype", "pré-production", "déployé"],
        default=data["phase"],
    )
    if new_phase != data["phase"]:
        changes.append(f"Phase : {data['phase']} → {new_phase}")
        data["phase"] = new_phase

    new_domaine = _choose(
        f"Nouveau domaine (laisser '{data['domaine']}' inchangé en confirmant)",
        ["hardware", "software", "hybride"],
        default=data["domaine"],
    )
    if new_domaine != data["domaine"]:
        changes.append(f"Domaine : {data['domaine']} → {new_domaine}")
        data["domaine"] = new_domaine


def _update_description(data: dict, llm, changes: list[str]) -> None:
    _section_header(
        "MODIFIER DESCRIPTION",
        "Description actuelle ci-dessous. Saisis la nouvelle, ou tape 'skip' pour conserver.",
    )
    console.print()
    console.print(Panel(data["description"], title="[dim]Actuel[/dim]", border_style="dim"))

    new = _ask_with_enrichment(
        llm,
        data["nom_projet"],
        section="Description",
        question="Nouvelle description (ou 'skip')",
        expectations=_SECTION_GUIDES["Description"],
        allow_skip=True,
    )
    if new.strip().lower() == "skip" or new.strip() == data["description"]:
        return
    changes.append("Description réécrite")
    data["description"] = new


def _update_prochain_rendu(data: dict, llm, changes: list[str]) -> None:
    _section_header("MODIFIER PROCHAIN RENDU", f"Actuel : {data['prochain_rendu']}")
    while True:
        new_date = _ask(
            f"Nouvelle date (YYYY-MM-DD ou N/A) — actuel : {data['prochain_rendu']['date']}",
            default=data["prochain_rendu"]["date"],
        )
        if new_date.upper() == "N/A" or re.match(r"^\d{4}-\d{2}-\d{2}$", new_date):
            break
        console.print("[red]Format invalide. Format attendu : YYYY-MM-DD ou N/A.[/red]")

    new_date = new_date.upper() if new_date.lower() == "n/a" else new_date
    if new_date != data["prochain_rendu"]["date"]:
        changes.append(f"Date prochain rendu : {data['prochain_rendu']['date']} → {new_date}")
        data["prochain_rendu"]["date"] = new_date

    if new_date != "N/A":
        new_nature = _choose(
            f"Nature (actuel : {data['prochain_rendu']['nature']})",
            ["démo", "livraison client", "soutenance", "release", "N/A"],
            default=data["prochain_rendu"]["nature"],
        )
        if new_nature != data["prochain_rendu"]["nature"]:
            changes.append(
                f"Nature rendu : {data['prochain_rendu']['nature']} → {new_nature}"
            )
            data["prochain_rendu"]["nature"] = new_nature

        new_contenu = _ask_with_enrichment(
            llm,
            data["nom_projet"],
            section="Contenu attendu rendu",
            question=(
                f"Contenu attendu (actuel : {data['prochain_rendu']['contenu_attendu']}) "
                "— ou 'skip'"
            ),
            expectations=_SECTION_GUIDES["Contenu attendu rendu"],
            allow_skip=True,
        )
        if (
            new_contenu.strip().lower() != "skip"
            and new_contenu != data["prochain_rendu"]["contenu_attendu"]
        ):
            changes.append("Contenu attendu du rendu mis à jour")
            data["prochain_rendu"]["contenu_attendu"] = new_contenu


# ─────────────────────────────────────────────────────────────
# Sections "liste" — CRUD générique
# ─────────────────────────────────────────────────────────────


def _crud_loop(
    data_key: str,
    label_singular: str,
    label_plural: str,
    data: dict,
    show_item: Callable[[int, dict], str],
    add_item: Callable[[dict, str, list[str]], dict],
    edit_item: Callable[[dict, dict, str, list[str]], dict],
    summarize_item: Callable[[dict], str],
    llm,
    changes: list[str],
    nom: str,
) -> None:
    """
    Boucle CRUD générique pour les sections de type liste de dict.

    Args:
        data_key:        clé du dict data (ex: "composants")
        label_singular:  ex: "composant"
        label_plural:    ex: "composants"
        show_item:       (index, item_dict) -> str pour l'affichage
        add_item:        (data, nom_projet, changes) -> nouveau item dict
        edit_item:       (item_existant, data, nom_projet, changes) -> nouveau item dict
        summarize_item:  item_dict -> str court (pour log de changements)
    """
    while True:
        items = data[data_key]
        console.print()
        console.print(f"[bold]{label_plural.capitalize()} actuels :[/bold]")
        if items:
            for i, item in enumerate(items):
                console.print(f"  [cyan]{i + 1}[/cyan]. {show_item(i, item)}")
        else:
            console.print(f"  [dim](aucun)[/dim]")

        console.print(
            f"\n[bold]Action :[/bold] [cyan]a[/cyan] = ajouter, "
            f"[cyan]m N[/cyan] = modifier #N, [cyan]s N[/cyan] = supprimer #N, "
            f"[cyan]r[/cyan] = retour"
        )
        action = Prompt.ask("→").strip().lower()

        if action == "r" or action == "":
            return
        if action == "a":
            new = add_item(data, nom, changes)
            items.append(new)
            changes.append(f"Ajout {label_singular} : {summarize_item(new)}")
            continue
        m = re.match(r"^([ms])\s*(\d+)$", action)
        if not m:
            console.print(f"[red]Action non reconnue : '{action}'.[/red]")
            continue
        kind = m.group(1)
        idx = int(m.group(2)) - 1
        if not (0 <= idx < len(items)):
            console.print(f"[red]Index hors plage (1-{len(items)}).[/red]")
            continue
        if kind == "s":
            removed = items.pop(idx)
            changes.append(f"Suppression {label_singular} : {summarize_item(removed)}")
        elif kind == "m":
            updated = edit_item(items[idx], data, nom, changes)
            items[idx] = updated
            changes.append(f"Modification {label_singular} : {summarize_item(updated)}")


# ── Adaptateurs pour Composants ──────────────────────────────


def _show_composant(idx: int, c: dict) -> str:
    return (
        f"[bold]{c['nom']}[/bold] — {c['role']} "
        f"([{c['statut_decisionnel']}], {c['role_pipeline']})"
    )


def _add_composant(data: dict, nom: str, changes: list[str], llm=None) -> dict:
    # llm est optionnel ici — on le récupère du closure dans run_update_dialog
    raise NotImplementedError("doit être appelé via _make_add/edit_composant")


def _make_add_composant(llm):
    def fn(data, nom, changes):
        comp_nom = _ask("Nom du composant")
        while not comp_nom.strip():
            console.print("[red]Le nom ne peut pas être vide.[/red]")
            comp_nom = _ask("Nom du composant")
        comp_role = _ask_with_enrichment(
            llm, nom,
            section="Composant / rôle",
            question=f"Rôle technique de '{comp_nom}'",
            expectations=_SECTION_GUIDES["Composant / rôle"],
        )
        comp_statut = _choose(
            "Statut décisionnel",
            ["figé", "validé", "en évaluation"],
            default="validé",
        )
        comp_pipeline = _choose(
            "Rôle pipeline",
            ["critique", "support", "accessoire"],
            default="critique",
        )
        return {
            "nom": comp_nom,
            "role": comp_role,
            "statut_decisionnel": comp_statut,
            "role_pipeline": comp_pipeline,
        }
    return fn


def _make_edit_composant(llm):
    def fn(existing, data, nom, changes):
        console.print(f"[dim]Édition de '{existing['nom']}'. Tape 'skip' pour conserver une valeur.[/dim]")
        comp_nom = _ask(f"Nom (actuel : {existing['nom']})", default=existing["nom"])
        new_role = _ask_with_enrichment(
            llm, nom,
            section="Composant / rôle",
            question=f"Rôle (actuel : {existing['role']}) — ou 'skip'",
            expectations=_SECTION_GUIDES["Composant / rôle"],
            allow_skip=True,
        )
        comp_role = existing["role"] if new_role.strip().lower() == "skip" else new_role
        comp_statut = _choose(
            f"Statut décisionnel (actuel : {existing['statut_decisionnel']})",
            ["figé", "validé", "en évaluation"],
            default=existing["statut_decisionnel"],
        )
        comp_pipeline = _choose(
            f"Rôle pipeline (actuel : {existing['role_pipeline']})",
            ["critique", "support", "accessoire"],
            default=existing["role_pipeline"],
        )
        return {
            "nom": comp_nom,
            "role": comp_role,
            "statut_decisionnel": comp_statut,
            "role_pipeline": comp_pipeline,
        }
    return fn


def _summary_composant(c: dict) -> str:
    return f"{c['nom']} ({c['role_pipeline']})"


# ── Adaptateurs pour Stack ───────────────────────────────────


def _show_stack(idx: int, s: dict) -> str:
    return f"[bold]{s['outil']}[/bold] {s['version']} — {s['role']} ({s['statut_decisionnel']})"


def _make_add_stack(llm):
    def fn(data, nom, changes):
        outil = _ask("Outil / framework")
        while not outil.strip():
            console.print("[red]Le nom ne peut pas être vide.[/red]")
            outil = _ask("Outil / framework")
        role = _ask_with_enrichment(
            llm, nom,
            section="Stack item / rôle",
            question=f"Rôle de '{outil}' dans le projet",
            expectations=_SECTION_GUIDES["Stack item / rôle"],
        )
        version = _ask("Version (ou N/A)", default="N/A")
        statut = _choose(
            "Statut décisionnel",
            ["figé", "validé", "en évaluation"],
            default="validé",
        )
        return {"outil": outil, "role": role, "version": version, "statut_decisionnel": statut}
    return fn


def _make_edit_stack(llm):
    def fn(existing, data, nom, changes):
        console.print(f"[dim]Édition de '{existing['outil']}'.[/dim]")
        outil = _ask(f"Outil (actuel : {existing['outil']})", default=existing["outil"])
        new_role = _ask_with_enrichment(
            llm, nom,
            section="Stack item / rôle",
            question=f"Rôle (actuel : {existing['role']}) — ou 'skip'",
            expectations=_SECTION_GUIDES["Stack item / rôle"],
            allow_skip=True,
        )
        role = existing["role"] if new_role.strip().lower() == "skip" else new_role
        version = _ask(f"Version (actuel : {existing['version']})", default=existing["version"])
        statut = _choose(
            f"Statut (actuel : {existing['statut_decisionnel']})",
            ["figé", "validé", "en évaluation"],
            default=existing["statut_decisionnel"],
        )
        return {"outil": outil, "role": role, "version": version, "statut_decisionnel": statut}
    return fn


def _summary_stack(s: dict) -> str:
    return f"{s['outil']} {s['version']}"


# ── Adaptateurs pour Interactions ────────────────────────────


def _show_interaction(idx: int, i: dict) -> str:
    extras = []
    if i.get("format"):
        extras.append(i["format"])
    if i.get("volume"):
        extras.append(i["volume"])
    extra_str = f" | {' | '.join(extras)}" if extras else ""
    return f"{i['source']} → {i['target']} : {i['nature']}{extra_str}"


def _make_add_interaction(llm):
    def fn(data, nom, changes):
        source = _ask("Source")
        target = _ask("Cible (→)")
        nature = _ask_with_enrichment(
            llm, nom,
            section="Interaction / nature",
            question=f"Nature de l'échange ({source} → {target})",
            expectations=_SECTION_GUIDES["Interaction / nature"],
        )
        fmt = _ask("Format / protocole (vide pour passer)", default="")
        volume = _ask("Volume / fréquence (vide pour passer)", default="")
        return {
            "source": source, "target": target, "nature": nature,
            "format": fmt or None, "volume": volume or None,
        }
    return fn


def _make_edit_interaction(llm):
    def fn(existing, data, nom, changes):
        source = _ask(f"Source (actuel : {existing['source']})", default=existing["source"])
        target = _ask(f"Cible (actuel : {existing['target']})", default=existing["target"])
        new_nat = _ask_with_enrichment(
            llm, nom,
            section="Interaction / nature",
            question=f"Nature (actuel : {existing['nature']}) — ou 'skip'",
            expectations=_SECTION_GUIDES["Interaction / nature"],
            allow_skip=True,
        )
        nature = existing["nature"] if new_nat.strip().lower() == "skip" else new_nat
        fmt = _ask(
            f"Format (actuel : {existing.get('format') or 'vide'})",
            default=existing.get("format") or "",
        )
        volume = _ask(
            f"Volume (actuel : {existing.get('volume') or 'vide'})",
            default=existing.get("volume") or "",
        )
        return {
            "source": source, "target": target, "nature": nature,
            "format": fmt or None, "volume": volume or None,
        }
    return fn


def _summary_interaction(i: dict) -> str:
    return f"{i['source']} → {i['target']}"


# ── Adaptateurs pour Objectifs (liste de strings) ───────────


def _crud_loop_strings(
    data_key: str,
    label_singular: str,
    label_plural: str,
    data: dict,
    section_for_llm: str,
    expectations_key: str,
    llm,
    changes: list[str],
    nom: str,
) -> None:
    """CRUD spécifique pour les sections qui sont une simple list[str]."""
    while True:
        items = data[data_key]
        console.print()
        console.print(f"[bold]{label_plural.capitalize()} actuels :[/bold]")
        if items:
            for i, item in enumerate(items):
                console.print(f"  [cyan]{i + 1}[/cyan]. {item}")
        else:
            console.print(f"  [dim](aucun)[/dim]")

        console.print(
            f"\n[bold]Action :[/bold] [cyan]a[/cyan] = ajouter, "
            f"[cyan]m N[/cyan] = modifier #N, [cyan]s N[/cyan] = supprimer #N, "
            f"[cyan]r[/cyan] = retour"
        )
        action = Prompt.ask("→").strip().lower()

        if action == "r" or action == "":
            return
        if action == "a":
            new = _ask_with_enrichment(
                llm, nom,
                section=section_for_llm,
                question=f"Nouveau {label_singular}",
                expectations=_SECTION_GUIDES.get(expectations_key, ""),
            )
            items.append(new)
            changes.append(f"Ajout {label_singular} : {new[:60]}")
            continue
        m = re.match(r"^([ms])\s*(\d+)$", action)
        if not m:
            console.print(f"[red]Action non reconnue.[/red]")
            continue
        kind = m.group(1)
        idx = int(m.group(2)) - 1
        if not (0 <= idx < len(items)):
            console.print(f"[red]Index hors plage.[/red]")
            continue
        if kind == "s":
            removed = items.pop(idx)
            changes.append(f"Suppression {label_singular} : {removed[:60]}")
        elif kind == "m":
            new = _ask_with_enrichment(
                llm, nom,
                section=section_for_llm,
                question=f"Nouvelle valeur (actuel : {items[idx][:80]})",
                expectations=_SECTION_GUIDES.get(expectations_key, ""),
                allow_skip=True,
            )
            if new.strip().lower() != "skip":
                changes.append(f"Modification {label_singular} #{idx + 1}")
                items[idx] = new


# ── Contraintes (sous-sections + critères) ──────────────────


def _update_contraintes(data: dict, llm, changes: list[str], nom: str) -> None:
    while True:
        sections = data["contraintes"]
        console.print()
        console.print("[bold]Sous-sections de contraintes :[/bold]")
        for i, s in enumerate(sections):
            console.print(
                f"  [cyan]{i + 1}[/cyan]. [bold]{s['titre']}[/bold] — "
                f"{len(s['criteres'])} critère{'s' if len(s['criteres']) > 1 else ''}"
            )
        console.print(
            f"\n[bold]Action :[/bold] [cyan]a[/cyan] = ajouter sous-section, "
            f"[cyan]e N[/cyan] = éditer critères de #N, [cyan]s N[/cyan] = supprimer #N, "
            f"[cyan]r[/cyan] = retour"
        )
        action = Prompt.ask("→").strip().lower()
        if action == "r" or action == "":
            return
        if action == "a":
            titre = _ask("Titre de la sous-section (ex. Énergie, Performance)")
            if not titre.strip():
                continue
            new_section = {"titre": titre, "criteres": []}
            sections.append(new_section)
            _edit_criteres(new_section, llm, changes, nom)
            changes.append(f"Ajout sous-section contraintes : {titre}")
            continue
        m = re.match(r"^([es])\s*(\d+)$", action)
        if not m:
            console.print("[red]Action non reconnue.[/red]")
            continue
        kind, idx = m.group(1), int(m.group(2)) - 1
        if not (0 <= idx < len(sections)):
            console.print("[red]Index hors plage.[/red]")
            continue
        if kind == "s":
            removed = sections.pop(idx)
            changes.append(f"Suppression sous-section contraintes : {removed['titre']}")
        elif kind == "e":
            _edit_criteres(sections[idx], llm, changes, nom)


def _edit_criteres(section: dict, llm, changes: list[str], nom: str) -> None:
    while True:
        criteres = section["criteres"]
        console.print()
        console.print(f"[bold]Critères de '{section['titre']}' :[/bold]")
        if criteres:
            for i, c in enumerate(criteres):
                console.print(f"  [cyan]{i + 1}[/cyan]. {c['nom']} : {c['valeur']}")
        else:
            console.print("  [dim](aucun)[/dim]")
        console.print(
            f"\n[bold]Action :[/bold] [cyan]a[/cyan] = ajouter, "
            f"[cyan]m N[/cyan] = modifier #N, [cyan]s N[/cyan] = supprimer #N, "
            f"[cyan]r[/cyan] = retour"
        )
        action = Prompt.ask("→").strip().lower()
        if action == "r" or action == "":
            return
        if action == "a":
            cnom = _ask("Nom du critère")
            if not cnom.strip():
                continue
            cval = _ask_with_enrichment(
                llm, nom,
                section="Critère de contrainte / valeur",
                question=f"Valeur du critère '{cnom}'",
                expectations=_SECTION_GUIDES["Critère de contrainte / valeur"],
            )
            criteres.append({"nom": cnom, "valeur": cval})
            changes.append(f"Ajout critère : {section['titre']} / {cnom}")
            continue
        m = re.match(r"^([ms])\s*(\d+)$", action)
        if not m:
            console.print("[red]Action non reconnue.[/red]")
            continue
        kind, idx = m.group(1), int(m.group(2)) - 1
        if not (0 <= idx < len(criteres)):
            console.print("[red]Index hors plage.[/red]")
            continue
        if kind == "s":
            removed = criteres.pop(idx)
            changes.append(f"Suppression critère : {section['titre']} / {removed['nom']}")
        elif kind == "m":
            cnom = _ask(
                f"Nom (actuel : {criteres[idx]['nom']})", default=criteres[idx]["nom"]
            )
            new_val = _ask_with_enrichment(
                llm, nom,
                section="Critère de contrainte / valeur",
                question=f"Valeur (actuel : {criteres[idx]['valeur']}) — ou 'skip'",
                expectations=_SECTION_GUIDES["Critère de contrainte / valeur"],
                allow_skip=True,
            )
            cval = criteres[idx]["valeur"] if new_val.strip().lower() == "skip" else new_val
            criteres[idx] = {"nom": cnom, "valeur": cval}
            changes.append(f"Modification critère : {section['titre']} / {cnom}")


# ─────────────────────────────────────────────────────────────
# Dialogue principal
# ─────────────────────────────────────────────────────────────


def run_update_dialog(
    project: ProjectModel, config: dict
) -> tuple[Optional[dict], list[dict], list[str]]:
    """
    Lance le dialogue de modification.

    Returns:
        Tuple (data, changements_complets, changements_resumes) :
            - data : dict prêt pour generate_md (None si abandon).
            - changements_complets : list[dict] (historique préservé + nouvelle entrée).
            - changements_resumes : list[str] (les changements effectués cette session,
              juste pour affichage côté CLI).
    """
    from src.llm import get_llm

    # Init LLM (peut échouer si Ollama down)
    llm = None
    try:
        llm = get_llm("interviewer", config)
        from langchain_core.messages import HumanMessage as _HM
        _ = llm.invoke([_HM(content="Réponds OK.")])
    except Exception as e:
        llm = None
        console.print(
            f"[yellow]Avertissement : LLM indisponible ({type(e).__name__}). "
            f"Le re-questionnement automatique est désactivé.[/yellow]"
        )

    console.print()
    console.print(
        Panel.fit(
            "[bold green]INTERVIEW — MODIFICATION DE FICHE PROJET[/bold green]\n"
            "Choisis une section à modifier au menu ci-dessous.\n"
            "Toutes les modifications sont auditées dans la section [bold]Changements[/bold].",
            border_style="green",
        )
    )

    data = project_to_data(project)
    historique = existing_changements_to_list(project)
    changes: list[str] = []
    nom = data["nom_projet"]

    _show_summary(project)

    while True:
        choice = _menu_principal(data)
        if choice == "0":
            break
        if choice == "1":
            _update_identite(data, llm, changes)
        elif choice == "2":
            _update_description(data, llm, changes)
        elif choice == "3":
            _crud_loop_strings(
                "objectifs", "objectif", "objectifs",
                data, "Objectifs actifs", "Objectifs actifs",
                llm, changes, nom,
            )
        elif choice == "4":
            _update_prochain_rendu(data, llm, changes)
        elif choice == "5":
            _crud_loop(
                "composants", "composant", "composants",
                data, _show_composant,
                _make_add_composant(llm), _make_edit_composant(llm),
                _summary_composant, llm, changes, nom,
            )
        elif choice == "6":
            _crud_loop(
                "stack", "outil", "outils de la stack",
                data, _show_stack,
                _make_add_stack(llm), _make_edit_stack(llm),
                _summary_stack, llm, changes, nom,
            )
        elif choice == "7":
            _crud_loop(
                "interactions", "interaction", "interactions",
                data, _show_interaction,
                _make_add_interaction(llm), _make_edit_interaction(llm),
                _summary_interaction, llm, changes, nom,
            )
        elif choice == "8":
            _update_contraintes(data, llm, changes, nom)
        elif choice == "9":
            _crud_loop_strings(
                "contraintes_non_negociables", "contrainte non négociable",
                "contraintes non négociables",
                data, "Contrainte non négociable", "Contrainte non négociable",
                llm, changes, nom,
            )

    # Pas de changements ? On renvoie None pour signaler à l'appelant
    if not changes:
        console.print()
        console.print("[yellow]Aucun changement effectué. Sortie sans modification.[/yellow]")
        return None, historique, []

    # Récap des changements
    console.print()
    console.print("[bold green]Récapitulatif des modifications :[/bold green]")
    for c in changes:
        console.print(f"  • {c}")
    console.print()

    if not Confirm.ask(
        "[bold]Appliquer ces modifications ?[/bold] "
        "(Y = poursuivre vers les 3 couches de validation, N = annuler)",
        default=True,
    ):
        return None, historique, []

    # Construit le nouvel item d'historique
    today = date.today().isoformat()
    resume = " ; ".join(changes)
    historique.append({"date_changement": today, "resume": resume[:500]})

    return data, historique, changes
