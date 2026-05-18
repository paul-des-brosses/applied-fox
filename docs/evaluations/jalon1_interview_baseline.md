# Évaluation Jalon 1 — Module Interview (baseline)

**Date** : 2026-05-04
**Évaluateur** : Claude Opus 4.7 (LLM-as-judge)
**Fiche évaluée** : `projects/esp32_weather_station.md`
**Protocole** : lecture à froid — le `.md` est lu sans contexte de la conversation qui l'a produit.

---

## Résultat couche 1 — validation structurelle

```
COUCHE 1 : OK
  Composants        : 7
  Critiques         : 5
  Objectifs         : 3
  Interactions      : 5
  Contraintes       : 4 sous-sections
  Phase             : prototype
  Prochain rendu    : 2026-09-15 — soutenance
```

Toutes sections obligatoires présentes, conformes au schéma, parsing Pydantic sans erreur.

---

## Résultat couche 2 — test de transmission (LLM réel : `mistral-nemo:latest` via Ollama)

Le test de transmission a été exécuté **avec un vrai LLM local** (mistral-nemo, qui se substitue au mistral 7B Q4 spécifié dans la config par défaut, non installé sur la machine de test). Réponse brute du LLM lue à froid :

```
1. Station Météo Connectée ESP32
2. prototype
3. ESP32-WROOM-32E, BME280, Panneau solaire 5W 6V, Batterie LiPo 2000 mAh 3.7V,
   Module LoRa SX1276
4. Tenir 6 mois d'autonomie en outdoor sans intervention sur batterie LiPo 2000
   mAh + panneau solaire 5W
5. 2026-09-15
```

| Vérification | Résultat | Détail |
|---|---|---|
| Nom du projet retrouvé | OK | exact |
| Phase retrouvée | OK | "prototype" cité textuellement |
| Composants critiques nommés | OK | les 5 critiques cités dans l'ordre du tableau |
| Premier objectif restitué | OK | citation littérale, sans déformation |
| Date du prochain rendu | OK | 2026-09-15 |

**Score réel : 4/4 vérifications + bonus date précise. Transmission complète sans déduction.**

Ce résultat est plus fort qu'attendu : un 7B/12B Q4 récupère **textuellement** les éléments structurés de la fiche, ce qui valide l'hypothèse centrale du module Interview — le `.md` est *autonome*, n'importe quel agent en aval peut l'utiliser sans avoir vu la conversation qui l'a produit.

---

## Évaluation LLM-as-judge — questions du protocole

### Q1. Représentation du projet

La fiche capture sans ambiguïté :

- **Quoi** : station météo outdoor mesurant T°/humidité/pression/GPS, transmission LoRaWAN.
- **Pour qui / pour quoi** : déploiement autonome 6 mois, pas d'intervention humaine.
- **Comment** : ESP32 central, capteurs I2C/UART, transmission SPI vers SX1276, alimentation solaire+LiPo via MPPT.
- **Avec quelles contraintes mesurables** : 5 mA moyen, <50 µA deep sleep, IP65, < 80€, portée 5 km, précision ±0,5°C/±3%/±1 hPa.
- **Pour quel rendu** : soutenance le 2026-09-15, prototype + 1 mois de données.

Les objectifs actifs sont **quantifiés** — ce qui est exactement le critère discriminant pour le filtre d'alignement téléologique de l'Éclaireur (cf. `DECISIONS.md` et règle "alignement téléologique" du `CLAUDE.md`). Les composants critiques (5 sur 7) sont distingués des accessoires, et chacun porte un statut décisionnel exploitable par les agents en aval.

**Représentation : forte. Pas de zone d'ombre majeure.**

---

### Q2. Divergences et incohérences internes

Vérification engineering des chiffres déclarés :

1. **Budget énergétique** — calcul rapide à partir des contraintes :
   - Cycle de 15 min : ~1 s actif (lecture + transmission), ~899 s deep sleep.
   - Conso active estimée : ~150 mA (ESP32 + LoRa TX).
   - Conso sleep : 50 µA déclaré.
   - Moyenne théorique : ~0,2 mA. Le budget de 5 mA est donc *très large* — bonne marge d'ingénierie.
   - Capacité utile LiPo 2000 mAh à 5 mA moyen : ~16 jours *sans solaire*. Avec panneau 5W et 4-6 h de soleil/jour en moyenne, le bilan est largement excédentaire pour la zone climatique implicite.
   - **Verdict : chiffres internes cohérents, marge réaliste.**

2. **Composants vs interactions vs contraintes non négociables** — trois écarts identifiés :

   a. **Passerelle LoRaWAN absente du tableau Composants.** Pourtant inscrite comme contrainte non négociable ("passerelle LoRaWAN locale obligatoire"). C'est un nœud physique du système qu'un agent de veille devrait pouvoir interroger (modèles Dragino, RAK, ChirpStack…).

   b. **Visualisation absente de la stack.** Le contenu attendu pour la soutenance mentionne explicitement "1 mois de données collectées et **visualisées**", mais aucun outil de Stack software ne porte ce rôle. Soit InfluxDB+Grafana, soit Node-RED, soit script Python custom — non tranché.

   c. **Régulateur MPPT et régulateur 3,3 V** apparaissent dans les *interactions* mais pas dans les *Composants*. Pour un projet en phase prototype, c'est une lacune : le régulateur MPPT (CN3791, BQ24650, etc.) est un point de veille fréquent (alternatives, robustesse outdoor).

