# CONFIG_SCHEMA — Spécification du fichier `config.yaml`

Ce document spécifie le format du fichier `~/.applied-fox/config.yaml`, qui contient la configuration globale du système.

**Au MVP, un seul mode est exposé : `local`.** Le mode `hybrid` (Interview local + agents en API cloud) est en backlog Niveau 2. La structure du fichier est conçue pour l'accueillir sans refactor.

---

## Template `config.yaml` complet pour le MVP

```yaml
# ~/.applied-fox/config.yaml
# Configuration globale Applied Fox

# === Mode de fonctionnement ===
mode: local                    # seule valeur au MVP. V2 : hybrid (agents en API, Interview reste local).

# === Configuration provider Ollama ===
ollama:
  base_url: http://localhost:11434
  models:
    interviewer: mistral:7b-instruct-q4_K_M    # local au MVP — voir note plus bas
    eclaireur: mistral:7b-instruct-q4_K_M       # legacy (déterministe — plus invoqué)
    integrateur: mistral:7b-instruct-q4_K_M     # tâche mécanique, 7B suffit
    juge: qwen3:8B                               # méta-raisonnement nécessite Qwen3
    rapporteur: mistral:7b-instruct-q4_K_M
  timeout_seconds: 120
  num_ctx: 8192                # taille de contexte allouée

# === Sources de veille ===
# Octopart (Nexar) est en V2 backlog : sa section sources.octopart sera
# réintroduite quand le module sera implémenté. Cf. docs/BACKLOG.md.
sources:
  reddit:
    enabled: true
    client_id_env: REDDIT_CLIENT_ID
    client_secret_env: REDDIT_CLIENT_SECRET
    user_agent: "applied-fox/0.1 by /u/[username]"
    cache_ttl_hours: 12
    filters:
      min_score: 5             # score minimum pour passer le filtre déterministe
      max_age_days: 365        # rejet des posts trop anciens

  github:
    enabled: true
    token_env: GITHUB_TOKEN
    cache_ttl_hours: 24
    filters:
      min_stars: 10
      max_age_days: 730

  rss:
    enabled: true
    feeds:
      - name: "Electronics Weekly"
        url: "https://www.electronicsweekly.com/feed/"
      - name: "EE Times"
        url: "https://www.eetimes.com/feed/"
    cache_ttl_hours: 24
    filters:
      max_age_days: 90

# === Filtres déterministes globaux ===
filters:
  enable_alignment_check: true     # alignement composants/objectifs (non négociable)
  enable_freshness_check: true
  enable_dedup: true
  enable_incremental_mode: true    # filtre les findings déjà vus

# === Chemins ===
paths:
  projects_dir: ~/.applied-fox/projects
  runs_dir: ~/.applied-fox/runs
  cache_dir: ~/.applied-fox/cache
  state_dir: ~/.applied-fox/state

# === Rapport ===
reporting:
  open_browser: true               # ouverture auto du HTML dans le navigateur
  html_template: default
  fallback_to_markdown: true       # si l'ouverture du navigateur échoue

# === Observabilité (optionnel, dev uniquement) ===
observability:
  enabled: false
  provider: langfuse               # langfuse (self-hosted) | langsmith
  langfuse:
    host: http://localhost:3000
    public_key_env: LANGFUSE_PUBLIC_KEY
    secret_key_env: LANGFUSE_SECRET_KEY
```

---

## Description champ par champ

### `mode`

| Valeur | Description | Statut |
|--------|-------------|--------|
| `local` | Tous les agents en local Ollama | **MVP — seule valeur exposée** |
| `hybrid` | Interview en local + agents en API cloud | Backlog Niveau 2 |

**Note** : le rôle `interviewer` est exclusivement local — contrainte codée dans `get_llm("interviewer", config)`. Le mode `hybrid` ne lève pas cette contrainte : l'Interview reste local même quand les agents de veille passent en API cloud.

### Section `ollama`

| Champ | Type | Description |
|-------|------|-------------|
| `base_url` | URL | Endpoint Ollama, par défaut `http://localhost:11434` |
| `models.interviewer` | string | Modèle utilisé pour l'Interviewer. **Toujours local** (contrainte fondamentale). |
| `models.eclaireur` | string | Modèle pour l'Éclaireur (suivant profile par défaut, surchargeable). |
| `models.integrateur` | string | Modèle pour l'Intégrateur. |
| `models.juge` | string | Modèle pour le Juge. |
| `models.rapporteur` | string | Modèle pour le Rapporteur. |
| `timeout_seconds` | int | Timeout par appel LLM. Défaut : 120s. |
| `num_ctx` | int | Taille de contexte allouée. Défaut : 8192. |

