# Évaluation Jalon 4 — Enrichissement du générateur de requêtes

**Date** : 2026-05-11
**Contexte** : la baseline `jalon4_rss_reddit_eval_2026-05-11.md` avait identifié que `_generate_queries()` était composant-centrique (`{composant} alternative/review/issue/vs`) et ratait les patterns techniques transverses. Conséquence mesurée : **0 finding sur "ESP32 deep sleep optimization"**, alors que c'est l'un des sujets les plus critiques pour le projet.
**Hypothèse testée** : ajouter des requêtes extraites des objectifs actifs et des contraintes non négociables via patterns regex débloque les patterns techniques transverses.
**LLM** : `mistral:7b-instruct-q4_K_M` (identique runs précédents)
**Sources** : Reddit + RSS (identiques)

---

## Implémentation

Modifications dans `src/agents/eclaireur.py` :

1. Ajout d'un dictionnaire `_OBJECTIVE_PATTERNS` (8 entrées) qui mappe des patterns regex (bilingue FR/EN) vers des listes de requêtes anglaises :
   - autonomie / battery life → "deep sleep optimization battery life", etc.
   - low power / deep sleep / µa → "RTC memory wifi fast reconnect", etc.
   - solaire / solar → "solar panel MPPT charging IoT", etc.
   - lorawan / lora → "SX1262 vs SX1276 comparison", etc.
   - outdoor / IP65 → "IP65 IP67 housing 3D printed embedded", etc.
   - GPS / GNSS → "low power GPS module embedded", etc.
   - précision / accuracy → "sensor calibration accuracy embedded"
   - transmission / range → "long range wireless IoT low power"

2. Nouvelle fonction `_extract_pattern_queries(text, project, seen_queries)` :
   - Pour chaque pattern qui matche le texte, ajoute toutes ses queries (avec dédup global).
   - Le `component_hint` pointe vers un composant cité dans le texte, sinon le premier composant critique.

3. Refactor de `_generate_queries(project)` en 3 passes :
   1. Par composant (existant : suffixes "alternative", "review", "issue", "vs")
   2. Par objectif actif (nouveau)
   3. Par contrainte non négociable (nouveau)

   Tout passe par un `seen: set[str]` partagé pour éviter les doublons.

---

## Résultats quantitatifs (vs baseline prompt durci)

| Métrique | Prompt durci | + Queries enrichies | Δ |
|---|---|---|---|
| Queries générées | 28 | **40** | +43 % |
| Raws Reddit | 67 | **148** | +120 % |
| Raws RSS | 109 | 109 | = |
| Total raws | 176 | **257** | +46 % |
| Rejets alignement | 97 (55 %) | 97 (38 %) | **stable en absolu, moins en %** |
| Findings kept | 59 | **132** | **×2.2** |
| Structuration réussie | 100 % | **100 %** | = |
| Hallucinations obsolescence | 2 | **0** | -100 % |
| Filter ratio | 66.5 % | **48.6 %** | baisse normale¹ |

¹ La baisse du filter_ratio est un **signal positif** : les nouvelles queries étant plus alignées avec le projet par construction ("deep sleep optimization" → posts pertinents), le filtre d'alignement rejette moins. C'est un meilleur taux raw/utile, pas une dégradation.

### Distribution des angles

| Angle | Avant | Après |
|---|---|---|
| energy | 42 | **98** |
| perf | 11 | 30 |
| obsolescence | 2 | 0 |
| supply | 3 | 3 |
| price | 1 | 1 |
| regulation | 0 | 0 |

L'explosion de `energy` (×2.3) reflète l'efficacité des nouvelles queries autour de l'autonomie/deep sleep/solaire, qui dominent les objectifs du projet test.

---

## Résultats qualitatifs sur les 3 axes critiques (suite éval baseline)

### Axe 1 — LoRa SX1276 → SX1262 : confirmé

1 finding pertinent, description correcte (cf. éval précédente). La query "SX1262 vs SX1276 comparison" est désormais générée mais le filtre d'alignement la rejette si les findings retournés ne mentionnent pas explicitement un composant projet. Mécaniquement OK, à laisser tourner sur la durée pour voir si des findings émergent.

### Axe 2 — BME280 issues : enrichi

