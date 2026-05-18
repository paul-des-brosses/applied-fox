# Jalon 7 — Menu interactif multi-projets

**Date** : 2026-05-12
**Statut** : implémenté, imports + discovery vérifiés sur données réelles.

## Objectif

Rendre `applied-fox` utilisable sans copier de chemins. Tout part de la
TUI ouverte par la commande nue : sélection projet → action → exécution.

## Architecture

```
applied-fox            (sans argument)
    │
    ▼
src/cli.py::main()  (Typer callback invoke_without_command=True)
    │
    ▼
src/menu/main.py::run_menu(config)
    │
    ├── list_projects(projects_dir)         → ProjectEntry[]
    ├── select_project(entries)             → choix
    │
    └── project_action_loop(entry, ...)
            │
            ├── _action_run_chain
            │     ├── run_pipeline_with_progress (thread + polling artefacts)
            │     ├── _action_validate (TUI Rich validation)
            │     └── _action_integrate (run_integrate_batch)
            │
            ├── view_past_runs   (ouverture HTML via webbrowser.open)
            ├── _action_validate_latest
            ├── _action_integrate_latest
            └── _action_update (run_update)
```

## Décisions clés

### 1. Pipeline en thread + polling d'artefacts pour la barre de progression

**Pourquoi** : LangGraph n'expose pas nativement de hook de progression
fin sans modifier chaque agent. Le polling des fichiers `01_*.json`,
`02_*.json`, etc. est **non-invasif** : aucun agent n'est modifié.

**Limites** :
- L'avancement intra-étape est interpolé linéairement (rough mais lisible).
- L'ETA affichée est calibrée RTX 3070 + profile small. Sur d'autres
  matériels, le temps réel diverge — mais la barre saute à 100 % quand
  l'artefact apparaît, donc pas de faux suspense.
- Avec cache LLM chaud, les 4 étapes finissent en quelques secondes : la
  barre passe à 100 % d'un coup. C'est OK, juste un peu rapide pour être
  lisible.

### 2. Action "Consulter runs passés" → ouverture HTML navigateur

Le rapport HTML est déjà produit par le Rapporteur (Jalon 5c). Le
réinjecter dans la TUI demanderait un parseur Markdown intégré et serait
moins riche que le HTML stylisé. `webbrowser.open(target.as_uri())` est
multi-plateforme et "just works".

### 3. Chaînage automatique run → validate → integrate

Avec confirmations entre étapes. Évite à l'utilisateur de re-naviguer
dans le menu après un run. Pour le portfolio, montre le workflow complet
en une session.

### 4. Wrap des `sys.exit` de l'interviewer

`run_create` et `run_update` historiques font `sys.exit(0)` en cas
d'abandon — comportement OK en mode CLI direct, mais fatal pour une boucle
de menu. Wrap dans `try / except SystemExit: pass`. Solution minimale et
sans risque ; refactor profond non nécessaire pour le MVP.

### 5. `projects_dir` configurable

Ajout d'un nouveau champ `paths.projects_dir` dans `config.yaml`. Défaut
`~/.applied-fox/projects`, mais permet de pointer vers le dossier où
l'utilisateur garde réellement ses fiches.

## Vérifications faites

```python
# Discovery sur projets_dir du repo
projects = list_projects(projects_dir)
# → Discovered 1 project(s):
#   - Station Météo Connectée ESP32 | phase=prototype | maj=2026-05-04

# Discovery des runs
runs = find_runs_for_project(runs_root, 'esp32_weather_station')
# → 19 runs trouvés
# → Plus récent : 2026-05-12 09:22 (79 findings, 7 suggestions, HTML OK)
```

Wiring CLI :
- `app.registered_callback` → `main` (Typer)
- Top commands : `run`, `validate`
- Group : `interview` → `create / skeleton / update / integrate`

## À tester interactivement par l'utilisateur

1. `applied-fox` (nu) → la TUI s'ouvre, liste 1 projet.
2. Choisir le projet → menu d'actions.
3. Choix `2` (runs passés) → ouvre un rapport HTML dans le navigateur.
4. Choix `1` (nouveau run) → barre de progression réelle pendant ~25 min,
   puis enchaîne sur validate + integrate.

## Limites connues (V2)

- Pas de **multi-projet batch** (un projet à la fois).
- Pas de **diff entre runs** ("qu'est-ce qui a changé depuis la dernière fois ?").
- Pas de **suppression de runs anciens** depuis la TUI (à faire manuellement).
- Le clignotement Rich Progress peut être imparfait sur certains terminaux
  Windows (cmd.exe). Le `wt.exe` / Windows Terminal donne le meilleur rendu.

## Status

✅ Code en place
✅ Imports + discovery validés sur données réelles
✅ Doc utilisateur à jour (GETTING_STARTED.md)
⏳ Test interactif de bout en bout à faire par l'utilisateur
⏭️ Jalon 8 : polish, doc démo portfolio, packaging
