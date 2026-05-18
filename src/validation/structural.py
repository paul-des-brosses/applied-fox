"""
Couche 1 de validation du fichier .md projet — parsing Markdown + Pydantic.

Trois niveaux imbriqués :
    Niveau 1 : toutes les sections obligatoires sont présentes dans le bon ordre.
    Niveau 2 : structure interne correcte (colonnes des tables, valeurs énumérées,
               formats de date).
    Niveau 3 : cohérence sémantique interne (tout composant référencé dans Interactions
               existe dans la table Composants ou Stack software ; dates cohérentes).

Usage :
    project, messages = parse_and_validate(md_content)
    if project is None:
        # messages contient les erreurs bloquantes
    elif messages:
        # project est valide mais messages contient des avertissements
        # (ex. lignes d'interactions ignorées car mal formatées)
    else:
        # project est valide, aucun avertissement
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from pydantic import ValidationError

from src.models import (
    Changement,
    Composant,
    CritereContrainte,
    Identite,
    Interaction,
    ProjectModel,
    ProchainRendu,
    SousSectionContraintes,
    StackItem,
)

# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

# Noms de sections attendus (normalisés en minuscules sans accents doublons)
_REQUIRED_SECTION_KEYS = [
    "identité",
    "description",
    "objectifs actifs",
    "prochain rendu",
    "composants",
    "stack software",
    "interactions",
    "contraintes",
    "contraintes non négociables",
    "changements",
]

_VALID_PHASES = {"exploration", "prototype", "pré-production", "déployé"}
_VALID_DOMAINES = {"hardware", "software", "hybride"}
_VALID_STATUTS = {"figé", "validé", "en évaluation"}
_VALID_ROLES_PIPELINE = {"critique", "support", "accessoire"}
_VALID_NATURES_RENDU = {"démo", "livraison client", "soutenance", "release", "N/A"}


# ─────────────────────────────────────────────────────────────
# Fonctions de parsing primitives
# ─────────────────────────────────────────────────────────────


def _norm(s: str) -> str:
    """Normalisation pour comparer les noms de section.

    Strip, lowercase, et suppression des accents — rend le parseur robuste
    aux oublis d'accent dans les titres H2 : "Identite" == "Identité".
    """
    s = s.strip().lower()
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _split_by_h2(content: str) -> tuple[str, dict[str, str]]:
    """
    Extrait le titre H1 et découpe le contenu par sections H2.
    Retourne (h1_title, {nom_section_normalisé: contenu_section}).
    """
    h1_title = ""
    sections: dict[str, str] = {}
    current_section: Optional[str] = None
    current_lines: list[str] = []

    for line in content.splitlines():
        # H1 (pas H2+)
        if re.match(r"^# [^#]", line):
            h1_title = line[2:].strip()
        # H2
        elif line.startswith("## "):
            if current_section is not None:
                sections[_norm(current_section)] = "\n".join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
        else:
            if current_section is not None:
                current_lines.append(line)

    if current_section is not None:
        sections[_norm(current_section)] = "\n".join(current_lines).strip()

    return h1_title, sections


def _parse_kv_list(text: str) -> dict[str, str]:
    """
    Parse une liste à puces du type `- Clé : Valeur`.
    Retourne un dict {clé_normalisée_en_minuscules: valeur}.

    Accepte n'importe quel espacement autour du `:` :
    `- phase : prototype`, `- phase: prototype` et `- phase:prototype`
    produisent tous {"phase": "prototype"}.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:]
        parts = re.split(r"\s*:\s*", content, maxsplit=1)
        if len(parts) == 2:
            result[parts[0].strip().lower()] = parts[1].strip()
    return result