**Important** : `models.interviewer` est validé au démarrage. Si la valeur n'est pas un modèle Ollama résolvable, démarrage avorté avec message d'erreur clair.

### Section `sources`

Une sous-section par source. Chaque source a au minimum un champ `enabled` (booléen). Si `enabled: false`, la source est ignorée et n'apparaît pas dans le rapport.

#### `sources.reddit`

| Champ | Description |
|-------|-------------|
| `enabled` | Activation |
| `client_id_env` | Nom de la variable d'env contenant le Reddit client_id |
| `client_secret_env` | Nom de la variable d'env contenant le Reddit client_secret |
| `user_agent` | User-Agent obligatoire pour PRAW |
| `cache_ttl_hours` | TTL cache, défaut 12h |
| `filters.min_score` | Score minimum d'un post pour passer le filtre déterministe |
| `filters.max_age_days` | Posts plus anciens rejetés |

#### `sources.github`

| Champ | Description |
|-------|-------------|
| `enabled` | Activation |
| `token_env` | Variable d'env du token GitHub |
| `cache_ttl_hours` | TTL cache, défaut 24h |
| `filters.min_stars` | Étoiles minimum d'un repo pour être considéré |
| `filters.max_age_days` | Repos plus anciens rejetés |

#### `sources.rss`

| Champ | Description |
|-------|-------------|
| `enabled` | Activation |
| `feeds` | Liste de flux. Chaque flux a `name` (libre) et `url` (URL du flux RSS). |
| `cache_ttl_hours` | TTL cache, défaut 24h |
| `filters.max_age_days` | Articles plus anciens rejetés |

### Section `filters`

| Champ | Description | Recommandé |
|-------|-------------|------------|
| `enable_alignment_check` | Filtre alignement composants/objectifs | `true` (non négociable de design) |
| `enable_freshness_check` | Rejet des findings trop anciens | `true` |
| `enable_dedup` | Déduplication par hash | `true` |
| `enable_incremental_mode` | Filtrage des findings déjà vus | `true` |

Ces flags existent pour le debug uniquement. **En usage normal, tous à `true`.**

### Section `paths`

Quatre chemins, par défaut tous sous `~/.applied-fox/`. Permet de relocaliser ailleurs (autre disque, dossier partagé local, etc.).

### Section `reporting`

| Champ | Description |
|-------|-------------|
| `open_browser` | Ouverture auto du HTML dans le navigateur après la génération |
| `html_template` | Template HTML à utiliser. `default` au MVP. |
| `fallback_to_markdown` | Si l'ouverture du navigateur échoue, affiche le Markdown brut dans le TUI |

### Section `observability` (optionnelle)

| Champ | Description |
|-------|-------------|
| `enabled` | Active le tracing (par défaut `false`) |
| `provider` | `langfuse` (recommandé self-hosted) ou `langsmith` |
| `langfuse.host` | URL de l'instance LangFuse self-hosted |
| `langfuse.public_key_env` | Variable d'env de la clé publique LangFuse |
| `langfuse.secret_key_env` | Variable d'env de la clé secrète LangFuse |

L'utilisateur final n'a pas besoin de cette section. C'est strictement un outil dev.

---

## Variables d'environnement attendues

| Variable | Utilité | Obligatoire ? |
|----------|---------|---------------|
| `REDDIT_CLIENT_ID` | OAuth Reddit | Si `sources.reddit.enabled: true` |
| `REDDIT_CLIENT_SECRET` | OAuth Reddit | Si `sources.reddit.enabled: true` |
| `GITHUB_TOKEN` | Token GitHub personnel ou app | Si `sources.github.enabled: true` |
| `LANGFUSE_PUBLIC_KEY` | LangFuse | Si observabilité activée |
| `LANGFUSE_SECRET_KEY` | LangFuse | Si observabilité activée |

Les variables d'env sont lues via `python-dotenv` au démarrage. Un fichier `.env` à la racine du projet est supporté pour le développement local. **Le fichier `.env` ne doit jamais être commité** — un `.env.example` documente les variables attendues.

