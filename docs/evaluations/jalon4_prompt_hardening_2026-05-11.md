# Évaluation Jalon 4 — Durcissement du prompt Éclaireur

**Date** : 2026-05-11
**Contexte** : suite à l'éval `jalon4_rss_reddit_eval_2026-05-11.md` qui révélait des hallucinations LLM significatives.
**Hypothèse testée** : durcir le prompt système (anti-hallucination, ancrage factuel, autorisation explicite de l'incertitude) améliore la qualité sans changer de modèle.
**LLM utilisé** : `mistral:7b-instruct-q4_K_M` (identique baseline)
**Sources** : identiques (Reddit + RSS, mêmes flux)

---

## Pourquoi pas qwen3.5:9b

Tentative initiale d'override Éclaireur sur `qwen3.5:9b`. Diagnostic au lancement (`ollama ps`) :

```
qwen3.5:9b    8.9 GB    28%/72% CPU/GPU    context 4096
```

Le modèle dépasse les 8 Go VRAM de la RTX 3070 même avec `num_ctx` réduit à 4096. Conséquence : 28 % du modèle s'exécute sur CPU, ralentissement 5-10×. **Pipeline tournant en 20+ minutes au lieu de 6**.

**Décision** : qwen3.5:9b est inadapté à cette machine. Pour profile `small` (8 Go VRAM), rester sur des modèles 7B. Le test d'amélioration LLM reportera quand on aura accès à une machine avec ≥ 12 Go VRAM.

---

## Modifications apportées au prompt

Remplacement du prompt `_STRUCTURE_PROMPT` dans `src/agents/eclaireur.py` :

1. **Section "RÈGLES STRICTES"** explicite avec 4 règles numérotées :
   - **Ancrage factuel** : "Ta description s'appuie UNIQUEMENT sur ce que dit CE post. N'invente PAS de faits techniques [...]"
   - **Incertitude autorisée** : "Si le post est trop pauvre [...], écris 'Aucun apport pertinent.' C'est PRÉFÉRABLE à inventer."
   - **Définitions inline des angles** avec critère explicite anti-hallucination sur "obsolescence" : "UNIQUEMENT si le post le mentionne explicitement"
   - **Format strict** : JSON exact, pas de markdown, pas de paraphrase du titre

2. **Exemples positifs ET négatifs** : un mauvais exemple explicite ("Ne PAS écrire 'BME280 may no longer be supported' si le post n'en parle pas. C'est une hallucination.")

3. **Adaptation multi-source** : remplacement de "post Reddit" par "post brut", introduction de `source_label` et `source_type` pour distinguer community (Reddit) vs news (RSS) dans le prompt.

---

## Résultats quantitatifs

| Métrique | Baseline ancien prompt | Prompt durci | Δ |
|---|---|---|---|
| Findings bruts | 176 | 176 | = |
| Filter ratio | 66.5 % | 66.5 % | = |
| Findings kept (post-filtre) | 59 | 59 | = |
| **Structuration réussie** | 53 (90 %) | **59 (100 %)** | **+10 pts** |
| Échecs structuration | 6 | **0** | -6 |
| Distribution angles | obsolescence:18, energy:29, perf:2, regulation:2, supply:1, price:1 | energy:42, perf:11, supply:3, obsolescence:2, price:1 | voir ↓ |
| **Angle obsolescence (proxy hallucinations EOL)** | **18 (34 %)** | **2 (3 %)** | **-31 pts** |

**Lecture** :
- Le prompt durci a **complètement éliminé** les échecs de parsing JSON (le LLM produit du JSON valide à 100 %).
- L'effondrement de l'angle `obsolescence` (de 34 % à 3 %) est le signal le plus net. La baseline classait abusivement des findings en EOL parce que l'angle existe — le prompt durci avec sa définition "UNIQUEMENT si le post le mentionne explicitement" a coupé les hallucinations.

---

## Résultats qualitatifs sur les 3 axes critiques

### Axe 1 — LoRa SX1276 → SX1262

**Baseline** : 2 findings, descriptions confuses.
> *"L'utilisation du SX1276 pour la communication LoRa n'est pas compatible avec la station météo connectée ESP32."* (faux)
> *"Ce module LoRa SX1276 est obsolète et ne peut plus être utilisé dans les projets."* (faux)

**Prompt durci** : 1 finding, description factuelle.
> *"Design of a LoRa Sensor Node with Ultra-Low Power consumption for extended battery life, using the STM32U073CCU6 MCU and Ebyte E22-900M22S LoRa Module."*

**Verdict** : description maintenant correcte. L'enjeu stratégique (l'upgrade SX1276→SX1262) reste à articuler en aval (Intégrateur Jalon 5), mais le LLM ne ment plus.

### Axe 2 — BME280 issues

**Baseline** : 6 findings, dont une hallucination ("may no longer be supported by the manufacturer"), descriptions creuses.

**Prompt durci** : 3 findings, dont **une pépite** :
> *"BME280 is not recommended for ambient temperature readings but SHT41 and SHT45 are the most popular recommendations."*

C'est exactement l'insight que ma recherche externe indépendante avait identifié (alternatives Sensirion SHT3x/SHT4x avec membrane PTFE). Le LLM 7B est capable de remonter cette information **quand le prompt l'autorise à dire ce qu'il voit dans le post sans déformer**.

**Verdict** : **gain majeur**. Le LLM a accès aux bonnes infos, le prompt durci les laisse passer.

### Axe 3 — ESP32 deep sleep

**Baseline** : 0 findings.
**Prompt durci** : 0 findings.

**Verdict** : **inchangé**. Confirmation que le problème n'est pas le LLM mais le **générateur de queries**. Les requêtes générées sont du type `{composant} alternative/review/issue/vs` — un pattern technique transverse comme "ESP32 deep sleep optimization" n'est jamais cherché.

**Action requise** : enrichir `_generate_queries()` pour inclure aussi des queries par objectif/contrainte projet (à faire en Jalon 4 ou en début Jalon 5).

---

## Verdict global

| Dimension | Baseline | Prompt durci | Évolution |
|---|---|---|---|
| Volume de signal | 8/10 | 8/10 | = |
| Filtrage déterministe | 8/10 | 8/10 | = |
| Qualité structuration LLM | 4/10 | **7/10** | **+3** |
| Pertinence stratégique | 5/10 | 6/10 | +1 |
| Découverte de nouveauté | 4/10 | 5/10 | +1 |

**Conclusion** : le prompt durci est un succès net, à coût zéro (un seul fichier modifié, aucun changement de modèle, aucun impact perf). À **garder en production**.

Limites restantes confirmées :
- L'angle `obsolescence` est sous-utilisé maintenant — possible faux négatif si un vrai EOL existe dans un post. À mesurer dans le temps.
- Le générateur de queries reste composant-centrique → fix nécessaire pour découvrir les patterns techniques transverses.
- L'absence de cross-référencement reste — c'est le rôle de l'Intégrateur (Jalon 5).

---

## Décisions actées

1. ✅ **Conserver le prompt durci** comme nouveau baseline Éclaireur
2. ✅ **Abandonner qwen3.5:9b** sur profile small (8 Go VRAM insuffisants). Tester ultérieurement sur machine ≥ 12 Go VRAM
3. ⏭️ **Enrichir `_generate_queries()`** avec des patterns par objectif/contrainte — à planifier en fin Jalon 4 ou début Jalon 5
4. ⏭️ **Reporter le test multi-LLM** post-MVP, quand l'archi est stable
