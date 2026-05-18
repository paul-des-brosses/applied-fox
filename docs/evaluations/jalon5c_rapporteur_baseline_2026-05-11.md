# Évaluation Jalon 5c — Baseline du Rapporteur (pipeline complet)

**Date** : 2026-05-11
**Contexte** : intégration du Rapporteur en fin de pipeline. Premier run end-to-end avec les **4 agents** (Éclaireur → Intégrateur → Juge → Rapporteur). Architecture cible MVP atteinte.
**LLM Rapporteur** : `mistral:7b-instruct-q4_K_M` (1 seul appel LLM pour la synthèse, le reste est déterministe)

---

## Architecture validée

```
applied-fox run --project ma_fiche.md
       ↓
  ┌────────────────────────────────────────────────┐
  │  Éclaireur     → 157 findings structurés     │
  │       ↓                                        │
  │  Intégrateur   → 157 verdicts d'intégration    │
  │       ↓                                        │
  │  [branchement conditionnel : si 0 intégrable] │
  │       ↓                                        │
  │  Juge          → 105 verdicts de pertinence    │
  │       ↓                                        │
  │  Rapporteur    → 10 suggestions + rapport HTML │
  └────────────────────────────────────────────────┘
       ↓
  runs/[timestamp]_[projet]/
    01_eclaireur_findings.json
    01_eclaireur_sources.json
    02_integrateur_verdicts.json
    02_integrateur_reasoning.md
    03_juge_verdicts.json
    03_juge_reasoning.md
    04_rapport.md
    04_rapport.html             ← OUVRABLE DANS LE NAVIGATEUR
    04_validated_suggestions.json
```

---

## Stratégie d'implémentation : déterministe majoritairement

Le Rapporteur fait **1 seul appel LLM** dans tout le pipeline (la "Synthèse en une ligne" en tête de rapport). Tout le reste est du templating Python depuis les modèles Pydantic.

**Pourquoi ce choix** :
- Le format du rapport est strict (cf. `docs/ARCHITECTURE.md`)
- Le LLM 7B produit des sections au ton variable d'un appel à l'autre → rapport incohérent
- Les champs sont déjà tous présents dans les `Finding` + `IntegrationVerdict` + `JudgeVerdict` produits en amont
- Conséquence : rapport reproductible, auditable, robuste

**Déduplication thématique** : groupage déterministe par `(component_concerned, angle)`. Sur 36 findings high+medium relevance / now timing, on retient un seul représentant par thème → **10 suggestions distinctes** affichées en détail. Les autres findings du groupe sont listés en "Sources additionnelles" sous chaque item.

---

## Résultats quantitatifs

| Étape | Compte | Δ vs étape précédente |
|---|---|---|
| Findings bruts (4 sources) | 303 | — |
| Findings retenus après filtre déterministe | 157 | -48 % |
| Findings structurés (Éclaireur) | 157 | 100 % succès |
| Verdicts intégration (Intégrateur) | 157 | 100 % succès |
| dont intégrables | 105 | 67 % |
| Verdicts pertinence (Juge) | 105 | 100 % succès |
| Findings prioritaires (high/medium · now) | 36 | 34 % des jugés |
| **Suggestions finales (Rapporteur)** | **10** | **-72 % via dédup thématique** |

**Le pipeline complet réduit donc 303 raws → 10 suggestions actionnables en une exécution.** C'est le bon ordre de grandeur pour un dashboard exploitable.

---

## Qualité qualitative

### Format respecté

