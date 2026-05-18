# DECISIONS — Récap structuré des choix de design

Ce document retrace toutes les décisions de design du MVP avec leurs justifications. Pour chaque décision : contexte, options envisagées, choix retenu, justification, trade-off accepté.

Les décisions sont groupées par thème. Les quatre premières sections couvrent les **contraintes fondamentales non négociables** — ce qui est figé pour la vie du projet. Les sections suivantes couvrent les choix d'implémentation du MVP.

---

## 1. Design — Tout en local possible

### Contexte
Le projet existe en réaction aux outils agentiques actuels qui exfiltrent les données projet vers des serveurs tiers. Cette exfiltration est rédhibitoire pour des projets sensibles (sécurisation de site critique, R&D, défense, médical, industrie sensible).

### Options envisagées
- **Option A** — Tout en local, par design, sans dérogation possible.
- **Option B** — Local par défaut, basculement opt-in vers API cloud avec accord utilisateur explicite.
- **Option C** — Cloud par défaut, mode local opt-in pour utilisateurs avancés.

### Décision retenue
**Option B avec asymétrie par module** :
- Le module **Interview** (qui ingère le contenu intime du projet) est en local **exclusivement**, à toutes les versions. Contrainte fondamentale non négociable : l'Interview ne quitte jamais la machine. Aucun mode API n'est prévu pour ce module.
- Les modules de veille (Éclaireur, Intégrateur, Juge, Rapporteur) sont en local par défaut au MVP, et pourront basculer en API cloud en V2 (mode `hybrid`) avec accord explicite de l'utilisateur.

### Justification
La donnée la plus sensible, c'est la fiche projet elle-même — composants, contraintes, intentions de design. Cette donnée transite par l'Interview et n'a aucune raison de quitter la machine. Les agents de veille, en revanche, manipulent surtout des informations publiques (specs de composants, posts Reddit, datasheets) et leurs prompts contiennent le `.md` projet, ce qui pose un risque moindre mais réel — d'où le choix du local par défaut au MVP, et de l'opt-in cloud en V2.

### Trade-off accepté
- Performance brute moindre qu'avec un Claude Opus ou un GPT-5 cloud.
- Qualité de raisonnement de premier niveau plus faible avec un 14B local qu'avec un modèle frontier.
- Ces trade-offs sont compensés par la garantie de souveraineté et par l'évolution rapide des modèles locaux open-source.

---

## 2. Design — Hot-swappable LLM

### Contexte
L'écosystème des modèles évolue vite. Un modèle de référence aujourd'hui peut être surpassé dans trois mois. Le système doit pouvoir basculer entre modèles sans refactor.

### Options envisagées
- **Option A** — Code couplé à un seul provider (Ollama au MVP), à refactorer plus tard.
- **Option B** — Abstraction provider dès le MVP, structurellement multi-provider, mais une seule option testée et exposée.
- **Option C** — Multi-provider exposé dès le MVP, plusieurs options documentées et maintenues.

### Décision retenue
**Option B**. Le code est structuré autour d'une fonction `get_llm(role, config)` qui peut router vers n'importe quel provider supporté par LangChain (Ollama, Anthropic, OpenAI, Mistral, Groq), mais le MVP n'expose et ne documente que le mode local Ollama. Les autres routes existent dans le code mais ne sont ni testées ni documentées en frontline.

### Justification
- Coût d'implémentation initial faible (LangChain fournit déjà l'abstraction).
- Permet le bascule de modèle local en moins de 5 minutes via une seule ligne de config (test de validation explicite dans la roadmap).
- Évite le piège classique du refactor d'urgence quand un meilleur modèle apparaît.
- Discipline MVP préservée : on ne maintient pas trois providers en parallèle au MVP, on n'expose qu'un mode.

### Trade-off accepté
- Une couche d'abstraction supplémentaire dès le départ, même si une seule route est utilisée.
- Légère complexité dans la gestion des modèles : on doit penser au support multi-provider même pour des tests qui n'utiliseront jamais que Ollama.

---

## 3. Design — Adaptable hardware

### Contexte
Les utilisateurs cibles ont des configurations matérielles très disparates — entre une station de travail puissante (GPU dédié, grande RAM) et un ultraportable modeste (GPU intégré, RAM limitée). Le projet doit pouvoir tourner sur l'ensemble de cet éventail sans nécessiter de refactoring.

### Options envisagées
- **Option A** — Un seul modèle cible, configuration figée.
- **Option B** — Trois profiles machine prédéfinis (`small`, `medium`, `large`), avec dégradation gracieuse.
- **Option C** — Détection automatique des ressources et choix dynamique du profile.

### Décision retenue
**Option B** avec trois profiles :
- `small` : modèle 7B Q4 (laptop modeste, ≥ 16 Go RAM, GPU optionnel).
- `medium` : modèle 14B Q4 (machine correcte, ≥ 32 Go RAM ou GPU 8 Go+).
- `large` : modèle 32B Q4 (machine puissante, GPU 16 Go+ ou 64 Go RAM).

