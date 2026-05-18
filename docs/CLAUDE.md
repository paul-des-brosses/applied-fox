# CLAUDE.md — Instructions pour Claude Code dans ce projet

Ce fichier est lu en début de chaque session de développement. Il fixe les règles de comportement et les invariants qu'on ne renégocie pas.

---

## Contexte projet en 5 lignes

- **Projet** : Applied Fox — système multi-agent local de veille technologique pour projets d'ingénierie.
- **Public** : étudiant M1 ESILV, base Python générale, débutant complet sur l'écosystème agentique (LangGraph, Ollama, RAG, agents).
- **Objectifs** : (1) apprentissage des agents IA en construisant, (2) reconnaissance portfolio par recruteurs, (3) impact réel sur les projets perso.
- **Machines cible** : station MSI (i7-11800H, 64 Go, RTX 3070 8 Go) jusqu'à fin de stage, et UX3402Z (16 Go, GPU intégré) en personnel.
- **Status** : MVP en développement, jalons numérotés dans [`ROADMAP_MVP.md`](ROADMAP_MVP.md).

---

## Règle 0 — Lire la doc avant de coder

**Aucune ligne de code ne doit être écrite avant d'avoir lu** :
1. [`VISION.md`](VISION.md) — pourquoi ce projet existe.
2. [`DECISIONS.md`](DECISIONS.md) — toutes les décisions de design avec justification.
3. [`ARCHITECTURE.md`](ARCHITECTURE.md) — structure technique complète.
4. [`ROADMAP_MVP.md`](ROADMAP_MVP.md) — jalons, ordre d'implémentation, validation par jalon.

Si une nouvelle session commence et ces fichiers n'ont pas été chargés en contexte, **les lire d'abord**.

---

## Règle 1 — Vulgariser systématiquement

L'utilisateur apprend l'écosystème agentique en construisant. Toute explication, tout commentaire de code, toute justification doit :
- Définir les termes techniques au moins une fois (ou renvoyer à [`GLOSSARY.md`](GLOSSARY.md)).
- Expliquer le *pourquoi*, pas seulement le *quoi*.
- Préférer la phrase claire au jargon dense.

Si tu utilises un terme nouveau (ex. "structured output", "function calling", "embedding"), explique-le sur place ou ajoute-le au glossaire.

---

## Règle 2 — Décisions stratégiques vs techniques

**Décisions stratégiques** (changement d'architecture, ajout d'agent, changement de framework, abandon d'une décision figée dans `DECISIONS.md`) :
- Ne tranche **jamais** seul.
- Rédige une note d'analyse claire (contexte, options, recommandation, trade-off).
- Renvoie à un chat exploratoire avec l'utilisateur pour décider.

**Décisions techniques d'implémentation** (choix d'une lib, structure d'un module, format d'un test) :
- Propose, justifie brièvement, exécute.
- Documente le choix dans le commit ou dans le code si non trivial.

En cas de doute sur la classification : par défaut, traite comme stratégique.

---

## Règle 3 — Les quatre contraintes fondamentales sont non négociables

1. **Tout en local par défaut.**
   - Le module Interview est exclusivement local. C'est codé dans `get_llm("interviewer", config)`. Cette contrainte est fondamentale et ne sera pas levée.
   - Les agents de veille sont en local par défaut au MVP. Le mode `hybrid` (agents en API cloud, Interview toujours local) est en V2 backlog.

2. **Hot-swappable LLM.**
   - Tout appel LLM passe par `get_llm(role, config)`.
   - Aucun import direct de `ChatOllama`, `ChatAnthropic`, etc., dans `src/agents/`.
   - Override par rôle via `ollama.models.<role>` dans `config.yaml` — bascule
     de modèle en une ligne.

