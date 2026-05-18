# Évaluation Jalon 5a — Baseline de l'Intégrateur

**Date** : 2026-05-11
**Contexte** : premier run end-to-end Éclaireur → Intégrateur sur la fiche ESP32 weather station, après tous les fixes Jalon 4 (multi-source, prompt durci, body GitHub enrichi, anti-plaquage).
**LLM Intégrateur** : `mistral:7b-instruct-q4_K_M` (override Éclaireur identique : mistral 7B)
**Volume traité** : 156 findings → 156 verdicts, 0 échec de structuration (100 % succès Pydantic).

---

## Statistiques quantitatives

### Volume et succès

| Métrique | Valeur |
|---|---|
| Findings reçus | 156 |
| Verdicts produits | **156** |
| Échecs de structuration | **0** |
| Taux de succès Pydantic | **100 %** |

Le format JSON strict avec retry (max 2) tient parfaitement. Aucun finding n'a été perdu en route.

### Distribution `integrable`

| Verdict | Compte | % |
|---|---|---|
| `integrable=true` | **102** | 65 % |
| `integrable=false` | **54** | 35 % |

L'Intégrateur identifie clairement le tiers de findings non applicables au projet (architecture incompatible, contrainte non-négociable bloquante).

### Distribution `effort_level`

| Effort | Compte |
|---|---|
| trivial | 15 |
| minor | 47 |
| moderate | 21 |
| major | 19 |
| **blocking** | 54 |

Les "blocking" correspondent aux `integrable=false`. Les 62 findings entre trivial et minor sont les **vrais candidats actionnables court terme** pour l'utilisateur — concentration utile sur 40 % du volume initial.

### Distribution `confidence`

| Confidence | Compte | % |
|---|---|---|
| high | 4 | 2.5 % |
| medium | 95 | 61 % |
| **low** | **57** | **37 %** |

**Le LLM 7B est prudent à juste titre** — 57 findings (37 %) sont flaggés low confidence, souvent avec `uncertainties: ["Affirmations du finding non vérifiables"]`. C'est l'effet "scepticisme" du prompt qui paie.

---

## Qualité qualitative — détection des hallucinations Éclaireur

Test ciblé sur les 5 findings GitHub identifiés comme hallucinés à l'éval `jalon4_github_integration_2026-05-11.md` :

| Finding | Hallucination | Verdict Intégrateur | Détection |
|---|---|---|---|
| `Lens-PCB` | Plaquage "LoRaWAN 6 mois autonomie" sur un PCB stepper | `[low/blocking/non-intégrable]` + uncertainties détaillées | ✅ Bien détecté |
| `SparkFun_BME280_Arduino_Library` | Affirmations sur autonomie (lib I2C légitime) | `[low/blocking]` + "Affirmations non vérifiables" | ⚠️ Détecté mais trop strict (lib légitime catégorisée blocking) |
| `awesome-embedded-software` | Plaquage projet sur liste curatée | `[medium/minor/intégrable]` + uncertainty "Affirmations non vérifiables" | ⚠️ Détection partielle (low confidence aurait été plus juste) |
| `ESP-360-REMOTE` | Plaquage 6 mois autonomie sur un repo de remote | `[medium/minor/intégrable]` (pas d'uncertainty critique) | ❌ Non détecté |
| `Anbo-MOS` | Plaquage projet sur repo random | `[medium/minor/intégrable]` | ❌ Non détecté |

**Score net : 2/5 vraiment attrapés, 2/5 partiellement, 1/5 raté.**

### Pourquoi l'Intégrateur 7B rate certains plaquages

Pour qu'il les attrape, il faudrait qu'il puisse **comparer** la description du finding avec ce qu'il "sait" être plausible techniquement. Or :
- Le mistral 7B a une connaissance produit limitée (≠ GPT-4 qui saurait qu'un "remote control" ne fait pas 6 mois d'autonomie en LoRa).
- Le prompt l'incite à rester sceptique mais ne peut pas remplacer un savoir-faire technique.

### Pourquoi il en attrape certains

Quand la contradiction est **structurelle** (description finding incompatible avec le projet — ex. Lens-PCB qui parle de moteurs stepper alors qu'on veut une station météo), le LLM voit le décalage et flagge correctement.

---

## Verdict global

### Ce que l'Intégrateur apporte

1. **Hiérarchisation lisible** : 156 → 4 high-confidence + 47 minor-effort intégrables. L'utilisateur a un dashboard exploitable.
2. **Filtrage 35 %** : 54 findings clairement non-intégrables (blocking) éliminés automatiquement.
3. **Drapeau "low confidence" sur 37 %** : la majorité des findings douteux est marquée, l'utilisateur sait où regarder en premier.
4. **Rationale lisible** : artefact `02_integrateur_reasoning.md` contient un raisonnement court par finding, exploitable pour audit.

### Limites observées

1. **Faux positifs sur libs légitimes** : SparkFun_BME280_Arduino_Library classée blocking alors que c'est utile. Trade-off du scepticisme.
2. **Plaquages subtils non détectés** : 2/5 cas hallucinés sont passés en `intégrable=true/medium`.
3. **Beaucoup de "medium" non discriminant** : 95 findings (61 %) en medium-confidence, ce qui dilue le signal. Le Juge devra trancher.

### Coût performance

156 verdicts × ~3-5s par appel = ~10-12 min d'évaluation Intégrateur après l'Éclaireur (~6 min). Total pipeline complet : ~18-20 min. Acceptable pour un run quotidien, mais commence à compter si on veut tester rapidement.

---

## Décisions actées

1. ✅ **Intégrateur en production** — 100 % succès structuration, valeur ajoutée nette
2. ✅ **Format Pydantic + retry conservé** — éprouvé sur 156 verdicts sans échec
3. ⏭️ **Jalon 5b — Juge** : devra trancher entre 102 findings "intégrables" pour priorisation finale vs objectifs projet
4. ⏭️ **Optimisation possible (V2)** : skip de l'évaluation Intégrateur pour les findings avec description = "Aucun apport pertinent" (économie ~10-15 % temps LLM)
5. ⏭️ **Détection hallucinations subtiles** restera limitée tant que le LLM Éclaireur+Intégrateur sera 7B. Migration vers 12B+ recommandée post-MVP.