Les 5 sections attendues sont présentes :
- ✅ Synthèse en une ligne
- ✅ À considérer maintenant (avec format détaillé Angle/Source/Ce qui change/Impact/Recommandation)
- ✅ À noter pour plus tard (format condensé)
- ✅ Rejetés (avec raison du Juge ou de l'Intégrateur)
- ✅ Sources consultées (compte par source_type)
- ✅ Métadonnées du run

### HTML autonome (42 Ko)

Le fichier `04_rapport.html` est un document autonome avec CSS inline, ouvrable dans n'importe quel navigateur sans dépendance externe. Pour un portfolio, c'est un livrable visuel immédiat.

### ValidatedSuggestions exploitables

Les 10 suggestions structurées contiennent :
- `title`, `changes_summary`, `components_affected` — pour l'affichage TUI Jalon 6
- `integration_notes`, `open_questions`, `interactions_changes` — pour l'Interviewer en mode `integrate`

Format Pydantic validé, prêt pour la boucle de validation utilisateur (Jalon 6).

### Synthèse en une ligne

Exemple produit :
> *"ESP32-WROOM-32E + BME280 pour une autonomie prolongée à 6 mois dans un environnement."*

Phrase coupée à la fin (LLM 7B qui tronque). Le fallback déterministe se déclenche en cas d'échec, mais ici le LLM a produit une sortie acceptable même si imparfaite. À améliorer avec un meilleur LLM post-MVP.

---

## Hallucinations qui persistent

Les défauts hérités de l'Éclaireur passent à travers les filtres Intégrateur et Juge :

### Cas typiques

> *"Diptyx E-reader : Intégration de la batterie LiPo 2000 mAh améliore l'autonomie du Diptyx E-reader en plus de 6 mois"*

Item présent en première place du rapport. Or, le Diptyx E-reader **est** un projet, et "intégrer une batterie LiPo dans l'e-reader" n'a aucun sens pour le projet station météo qui est en train de la veiller. C'est l'inversion classique : le rapport projet sur le finding au lieu de l'inverse.

> *"Migration ESP8266→ESP32 augmente l'autonomie batterie de ~75%"*

Hallucination : le projet utilise **déjà** un ESP32. Migrer ESP8266→ESP32 ne s'applique pas. Mais la phrase factuelle "+75% d'autonomie" est correcte si on substitue SX1276→SX1262 (qui est l'insight réel).

### Diagnostic

Le LLM 7B n'a pas la capacité de raisonner sur "ce composant est DÉJÀ dans le projet". Tous les agents voient seulement la fiche projet et le finding, sans logique de "comparaison à l'existant". Le filet déterministe pourrait être ajouté en V2 :
- *si `finding.component_concerned in [c.nom for c in project.composants]` ET le verdict propose une "migration vers" ce même composant → flag incohérent*

À noter dans le backlog.

---

## Pépites confirmées dans le rapport final

Malgré les hallucinations, plusieurs vraies suggestions actionnables émergent :

1. **wulpus** (lib pulp-bio sur GitHub) avec consommation chiffrée 22 mW — finding factuel, utile.
2. **Migration SX1276 → SX1262** (gain autonomie ~75 %) — l'insight stratégique majeur identifié par ma recherche externe indépendante.
3. **Solar charging avec MPPT** sur ESP32 — référence concrète pertinente.

---

## Verdict Jalon 5c

### Ce qui marche
1. ✅ **Pipeline 4 agents end-to-end fonctionnel** — architecture MVP cible atteinte
2. ✅ **Format de rapport conforme** à `docs/ARCHITECTURE.md`
3. ✅ **HTML autonome 42 Ko** ouvrable dans le navigateur
4. ✅ **Déduplication thématique** réduit 36 → 10 (gain ×3.6)
5. ✅ **10 ValidatedSuggestions structurées** prêtes pour Jalon 6
6. ✅ **Stratégie déterministe** : 1 seul appel LLM Rapporteur, rapport reproductible
7. ✅ **Branchement conditionnel LangGraph** valide (skip Juge si pas d'intégrable, mais passe quand même au Rapporteur)

### Limites résiduelles
1. **Hallucinations héritées** des agents amont passent dans le rapport final (Diptyx E-reader, "migration ESP8266→ESP32")
2. **Synthèse parfois tronquée** par le LLM 7B
3. **`component_concerned == "?"`** sur certaines suggestions (Éclaireur n'a pas inféré le composant)
4. **Pas de détection "composant déjà dans le projet"** — proposer un fix V2 backlog

### Performance
Run complet 4 agents : ~15-20 min sur la fiche ESP32. Le Rapporteur ajoute seulement ~30s (1 appel LLM + templating). Le coût reste concentré sur Éclaireur + Intégrateur + Juge.

---

## Décisions actées

1. ✅ **Pipeline MVP Jalon 5 complet** — les 4 agents tournent ensemble proprement
2. ✅ **Stratégie déterministe Rapporteur conservée** — rapport reproductible et auditable
3. ⏭️ **Jalon 6 — Boucle validation utilisateur** : TUI Rich qui ouvre le HTML, demande validation, passe les `ValidatedSuggestion` à l'Interviewer mode `integrate`
4. ⏭️ **V2 backlog** : filet déterministe "composant déjà dans le projet → pas de proposition de migration vers ce même composant"
5. ⏭️ **V2 backlog** : amélioration synthèse LLM (modèle plus fort, prompt avec exemple long)
