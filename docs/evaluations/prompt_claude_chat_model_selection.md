# Prompt à coller dans Claude.ai pour figer les modèles MVP

> **Mode d'emploi** : ce prompt est conçu pour ouvrir une conversation
> chat Claude.ai avec un modèle récent (Claude Opus 4.x ou Sonnet 4.x).
> Il doit déboucher sur une décision **figée par profile machine**
> (small/medium/large) à inscrire dans `src/llm/__init__.py` et dans
> `~/.applied-fox/config.yaml`.
>
> Avant de coller, remplace `<XX/10>` par le score Opus de l'éval v1.4
> (tu auras le chiffre après le run du Juge en qwen3.5:9b).

---

## Prompt à copier-coller

```
Bonjour. Je suis étudiant M1 ESILV, je construis Applied Fox : un système
multi-agent local de veille technologique pour projets d'ingénierie (cf.
contexte plus bas). J'ai besoin de figer définitivement le choix des
modèles Ollama par profile matériel pour mon MVP. Tu as accès à des
informations plus récentes que mes recherches manuelles. C'est important :
fais une recherche web sur les sorties de modèles open-weight au cours
des 4 dernières semaines avant de répondre, parce que ce domaine bouge
chaque semaine.

═══ CONTEXTE PROJET (rappel rapide) ═══

- 4 agents LLM : Éclaireur (déterministe, plus de LLM), Intégrateur,
  Juge, Rapporteur. Aussi un Interviewer (toujours local, 7B max).
- Architecture hot-swappable : `get_llm(role, config)` retourne un LLM
  configuré, on peut donc avoir un modèle par rôle si pertinent.
- 3 profiles matériel à figer :
    - small  → laptop modeste, 16 Go RAM, GPU intégré OU RTX 3070 8 Go
    - medium → station 32-64 Go RAM, GPU 8-12 Go
    - large  → station 64+ Go RAM, GPU 16+ Go
- Contrainte non négociable : l'Interviewer reste TOUJOURS en local
  7B Q4 (CLAUDE.md règle 3, "tout en local par défaut" + budget RAM).
- Provider : Ollama (donc modèles publiés sur ollama.com/library).

═══ PROBLÈME OBSERVÉ (4 itérations mesurées) ═══

Sur mistral:7b-instruct-q4_K_M partout, sur 3 projets test (greenhouse,
tracker LoRa, BMS DIY), j'ai mesuré :

| Itération | Alignement avec objectifs | Note Opus 4.7 |
|---|---:|---:|
| v1.0 baseline | 0% | 2.5/10 |
| v1.1 prompts durcis + subreddits | 10% | 4/10 |
| v1.2 + filtre déterministe ancrage | 26% | 5.5/10 |
| v1.3 + Éclaireur déterministe (skip LLM struct) | 33% | 5.5-6/10 |
| v1.4 + Juge en qwen3.5:9b | <XX/10> | <XX/10> |

Le maillon faible identifié : l'agent **Juge** (LLM-as-a-Judge sur
"ce post est-il aligné avec un objectif de mon projet ?"). Le 7B Q4
ignore régulièrement les règles d'ancrage textuelles malgré 4 itérations
de prompts.

Cible MVP ROADMAP : ≥ 80% suggestions alignées, 0 non-alignée, note ≥ 6/10.

═══ MA QUESTION ═══

Pour chaque profile (small / medium / large), donne-moi **un mapping
définitif rôle → modèle Ollama**, à inscrire dans le code et la config
de mon MVP. Critères de décision :

1. Disponible sur ollama.com/library (donne le tag exact, ex.
   `qwen3.5:9b-instruct-q4_K_M`).
2. Tient en VRAM/RAM du profile cible sans CPU offload > 30%.
3. Bon pour LLM-as-a-Judge (méta-raisonnement, détection hors-sujet,
   ancrage textuel strict). Phi-4, Qwen3.x, Llama 3.x ou plus récent.
4. Le **Juge** peut avoir un modèle différent / plus gros que
   l'**Intégrateur** et le **Rapporteur** si pertinent (split par rôle).
5. Privilégie les modèles sortis ces 6 derniers mois si dispos.

═══ FORMAT DE RÉPONSE ATTENDU ═══

Pour chacun des 3 profiles, exactement ce template :

```yaml
profile: <small|medium|large>
hardware_cible: <résumé en 1 ligne>
modèles:
  interviewer: <tag ollama>     # toujours local 7B Q4, ne pas changer la classe
  eclaireur:    <tag ollama OR "deterministe — pas de LLM">
  integrateur:  <tag ollama>
  juge:         <tag ollama>
  rapporteur:   <tag ollama>
estimation_temps_3_projets_cold: <XX min>
estimation_VRAM_pic: <XX GB>
risque: <1 ligne, ex. "Qwen3-14B Q4 nécessite ~9 GB, offload CPU 15% sur RTX 3070 8GB">
justification_choix_juge: <2-3 phrases — pourquoi ce modèle pour ce rôle critique>
```

Puis une section finale **"À jour en mois et année"** où tu listes :
- Les modèles que tu as considérés mais écartés, avec raison brève.
- Les modèles "à surveiller dans les 3 mois" qui pourraient changer
  la donne.
- Une recommandation sur la **fréquence à laquelle ré-évaluer** ces
  choix (genre "tous les 6 mois, voir Qwen, Mistral, Phi blogs").

Sois concis, pas de blabla introductif. Mon temps est limité.
```

---

## Ce que tu fais des réponses

1. Le mapping `profile: small` → tu l'inscris dans `src/llm/__init__.py`
   en remplaçant `_PROFILE_MODELS["small"]` par les nouveaux tags.
2. Idem `medium` et `large`.
3. Tu mets à jour `~/.applied-fox/config.yaml` avec le mapping `medium`
   par défaut (ou small si tu n'as qu'un laptop modeste).
4. Tu mets à jour `docs/DECISIONS.md` avec un §20 "Choix des modèles
   par profile au <mois année>" qui cite le rationnel donné par Claude.
5. Tu pulls les modèles manquants via `ollama pull <tag>`.
6. Tu re-runs le pipeline une fois pour valider qu'il n'y a pas de
   régression (déjà acquis : ton harness hot-swap est déjà câblé).

## À garder en tête

- Le **mode "thinking"** de Qwen3.x peut significativement améliorer la
  qualité du Juge mais coûter 2-3× plus de tokens en latence. Active-le
  uniquement pour le Juge si tu vises qualité maximale.
- Si Claude te recommande un modèle pas sur ollama.com/library, demande
  une alternative.
- Si Claude te conseille de TOUT mettre en 14B+, méfie-toi : ton
  Rapporteur fait 1 seul appel par run (synthèse), inutile de l'upgrader.
