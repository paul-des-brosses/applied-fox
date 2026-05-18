# Évaluation Opus 4.7 — Pertinence multi-projets

**Date** : 2026-05-12
**Évaluateur** : Claude Opus-class (LLM-as-a-judge, protocole ROADMAP_MVP §Évaluation Veille)
**Projets testés** : 3 fiches inventées, domaines différents
**Conditions** : profile `small` (mistral 7B Q4), Reddit + RSS actifs, GitHub désactivé (token non hérité par le subshell bash de l'agent)

## Méthode

Pour chaque projet :
1. Fiche `.md` créée à la main, validée par `parse_and_validate`.
2. Pipeline complet exécuté (Éclaireur → Intégrateur → Juge → Rapporteur).
3. Évaluation indépendante de chaque suggestion retenue dans la section
   "À considérer maintenant" du rapport final, selon les axes :
   - **Alignement avec objectifs actifs déclarés** (aligned / partial / non-aligned)
   - **Présence d'hallucinations** dans la description du gain
   - **Justification du Juge** (cohérente / faible / contradictoire)
4. Note globale /10 par projet, puis agrégat.

## Projets testés

### Projet 1 : Serre Connectée Autonome (smart_greenhouse)
- Domaine : hybride hardware/software, irrigation goutte-à-goutte ESP32-S3.
- Objectifs : réduction conso d'eau 40%, T° 15-30°C sans chauffage, autonomie 12 mois capteurs.
- **Résultat pipeline** : 42 findings bruts, 7 suggestions retenues.

### Projet 2 : Tracker LoRa Faune Sauvage (wildlife_lora_tracker)
- Domaine : hardware embarqué basse conso, balise GPS LoRa P2P.
- Objectifs : autonomie 18 mois batterie primaire, poids < 80 g, portée 1.5 km forêt dense.
- **Résultat pipeline** : 34 findings bruts, 5 suggestions retenues.

### Projet 3 : BMS DIY Vélo Électrique 48V (ebike_bms_diy)
- Domaine : hardware critique sécurité, BMS 13S 30A continu / 50A pic.
- Objectifs : sécurité ISO 13849-1 cat. B, coût < 60€, précision ±10 mV cellule.
- **Résultat pipeline** : 72 findings bruts, 9 suggestions retenues.

## Évaluation détaillée

### Projet 1 — Serre Connectée

| # | Suggestion | Source | Alignement | Hallucination |
|---|---|---|---|---|
| 1 | ESP32-S3 GC9A01 SPI Display | r/esp32 | **NON-ALIGNÉ** | "réduit consommation d'eau 40%" alors qu'aucun display dans le projet |
| 2 | Half-bridge SMPS lab bench | r/AskElectronics | **NON-ALIGNÉ** | "consommation +20%" plaquée sur lab bench PSU sans rapport |
| 3 | Capacitive soil moisture review | r/PrintedCircuitBoard | **PARTIEL** | C'est le composant en évaluation, mais l'angle "energy" est faux (perf attendu) |
| 4 | SK9822 LED Matrix ESP32-C6 | r/PrintedCircuitBoard | **NON-ALIGNÉ** | "remplacement ventilation pour 1 zone humidité" — hallucination grossière |
| 5 | ESP32-P4 + ESP32-C5 MIPI board | cnx-software | **NON-ALIGNÉ** | "reduce water consumption by 40%" sur un board ESP32 |
| 6 | ESP32 Stepper Motor Controller | r/PrintedCircuitBoard | **PARTIEL** | Idée (stepper pour pompe) intéressante mais source non pertinente, "autonomie 6 mois" hallucinée |
| 7 | LED Current Limiting | r/arduino | **NON-ALIGNÉ** | Thread Arduino LED drivers, aucun rapport |

**Note Opus 4.7 projet 1 : 2/10**
- Alignement : 0% high, 28% partiel, 72% non-aligné.
- **Échec critère MVP** (80% aligné requis).

### Projet 2 — Tracker LoRa Faune

| # | Suggestion | Source | Alignement | Hallucination |
|---|---|---|---|---|
| 1 | Nvidia Jetson power supply PCB | r/PrintedCircuitBoard | **PARTIEL** | Source non pertinente, mais l'IDÉE (SX1276→SX1262) est juste |
| 2 | JesFs IoT file system MIT | r/embedded | **PARTIEL** | Vraiment utile pour logs basse conso, mais description plaque RAK3172 sans rapport avec le sujet du finding |
| 3 | War stories IoT failed prod | r/embedded | **NON-ALIGNÉ** | "Migration RAK3172 vers SX1262 +90% autonomie" hallucinée |
| 4 | GNSS motorsport 20-25 Hz logger | r/esp32 | **NON-ALIGNÉ** | Logger sport haute fréq vs balise 30 min — opposé. "+100% portée +75% autonomie" hallucinées |
| 5 | Balancing Robot v3 PCB | r/PrintedCircuitBoard | **NON-ALIGNÉ** | "ER18505 réduit autonomie à < 12 mois" — formulation contradictoire avec l'objectif (qui veut +18 mois) |

**Note Opus 4.7 projet 2 : 3/10**
- Alignement : 0% high, 40% partiel, 60% non-aligné.
- Point positif : le Juge a explicitement rejeté 2 findings avec mention "hallucination LLM amont" dans la raison.

### Projet 3 — BMS DIY Vélo Électrique

| # | Suggestion | Source | Alignement | Hallucination |
|---|---|---|---|---|
| 1 | TableTop PCB Tile with AI | r/esp32 | **NON-ALIGNÉ** | Game design AI, zéro rapport avec BMS |
| 2 | STM32F103C8T6 bare minimum | r/PrintedCircuitBoard | **PARTIEL** | Vrai chipset utilisé dans le projet, mais contrainte hallucinée "compatible vitesse variable" |
| 3 | STM32 + SIM800L + BQ24133 PCB | r/PrintedCircuitBoard | **NON-ALIGNÉ** | "augmente autonomie de ~10 mV" — mV n'est pas une unité d'autonomie |
| 4 | LED Current Limiting | r/arduino | **NON-ALIGNÉ** | "Diode protection LED → objectif sécurité ISO 13849" — confusion totale (LED ≠ MOSFET puissance) |
| 5 | Self-balancing cube control PCB | r/PrintedCircuitBoard | **NON-ALIGNÉ** | "Shunt 1mΩ 75A de type INR21700-40T" — confusion cellule/shunt |
| 6 | Rocket Flight Computer | r/PrintedCircuitBoard | **NON-ALIGNÉ** | "PCB 70µm cuivre diminue coût" — déjà 70µm dans la fiche |
| 7 | DAQ board 4 vs 6 layers | r/PrintedCircuitBoard | **PARTIEL** | Vraie discussion technique sur stack-up PCB, mais description hallucine "réduit coût + précision tension simultanément" |
| 8 | Universal 12V PC fan controller | r/PrintedCircuitBoard | **NON-ALIGNÉ** | Suggestion NTC 8k au lieu de 10k arbitraire et hallucinée |
| 9 | ESP32-C3 24V Robotic Gripper | r/esp32 | **NON-ALIGNÉ** | "MOSFET IRFB7430 réduit coûts BMS de 25%" — invention pure |

**Note Opus 4.7 projet 3 : 2/10**
- Alignement : 0% high, 22% partiel, 78% non-aligné.
- **Bug critique côté Juge** : a rejeté `BQ25616 based voltage supply` (composant TI battery management, potentiellement pertinent) avec raison confuse "contrainte d'utilisation de seule une cellule chimique".

## Agrégat sur les 3 projets

| Métrique | Valeur | Cible MVP ROADMAP |
|---|---:|---:|
| Total suggestions retenues | 21 | — |
| Vraiment alignées (high) | **0 (0%)** | ≥ 80% |
| Partiellement alignées | 6 (29%) | — |
| Non-alignées | 15 (71%) | 0 (zéro tolérance) |
| Hallucinations identifiées | 14 (67%) | — |
| Note globale Opus 4.7 | **~2.5/10** | ≥ 6/10 |

**Verdict : ÉCHEC du critère de pertinence MVP.**
Le pipeline produit techniquement des suggestions, mais leur valeur est faible :
- Aucune suggestion ne propose un changement précis qu'un ingénieur appliquerait sans relire la fiche.
- 67% contiennent une hallucination quantitative ("+40% d'eau", "+90% d'autonomie") inventée par l'Intégrateur.
- 71% sont issues de Reddit r/PrintedCircuitBoard ou r/AskElectronics, qui sont des forums de review PCB DIY, pas de veille techno.

## Diagnostic des causes racines

### 1. Source dominante = forum de review PCB DIY
71% des suggestions retenues viennent de `r/PrintedCircuitBoard` et `r/AskElectronics`. Ces subreddits agrègent des projets DIY divers (LED matrix, rocket flight, balancing cube, etc.) qui contiennent les bons mots-clés techniques (ESP32, LoRa, MOSFET, PCB) mais aucun ne traite de veille technologique alignée.

**Impact** : le filtre déterministe laisse passer le bruit parce que les mots-clés sont présents. Le LLM filtre ensuite mal parce qu'il est entraîné à trouver des liens.

### 2. L'Intégrateur hallucine systématiquement
Pattern observé sur 14 suggestions sur 21 : la description "Ce qui change" plaque l'objectif principal du projet sur un finding sans rapport, en inventant une métrique quantitative. Exemples :
- "Display SPI réduit consommation d'eau de 40%" (greenhouse)
- "MOSFET IRFB7430 réduit coûts BMS de 25%" (BMS, finding parle d'un gripper robotique)
- "PCB 70µm cuivre diminue coût" alors que la fiche utilise déjà ce stack-up

**Cause probable** : le prompt de l'Intégrateur incite à trouver un lien à tout prix ("estime un gain quantitatif") et le LLM 7B Q4 invente quand l'information n'est pas dans le finding.

### 3. Le Juge laisse passer mais détecte parfois
Sur 21 suggestions retenues, le Juge a au moins explicitement marqué 4 findings comme "hallucination LLM amont" dans les rejetés — le mécanisme fonctionne donc partiellement. Mais sur les findings retenus, l'évaluation `relevance: high/medium` ne détecte pas l'absurdité de "PCB → consommation d'eau".

### 4. GitHub désactivé
Le token `GITHUB_TOKEN` n'a pas été hérité par le subshell bash où le pipeline a été lancé (problème d'environnement d'agent). Effet : 71% des findings viennent d'une seule source bruyante, sans le contrepoint de repos GitHub typés (qui auraient été plus alignés sur le domaine).

### 5. Modèle 7B Q4 (profile small)
Tous les runs sont en mistral 7B Q4. Pour des tâches de filtrage de pertinence et de détection de hors-sujet, un 14B (medium) ou 32B (large) ferait probablement mieux. À tester comme axe d'amélioration prioritaire.

## Recommandations actionnables

### Court terme (sans refonte)
1. **Blacklister `r/PrintedCircuitBoard` et `r/AskElectronics`** dans la config par défaut. Garder seulement les subreddits domaine-spécifiques (`r/esp32`, `r/embedded`, `r/LoRa`, `r/batteries`, etc.).
2. **Activer GitHub** systématiquement : passer `GITHUB_TOKEN` via `.env` chargé par `python-dotenv` (déjà en place dans `cli.py` mais peut-être pas en mode direct python).
3. **Durcir le prompt Intégrateur** : ajouter "si tu n'es pas certain à 80% qu'il y ait un lien explicite entre le titre du finding et un composant de la fiche, retourne `integrable=False`".
4. **Tester profile `medium`** (qwen2.5 14B) sur le même corpus de 3 projets pour mesurer l'écart.

### Moyen terme (refonte ciblée)
1. **Stratégie de requêtes** : générer des requêtes plus spécifiques par composant critique (ex. "BQ76940 alternative", "RAK3172 vs SX1262 power") plutôt que des requêtes thématiques larges.
2. **Anti-hallucination en post-traitement** : un check déterministe sur la description de l'Intégrateur — si la description mentionne une métrique chiffrée qui n'apparaît pas dans le finding source, rejeter.
3. **Évaluation continue** : intégrer ce protocole comme test de régression. Si la note tombe sous 4/10, refuser de merger.

### Long terme (V2 backlog)
1. **Sources supply chain** (Octopart) pour la veille EOL/prix réelle.
2. **Mode batch multi-projets** pour amortir le coût d'une éval globale.
3. **Multi-provider** : permettre d'utiliser Claude/GPT-4 sur l'Intégrateur (le maillon faible) tout en gardant Ollama local sur les autres.

## Conclusions pour le portfolio

**Honnêteté intellectuelle** : ces résultats doivent figurer dans la démonstration portfolio. Ils montrent :
- Que l'architecture est solide (pipeline tourne, schémas validés, artefacts générés).
- Que l'évaluation est rigoureuse (protocole défini, mesurée, documentée).
- Que les limites sont identifiées avec leurs causes racines et un plan d'amélioration.
- C'est exactement ce qu'on attend d'un ingénieur en stage R&D : ne pas vendre du vent.

Le **MVP technique est livré**, mais la **qualité du signal final n'atteint pas le critère ROADMAP**. Les améliorations sont identifiées et chiffrables. La version 1.1 (blacklist + GitHub réactivé + prompt durci + profile medium) devrait permettre d'atteindre 60%+ d'alignement.

## Artefacts

- Fiches projets : `projects/smart_greenhouse.md`, `projects/wildlife_lora_tracker.md`, `projects/ebike_bms_diy.md`
- Runs :
  - `~/.applied-fox/runs/20260512_110442_smart_greenhouse/`
  - `~/.applied-fox/runs/20260512_111918_wildlife_lora_tracker/`
  - `~/.applied-fox/runs/20260512_113154_ebike_bms_diy/`
- Rapports HTML lisibles dans chaque run_dir : `04_rapport.html`
