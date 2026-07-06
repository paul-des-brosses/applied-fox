#!/usr/bin/env bash
# setup.sh — Installation de Applied Fox
# Cible : Linux / WSL2 / macOS avec bash
# Usage  : bash setup.sh

set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Couleurs (désactivées si pas de terminal interactif)
# ─────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; NC=''
fi

info()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[ATTENTION]${NC} $*"; }
fail()    { echo -e "${RED}[ERREUR]${NC} $*"; exit 1; }
section() { echo -e "\n${GREEN}=== $* ===${NC}"; }

# ─────────────────────────────────────────────────────────────
# 1. Vérification Python >= 3.11
# ─────────────────────────────────────────────────────────────
section "Vérification Python"

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        MAJOR=${VER%%.*}; MINOR=${VER##*.}
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            info "Python $VER trouvé ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    fail "Python 3.11+ requis. Installe-le depuis https://www.python.org ou via ton gestionnaire de paquets."
fi

# ─────────────────────────────────────────────────────────────
# 2. Création du venv
# ─────────────────────────────────────────────────────────────
section "Environnement virtuel"

if [ -d ".venv" ]; then
    warn "Un venv existe déjà (.venv). Il sera réutilisé."
else
    "$PYTHON_CMD" -m venv .venv
    info "Venv créé dans .venv/"
fi

# Activation dans ce script (ne persiste pas dans le shell parent)
source .venv/bin/activate

# ─────────────────────────────────────────────────────────────
# 3. Installation des dépendances
# ─────────────────────────────────────────────────────────────
section "Installation des dépendances"

pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet
info "Dépendances installées (core + dev)."

# ─────────────────────────────────────────────────────────────
# 4. Vérification Ollama
# ─────────────────────────────────────────────────────────────
section "Vérification Ollama"

OLLAMA_OK=false
if command -v ollama &>/dev/null; then
    info "Ollama installé ($(ollama --version 2>/dev/null || echo 'version inconnue'))"
    OLLAMA_OK=true
else
    warn "Ollama non trouvé dans le PATH."
    echo "    → Installe Ollama : https://ollama.com/download"
    echo "    → Puis relance ce script, ou télécharge le modèle manuellement :"
    echo "      ollama pull mistral:7b-instruct-q4_K_M"
fi

# ─────────────────────────────────────────────────────────────
# 5. Téléchargement des modèles LLM (si Ollama disponible)
# ─────────────────────────────────────────────────────────────
if [ "$OLLAMA_OK" = true ]; then
    section "Modèles LLM locaux"

    # mistral:7b — Interviewer, Intégrateur, Rapporteur (~4.4 Go)
    MODEL_BASE="mistral:7b-instruct-q4_K_M"
    if ollama list 2>/dev/null | grep -q "${MODEL_BASE%%:*}"; then
        info "Mistral 7B déjà présent. Skip."
    else
        echo "Téléchargement $MODEL_BASE (~4.4 Go)…"
        if ollama pull "$MODEL_BASE"; then
            info "$MODEL_BASE prêt."
        else
            warn "Échec du pull. Essaie : ollama pull $MODEL_BASE"
        fi
    fi

    # qwen3:8B — Juge uniquement (~5 Go, méta-raisonnement)
    MODEL_JUGE="qwen3:8B"
    if ollama list 2>/dev/null | grep -q "qwen3:8b"; then
        info "qwen3:8B déjà présent. Skip."
    else
        echo "Téléchargement $MODEL_JUGE (~5 Go, modèle du Juge)…"
        if ollama pull "$MODEL_JUGE"; then
            info "$MODEL_JUGE prêt."
        else
            warn "Échec du pull. Essaie : ollama pull $MODEL_JUGE"
            warn "Sans ce modèle, le pipeline plantera à l'étape Juge."
            warn "Voir docs/HARDWARE.md pour le fallback mistral 7B si besoin."
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────
# 6. Création de ~/.applied-fox et de la config par défaut
# ─────────────────────────────────────────────────────────────
section "Répertoire de travail ~/.applied-fox"

TECH_WATCH_DIR="$HOME/.applied-fox"
for subdir in projects runs cache state; do
    mkdir -p "$TECH_WATCH_DIR/$subdir"
done
info "Arborescence $TECH_WATCH_DIR/ créée."

CONFIG_FILE="$TECH_WATCH_DIR/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    warn "Un config.yaml existe déjà — conservé sans modification."
else
    cat > "$CONFIG_FILE" << 'YAML_EOF'
# ~/.applied-fox/config.yaml
# Configuration globale Applied Fox
# Spec complète : docs/CONFIG_SCHEMA.md
# Hardware : voir docs/HARDWARE.md pour adapter à ta machine.

mode: local

ollama:
  base_url: http://localhost:11434
  models:
    # interviewer est toujours forcé en local (contrainte MVP).
    # integrateur + rapporteur : tâches mécaniques, mistral 7B suffit.
    # juge : méta-raisonnement → nécessite qwen3:8B (ou mistral 7B en fallback
    #         sur hardware limité, au prix d'hallucinations accrues).
    integrateur: mistral:7b-instruct-q4_K_M
    juge:        qwen3:8B
    rapporteur:  mistral:7b-instruct-q4_K_M
  timeout_seconds: 120
  num_ctx: 8192

sources:
  reddit:
    enabled: false
    client_id_env: REDDIT_CLIENT_ID
    client_secret_env: REDDIT_CLIENT_SECRET
    user_agent: "applied-fox/0.1"
    cache_ttl_hours: 12
    filters:
      min_score: 5
      max_age_days: 365
  github:
    enabled: false
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
    cache_ttl_hours: 24
    filters:
      max_age_days: 90

filters:
  enable_alignment_check: true
  enable_freshness_check: true
  enable_dedup: true
  enable_incremental_mode: true

paths:
  projects_dir: ~/.applied-fox/projects
  runs_dir: ~/.applied-fox/runs
  cache_dir: ~/.applied-fox/cache
  state_dir: ~/.applied-fox/state

reporting:
  open_browser: true
  html_template: default
  fallback_to_markdown: true

observability:
  enabled: false
YAML_EOF
    info "Config par défaut créée : $CONFIG_FILE"
fi

# ─────────────────────────────────────────────────────────────
# 7. Vérification rapide du package
# ─────────────────────────────────────────────────────────────
section "Vérification du package"

if python -c "from src.llm import get_llm; llm = get_llm('interviewer', {}); print(f'get_llm OK → {type(llm).__name__}')"; then
    info "Import get_llm réussi."
else
    fail "Import get_llm échoué. Vérifie l'installation."
fi

# ─────────────────────────────────────────────────────────────
# Récap final
# ─────────────────────────────────────────────────────────────
section "Setup terminé"
echo ""
echo "  Pour activer l'environnement :"
echo "    source .venv/bin/activate"
echo ""
echo "  Pour démarrer une interview :"
echo "    applied-fox interview create"
echo ""
echo "  Pour lancer la veille sur un projet :"
echo "    applied-fox run --project ~/.applied-fox/projects/mon_projet.md"
echo ""
if [ "$OLLAMA_OK" = false ]; then
    warn "N'oublie pas d'installer Ollama et de télécharger un modèle avant de démarrer."
fi
