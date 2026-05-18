"""
Module Interview — Dialogue guidé pour la création et la mise à jour des fiches projet.

Ce module est le seul point d'entrée pour produire ou modifier un fichier .md projet.
Il encapsule les trois modes : create, update, integrate.

Délègue l'implémentation à :
    src/agents/interviewer.py    — logique LLM et prompts
    src/validation/             — 3 couches de validation

Implémentation : Jalon 1 (create) et Jalon 2 (update + integrate).
"""
