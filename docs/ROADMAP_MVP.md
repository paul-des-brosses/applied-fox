# ROADMAP MVP — Applied Fox

Cette roadmap définit les **8 jalons** qui mènent au MVP. Chaque jalon est démontrable indépendamment et peut servir de point d'arrêt sans casser ce qui précède.

**Pas d'estimation en jours figée.** Méthode : itération jalon par jalon. Un jalon est terminé quand sa validation explicite est passée.

## Statut au 2026-05-13 — MVP livré, cible 80 % alignement atteinte post-MVP

| Jalon | Sujet | Statut | Eval |
|---|---|---|---|
| 0 | Setup environnement | ✅ Terminé | — |
| 1 | Interview create + 3 couches | ✅ Terminé | `docs/evaluations/jalon1_*` |
| 1bis | UX Interview (skeleton, enrichment, review, back, consistency) | ✅ Terminé | — |
| 2 | Modes update + integrate | ✅ Terminé | — |
| 3 | Éclaireur Reddit minimal | ✅ Terminé | `docs/evaluations/jalon3_*` |
| 4 | Éclaireur multi-sources (Reddit + RSS + GitHub) | ✅ Terminé | `docs/evaluations/jalon4_*` |
| 5 | Pipeline 4 agents complet (Intégrateur + Juge + Rapporteur) | ✅ Terminé | `docs/evaluations/jalon5*_*` |
| 6 | Boucle validation + intégration | ✅ Terminé | `docs/evaluations/jalon6_*` |
| 7 | Menu multi-projets | ✅ Terminé | `docs/evaluations/jalon7_*` |
| 8 | Polish + démo portfolio + pertinence | ✅ Terminé (qwen3:8B Juge, 70-82% aligné sur 3 projets, 3-profils supprimés) | `docs/evaluations/jalon8_*` + `docs/evaluations/modeles_perf_2026-05-13.md` |

Octopart a été poussé en V2 (voir [`BACKLOG.md`](BACKLOG.md)).

Les validations transverses (hot-swap, adaptabilité hardware, économie API, chaîne complète) sont rattachées à des jalons précis pour éviter qu'elles passent à la trappe.

---

## Jalon 0 — Setup environnement et squelette projet

### Objectif
Disposer d'un projet installable proprement en moins de 10 minutes sur une machine vierge.

### Livrables
- Repo Git initialisé avec la structure de dossiers complète (cf. [`CLAUDE.md` Règle 6](CLAUDE.md)).
- `pyproject.toml` avec les dépendances core (cf. [`DEPENDENCIES.md`](DEPENDENCIES.md) — bloc "Core" + "Providers locaux").
- `setup.sh` qui : crée un venv, installe les dépendances, vérifie la présence d'Ollama, télécharge le modèle 7B par défaut.
- Configuration par défaut `~/.applied-fox/config.yaml` (profile `small`).
- Fichier `.env.example` documentant les variables d'environnement attendues.
- README minimal à la racine (sera finalisé au Jalon 8 Polish portfolio).
- Squelette des 5 modules d'agents avec docstring + signature de la fonction principale.
- Squelette de `src/llm/__init__.py` exposant `get_llm(role, config)` (peut renvoyer un stub au début).

### Validation explicite
- `bash setup.sh` sur une machine vierge (Linux ou WSL2) exécute sans erreur en moins de 10 minutes.
- `python -c "from src.llm import get_llm; print(get_llm('interviewer', {}))"` renvoie un objet ChatOllama (ou stub clair).
- L'arborescence de fichiers correspond exactement à la structure documentée.

---

## Jalon 1 — Module Interview en CLI/TUI fonctionnel (mode `create` + 3 couches de validation)

### Objectif
Produire un `.md` projet complet et validé à partir d'un dialogue avec l'utilisateur, sans aucun agent de veille.

### Livrables
- `src/interview/create.py` — questionnaire guidé section par section, re-questionnement si réponse floue.
- `src/agents/interviewer.py` — prompts système et utilisateur du mode `create`.
- `src/validation/structural.py` — couche 1 (Pydantic + parsers Markdown) avec les trois niveaux de validation.
- `src/validation/transmission.py` — couche 2 (test de transmission par LLM tiers).
- `src/validation/human.py` — couche 3 (récap TUI Rich + validation utilisateur).
- Schéma Pydantic `ProjectModel` complet (cf. [`MD_SCHEMA.md`](MD_SCHEMA.md)).
- CLI : `applied-fox interview create` lance le questionnaire et écrit `~/.applied-fox/projects/[nom].md`.
- Évaluation Opus 4.7 baseline du module Interview, sauvegardée dans `docs/evaluations/jalon1_interview_baseline.md`.

