# Jalon 8 — Polish & démo portfolio

**Date** : 2026-05-12
**Statut** : code/doc complétés. Reste les livrables côté utilisateur (démo
vidéo, dogfooding réel sur projet perso, partage public).

## Périmètre de ce Jalon 8

Le Jalon 8 selon `ROADMAP_MVP.md` mélange du code (mineur), de la doc
(majeure), et des activités côté utilisateur (vidéo, dogfooding, lecture
par camarades de promo). Cette eval découpe précisément ce qui a été
livré côté code/doc, et ce qui reste à faire côté utilisateur.

## Livrables ✅ Terminés (code/doc)

### 1. README.md portfolio-ready
- Pitch en 30 secondes lisible par un non-initié.
- Quickstart 5 min vérifiable.
- Section "Pourquoi ce projet existe" — narratif court, ancré dans les
  douleurs concrètes (EOL composants, veille hardware bruyante, outils
  généralistes qui ne connaissent pas ton projet).
- Schéma d'architecture en ASCII art compréhensible sans outil externe.
- Tableau de différenciation vs Google Alerts / ChatGPT / Aider / Devin.
- Mesures observées (cold run 27 min, hot run 3-5 min, premier setup 20-30 min).
- Liens vers toute la documentation interne (8 docs + dossier evaluations).

### 2. DEMO.md
- Pas-à-pas reproductible en moins de 30 min sur machine vierge.
- 6 étapes : install → menu → premier run → validation → intégration →
  consultation → 2ème run (incrémental).
- Section troubleshooting (5 erreurs typiques).
- Scénario "démo 5 min" pour jury / recruteur avec scénario d'enchaînement
  optimal.

### 3. ROADMAP_MVP.md à jour
- Tableau de statut clair au début (jalons 0-8 avec ✅/🟡 + lien eval).
- Octopart explicitement marqué comme V2 backlog.

### 4. Polish menu
- `run_menu` crée `projects_dir` et `runs_root` au démarrage s'ils
  n'existent pas. Évite l'erreur "FileNotFoundError" au premier lancement
  sur machine vierge.
- Gestion gracieuse d'OSError (logge un warning, ne plante pas).

### 5. Doc utilisateur (GETTING_STARTED.md)
- À jour avec les 7 jalons (mode menu interactif documenté).
- Section "Valider et intégrer les suggestions" pour les utilisateurs qui
  préfèrent les commandes directes au menu.

## Livrables ⏳ À faire côté utilisateur

Ces points sont explicitement hors du périmètre code/doc et doivent être
réalisés par l'utilisateur principal :

### a. Démo vidéo
- GIF court (< 30 sec) embarqué dans le README — scène recommandée :
  ouverture menu → choix projet → barre de progression → résultat → ouverture
  HTML.
- Vidéo longue (3-5 min) sur YouTube ou Loom — pitch + démo + ouverture
  d'un fichier de décisions (`DECISIONS.md`) pour montrer la rigueur design.

### b. Dogfooding réel
- Lancer Applied Fox sur **au moins un projet perso non-démo** (Forest of
  Senses, Lightning Simulation, Digital Twin Percheron).
- Observer **au moins une suggestion qui change concrètement une décision**
  technique du projet. Documenter cette suggestion dans une eval séparée
  (`docs/evaluations/jalon8_dogfooding_<nom_projet>.md`).
- Critère de succès MVP (cf. ROADMAP_MVP : "Validation finale du MVP — trois
  conditions absolues", point 2).

### c. Démo live testée par tiers
- Faire cloner le repo par **un dev externe** (un camarade de promo ESILV
  par exemple). Vérifier qu'il fait tourner la démo en moins de 30 min.
- Documenter les frictions observées (étape qui patine, message d'erreur
  confus, etc.) — ce sera l'input du polish itératif post-MVP.

### d. Lecture du README par 3 camarades
- Critère ROADMAP : 3 camarades comprennent l'outil en moins de 30 sec
  après lecture du README.
- Si feedback "j'ai pas compris", ajuster le README — c'est probablement
  le pitch initial qui pèche.

### e. Évaluation Opus 4.7 finale
- Format identique aux baselines des Jalons 1 et 5.
- Input : `.md` projet + rapport final + reasoning files.
- Critère : note ≥ baseline (≥ 7/10 sur l'Interview, ≥ 6/10 sur la veille).

### f. Pinning GitHub + mention LinkedIn
- Repo épinglé sur le profil GitHub de l'utilisateur.
- Post LinkedIn lien projet (à valider — l'utilisateur le fait quand il
  estime que c'est prêt).

## Décisions clés du Jalon 8

### 1. Pas de section "feedback exploité" dans le rapport final
- Rappelé dans CLAUDE.md règle 5. Cas limite non implémenté = pas de risque
  de pollution de contexte. Conservé pour V2 si réintroduction explicite.

### 2. Pas de daemon de veille permanente
- Hors scope MVP. L'utilisateur lance manuellement les runs. Pour V2 :
  cron + notification système (cf. `BACKLOG.md`).

### 3. Pas de polish UX cmd.exe vs Windows Terminal
- La TUI Rich peut clignoter dans cmd.exe legacy. On documente la recommandation
  (`wt.exe` / Windows Terminal) sans détecter automatiquement le terminal.
  Ratio coût/bénéfice médiocre pour le MVP.

### 4. README en français
- Le projet est porté par un étudiant français pour un public francophone
  ESILV. La traduction anglaise est V2 si visibilité internationale recherchée.

## Critère MVP (cf. ROADMAP_MVP)

Les 3 conditions absolues du MVP, statut actuel :

1. **Chaîne complète bout-en-bout sans intervention correctrice**
   `applied-fox interview create` → édition → `applied-fox run` →
   validation rapport → suggestions intégrées → `.md` modifié →
   `applied-fox run` suivant montrant incrémental fonctionnel.

   → **Statut : code en place, à valider en run interactif réel.**

2. **Dogfooding réussi** : au moins 1 suggestion réelle a changé une
   décision sur un projet perso.

   → **Statut : à faire côté utilisateur.**

3. **Démo accessible à un dev externe en moins de 30 min**.

   → **Statut : DEMO.md écrit, à tester par un dev externe.**

Le MVP est donc **techniquement complet** mais sa validation finale dépend
des activités utilisateur a/b/c/d/e/f ci-dessus.

## Limites connues / V2

Tout dans `docs/BACKLOG.md`. Les plus saillantes :
- Asyncio + parallélisation des sources (gain ~30-40% sur cold run estimé).
- Mode `full_api` / `hybrid` (cloud opt-in avec avertissement).
- Multi-projets batch + comparaison runs.
- Daemon + notification.
- Octopart (prix + supply chain).
- Mode exécutif (ouverture issues, commande composants).
- Web UI.

## Status final

✅ Code (jalons 1-7 + polish menu)
✅ Documentation (README, DEMO, GETTING_STARTED, ROADMAP statut, 12+ docs
   internes, 10+ evals par jalon)
🟡 Démo interactive bout-en-bout : à exécuter par l'utilisateur
🟡 Dogfooding : à exécuter par l'utilisateur sur projet perso non-démo
🟡 Validation par dev externe : à organiser par l'utilisateur
⏭️ V2 (post-MVP) : voir `BACKLOG.md`
