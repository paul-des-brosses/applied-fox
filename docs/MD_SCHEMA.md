# MD_SCHEMA — Spécification du fichier projet `.md`

Ce document spécifie strictement le format du fichier `.md` qui décrit un projet. Ce fichier est l'**artefact central** du système : tous les agents en aval ne lisent que lui pour comprendre le projet.

Le format est un Markdown structuré à deux étages :
- **Sections fixes obligatoires** — leur présence et leur structure sont validées par règles déterministes.
- **Section Contraintes adaptative** — sous-sections libres (Performance, Énergie, Connectivité, etc.), avec des valeurs définies, `N/A`, ou `TBD` justifié.

Spec validée à trois couches : Pydantic + parsers Markdown (déterministe), test de transmission par LLM tiers, validation humaine. Les détails sont dans [`ARCHITECTURE.md`](ARCHITECTURE.md) section "Système de validation à 3 couches".

---

## Schéma complet — template à remplir

```markdown
# [NOM DU PROJET]

## Identité
- Nom : [nom complet du projet]
- Phase : [exploration / prototype / pré-production / déployé]
- Domaine : [hardware / software / hybride]
- Dernière mise à jour : [YYYY-MM-DD]

## Description
[2-3 phrases qui décrivent ce que fait le projet et pour qui.]

## Objectifs actifs
- [Objectif 1, formulé de façon précise et mesurable si possible]
- [Objectif 2]
- [...]

## Prochain rendu
- Date : [YYYY-MM-DD ou N/A]
- Nature : [démo / livraison client / soutenance / release / N/A]
- Contenu attendu : [ce qui doit fonctionner pour ce rendu, ou N/A]

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| [Nom] | [Rôle dans le système] | [figé / validé / en évaluation] | [critique / support / accessoire] |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| [Nom] | [Rôle] | [Version ou N/A] | [figé / validé / en évaluation] |

## Interactions
- [A] → [B] : [nature de l'échange] | [format] | [volume si pertinent]

## Contraintes

### [Sous-section libre 1, ex. Performance]
- [Critère] : [valeur définie / N/A / TBD : justification]

### [Sous-section libre 2, ex. Énergie]
- [Critère] : [valeur définie / N/A / TBD : justification]

[etc.]

## Contraintes non négociables
- [Ce qui est figé par décision externe — client, certification, choix stratégique]

## Changements
- YYYY-MM-DD : [résumé du changement validé]
```

---

## Description champ par champ

### `# [NOM DU PROJET]` — titre H1

- Obligatoire, exactement un seul titre H1 dans le fichier.
- Doit correspondre au champ `Identité > Nom`.

### Section `## Identité`

| Champ | Type | Obligatoire | Valeurs autorisées |
|-------|------|-------------|--------------------|
| `Nom` | string | oui | non vide, 1-80 caractères |
| `Phase` | enum | oui | `exploration`, `prototype`, `pré-production`, `déployé` |
| `Domaine` | enum | oui | `hardware`, `software`, `hybride` |
| `Dernière mise à jour` | date | oui | format ISO `YYYY-MM-DD` |

### Section `## Description`

- Texte libre, 50 à 500 caractères recommandé.
- Pas de listes, pas de sous-titres : prose simple.
- Le test de transmission (couche 2) vérifie que cette section permet à un LLM tiers de comprendre la finalité du projet.

### Section `## Objectifs actifs`

- Liste à puces, au moins 1 objectif, idéalement 2-5.
- **Section critique pour l'alignement téléologique** : tout finding non aligné avec ces objectifs est rejeté en amont.
- Formuler avec précision (pas "améliorer la perf", mais "tenir une autonomie de 6 mois sur batterie LiPo de 2000 mAh").
- Un objectif peut être qualitatif ou quantitatif, mais doit être discriminant.

### Section `## Prochain rendu`

| Champ | Type | Obligatoire | Valeurs autorisées |
|-------|------|-------------|--------------------|
| `Date` | date ou `N/A` | oui | format `YYYY-MM-DD` ou littéralement `N/A` |
| `Nature` | enum ou `N/A` | oui | `démo`, `livraison client`, `soutenance`, `release`, `N/A` |
| `Contenu attendu` | string | oui | non vide ou `N/A` |

Cette section permet au Juge de calibrer le `timing_recommendation` : un projet à deux semaines de la livraison ne reçoit pas les mêmes suggestions qu'un projet en exploration libre.

### Section `## Composants`

Tableau Markdown avec exactement quatre colonnes : `Composant`, `Rôle`, `Statut décisionnel`, `Rôle pipeline`.