3. **Adaptable hardware.**
   - L'abstraction "profile small/medium/large" a été supprimée en v1.4
     (cf. `docs/evaluations/modeles_perf_2026-05-13.md`). Le bon design
     est "1 modèle par agent selon la tâche", pas "1 profil pour tout".
   - Config par défaut testée sur RTX 3070 8 GB : mistral 7b partout +
     qwen3:8B pour le Juge (le seul rôle qui demande du méta-raisonnement).
   - Voir `docs/HARDWARE.md` pour adapter à d'autres matériels.
   - Le code doit fonctionner sur GPU faible / CPU only / GPU costaud sans
     branchement spécial — uniquement via override de modèle en config.

4. **Format `.md` strict.**
   - Spec : [`MD_SCHEMA.md`](MD_SCHEMA.md).
   - Validation à 3 couches symétriques (création + modification).
   - L'Interviewer est le seul module qui produit ou modifie un `.md`.

---

## Règle 4 — Discipline MVP

Si une feature **n'est pas dans la roadmap MVP** ([`ROADMAP_MVP.md`](ROADMAP_MVP.md)), elle ne va pas dans le code. Elle va dans [`BACKLOG.md`](BACKLOG.md).

Ce qui est explicitement **hors MVP** :
- L'Historien comme agent à part entière.
- La mémoire adaptative distribuée.
- Le daemon de veille permanente, les alertes push.
- Le mode `hybrid` (agents de veille en API cloud, V2 backlog).
- L'auto-découverte des sources.
- L'évaluation auto de la crédibilité des sources.
- La section feedback exploitée par le Juge.
- Le mode exécutif (modifs de code, ouverture issues, commande de composants).
- L'interface graphique de configuration.
- La web app.
- La détection de synergies multi-projets.
- La veille étendue (software, papers, réglementaire).

Si l'utilisateur demande l'une de ces features pendant une session de dev, **rappeler poliment la discipline MVP** et proposer d'ajouter une entrée au backlog.

---

## Règle 5 — Discipline architecturale

Quelques règles dures héritées de [`DECISIONS.md`](DECISIONS.md) :

- **Pas de scraping au MVP.** Sources MVP : Reddit, GitHub, RSS. Octopart en V2 backlog.
- **Filtrage déterministe en amont du LLM.** Toujours. Économie tokens + qualité signal.
- **Mode incrémental dès le MVP.** `~/.applied-fox/state/[projet]_seen.json` filtre les findings déjà présentés.
- **Alignement téléologique** : un finding non aligné avec les objectifs actifs déclarés est rejeté. Inscrit à la fois dans le prompt système de l'Éclaireur ET dans le filtre déterministe.
- **Pas de section feedback exploitée au MVP** : rejetée explicitement (cf. [`DECISIONS.md` §12](DECISIONS.md)). Ne pas la réintroduire sans discussion stratégique.
- **Communication inter-agents** : JSON Pydantic + retry. Markdown libre uniquement pour la sortie utilisateur finale.
- **Modification du `.md`** : exclusivement via l'Interviewer en mode `integrate`. Pas de module dédié.

---

## Règle 6 — Structure du repo à respecter

```
applied-fox-agent-ia/
├── docs/
│   ├── VISION.md
│   ├── DECISIONS.md
│   ├── ARCHITECTURE.md
│   ├── CLAUDE.md
│   ├── ROADMAP_MVP.md
│   ├── BACKLOG.md
│   ├── MD_SCHEMA.md
│   ├── CONFIG_SCHEMA.md
│   ├── DEPENDENCIES.md
│   ├── GLOSSARY.md
│   └── evaluations/         # évaluations Opus 4.7 (LLM-as-a-judge)
├── src/
│   ├── agents/              # un fichier par agent
│   │   ├── interviewer.py
│   │   ├── eclaireur.py
│   │   ├── integrateur.py
│   │   ├── juge.py
│   │   └── rapporteur.py
│   ├── llm/                 # abstraction provider, get_llm()
│   ├── sources/             # un fichier par source MVP
│   │   ├── reddit.py
│   │   ├── github.py
│   │   ├── rss.py
│   │   └── common.py        # types partagés (octopart.py : V2 backlog)
│   ├── interview/           # logique du module Interview (modes create/update/integrate)
│   ├── reporting/           # génération rapports Markdown + HTML
│   ├── validation/          # 3 couches de validation
│   │   ├── structural.py
│   │   ├── transmission.py
│   │   └── human.py
│   ├── graph/               # définition LangGraph (TechWatchState, nœuds, edges)
│   └── cli.py               # entrée CLI (commande `applied-fox run`)
├── projects/                # exemples de fiches projet
│   └── esp32_weather_station.md
├── tests/
├── README.md
├── GETTING_STARTED.md
├── setup.sh
└── pyproject.toml
```

