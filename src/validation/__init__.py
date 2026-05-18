"""
Module Validation — Les 3 couches de validation du fichier .md projet.

Couche 1 (structural.py)   : règles déterministes, Pydantic + parsers Markdown.
Couche 2 (transmission.py) : test de transmission par LLM tiers (autonomie du .md).
Couche 3 (human.py)        : récap TUI Rich + confirmation explicite de l'utilisateur.

Si une couche échoue, on ne passe PAS à la suivante.
Ce pipeline est appliqué symétriquement à la création ET à la modification.

Implémentation : Jalon 1.
"""