**Statut décisionnel** :
- `figé` — choix imposé, non négociable. Le Juge ne suggère jamais de remplacement.
- `validé` — choix actuel, ouvert à discussion. Le Juge peut suggérer alternatives si gain réel.
- `en évaluation` — pas encore tranché. Le Juge priorise les suggestions sur ces composants.

**Rôle pipeline** :
- `critique` — sans lui le système ne fonctionne pas. Tout changement est risqué.
- `support` — peut être substitué sans casser le système. Plus de souplesse.
- `accessoire` — option, amélioration. Substitution facile.

Au moins 1 ligne. Le tableau peut être long (pas de limite haute pratique).

### Section `## Stack software`

Tableau avec quatre colonnes : `Outil`, `Rôle`, `Version`, `Statut décisionnel`.

- `Version` : peut être une version exacte (`v1.2.3`), une plage (`>=1.2`), ou `N/A`.
- `Statut décisionnel` : mêmes valeurs que pour Composants.

Section obligatoire mais peut contenir un seul item (par exemple le langage principal) si le projet est essentiellement hardware.

### Section `## Interactions`

Liste à puces, format orienté `A → B` :
- `Capteur BME280 → ESP32 : mesures température/humidité/pression | I2C | 1 lecture/min`

- `→` est obligatoire pour matérialiser le sens de l'interaction.
- Au moins 1 interaction.
- **Validation niveau 3** : tous les `A` et `B` doivent apparaître dans la table `Composants` ou la table `Stack software`.

### Section `## Contraintes` — adaptative

C'est la section qui s'adapte à la diversité des projets.

**Règles** :
- Au moins une sous-section `###`.
- Sous-sections libres en titre (Performance, Énergie, Consommation, Environnementales, Connectivité, Budget, Réglementaires, Maintenance, etc.).
- Chaque sous-section contient au moins 1 critère sous forme de puce.
- Chaque critère a l'une des trois formes :
  - **Valeur définie** : `Autonomie : 6 mois sur batterie LiPo 2000 mAh`
  - **Non applicable** : `Connectivité 5G : N/A`
  - **À déterminer avec justification** : `Étanchéité : TBD — dépend du retour client sur le boîtier`

**Pourquoi cette structure** : tous les projets ont des contraintes mais pas les mêmes. Forcer une structure rigide produirait soit des cases vides ("nous n'avons pas de contraintes énergétiques" sur un projet web), soit l'omission de contraintes propres au projet.

### Section `## Contraintes non négociables`

Liste à puces des contraintes figées par décision externe (client, certification, choix stratégique). Différent de la section `Contraintes` qui décrit les contraintes physiques/techniques.

Exemples :
- `Certification CE obligatoire pour livraison Q4 2026.`
- `Code source en français pour conformité interne.`
- `Pas de cloud public sur ce projet.`

