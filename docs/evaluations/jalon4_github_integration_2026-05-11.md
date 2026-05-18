# Évaluation Jalon 4 — Intégration GitHub (3e source)

**Date** : 2026-05-11
**Contexte** : ajout de la source GitHub après Reddit + RSS + prompt durci + queries enrichies.
**LLM** : `mistral:7b-instruct-q4_K_M` (identique runs précédents)

---

## Itération nécessaire — adaptation des queries

**Premier run avec queries Éclaireur brutes** : **1 finding GitHub sur 38 queries**. Constat : GitHub Search fait du AND littéral. Une query comme `"Module LoRa SX1276 alternative stars:>=10 pushed:>=2025-05-12"` exige TOUS les termes simultanément dans le repo → quasi aucun match.

**Fix** : ajout d'une fonction `_simplify_query_for_github(query)` dans `src/sources/github.py` :
- Retire les suffixes Reddit-style (`alternative`, `review`, `issue`, `vs`, `comparison`, `tips`, etc.)
- Tronque à 3 mots max (seuil empirique : 4 mots → quasi 0 résultats, 3 mots → 1-5 résultats par query)

**Résultat après fix** : **46 raws GitHub sur 40 queries** (×46). Validation que le sweet spot empirique de 3 mots est correct.

---

## Résultats quantitatifs

| Métrique | Reddit + RSS + queries enrichies | + GitHub | Δ |
|---|---|---|---|
| Sources actives | 2 | 3 | +1 |
| Raws Reddit | 148 | 148 | = |
| Raws RSS | 109 | 109 | = |
| Raws GitHub | 0 | **46** | +46 |
| Total raws | 257 | **303** | +18 % |
| Filter ratio | 48.6 % | 48.2 % | stable |
| Findings structurés | 132 | **153** | +16 % |
| Structuration réussie | 100 % | 97.5 % | légère baisse |

Distribution des angles après ajout GitHub :
```
energy: 114 (+16)
perf: 28 (-2)
obsolescence: 5 (+5)  ← retour de quelques hallucinations
price: 5 (+4)
supply: 1 (-2)
```

---

## Qualité GitHub — problème détecté

Sur 25 findings GitHub structurés, **environ 40 % contiennent des hallucinations factuelles**. Exemples concrets observés :

| Repo | Description LLM générée | Diagnostic |
|---|---|---|
| `Lens-PCB` | *"ESP32-WROOM-32E has energy consumption of 550 mA in sleep mode and 640 mA when fully awake"* | Inventé — chiffres faux, 550 mA en sleep est techniquement impossible pour un ESP32 |
| `unitemp-flipperzero` | *"designed to operate with a LiPo battery and solar panel, providing 6 months of autonomous operation"* | Plaquage de la description projet sur un repo Flipper Zero qui n'en parle pas |
| `BME280` (repo) | *"Un prix de vente de 5,99€ par unité pour la BME280 avec une garantie de deux ans"* | 100 % inventé |
| `SparkFun_BME280_Arduino_Library` | *"can maintain an autonomous operation for up to 6 months..."* | Plaquage projet sur une lib qui ne fait que driver I2C |

**Diagnostic technique** : les findings GitHub ont un body très court (description repo : 0-100 caractères vs 1000-2000 pour Reddit). Le LLM 7B, à court de matière première, **comble le vide en plaquant le contexte projet** (que le prompt système fournit) sur le finding, comme s'il s'agissait d'information réelle du repo.

C'est une régression de la qualité prompt-durci sur ce cas précis. Le prompt durci dit *"si le post est trop pauvre, écris 'Aucun apport pertinent'"* — mais le LLM 7B n'applique pas cette règle quand le titre du repo lui suggère un lien plausible.

---

## Findings GitHub légitimes

Heureusement, beaucoup de findings GitHub sont factuels et utiles :

> *"`ESP-360-REMOTE` : An all-in-one remote based on the ESP32-WROOM-32E"* — description correcte du repo, info utilisable.

> *"`MasteringMCU2` : platform pour transmettre des mesures via LoRaWAN"* — lien projet valide.

> *"`unitemp-flipperzero` : application qui interroge des capteurs"* (sans le placage "6 mois autonomie") — repo réel intéressant.

Le **signal underlying est là** (libs, drivers, projets de référence), mais le filtre LLM laisse passer des hallucinations confiantes qui nécessiteront un cross-check humain ou un agent Juge.

---

## Verdict honnête

### Ce que GitHub apporte
- **+46 raws cumulés** (Reddit + RSS + GitHub) qui ne sont pas redondants avec les deux autres sources
- **Découverte de libs concrètes** : SparkFun BME280 Arduino Library, mpy-lib, awesome-embedded-software (collections)
- **Couverture de l'écosystème open-source** qu'aucune autre source ne donne

### Le coût
- Le ratio "findings fiables / hallucinations" baisse sur GitHub spécifiquement (~60 % fiables, ~40 % à vérifier manuellement)
- La validation Jalon 4 sur la sécurité (clé API non leakée) reste à faire systématiquement
- Setup utilisateur : token GitHub à générer (5 min mais non triviale pour un newbie)

### Le compromis MVP
**GitHub est conservé en source active**, mais la qualité de structuration LLM sur les findings courts est un goulot connu. C'est précisément le type de problème que l'**Intégrateur (Jalon 5)** devrait corriger via cross-référencement :
- Un finding GitHub avec body court qui affirme "550 mA en sleep" → l'Intégrateur peut le confronter à 12 autres findings ESP32 qui parlent de µA en sleep → flag "incohérence factuelle" → finding rejeté ou marqué incertain.

Le pipeline n'est PAS prêt sans Intégrateur. C'est le bon moment pour passer à Jalon 5.

---

## Décisions actées

1. ✅ **GitHub source activée par défaut** (config.yaml : `sources.github.enabled: true`)
2. ✅ **`_simplify_query_for_github()` conservé** comme contournement empirique des limites GitHub Search
3. ⚠️ **Limitation connue documentée** : hallucinations LLM sur findings GitHub à body court
4. ⏭️ **Jalon 5 (Intégrateur) devient critique** pour cross-référencer et détecter les hallucinations
5. ⏭️ **Optionnel V2** : fetcher le README de chaque repo pour enrichir le body avant structuration LLM (coût : ×N appels API GitHub, mais résout le problème)
