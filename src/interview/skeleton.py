"""
Génération de squelette .md — mode `skeleton` de l'Interviewer.

Génère un fichier .md pré-structuré avec des commentaires d'aide
et des placeholders explicites, puis tente de l'ouvrir dans l'éditeur système.

Conçu pour les utilisateurs qui préfèrent remplir leur fiche directement
dans un éditeur plutôt que de passer par le questionnaire interactif.

Workflow :
    applied-fox interview skeleton          → génère la fiche
    [édition dans VS Code / Notepad / vim]
    applied-fox run --project ma_fiche.md   → valide et lance la veille
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()


def generate_skeleton_md(project_name: str) -> str:
    """
    Génère le contenu Markdown d'une fiche projet vierge avec commentaires d'aide.

    Les commentaires HTML (<!-- -->) sont ignorés par structural.py lors du parsing.
    Les valeurs "À compléter" seront détectées comme invalides par Pydantic —
    c'est intentionnel : la validation signale clairement ce qui reste à remplir.
    """
    today = date.today().isoformat()
    return f"""# {project_name}

## Identité
- Nom : {project_name}
- Phase : prototype
- Domaine : hybride
- Dernière mise à jour : {today}

## Description
<!--
  Décris en 2-3 phrases :
    (1) ce que fait le système (fonction technique précise)
    (2) pour qui / dans quel contexte de déploiement
    (3) scope concret : durée, environnement, ordres de grandeur

  Exemple valide :
    Station météo autonome ESP32 mesurant température, humidité et pression.
    Transmission LoRaWAN vers passerelle locale, déploiement outdoor 6 mois sans intervention.

  À éviter (trop générique) :
    "Système qui collecte des données environnementales de manière fiable."
-->
À compléter

## Objectifs actifs
<!--
  Un objectif par ligne, commençant par "- ".
  Chaque objectif doit être chiffré (mesure + unité + condition) ou binaire vérifiable.

  Exemples valides :
    - Tenir 6 mois d'autonomie sur batterie LiPo 2000 mAh + panneau solaire 5W
    - Précision température ±0.5°C en plage -10°C / +50°C
    - Coût matériel < 80€ par unité
    - Compatible LoRaWAN classe A (binaire)

  À éviter : "être performant", "consommer peu", "optimiser le coût"
-->
- À compléter

## Prochain rendu
<!--
  Date au format YYYY-MM-DD, ou N/A si pas de deadline.
  Nature : démo | livraison client | soutenance | release | N/A
  Contenu attendu : artefacts concrets + métriques
    Exemple : Prototype fonctionnel + 1 mois de données collectées et visualisées
-->
- Date : N/A
- Nature : N/A
- Contenu attendu : N/A

## Composants
<!--
  Tous les composants physiques structurants : MCU, capteurs, modules comm.,
  alimentation, boîtiers IP...

  Colonnes :
    Statut décisionnel : figé | validé | en évaluation
    Rôle pipeline      : critique (sans lui ça ne marche pas) | support | accessoire

  Exemples :
    | ESP32-WROOM-32E        | Microcontrôleur principal + LoRa            | validé | critique   |
    | BME280                 | Capteur T°/humidité/pression I2C            | validé | critique   |
    | Module LoRa SX1276     | Transmission longue distance LoRaWAN        | validé | critique   |
    | Batterie LiPo 2000 mAh | Stockage énergie principale                 | validé | critique   |
    | Panneau solaire 5W 6V  | Recharge via MPPT                           | validé | critique   |
-->
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| À compléter | À compléter | validé | critique |

## Stack software
<!--
  Frameworks, langages, librairies structurants du projet.

  Exemples :
    | ESP-IDF   | Framework firmware principal          | 5.x   | validé        |
    | Python    | Scripts de traitement côté serveur    | 3.11  | validé        |
    | Grafana   | Visualisation des données             | N/A   | en évaluation |
-->
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| À compléter | À compléter | N/A | validé |