5 findings (vs 3 avant), pépite confirmée et étendue :
> *"BME280 is not good for ambient temperature readings, DHT22 is okay for casual use cases but not accurate or fast enough, SHT31 is old but good enough for most"*

Ma recherche externe avait identifié exactement ces alternatives (SHT3x/4x Sensirion). **Validation croisée réussie.**

### Axe 3 — ESP32 deep sleep optimization : **DÉBLOQUÉ**

**Avant : 0 findings. Après : 7 findings.**

Sélection des plus pertinents :

> *"ESP32 WiFI weather node: ~8 mA in 'deep sleep'"* — anomalie documentée, post communautaire qui aurait pu sauver l'utilisateur d'un piège classique (configuration WiFi mal coupée pendant deep sleep).

> *"Experiment: STM32-based, Nano-pinout board with ~1 µA sleep"* — comparaison radicale : 1.1 µA STM32 vs ~8 mA ESP32 = **rapport 7000:1**. Insight stratégique pour un projet "6 mois d'autonomie".

> *"How to save battery in deep sleep with sensors?"* — best practices terrain (GPIO bas pour capteurs).

**Verdict** : le générateur enrichi a fait sortir un axe entier qui était invisible avant. La query "deep sleep optimization battery life" a fait son job.

### Nouveaux axes débloqués (non testés dans la baseline)

**MPPT solar charging** : 2 findings dont :
> *"I built an ESP32 add-on that gives my cheap MPPT solar controller a brain"*

C'est exactement le type d'info dont a besoin un projet "batterie LiPo + panneau solaire 5W + MPPT".

**IP65 enclosure** : 1 finding :
> *"ESP32 + PM Sensor – Ideas for a weatherproof yet breathable enclosure?"*

Couvre la contrainte projet (déploiement outdoor 6 mois).

---

## Limites identifiées

### Volume élevé : 132 findings

Trop pour une lecture humaine séquentielle. À ce stade le pipeline devient **dépendant** de l'Intégrateur (Jalon 5) pour le cross-référencement et de la Juge pour la priorisation. Sans ces deux étages, l'utilisateur va recevoir un dump de 132 cards et ne pas savoir où regarder en premier.

**Décision** : ne pas chercher à réduire artificiellement le volume au Jalon 4. Le signal est bon, les filtres aval doivent prendre le relais.

### Patterns regex linguistiquement fragiles

Le pattern `\b(transmission|longue\s+distance|range|portée|portee)\b` ne matche pas "Transmettre". Si le projet test avait dit "Transmettre une mesure" sans dire "Transmission", la query "long range wireless" ne serait pas générée.

**Mitigation possible (V2)** : passer par un LLM en amont pour extraire les patterns techniques d'un objectif libre, plutôt que regex. Trade-off coût LLM vs robustesse linguistique. À ne pas faire au MVP.

### Le hint reste imprécis

Le `component_hint` de la query "deep sleep optimization battery life" pointe vers "ESP32-WROOM-32E" (premier composant critique), mais le finding remonté peut concerner STM32 (comparaison). L'alignement reste correct via le filtre déterministe, mais le tracing est moins propre.

---

## Bilan des 4 itérations Jalon 4

| Itération | Findings | Hallucinations | Axes critiques couverts |
|---|---|---|---|
| 1. Reddit seul (fin Jalon 3) | 46 | nombreuses | 0 / 3 |
| 2. + RSS | 53 | 18 (34 %) | 1 / 3 |
| 3. + Prompt durci | 59 | 2 (3 %) | 1.5 / 3 |
| 4. **+ Queries enrichies** | **132** | **0 (0 %)** | **3 / 3 + 2 nouveaux axes** |

Le pipeline est passé d'un **agrégateur naïf à un outil qui remonte du signal stratégique aligné avec les objectifs métier**. La validation croisée avec ma recherche web externe indépendante est concluante sur les 3 axes testés.

---

## Décisions actées

1. ✅ **Conserver le générateur enrichi** comme nouveau baseline Éclaireur
2. ⏭️ **Jalon 5 — Intégrateur** devient prioritaire pour digérer le volume 132 findings
3. ⏭️ **Ajout de GitHub** comme 3e source (en cours) pour compléter les retours communautaires
4. ⏭️ **Reporter les patterns LLM-based** en V2 si les regex montrent leurs limites en usage réel
