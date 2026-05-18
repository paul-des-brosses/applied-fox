"""
Rendu Markdown → HTML pour le rapport final Applied Fox.

Utilise mistune (parser Markdown rapide et stable) + un template HTML
autonome avec CSS inline. Le fichier HTML produit s'ouvre dans n'importe
quel navigateur sans dépendance externe.
"""

from __future__ import annotations

from pathlib import Path

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #222;
            max-width: 880px;
            margin: 2rem auto;
            padding: 0 1.5rem;
            background: #fafafa;
        }}
        h1 {{ color: #1a1a1a; border-bottom: 3px solid #2563eb; padding-bottom: 0.4em; }}
        h2 {{
            color: #1a1a1a;
            border-bottom: 1px solid #d1d5db;
            padding-bottom: 0.3em;
            margin-top: 2.2em;
        }}
        h3 {{ color: #2563eb; margin-top: 1.6em; }}
        h4 {{ color: #444; margin-top: 1.2em; margin-bottom: 0.4em; }}
        a {{ color: #2563eb; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        code {{
            background: #eef2f7;
            padding: 0.15em 0.4em;
            border-radius: 3px;
            font-size: 0.92em;
            font-family: "SF Mono", Consolas, "Liberation Mono", monospace;
        }}
        pre {{
            background: #1f2937;
            color: #e5e7eb;
            padding: 1em;
            border-radius: 6px;
            overflow-x: auto;
        }}
        pre code {{ background: transparent; color: inherit; padding: 0; }}
        blockquote {{
            border-left: 4px solid #2563eb;
            background: #eef2ff;
            margin: 1em 0;
            padding: 0.6em 1em;
            color: #1e3a8a;
        }}
        ul, ol {{ padding-left: 1.5em; }}
        li {{ margin: 0.25em 0; }}
        em {{ color: #6b7280; }}
        hr {{
            border: none;
            border-top: 1px solid #d1d5db;
            margin: 2em 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        th, td {{
            border: 1px solid #d1d5db;
            padding: 0.5em 0.8em;
            text-align: left;
        }}
        th {{ background: #f3f4f6; }}
        .meta {{
            color: #6b7280;
            font-size: 0.92em;
            font-style: italic;
            margin-bottom: 1.5em;
        }}
    </style>
</head>
<body>
{body}
</body>
</html>
"""


def markdown_to_html(markdown_text: str, project_name: str = "Applied Fox") -> str:
    """
    Convertit un rapport Markdown en HTML autonome avec CSS inline.

    Args:
        markdown_text: contenu Markdown brut produit par le Rapporteur.
        project_name: nom du projet (utilisé dans le <title> HTML).

    Returns:
        String HTML complète, prête à être écrite sur disque.

    Raises:
        ImportError si mistune n'est pas installé (devrait être dans pyproject.toml).
    """
    import mistune

    body_html = mistune.html(markdown_text)
    return _HTML_TEMPLATE.format(
        title=f"Rapport de veille — {project_name}",
        body=body_html,
    )


def save_html_report(
    markdown_text: str,
    output_path: Path,
    project_name: str = "Applied Fox",
) -> Path:
    """
    Sauvegarde le rapport HTML sur disque.

    Args:
        markdown_text: contenu Markdown du rapport.
        output_path: chemin du fichier HTML à écrire (créé si nécessaire).
        project_name: nom du projet pour le <title>.

    Returns:
        Le chemin absolu du fichier HTML écrit.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = markdown_to_html(markdown_text, project_name=project_name)
    output_path.write_text(html, encoding="utf-8")
    return output_path.resolve()
