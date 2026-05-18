"""
Module Reporting — Génération et présentation du rapport final.

Responsabilités :
    - Convertir le rapport Markdown produit par le Rapporteur en HTML.
    - Appliquer un template HTML simple pour un rendu propre, autonome.
    - Sauvegarder sur disque et exposer le chemin pour ouverture navigateur.
"""

from __future__ import annotations

from src.reporting.render import markdown_to_html, save_html_report

__all__ = ["markdown_to_html", "save_html_report"]
