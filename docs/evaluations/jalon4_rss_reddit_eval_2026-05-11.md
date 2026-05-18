# Évaluation Jalon 4 — Pipeline multi-source Reddit + RSS

**Date** : 2026-05-11
**Fiche projet testée** : `projects/esp32_weather_station.md` (Station Météo ESP32, ESP-IDF, BME280, SX1276, LiPo 2000 mAh, panneau solaire 5W)
**Modèle Éclaireur** : `mistral:7b-instruct-q4_K_M` (profile small)
**Sources actives** : Reddit (endpoints publics), RSS (5 flux : Hackaday, CNX-Software, Adafruit, Electronics Weekly, EE Times)
**Méthode** : run du pipeline puis recherche web indépendante sur les mêmes sujets pour comparer

---

## 1. Statistiques quantitatives

| Métrique | Valeur | Critère Jalon 4 | Verdict |
|---|---|---|---|
| Findings bruts (Reddit) | 67 | — | OK |
| Findings bruts (RSS) | 109 | — | OK |
| Total brut cumulé | 176 | — | OK |
| Rejets alignement | 97 (55 %) | — | Filtrage efficace |
| Rejets dedup | 20 | — | OK |
| Rejets fraîcheur / score | 0 | — | Normal (RSS exclus du score) |
| Findings retenus | 59 | — | — |
| Ratio rejet global | **66.5 %** | 60-70 % | ✅ Dans la cible |
| Findings structurés | 53 | — | OK |
| Échecs structuration LLM | 6 (10 %) | < 5 % visé Jalon 5 | ⚠️ Trop haut |
| Distribution angles | energy:29, obsolescence:18, perf:2, regulation:2, supply:1, price:1 | — | Cohérent projet |

**Validation quantitative : succès.** Le ratio de rejet est dans la cible et la distribution des angles reflète bien la nature du projet (autonomie, EOL).

---

## 2. Évaluation qualitative — méthode

Pour évaluer si les findings apportent un **vrai signal**, j'ai fait en parallèle une recherche web indépendante sur les sujets clés du projet, puis comparé. Trois axes testés :

1. **LoRa SX1276 → SX1262** : un upgrade matériel évident pour ce projet
2. **BME280 issues connus** : drift, self-heating, alternatives
3. **ESP32 deep sleep optimisation** : best practices pour autonomie 6 mois

### Recherche indépendante — résultats

**LoRa SX1276 vs SX1262** : SX1262 a 57 % de réduction de courant RX (4.6 mA vs 10.8 mA sur SX1276). Pour une station avec batterie 2000 mAh transmettant chaque 15 min, l'autonomie passe de **544 jours à 952 jours** (+75 %). Recommandation officielle Semtech pour tout nouveau design.

**BME280 issues** : self-heating mesuré (+1.2°C bias à basse T°), drift humidité après plusieurs heures, longévité spec 2-3 ans, alternatives premium SHT3x (Sensirion) avec membrane PTFE pour environnements hostiles.

**ESP32 deep sleep** : < 10 µA atteignable avec ESP32-S3, RTC memory pour WiFi fast connect (×2 autonomie), 4×18650 + 5W solaire largement suffisant pour fonctionnement perpétuel.

---

## 3. Comparaison Applied Fox vs recherche indépendante

### Axe 1 — LoRa SX1262 upgrade

**Findings Applied Fox** : 2 sur le sujet.
- *"[Schematic Review] Ultra-Low Power LoRa Sensor Node STM32U073 + E22 (SX1262)"* — bonne source identifiée, mais description LLM **confuse** : *"L'utilisation du SX1276 pour la communication LoRa n'est pas compatible avec la station météo connectée ESP32"* (factuellement faux, c'est juste une référence à un design moderne).
- *"An Arduino library for the EByte E22-T series LoRa modules"* — descriptif correct, mais sans articulation stratégique de l'enjeu.

**Diagnostic** : Le pipeline trouve les bonnes sources mais le **LLM 7B échoue à articuler l'insight critique**. L'utilisateur lit "obsolescence module LoRa SX1276" sans comprendre l'enjeu chiffré (75 % d'autonomie en plus). Pour saisir cette info, il devra cliquer sur l'URL et lire la source.

