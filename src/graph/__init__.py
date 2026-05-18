"""
Module Graph — Définition du graphe LangGraph et de l'état partagé.

Contenu :
    state.py  — TechWatchState, type partagé entre tous les nœuds du graphe.
    graph.py  — définition des nœuds, edges, et branchements conditionnels.

Le graphe orchestre : Éclaireur → Intégrateur (|| par finding) → Juge → Rapporteur.
Branchement conditionnel clé : si IntegrationVerdict.integrable == False,
le finding saute le nœud Juge et va directement dans les rejetés du Rapporteur.

Implémentation : Jalon 3 (graphe minimal 1 agent) → Jalon 5 (graphe complet).
"""
