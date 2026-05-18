# GLOSSARY — Vocabulaire technique du projet

Ce glossaire vulgarise tous les termes techniques utilisés dans la doc. Chaque terme est défini en 2-4 phrases avec, quand c'est utile, un exemple concret et une note sur son usage dans **Applied Fox**.

Les termes sont groupés par thème : modèles et inférence, agents et orchestration, validation et données, cache et performance, infrastructure.

---

## Modèles et inférence

### LLM — Large Language Model

Un grand modèle de langage est un réseau de neurones entraîné sur d'énormes quantités de texte pour produire du texte plausible en réponse à un prompt. Exemples : Claude, GPT-5, Mistral, Llama. Un LLM ne "sait" rien — il modélise des probabilités sur les mots.

> **Dans ce projet** : tous les agents (Interviewer, Éclaireur, Intégrateur, Juge, Rapporteur) sont des LLM. Au MVP, ils tournent en local via Ollama.

### Modèle local vs cloud

Un modèle **local** s'exécute sur la machine de l'utilisateur (CPU ou GPU). Un modèle **cloud** est hébergé chez un fournisseur (Anthropic, OpenAI, Mistral) et accessible via API. Local : confidentialité maximale, latence variable, coût matériel. Cloud : qualité de raisonnement souvent supérieure, latence réseau, coût récurrent, données qui sortent.

> **Dans ce projet** : module Interview exclusivement local, sans exception. Agents de veille en local par défaut. Le mode `hybrid` (agents en API cloud, Interview toujours local) est en backlog V2.

### Quantification (Q4, Q5, Q8, FP16)

Technique qui réduit la précision numérique des poids du modèle pour le rendre plus compact et plus rapide. `FP16` (16-bit) est la précision native de la plupart des modèles. `Q8` (8-bit), `Q5` (5-bit), `Q4` (4-bit) compriment progressivement, au prix d'une légère perte de qualité.

> **Dans ce projet** : on utilise systématiquement Q4 pour le bon équilibre taille/qualité. Un modèle 7B Q4 fait ~4-5 Go au lieu de ~14 Go en FP16.

### Tokens, contexte, fenêtre de contexte

Un **token** est l'unité de découpage du texte par le modèle (à peu près un mot ou un fragment de mot). Le **contexte** est l'ensemble des tokens fournis au modèle (prompt système + prompt utilisateur + historique). La **fenêtre de contexte** est la limite haute du nombre de tokens que le modèle peut traiter d'un coup (ex. 8 192 tokens pour un modèle Mistral 7B classique).

> **Dans ce projet** : un finding non aligné est filtré en amont pour économiser le contexte. Un `.md` projet bien rédigé tient en quelques milliers de tokens — laisse de la marge pour les findings et le raisonnement.

### Hallucination LLM

Quand un modèle produit une affirmation plausible mais fausse (composant inexistant, citation inventée, comportement imaginaire). C'est une caractéristique intrinsèque, pas un bug.

> **Dans ce projet** : on combat les hallucinations par (1) la validation Pydantic à chaque étape — sortie mal formée = retry, (2) les artefacts intermédiaires sauvegardés pour audit, (3) la validation humaine finale.

### Prompt engineering

Discipline qui consiste à formuler les prompts (instructions données au LLM) pour obtenir des sorties fiables et exploitables.

> **Dans ce projet** : chaque agent a un prompt système soigneusement rédigé. L'alignement téléologique est inscrit dans le prompt système de l'Éclaireur.

### Prompt système vs prompt utilisateur

Le **prompt système** définit le rôle, le ton, les contraintes du modèle. Le **prompt utilisateur** est la requête concrète. Convention LLM : le prompt système est plus stable (rarement changé), le prompt utilisateur change à chaque appel.

> **Dans ce projet** : prompts système versionnés dans `src/agents/[agent]/prompts.py`. Prompts utilisateur construits dynamiquement à partir du `.md` et des inputs de l'agent.

### Chain of thought (chaîne de raisonnement)

Technique qui demande au modèle de "réfléchir à voix haute" avant de répondre. Améliore la qualité des réponses sur les tâches complexes.

> **Dans ce projet** : le rationale en clair (`02_integrateur_reasoning.md`, `03_juge_reasoning.md`) est une forme persistée de chain of thought, utile pour audit.

### Tool use / function calling

Capacité d'un LLM à appeler des fonctions externes (recherche web, calcul, accès API) à la place de "deviner" la réponse. Les sorties sont structurées en JSON.