**Note** : **6/10**. Signal présent, raisonnement défaillant.

### Axe 2 — BME280 issues

**Findings Applied Fox** : 6 sur BME280, mais aucun ne touche les problèmes documentés :
- *"très peu d'énergie"* — vrai mais générique
- *"performances relativement élevées"* — phrase creuse
- *"may no longer be supported by the manufacturer"* — **hallucination LLM** (Bosch produit toujours le BME280)
- Rien sur drift, self-heating, alternatives SHT3x

**Diagnostic** : **Signal manquant**. La recherche Reddit a remonté des posts BME280 mais aucun ne discutait des issues spécifiques. Sur RSS, aucun article récent sur le BME280 (capteur ancien, peu d'actu). Les alternatives premium (SHT3x) n'ont pas été cherchées car non listées comme composants du projet.

**Note** : **3/10**. Pas de valeur ajoutée par rapport à ce que l'utilisateur sait déjà.

### Axe 3 — ESP32 deep sleep optimisation

**Findings Applied Fox** : **0 sur ce thème**.

**Diagnostic** : Manqué complètement. Le `_generate_queries` produit des requêtes du type `{composant} alternative/review/issue/vs`. Or "deep sleep optimization" n'est pas un composant, c'est un **pattern technique** — il n'est jamais cherché. C'est une faille architecturale du générateur de requêtes, pas du LLM.

**Note** : **0/10**.

### Axe bonus — Solar / Battery

3 findings remontés, dont 2 pertinents :
- *"Demonstrates 6 months of autonomous operation on a LiPo battery and solar panel"* — confirme la faisabilité de l'objectif projet
- *"Is it safe to power esp32 c3 super mini with tp4056"* — discussion concrète de charger LiPo, utile

**Note** : **6/10**. Pertinence correcte, descriptions LLM acceptables.

---

## 4. Synthèse qualitative

### Ce qui marche

- **Récolte multi-source efficace** : 176 raws sur 2 sources, ratio 67/109 équilibré
- **Filtre déterministe solide** : 66.5 % de rejet, distribution des angles cohérente
- **Identification de sources réelles** : le pipeline trouve effectivement des posts/articles pertinents (l'URL est correcte, le titre est juste)
- **Couverture diversifiée** : 6 angles distincts, pas de fixation mono-thématique

### Ce qui ne marche pas

1. **Le LLM 7B est trop limité pour la structuration**
   - Hallucinations sur les faits ("SX1276 obsolète", "BME280 may no longer be supported")
   - Descriptions creuses ou contradictoires
   - 10 % d'échec de structuration (cible Jalon 5 : < 5 %)

2. **Le générateur de queries est composant-centrique**
   - Manque les "best practices" et patterns techniques transverses
   - Ex : "ESP32 deep sleep optimization", "low power LoRaWAN class A", "outdoor IP65 enclosure design"

3. **Pas de cross-référencement**
   - 2 findings parlent du SX1262, 1 du SX1276 → pas de mise en perspective "le marché bouge vers SX1262, ton SX1276 est legacy"
   - C'est le job de l'Intégrateur (Jalon 5), pas du pipeline actuel

4. **L'utilisateur reste obligé de cliquer sur les URLs** pour vérifier
   - Le rapport final (Jalon 6) devra rendre les URLs sources très visibles
   - Sans cette visibilité, l'utilisateur risque de prendre les descriptions LLM erronées au pied de la lettre

---

## 5. Recommandations actionables

### Immédiat (avant Jalon 5)

1. **Tester un meilleur modèle Éclaireur**
   - `qwen3.5:9b` (déjà installé sur la machine de test) → tester en override sur l'Éclaireur
   - `mistral-nemo:latest` (12B, déjà installé) → meilleure prose française, à comparer
   - Critère : passer de 10 % à < 5 % d'échec de structuration, et réduire les hallucinations factuelles

2. **Enrichir le générateur de queries**
   - Ajouter des requêtes par **objectif actif** : pour chaque objectif "Tenir 6 mois d'autonomie", générer une query "ESP32 6 months battery autonomy" — pas qu'une query par composant
   - Ajouter des requêtes par **contrainte** : "IP65 outdoor enclosure" si la contrainte existe

### Jalon 5

3. **L'Intégrateur doit faire le cross-référencement**
   - Verdict d'intégration doit pouvoir dire : "3 findings indépendants pointent vers SX1262 → upgrade probablement pertinent"
   - Sinon le pipeline reste un agrégateur de bruit corrélé

4. **Le Juge doit corriger les hallucinations factuelles**
   - Recevoir la description LLM ET l'URL ET le titre original → flagger l'incohérence
   - Ex : "Le LLM dit 'BME280 obsolète' mais le titre source dit juste 'Flight Computer HELP' → finding non fiable"

### Jalon 6

5. **Le rapport final doit afficher les URLs sources de manière proéminente**
   - Sous chaque suggestion : "Sources : [titre du post Reddit] · [titre article Hackaday]"
   - Sans URL, le rapport est moins fiable qu'une recherche manuelle

---

## 6. Verdict global du Jalon 4

| Dimension | Note | Commentaire |
|---|---|---|
| Volume de signal | 8/10 | 176 raws, bonne diversité |
| Filtrage déterministe | 8/10 | Ratio cible atteint, pas de faux positifs alignement vus |
| Qualité structuration LLM | 4/10 | Trop d'hallucinations sur 7B |
| Pertinence stratégique | 5/10 | Trouve les sources, manque l'articulation |
| Découverte de nouveauté | 4/10 | Loupe les patterns techniques transverses (deep sleep, etc.) |

**Verdict** : Le pipeline Jalon 4 délivre une couverture de surveillance qui est **comparable à une recherche manuelle débutante**, pas à une recherche manuelle ciblée par un ingénieur expérimenté. Il **identifie les sujets et les sources** mais **rate la hiérarchisation et l'articulation stratégique**.

Pour atteindre la valeur ajoutée promise par la VISION ("l'assistant qui ne décide jamais à ta place mais qui te fait gagner du temps"), il faut :
- L'Intégrateur (cross-référencement)
- Le Juge (anti-hallucination)
- Et probablement un meilleur LLM Éclaireur (test prévu)

Le Jalon 4 valide l'architecture multi-source, mais pas encore la promesse produit.

---

## Annexes

### A. Couverture par recherche indépendante (sources externes)

- **BME280 issues** : Bosch community, Adafruit forums, Electrobob blog
- **SX1276 vs SX1262** : Rokland blog, NiceRF, Zbotic, Semtech datasheets
- **ESP32 deep sleep** : esp32.co.uk, Home Assistant community, GitHub projects ESPHome

Ces sources ne sont **pas dans les flux RSS configurés** d'Applied Fox (Hackaday, CNX-Software, Adafruit, EW, EET). Adafruit forums ≠ Adafruit blog. C'est un trou de couverture à corriger en Jalon 4 final ou Jalon 7.

### B. Distribution des findings par sous-source

```
news (RSS)    : 109 raws  →  rejets surtout par alignement (RSS est éditorial, peu de signal composant-spécifique)
community     :  67 raws  →  meilleure conversion (Reddit cible déjà /r/embedded, /r/esp32)
```

Le RSS apporte du volume mais peu de signal aligné. Question pour V2 : faut-il pondérer le filtre alignement en fonction de la source ?
