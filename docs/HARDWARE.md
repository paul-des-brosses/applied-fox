# Hardware & modèles — Applied Fox

Tout ce qu'il faut savoir pour adapter Applied Fox à ton matériel.

## Config par défaut (validée mai 2026)

| Agent | Modèle | Taille Q4 | VRAM occupée |
|---|---|---:|---:|
| Interviewer | `mistral:7b-instruct-q4_K_M` | 4.4 GB | ~5.2 GB |
| Éclaireur | *(plus de LLM — déterministe)* | — | — |
| Intégrateur | `mistral:7b-instruct-q4_K_M` | 4.4 GB | ~5.2 GB |
| **Juge** | `qwen3:8B` | 5.0 GB | ~6.0 GB |
| Rapporteur | `mistral:7b-instruct-q4_K_M` | 4.4 GB | ~5.2 GB |

**Pré-requis hardware minimum** : 8 GB VRAM ou 16 GB RAM unifiée (Apple Silicon).
Le Juge swappe avec mistral 7B en VRAM pendant le pipeline — il faut pouvoir
loader un des deux (max 6 GB simultanément). Si tu n'as pas la VRAM pour
qwen3:8B, voir la section "Tu as < 8 GB VRAM" plus bas.

**Cas testé** : Intel i7-11800H + 64 GB RAM + RTX 3070 Laptop 8 GB sous
Windows 11 Pro. Pipeline complet 3 projets en ~30 min cold, ~5 min avec cache LLM chaud.

## Pré-requis : pull des modèles avant premier run

```bash
ollama pull mistral:7b-instruct-q4_K_M    # 4.4 GB
ollama pull qwen3:8B                        # 5.0 GB
```

Total disque : ~10 GB.

## Changer un modèle facilement (CLI)

Le hot-swap est conçu pour être trivial. Les modèles testés sont gardés
dans un registre interne et la CLI te protège des choix risqués.

```bash
# Voir quels modèles sont testés/rejetés/actifs pour chaque rôle
applied-fox models list
applied-fox models list juge        # filtre par rôle

# Changer un modèle pour un rôle donné
applied-fox models set juge qwen3:14b      # warning : non testé
applied-fox models set juge qwen3.5:9b     # bloqué : rejected (override --force)

# Revenir aux défauts testés
applied-fox models reset                    # tous les rôles
applied-fox models reset juge              # un seul rôle
```

**Comportement attendu** :
- **`tested`** → set silencieux, marqueur ✓ vert dans `list`
- **`rejected`** → set bloqué par défaut, raison expliquée (override `--force`)
- **non testé** → set autorisé avec ⚠ warning, marqueur jaune dans `list`,
  warning émis à chaque appel LLM au runtime

L'**interviewer** est verrouillé (contrainte CLAUDE.md règle 3 — tout en
local 7B Q4 au MVP). Toute tentative de set sur ce rôle est refusée.

## Adapter à un autre matériel

### Tu as < 8 GB VRAM (laptop intégré, mac M1/M2 base)
La config par défaut tient en 6 GB VRAM (un seul des deux modèles chargé à la
fois). Sur Apple Silicon avec mémoire unifiée, ajuste `num_ctx: 4096` dans
config.yaml pour économiser. Si qwen3:8B est vraiment trop juste, tu peux
basculer le Juge sur mistral 7B :
```yaml
ollama:
  models:
    juge: mistral:7b-instruct-q4_K_M  # fallback — risque d'hallucinations accru
```
**Caveat** : mistral 7B sur le rôle Juge accepte presque tout (0 rejet sur
18 findings en éval). La TUI de validation humaine reste ton filet de
sécurité dans ce cas.

### Tu as 12-16 GB VRAM (RTX 3060 12GB, RTX 4070 12GB)
Tu peux upgrader le Juge vers une variante plus grosse :

```yaml
ollama:
  models:
    juge: qwen3:14b   # nécessite ~9 GB VRAM
```

Gain attendu : ~5-10 pp d'alignement supplémentaire selon nos mesures
projetées. Pull : `ollama pull qwen3:14b` (9.3 GB).

### Tu as 24+ GB VRAM (RTX 3090, RTX 4090, RTX 5090)
Tu peux pousser plus loin :

```yaml
ollama:
  models:
    integrateur: qwen3:14b
    juge: qwen3:32b           # ou llama3.3:70b-instruct-q4 si tu as ≥48 GB
    rapporteur: qwen3:14b
```

À ce niveau-là, garde quand même l'interviewer en mistral 7B (contrainte
CLAUDE.md règle 3).

### Tu n'as PAS de GPU (CPU only)
Reste sur la config par défaut. Augmente le timeout :

```yaml
ollama:
  timeout_seconds: 240   # 4 min au lieu de 2
```

Compte ~3-5× plus de temps qu'un run GPU. Le Juge qwen3:8B sur CPU pur
peut prendre ~60 s par appel ; un pipeline complet peut dépasser 2 h.

## Modèles testés et rejetés (pour info)

| Modèle | Verdict | Détail |
|---|---|---|
| `qwen3.5:9b` (Q4) | rejeté | Offload CPU 26% sur 8 GB VRAM + mode thinking buggy |
| `mistral-nemo:latest` (12B Q4) | rejeté | Refuse de prendre des décisions tranchées (89% en `medium · next_iteration`) |
| `phi-4` (14B Q4) | non testé | Bons benchmarks math, faible sur LLM-as-a-judge selon CodeJudgeBench |

Mesures complètes : `docs/evaluations/modeles_perf_2026-05-13.md`.

## Vérifier ton install

```bash
# Test 1 : Ollama répond
curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | head -3

# Test 2 : les 2 modèles requis sont là
ollama list | grep -E "mistral:7b-instruct-q4_K_M|qwen3:8B"

# Test 3 : le harness eval marche sur un run existant
python scripts/eval_juge.py ~/.applied-fox/runs/<n'importe_quel_run> --max-findings 3
```

## Si ta config bouge

Pour ré-évaluer les modèles à dispo (les modèles open-weight sortent tous
les 2-3 mois) :

1. Lance le harness sur un run existant avec le nouveau modèle :
   ```bash
   python scripts/eval_juge.py ~/.applied-fox/runs/<run> --model <nouveau-tag>
   ```
2. Compare le taux de rejet et la distribution `high/medium/low/reject`
   avec qwen3:8B (notre baseline actuelle).
3. Si le nouveau modèle rejette mieux et est aussi rapide → édite `config.yaml`.

Voir aussi `docs/evaluations/modeles_perf_2026-05-13.md` pour le protocole.

## Une dernière chose

L'abstraction "profile small/medium/large" qui existait avant la v1.4 a
été supprimée. Pourquoi : on s'est aperçu que le bon design est **1
modèle par agent selon la complexité de sa tâche**, pas un profil
abstrait par hardware. Le mapping `profile → 1 modèle pour tout` était
trompeur (un Juge a besoin de plus d'intelligence qu'un Rapporteur, même
sur la même machine).

Si tu vois encore des références à `profile:` dans un README ou un doc
ancien, c'est un oubli — signale-le.