def _parse_table(text: str) -> list[list[str]]:
    """
    Parse un tableau Markdown.
    Retourne une liste de lignes (header inclus) sous forme de listes de cellules.
    Les lignes séparateurs (|---|---) sont ignorées.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Ligne séparateur : ne contient que |, -, :, espace
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]  # retire les cellules vides (bords du |)
        if cells:
            rows.append(cells)
    return rows


def _parse_bullet_list(text: str) -> list[str]:
    """Parse une liste à puces simple. Retourne les valeurs sans le `- `."""
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _parse_interactions(text: str) -> tuple[list[dict], list[str]]:
    """
    Parse la section Interactions.
    Format attendu : `- A → B : nature | format | volume`

    Retourne (interactions_valides, avertissements).
    Les lignes non reconnues ne bloquent pas la validation mais sont
    signalées pour que l'utilisateur puisse les corriger.
    """
    interactions: list[dict] = []
    warnings: list[str] = []
    for item in _parse_bullet_list(text):
        # Le → peut aussi être écrit "->" selon ce que l'utilisateur tape
        arrow_pattern = r"^(.+?)\s*(?:→|->)\s*(.+?)\s*:\s*(.+)$"
        m = re.match(arrow_pattern, item)
        if not m:
            warnings.append(
                f"Avertissement / Interactions : ligne non reconnue (ignorée) : "
                f"« {item} ». Format attendu : A → B : nature | format | volume"
            )
            continue
        source = m.group(1).strip()
        target = m.group(2).strip()
        rest = m.group(3)
        parts = [p.strip() for p in rest.split("|")]
        interactions.append(
            {
                "source": source,
                "target": target,
                "nature": parts[0] if parts else "",
                "format": parts[1] if len(parts) > 1 else None,
                "volume": parts[2] if len(parts) > 2 else None,
            }
        )
    return interactions, warnings


def _parse_contraintes(text: str) -> list[dict]:
    """
    Parse la section Contraintes (avec sous-sections ###).
    Retourne une liste de dicts {titre, criteres: [{nom, valeur}]}.
    """
    result: list[dict] = []
    current_title: Optional[str] = None
    current_criteria: list[dict] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            if current_title is not None:
                result.append({"titre": current_title, "criteres": current_criteria})
            current_title = stripped[4:].strip()
            current_criteria = []
        elif stripped.startswith("- ") and current_title is not None:
            content = stripped[2:]
            if " : " in content:
                nom, _, valeur = content.partition(" : ")
                current_criteria.append({"nom": nom.strip(), "valeur": valeur.strip()})
            else:
                current_criteria.append({"nom": content.strip(), "valeur": ""})

    if current_title is not None:
        result.append({"titre": current_title, "criteres": current_criteria})

    return result


def _parse_changements(text: str) -> list[dict]:
    """
    Parse la section Changements.
    Format : `- YYYY-MM-DD : résumé`
    Gère `- Aucun changement` comme cas spécial (produit une entrée symbolique).
    """
    changements: list[dict] = []
    today_str = date.today().isoformat()

    for item in _parse_bullet_list(text):
        if item.strip().lower() in ("aucun changement", "aucun"):
            continue  # placeholder — géré après la boucle

        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*:\s*(.+)$", item)
        if m:
            changements.append(
                {"date_changement": m.group(1), "resume": m.group(2).strip()}
            )
        else:
            # Ligne non structurée → on la garde avec date du jour
            changements.append({"date_changement": today_str, "resume": item})

    if not changements:
        # Fichier sans changements (ex. template vierge) → entrée symbolique
        changements.append({"date_changement": today_str, "resume": "Création de la fiche"})

    return changements


# ─────────────────────────────────────────────────────────────
# Validation de haut niveau
# ─────────────────────────────────────────────────────────────


def _validate_level3(project: ProjectModel) -> list[str]:
    """
    Niveau 3 — cohérence sémantique interne.
    Vérifie que les entités référencées dans Interactions existent
    dans Composants ou Stack software.
    """
    errors: list[str] = []

    known_names = {c.nom for c in project.composants} | {s.outil for s in project.stack_software}

    for interaction in project.interactions:
        if interaction.source not in known_names:
            errors.append(
                f"Interactions : '{interaction.source}' n'existe pas dans Composants ni Stack software."
            )
        if interaction.target not in known_names:
            errors.append(
                f"Interactions : '{interaction.target}' n'existe pas dans Composants ni Stack software."
            )

    # Cohérence : Identité.nom == titre H1 (vérifié à l'appel, pas ici)
    # Cohérence dates
    if project.prochain_rendu.date_prevue is not None:
        if project.prochain_rendu.date_prevue < project.identite.derniere_mise_a_jour:
            errors.append(
                "Prochain rendu : la date de rendu est antérieure à la dernière mise à jour."
            )

    return errors


def parse_and_validate(md_content: str) -> tuple[Optional[ProjectModel], list[str]]:
    """
    Parse et valide un fichier .md projet en 3 niveaux.

    Args:
        md_content: Contenu brut du fichier .md.

    Returns:
        (ProjectModel, messages) où messages peut contenir :
          - des erreurs bloquantes si ProjectModel est None,
          - des avertissements non-bloquants (préfixés "Avertissement")
            si ProjectModel est valide mais que des lignes ont été ignorées.
    """
    errors: list[str] = []
    warnings: list[str] = []  # non-bloquants, retournés avec le modèle valide

    # ── Niveau 1 : sections présentes ────────────────────────
    h1_title, sections = _split_by_h2(md_content)

    if not h1_title:
        errors.append("Niveau 1 : titre H1 manquant (# Nom du projet).")

    # Les clés de `sections` sont normalisées (sans accents) par _split_by_h2.
    # On normalise aussi les required keys pour la comparaison.
    missing = [s for s in _REQUIRED_SECTION_KEYS if _norm(s) not in sections]
    if missing:
        errors.append(
            f"Niveau 1 : sections manquantes : {', '.join(missing)}."
        )
        return None, errors

    # ── Niveau 2 : structure interne ─────────────────────────

    # Identité
    identite_raw = _parse_kv_list(sections[_norm("identité")])
    required_id_fields = ["nom", "phase", "domaine", "dernière mise à jour"]
    for field in required_id_fields:
        if field not in identite_raw:
            errors.append(f"Niveau 2 / Identité : champ '{field}' manquant.")

    if errors:
        return None, errors

    phase = identite_raw.get("phase", "")
    if phase not in _VALID_PHASES:
        errors.append(
            f"Niveau 2 / Identité : phase '{phase}' invalide. "
            f"Valeurs : {sorted(_VALID_PHASES)}."
        )

    domaine = identite_raw.get("domaine", "")
    if domaine not in _VALID_DOMAINES:
        errors.append(
            f"Niveau 2 / Identité : domaine '{domaine}' invalide. "
            f"Valeurs : {sorted(_VALID_DOMAINES)}."
        )

    try:
        derniere_maj = date.fromisoformat(identite_raw.get("dernière mise à jour", ""))
    except ValueError:
        errors.append(
            "Niveau 2 / Identité : 'dernière mise à jour' doit être au format YYYY-MM-DD."
        )
        derniere_maj = date.today()

    if errors:
        return None, errors

    # Description
    description = sections["description"].strip()
    if len(description) < 50:
        errors.append(
            f"Niveau 2 / Description : trop courte ({len(description)} caractères, minimum 50)."
        )

    # Objectifs actifs
    objectifs = _parse_bullet_list(sections["objectifs actifs"])
    if not objectifs:
        errors.append("Niveau 2 / Objectifs actifs : au moins un objectif requis.")

    # Prochain rendu
    rendu_raw = _parse_kv_list(sections["prochain rendu"])
    date_rendu_str = rendu_raw.get("date", "N/A")
    date_rendu: Optional[date] = None
    if date_rendu_str not in ("N/A", "n/a", ""):
        try:
            date_rendu = date.fromisoformat(date_rendu_str)
        except ValueError:
            errors.append(
                "Niveau 2 / Prochain rendu : 'date' doit être YYYY-MM-DD ou N/A."
            )

    nature_rendu = rendu_raw.get("nature", "")
    if nature_rendu not in _VALID_NATURES_RENDU:
        errors.append(
            f"Niveau 2 / Prochain rendu : nature '{nature_rendu}' invalide. "
            f"Valeurs : {sorted(_VALID_NATURES_RENDU)}."
        )

    contenu_attendu = rendu_raw.get("contenu attendu", "")

    # Composants (table)
    composants_rows = _parse_table(sections["composants"])
    if len(composants_rows) < 2:  # header + at least 1 row
        errors.append("Niveau 2 / Composants : au moins une ligne de composant requise.")
    composants_data_rows = composants_rows[1:]  # skip header
    for i, row in enumerate(composants_data_rows):
        if len(row) < 4:
            errors.append(f"Niveau 2 / Composants : ligne {i+1} incomplète (4 colonnes attendues).")
            continue
        if row[2] not in _VALID_STATUTS:
            errors.append(
                f"Niveau 2 / Composants : statut décisionnel '{row[2]}' invalide."
            )
        if row[3] not in _VALID_ROLES_PIPELINE:
            errors.append(
                f"Niveau 2 / Composants : rôle pipeline '{row[3]}' invalide."
            )

    # Stack software (table)
    stack_rows = _parse_table(sections["stack software"])
    if len(stack_rows) < 2:
        errors.append("Niveau 2 / Stack software : au moins une ligne requise.")
    stack_data_rows = stack_rows[1:]
    for i, row in enumerate(stack_data_rows):
        if len(row) < 4:
            errors.append(f"Niveau 2 / Stack software : ligne {i+1} incomplète (4 colonnes).")
            continue
        if row[3] not in _VALID_STATUTS:
            errors.append(
                f"Niveau 2 / Stack software : statut décisionnel '{row[3]}' invalide."
            )

    # Interactions
    interactions_data, interaction_warnings = _parse_interactions(sections["interactions"])
    warnings.extend(interaction_warnings)  # non-bloquants : collectés séparément
    if not interactions_data:
        errors.append(
            "Niveau 2 / Interactions : au moins une interaction requise. "
            "Format : `- A → B : nature | format | volume`."
        )

    # Contraintes
    contraintes_data = _parse_contraintes(sections["contraintes"])
    if not contraintes_data:
        errors.append("Niveau 2 / Contraintes : au moins une sous-section ### requise.")

    # Contraintes non négociables
    cnn_items = _parse_bullet_list(sections[_norm("contraintes non négociables")])
    if not cnn_items:
        errors.append(
            "Niveau 2 / Contraintes non négociables : au moins un item requis "
            "(utilise '- Aucune' si applicable)."
        )

    if errors:
        return None, errors

    # ── Construction du ProjectModel via Pydantic ─────────────
    try:
        identite = Identite(
            nom=identite_raw.get("nom", h1_title),
            phase=phase,  # type: ignore[arg-type]
            domaine=domaine,  # type: ignore[arg-type]
            derniere_mise_a_jour=derniere_maj,
        )

        prochain_rendu = ProchainRendu(
            date_prevue=date_rendu,
            nature=nature_rendu,  # type: ignore[arg-type]
            contenu_attendu=contenu_attendu or "N/A",
        )

        composants = [
            Composant(
                nom=row[0],
                role=row[1],
                statut_decisionnel=row[2],  # type: ignore[arg-type]
                role_pipeline=row[3],  # type: ignore[arg-type]
            )
            for row in composants_data_rows
            if len(row) >= 4
        ]

        stack_software = [
            StackItem(
                outil=row[0],
                role=row[1],
                version=row[2],
                statut_decisionnel=row[3],  # type: ignore[arg-type]
            )
            for row in stack_data_rows
            if len(row) >= 4
        ]

        interactions = [
            Interaction(
                source=i["source"],
                target=i["target"],
                nature=i["nature"],
                format=i.get("format"),
                volume=i.get("volume"),
            )
            for i in interactions_data
        ]

        contraintes = [
            SousSectionContraintes(
                titre=s["titre"],
                criteres=[
                    CritereContrainte(nom=c["nom"], valeur=c["valeur"])
                    for c in s["criteres"]
                ],
            )
            for s in contraintes_data
        ]

        changements_raw = _parse_changements(sections["changements"])
        changements = [
            Changement(
                date_changement=date.fromisoformat(c["date_changement"]),
                resume=c["resume"],
            )
            for c in changements_raw
        ]

        project = ProjectModel(
            nom_projet=h1_title or identite_raw.get("nom", ""),
            identite=identite,
            description=description,
            objectifs_actifs=objectifs,
            prochain_rendu=prochain_rendu,
            composants=composants,
            stack_software=stack_software,
            interactions=interactions,
            contraintes=contraintes,
            contraintes_non_negociables=cnn_items,
            changements=changements,
        )

    except ValidationError as exc:
        for err in exc.errors():
            loc = " > ".join(str(l) for l in err["loc"])
            errors.append(f"Niveau 2 / Pydantic — {loc} : {err['msg']}")
        return None, errors

    # ── Niveau 3 : cohérence sémantique ─────────────────────
    level3_errors = _validate_level3(project)
    if level3_errors:
        errors.extend(level3_errors)
        return None, errors

    # Fiche valide — on retourne les warnings non-bloquants s'il y en a
    # (lignes d'interactions ignorées, etc.). L'appelant peut les afficher
    # sans bloquer la suite : project est non-None.
    return project, warnings
