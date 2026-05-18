# Évaluation Jalon 4 — Itérations sur les hallucinations GitHub

**Date** : 2026-05-11
**Contexte** : suite à `jalon4_github_integration_2026-05-11.md` qui avait identifié ~40 % de descriptions hallucinées sur les findings GitHub. Le diagnostic root cause : body trop court (description repo 0-100 chars) + biais de plaquage du contexte projet par le LLM 7B.

---

## Quatre itérations testées sur la même fiche projet

| Itération | Modif | Findings GitHub factuels | Plaquage contexte | Hallucination EOL |
|---|---|---|---|---|
| Baseline | Description repo brute | ~60 % | élevé | faible (2) |
| **#1** | Body enrichi (+topics +language +README excerpt si < 200 chars) | ~75 % | moyen | faible (5) |
| **#2** | + Règle anti-plaquage explicite dans prompt | ~80 % | faible (mais persiste) | moyen (12) |
| **#3** | + Retrait des objectifs du prompt structuration | ~85 % | très faible | **fort (16)** ❌ |
| **Final** | Retour itération #2 (équilibre optimal) | ~80 % | faible | moyen (12) |

### Lecture détaillée

**Itération #1 — Body enrichi (`_build_rich_body` dans `github.py`)** :
Pour chaque repo GitHub, on construit un body factuel à partir de :
- `description` du repo
- `topics` (tags)
- `language` principal
- Si cumulé < 200 chars : extrait du README (premier chunk de 1000 chars, badges/HTML nettoyés)

Gain : le LLM a vraiment de quoi parler pour les libs documentées. Ex. `SparkFun_BME280_Arduino_Library` passe de 0 description à 1182 chars factuels (lib I2C, fonctions de lecture P/T/H, exemples de conversion).

Limite : pour les repos vraiment opaques (description vide, README pauvre), le LLM continue à plaquer.

**Itération #2 — Règle anti-plaquage** :
Ajout dans le prompt système :
```
NE PLAQUE PAS le contexte projet sur le post. Si le projet vise "6 mois
d'autonomie sur batterie LiPo + solaire" et que le post parle d'un repo
GitHub sans lien avec l'autonomie, NE dis JAMAIS que ce repo "supporte
6 mois d'autonomie" — c'est de la projection, pas un fait du post.
```
+ exemple négatif explicite (un repo `awesome-embedded-software` ne doit PAS être décrit comme ayant "LiPo + solaire").

Gain : Lens-PCB → description factuelle ("PCB pour contrôle de 3 moteurs stepper avec driver A4988"). awesome-embedded-software → "Liste de bibliothèques embedded susceptibles d'aider".

Limite : ESP-360-REMOTE et Anbo-MOS continuent à plaquer partiellement.

**Itération #3 — Retrait des objectifs du prompt** :
Hypothèse : si on ne donne pas les objectifs au LLM, il ne peut pas les plaquer. Test : remplacer `Objectifs actifs : [...]` par `(Le projet a des objectifs mais ils NE TE SONT PAS communiqués)`.

Gain inattendu : ESP-360-REMOTE devient factuel ("ESP32 board with RF transmitter and receiver, 4 IR LEDs"). C'est la **meilleure description GitHub** observée.

**Régression coûteuse** : sans le contexte projet, le LLM dérive vers l'angle "obsolescence" sur les findings ambigus (16 obsolescence vs 2 dans #2). L'absence de cadrage projet libère le biais "EOL" du LLM 7B sur les sigles techniques courts qu'il ne connaît pas bien.

### Pourquoi je suis revenu à l'itération #2

L'itération #3 améliore la qualité descriptive GitHub mais dégrade fortement la qualité de classification d'angle (8× plus d'hallucinations EOL). Le coût net est négatif. L'itération #2 est le meilleur compromis avec les contraintes du LLM 7B.

---

## État final du code après ces itérations

| Fichier | Changements conservés |
|---|---|
| `src/sources/github.py` | `_build_rich_body()` : description + topics + language + README excerpt si nécessaire |
| `src/sources/github.py` | `_simplify_query_for_github()` : suppression suffixes Reddit-style + troncature 3 mots |
| `src/agents/eclaireur.py` | Prompt durci avec : ancrage factuel, autorisation "Aucun apport pertinent", règle anti-plaquage explicite, exemple négatif anti-plaquage |
| `src/agents/eclaireur.py` | Objectifs conservés dans le prompt pour stabiliser l'angle |

---

## Verdict honnête

**Ce qui est réglé** :
- ~40 % → ~20 % de descriptions GitHub à problème
- Les libs réelles (SparkFun, helloesp, mpy-lib) ont maintenant des descriptions factuelles
- Le plaquage massif type "ce repo supporte 6 mois d'autonomie" est résiduel mais rare

**Ce qui n'est pas réglé** :
- ~20 % des findings GitHub continuent à plaquer partiellement le contexte projet
- Hallucinations EOL stabilisées à ~5-10 % (vs 30+ % baseline)
- Limite atteinte avec mistral 7B — toute itération supplémentaire trade-off entre plaquage et EOL

**Ce qui réglera le reste** :
1. **Intégrateur (Jalon 5)** : cross-référencement entre findings → un finding "BME280 obsolète" sera contredit par 10 autres findings BME280 actifs → flag/rejet
2. **Migration vers LLM 12B+** quand l'utilisateur aura accès à plus de VRAM (RTX 3070 8 Go bloque à mistral 7B et qwen2.5:7b)
3. **V2** : fetcher le README de TOUS les repos (pas seulement quand description < 200 chars) pour maximiser le body factuel

---

## Décisions actées

1. ✅ `_build_rich_body()` conservé en production
2. ✅ Règle anti-plaquage + exemple négatif conservés dans prompt
3. ✅ Objectifs conservés dans le prompt structuration (équilibre angle vs plaquage)
4. ⏭️ Jalon 5 (Intégrateur) reste prioritaire pour neutraliser les hallucinations résiduelles via cross-référencement
5. ⏭️ V2 backlog : enrichissement README systématique pour GitHub