---

## Schéma Pydantic correspondant

```python
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl

ModeType = Literal["local"]  # MVP : seul "local" autorisé. V2 élargira l'enum.
ProfileType = Literal["small", "medium", "large"]


class OllamaModels(BaseModel):
    interviewer: str
    eclaireur: str
    integrateur: str
    juge: str
    rapporteur: str


class OllamaConfig(BaseModel):
    base_url: HttpUrl = "http://localhost:11434"
    models: OllamaModels
    timeout_seconds: int = 120
    num_ctx: int = 8192


class RedditFilters(BaseModel):
    min_score: int = 5
    max_age_days: int = 365


class RedditConfig(BaseModel):
    enabled: bool = True
    client_id_env: str = "REDDIT_CLIENT_ID"
    client_secret_env: str = "REDDIT_CLIENT_SECRET"
    user_agent: str
    cache_ttl_hours: int = 12
    filters: RedditFilters = RedditFilters()


class GithubFilters(BaseModel):
    min_stars: int = 10
    max_age_days: int = 730


class GithubConfig(BaseModel):
    enabled: bool = True
    token_env: str = "GITHUB_TOKEN"
    cache_ttl_hours: int = 24
    filters: GithubFilters = GithubFilters()


class RssFeed(BaseModel):
    name: str
    url: HttpUrl


class RssFilters(BaseModel):
    max_age_days: int = 90


class RssConfig(BaseModel):
    enabled: bool = True
    feeds: list[RssFeed]
    cache_ttl_hours: int = 24
    filters: RssFilters = RssFilters()


class SourcesConfig(BaseModel):
    reddit: RedditConfig
    github: GithubConfig
    rss: RssConfig
    # octopart : V2 backlog (cf. docs/BACKLOG.md)


class FiltersConfig(BaseModel):
    enable_alignment_check: bool = True
    enable_freshness_check: bool = True
    enable_dedup: bool = True
    enable_incremental_mode: bool = True


class PathsConfig(BaseModel):
    projects_dir: Path
    runs_dir: Path
    cache_dir: Path
    state_dir: Path


class ReportingConfig(BaseModel):
    open_browser: bool = True
    html_template: str = "default"
    fallback_to_markdown: bool = True


class LangfuseConfig(BaseModel):
    host: HttpUrl
    public_key_env: str = "LANGFUSE_PUBLIC_KEY"
    secret_key_env: str = "LANGFUSE_SECRET_KEY"


class ObservabilityConfig(BaseModel):
    enabled: bool = False
    provider: Literal["langfuse", "langsmith"] = "langfuse"
    langfuse: Optional[LangfuseConfig] = None


class Config(BaseModel):
    mode: ModeType = "local"
    ollama: OllamaConfig
    sources: SourcesConfig
    filters: FiltersConfig = FiltersConfig()
    paths: PathsConfig
    reporting: ReportingConfig = ReportingConfig()
    observability: ObservabilityConfig = ObservabilityConfig()
```

---

## Exemples de configurations courantes

### Config hardware limité — UX3402Z (16 Go RAM, GPU intégré)

> Fallback si `qwen3:8B` ne tient pas en VRAM. Le Juge utilise `mistral:7b`
> au prix d'un taux de rejet ~0 (accepte presque tout). La TUI de validation
> humaine est ton seul filet de sécurité dans ce cas.

```yaml
mode: local

ollama:
  base_url: http://localhost:11434
  models:
    interviewer: mistral:7b-instruct-q4_K_M
    eclaireur: mistral:7b-instruct-q4_K_M
    integrateur: mistral:7b-instruct-q4_K_M
    juge: mistral:7b-instruct-q4_K_M       # fallback VRAM < 6 Go
    rapporteur: mistral:7b-instruct-q4_K_M
  timeout_seconds: 240        # plus large car CPU only
  num_ctx: 4096                # contexte réduit pour économiser RAM

sources:
  reddit:
    enabled: true
    client_id_env: REDDIT_CLIENT_ID
    client_secret_env: REDDIT_CLIENT_SECRET
    user_agent: "applied-fox/0.1 by /u/exemple"
    cache_ttl_hours: 12
    filters:
      min_score: 10
      max_age_days: 180
  github:
    enabled: true
    token_env: GITHUB_TOKEN
    cache_ttl_hours: 24
    filters:
      min_stars: 50
      max_age_days: 365
  rss:
    enabled: true
    feeds:
      - name: "Electronics Weekly"
        url: "https://www.electronicsweekly.com/feed/"

paths:
  projects_dir: ~/.applied-fox/projects
  runs_dir: ~/.applied-fox/runs
  cache_dir: ~/.applied-fox/cache
  state_dir: ~/.applied-fox/state
```

