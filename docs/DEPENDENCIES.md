# DEPENDENCIES — Packages Python du projet

Ce document liste les dépendances du projet, leurs versions recommandées, leur rôle, et les alternatives possibles.

> **Note importante** : les versions exactes sont à valider au moment de l'implémentation, l'écosystème agentique évolue très vite. Quand une lib est mature et stable, on indique une plage `>=X.Y` ; quand elle évolue rapidement (LangChain, LangGraph, Ollama), on recommande de figer la version au moment du Jalon 0 et de mettre à jour explicitement.

Les dépendances sont organisées en **profiles** correspondant aux blocs de `pyproject.toml`. Le profile **Core** est toujours installé. Les autres sont installables séparément (extras) si nécessaire.

---

## Core — toujours installé

### `langgraph`

- **Rôle** : framework d'orchestration multi-agent. Définit le graphe `TechWatchState` qui enchaîne les agents Éclaireur → Intégrateur → Juge → Rapporteur avec branchements conditionnels.
- **Version recommandée** : à figer au Jalon 0. Au moment de la rédaction (début 2026), viser la dernière mineure stable.
- **Alternatives** : CrewAI (rejetée — trop conversationnelle, cf. [`DECISIONS.md` §6](DECISIONS.md)), smolagents (trop minimal), orchestration custom (effort excessif).

### `langchain-core`

- **Rôle** : abstractions de base utilisées par LangGraph et par la couche provider (`get_llm()`).
- **Version recommandée** : aligner avec la version de `langgraph` (les deux évoluent ensemble).
- **Alternatives** : aucune réaliste — c'est la base de l'écosystème LangChain.

### `pydantic`

- **Rôle** : validation des schémas (Finding, IntegrationVerdict, JudgeVerdict, ValidatedSuggestion, ProjectModel, Config). Couche 1 de validation du `.md`.
- **Version recommandée** : `>=2.5`.
- **Alternatives** : `attrs` + validateurs manuels (verbeux), `dataclasses` (sans validation auto). Pydantic est le standard de fait.

### `pyyaml`

- **Rôle** : parsing du `config.yaml`.
- **Version recommandée** : `>=6.0`.
- **Alternatives** : `ruamel.yaml` si on a besoin de préserver les commentaires/format (pas le cas au MVP).

### `rich`

- **Rôle** : TUI. Tableaux, prompts, mises en forme du terminal pour l'Interview, la validation utilisateur, l'affichage des étapes.
- **Version recommandée** : `>=13`.
- **Alternatives** : `textual` (rejetée pour le MVP — trop lourde, cf. [`DECISIONS.md` §15](DECISIONS.md)). `prompt_toolkit` plus bas niveau.

### `markdown2` ou `mistune`

- **Rôle** : conversion Markdown → HTML pour l'affichage du rapport final dans le navigateur.
- **Version recommandée** :
  - `markdown2` : `>=2.4`.
  - `mistune` : `>=3.0`.
- **Choix entre les deux** : `mistune` est généralement plus rapide et plus extensible, `markdown2` plus simple. À trancher au Jalon 5 selon le rendu obtenu sur le rapport. Une seule des deux libs sera installée.
- **Alternatives** : `markdown` (lib standard), `pandoc` via subprocess (overkill).

### `requests-cache`

- **Rôle** : cache des requêtes HTTP avec TTL différenciés. Utilisé par toutes les sources (Reddit, GitHub, RSS au MVP ; Octopart en V2).
- **Version recommandée** : `>=1.1`.
- **Alternatives** : `cachecontrol` (moins ergonomique), cache custom SQLite (réinventer la roue).

### `python-dotenv`

- **Rôle** : chargement des variables d'environnement depuis un `.env` local en développement.
- **Version recommandée** : `>=1.0`.
- **Alternatives** : variables d'env système pures (acceptable en prod).

### `click` ou `typer`

- **Rôle** : framework CLI pour `applied-fox run`, `applied-fox interview create`, etc.
- **Version recommandée** :
  - `typer` : `>=0.9`.
  - `click` : `>=8.1`.