Peut être vide (`- Aucune` ou ne pas mettre de puce, juste laisser la section vide n'est pas accepté — utiliser explicitement `- Aucune`).

### Section `## Changements`

- Section auto-appendée par l'Interviewer en mode `integrate` après chaque modification validée.
- Format strict : `- YYYY-MM-DD : [résumé du changement]`
- Ordre chronologique inverse (le plus récent en haut) ou direct (le plus récent en bas) — choix à figer dans le code, recommandation : direct (append-only).
- Initialement vide : `- Aucun changement` à la création.

---

## Règles de validation niveau 1 — sections obligatoires

La couche 1 vérifie d'abord la **présence** des sections suivantes, dans cet ordre :

1. Titre H1 (`# ...`)
2. `## Identité`
3. `## Description`
4. `## Objectifs actifs`
5. `## Prochain rendu`
6. `## Composants`
7. `## Stack software`
8. `## Interactions`
9. `## Contraintes`
10. `## Contraintes non négociables`
11. `## Changements`

Toute absence ou inversion d'ordre échoue le niveau 1.

---

## Règles de validation niveau 2 — structure interne

La couche 1 vérifie ensuite la **structure interne** :

- **Identité** : tous les sous-champs présents, formats respectés (date ISO, enums valides).
- **Description** : entre 50 et 500 caractères, pas de Markdown autre que du texte.
- **Objectifs actifs** : ≥ 1 puce.
- **Prochain rendu** : tous les sous-champs présents, formats respectés.
- **Composants** : tableau valide à 4 colonnes, ≥ 1 ligne, valeurs énumérées valides.
- **Stack software** : tableau valide à 4 colonnes, ≥ 1 ligne.
- **Interactions** : ≥ 1 puce, présence du `→`, format `A → B : ...`.
- **Contraintes** : ≥ 1 sous-section `###`, chaque sous-section ≥ 1 puce, format de critère respecté (valeur définie / `N/A` / `TBD : ...`).
- **Contraintes non négociables** : ≥ 1 puce (peut contenir uniquement `Aucune`).
- **Changements** : ≥ 1 puce (peut contenir uniquement `Aucun changement`), entrées au format `YYYY-MM-DD : ...`.

---

## Règles de validation niveau 3 — cohérence sémantique

La couche 1 vérifie enfin la **cohérence sémantique interne** :

- **Cohérence entre Identité et titre H1** : `Identité > Nom` doit correspondre au titre H1.
- **Composants référencés dans Interactions** : tous les `A` et `B` des interactions doivent exister dans la table `Composants` ou la table `Stack software`.
- **Cohérence dates** : `Identité > Dernière mise à jour` ≤ aujourd'hui.
- **Cohérence date de rendu** : `Prochain rendu > Date` ≥ `Identité > Dernière mise à jour` (ou `N/A`).
- **Cohérence phase / statuts** : aucune contrainte sur les statuts en phase `déployé` — un composant `en évaluation` peut légitimement représenter un candidat à la substitution pour une version future.
- **Pas de doublon** dans les listes (composants, interactions, objectifs).

Une erreur niveau 3 retourne un message clair pointant l'incohérence (ex. `Composant 'BME680' référencé dans Interactions mais absent de la table Composants`).

---

## Schéma Pydantic correspondant

```python
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

PhaseType = Literal["exploration", "prototype", "pré-production", "déployé"]
DomaineType = Literal["hardware", "software", "hybride"]
StatutDecisionnelType = Literal["figé", "validé", "en évaluation"]
RolePipelineType = Literal["critique", "support", "accessoire"]
NatureRenduType = Literal["démo", "livraison client", "soutenance", "release", "N/A"]


class Identite(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    phase: PhaseType
    domaine: DomaineType
    derniere_mise_a_jour: date


class ProchainRendu(BaseModel):
    date: Optional[date]  # None si N/A
    nature: NatureRenduType
    contenu_attendu: str  # peut valoir "N/A"


class Composant(BaseModel):
    nom: str
    role: str
    statut_decisionnel: StatutDecisionnelType
    role_pipeline: RolePipelineType


class StackItem(BaseModel):
    outil: str
    role: str
    version: str  # libre : "v1.2.3" / ">=1.2" / "N/A"
    statut_decisionnel: StatutDecisionnelType


class Interaction(BaseModel):
    source: str
    target: str
    nature: str
    format: Optional[str] = None
    volume: Optional[str] = None


class CritereContrainte(BaseModel):
    nom: str
    valeur: str  # valeur, "N/A", ou "TBD : justification"


class SousSectionContraintes(BaseModel):
    titre: str
    criteres: list[CritereContrainte]


class Changement(BaseModel):
    date_changement: date
    resume: str


class ProjectModel(BaseModel):
    nom_projet: str  # titre H1
    identite: Identite
    description: str = Field(min_length=50, max_length=500)
    objectifs_actifs: list[str] = Field(min_length=1)
    prochain_rendu: ProchainRendu
    composants: list[Composant] = Field(min_length=1)
    stack_software: list[StackItem] = Field(min_length=1)
    interactions: list[Interaction] = Field(min_length=1)
    contraintes: list[SousSectionContraintes] = Field(min_length=1)
    contraintes_non_negociables: list[str] = Field(min_length=1)
    changements: list[Changement] = Field(min_length=1)

    @field_validator("nom_projet")
    @classmethod
    def nom_projet_match_identite(cls, v, info):
        # validation cross-field gérée dans une fonction de validation niveau 3 dédiée
        return v
```

(Note : la validation niveau 3 — cohérence cross-section comme "composant cité dans Interactions doit exister dans Composants" — est faite par une fonction dédiée plutôt que dans le `field_validator` Pydantic, pour clarté et messages d'erreur lisibles.)

---

## Exemple 1 — fiche minimale

```markdown
# Mini Robot Suiveur de Ligne

## Identité
- Nom : Mini Robot Suiveur de Ligne
- Phase : prototype
- Domaine : hardware
- Dernière mise à jour : 2026-04-15

## Description
Petit robot autonome qui suit une ligne tracée au sol grâce à des capteurs infrarouges. Projet pédagogique pour démonstration en école d'ingénieur.

## Objectifs actifs
- Suivre une ligne noire de 2 cm sur sol clair à 0,3 m/s sans perte de cap
- Tenir 30 minutes d'autonomie sur batterie 9V

## Prochain rendu
- Date : 2026-06-30
- Nature : démo
- Contenu attendu : démonstration en classe sur parcours en huit

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| Arduino Uno | Microcontrôleur | validé | critique |
| TCRT5000 x2 | Capteurs IR ligne | validé | critique |
| Moteur DC + driver L298N | Propulsion | validé | critique |
| Châssis 3D printé | Structure | en évaluation | support |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| Arduino IDE | Programmation | 2.x | validé |

## Interactions
- TCRT5000 → Arduino Uno : valeurs analogiques | A0/A1 | 100 Hz
- Arduino Uno → L298N : commande PWM | digital pins | continue

## Contraintes

### Énergie
- Autonomie : 30 minutes minimum sur batterie 9V
- Tension d'alimentation : 7-12V

### Performance
- Vitesse cible : 0,3 m/s
- Précision suivi : ±5 mm sur ligne 2 cm

## Contraintes non négociables
- Aucune

## Changements
- Aucun changement
```

---

## Exemple 2 — fiche complète (Station météo connectée ESP32)

```markdown
# Station Météo Connectée ESP32

## Identité
- Nom : Station Météo Connectée ESP32
- Phase : prototype
- Domaine : hybride
- Dernière mise à jour : 2026-05-04

## Description
Station météo autonome basée ESP32 mesurant température, humidité, pression atmosphérique et position GPS. Transmission des données par LoRaWAN vers une passerelle locale, fonctionnement sur panneau solaire et batterie LiPo. Destiné à un déploiement outdoor sans intervention humaine pendant 6 mois.

## Objectifs actifs
- Tenir 6 mois d'autonomie en outdoor sans intervention sur batterie LiPo 2000 mAh + panneau solaire 5W
- Transmettre une mesure complète toutes les 15 minutes par LoRaWAN sur 5 km en zone semi-rurale
- Précision température ±0.5°C, humidité ±3% RH, pression ±1 hPa

## Prochain rendu
- Date : 2026-09-15
- Nature : soutenance
- Contenu attendu : prototype fonctionnel, 1 mois de données collectées et visualisées

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| ESP32-WROOM-32E | Microcontrôleur principal + LoRa | validé | critique |
| BME280 | Capteur T°/humidité/pression | validé | critique |
| GP-20U7 | Module GPS | validé | support |
| Panneau solaire 5W 6V | Recharge | validé | critique |
| Batterie LiPo 2000 mAh 3.7V | Stockage énergie | validé | critique |
| Module LoRa SX1276 | Transmission longue distance | validé | critique |
| Boîtier IP65 imprimé 3D | Protection environnement | en évaluation | support |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| ESP-IDF | Framework principal | 5.x | validé |
| LoRaWAN stack (LMIC) | Stack LoRaWAN | dernière stable | validé |
| MicroPython | Évalué comme alternative | 1.22+ | en évaluation |

## Interactions
- BME280 → ESP32 : mesures T°/humidité/pression | I2C | 1 lecture/15 min
- GP-20U7 → ESP32 : trames NMEA position | UART 9600 | 1 lecture/15 min
- ESP32 → SX1276 : trame LoRaWAN | SPI | 1 émission/15 min
- Panneau solaire → Batterie LiPo : recharge | régulateur MPPT | continu si soleil
- Batterie LiPo → ESP32 : alimentation | régulateur 3.3V | continu

## Contraintes

### Énergie
- Autonomie cible : 6 mois sans intervention
- Consommation moyenne max : 5 mA en moyenne sur cycle 15 min
- Mode sommeil profond ESP32 entre mesures : < 50 µA

### Environnementales
- Plage température opérationnelle : -10°C à +50°C
- Étanchéité : IP65 minimum
- UV : tenue 6 mois exposition directe

### Connectivité
- Portée LoRaWAN : 5 km en zone semi-rurale
- Latence acceptable : 15 min (pas temps réel)
- Connectivité 5G : N/A
- Connectivité Wi-Fi : TBD — utile en mode debug, à arbitrer selon impact conso

### Budget
- Coût matériel cible : < 80€ par station
- Coût logiciel : 0€ (open-source uniquement)

## Contraintes non négociables
- Pas de cloud commercial pour les données — passerelle LoRaWAN locale obligatoire
- Code source open-source MIT pour la soutenance

## Changements
- 2026-04-20 : ajout de l'objectif de précision pression ±1 hPa après échange avec le tuteur
- 2026-04-28 : remplacement BMP280 par BME280 pour ajouter mesure d'humidité
```

---

## Notes d'implémentation

- L'Interviewer génère ce `.md` section par section. À chaque section, il valide niveau 1+2 partiellement, et fait une validation niveau 3 globale en fin de questionnaire.
- Le mode `integrate` modifie ciblement les sections impactées par une `ValidatedSuggestion`, puis revalide intégralement les trois couches.
- Le `.md` est lu directement par les agents en aval. Aucune transformation intermédiaire — c'est ce qui garantit que la fiche est l'unique source de vérité.
