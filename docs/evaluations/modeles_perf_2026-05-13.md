# Performance des modèles Ollama — Applied Fox Juge

**Date** : 2026-05-13
**Contexte** : choix définitif du modèle pour chaque rôle d'agent du pipeline
de veille, mesuré sur le harness `scripts/eval_juge.py` qui rejoue le Juge
en isolation sur des findings produits par un run précédent.

## Configuration matérielle de référence

| Composant | Spec |
|---|---|
| CPU | Intel Core i7-11800H @ 2.30 GHz (8 cœurs / 16 threads) |
| RAM | 63.7 GB DDR4 |
| GPU dédié | NVIDIA GeForce RTX 3070 Laptop GPU (8 GB VRAM, driver 572.16) |
| GPU intégré | Intel UHD (utilisé pour l'affichage seulement) |
| OS | Windows 11 Professionnel |
| Runtime LLM | Ollama (port 11434) |
| Inférence | GPU compute via CUDA, modèles Q4_K_M sauf mention |

**Rappel architectural** : sur RTX 3070 8 GB, un modèle Q4 doit tenir
sous ~7 GB en VRAM pour éviter le CPU offload qui dégrade la vitesse de
3-5× et peut casser le mode "thinking" de certains modèles.

## Protocole de test

1. Un pipeline a été lancé jusqu'à l'Intégrateur inclus sur 3 projets
   (greenhouse, tracker LoRa, BMS DIY 48V), produisant
   `02_integrateur_verdicts.json` pour chaque.
2. Le harness charge ces verdicts + les findings, et appelle uniquement
   l'agent Juge en boucle sur les findings marqués `integrable=True`.
3. Mesures : taux de parsing JSON, temps par appel, distribution des
   verdicts `relevance` et `timing_recommendation`.

L'évaluation qualitative (alignement avec les objectifs du projet) est
faite par lecture manuelle des verdicts produits.

## Résultats par modèle

### `mistral:7b-instruct-q4_K_M` (baseline)

| Métrique | Greenhouse (18 findings) |
|---|---:|
| JSON parsé | 18/18 (100%) |
| Temps total | 117 s |
| Temps moyen / appel | **6.5 s** |
| Distribution relevance | high=9, medium=5, low=4, **reject=0** |
| Distribution timing | now=10, next_iter=3, noted_for_future=5, reject=0 |

**Comportement** : accepte la quasi-totalité des findings comme pertinents,
y compris des hors-sujet manifestes ("Motorcycle wiring", "amsOsram sells
sensor business", "ha-simple-media-player" tous notés `high · now`).

**Verdict** : insuffisant comme Juge — pas de capacité à rejeter le bruit.
Utilisable pour des tâches mécaniques (Intégrateur, Rapporteur) qui ne
demandent pas de méta-raisonnement.

### `qwen3:8B` (Q4_K_M, ~5 GB VRAM)

**Greenhouse (18 findings)** :

| Métrique | Valeur |
|---|---:|
| JSON parsé | 18/18 (100%) |
| Temps total | 256 s |
| Temps moyen / appel | **14.3 s** |
| Distribution relevance | high=2, medium=8, low=1, **reject=7 (39%)** |

**Tracker LoRa (21 findings)** :

| Métrique | Valeur |
|---|---:|
| JSON parsé | 21/21 (100%) |
| Temps total | 324 s |
| Temps moyen / appel | **15.4 s** |
| Distribution relevance | high=6, medium=7, low=0, **reject=8 (38%)** |

**BMS DIY (22 findings)** :

| Métrique | Valeur |
|---|---:|
| JSON parsé | 22/22 (100%) |
| Temps total | 286 s |
| Temps moyen / appel | **13.0 s** |
| Distribution relevance | high=0, medium=8, low=3, **reject=11 (50%)** |

**Comportement** : rejette agressivement les hors-sujet (Pong, Motorcycle,
ha-media-player, Porsche KVM, LTE Formula Student, e-ink litter scooper,
ESP32 dryager). Garde les vraies pépites (`RAK3172`, `ArduLora`,
`SoilMoisureLogger`, `Adafruit_CircuitPython_SHT31D`, `ErriezMHZ19B`,
`INA219_WE`, `bq769x0-arduino-library`, `STM32 Forever on Indoor Light`).

**Alignement qualitatif** (lecture manuelle des verdicts retenus) :
- Greenhouse : ~82% des findings retenus sont pertinents
- Tracker : ~70% des findings retenus sont pertinents
- BMS : ~50% des findings retenus sont pertinents (anchors STM32 moins discriminants)

**Verdict** : meilleur choix pour le Juge sur cette config matérielle.
Tient en VRAM proprement, ~2× plus lent que 7B mais qualité de jugement
significativement supérieure.

### `qwen3.5:9b` (Q4_K_M, ~6.6 GB initial, ~8.3 GB avec contexte)

**Tests pratiques** : modèle inutilisable sur cette config.

| Métrique | Constat |
|---|---|
| VRAM nécessaire (avec context) | 8.3 GB |
| VRAM tenue effectivement | 6.13 GB |
| CPU offload | ~26 % du modèle |
| Test isolé (prompt court) | OK, retourne JSON propre |
| Test prompt long (Juge réel) | Boucle de "thinking" interminable, échec JSON |
| Test interactif `ollama run` | "Combien de présidents en France" → 366 s de "thinking", aucune réponse |

**Cause** : le 2.18 GB en RAM CPU + le mode "thinking" implicite par défaut
de Qwen3.x fait diverger le modèle sur des prompts un peu longs. Le débit
tombe à ~0.5-1 token/s, ce qui rend toute interaction impossible.

**Verdict** : à exclure. Nécessite ≥ 10 GB VRAM (RTX 3080+ ou RTX 4070+).

### `mistral-nemo:latest` (12B, Q4)

**Greenhouse (18 findings)** :

| Métrique | Valeur |
|---|---:|
| JSON parsé | 18/18 (100%) |
| Temps total | 302 s |
| Temps moyen / appel | **16.8 s** |
| Distribution relevance | high=0, medium=16, low=2, **reject=0** |
| Distribution timing | now=0, next_iter=15, noted_for_future=3, reject=0 |

**Comportement** : refuse de prendre une décision tranchée. Classe 89%
des findings en `medium · next_iteration`, quelle que soit la pertinence
réelle. "Motorcycle wiring" et "ESP-FLY DIY drone" arrivent au même niveau
que `SoilMoisureLogger`.

**Verdict** : inutilisable comme Juge. Plus lent que qwen3:8B et qualité
de tri largement inférieure. Pas d'amélioration vs mistral 7B malgré la
taille supérieure.

## Tableau de synthèse

| Modèle | Taille | VRAM occupée | Offload CPU | Temps/appel | Taux rejet | Qualité jugement |
|---|---:|---:|---:|---:|---:|---|
| mistral:7b-instruct-q4_K_M | 4.4 GB | 5.2 GB | 0% | 6.5 s | **0%** | Accepte tout |
| **qwen3:8B (Q4_K_M)** | **5.0 GB** | **6.0 GB** | **0%** | **14.2 s** | **39-50%** | **Tri rigoureux** |
| qwen3.5:9b (Q4_K_M) | 6.6 GB | 6.1 GB | 26% | inutilisable | — | Boucle infinie |
| mistral-nemo:latest (12B Q4) | 7.1 GB | ~6.5 GB | ~10% | 16.8 s | 0% | Refuse de décider |

## Recommandation officielle Applied Fox

Pour le hardware de référence (RTX 3070 8 GB ou équivalent 8-12 GB VRAM) :

```yaml
ollama:
  models:
    interviewer:  mistral:7b-instruct-q4_K_M   # contrainte CLAUDE.md règle 3 (local + 7B)
    eclaireur:    # plus d'appel LLM (déterministe)
    integrateur:  mistral:7b-instruct-q4_K_M   # tâche mécanique, 7B suffit
    juge:         qwen3:8B                      # méta-raisonnement, nécessite Qwen3
    rapporteur:   mistral:7b-instruct-q4_K_M   # 1 seul appel synthèse, 7B suffit
```

**Pourquoi qwen3:8B uniquement pour le Juge** : c'est le seul rôle qui demande
du méta-raisonnement ("ce post hors-sujet ressemble-t-il malgré tout à mon
projet ?"). Les autres agents font des tâches mécaniques (sérialisation,
décision binaire d'intégrabilité, synthèse en une phrase) où mistral 7B est
suffisant et 2× plus rapide.

**Fallback hardware contraint** : si qwen3:8B ne tient pas, le Juge peut être
basculé sur mistral 7B au prix d'un taux de rejet ~0 (accepte tout). Dans ce
cas la TUI de validation humaine porte tout le poids du tri.

## Limites de cette évaluation

1. **Sur 3 projets seulement** (greenhouse, tracker LoRa, BMS DIY). Le
   pattern peut varier sur d'autres domaines (logiciel pur, papers
   académiques, etc.).
2. **Évaluation qualitative manuelle** (par moi, l'auteur). Une éval
   Opus 4.7 LLM-as-a-judge plus rigoureuse serait souhaitable.
3. **Pas de mesure de variance** : un seul run par (modèle, projet). Les
   LLMs sont non-déterministes ; un re-run peut donner des chiffres
   différents à ±5-10pp.
4. **Modèles V2 non testés** : qwen3:14b (nécessite ≥ 10 GB VRAM),
   gemma 3, deepseek-r1:14b, etc. Ces modèles pourraient être meilleurs
   mais demandent un hardware plus capable.

## Pour ré-évaluer

Cf. `scripts/eval_juge.py` :

```bash
# Test rapide sur un run existant
python scripts/eval_juge.py ~/.applied-fox/runs/<run_dir> --model <ollama_tag>

# Limiter le nombre de findings (debug rapide)
python scripts/eval_juge.py ~/.applied-fox/runs/<run_dir> --model <tag> --max-findings 5
```

Le harness sauvegarde les résultats dans `<run_dir>/juge_eval_<model>.json`
pour comparaison ultérieure. Un appel ne coûte ~5 min vs 25-40 min pour
un pipeline complet.
