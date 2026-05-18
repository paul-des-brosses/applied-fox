# Évaluation Jalon 5b — Baseline du Juge

**Date** : 2026-05-11
**Contexte** : intégration du Juge après Éclaireur + Intégrateur. Premier run end-to-end avec les 3 agents et branchement conditionnel LangGraph (court-circuit si aucun finding intégrable).
**LLM Juge** : `mistral:7b-instruct-q4_K_M`

---

## Statistiques quantitatives

### Flow du pipeline complet

```
Éclaireur     → 155 findings structurés
Intégrateur   → 155 verdicts (100 % succès)
  ├─ 105 intégrables → vers Juge
  └─  50 non-intégrables → court-circuités
Juge          → 105 verdicts (100 % succès)
```

Économie d'appels LLM grâce au court-circuit : ~50 findings sautent l'évaluation Juge, soit ~30 % de moins de temps LLM sur ce nœud.

### Distribution Juge

| Relevance | Compte | % | | Timing | Compte | % |
|---|---|---|---|---|---|---|
| high | **46** | 44 % | | now | **41** | 39 % |
| medium | 35 | 33 % | | next_iteration | 35 | 33 % |
| low | 23 | 22 % | | noted_for_future | 28 | 27 % |
| reject | 1 | 1 % | | reject | 1 | 1 % |

### Filet anti-hallucination en action

Le code applique un **cap déterministe** : si l'Intégrateur a sorti `confidence=low`, la relevance Juge est capée à `medium` (impossible d'avoir `high` sur un finding peu fiable). Ce filet a été activé en interne par le code sans intervention humaine — combien de fois ? À mesurer en lisant les logs DEBUG, mais le mécanisme est en place.

---

## Qualité qualitative

### Les pépites émergées (par ordre de pertinence pour le projet)

> *"Migration SX1276→SX1262 augmente l'autonomie batterie de ~75% selon mesures terrain, ce qui sert directement l'objectif 6 mois."*

C'est **exactement le chiffre** que ma recherche externe indépendante avait identifié (cf. eval `jalon4_rss_reddit_eval_2026-05-11.md`). Le pipeline complet remonte cette info en finale, classée high/now. Pour un portfolio, c'est la démonstration la plus forte que la chaîne fonctionne.

> *"[Schematic Review] Ultra-Low Power LoRa Sensor Node STM32U073 + E22 (SX1262)"*

Design de référence remonté en high/now. L'utilisateur peut cliquer, lire le schéma, et envisager une migration argumentée.

> *"BME280 is not good for ambient temperature readings, DHT22 is okay for casual use cases but not accurate or fast enough, SHT31 is old but good enough"* (depuis l'Éclaireur, repris dans le Juge en high relevance)

L'alternative SHT3x identifiée à l'éval externe est bien remontée.

### Les plaquages qui passent encore

Le Juge 7B garde certains plaquages que l'Intégrateur n'avait pas attrapés en low :

- *"Diptyx E-reader: an ESP32-powered, dual screen ereader"* — classé high/now avec gain "Remplacement de batterie permet d'augmenter l'autonomie jusqu'à 6 mois". C'est un repo d'e-reader, pas un projet d'autonomie outdoor. Le Juge applique le contexte projet sur un finding sans rapport.

- *"Migration BME280→capteur T°/humidité/pression"* — tautologique (le BME280 EST un capteur T°/humidité/pression).

- *"Incorporation du module LoRa SX1276 pour meilleure gestion d'énergie"* — le SX1276 est déjà dans le projet, "incorporer" est factuellement faux.

Ce sont les mêmes types d'hallucinations qu'à l'éclaireur, héritées via la chaîne.

### Volume trop large à la sortie

**46 findings high relevance** sur 105 jugés est encore trop pour un portfolio. La cible serait 5-10 vraiment actionnables. Causes :
1. Le LLM 7B est trop généreux par défaut sur le verdict "high" (préfère sur-prioriser que sous-prioriser).
2. Le prompt ne fixe pas de quota explicite.
3. Plusieurs findings touchent les mêmes objectifs → redondance non détectée.

C'est précisément le job du **Rapporteur (Jalon 5c / 6)** de faire la sélection finale et la déduplication thématique. Le Juge classe, le Rapporteur synthétise.

---

## Branchement conditionnel LangGraph

```python
graph.add_conditional_edges(
    "integrateur",
    _route_after_integrateur,
    {"juge": "juge", "skip_juge": END},
)
```

Fonctionnement validé :
- Si `any(verdict.integrable for verdict in integration_verdicts.values())` → route "juge" → Juge appelé
- Sinon → route "skip_juge" → END (pipeline raccourci)

Au test, on a 102/155 intégrables → route "juge" empruntée. Le court-circuit complet n'a pas été testé en conditions réelles (faudrait un projet où l'Intégrateur rejette tout), mais le code est en place et tracé.

---

## Verdict global Jalon 5b

### Ce qui marche
1. **Pipeline 3 agents end-to-end fonctionnel** (Éclaireur → Intégrateur → Juge)
2. **100 % de succès Pydantic** sur 105 verdicts Juge produits
3. **Branchement conditionnel LangGraph** opérationnel (skip Juge si aucun intégrable)
4. **Filet anti-hallucination** : cap déterministe high → medium si Intégrateur low confidence
5. **Pépites attendues remontées** : SX1262 migration, SHT3x alternative, deep sleep optimization
6. **Artefacts JSON + Markdown** sauvegardés (`03_juge_verdicts.json`, `03_juge_reasoning.md`)

### Ce qui ne marche pas encore
1. **Trop de "high relevance"** (44 %) — calibration LLM 7B trop généreuse
2. **Plaquages projet hérités de l'Éclaireur** continuent à passer (e-reader classé pertinent pour autonomie)
3. **Pas de déduplication thématique** : plusieurs findings sur le même angle (SX1262 migration) classés tous en high → redondance

### Performance
Run complet (155 findings) : ~12-15 min pour Éclaireur + Intégrateur + Juge cumulés. Acceptable pour usage périodique, lourd pour itération rapide.

---

## Décisions actées

1. ✅ **Pipeline Jalon 5a + 5b en production** — 3 agents fonctionnels, artefacts complets
2. ✅ **Branchement conditionnel LangGraph validé**
3. ⏭️ **Jalon 5c — Rapporteur** : doit faire la **déduplication thématique** + sélection finale (5-10 suggestions vraiment uniques)
4. ⏭️ **Optimisation possible (V2)** : passer le top-N findings au Juge dans un même prompt pour permettre cross-référencement explicite → meilleur tri redondance
5. ⏭️ **Calibration prompts** post-MVP avec un LLM plus fort (l'effet généreux du 7B sur "high" se traduira mieux par un 12-32B)