- **Choix recommandé** : `typer` (plus moderne, type hints natifs, basé sur `click`).
- **Alternatives** : `argparse` (lib standard, suffisant mais verbeux).

---

## Providers locaux — toujours installé au MVP

### `langchain-ollama`

- **Rôle** : intégration Ollama pour LangChain. Permet à `get_llm()` de retourner un `ChatOllama` configuré.
- **Version recommandée** : à figer au Jalon 0, aligner avec `langchain-core`.
- **Alternatives** : appel direct à l'API REST Ollama (perd les abstractions LangChain).
- **Pré-requis externe** : Ollama installé sur la machine, modèles téléchargés. Le `setup.sh` doit vérifier.

---

## Providers API — V2, à préparer dans la doc

Ces dépendances **ne sont pas installées au MVP**, mais elles sont mentionnées ici pour que l'utilisateur sache à quoi s'attendre quand le mode `hybrid` arrivera (cf. [`BACKLOG.md`](BACKLOG.md) Niveau 2). L'Interview reste toujours locale par design.

### `langchain-anthropic` (V2)

- **Rôle** : provider Claude pour `get_llm()` en mode hybrid (agents de veille en API cloud, Interview toujours locale).
- **Version recommandée** : aligner avec `langchain-core` au moment de l'activation.
- **Variable d'env** : `ANTHROPIC_API_KEY`.

### `langchain-openai` (V2)

- **Rôle** : provider OpenAI (GPT-5 et successeurs) pour `get_llm()`.
- **Variable d'env** : `OPENAI_API_KEY`.

### `langchain-mistralai` (V2)

- **Rôle** : provider Mistral cloud pour `get_llm()`.
- **Variable d'env** : `MISTRAL_API_KEY`.

### `langchain-groq` (V2)

- **Rôle** : provider Groq (inférence rapide) pour `get_llm()`.
- **Variable d'env** : `GROQ_API_KEY`.

---

## Sources de veille

### `praw` (Python Reddit API Wrapper)