### Validation explicite
- L'utilisateur peut produire une fiche complète pour un projet test (par exemple : la station météo ESP32 du projet d'exemple).
- Le `.md` produit passe les trois couches sans intervention manuelle correctrice.
- L'évaluation Opus 4.7 retourne une note ≥ 7/10, infos manquantes uniquement de second ordre.

### Validation transverse
- Le module Interview tourne **en local** sur Ollama 7B Q4 (contrainte MVP). Test : couper l'accès internet pendant l'interview, le module continue de fonctionner.

---

## Jalon 1bis — Améliorations UX du module Interview

### Contexte
Ce jalon formalise rétroactivement trois améliorations UX du module Interview qui ont émergé pendant le développement à partir des retours de l'utilisateur principal. Elles ne figuraient pas dans le scope initial du Jalon 1 mais ont été codées avant Jalon 4. Officialisées ici pour préserver la traçabilité.

### Objectif
Rendre le module Interview utilisable par un débutant sans frustrations bloquantes, sans dégrader la qualité des fiches produites pour les utilisateurs experts.

### Livrables

**1. Mode `interview skeleton`** (`src/interview/skeleton.py`)
- Génère un fichier `.md` pré-structuré avec commentaires d'aide et placeholders explicites.
- Ouvre le fichier dans l'éditeur système (cross-platform : `os.startfile` Windows, `open` macOS, `$EDITOR` Linux).
- CLI : `applied-fox interview skeleton`.
- Cas d'usage : utilisateur expert qui préfère remplir directement dans son éditeur plutôt que de passer par le questionnaire interactif.

**2. Système d'enrichissement remplaçant le validateur strict** (cf. [`DECISIONS.md` §19](DECISIONS.md))
- `_ask_with_enrichment()` accepte la réponse initiale, propose UNE question de précision optionnelle.
- Mot-clé `skip` pour conserver la réponse initiale telle quelle.
- `skip` bloqué automatiquement sur les sections critiques (Description, Objectifs, Contraintes) si la réponse initiale est < 4 mots et sans indicateur technique.
- La mécanique skip est affichée dans le panneau d'introduction du questionnaire.