## Interactions
<!--
  Format : Source → Cible : nature | protocole/format | volume/fréquence
  Le protocole et le volume sont optionnels mais recommandés.

  Exemples :
    - BME280 → ESP32-WROOM-32E : mesures T°/humidité/pression | I2C | 1 lecture/15 min
    - ESP32-WROOM-32E → Module LoRa SX1276 : trame de données sérialisée | SPI | 1 envoi/15 min
    - Panneau solaire 5W → Batterie LiPo : courant de recharge | MPPT | continu
-->
- À compléter → À compléter : À compléter

## Contraintes

### À compléter
<!--
  Regroupe par sous-thème : Énergie, Performance, Connectivité, Budget, Environnementales...
  Pour chaque critère : valeur chiffrée + unité, état explicite, N/A : raison, ou TBD : raison.

  Exemple de section "Énergie" :
    - Autonomie cible : 6 mois
    - Consommation en veille : < 50 µA
    - Consommation en transmission : < 200 mA pic

  Exemple de section "Environnementales" :
    - Indice de protection : IP65 minimum
    - Plage de température opérationnelle : -10°C / +60°C
-->
- À compléter : À compléter

## Contraintes non négociables
<!--
  Imposées par décision externe (client, certification, stratégie figée).
  Pas une préférence — quelque chose qui NE PEUT PAS changer.
  Indique QUI l'impose ou POURQUOI c'est figé.

  Exemples :
    - Pas de cloud commercial — données stockées sur passerelle locale (exigence client)
    - Code source sous licence MIT pour la soutenance (règlement école)
    - Certification CE obligatoire avant commercialisation
-->
- À compléter

## Changements
- {today} : Création initiale de la fiche projet
"""


def _open_in_editor(filepath: Path) -> None:
    """Tente d'ouvrir le fichier dans l'éditeur système."""
    try:
        if sys.platform == "win32":
            os.startfile(str(filepath))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(filepath)])
        else:
            editor = os.environ.get("EDITOR", "xdg-open")
            subprocess.Popen([editor, str(filepath)])
    except Exception as exc:
        console.print(f"[yellow]Impossible d'ouvrir l'éditeur automatiquement : {exc}[/yellow]")


def run_skeleton(output_dir: Path, config: dict) -> None:  # noqa: ARG001
    """
    Génère un squelette .md et l'ouvre dans l'éditeur système.
    """
    console.print()
    console.print(
        Panel.fit(
            "[bold green]SKELETON — CRÉATION DE FICHE PROJET[/bold green]\n\n"
            "Génère un [bold].md[/bold] pré-structuré avec des commentaires d'aide.\n"
            "Remplis-le dans ton éditeur, puis lance :\n\n"
            "  [cyan]applied-fox run --project ta_fiche.md[/cyan]",
            border_style="green",
        )
    )

    # Nom du projet
    while True:
        nom = Prompt.ask("\nNom du projet").strip()
        if nom:
            break
        console.print("[red]Le nom ne peut pas être vide.[/red]")

    # Nom de fichier : slug sans accents ni caractères spéciaux
    slug = nom.lower()
    slug = re.sub(r"[àáâãäå]", "a", slug)
    slug = re.sub(r"[èéêë]", "e", slug)
    slug = re.sub(r"[ìíîï]", "i", slug)
    slug = re.sub(r"[òóôõö]", "o", slug)
    slug = re.sub(r"[ùúûü]", "u", slug)
    slug = re.sub(r"[ç]", "c", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")

    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"{slug}.md"

    # Évite d'écraser un fichier existant sans confirmation
    if filepath.exists():
        console.print(f"[yellow]Fichier existant : {filepath}[/yellow]")
        if not Confirm.ask("Écraser ?", default=False):
            console.print("[dim]Annulé.[/dim]")
            return

    content = generate_skeleton_md(nom)
    filepath.write_text(content, encoding="utf-8")

    console.print(f"\n[green]✓ Fiche créée :[/green] [cyan]{filepath}[/cyan]")
    console.print("[dim]Ouverture dans l'éditeur...[/dim]")
    _open_in_editor(filepath)
    console.print(
        f"\nQuand tu auras rempli la fiche, lance :\n"
        f"[bold cyan]applied-fox run --project \"{filepath}\"[/bold cyan]"
    )
