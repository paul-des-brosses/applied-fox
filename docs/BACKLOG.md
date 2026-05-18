# BACKLOG — Features post-MVP

Ce document liste tout ce qui est volontairement hors MVP. Chaque feature est suffisamment détaillée pour servir de spec d'implémentation directe sans repasser par une phase d'idéation.

**Hiérarchie en trois niveaux** :
- **Niveau 1** — Fort impact, effort modéré. Premiers candidats post-MVP.
- **Niveau 2** — Fort impact, effort élevé. Plus de planification.
- **Niveau 3** — Vision long terme. Ambitions du projet à 1-2 ans.

---

## Niveau 1 — Fort impact, effort modéré

### L'Historien comme agent à part entière

**Valeur ajoutée** : mémoire longue structurée des décisions passées. Évite de reposer trois fois la même question d'arbitrage. Permet à l'utilisateur de retrouver pourquoi un composant a été choisi six mois plus tôt.

**Effort** : modéré.

**Dépendances** : aucune dépendance forte sur les autres features du backlog. Peut être fait après le MVP directement.

**Spec d'implémentation** :
- Nouvel agent `src/agents/historien.py` consulté par le Juge avant le verdict.
- Format de mémoire : un fichier `~/.applied-fox/state/[projet]_history.jsonl` (append-only) contenant les décisions passées (suggestion, verdict, rationale, date).
- Au lancement du Juge, l'Historien retrouve les décisions similaires (similarité par embedding ou par tags structurés sur le composant + angle).
- Le verdict du Juge inclut une référence aux décisions passées si pertinent.
- Section "Décisions historiques" dans le rapport pour la transparence.
- Pas de risque de pollution contexte si on limite à 3-5 décisions historiques injectées.

### Veille permanente en arrière-plan

**Valeur ajoutée** : l'utilisateur ne pense plus à lancer la veille — elle tourne et alerte quand quelque chose de critique apparaît.

**Effort** : modéré.

**Dépendances** : aucune dure, mais s'articule bien avec les "Alertes critiques" (feature suivante).

**Contrainte UX non négociable** : toute automatisation de la veille doit s'accompagner d'une interface claire permettant d'**archiver ou d'arrêter la veille sur un projet** (ex. projet livré, abandonné, mis en pause). Sans cette interface, l'utilisateur perd le contrôle sur ce qui tourne en fond — ce qui contredit l'invariant "l'agent ne décide jamais à ta place". L'interface d'arrêt n'est pas optionnelle, elle est livrée en même temps que le daemon.