**3. Récap + correction post-questionnaire**
- `_show_review_and_correct(data)` : affichage numéroté de tous les champs saisis avant sauvegarde.
- Édition par numéro (re-saisie d'un champ avec valeur courante pré-remplie).
- Boucle jusqu'à validation par Entrée.

**4. Commande `back` pendant le questionnaire**
- Mot-clé `back` reconnu à chaque question texte du questionnaire.
- Permet de revenir à l'étape précédente sans attendre le récap final.
- Refusé sur la première question (pas d'étape précédente).
- Sur la première question d'un item de liste (composant N+1), `back` revient au dernier champ du composant N avec valeurs courantes éditables.

**5. Vérifications de cohérence post-questionnaire**
- `_consistency_check(data)` (déterministe) : composants orphelins, interactions fantômes.
- `_infer_missing_components(data, llm)` : un seul appel LLM en fin de questionnaire pour suggérer des composants potentiellement oubliés au vu de la description.
- Affichage non-bloquant : l'utilisateur peut ignorer toutes les alertes.

### Validation explicite
- L'utilisateur peut taper `skip` sur une question d'enrichissement et voir sa réponse initiale conservée.
- Sur "description = projet" (3 mots, pas d'indicateur), `skip` est explicitement refusé.
- Le récap final permet de modifier n'importe quel champ par numéro et de voir le changement reflété immédiatement.
- `back` à la 5e question revient à la 4e avec la valeur précédente pré-remplie.
- Lancer le questionnaire, déclarer un composant non utilisé dans une interaction → vérification finale signale l'orphelin.

### Validation transverse
- Aucun import direct d'un provider LLM dans `src/interview/skeleton.py` — utilise `os.startfile` / `subprocess` uniquement, pas de LLM.
- Le skeleton produit reste compatible avec `parse_and_validate()` après remplissage.

---

## Jalon 2 — Mode `update` et boucle d'intégration

### Objectif
Permettre la modification d'un `.md` existant via dialogue, en conservant les invariants de validation.

### Livrables
- `src/interview/update.py` — charge un `.md` existant, propose des révisions ciblées.
- `src/interview/integrate.py` — accepte un objet `ValidatedSuggestion` (mode `integrate`).
- Mécanisme d'append à la section "Changements" du `.md` à chaque modification validée.
- Les trois couches de validation sont **réappliquées** au `.md` modifié (symétrie création / modification).
- CLI : `applied-fox interview update --project [path]`.

### Validation explicite
- Charger un `.md` valide, en modifier un composant via dialogue, le `.md` reste valide aux trois couches.
- La section "Changements" contient une nouvelle ligne au format `YYYY-MM-DD : [résumé]`.
- Tester le mode `integrate` avec un objet `ValidatedSuggestion` construit à la main : la modification s'applique correctement, les `open_questions` sont posées à l'utilisateur, le `.md` final est valide.

---

## Jalon 3 — Premier agent Éclaireur sur Reddit (pipeline LangGraph minimal)

### Objectif
Disposer d'un pipeline LangGraph fonctionnel à un seul agent (Éclaireur) qui produit des `Finding` structurés à partir de Reddit.

### Livrables
- `src/sources/reddit.py` — recherche Reddit avec PRAW, retour de `RawFinding`.
- `src/agents/eclaireur.py` — prompt + parsing en `Finding` Pydantic, retry sur erreur.
- `src/graph/` — squelette LangGraph avec `TechWatchState`, un seul nœud (Éclaireur), pas encore de branchement.
- Filtre déterministe en amont du LLM (alignement composants/objectifs, fraîcheur, score communautaire minimum).
- Cache `requests-cache` configuré pour Reddit (TTL 12h).
- Mode incrémental : lecture/écriture de `~/.applied-fox/state/[projet]_seen.json`.
- Sauvegarde des artefacts `01_eclaireur_findings.json` et `01_eclaireur_sources.json` dans le dossier de run.
- CLI : `applied-fox run --project [path]` lance le pipeline minimal.

### Validation explicite
- Sur le projet d'exemple ESP32, l'Éclaireur produit ~10-20 `Finding` en moins de 5 minutes (machine MSI).
- Le filtre déterministe rejette > 50% des résultats Reddit bruts (consigner le ratio dans `01_eclaireur_sources.json`).
- Mode incrémental : un second run sur le même projet sans changement affiche 0 nouveau finding.
- Test cache : un run dans la fenêtre TTL ne déclenche aucun appel Reddit (vérifiable via les logs ou via LangFuse si activé).

### Validation transverse — Hot-swap structurel
- L'agent Éclaireur n'importe **pas directement** ChatOllama. Il passe par `get_llm("eclaireur", config)`.
- Test : changer le modèle dans la config (ex. `mistral:7b` → `qwen:7b`) et relancer ; aucune ligne de code modifiée. Pipeline fonctionne.

---

## Jalon 4 — Éclaireur multi-sources avec cache et mode incrémental complet

### Objectif
Activer les trois sources MVP avec leurs patterns d'intégration distincts, et valider le filtre déterministe en conditions réelles. Octopart a été poussé en V2 backlog (cf. [`BACKLOG.md`](BACKLOG.md)).

### Livrables
- `src/sources/github.py` — recherche de repos liés aux composants, token via `GITHUB_TOKEN`, TTL 24h.
- `src/sources/rss.py` — Hackaday, CNX-Software, Adafruit Blog, Electronics Weekly, EE Times via `feedparser`, TTL 24h.
- Reddit (déjà en place du Jalon 3) consolidé.
- Configuration sources dans `config.yaml` (cf. [`CONFIG_SCHEMA.md`](CONFIG_SCHEMA.md)).
- Dégradation gracieuse : si une source échoue, le pipeline continue (warning, pas d'arrêt).
- Filtre déterministe enrichi : seuils par source, déduplication cross-source par hash.

### Validation explicite
- Sur le projet d'exemple ESP32, les quatre sources retournent des résultats. Si une est down, le pipeline produit un rapport diminué mais valide.
- Le filtre déterministe élimine 60-70% des résultats bruts cumulés (consigner le ratio).
- Vérifier que les clés API ne fuient ni dans la config persistée, ni dans les logs, ni dans les artefacts de run.

---

## Jalon 5 — Pipeline complet à 4 agents

### Objectif
Compléter le pipeline avec Intégrateur, Juge, Rapporteur. Première version du rapport final.

### Livrables
- `src/agents/integrateur.py` — produit `IntegrationVerdict` à partir d'un `.md` + `Finding`.
- `src/agents/juge.py` — produit `JudgeVerdict` à partir d'un `.md` + `Finding` + `IntegrationVerdict`.
- `src/agents/rapporteur.py` — synthèse Markdown + production des `ValidatedSuggestion` pour les findings retenus.
- Branchement conditionnel dans le graphe : si `integrable=False`, court-circuit du Juge.
- `src/reporting/` — génération du Markdown final + conversion HTML via `markdown2` ou `mistune` + template HTML simple.
- Sauvegarde de tous les artefacts intermédiaires dans `runs/[timestamp]_[projet]/`.
- Évaluation Opus 4.7 baseline du pipeline complet, sauvegardée dans `docs/evaluations/jalon5_veille_baseline.md`.

### Validation explicite
- Pipeline bout en bout sur le projet d'exemple : Éclaireur → Intégrateur → Juge → Rapporteur, en moins de 15 minutes sur la machine MSI.
- Le rapport final contient des sections "À considérer maintenant", "À noter pour plus tard", "Rejetés", "Sources consultées", "Métadonnées du run".
- L'évaluation Opus 4.7 retourne : 80% suggestions alignées avec objectifs actifs, 0 non alignée, note ≥ 6/10.
- Taux de retry Pydantic mesuré : < 5%.

### Validation transverse — Adaptabilité hardware
- **Bascule de modèle Ollama 7B vers 14B** (changement de profile machine `small` → `medium`) **sans modification de code, en moins de 5 minutes**. Une seule ligne de config change.
- Pipeline complet tourne sur la machine UX3402Z (16 Go RAM, GPU intégré) en profile `small`, en moins de 30 minutes.

---

## Jalon 6 — Boucle de validation et modification du `.md`

### Objectif
Boucler la chaîne complète : rapport → validation utilisateur → intégration via Interviewer → `.md` modifié.

### Livrables
- Ouverture automatique du rapport HTML dans le navigateur par défaut, avec fallback Markdown brut.
- TUI Rich qui prompte `Valider rapport (Y/N)`.
- Si `Y` : itération sur les `ValidatedSuggestion` une par une.
- Pour chaque suggestion : appel de l'Interviewer en mode `integrate` avec l'objet `ValidatedSuggestion`.
- L'Interviewer dialogue pour clarifier les `open_questions`, modifie le `.md`.
- Le `.md` modifié repasse les **trois couches de validation** (couche 1, couche 2, couche 3).
- Append à la section "Changements" + diff sauvegardé dans `06_md_diffs/`.
- Sauvegarde de `05_validated_suggestions.json`.

### Validation explicite — chaîne complète bout-en-bout
- Sur le projet d'exemple : passage complet de `applied-fox interview create` → édition manuelle pour ajouter un objectif actif → `applied-fox run` → validation d'au moins une suggestion → `.md` modifié et valide → `applied-fox run` à nouveau, le finding correspondant n'est plus présenté (mode incrémental).
- Vérifier qu'une modification fait vraiment passer les trois couches (pas de raccourci).
- Tester l'annulation (`N`) : le `.md` reste inchangé.

---

## Jalon 7 — Multi-projets et configuration complète

### Objectif
Permettre à un utilisateur de gérer plusieurs projets en parallèle, avec une configuration claire.

### Livrables
- TUI menu interactif qui scanne `~/.applied-fox/projects/` et liste les projets disponibles (`applied-fox` sans argument).
- CLI : `applied-fox run --project [nom_ou_path]`, `applied-fox interview create`, `applied-fox interview update --project [...]`.
- Spec config complète documentée dans [`CONFIG_SCHEMA.md`](CONFIG_SCHEMA.md), template fourni à l'install.
- Trois exemples de configuration (small / medium / démo) dans `examples/configs/`.
- Validation de la config au démarrage (Pydantic), erreurs lisibles.

### Validation explicite — économie API et cohérence multi-projets
- Trois projets différents dans `~/.applied-fox/projects/` : station météo ESP32 (exemple) + 2 autres (Forest of Senses ou Lightning Simulation pour dogfooding).
- Lancer la veille sur les trois successivement. Chaque projet a son propre state incrémental, son propre dernier rapport.
- Le cache `requests.sqlite` est partagé : si deux projets référencent un même composant, la seconde requête ne déclenche pas d'appel API.
- Vérifier que les configurations utilisateur surchargent correctement les défauts.

---

## Jalon 8 — Démo publique et polish portfolio

### Objectif
Rendre le projet présentable publiquement, démontrable en moins de 30 minutes par un dev externe.

### Livrables
- `README.md` final : storytelling, démo, quickstart, différenciation.
- `GETTING_STARTED.md` détaillé : install pas à pas, premier run, troubleshooting commun.
- **Démo statique** : projet d'exemple ESP32 complet + dossier `runs/` pré-exécuté + rapport HTML rendu via GitHub Pages.
- **Démo vidéo** : GIF court (< 30 sec, scène : interview → run → rapport) embarqué dans le README + vidéo plus longue (~3-5 min) sur YouTube ou Loom.
- **Démo live** : `setup.sh` qui rend le projet utilisable en moins de 30 min sur une machine vierge.
- Section "Pourquoi j'ai construit ça" dans le README, avec lien narratif vers Forest of Senses, Lightning Simulation, Digital Twin Percheron.
- Section différenciation (vs Aider/Cursor, vs Devin, vs PaperQA, vs Octopart, vs Google Alerts).
- Évaluation Opus 4.7 finale, sauvegardée dans `docs/evaluations/jalon8_final.md`.
- Repo épinglé GitHub, mention LinkedIn, lien CV.

### Validation explicite
- Trois camarades de promo lisent le README et comprennent l'outil en moins de 30 secondes.
- Un dev externe clone le repo et fait tourner la démo en moins de 30 minutes (validation à demander à au moins une personne).
- Évaluation Opus 4.7 finale au moins équivalente aux baselines des Jalons 1 et 5.
- Au moins **une suggestion produite par l'outil sur un projet perso a réellement changé une décision** (dogfooding).

---

## Validation finale du MVP — trois conditions absolues

Le MVP est livré quand les trois conditions suivantes sont satisfaites :

1. **Chaîne complète bout-en-bout** sans intervention manuelle correctrice : `applied-fox interview create` → édition → `applied-fox run` → validation rapport → suggestions intégrées → `.md` modifié → `applied-fox run` suivant montrant le mode incrémental fonctionnel.
2. **Dogfooding réussi** : l'utilisateur a utilisé l'outil sur ses propres projets et au moins une suggestion a concrètement changé quelque chose.
3. **Démo accessible à un dev externe en moins de 30 minutes** depuis le clone du repo.

---

## Critères de succès quantitatifs (transverses, mesurés au fil des jalons)

- Temps de veille : < 15 min sur la machine MSI (RTX 3070), 25-30 min sur l'UX3402Z.
- Taux de retry Pydantic : < 5%.
- ≥ 3 projets analysables sans modification de code.
- Hot-swap de modèle : < 5 min via une seule ligne de config.
- Adaptabilité hardware : tourne sur les deux machines de l'utilisateur.

---

## Critères de succès qualitatifs

- README < 5 min de lecture, accessible à un étudiant en informatique.
- `GETTING_STARTED.md` détaillé suffisant pour un dev externe.
- Décisions techniques défendables en entretien (cf. [`DECISIONS.md`](DECISIONS.md) comme support).
- Évaluation Opus 4.7 finale conforme aux seuils baseline.

---

## Évaluations Opus 4.7 — protocole

Les évaluations LLM-as-a-judge sont insérées à trois jalons :

| Jalon | Évaluation | Fichier |
|-------|------------|---------|
| 1 | Baseline Interview | `docs/evaluations/jalon1_interview_baseline.md` |
| 5 | Baseline Veille | `docs/evaluations/jalon5_veille_baseline.md` |
| 8 | Évaluation finale | `docs/evaluations/jalon8_final.md` |

### Évaluation Interview
- **Input** : `.md` produit + résumé du test de transmission.
- **Questions à Opus** : représentation du projet, divergences avec la vérité terrain, infos manquantes, note /10.
- **Critère succès** : note ≥ 7/10, infos manquantes de second ordre uniquement.

### Évaluation Veille
- **Input** : `.md` projet + rapport final + reasoning files (`02_integrateur_reasoning.md`, `03_juge_reasoning.md`).
- **Questions à Opus** : alignement de chaque suggestion avec objectifs, points faibles du raisonnement, angles non couverts, valeur globale /10.
- **Critère succès** : 80% suggestions alignées, 0 non alignée, note ≥ 6/10.

Les évaluations sont conservées dans `docs/evaluations/` pour traçabilité historique.