- **Rôle** : interrogation de Reddit pour la source `reddit.py`.
- **Version recommandée** : `>=7.7`.
- **Alternatives** : appel direct à l'API REST Reddit (perd la gestion d'OAuth et du rate limit).
- **Pré-requis externes** : créer une app Reddit (https://www.reddit.com/prefs/apps), récupérer `client_id` et `client_secret`.

### `PyGithub`

- **Rôle** : interrogation de l'API GitHub pour la source `github.py`.
- **Version recommandée** : `>=2.1`.
- **Alternatives** : `requests` direct sur l'API REST GitHub. PyGithub apporte une couche d'abstraction confortable.
- **Pré-requis externes** : token personnel GitHub (https://github.com/settings/tokens) avec scopes `public_repo` minimum.

### `feedparser`

- **Rôle** : parsing des flux RSS (Electronics Weekly, EE Times, etc.).
- **Version recommandée** : `>=6.0`.
- **Alternatives** : `aiohttp` + parsing XML manuel (plus de boulot).

---

## Validation et qualité

### `pytest`

- **Rôle** : framework de tests. Tests unitaires sur le filtre déterministe, les schémas Pydantic, les parsers Markdown.
- **Version recommandée** : `>=7.4`.
- **Plugins utiles** :
  - `pytest-cov` pour la couverture.
  - `pytest-mock` pour les mocks (mais éviter de mocker les LLMs — préférer ne pas tester les agents en unit).

### Hygiène de code (optionnel mais recommandé)

| Outil | Rôle | Version recommandée |
|-------|------|---------------------|
| `ruff` | Linter + formatter rapide | `>=0.1` |
| `mypy` | Vérification de types statique | `>=1.8` |

---

## Outils dev (optionnels)

### `langfuse`

- **Rôle** : SDK pour envoyer les traces LLM vers une instance LangFuse self-hosted.
- **Version recommandée** : à figer au moment où l'observabilité est activée.
- **Pré-requis externes** : instance LangFuse (Docker compose, gratuit, instructions sur leur repo).
- **Statut MVP** : strictement optionnel. Activé via `observability.enabled: true` dans `config.yaml`.

### `langsmith` (alternative)

- **Rôle** : SDK pour LangSmith hébergé (cloud).
- **Statut** : alternative à LangFuse pour usage perso uniquement (gratuit jusqu'à un certain volume). Cohérent avec la philosophie locale uniquement si on accepte que les traces transitent par le cloud — à n'utiliser que sur ses propres projets non sensibles.

---

## Récap par profile `pyproject.toml`

```toml
[project]
name = "applied-fox-agent-ia"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # === Core ===
    "langgraph>=A.B",          # à figer au Jalon 0
    "langchain-core>=A.B",     # aligner avec langgraph
    "pydantic>=2.5",
    "pyyaml>=6.0",
    "rich>=13",
    "requests-cache>=1.1",
    "python-dotenv>=1.0",
    "typer>=0.9",
    "mistune>=3.0",            # ou markdown2

    # === Provider local ===
    "langchain-ollama>=A.B",   # à figer au Jalon 0

    # === Sources MVP ===
    "praw>=7.7",
    "PyGithub>=2.1",
    "feedparser>=6.0",
    # Octopart/Nexar : V2 backlog, pas installé au MVP
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov",
    "pytest-mock",
    "ruff>=0.1",
    "mypy>=1.8",
]

observability = [
    "langfuse",                # optionnel, dev only
]

# V2 — multi-provider, non installé au MVP
multi_provider = [
    "langchain-anthropic",
    "langchain-openai",
    "langchain-mistralai",
    "langchain-groq",
]

[project.scripts]
applied-fox = "src.cli:app"
```

---

## Pré-requis externes (non Python)

| Outil | Rôle | Installation |
|-------|------|--------------|
| **Ollama** | Inférence LLM locale | https://ollama.com/download |
| **Modèles Ollama** | Au minimum un modèle 7B Q4 | `ollama pull mistral:7b-instruct-q4_K_M` (ou équivalent) |
| **Python ≥ 3.11** | Runtime | https://www.python.org |
| **Git** | Versionnement | https://git-scm.com |

Le `setup.sh` (Jalon 0) doit vérifier la présence de ces pré-requis et les signaler clairement si absents.

---

## Politique de versioning

- **Versions exactes** (pinning strict) pour : `langgraph`, `langchain-core`, `langchain-ollama`. Ces libs évoluent vite et changent parfois leur API.
- **Plages stables** (`>=X.Y`) pour : `pydantic`, `pyyaml`, `rich`, `requests-cache`, `python-dotenv`, `typer`, `pytest`. Libs matures, ABI stable.
- **Mise à jour explicite** : pas d'auto-bump des versions épinglées. Une mise à jour LangChain/LangGraph est traitée comme une mini-tâche : tester, mettre à jour, valider sur le projet d'exemple.

Le `pyproject.toml` doit être accompagné d'un `requirements.lock` (généré par `pip-tools` ou équivalent) pour reproductibilité exacte.

---

## Notes spécifiques

- **`mistune` vs `markdown2`** : choix à trancher au Jalon 5 quand le template HTML du rapport sera défini. Une seule des deux est installée au final.
- **Client Octopart (V2 backlog)** : quand on l'introduira, vérifier si Nexar fournit un SDK Python officiel à jour. Si non, fallback sur `gql` ou `requests` direct sur leur endpoint GraphQL.
- **`langchain-ollama` vs `ollama` (client direct)** : `langchain-ollama` est préféré pour bénéficier de l'abstraction `BaseChatModel` qui rend `get_llm()` parfaitement substituable.
- **Tailles approximatives des modèles Ollama Q4** :
  - 7B Q4 : ~4-5 Go disque, ~6 Go RAM/VRAM en inférence.
  - 14B Q4 : ~8-9 Go disque, ~10-12 Go RAM/VRAM.
  - 32B Q4 : ~18-20 Go disque, ~22-24 Go RAM/VRAM.
- Ces ordres de grandeur conditionnent le profile machine choisi.