### Config validée — machine MSI (i7-11800H, 64 Go, RTX 3070 8 Go)

> Config de référence, testée et mesurée en mai 2026.
> Voir `docs/evaluations/modeles_perf_2026-05-13.md` pour le détail.

```yaml
mode: local

ollama:
  base_url: http://localhost:11434
  models:
    interviewer: mistral:7b-instruct-q4_K_M    # local au MVP
    eclaireur: mistral:7b-instruct-q4_K_M       # legacy (déterministe — plus invoqué)
    integrateur: mistral:7b-instruct-q4_K_M     # tâche mécanique, 7B suffit
    juge: qwen3:8B                               # méta-raisonnement — seul agent qui nécessite Qwen3
    rapporteur: mistral:7b-instruct-q4_K_M
  timeout_seconds: 120
  num_ctx: 8192

sources:
  reddit:
    enabled: true
    client_id_env: REDDIT_CLIENT_ID
    client_secret_env: REDDIT_CLIENT_SECRET
    user_agent: "applied-fox/0.1 by /u/exemple"
    cache_ttl_hours: 12
    filters:
      min_score: 5
      max_age_days: 365
  github:
    enabled: true
    token_env: GITHUB_TOKEN
    cache_ttl_hours: 24
    filters:
      min_stars: 10
      max_age_days: 730
  rss:
    enabled: true
    feeds:
      - name: "Electronics Weekly"
        url: "https://www.electronicsweekly.com/feed/"
      - name: "EE Times"
        url: "https://www.eetimes.com/feed/"

paths:
  projects_dir: ~/.applied-fox/projects
  runs_dir: ~/.applied-fox/runs
  cache_dir: ~/.applied-fox/cache
  state_dir: ~/.applied-fox/state

observability:
  enabled: true
  provider: langfuse
  langfuse:
    host: http://localhost:3000
    public_key_env: LANGFUSE_PUBLIC_KEY
    secret_key_env: LANGFUSE_SECRET_KEY
```

### Config démo — sources minimales, pas de clé API requise

```yaml
mode: local

ollama:
  base_url: http://localhost:11434
  models:
    interviewer: mistral:7b-instruct-q4_K_M
    eclaireur: mistral:7b-instruct-q4_K_M
    integrateur: mistral:7b-instruct-q4_K_M
    juge: qwen3:8B                        # fallback : mistral:7b si VRAM insuffisante
    rapporteur: mistral:7b-instruct-q4_K_M

sources:
  # Pour la démo, on désactive les sources nécessitant des clés tierces
  reddit:
    enabled: false           # nécessite client_id / secret
    client_id_env: REDDIT_CLIENT_ID
    client_secret_env: REDDIT_CLIENT_SECRET
    user_agent: "applied-fox/0.1"
  github:
    enabled: false           # nécessite GITHUB_TOKEN
    token_env: GITHUB_TOKEN
  rss:
    enabled: true            # seule source sans clé requise
    feeds:
      - name: "Electronics Weekly"
        url: "https://www.electronicsweekly.com/feed/"

paths:
  projects_dir: ~/.applied-fox/projects
  runs_dir: ~/.applied-fox/runs
  cache_dir: ~/.applied-fox/cache
  state_dir: ~/.applied-fox/state
```

---

## Validation au démarrage

Au lancement de la CLI :

1. Le `config.yaml` est chargé et parsé en `Config` Pydantic.
2. Si erreur de structure : message clair pointant le champ fautif.
3. Le modèle `interviewer` est testé contre Ollama : si non résolvable, démarrage avorté.
4. Les variables d'environnement déclarées dans la config (`api_key_env`, `token_env`, etc.) sont vérifiées si les sources correspondantes sont `enabled: true`. Une variable manquante désactive automatiquement la source avec un warning lisible.
5. Les chemins (`paths`) sont créés si absents.

Toute erreur de configuration retourne un message en français clair, indiquant le fichier (`~/.applied-fox/config.yaml`), la section concernée, et un exemple correct.
