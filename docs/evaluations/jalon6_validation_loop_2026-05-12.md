# Jalon 6 — Boucle de validation utilisateur

**Date** : 2026-05-12
**Statut** : implémenté, smoke-test OK, test interactif end-to-end à faire par l'utilisateur.

## Objectif

Fermer la boucle du pipeline : passer des `ValidatedSuggestion` produites par
le Rapporteur à des modifications effectives de la fiche projet `.md`, sous
contrôle explicite de l'utilisateur.

## Architecture

Le Jalon 6 introduit **deux commandes CLI** qui s'enchaînent et **un module TUI**.

```
[Run pipeline]
  └─> 04_validated_suggestions.json   (Rapporteur)
        │
        ▼
[applied-fox validate --run <run_dir>]
  └─> TUI Rich (accept/reject/defer)
        └─> 05_user_validated.json    (décisions utilisateur)
              │
              ▼
[applied-fox interview integrate --project X --validated Y]
  └─> Pour chaque "accept" :
        1. apply_suggestion (dialogue open_questions)
        2. generate_md
        3. 3 couches de validation (structurelle, transmission, humaine)
        4. write_text si OK
```

## Choix architecturaux (et leur "pourquoi")

### 1. Séparation `validate` / `integrate` en deux commandes

**Choix** : deux commandes plutôt qu'un flow unifié.

**Pourquoi** :
- L'utilisateur peut valider rapidement à un moment, puis appliquer plus tard
  quand il a l'énergie de répondre aux questions ouvertes.
- `05_user_validated.json` est un artefact auditable séparé. Pour le portfolio,
  on peut montrer les décisions de validation comme étape distincte.
- Permet de **rejouer** l'intégration sans reposer toutes les questions de validation.

### 2. Batch séquentiel, pas tout-en-un

**Choix** : `run_integrate_batch` applique les suggestions une par une, rechargeant
le `.md` à chaque tour.

**Pourquoi** :
- Évite les conflits si deux suggestions touchent au même composant.
- Auditable : chaque suggestion crée son propre item dans la section Changements.
- **Reprenable** : un crash en milieu de batch laisse l'état cohérent.
- Plus simple à débugger qu'un système de "transaction" globale.

### 3. Réutilisation maximale de l'existant

- `apply_suggestion` (Jalon 2) est conservé tel quel.
- `run_integrate` (mono-suggestion) coexiste avec `run_integrate_batch` :
  utile pour les tests unitaires.
- Les 3 couches de validation (structurelle, transmission, humaine) sont
  appliquées par suggestion, garantissant que le `.md` ne devient jamais
  invalide même en cas d'échec.

### 4. TUI Rich, pas full-screen keyboard-driven

**Choix** : prompts séquentiels Rich (Panel + Prompt) plutôt qu'un `live` plein écran.

**Pourquoi** :
- Cohérent avec le reste de l'UX (`interview create/update`).
- Accessible (SSH, terminaux limités, lecteurs d'écran).
- Permet à l'utilisateur de lire chaque suggestion à son rythme, sans timer.
- Plus simple à maintenir.

## Sortie attendue

Un appel typique produit :

| Fichier | Contenu | Producteur |
|---|---|---|
| `04_validated_suggestions.json` | N suggestions structurées | Rapporteur (Jalon 5c) |
| `05_user_validated.json` | N décisions (accept/reject/defer + raison) | TUI validate |
| `<projet>.md` modifié | Suggestions acceptées intégrées + log Changements | interview integrate |

## Smoke-test 2026-05-12

```python
from src.validation.tui import load_suggestions, save_decisions, load_decisions
suggestions = load_suggestions(run_dir / "04_validated_suggestions.json")
# → Loaded 7 suggestions
# Round-trip save/load: OK
```

Imports `run_integrate_batch` et CLI registration `validate` + `interview integrate` :
vérifiés (test inspection.signature + `app.registered_commands`).

## Test interactif manuel à faire

L'utilisateur doit lancer dans l'ordre :

```bash
applied-fox validate --run ~/.applied-fox/runs/20260512_092234_esp32_weather_station
# → TUI s'ouvre, propose 7 suggestions, demande décisions
# → écrit 05_user_validated.json

applied-fox interview integrate \
    --project ~/.applied-fox/projects/esp32_weather_station.md \
    --validated ~/.applied-fox/runs/20260512_092234_esp32_weather_station/05_user_validated.json
# → Pour chaque accept :
#   - récap suggestion
#   - questions ouvertes (si présentes)
#   - récap modifications
#   - 3 couches de validation
#   - write_text
```

## Limites connues / Jalon 7+

- Pas de **résumé global** pré-intégration des suggestions acceptées avant
  de commencer la boucle (chaque suggestion est présentée individuellement
  par `apply_suggestion`).
- Pas de **mode dry-run** (`--dry-run` qui simule sans écrire).
- Pas de **branchement par lots** (intégrer 3 suggestions cohérentes ensemble,
  puis rejouer le pipeline avant les 3 suivantes).
- L'utilisateur doit recopier manuellement les chemins. Le **menu interactif
  Jalon 7** unifiera ça (sélection projet → run le plus récent auto).

Aucun de ces points ne bloque la démonstrabilité MVP.

## Status

✅ Code en place
✅ Imports et signatures vérifiés
✅ Persistance JSON round-trip OK
⏳ Test interactif end-to-end à faire par l'utilisateur
⏭️ Jalon 7 : menu interactif multi-projets