Si un fichier nouveau ne tient dans aucune de ces dossiers, c'est probablement le signe qu'il ne doit pas exister. Discuter avant de créer un dossier nouveau.

---

## Règle 7 — Gestion des dépendances et versions

- Toute nouvelle dépendance va dans `pyproject.toml` ET dans [`DEPENDENCIES.md`](DEPENDENCIES.md) (avec rôle, version recommandée, alternative).
- Les versions exactes sont à valider au moment de l'implémentation (l'écosystème agentique évolue vite). Préférer les plages stables (`>=X.Y`) quand la lib est mature.
- Aucune lib non listée dans `DEPENDENCIES.md` ne doit apparaître dans un `import` du code source. Si tu as besoin d'une lib non listée, **mettre à jour `DEPENDENCIES.md` d'abord**.

---

## Règle 8 — Sécurité

- Aucune clé API en dur dans la config ni dans le code.
- Toutes les clés passent par variables d'environnement : `OCTOPART_API_KEY`, `GITHUB_TOKEN`, etc.
- Les fichiers `.env` ne doivent jamais être commités. Un `.env.example` peut documenter les clés attendues.
- Aucun appel réseau "discret" (télémétrie, anonymisé, etc.) — incompatible avec la philosophie locale du projet.

---

## Règle 9 — Tests et qualité

- Les fonctions du filtre déterministe (`src/sources/*` et logique de filtrage Éclaireur) sont testables unitairement, sans LLM. **Tester systématiquement.**
- Les schémas Pydantic ont des tests de validation (entrées valides, entrées invalides, edge cases).
- Les agents LLM ne sont pas testés unitairement (coût + non-déterminisme), mais via les évaluations Opus 4.7 décrites dans [`ROADMAP_MVP.md`](ROADMAP_MVP.md).
- Pas de test d'intégration qui appelle de vrais LLMs en CI.

---

## Règle 10 — Communication avec l'utilisateur

- Réponses concises, format adapté à la complexité de la question.
- Quand un choix d'implémentation est non évident, exposer la logique en deux phrases avant de coder.
- Ne pas écrire de commentaires inutiles dans le code (cf. règle générale Claude Code) — mais commenter ce qui est subtil ou contre-intuitif.
- En fin de session ou de jalon, proposer un récap court : ce qui a été fait, ce qui reste à valider, prochaine étape.

---

## Rappel ferme — designs fondamentaux à ne jamais oublier

Cette liste est volontairement répétée parce qu'elle est centrale.

- Module **Interview** exclusivement local, sans exception. L'Interview ne quitte jamais la machine.
- **Hot-swappable** structurellement via `get_llm(role, config)`. Aucun import direct d'un provider dans les agents.
- **3 couches de validation symétriques** entre création et modification du `.md`. Pas de raccourci à la modification.
- **Filtrage déterministe en amont** du LLM. Économie + qualité signal. Non négociable.
- **Alignement téléologique** avec objectifs actifs. Règle non négociable inscrite dans le prompt Éclaireur ET dans le filtre.
- **Pas de section feedback exploitée** au MVP. Risques de pollution contexte et cascade incontrôlable.
- **Mode local seul exposé** au MVP. Discipline.

Tout le reste est secondaire. Ces sept règles passent avant tout.