3. **Statuts "en évaluation" non rattachés à une décision datée.** Le boîtier IP65 et MicroPython sont marqués "en évaluation" — l'utilisateur devra trancher avant le rendu. Aucune deadline implicite n'est attachée. Pas bloquant pour la veille, mais un agent intelligent devrait potentiellement signaler ces décisions ouvertes en priorité.

---

### Q3. Informations manquantes

**Premier ordre — pourrait bloquer un agent en aval :** *aucune.*

Le pipeline composants → interactions → contraintes est suffisamment complet pour qu'un Éclaireur produise immédiatement des findings exploitables sur ESP32, BME280, SX1276, LiPo 2000 mAh, panneau 5W, et les contraintes énergétiques.

**Second ordre — améliorerait la qualité des suggestions :**

- Passerelle LoRaWAN (modèle, statut, position dans le réseau) — voir Q2.
- Outil de visualisation (Grafana/InfluxDB/script) — voir Q2.
- Régulateur de charge solaire MPPT (modèle, courant max) — voir Q2.
- Régulateur de tension 3,3 V vers ESP32 (LDO ou buck) — pas critique mais cible de veille.
- **Antenne LoRa** : 5 km en zone semi-rurale exige un dipôle ou hélicoïdale 868 MHz adaptée. Non documentée.
- **Format de payload LoRaWAN** : Cayenne LPP ? CBOR ? Custom ? Impacte les findings sur protocoles de sérialisation embarquée.
- **Décision MicroPython vs ESP-IDF** non tranchée — bloque indirectement les findings sur la stack (LMIC C vs port Python, outils de debug, etc.).
- **Stratégie de mise à jour OTA** : 6 mois sans intervention implique du firmware capable de se mettre à jour, ou alors zéro mise à jour pendant 6 mois — non précisé.
- **Politique de gestion d'erreur** : que se passe-t-il si la transmission LoRa échoue 3 fois de suite ? Stockage local, retry, perte ? Non documenté.

---

### Q4. Note globale

| Critère | Score | Commentaire |
|---|---|---|
| Complétude structurelle | 10/10 | toutes sections, schéma respecté, validation Pydantic OK |
| Objectifs actifs quantifiés | 10/10 | 3 objectifs mesurables, idéaux pour filtre d'alignement |
| Composants & interactions | 8/10 | 7 composants typés ; passerelle, MPPT, visualisation manquants |
| Contraintes mesurables | 9/10 | 4 sous-sections, valeurs chiffrées, non-négociables explicites |
| Cohérence interne | 9/10 | budgets énergétiques tiennent, statuts cohérents |
| Autonomie de lecture (test couche 2 réel) | 10/10 | 4/4 vérifications par mistral-nemo |

**Note finale : 8,5 / 10**

Cette note reflète une fiche **opérationnelle dès maintenant** pour le pipeline de veille : pas de lacune bloquante, des objectifs alignables, des composants typés, des contraintes chiffrées. Les 1,5 points soustraits pointent des lacunes corrigibles via le mode `update` (Jalon 2) — typiquement l'ajout de la passerelle LoRaWAN dans Composants et la résolution de la décision MicroPython/ESP-IDF.

---

## Verdict

**Critère de succès Jalon 1 atteint** (seuil roadmap : ≥ 7/10).

Les informations manquantes sont **toutes de second ordre**. Aucune ne bloque le pipeline de veille. La fiche peut servir d'entrée à l'Éclaireur dès le Jalon 3 sans modification préalable.

**Recommandations à intégrer via `applied-fox interview update` (Jalon 2)** :

1. Ajouter la passerelle LoRaWAN au tableau Composants (modèle, statut décisionnel, rôle pipeline).
2. Ajouter le régulateur MPPT et le régulateur 3,3 V au tableau Composants.
3. Ajouter un outil de visualisation à Stack software (ou retirer la mention "visualisées" du contenu attendu).
4. Trancher la décision MicroPython vs ESP-IDF.
5. Documenter la stratégie OTA et la politique d'erreur LoRa (peut aller dans Contraintes / sous-section "Robustesse").

---

## Conclusion Jalon 1

| Livrable | Statut |
|---|---|
| `src/interview/create.py` — questionnaire guidé | Implémenté |
| `src/agents/interviewer.py` — orchestration `run_create` | Implémenté |
| `src/validation/structural.py` — couche 1 | Implémenté |
| `src/validation/transmission.py` — couche 2 | Implémenté |
| `src/validation/human.py` — couche 3 | Implémenté |
| `src/models.py` — `ProjectModel` complet | Implémenté |
| CLI `applied-fox interview create` | Câblé |
| Tests structurels (37 tests, 0 échec) | Passés |
| Couche 2 testée avec un vrai LLM (mistral-nemo) | OK — 4/4 |
| Évaluation baseline Opus 4.7 | Ce fichier |

### Validation transverse — local exclusif

Le module Interview tourne **entièrement en local** : Ollama sur localhost, aucun appel réseau externe lors de l'interview ni du test de transmission. La règle 0 de l'invariant "tout en local possible" est respectée structurellement (codée dans `get_llm("interviewer", config)`).

**Jalon 1 : TERMINÉ.**