> **Dans ce projet** : pas utilisé de manière native (le function calling varie selon les providers — incompatible avec l'objectif hot-swap). On préfère un parsing Pydantic explicite avec retry.

### Sortie structurée (structured output)

Au lieu de produire du texte libre, le LLM produit du JSON conforme à un schéma. Plus fiable pour l'orchestration entre modules.

> **Dans ce projet** : tous les agents internes communiquent en JSON Pydantic (Finding, IntegrationVerdict, etc.). Seule la sortie utilisateur finale (rapport) est en Markdown libre.

### Embedding

Représentation numérique d'un texte sous forme de vecteur de quelques centaines de dimensions, qui capture la sémantique. Permet la recherche par similarité.

> **Dans ce projet** : pas central au MVP. Les embeddings deviendront utiles en V2 pour la mémoire adaptative distribuée et la déduplication sémantique des findings.

### RAG — Retrieval Augmented Generation

Architecture où on récupère (retrieve) des documents pertinents dans une base avant de les passer au LLM (augmented generation). Différent de simplement "lui donner accès au web".

> **Dans ce projet** : pas central au MVP. L'Éclaireur n'est pas un système RAG classique — il interroge des sources structurées (APIs, RSS) plutôt que de chercher dans une base vectorielle. Le RAG pourrait apparaître en V2 pour l'Historien.

---

## Agents et orchestration

### Agent IA

Un programme qui combine un LLM avec des outils (recherche web, accès fichiers, appels API) et une boucle de raisonnement, pour atteindre un objectif au lieu de simplement produire une réponse one-shot.

> **Dans ce projet** : 4 agents LLM au MVP (Éclaireur, Intégrateur, Juge, Rapporteur) + l'Interviewer. Plus l'Historien et 1 chef en V2.

### Système multi-agent

Architecture où plusieurs agents collaborent, chacun spécialisé sur une sous-tâche. Permet de découper un problème complexe en problèmes plus simples.

> **Dans ce projet** : pipeline Éclaireur → Intégrateur → Juge → Rapporteur. Filtrage progressif : 20 findings → ~10 verdicts → ~5 retenus → rapport.

### Framework agentique

Une bibliothèque qui fournit l'infrastructure pour construire des systèmes multi-agents : orchestration, état partagé, persistance des runs, abstraction provider.

> **Dans ce projet** : on utilise LangGraph.

### LangGraph

Framework agentique de l'écosystème LangChain, organisé autour d'un graphe d'états et d'événements. Chaque nœud du graphe est un agent ou une fonction. Les edges (liens) peuvent être conditionnels.

> **Dans ce projet** : standard de fait en 2026. Gère l'orchestration entre agents, l'état partagé `TechWatchState`, et le branchement conditionnel (un finding non intégrable saute l'étape Juge).

### Ollama

Outil qui simplifie l'exécution de modèles open-source en local. Téléchargement, gestion, exposition d'une API REST locale (port 11434 par défaut).

> **Dans ce projet** : socle local du MVP. `ollama pull mistral:7b-instruct-q4_K_M` télécharge un modèle, puis tous les agents l'interrogent via l'API REST.

---

## Validation et données

### Pydantic

Bibliothèque Python de validation de données par schéma typé. On déclare une classe avec des types, Pydantic vérifie que les entrées correspondent.

> **Dans ce projet** : valide tous les schémas (ProjectModel, Finding, IntegrationVerdict, Config). Couche 1 de validation du `.md`. Si un agent renvoie un JSON malformé, retry automatique.

### LLM-as-a-judge

Méthodologie d'évaluation où on utilise un LLM (typiquement plus puissant que celui évalué) pour noter les sorties d'un autre LLM. Permet une évaluation à grande échelle sans intervention humaine systématique.

> **Dans ce projet** : on utilise Claude Opus 4.7 pour évaluer la qualité des `.md` produits par l'Interviewer (note ≥ 7/10) et la pertinence des suggestions du pipeline (≥ 80% alignées). Cf. [`ROADMAP_MVP.md`](ROADMAP_MVP.md).

### Mode incrémental

Stratégie qui consiste à filtrer les findings déjà présentés à l'utilisateur lors des runs précédents, pour ne montrer que les nouveautés.

> **Dans ce projet** : `~/.applied-fox/state/[projet]_seen.json` contient les hashs des findings déjà présentés. Critique pour la qualité de signal dès le second run.

### Filtrage déterministe

Filtre par règles dures (pas de LLM), appliqué aux résultats bruts des sources avant de les soumettre au LLM. Élimine 60-70% du bruit.

> **Dans ce projet** : critères = alignement composants/objectifs, fraîcheur, score communautaire minimum, déduplication par hash. Inscrit comme règle non négociable dans [`DECISIONS.md` §10](DECISIONS.md).

### Hash (déduplication par hash)

Empreinte numérique courte et stable d'un contenu. Si deux findings ont le même hash, ce sont les mêmes — on en garde un seul.

> **Dans ce projet** : hash calculé sur `nom_composant + titre + source`. Stable au MVP (rudimentaire mais suffisant), à raffiner en V2 avec similarité sémantique.

---

## Cache et performance

### Cache TTL — Time To Live

Durée de vie d'une entrée en cache. Une fois écoulée, la requête est rejouée et le cache rafraîchi.

> **Dans ce projet** : TTL différenciés par source : Reddit (12h), GitHub (24h), RSS (24h). Géré par `requests-cache`. Octopart prévu en V2 avec TTL différenciés prix (24h) / dispo (6h) / datasheets (quasi-permanent).

### Rate limit

Limite imposée par une API sur le nombre de requêtes par unité de temps. Dépasser le rate limit = erreur 429 ou blocage temporaire.

> **Dans ce projet** : Reddit, GitHub, RSS ont chacun leurs limites. Le cache `requests-cache` réduit drastiquement les requêtes. La dégradation gracieuse permet au pipeline de continuer si une source est limitée temporairement.

---

## Architecture du projet

### Hot-swappable

Caractéristique d'un système où un composant peut être remplacé sans modification du code environnant. Pour un LLM, ça signifie : changer de modèle ou de provider via la config seule.

> **Dans ce projet** : contrainte non négociable. Tous les appels LLM passent par `get_llm(role, config)`. Aucun import direct de `ChatOllama`, `ChatAnthropic`, etc. Test de validation : bascule 7B → 14B en moins de 5 min via la config.

### Profile hardware

Préset de configuration adapté à une classe de machines. L'abstraction "profile" (small/medium/large) a été abandonnée en v1.4 au profit d'un modèle par agent selon la complexité de sa tâche. Voir `docs/HARDWARE.md`.

### TUI — Terminal User Interface

Interface utilisateur qui s'exécute dans un terminal, avec des éléments visuels (tableaux, prompts colorés, barres de progression). Plus riche qu'une CLI plate, plus simple qu'une web app.

> **Dans ce projet** : TUI construit avec `rich`. Suffisant pour le MVP, web app en backlog.

### API REST

Style d'interface où les fonctions sont exposées comme des routes HTTP (GET, POST, etc.) sur un endpoint. Standard du web moderne.

> **Dans ce projet** : Reddit, GitHub, RSS, Ollama exposent tous des APIs REST. Le projet est consommateur d'APIs, pas producteur (au MVP).

### Variable d'environnement

Valeur stockée dans l'environnement du shell, accessible aux processus enfants. Manière standard de fournir des secrets (clés API) à un programme sans les écrire en dur dans le code.

> **Dans ce projet** : toutes les clés API sont des variables d'env (`GITHUB_TOKEN`, `REDDIT_CLIENT_ID`, etc.). Lecture via `python-dotenv` qui supporte aussi un `.env` local en développement.

---

## Outils dev

### LangFuse

Plateforme open-source d'observabilité pour systèmes LLM. Trace les prompts, les latences, les tokens consommés, les erreurs. Self-hostable via Docker.

> **Dans ce projet** : recommandé pour le développement. Self-hosted = aucune fuite de traces. Strictement optionnel — l'utilisateur final n'en a pas besoin.

### LangSmith

Équivalent cloud de LangFuse, hébergé par LangChain. Gratuit jusqu'à un certain volume.

> **Dans ce projet** : alternative à LangFuse pour usage perso uniquement. Cohérent avec la philosophie locale uniquement si on accepte que les traces transitent par le cloud.

---

## Termes spécifiques au projet

### `.md` projet (fiche projet)

Le fichier Markdown structuré qui décrit un projet. Artefact central, lu par tous les agents en aval. Spec : [`MD_SCHEMA.md`](MD_SCHEMA.md).

### Validation à 3 couches

Stratégie de validation appliquée au `.md` projet à chaque création ou modification. Couche 1 : règles déterministes (Pydantic + parsers). Couche 2 : test de transmission par LLM tiers (vérifie que le `.md` est autonome). Couche 3 : validation humaine.

### Alignement téléologique

Principe selon lequel toute suggestion non alignée avec les objectifs actifs déclarés du projet est rejetée. Inscrit dans le prompt système de l'Éclaireur ET dans le filtre déterministe en amont du LLM.

### Modes Interview (`create` / `update` / `integrate`)

L'Interviewer est un module à plusieurs modes. `create` : questionnaire à blanc pour produire un `.md` neuf. `update` : modification ciblée d'un `.md` existant. `integrate` : application d'un objet `ValidatedSuggestion` issue d'une suggestion validée par l'utilisateur.

### Filtrage progressif

Réduction du nombre de findings à chaque étape du pipeline : Éclaireur produit ~20 → Intégrateur en filtre la moitié (non intégrables) → Juge en filtre encore (gain insuffisant) → Rapporteur ne synthétise que ce qui reste.

### Run

Une exécution complète du pipeline pour un projet donné. Produit un dossier d'artefacts dans `~/.applied-fox/runs/[timestamp]_[projet]/`.

### Statut décisionnel (`figé` / `validé` / `en évaluation`)

Métadonnée portée par les composants et les outils de la stack software. `figé` = non négociable. `validé` = choix actuel ouvert à discussion. `en évaluation` = pas encore tranché.

### Rôle pipeline (`critique` / `support` / `accessoire`)

Métadonnée portée par les composants. `critique` = sans lui le système ne fonctionne pas. `support` = peut être substitué. `accessoire` = option, amélioration.

---

## Prompt engineering

### Prompt

Le texte qu'on envoie à un LLM pour obtenir une réponse. Composé typiquement de deux parties : le **system prompt** (instructions de rôle, contraintes, format de sortie) et le **user prompt** (la requête concrète, les données à traiter). La qualité d'un prompt détermine la qualité de la sortie — un LLM ne peut pas deviner ce qu'on attend.

> **Dans ce projet** : chaque agent (Interviewer, Éclaireur, Intégrateur, Juge, Rapporteur) a un system prompt dédié. Ces prompts sont du **code critique** au même titre que la logique Python : ils sont versionnés, testés, et révisés.

### System prompt vs user prompt

Le **system prompt** définit le comportement persistant de l'agent : qui il est, quelles règles il respecte, quel format de sortie il doit produire. Le **user prompt** porte les données d'entrée variables (la fiche projet, le finding, la réponse à valider). Le system prompt est rédigé une fois et stabilisé ; le user prompt change à chaque appel.

> **Dans ce projet** : voir `_REQUESTION_SYSTEM_TEMPLATE` dans `src/interview/create.py` — c'est le system prompt du re-questionnement Interview.

### Few-shot (zero-shot, one-shot, few-shot)

Stratégie qui consiste à donner au LLM des **exemples de l'output attendu** dans le prompt avant la vraie question. `zero-shot` = aucun exemple, `one-shot` = un exemple, `few-shot` = plusieurs exemples. Les exemples calibrent fortement le comportement, notamment sur les modèles plus petits (7B, 12B Q4) qui ont du mal à inférer le format attendu sans exemple.

### Failure mode (mode d'échec)

Une manière connue par laquelle un LLM peut donner une mauvaise réponse : hallucination, paraphrase, sur-permissivité, sur-rejet, format incorrect. Un bon system prompt liste explicitement les failure modes à éviter. Pour les modèles locaux 7B-14B, on combine souvent prompts + **pré-checks déterministes** (regex, schémas Pydantic) pour compenser la variabilité du modèle.

> **Dans ce projet** : `_deterministic_verdict()` dans `src/interview/create.py` détecte par regex les modes d'échec triviaux (TBD seul, phrases génériques sans chiffre ni sigle technique) sans appeler le LLM, qui n'est sollicité que pour les cas subtils.

### Hybrid validation (validation hybride)

Pattern qui combine **règles déterministes en code** (regex, schémas) et **jugement LLM** dans un même flux de validation. Les règles capturent les cas évidents avec une fiabilité 100% ; le LLM est réservé aux jugements subjectifs. Plus robuste qu'un système 100% LLM (qui peut halluciner) ou 100% règles (qui rate les cas subtils).

> **Dans ce projet** : le re-questionnement Interview rejette d'abord par regex (TBD seul, < 6 mots, aucun chiffre/sigle), puis appelle le LLM pour les zones grises (phrase verbeuse mais générique).

### Structured output

Sortie LLM contrainte à un format machine-lisible (JSON, Pydantic schema, function call). Réduit la variabilité, élimine le parsing texte fragile, force l'inclusion de tous les champs requis. Soutenu nativement par certains providers (OpenAI tools, Anthropic tools, Ollama format JSON).

> **Dans ce projet** : tous les `Finding`, `IntegrationVerdict`, `JudgeVerdict`, `ValidatedSuggestion` sont produits en sortie structurée Pydantic. Voir `src/models.py`.