**Spec d'implémentation** :
- Mode daemon : `applied-fox daemon start --interval 24h`.
- Implémentation : process Python tournant en boucle avec `time.sleep` ou via cron système.
- Génération de rapport quotidien/hebdomadaire selon configuration.
- Mode incrémental déjà en place (héritage MVP) : seuls les nouveaux findings sont remontés.
- Configurable par projet (un projet en phase exploration veut une veille plus large qu'un projet figé).
- Fichier de log `~/.applied-fox/daemon.log`.
- Commandes de gestion : `applied-fox daemon stop`, `applied-fox daemon status`, `applied-fox daemon pause --project [nom]`, `applied-fox daemon archive --project [nom]` (archive = arrêt définitif + conservation de l'historique).
- TUI de supervision : liste tous les projets avec leur statut de veille (active, en pause, archivée) et la date du dernier run.

### Alertes critiques configurables

**Valeur ajoutée** : sortir du modèle "rapport périodique" pour le modèle "alerte immédiate" sur des événements critiques (EOL d'un composant clé, pénurie majeure, faille de sécurité).

**Effort** : modéré.

**Dépendances** : la veille permanente (feature précédente) — l'alerte est déclenchée par un run de veille.

**Spec d'implémentation** :
- Configuration : seuils de criticité par type (`obsolescence`, `supply`, `regulation`).
- Le Juge marque les findings dépassant le seuil avec un flag `critical=True`.
- Notification : mail (SMTP local), notification système (`plyer` ou équivalent), ou simple fichier `~/.applied-fox/alerts.md` consulté manuellement.
- Pas d'intégration avec Slack/Discord/Teams au début (ces canaux exfiltreraient les données — incompatible avec la philosophie locale, à moins d'utiliser un webhook self-hosted).

### Section feedback exploitée par le Juge

**Valeur ajoutée** : permettre à l'utilisateur d'apprendre au système ses préférences durables ("on a déjà essayé, ça ne marche pas pour notre cas", "trop cher pour ce projet précis").

**Effort** : modéré côté implémentation, mais demande des garde-fous solides (cf. [`DECISIONS.md` §12](DECISIONS.md) — la feature a été rejetée du MVP pour cause de risques de pollution contexte et cascade incontrôlable).

**Dépendances** : nécessite l'Historien pour fonctionner correctement (les feedbacks sont une variante structurée de mémoire historique).

**Spec d'implémentation** :
- Champ `feedback` ajouté au format `ValidatedSuggestion` rejeté par l'utilisateur.
- L'Historien consigne les feedbacks dans `[projet]_feedback.jsonl`.
- Le Juge consulte les feedbacks similaires au lancement (limite stricte : 3-5 feedbacks max injectés).
- Mécanisme d'expiration : un feedback de plus de N mois est marqué obsolète et n'influence plus.
- TUI Rich : interface dédiée pour consulter, modifier, supprimer les feedbacks.
- Couche de tests unitaires sur les invariants (pas de cascade — un feedback n'en génère pas un autre automatiquement).

### Optimisation performance du pipeline (parallélisation, batching, modèle plus rapide)

**Contexte** : le pipeline complet sur la fiche ESP32 weather station (157 findings) prend ~15-20 minutes — Éclaireur ~6 min, Intégrateur ~5-7 min, Juge ~3-5 min, Rapporteur ~30s. Deux des six pistes d'optimisation initialement listées ici ont été **promues dans le MVP** (cache LLM disque + skip déterministe des findings sans apport) car elles sont simples et sans risque. Les pistes restantes ci-dessous nécessitent du tuning ou du re-benchmarking.

**Pistes restantes pour V2** :

1. **Parallélisation LLM via asyncio** — Ollama supporte plusieurs requêtes concurrentes via son endpoint HTTP. Remplacer les boucles `for finding in findings: llm.invoke(...)` par `asyncio.gather(*[evaluate_one(f) for f in findings])` avec un semaphore qui limite à 4-8 appels concurrents (selon VRAM dispo). Gain théorique : ×4-8 sur les nœuds Intégrateur et Juge. **Reportée car** : refactor de toute l'orchestration, risque de contention sur Ollama (qui charge un seul modèle en VRAM à la fois), à valider sur les deux machines cibles.

2. **Batching de findings dans un seul prompt** — pour les findings courts/similaires (même composant, même angle), envoyer 5-10 findings dans un seul prompt LLM avec sortie JSON liste. Gain : réduction du tokens overhead. **Reportée car** : risque concret de qualité dégradée si le LLM 7B mélange les contextes (déjà sensible aux plaquages projet → finding, multiplié par N si plusieurs findings dans le même contexte). À benchmarker avec un LLM 12B+.

3. **Modèle plus rapide pour certains rôles** — l'Éclaireur structure des JSON simples : un Qwen 2.5 3B-Instruct serait probablement suffisant et 2-3× plus rapide que mistral 7B. **Reportée car** : nécessite une éval complète de qualité comparable à `jalon4_*` pour valider qu'on ne dégrade pas. Le hot-swap LLM est déjà en place via `get_llm(role, config)`, donc c'est juste une config à tester quand on aura le temps de re-évaluer.

**Optimisations déjà intégrées au MVP** (voir Jalon 5d dans ROADMAP_MVP.md) :
- ✅ Cache LLM disk-based (hash du prompt complet → SQLite, invalidation auto si prompt change)
- ✅ Skip déterministe des findings dont la description est "Aucun apport pertinent." avant l'appel Intégrateur

**Justification du report V2** : le cache LLM seul couvre la majorité du frein pendant le dev (relancer un run modifié ne refait que les appels nouveaux). Les pistes restantes apportent du gain en production usage mais demandent du tuning et du benchmarking qui sortent du scope MVP.

---

## Niveau 2 — Fort impact, effort élevé

### Mémoire adaptative distribuée

**Valeur ajoutée** : chaque agent apprend dans son domaine. L'Éclaireur apprend les sources de qualité pour ce projet précis. L'Intégrateur retient les contraintes implicites du créateur. Le Juge garde la trace des arbitrages.

**Effort** : élevé.

**Dépendances** : Historien (Niveau 1) doit être en place. Évaluation auto de la crédibilité des sources est complémentaire mais peut suivre.

**Spec d'implémentation** :
- Un store de mémoire par agent : `~/.applied-fox/memory/[projet]/[agent]_memory.json` (ou base vectorielle locale type ChromaDB pour les agents qui en ont besoin).
- Format spécifique par agent :
  - Éclaireur : sources et leur taux de pertinence empirique.
  - Intégrateur : patterns de contraintes implicites détectés.
  - Juge : décisions historiques avec leurs résultats observés.
  - Rapporteur : préférences de présentation observées.
- Mécanisme de mise à jour explicite (à la fin de chaque run) plutôt qu'implicite (évite la dérive silencieuse).
- Possibilité pour l'utilisateur d'inspecter et reset la mémoire de chaque agent indépendamment.
- Test critique : la mémoire doit améliorer mesurablement le système après N runs (LLM-as-a-judge en avant/après).

### Évaluation automatique de la crédibilité des sources

**Valeur ajoutée** : distinguer un retour terrain d'un communiqué fabricant, un benchmark indépendant d'un test marketing. Pondère les findings selon la fiabilité observée de la source.

**Effort** : élevé.

**Dépendances** : aucune dure, mais s'articule mieux avec mémoire adaptative distribuée.

**Spec d'implémentation** :
- Score de crédibilité par source, calculé dynamiquement sur la base de :
  - Nombre de findings retenus / rejetés issus de cette source.
  - Cohérence des findings avec ceux d'autres sources (cross-validation).
  - Type d'auteur (expert reconnu, anonyme, fabricant identifié).
- Stockage dans `~/.applied-fox/memory/sources_credibility.json`.
- Le filtre déterministe utilise le score pour pondérer les seuils.
- Le Juge utilise le score dans son rationale.
- Affiché dans le rapport comme métadonnée par finding.

### Auto-découverte et cartographie autonome des sources

**Valeur ajoutée** : l'Éclaireur n'attend plus une liste prédéfinie. Il identifie lui-même où l'information existe pour le projet en cours (nouveaux subreddits, dépôts GitHub spécifiques, blogs spécialisés, bases de données réglementaires).

**Effort** : élevé.

**Dépendances** : évaluation auto de crédibilité (sinon explosion combinatoire de sources non triées).

**Spec d'implémentation** :
- Module `src/sources/discovery.py`.
- L'Éclaireur, à intervalles configurables (ex. tous les 10 runs), lance une phase de découverte :
  - Recherche web ouverte (DuckDuckGo, SearXNG self-hosted) avec requêtes dérivées de la fiche projet.
  - Extraction des domaines récurrents.
  - Évaluation initiale de crédibilité.
  - Proposition à l'utilisateur d'ajouter une nouvelle source.
- Validation utilisateur explicite avant intégration.
- Pas de scraping automatique (cohérence avec la décision MVP) — uniquement APIs ou flux RSS exposés.

### Source Octopart / Nexar (prix, disponibilité, datasheets)

**Valeur ajoutée** : ajouter une source officielle constructeur (vs Reddit/GitHub qui sont communautaires). Permet l'angle `price` et `supply` avec données fiables, et le téléchargement automatique des datasheets pour enrichir le contexte projet.

**Effort** : moyen (4-6h). Le module `src/sources/octopart.py` n'a pas été implémenté au MVP — Octopart utilise GraphQL Nexar avec auth OAuth, ce qui ajoute une 4e patron d'intégration que le MVP ne justifie pas (les 3 patterns Reddit/GitHub/RSS suffisent à valider l'architecture extensible).

**Dépendances** : compte Nexar dev (gratuit), `OCTOPART_API_KEY`.

**Spec d'implémentation** :
- Réintroduire `src/sources/octopart.py` avec `search_component(mpn, api_key)` retournant un `OctopartResult` (mpn, manufacturer, datasheet_url, avg_price_usd, stock_total, distributors).
- Wire dans `eclaireur.py` derrière `config.sources.octopart.enabled`.
- TTL `requests-cache` différenciés : prix 24h, dispo 6h, datasheets quasi-permanent.
- Tests unitaires sur le mapping GraphQL → `OctopartResult` (mocker la réponse Nexar).
- Mettre à jour `CONFIG_SCHEMA.md`, `DEPENDENCIES.md`, `ARCHITECTURE.md`.

### Mode `hybrid` (Interview local + agents API)

**Valeur ajoutée** : permet aux utilisateurs avancés d'utiliser des modèles frontier (Claude, GPT-5) pour les agents de veille tout en gardant le module Interview en local — équilibre souveraineté / qualité de raisonnement.

**Effort** : élevé (test, doc, gestion d'erreurs API multi-provider).

**Dépendances** : aucune dure.

**Spec d'implémentation** :
- Section `mode: hybrid` dans `config.yaml`.
- `get_llm("interviewer", config)` reste local (mode `hybrid` ne couvre pas l'Interview).
- `get_llm("eclaireur" / "integrateur" / "juge" / "rapporteur", config)` route vers le provider configuré (Anthropic, OpenAI, Mistral, Groq).
- Variables d'environnement pour les clés API : `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.
- Gestion d'erreurs : rate limits, timeouts, retries exponentiels.
- Avertissement à l'utilisateur : "le contenu de ta fiche projet sera envoyé à [provider]. Confirmer ?".
- Calcul du coût estimé par run basé sur les tokens.

### Support multi-provider (Anthropic, OpenAI, Mistral, Groq)

**Valeur ajoutée** : flexibilité, redondance, choix de coût/qualité.

**Effort** : élevé en cumul (tests, doc, gestion des spécificités par provider).

**Dépendances** : mode hybrid.

**Spec d'implémentation** :
- Implémenter et tester les routes pour chaque provider.
- Documentation par provider (forces, faiblesses, coûts approximatifs au moment de l'implémentation).
- Tests de hot-swap multi-provider (basculer en moins de 5 minutes entre Anthropic et OpenAI sans modification de code).
- LangChain fournit déjà les wrappers — l'effort principal est la doc, les tests et la gestion d'erreurs spécifiques.

### Veille étendue aux librairies software pertinentes (Niveau B)

**Valeur ajoutée** : couvre les frameworks et libs autour des composants (ex. pour ESP32 : ESP-IDF, Arduino libraries, MicroPython packages). Élargit le périmètre au-delà du hardware brut.

**Effort** : élevé (nouveaux types de findings, nouveau prompt pour l'Éclaireur).

**Dépendances** : aucune.

**Spec d'implémentation** :
- Nouvelles sources : PyPI / npm / crates.io selon l'écosystème du projet.
- Nouveau type de `Finding.source_type` : `library`.
- Nouveau angle : `breaking_change` (mise à jour d'une lib avec migration nécessaire).
- L'Intégrateur évalue l'impact d'une mise à jour de lib comme il évalue un changement de composant.

### Veille sur l'écosystème techno complet, papers inclus (Niveau C)

**Valeur ajoutée** : couvre les pré-publications scientifiques (arXiv, IEEE, ACM) qui anticipent les évolutions à 1-2 ans.

**Effort** : élevé.

**Dépendances** : utile d'avoir l'évaluation de crédibilité (Niveau 2) pour ne pas remonter du bruit académique.

**Spec d'implémentation** :
- Source arXiv via API officielle, recherche par mots-clés dérivés des objectifs actifs.
- Filtre : papier publié dans les N derniers mois, citations minimum, cohérence avec les composants.
- Le Rapporteur ajoute une section dédiée "Veille recherche" si pertinent.

### Veille réglementaire automatique

**Valeur ajoutée** : alertes automatiques sur changements CE, RoHS, FCC, et toute réglementation pertinente pour le projet.

**Effort** : élevé (sources hétérogènes, parsing complexe).

**Dépendances** : aucune.

**Spec d'implémentation** :
- Sources : bases de données officielles (FCC database, ECHA REACH, registres CE), flux RSS d'organismes réglementaires.
- Module dédié `src/sources/regulatory.py`.
- Nouveau angle `Finding.angle = "regulation"` (déjà présent dans le schéma MVP — la donnée existe, il faut alimenter).

### Chat "intégration" pour aider à intégrer concrètement

**Valeur ajoutée** : une fois qu'une suggestion est validée, l'utilisateur peut demander de l'aide pour l'intégrer dans le code/setup réel ("où dans mon code je remplace le BME280 par le BME680 ?").

**Effort** : élevé (nouvelle interface, nouveau type de dialogue, accès optionnel au code source).

**Dépendances** : aucune dure, mais cohérent avec mode exécutif (Niveau 3).

**Spec d'implémentation** :
- Module `src/chat/integration.py`.
- Mode `applied-fox chat --project [path] --suggestion [id]`.
- Accès optionnel à un dossier code source (path configurable, lecture seule au début).
- Réponses guidées : "voici les fichiers à modifier", "voici un patch suggéré".
- Pas de modification de code automatique — toujours validation humaine (cf. mode exécutif Niveau 3).

### Web app

**Valeur ajoutée** : ouverture du projet à un public moins technique. Visualisation enrichie des rapports, gestion multi-projets, historique.

**Effort** : élevé (nouveau frontend, gestion de session, refactor partiel du backend).

**Dépendances** : aucune dure.

**Spec d'implémentation** :
- Backend : FastAPI (réutilise les modules existants).
- Frontend : framework léger (Svelte, Vue, ou même HTMX) — privilégier la simplicité.
- Reste 100% local : serveur web tourne sur `127.0.0.1:[port]`, jamais exposé.
- L'utilisateur ouvre `localhost:[port]` dans son navigateur.
- Authentification simple (token local) si plusieurs utilisateurs sur la même machine.
- Aucune dépendance à un service cloud.

---

## Niveau 3 — Vision long terme

### Mode exécutif

**Valeur ajoutée** : l'agent agit après validation humaine. Modifie du code, ouvre des issues GitHub, commande des composants, met à jour un BOM.

**Effort** : très élevé (sécurité, gestion d'erreurs, scope énorme).

**Dépendances** : chat intégration (Niveau 2) en pré-requis fort. Idéalement après mémoire adaptative et Historien.

**Spec d'implémentation** :
- Modes d'exécution opt-in et granulaires (ex. : `code_modification: false`, `github_issues: true`, `purchase: false`).
- Toujours après validation humaine explicite.
- Sandboxé : modifications de code dans un branch git séparé, jamais sur main directement.
- Audit trail complet : chaque action exécutée est consignée.
- Tests d'intrusion / safety review avant release.

### Interface graphique de configuration

**Valeur ajoutée** : utilisateurs moins à l'aise avec YAML peuvent configurer.

**Effort** : modéré à élevé selon le scope.

**Dépendances** : web app (Niveau 2) si on choisit cette voie. Sinon, possible en Textual.

**Spec d'implémentation** :
- Soit comme partie de la web app (Niveau 2).
- Soit comme TUI Textual full-screen.
- Génère le `config.yaml` propre à partir d'un assistant.

### Multi-projets avec détection de synergies

**Valeur ajoutée** : l'agent suggère de mutualiser un composant ou un module entre plusieurs projets de l'utilisateur (ex. mutualiser le BME680 entre Forest of Senses et Digital Twin Percheron).

**Effort** : très élevé.

**Dépendances** : mémoire adaptative distribuée.

**Spec d'implémentation** :
- Nouvel agent `synergiste` (ou extension du Juge).
- Lit les fiches de plusieurs projets, identifie les composants partagés ou substituables.
- Propose des mutualisations dans un rapport cross-projets.
- L'utilisateur peut activer/désactiver par paire de projets.

### Veille communautaire prédictive (anticipation EOL, pénuries)

**Valeur ajoutée** : ne plus attendre l'annonce d'EOL — l'identifier 6-12 mois avant via signaux faibles (réduction des stocks fabricant, baisse de fréquence de mise à jour de la datasheet, diminution des nouveaux designs sur ce composant).

**Effort** : très élevé.

**Dépendances** : évaluation auto de crédibilité, mémoire adaptative.

**Spec d'implémentation** :
- Module d'analyse temporelle des données Octopart (séries de prix, dispo, stocks).
- Détection de patterns prédictifs (par règles déterministes au début, ML possible ensuite).
- Score de risque EOL par composant.
- Alerte proactive si un composant critique du projet voit son score grimper.

### Extension aux projets purement software

**Valeur ajoutée** : couvrir les projets sans hardware (frameworks web, libs Python, etc.).

**Effort** : élevé (refonte des sources, nouveau schéma de fiche).

**Dépendances** : utilité jugée moindre par l'utilisateur — à étudier seulement si demande externe forte.

**Spec d'implémentation** : à instruire au moment de la décision.

### Saint graal — copilote de R&D souverain pour équipes

**Valeur ajoutée** : transformer l'outil personnel en plateforme exportable à des équipes R&D entières.

**Effort** : très élevé. Implique : multi-utilisateurs, gestion des droits, partage sélectif de fiches, audit, conformité.

**Dépendances** : la quasi-totalité des features Niveaux 1 et 2.

**Spec d'implémentation** : à instruire au moment de la décision. Probablement un fork "enterprise" plutôt qu'une évolution du repo personnel.