Le profile est défini en config. L'utilisateur peut surcharger le modèle exact (ex. tester un Mistral Small 3 spécifique).

### Justification
- Trois profiles couvrent l'éventail réaliste des machines d'étudiants/ingénieurs sans complexité excessive.
- La configuration minimum supportée (7B Q4 sur 16 Go RAM, GPU optionnel) reste alignée avec ce que tournent Unity ou SolidWorks sur un laptop étudiant correct — donc cohérente avec le public cible.
- Détection automatique (Option C) ajouterait une dépendance et un cas d'erreur pour un gain marginal — un utilisateur capable d'installer Ollama est capable de choisir un profile.

### Trade-off accepté
- L'utilisateur doit choisir son profile manuellement (mais le défaut `small` fonctionne partout).
- Le profile choisi peut être sous-optimal si l'utilisateur ne connaît pas sa machine — mitigé par une page de doc claire.

---

## 4. Design — Format `.md` strict

### Contexte
Tous les agents en aval ont besoin d'une représentation fiable et exploitable du projet. Cette représentation doit être à la fois lisible par un humain (pour pouvoir l'éditer manuellement), structurée (pour être validable), versionnable (git-friendly) et autonome (lisible sans contexte de la conversation).

### Options envisagées
- **Option A** — JSON pur, validable mais peu lisible humainement.
- **Option B** — YAML, équilibre entre lisibilité et structure.
- **Option C** — Markdown libre, lisible mais non validable.
- **Option D** — Markdown structuré strict, validable par parsers + Pydantic.

### Décision retenue
**Option D** — Markdown structuré à deux étages :
- Sections fixes obligatoires (Identité, Description, Objectifs actifs, Prochain rendu, Composants, Stack software, Interactions, Contraintes non négociables, Changements).
- Section **Contraintes** adaptative : sous-sections libres (Performance, Énergie, Connectivité, Environnementales, Budget, etc.), chaque critère exprimé soit en valeur définie, soit en `N/A`, soit en `TBD` avec justification.

La spec complète vit dans [`MD_SCHEMA.md`](MD_SCHEMA.md).

### Justification

C'est un choix délibérément plus difficile que JSON, pour une raison précise : une fiche projet a deux vies. Elle est lue par des machines (les agents), mais elle est aussi lue, corrigée et commitée par un humain en dehors de l'outil. JSON résout bien la première vie, moins bien la deuxième.

**Git diffs lisibles.** Un `git diff` sur une fiche `.md` après un run d'intégration est immédiatement compréhensible ("le composant BME680 a été ajouté, l'objectif X a été mis à jour"). Sur JSON, c'est du bruit de guillemets et de virgules.

**Format auto-documenté.** On ouvre une fiche sans connaître le schéma et on comprend ce qu'on lit. Un tableau Markdown avec `| BME680 | capteur T/H | validé | critique |` est plus naturel à lire qu'un objet JSON avec les mêmes clés.

**Deux chemins de correction, pas un seul.** Si une fiche est fausse ou incomplète, l'utilisateur peut soit l'éditer directement dans son éditeur de texte, soit repasser par `applied-fox interview update` qui reprend chaque champ en proposant la valeur actuelle. Cette deuxième voie est particulièrement utile après un run qui a modifié la fiche : on peut vérifier champ par champ que l'intégration est correcte, sans toucher au fichier brut.

**Problème d'ingénierie réel.** Construire un format à la fois éditable à la main et validable par une machine est un vrai problème. Le parseur custom (`src/validation/structural.py`) en est la solution — pas un contournement.

**Ce qu'on ne prétend pas.** JSON serait difficile à éditer à la main (faux, VSCode gère bien). Les LLMs comprennent mieux le Markdown que le JSON en contexte (non mesuré). Ces arguments ne font pas partie de la justification.

### Trade-off accepté
- Plus de code à écrire pour le parsing/validation que pour du JSON pur.
- Le parseur a des points de fragilité connus (accents dans les titres de section, espacement autour du `:` dans les listes KV, interactions silencieusement ignorées si mal formatées) — mitigés par la normalisation dans `_norm()` et les messages d'erreur explicites.

---

## 5. Validation à 3 couches symétriques

### Contexte
Le `.md` projet est l'artefact central du système. Si la fiche est incohérente ou incomplète, tous les agents en aval produisent du bruit. Une validation simple ne suffit pas — un `.md` peut être structurellement valide mais sémantiquement faux.

### Options envisagées
- **Option A** — Validation Pydantic uniquement.
- **Option B** — Validation Pydantic + relecture humaine.
- **Option C** — Trois couches : règles déterministes, test de transmission par LLM tiers, validation humaine.

### Décision retenue
**Option C**, appliquée *symétriquement* à la création initiale du `.md` ET à toute modification ultérieure (mode integrate après validation d'une suggestion).

- **Couche 1 — Validation déterministe** (Pydantic + parsers Markdown) :
  - Niveau 1 : sections obligatoires présentes.
  - Niveau 2 : structure interne correcte (colonnes des tables, valeurs énumérées correctes, formats de date).
  - Niveau 3 : cohérence sémantique interne (composants référencés dans Interactions existent dans la table Composants, dates cohérentes avec la phase, etc.).
- **Couche 2 — Test de transmission par LLM** : un LLM lit le `.md` *sans* contexte de la conversation et produit un résumé en clair de ce qu'il comprend du projet. Cette couche teste si le `.md` est autonome — les autres agents en aval n'auront que ce fichier.
- **Couche 3 — Validation humaine finale explicite** par l'utilisateur.

Si une couche échoue, on ne passe pas à la suivante.

### Justification
- La couche 1 attrape les erreurs de structure pures (cheap).
- La couche 2 attrape les erreurs sémantiques que Pydantic ne voit pas (un `.md` qui parle d'un capteur sans préciser sa fonction passe Pydantic mais échoue le test de transmission).
- La couche 3 garde l'humain comme dernier rempart — alignée avec le principe "ne décide jamais à votre place".
- Symétrie création/modification : un `.md` modifié après une suggestion validée doit passer les mêmes contrôles qu'un `.md` neuf, sinon on accumule de la dette de cohérence à chaque cycle.

### Trade-off accepté
- Coût additionnel à chaque modification (couche 2 nécessite un appel LLM dédié).
- Friction utilisateur si une modification simple déclenche les trois couches — assumé : la fiche projet est l'artefact critique, sa qualité prime sur la fluidité.

---

## 6. LangGraph plutôt que CrewAI, smolagents ou custom Python

### Contexte
Le système est multi-agent. Il faut choisir un framework d'orchestration ou écrire le sien.

### Options envisagées
- **Option A** — LangGraph (LangChain).
- **Option B** — CrewAI.
- **Option C** — smolagents (Hugging Face).
- **Option D** — Orchestration custom en Python pur.

### Décision retenue
**Option A — LangGraph.**

### Justification
- Standard de facto en 2026 dans l'écosystème agentique sérieux.
- Gestion d'état partagé (`TechWatchState`) native, ce qui colle parfaitement au flux entre Éclaireur → Intégrateur → Juge → Rapporteur.
- Persistance des runs intégrée, utile pour les artefacts intermédiaires (`runs/[timestamp]_[projet]/`).
- Abstraction provider quasi-gratuite via LangChain (lien direct avec la décision hot-swap).
- Branchements conditionnels (un finding non intégrable est court-circuité avant le Juge) idiomatiques.
- CrewAI : orientée "agents qui se parlent", trop conversationnel pour notre flux structuré. smolagents : trop minimal, manque la gestion d'état. Custom : reconstruirait LangGraph en moins bien.

### Trade-off accepté
- Dépendance à un framework qui évolue vite (l'API LangGraph a changé plusieurs fois).
- Courbe d'apprentissage initiale — mitigée par la valeur portfolio (LangGraph est ce que les recruteurs reconnaissent).

---

## 7. Quatre agents LLM + graphe orchestrateur, pas six agents

### Contexte
La vision long terme prévoit six agents (Chef, Éclaireur, Intégrateur, Juge, Rapporteur, Historien). Le MVP doit-il déjà tous les implémenter ?

### Options envisagées
- **Option A** — Implémenter les six agents au MVP.
- **Option B** — Implémenter quatre agents LLM + déléguer le rôle du Chef au graphe LangGraph + reporter l'Historien.
- **Option C** — Tout fusionner en un seul agent monolithique pour le MVP.

### Décision retenue
**Option B**. Au MVP : quatre agents LLM (Éclaireur, Intégrateur, Juge, Rapporteur) + le graphe LangGraph qui assume le rôle du Chef + l'Historien renvoyé au backlog.

### Justification
- Le rôle du Chef au MVP est purement orchestrationnel (qui parle quand, dans quel ordre). LangGraph remplit cela nativement, sans surcoût LLM.
- L'Historien implique une mémoire longue persistante structurée — feature complexe en soi, qui mérite un jalon dédié post-MVP.
- Quatre agents LLM suffisent à valider l'architecture, prouver la valeur, et générer un rapport utile.
- Un Chef LLM peut être ajouté en V2 si le besoin émerge (ex. un projet où la priorisation dynamique des tâches devient critique).

### Trade-off accepté
- Pas de "vraie" mémoire long terme au MVP — la section "Changements" du `.md` joue ce rôle de façon minimale, ce qui est suffisant pour les premiers cycles.
- Coordination figée par le code du graphe, moins flexible qu'un Chef LLM — assumé pour le MVP.

---

## 8. Sources MVP — Reddit, GitHub, RSS — pas de scraping

### Contexte
Il faut choisir où l'Éclaireur va chercher l'information. L'écosystème offre des dizaines de sources possibles ; le MVP doit en couvrir une diversité représentative sans s'éparpiller.

### Options envisagées
- **Option A** — Une seule source bien intégrée (ex. Reddit).
- **Option B** — Trois sources représentatives, trois patterns d'intégration différents.
- **Option C** — Dix+ sources, couverture maximale.
- **Option D** — Inclure du web scraping pour les sources sans API.

### Décision retenue
**Option B**. Trois sources, trois patterns :
1. **Reddit (endpoints publics)** — retours communautaires (gratuit, généreux en quota).
2. **GitHub API** — écosystème open-source autour des composants (token via `GITHUB_TOKEN`).
3. **RSS press tech** — Hackaday, CNX-Software, Adafruit Blog, Electronics Weekly, EE Times pour annonces fabricants.

**Pas de scraping au MVP.**

Octopart (Nexar API) avait initialement été retenu comme 4e source mais a été reporté en V2 (cf. [`BACKLOG.md`](BACKLOG.md) Niveau 2). Justification : son intégration GraphQL avec OAuth ajoute un 4e pattern d'intégration que le MVP ne justifie pas — les 3 patterns existants (REST sans auth, REST avec token, parsing RSS) suffisent à valider l'architecture extensible. La source supply-chain spécialisée rejoindra le V2 quand le coût total (auth + tests + maintenance) sera justifié par un usage prouvé.

### Justification
- Trois sources couvrent trois angles complémentaires : retour terrain (Reddit), écosystème logiciel (GitHub), annonces officielles (RSS).
- Chaque source utilise un pattern d'intégration différent (REST public, REST avec token, parsing RSS) — démontre l'architecture extensible sans la surcharger.
- Pas de scraping : zone juridiquement grise (CGU souvent ambiguës), maintenance pénible (les sites changent), mauvais signal portfolio (un projet sérieux respecte les conditions d'usage des plateformes).
- Une source unique (Option A) ne validerait pas l'architecture multi-source. Dix sources (Option C) noieraient le MVP dans la maintenance.

### Trade-off accepté
- Pas de source supply-chain officielle au MVP (prix, dispo, distributeurs) — l'utilisateur compense en lisant les fiches composants des suggestions à la main. À résoudre en V2 via Octopart.
- Couverture incomplète (pas de Hackster, pas de bases datasheet directes, pas de papiers arXiv) — assumé, ces sources rejoignent le backlog.
- Dépendance à des APIs tierces — mitigée par le cache et la dégradation gracieuse (si Reddit est down, le rapport sort sans Reddit).

---

## 9. Mode incrémental dès le MVP — pas en backlog

### Contexte
Sans mode incrémental, chaque run de l'agent re-présente les mêmes findings que le run précédent. L'utilisateur perd confiance immédiatement. C'est un problème de qualité de signal majeur.

### Options envisagées
- **Option A** — Mode incrémental en backlog post-MVP.
- **Option B** — Mode incrémental dès le MVP, simple : hashs des findings déjà présentés stockés sur disque.

### Décision retenue
**Option B**. Le bloc 9 d'idéation a explicitement déplacé cette feature du backlog au MVP. Implémentation : `~/.applied-fox/state/[projet]_seen.json` contient les hashs des findings déjà présentés ; au lancement, l'Éclaireur filtre.

### Justification
- Sans cette feature, l'expérience utilisateur du second run est désastreuse — et il n'y a généralement pas de troisième run.
- Coût d'implémentation très faible (un fichier JSON, une fonction de hash).
- Pertinence forte : aligne le système avec un usage réaliste (lancer la veille toutes les semaines, pas une seule fois).

### Trade-off accepté
- Le hash doit être stable (`nom_composant + titre + source`) — si la source change le titre légèrement, le finding est re-présenté. Acceptable au MVP, à raffiner en V2 (similarité sémantique).

---

## 10. Filtrage déterministe en amont du LLM

### Contexte
Sans filtrage en amont, l'Éclaireur envoie au LLM des dizaines de findings dont la majorité est manifestement non pertinente (mauvais composant, trop ancien, score communautaire ridicule). Cela coûte des tokens, ralentit le pipeline, et noie le signal.

### Options envisagées
- **Option A** — Tout envoyer au LLM, le laisser filtrer.
- **Option B** — Filtre déterministe en amont (règles dures), seul le pertinent atteint le LLM.

### Décision retenue
**Option B — règle non négociable.**

Critères du filtre déterministe :
- Alignement avec les composants déclarés dans la fiche.
- Alignement avec les objectifs actifs déclarés (cf. décision suivante).
- Fraîcheur (pas de findings de plus de N mois selon la source).
- Score communautaire minimum (pour Reddit : score > seuil, pour GitHub : étoiles > seuil).

### Justification
- Élimine 60-70% du bruit avant l'appel LLM.
- Économie tokens significative — critique pour la viabilité du MVP en local (un 14B Q4 plus son contexte saturé devient lent rapidement).
- Améliore la qualité de signal : le LLM travaille sur du matériel pré-trié, sa sortie est plus fiable.
- Le filtre déterministe est testable unitairement — pas besoin de LLM pour valider qu'il fait son travail.

### Trade-off accepté
- Risque théorique de filtrer un finding pertinent qui ne matche pas les critères — mitigé par la conservation des findings filtrés dans `01_eclaireur_sources.json` pour audit.
- Configuration des seuils à itérer sur la durée — pas un blocage MVP.

---

## 11. Alignement téléologique avec les objectifs actifs

### Contexte
Risque majeur des IA de veille : le gold-plating. L'agent suggère en permanence des "améliorations" qui n'apportent rien à la finalité du projet, parce qu'il optimise sur des métriques abstraites (perf, prix, modernité) sans regarder si ces métriques comptent pour *ce projet à ce moment*.

### Options envisagées
- **Option A** — L'agent évalue les findings sur des métriques universelles.
- **Option B** — L'agent évalue les findings strictement contre les objectifs actifs déclarés dans la fiche projet.

### Décision retenue
**Option B — règle de design fondamentale.**

Un finding non aligné avec les objectifs actifs déclarés est rejeté automatiquement, à deux endroits :
1. Dans le **prompt système de l'Éclaireur** (instruction explicite).
2. Dans le **filtre déterministe en amont du LLM** (règle dure).

### Justification
- Aligne le système avec la philosophie du projet : aider à livrer, pas à reporter sous prétexte d'optimisation.
- Évite le piège classique des outils "intelligents" qui produisent du bruit sous couvert de pertinence technique.
- Force l'utilisateur à expliciter ses objectifs actifs dans la fiche — bénéfice secondaire : il y réfléchit lui-même.
- Double application (prompt + filtre déterministe) garantit la robustesse même si le LLM dérape.

### Trade-off accepté
- Une découverte qui sortirait du cadre des objectifs actifs (mais qui pourrait reformuler ces objectifs) sera filtrée. Conscient et assumé : si un finding est si fort qu'il devrait reformuler les objectifs, il ressortira au prochain run après que l'utilisateur a ajusté la fiche.

---

## 12. Pas de section feedback exploitée au MVP

### Contexte
Idée tentante : permettre à l'utilisateur de commenter chaque suggestion ("trop cher", "déjà essayé", "pas pertinent") pour que le Juge apprenne. Mais cette feature présente des risques.

### Options envisagées
- **Option A** — Section feedback exploitée par le Juge dès le MVP.
- **Option B** — Section feedback affichée mais non exploitée (cosmetic).
- **Option C** — Pas de section feedback du tout au MVP.

### Décision retenue
**Option C.**

### Justification
- **Risques cumulés inacceptables au MVP** :
  - *Pollution du contexte* — feedbacks accumulés sur de nombreux runs grossissent le prompt sans contrôle, dégradent les performances LLM en local.
  - *Cascade incontrôlable* — un feedback mal interprété par le Juge influence tous les runs suivants, et il devient difficile de remonter à la cause d'une dérive.
  - *Debug difficile* — distinguer une mauvaise suggestion due à un mauvais prompt d'une mauvaise suggestion due à un feedback antérieur mal calibré est très coûteux.
- Pas de fonctionnalité morte (Option B) — afficher quelque chose d'inutile dégrade la perception de qualité.
- Backlog : la feature reviendra avec un design propre (l'Historien la portera).

### Trade-off accepté
- L'utilisateur ne peut pas "apprendre" au système ses préférences au MVP. Mitigé par : il peut éditer la fiche projet, qui reste la source de vérité.

---

## 13. Modification du `.md` via l'Interviewer en mode "integrate"

### Contexte
Quand une suggestion est validée par l'utilisateur, il faut modifier le `.md`. Qui le fait ? Un nouveau module dédié ? Le Rapporteur ? L'Interviewer ?

### Options envisagées
- **Option A** — Module dédié de modification du `.md`.
- **Option B** — Le Rapporteur modifie directement.
- **Option C** — L'Interviewer en mode "integrate suggestion" reçoit l'objet `ValidatedSuggestion` et modifie le `.md`.

### Décision retenue
**Option C.**

### Justification
- **Élégance architecturale** : l'Interviewer est déjà le seul module qui sait construire un `.md` valide passant les trois couches de validation. Réutiliser ce module garantit que toute modification respecte les mêmes invariants que la création initiale.
- **Point unique de validation** : un seul endroit dans le code valide un `.md`. Pas de duplication, pas de divergence possible entre "création" et "modification".
- **Pas de duplication** des prompts de génération de `.md`.
- **Cohérence narrative** : l'Interviewer dialogue déjà avec l'utilisateur, il est le bon agent pour clarifier les `open_questions` d'une `ValidatedSuggestion`.

### Trade-off accepté
- L'Interviewer devient un module à deux modes (`create` + `integrate`) — accepté, c'est un découplage logique propre.
- Coût d'un appel LLM supplémentaire à chaque modification (couche 2 de validation incluse) — accepté, la qualité de la fiche projet prime.

---

## 14. Mode local seul exposé au MVP, multi-provider en V2

### Contexte
Le code est structurellement hot-swappable (cf. décision 2). Faut-il exposer plusieurs providers dès le MVP ou un seul ?

### Options envisagées
- **Option A** — Un seul mode exposé et documenté (`local` via Ollama).
- **Option B** — Deux modes exposés (`local`, `hybrid`).

### Décision retenue
**Option A** au MVP. La V2 ajoutera **un seul** mode supplémentaire :
- `hybrid` : Interview toujours en local (contrainte fondamentale non négociable, cf. §1) + agents de veille en API cloud avec accord explicite de l'utilisateur.

Un mode `full_api` (Interview en API) a été envisagé mais explicitement écarté : il contredirait la contrainte fondamentale n°1 ("Interview exclusivement local"). L'Interview ingère les données les plus sensibles du projet et ne quittera jamais la machine.

### Justification
- **Discipline MVP** : maintenir, tester et documenter trois modes au MVP triplerait la charge. On préfère un mode parfait à trois modes médiocres.
- **Cohérence avec l'identité du projet** : le pitch principal, c'est le local. Sortir au MVP avec "et puis y a aussi un mode API" dilue le message.
- **Le code reste prêt** : la fonction `get_llm()` accepte déjà n'importe quel provider, la transition V2 sera principalement de la doc et des tests.
- Sécurité : les clés API (V2) seront référencées via variables d'environnement uniquement, jamais en dur dans la config.

### Trade-off accepté
- Utilisateurs qui voudraient tester avec un Claude ou un GPT-5 dès le MVP devront patcher le code — assumé, ce ne sont pas les utilisateurs cibles du MVP.

---

## 15. TUI Rich plutôt que web app au MVP

### Contexte
Comment l'utilisateur interagit-il avec l'agent ? Terminal, web, app desktop ?

### Options envisagées
- **Option A** — TUI avec Rich (terminal interactif).
- **Option B** — TUI avec Textual (terminal full-screen).
- **Option C** — Web app (Flask/FastAPI + frontend).
- **Option D** — App desktop native.

### Décision retenue
**Option A — TUI Rich.**

L'affichage du rapport final passe par une **ouverture automatique en HTML rendu dans le navigateur** (conversion `markdown2` ou `mistune` + template HTML simple), en parallèle du TUI qui prompt `Valider rapport (Y/N)`.

### Justification
- **Coût d'implémentation faible** : Rich est déjà l'outil standard Python pour ce type d'interaction.
- **Cohérence avec le public cible** : ingénieurs, développeurs, étudiants techniques — tous habitués au terminal.
- **Pas de stack web à maintenir** : un projet web ajoute un serveur, des routes, du frontend, des CORS — toute une couche que le MVP n'a pas besoin de porter.
- **Rapport en HTML dans le navigateur** : meilleure expérience de lecture pour le rapport final, sans imposer une UI web pour le reste.
- Textual (Option B) : surdimensionné pour le besoin, ajoute une dépendance lourde.
- Web app (Option C) : ira en backlog, mais pas avant que le cœur soit solide.

### Trade-off accepté
- Pas d'expérience visuelle riche pendant l'interview elle-même — assumé, le contenu prime sur la forme à ce stade.
- Pas accessible à des utilisateurs non techniques — assumé, ce n'est pas le public MVP.

---

## 16. Rapport en HTML dans le navigateur + validation TUI

### Contexte
Le rapport final est l'artefact que l'utilisateur consulte. Comment le présenter pour qu'il soit à la fois agréable à lire et exploitable pour la validation ?

### Options envisagées
- **Option A** — Rapport en Markdown brut dans le terminal.
- **Option B** — Rapport en HTML rendu, ouvert dans le navigateur, validation dans le terminal.
- **Option C** — Tout en TUI Rich (rendu Markdown + validation).

### Décision retenue
**Option B.**

Pipeline : le Rapporteur produit un Markdown → conversion en HTML via `markdown2` ou `mistune` → ouverture automatique dans le navigateur par défaut → en parallèle, le TUI prompt `Valider rapport (Y/N)`.

Si `Y` : lance la séquence de validation des suggestions une par une via l'Interviewer en mode "integrate".

### Justification
- Le rapport final mérite une présentation soignée (lien narratif avec le storytelling portfolio).
- L'utilisateur peut faire défiler tranquillement dans son navigateur pendant qu'il décide.
- Le terminal reste l'endroit de la validation et de l'interaction — séparation propre lecture/action.

### Trade-off accepté
- Dépendance au navigateur par défaut — mitigée par fallback Markdown brut si l'ouverture échoue.
- Léger délai à l'ouverture — négligeable.

---

## 17. Communication inter-agents par JSON Pydantic + retry

### Contexte
Les agents s'échangent des données structurées (Findings, Verdicts, Suggestions). Format ?

### Options envisagées
- **Option A** — Markdown libre entre agents.
- **Option B** — JSON validé par Pydantic, retry sur erreur de parsing.
- **Option C** — Function calling natif du LLM.

### Décision retenue
**Option B.** Le Markdown libre n'est utilisé que pour la sortie utilisateur finale (rapport).

### Justification
- Robustesse : Pydantic + retry attrape les hallucinations de structure.
- Auditabilité : chaque artefact intermédiaire est sérialisé proprement dans `runs/[timestamp]_[projet]/`.
- Function calling (Option C) varie selon le provider — incompatible avec l'objectif hot-swap.
- Markdown libre (Option A) est trop fragile pour l'orchestration interne.

### Trade-off accepté
- Coût d'un retry occasionnel quand le LLM produit un JSON malformé — l'objectif du MVP est < 5% de retries.

---

## 18. LangFuse self-hosted comme outil dev (optionnel)

### Contexte
Pendant le développement, on veut pouvoir inspecter les traces LLM (prompts, latences, tokens, erreurs) pour debugger.

### Options envisagées
- **Option A** — Logs Python custom.
- **Option B** — LangSmith hébergé (cloud).
- **Option C** — LangFuse self-hosted (Docker, local).

### Décision retenue
**Option C** recommandé pour le développement, **Option B** acceptable pour usage perso uniquement (gratuit jusqu'à un certain volume).

L'utilisateur final n'a pas besoin de l'un ou l'autre — c'est strictement un outil de dev, optionnel.

### Justification
- Cohérence avec la philosophie locale : LangFuse self-hosted = aucune fuite de traces.
- Gratuit, Docker compose en quelques minutes.
- LangSmith est accepté pour usage perso si l'utilisateur préfère le confort cloud — son projet perso n'a pas la sensibilité d'un projet R&D client.

### Trade-off accepté
- Setup Docker pour LangFuse — accepté, c'est une étape unique.

---

## 19. Mécanique d'interview : enrichissement assisté plutôt que validateur strict

### Contexte
La conception initiale du module Interview prévoyait un LLM jouant le rôle de validateur strict : à chaque réponse texte libre, le LLM rendait un verdict binaire `OK / REJECT` et bouclait jusqu'à deux relances de clarification en cas de rejet. Ce design a été testé et soulevait deux problèmes UX :
- L'utilisateur ressentait l'interview comme un examen ("ta réponse est rejetée, recommence").
- Sur les questions où la réponse initiale était techniquement valide mais simplement courte, le LLM générait des relances superflues.

### Options envisagées
- **Option A** — Garder le validateur strict, ajuster les prompts pour réduire les faux rejets.
- **Option B** — Remplacer par un système d'enrichissement : la réponse est acceptée d'office, le LLM propose **une seule** question de précision optionnelle avec un mot-clé `skip` pour conserver la réponse initiale.
- **Option C** — Supprimer toute assistance LLM en mode interview, ne garder que les pré-checks regex.

### Décision retenue
**Option B**.

La réponse initiale est toujours acceptée. Le LLM est repositionné comme assistant, pas comme juge — il propose une précision, l'utilisateur peut taper `skip` pour passer. Sur les sections critiques (Description, Objectifs, Contraintes), le `skip` est bloqué uniquement si la réponse initiale est manifestement insuffisante (< 4 mots ET aucun indicateur technique).

### Justification
- **Cohérence philosophique** : "l'agent ne décide jamais à votre place" implique que le LLM ne doit pas rejeter les réponses humaines, juste suggérer.
- **Préservation du signal** : les pré-checks regex déterministes (chiffres+unités, sigles techniques connus) capturent les ~80 % des cas évidents sans appel LLM. Le LLM n'intervient que sur les cas verbalement longs mais techniquement vides.
- **Skip bloqué = garde-fou ciblé** : empêche un utilisateur de générer une fiche projet inutilisable pour le pipeline de veille (description vide → 0 finding aligné).
- **Filet de sécurité aval** : le récap+correction post-questionnaire (voir Jalon 1bis dans `ROADMAP_MVP.md`) permet de revenir corriger n'importe quel champ avant la sauvegarde finale.

### Trade-off accepté
- Qualité moyenne légèrement inférieure sur les utilisateurs déterminés à minimiser leur effort (skip répété → fiche moins riche).
- Mitigation : récap final + skip bloqué sur sections critiques + alignement téléologique en aval qui rejette les findings non alignés.

---

## 20. Suppression de l'abstraction "profile small/medium/large" et choix de modèles par rôle

### Contexte
La conception initiale (cf. CLAUDE.md règle 3 d'origine) prévoyait trois profils matériels : `small` (7B Q4 partout), `medium` (14B Q4), `large` (32B Q4). Chaque profil mappait UN modèle pour TOUS les agents. L'évaluation Jalon 8 (cf. `docs/evaluations/modeles_perf_2026-05-13.md`) a montré que ce mapping est mauvais : un Juge a besoin de plus d'intelligence qu'un Rapporteur, indépendamment du hardware.

### Mesures qui ont forcé cette décision
- Sur RTX 3070 8 GB avec `mistral:7b` partout : 0 % de rejets côté Juge → 71 % de findings non-alignés dans le rapport final.
- Sur RTX 3070 8 GB avec `mistral:7b` partout + `qwen3:8B` au Juge seulement : ~50 % de rejets justifiés, alignement passe à 66-82 % selon les projets.
- `qwen2.5:14b` initialement prévu pour le profil "medium" est obsolète mai 2026 — `qwen3:8B` (plus récent et plus petit) le surpasse sur LLM-as-a-judge (cf. CodeJudgeBench).
- `qwen3.5:9b` ne tient pas en 8 GB VRAM (offload CPU 26 %) — donc inutilisable sur la config de référence.

### Options envisagées
- **Option A** — Garder les 3 profils, mettre à jour la liste de modèles tous les 3 mois.
- **Option B** — Supprimer les profils, garder le hot-swap `get_llm("role", config)` avec mapping par rôle dans `config.yaml`.
- **Option C** — Hardcoder un mapping unique, sans hot-swap.

### Décision retenue
**Option B**.

Suppression de la clé `profile:` dans `config.yaml` et de `_PROFILE_MODELS` dans `src/llm/__init__.py`. Remplacement par un mapping par rôle (`_DEFAULT_MODELS`) avec override possible via `ollama.models.<role>` dans `config.yaml`. Création de `docs/HARDWARE.md` qui documente les variantes selon le matériel ("si tu as ≥ 12 GB VRAM, upgrade le Juge en `qwen3:14b`").

### Justification
- **Mesure terrain** : 4 itérations Jalon 8 ont montré que la qualité du jugement (Juge) est ce qui plafonne le système. Optimiser ce maillon en priorité, garder le reste léger.
- **Maintenance** : maintenir 3 profils × 5 rôles = 15 cases à valider à chaque release de modèle, contre 5 (1 par rôle). L'abstraction par hardware déduit mal du modèle optimal.
- **Honnêteté avec l'utilisateur** : un profil "medium" abstrait fait promesse vague. Un mapping nommé (`juge: qwen3:8B`) est testable et reproductible.
- **Économie tokens** : ne payer la grosse latence (qwen3:8B = 14 s/call) que sur le seul agent qui en bénéficie. Mistral 7B reste partout ailleurs (6.5 s/call).

### Trade-off accepté
- Légère complexité supplémentaire dans `config.yaml` (4 lignes au lieu d'une `profile: small`).
- Mitigé par `docs/HARDWARE.md` qui pré-mâche les variantes courantes.

---

## Synthèse — décisions structurantes en une page

| # | Décision | Caractère |
|---|----------|-----------|
| 1 | Tout en local par défaut (Interview local au MVP, cloud opt-in en V2 sur choix explicite) | Non négociable au MVP |
| 2 | Hot-swappable LLM via abstraction `get_llm()` | Non négociable |
| 3 | ~~Trois profiles hardware~~ → Mapping par rôle (cf. §20) | Architecture |
| 4 | Format `.md` strict à deux étages | Non négociable |
| 5 | Validation 3 couches symétriques création / modification | Architecture |
| 6 | LangGraph comme framework d'orchestration | Architecture |
| 7 | 4 agents LLM + graphe Chef + Historien en backlog | Architecture |
| 8 | 4 sources MVP, pas de scraping | Périmètre |
| 9 | Mode incrémental dès le MVP | Périmètre |
| 10 | Filtrage déterministe en amont du LLM | Architecture |
| 11 | Alignement téléologique avec objectifs actifs | Design fondamental |
| 12 | Pas de section feedback exploitée au MVP | Périmètre |
| 13 | Modification du `.md` via Interviewer mode integrate | Architecture |
| 14 | Mode local seul exposé au MVP | Périmètre |
| 15 | TUI Rich + rapport HTML navigateur | UX |
| 16 | Rapport en HTML dans navigateur + validation TUI | UX |
| 17 | Communication JSON Pydantic + retry | Architecture |
| 18 | LangFuse self-hosted optionnel | Outil dev |
| 19 | Enrichissement assisté plutôt que validateur strict en interview | UX / Design |
| 20 | Suppression profils, mapping modèle par rôle (qwen3:8B pour Juge) | Architecture |
