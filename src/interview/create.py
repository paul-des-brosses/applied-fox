"""
Questionnaire guidé section par section — mode `create` de l'Interviewer.

Principe :
    Le programme pose des questions guidées via TUI Rich. Pour chaque champ
    texte libre, la réponse est d'abord acceptée, puis le LLM propose UNE
    question d'enrichissement optionnelle. L'utilisateur peut taper "skip"
    pour conserver sa réponse initiale telle quelle.

    Le skip est bloqué sur les sections critiques quand la réponse initiale
    est manifestement trop courte (< 4 mots, aucun indicateur technique) —
    pour éviter de générer une fiche inutilisable pour le pipeline.

Mécanique skip (affichée dans le TUI au démarrage) :
    - Toutes les questions d'enrichissement proposent [skip].
    - Taper "skip" conserve la réponse initiale sans modification.
    - Le skip est BLOQUÉ sur Description / Objectifs / Contraintes si la
      réponse initiale est trop vague (< 4 mots sans indicateur technique).
    - Les questions initiales n'acceptent jamais "skip" comme réponse.

Robustesse :
    - Réponses vides → relance immédiate, sans consommer de tentative.
    - "skip" sur question initiale → refusé explicitement.
    - Si Ollama est indisponible → dégradation gracieuse, enrichissement
      désactivé, réponses acceptées sans relance.
    - Post-questionnaire : vérification de cohérence déterministe +
      inférence LLM de composants possiblement oubliés (non-bloquants).

Le .md est généré à la fin du questionnaire, pas question par question.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()


# ─────────────────────────────────────────────────────────────
# Mécanique de navigation back
# ─────────────────────────────────────────────────────────────


class BackRequested(Exception):
    """Levée par les helpers d'input quand l'utilisateur tape 'back'."""


def _navigate_steps(
    steps: list[Callable[[dict], None]],
    data: dict,
    *,
    allow_back_at_start: bool = False,
) -> None:
    """
    Exécute une liste de steps séquentiellement avec support du back.

    Chaque step prend `data` et le modifie en place. Si un step lève
    BackRequested, on revient au step précédent en restaurant l'état
    de `data` à ce qu'il était avant ce step.

    Args:
        allow_back_at_start: Si True, BackRequested au step 0 re-lève
                             pour que l'appelant puisse remonter encore.
                             Si False, on affiche un message et on redemande.
    """
    snapshots: list[dict] = [deepcopy(data)]
    i = 0
    while i < len(steps):
        try:
            steps[i](data)
            i += 1
            snapshots.append(deepcopy(data))
        except BackRequested:
            if i == 0:
                if allow_back_at_start:
                    raise
                console.print("[yellow]Première étape, rien à corriger en arrière.[/yellow]")
            else:
                snapshots.pop()
                i -= 1
                data.clear()
                data.update(snapshots[i])
                console.print("[dim]Retour à la question précédente.[/dim]")


# ─────────────────────────────────────────────────────────────
# Pré-checks déterministes (sans LLM)
# ─────────────────────────────────────────────────────────────

_CONCRETE_REQUIRED_SECTIONS = {
    "Description",
    "Objectifs actifs",
    "Critère de contrainte / valeur",
    "Contrainte non négociable",
    "Contenu attendu rendu",
}

_CONCRETE_INDICATORS = re.compile(
    r"""(?ix)
    (?:
        \d+(?:[\.,]\d+)?\s*
            (?:[µu]A|mA|A|mV|V|kV|W|kW|°C|°F|%|hPa|kPa|Pa|Hz|kHz|MHz|GHz|
               km|m|cm|mm|s|min|h|j|jours?|mois|ans?|€|\$|RH|dB|dBm|bps|
               Mbps|kbps|Mo|Go|Ko|MB|GB|KB|RPM|fps)
    )
    | (?:[<>±]\s*\d)
    | (?:\d+\s*[x×]\s*\d)
    | (?:\b(?:I2C|UART|SPI|USB|HTTP|HTTPS|MQTT|TCP|UDP|JSON|XML|REST|gRPC|
            LoRa|LoRaWAN|BLE|WiFi|Wi-Fi|GSM|GPRS|LTE|5G|4G|3G|GPS|GNSS|RTK|
            NMEA|MIT|GPL|BSD|Apache|ISO|IEC|IEEE|RFC|IP\d+|FCC|CE|RoHS)\b)
    | (?:\b[A-Z]{2,}[\-]?\d+[A-Z\-\d]*\b)
    """,
)

_PURE_TBD_PATTERNS = re.compile(
    r"^\s*(?:tbd|à\s*voir|a\s*voir|je\s*(?:ne\s*)?sais\s*pas|à\s*définir|a\s*definir|à\s*faire|a\s*faire|inconnu|inconnue|sais\s*pas|sp|nsp|\?+)\s*$",
    re.IGNORECASE,
)

_TRIVIAL_PATTERNS = re.compile(
    r"^\s*(?:rien|aucun(?:e)?\s*id[ée]e|bof|ouais|non|oui|peut[-\s]?[êe]tre|euh+|hmm+|\.+|-+)\s*$",
    re.IGNORECASE,
)


def _has_concrete_indicator(text: str) -> bool:
    return bool(_CONCRETE_INDICATORS.search(text))


def _is_pure_tbd(text: str) -> bool:
    return bool(_PURE_TBD_PATTERNS.match(text))


def _is_trivial(text: str) -> bool:
    return bool(_TRIVIAL_PATTERNS.match(text))


def _is_valid_placeholder(text: str) -> bool:
    s = text.strip()
    if re.match(r"^n[/\.]?a\.?$", s, re.IGNORECASE):
        return True
    m = re.match(
        r"^(?:tbd|à\s*voir|a\s*voir|à\s*définir|a\s*definir|à\s*faire|a\s*faire)\s*:\s*(.+)$",
        s,
        re.IGNORECASE,
    )
    if m and len(m.group(1).strip()) >= 4:
        return True
    return False


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _deterministic_accept(section: str, answer: str) -> bool:
    """Court-circuit POSITIF : réponse suffisamment concrète, pas besoin du LLM."""
    s = answer.strip()
    if _is_valid_placeholder(s):
        if section == "Description":
            return False
        return True
    if _has_concrete_indicator(s) and _word_count(s) >= 2:
        if section == "Description" and _word_count(s) < 6:
            return False
        return True
    return False


def _skip_should_be_blocked(section: str, answer: str) -> bool:
    """
    True si le skip doit être bloqué sur la question d'enrichissement.

    Bloqué quand la réponse initiale est manifestement insuffisante
    ET que la section est critique pour le pipeline de veille.
    Évite de persister une fiche inutilisable.
    """
    s = answer.strip()
    if section in _CONCRETE_REQUIRED_SECTIONS:
        if _word_count(s) < 4 and not _has_concrete_indicator(s):
            return True
    if section == "Description" and _word_count(s) < 5:
        return True
    return False


# ─────────────────────────────────────────────────────────────
# Helpers UI
# ─────────────────────────────────────────────────────────────


def _section_header(title: str, hint: str = "") -> None:
    content = f"[bold]{title}[/bold]"
    if hint:
        content += f"\n[dim]{hint}[/dim]"
    content += "\n[dim]Tape [bold]back[/bold] pour revenir à la question précédente.[/dim]"
    console.print()
    console.print(Panel.fit(content, border_style="cyan"))


def _ask(question: str, default: str = "", allow_back: bool = True) -> str:
    """
    Helper Prompt.ask avec reconnaissance du mot-clé 'back'.

    Si allow_back=True (défaut) et que l'utilisateur tape 'back',
    lève BackRequested pour signaler la demande de retour arrière.
    Mettre allow_back=False sur les questions où le back n'a pas de sens
    (ex. dernière question d'un récap, choix Oui/Non simples).
    """
    val = Prompt.ask(question, default=default) if default else Prompt.ask(question)
    if allow_back and val.strip().lower() == "back":
        raise BackRequested()
    return val


def _choose(question: str, choices: list[str], default: str = "") -> str:
    """Choix multiple numéroté — l'utilisateur tape 1, 2, 3…"""
    default_choice = default if default in choices else choices[0]
    console.print(f"\n{question}")
    for i, c in enumerate(choices, 1):
        suffix = " [dim](défaut)[/dim]" if c == default_choice else ""
        console.print(f"  [cyan]{i}.[/cyan] {c}{suffix}")
    default_idx = str(choices.index(default_choice) + 1)
    while True:
        raw = Prompt.ask("→", default=default_idx).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        # Tolérance : l'utilisateur tape le texte directement
        if raw in choices:
            return raw
        console.print(f"[red]Tape un chiffre entre 1 et {len(choices)}.[/red]")


# ─────────────────────────────────────────────────────────────
# Système d'enrichissement LLM (remplace le système VERDICT)
# ─────────────────────────────────────────────────────────────

_ENRICHMENT_SYSTEM_TEMPLATE = """Tu es un assistant qui aide à compléter une fiche projet technique.
L'utilisateur vient de répondre à une question d'interview.

Section : {section}
Question posée : {question}
Ce qui est attendu pour cette section : {expectations}

Ta tâche : décider si la réponse est suffisante OU proposer UNE courte question de précision.

RÉPONDS "OK" si la réponse contient déjà au moins un élément concret parmi :
- chiffre avec unité (5 mA, 6 mois, ±0.5°C, < 80€)
- sigle ou protocole technique (ESP32, BME280, I2C, LoRa, MQTT, IP65, MIT)
- nom propre concret (Grafana, FastAPI, GitHub, Android)
- état observable (open-source, hors-ligne, certifié CE)
- "N/A" ou "TBD : raison"

POSE UNE QUESTION DE PRÉCISION (max 12 mots) si la réponse est trop générique
(ex. "mesure des données", "composant principal", "système fiable").

FORMAT STRICT — une seule ligne, rien d'autre :
OK
ou
[ta question de précision, max 12 mots, formulée pour l'utilisateur]"""

_SECTION_GUIDES: dict[str, str] = {
    "Description": (
        "Trois axes : (1) fonction technique précise, (2) contexte/utilisateur/environnement, "
        "(3) scope concret (durée, ordres de grandeur). "
        "Acceptable : 'Station météo ESP32 mesurant T°/humidité/pression, LoRaWAN, outdoor 6 mois.' "
        "À rejeter : 'Système qui collecte des données environnementales de manière fiable.'"
    ),
    "Objectifs actifs": (
        "Chiffré et vérifiable : mesure + unité + condition, ou état binaire observable. "
        "Acceptable : 'Tenir 6 mois autonomie LiPo 2000 mAh + solaire 5W'. "
        "À rejeter : 'être performant', 'consommer peu'."
    ),
    "Composant / rôle": (
        "Fonction technique dans le système, avec point d'intégration ou caractéristique distinctive. "
        "Acceptable : 'Microcontrôleur principal + LoRa', 'Capteur T°/humidité I2C'. "
        "À rejeter : 'composant principal', 'le cerveau du système'."
    ),
    "Stack item / rôle": (
        "Ce que l'outil fait concrètement dans le projet. "
        "Acceptable : 'Framework principal FW', 'Stack LoRaWAN'. "
        "À rejeter : 'utilitaire', 'outil de dev'."
    ),
    "Interaction / nature": (
        "Ce qui transite en termes techniques précis. "
        "Acceptable : 'mesures T°/humidité/pression', 'trames NMEA'. "
        "À rejeter : 'données', 'communication', 'échange'."
    ),
    "Critère de contrainte / valeur": (
        "Numérique + unité, état explicite, N/A, ou TBD : raison. "
        "Acceptable : '< 50 µA', 'IP65 minimum', 'N/A : pas de contrainte budget'. "
        "À rejeter : 'élevé', 'faible', 'TBD' seul."
    ),
    "Contrainte non négociable": (
        "Imposée par décision externe (client, certification, stratégie figée). "
        "Doit dire QUI l'impose ou POURQUOI elle est figée. "
        "À rejeter : simples préférences."
    ),
    "Contenu attendu rendu": (
        "Artefacts concrets livrables le jour J, avec métrique si possible. "
        "Acceptable : 'Prototype fonctionnel + 1 mois de données visualisées'. "
        "À rejeter : 'présentation du projet'."
    ),
}


def _get_enrichment_question(
    llm,
    project_name: str,
    section: str,
    question: str,
    answer: str,
    expectations: str,
) -> Optional[str]:
    """
    Demande au LLM si l'enrichissement est utile.

    Returns:
        None si la réponse est suffisante (LLM dit OK).
        Une question de précision courte sinon.
        None si le LLM est indisponible (dégradation gracieuse).
    """
    if llm is None:
        return None
    try:
        sys_prompt = _ENRICHMENT_SYSTEM_TEMPLATE.format(
            section=section,
            question=question,
            expectations=expectations or "(pas de guide spécifique)",
        )
        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(
                content=f"Projet : {project_name}\nRéponse de l'utilisateur :\n{answer}"
            ),
        ]
        resp = llm.invoke(messages)
        content = resp.content.strip()

        # Détection OK (variantes tolérées)
        first_line = content.splitlines()[0].strip() if content else ""
        if re.match(r"^ok[.!]?$", first_line, re.IGNORECASE):
            return None
        if re.search(r"\bla\s+r[ée]ponse\s+est\s+(?:suffisante|acceptable|correcte|bonne)\b", content, re.IGNORECASE):
            return None

        # Retourne la première ligne non-vide comme question de précision
        question_out = first_line[:200] if first_line else None
        # Retire les préfixes parasites éventuels
        for pfx in ("→", "-", "*", "•", "Question :", "Précision :"):
            if question_out and question_out.startswith(pfx):
                question_out = question_out[len(pfx):].strip()
        return question_out or None

    except Exception:
        return None  # LLM indisponible → dégradation gracieuse


def _ask_with_enrichment(
    llm,
    project_name: str,
    section: str,
    question: str,
    expectations: Optional[str] = None,
    allow_skip: bool = False,
) -> str:
    """
    Pose une question initiale, accepte la réponse, puis propose UNE question
    d'enrichissement optionnelle.

    Args:
        allow_skip: Si True, accepte "skip" comme réponse valide qui retourne
                    immédiatement la chaîne "skip". Utilisé en mode update
                    pour permettre à l'utilisateur de conserver une valeur
                    existante sans avoir à la recopier ni à répondre aux
                    questions de précision.

    Comportement :
        - Réponse vide → relance immédiate (sans LLM).
        - "skip" sur question initiale :
            - Si allow_skip=False → refusé avec message explicite.
            - Si allow_skip=True → retourne "skip" immédiatement.
        - Réponse déterministement bonne → pas d'enrichissement LLM.
        - LLM dit OK → pas d'enrichissement.
        - LLM propose une question → affichée avec [skip] si autorisé.
        - Enrichissement pré-rempli avec la réponse initiale (l'utilisateur édite).
        - Si skip et skip_blocked → rappel et nouvelle demande.

    Returns:
        La réponse finale (initiale ou enrichie), ou "skip" si allow_skip=True
        et l'utilisateur a tapé skip sur la question initiale.
    """
    # ── Question initiale ───────────────────────────────────────
    while True:
        # _ask peut lever BackRequested → laissée remonter à l'appelant
        answer = _ask(question)

        if not answer.strip():
            console.print("[yellow]Réponse vide — donne au moins quelques mots.[/yellow]")
            continue

        # "skip" sur question initiale : accepté si allow_skip=True (mode update)
        if answer.strip().lower() == "skip":
            if allow_skip:
                return "skip"
            console.print(
                "[yellow]Cette question est obligatoire. "
                "Le skip est disponible uniquement sur les questions de précision.[/yellow]"
            )
            continue

        break

    # ── Vérification déterministe rapide ────────────────────────
    if _deterministic_accept(section, answer):
        return answer

    # ── Pas de LLM → on accepte tel quel ────────────────────────
    if llm is None:
        return answer

    # ── Enrichissement LLM ──────────────────────────────────────
    with console.status("[dim]Analyse de la réponse…[/dim]", spinner="dots"):
        enrichment_q = _get_enrichment_question(
            llm, project_name, section, question, answer,
            expectations or _SECTION_GUIDES.get(section, ""),
        )

    if enrichment_q is None:
        return answer  # LLM satisfait

    # Détermine si le skip est bloqué
    blocked = _skip_should_be_blocked(section, answer)

    if blocked:
        console.print(
            f"[yellow italic]Pour préciser "
            f"[bold](requis — réponse trop vague)[/bold] :[/yellow italic] {enrichment_q}"
        )
    else:
        console.print(
            f"[yellow italic]Pour préciser "
            f"[dim](ou tape [bold]skip[/bold] pour conserver ta réponse)[/dim] :[/yellow italic] "
            f"{enrichment_q}"
        )

    # Pré-remplit avec la réponse initiale pour édition en place
    enriched = Prompt.ask("→", default=answer)

    if enriched.strip().lower() == "skip":
        if blocked:
            console.print(
                "[red]Skip non disponible ici — ta réponse est trop courte "
                "pour que la veille soit utile. Précise avec un chiffre ou un nom technique.[/red]"
            )
            # Une dernière chance sans pré-remplissage
            enriched = _ask(enrichment_q)
            if not enriched.strip() or enriched.strip().lower() == "skip":
                return answer  # On accepte quand même après insistance
        else:
            return answer  # Skip accepté → réponse initiale conservée

    if not enriched.strip() or enriched.strip() == answer.strip():
        return answer

    return enriched


# ─────────────────────────────────────────────────────────────
# Vérifications post-questionnaire
# ─────────────────────────────────────────────────────────────


def _consistency_check(data: dict) -> list[str]:
    """
    Vérification déterministe de cohérence interne (sans LLM).

    Vérifie :
    1. Composants orphelins (déclarés mais absents de toute interaction).
    2. Interactions fantômes (référencent un nom inconnu des composants/stack).

    Utilise du substring matching case-insensitive pour absorber les
    variations de casse et de formulation (ESP32 vs ESP32-WROOM-32E).
    """
    warnings: list[str] = []

    known_names = [c["nom"].lower() for c in data.get("composants", [])]
    known_names += [s["outil"].lower() for s in data.get("stack", [])]

    interactions = data.get("interactions", [])

    # 1. Composants orphelins
    for comp in data.get("composants", []):
        name_lower = comp["nom"].lower()
        in_interaction = any(
            name_lower in (i.get("source", "") + " " + i.get("target", "")).lower()
            for i in interactions
        )
        # Tolérance inverse : l'interaction mentionne un sous-nom du composant
        if not in_interaction:
            words = [w for w in re.findall(r"\w+", name_lower) if len(w) > 3]
            in_interaction = any(
                any(w in (i.get("source", "") + " " + i.get("target", "")).lower() for w in words)
                for i in interactions
            )
        if not in_interaction and interactions:
            warnings.append(
                f"'{comp['nom']}' est déclaré dans les composants mais n'apparaît "
                f"dans aucune interaction — oublié de câbler ?"
            )

    # 2. Interactions fantômes
    for inter in interactions:
        for role in ("source", "target"):
            ref = inter.get(role, "").lower()
            if not ref:
                continue
            known = any(
                n in ref or ref in n or
                any(w in ref for w in re.findall(r"\w+", n) if len(w) > 3)
                for n in known_names
            )
            if not known:
                warnings.append(
                    f"Interaction : '{inter.get(role, '')}' non reconnu dans "
                    f"les composants ou la stack."
                )

    return warnings


def _infer_missing_components(data: dict, llm) -> list[str]:
    """
    Appel LLM unique post-questionnaire pour détecter des composants
    possiblement oubliés au vu de la description et des objectifs.

    Non-bloquant : suggestions uniquement, jamais d'obligation.
    Graceful degradation si LLM indisponible.

    Returns:
        Liste de suggestions au format "Nom : raison courte".
    """
    if llm is None:
        return []

    component_names = [c["nom"] for c in data.get("composants", [])]
    stack_names = [s["outil"] for s in data.get("stack", [])]
    objectives = data.get("objectifs", [])

    prompt = (
        f"Projet : {data.get('nom_projet', '')}\n"
        f"Description : {data.get('description', '')}\n"
        f"Objectifs : {'; '.join(objectives)}\n"
        f"Composants déclarés : {', '.join(component_names)}\n"
        f"Stack logicielle : {', '.join(stack_names)}\n\n"
        "En te basant UNIQUEMENT sur la description et les objectifs, "
        "y a-t-il des composants matériels évidents qui semblent manquants ?\n"
        "Ne suggère QUE si tu es très confiant (> 90%). Maximum 3 suggestions.\n"
        "Si rien de flagrant, réponds uniquement : RIEN\n\n"
        "FORMAT STRICT :\n"
        "RIEN\n"
        "ou\n"
        "- [Nom composant] : [raison en max 10 mots]\n"
        "- [Nom composant] : [raison en max 10 mots]"
    )

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        content = resp.content.strip()

        if re.match(r"^rien[.!]?$", content.splitlines()[0].strip(), re.IGNORECASE):
            return []

        suggestions = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- "):
                suggestions.append(line[2:])
        return suggestions[:3]

    except Exception:
        return []


def _show_post_checks(data: dict, llm) -> None:
    """
    Affiche le récap post-questionnaire avec les vérifications de cohérence
    et les suggestions de composants manquants.

    Entièrement non-bloquant : l'utilisateur peut ignorer toutes les alertes.
    """
    console.print()

    # Vérification déterministe (instantanée)
    det_warnings = _consistency_check(data)

    # Inférence LLM (peut prendre quelques secondes)
    llm_suggestions: list[str] = []
    if llm is not None:
        with console.status(
            "[dim]Vérification finale de cohérence…[/dim]", spinner="dots"
        ):
            llm_suggestions = _infer_missing_components(data, llm)

    if not det_warnings and not llm_suggestions:
        console.print("[green]✓ Aucune incohérence détectée.[/green]")
        return

    lines = []
    for w in det_warnings:
        lines.append(f"  [yellow]⚠[/yellow] {w}")
    for s in llm_suggestions:
        lines.append(f"  [yellow]⚠[/yellow] Composant possiblement oublié : {s}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[yellow bold]Points à vérifier[/yellow bold]",
            border_style="yellow",
            subtitle="[dim]Non-bloquant — tu peux relancer l'interview pour corriger[/dim]",
        )
    )


# ─────────────────────────────────────────────────────────────
# Récapitulatif + correction avant sauvegarde
# ─────────────────────────────────────────────────────────────


def _ask_nonempty(question: str, default: str = "") -> str:
    """Pose une question et refuse les réponses vides ou 'skip'."""
    while True:
        val = _ask(question, default=default)
        if val.strip() and val.strip().lower() != "skip":
            return val
        console.print("[yellow]Cette valeur est obligatoire.[/yellow]")


def _edit_rendu_date(data: dict) -> None:
    import re as _re
    while True:
        val = _ask(
            "Date du prochain rendu (YYYY-MM-DD ou N/A)",
            default=data["prochain_rendu"]["date"],
        )
        if val.lower() == "n/a":
            data["prochain_rendu"].update(
                {"date": "N/A", "nature": "N/A", "contenu_attendu": "N/A"}
            )
            return
        if _re.match(r"^\d{4}-\d{2}-\d{2}$", val):
            data["prochain_rendu"]["date"] = val
            return
        console.print("[red]Format invalide — YYYY-MM-DD ou N/A.[/red]")


def _edit_composant(data: dict, idx: int) -> None:
    comp = data["composants"][idx]
    console.print(f"\n[bold]Édition : {comp['nom']}[/bold]")
    nom_c = _ask_nonempty("Nom du composant", default=comp["nom"])
    role_c = _ask("Rôle technique", default=comp["role"])
    if not role_c.strip() or role_c.strip().lower() == "skip":
        role_c = comp["role"]
    statut_c = _choose(
        "Statut décisionnel",
        ["figé", "validé", "en évaluation"],
        default=comp["statut_decisionnel"],
    )
    pipeline_c = _choose(
        "Rôle pipeline",
        ["critique", "support", "accessoire"],
        default=comp["role_pipeline"],
    )
    data["composants"][idx] = {
        "nom": nom_c, "role": role_c,
        "statut_decisionnel": statut_c, "role_pipeline": pipeline_c,
    }


def _edit_stack_item(data: dict, idx: int) -> None:
    s = data["stack"][idx]
    console.print(f"\n[bold]Édition : {s['outil']}[/bold]")
    outil_s = _ask_nonempty("Nom de l'outil", default=s["outil"])
    role_s = _ask("Rôle", default=s["role"])
    if not role_s.strip() or role_s.strip().lower() == "skip":
        role_s = s["role"]
    version_s = _ask("Version", default=s["version"])
    if not version_s.strip() or version_s.strip().lower() == "skip":
        version_s = s["version"]
    statut_s = _choose(
        "Statut décisionnel",
        ["figé", "validé", "en évaluation"],
        default=s["statut_decisionnel"],
    )
    data["stack"][idx] = {
        "outil": outil_s, "role": role_s,
        "version": version_s, "statut_decisionnel": statut_s,
    }


def _edit_interaction(data: dict, idx: int) -> None:
    inter = data["interactions"][idx]
    console.print(f"\n[bold]Édition : interaction {idx + 1}[/bold]")
    src = _ask("Source", default=inter["source"])
    if not src.strip() or src.strip().lower() == "skip":
        src = inter["source"]
    tgt = _ask("Cible", default=inter["target"])
    if not tgt.strip() or tgt.strip().lower() == "skip":
        tgt = inter["target"]
    nat = _ask("Nature", default=inter["nature"])
    if not nat.strip() or nat.strip().lower() == "skip":
        nat = inter["nature"]
    fmt = _ask("Format / protocole", default=inter.get("format") or "")
    vol = _ask("Volume / fréquence", default=inter.get("volume") or "")
    data["interactions"][idx] = {
        "source": src, "target": tgt, "nature": nat,
        "format": fmt or None, "volume": vol or None,
    }


def _edit_critere(data: dict, section_idx: int, critere_idx: int) -> None:
    section = data["contraintes"][section_idx]
    crit = section["criteres"][critere_idx]
    console.print(f"\n[bold]Édition : {section['titre']} — {crit['nom']}[/bold]")
    nom_cr = _ask("Nom du critère", default=crit["nom"])
    if not nom_cr.strip() or nom_cr.strip().lower() == "skip":
        nom_cr = crit["nom"]
    val_cr = _ask("Valeur", default=crit["valeur"])
    if not val_cr.strip() or val_cr.strip().lower() == "skip":
        val_cr = crit["valeur"]
    data["contraintes"][section_idx]["criteres"][critere_idx] = {
        "nom": nom_cr, "valeur": val_cr,
    }


def _build_review_items(data: dict) -> list[dict]:
    """
    Construit la liste aplatie des champs affichables et modifiables.
    Reconstruite à chaque affichage pour refléter les corrections en cours.

    Chaque item : {section, label, value, type, ...indices pour dispatch}.
    """
    items: list[dict] = []

    def add(section, label, value, **kw):
        items.append({"section": section, "label": label, "value": value, **kw})

    # Identité
    add("IDENTITÉ", "Nom du projet", data["nom_projet"], type="nom_projet")
    add("IDENTITÉ", "Phase", data["phase"], type="phase")
    add("IDENTITÉ", "Domaine", data["domaine"], type="domaine")

    # Description (tronquée à l'affichage)
    desc = data["description"]
    add("DESCRIPTION", "Description",
        desc[:80] + ("…" if len(desc) > 80 else ""), type="description")

    # Objectifs
    for i, obj in enumerate(data["objectifs"]):
        add("OBJECTIFS", f"Objectif {i + 1}", obj, type="objectif", idx=i)

    # Prochain rendu
    add("PROCHAIN RENDU", "Date", data["prochain_rendu"]["date"], type="rendu_date")
    if data["prochain_rendu"]["date"] != "N/A":
        add("PROCHAIN RENDU", "Nature", data["prochain_rendu"]["nature"], type="rendu_nature")
        ca = data["prochain_rendu"]["contenu_attendu"]
        add("PROCHAIN RENDU", "Contenu attendu",
            ca[:60] + ("…" if len(ca) > 60 else ""), type="rendu_contenu")

    # Composants
    for i, comp in enumerate(data["composants"]):
        val = f"{comp['role']} | {comp['statut_decisionnel']} | {comp['role_pipeline']}"
        add("COMPOSANTS", comp["nom"], val, type="composant", idx=i)

    # Stack
    for i, s in enumerate(data["stack"]):
        val = f"{s['role']} | {s['version']} | {s['statut_decisionnel']}"
        add("STACK", s["outil"], val, type="stack", idx=i)

    # Interactions
    for i, inter in enumerate(data["interactions"]):
        val = f"{inter['source']} → {inter['target']} : {inter['nature']}"
        add("INTERACTIONS", f"Interaction {i + 1}", val, type="interaction", idx=i)

    # Contraintes
    for si, section in enumerate(data["contraintes"]):
        for ci, crit in enumerate(section["criteres"]):
            add(
                f"CONTRAINTES — {section['titre']}",
                crit["nom"], crit["valeur"],
                type="critere", section_idx=si, critere_idx=ci,
            )

    # Contraintes non négociables
    for i, cnn in enumerate(data["contraintes_non_negociables"]):
        add("CONTRAINTES NON NÉGOCIABLES", f"CNN {i + 1}",
            cnn[:70] + ("…" if len(cnn) > 70 else ""), type="cnn", idx=i)

    return items


def _dispatch_edit(data: dict, item: dict) -> None:
    """Redirige vers la bonne fonction d'édition selon le type d'item."""
    t = item["type"]
    if t == "nom_projet":
        data["nom_projet"] = _ask_nonempty("Nom du projet", default=data["nom_projet"])
    elif t == "phase":
        data["phase"] = _choose(
            "Phase", ["exploration", "prototype", "pré-production", "déployé"],
            default=data["phase"],
        )
    elif t == "domaine":
        data["domaine"] = _choose(
            "Domaine", ["hardware", "software", "hybride"], default=data["domaine"]
        )
    elif t == "description":
        console.print("[dim]Réponse actuelle (complète) :[/dim]")
        console.print(f"  {data['description']}")
        data["description"] = _ask_nonempty("Nouvelle description", default=data["description"])
    elif t == "objectif":
        i = item["idx"]
        data["objectifs"][i] = _ask_nonempty(
            f"Objectif {i + 1}", default=data["objectifs"][i]
        )
    elif t == "rendu_date":
        _edit_rendu_date(data)
    elif t == "rendu_nature":
        data["prochain_rendu"]["nature"] = _choose(
            "Nature du rendu",
            ["démo", "livraison client", "soutenance", "release", "N/A"],
            default=data["prochain_rendu"]["nature"],
        )
    elif t == "rendu_contenu":
        ca = data["prochain_rendu"]["contenu_attendu"]
        console.print(f"[dim]Valeur actuelle :[/dim] {ca}")
        data["prochain_rendu"]["contenu_attendu"] = _ask_nonempty(
            "Contenu attendu", default=ca
        )
    elif t == "composant":
        _edit_composant(data, item["idx"])
    elif t == "stack":
        _edit_stack_item(data, item["idx"])
    elif t == "interaction":
        _edit_interaction(data, item["idx"])
    elif t == "critere":
        _edit_critere(data, item["section_idx"], item["critere_idx"])
    elif t == "cnn":
        i = item["idx"]
        data["contraintes_non_negociables"][i] = _ask_nonempty(
            f"Contrainte non négociable {i + 1}",
            default=data["contraintes_non_negociables"][i],
        )


def _show_review_and_correct(data: dict) -> None:
    """
    Affiche un récapitulatif numéroté de toutes les données saisies et
    permet de corriger n'importe quel champ avant la sauvegarde finale.

    Boucle jusqu'à ce que l'utilisateur valide (Entrée sans numéro).
    Le récap est reconstruit après chaque correction pour refléter les changements.
    """
    while True:
        items = _build_review_items(data)

        lines: list[str] = []
        current_section = None
        for i, item in enumerate(items, 1):
            if item["section"] != current_section:
                current_section = item["section"]
                lines.append(f"\n[bold dim]── {current_section}[/bold dim]")
            lines.append(
                f"  [cyan]{i:>2}.[/cyan] [bold]{item['label']}[/bold] : {item['value']}"
            )

        console.print()
        console.print(
            Panel(
                "\n".join(lines),
                title="[bold]RÉCAPITULATIF[/bold]",
                subtitle="[dim]Tape un numéro pour corriger · Entrée pour valider et sauvegarder[/dim]",
                border_style="cyan",
            )
        )

        raw = Prompt.ask("→ Numéro à corriger", default="").strip()

        if not raw:
            break

        if raw.isdigit() and 1 <= int(raw) <= len(items):
            _dispatch_edit(data, items[int(raw) - 1])
        else:
            console.print(f"[red]Numéro invalide (1–{len(items)}).[/red]")


# ─────────────────────────────────────────────────────────────
# Générateur de .md
# ─────────────────────────────────────────────────────────────


def generate_md(data: dict, changements: Optional[list[dict]] = None) -> str:
    """
    Génère le contenu Markdown du fichier projet à partir des données collectées.

    Args:
        data: Dictionnaire de toutes les données collectées par le questionnaire.
        changements: Liste optionnelle d'entrées Changements préexistantes
                    [{date_changement, resume}]. Si None, insère "Création initiale".

    Returns:
        String Markdown conforme au format MD_SCHEMA.md.
    """
    today = date.today().isoformat()
    lines: list[str] = []

    nom = data["nom_projet"]
    lines += [f"# {nom}", ""]

    lines += [
        "## Identité",
        f"- Nom : {nom}",
        f"- Phase : {data['phase']}",
        f"- Domaine : {data['domaine']}",
        f"- Dernière mise à jour : {today}",
        "",
    ]

    lines += ["## Description", data["description"].strip(), ""]

    lines += ["## Objectifs actifs"]
    for obj in data["objectifs"]:
        lines.append(f"- {obj}")
    lines.append("")

    rendu = data["prochain_rendu"]
    lines += [
        "## Prochain rendu",
        f"- Date : {rendu['date']}",
        f"- Nature : {rendu['nature']}",
        f"- Contenu attendu : {rendu['contenu_attendu']}",
        "",
    ]

    lines += [
        "## Composants",
        "| Composant | Rôle | Statut décisionnel | Rôle pipeline |",
        "|-----------|------|--------------------|---------------|",
    ]
    for c in data["composants"]:
        lines.append(
            f"| {c['nom']} | {c['role']} | {c['statut_decisionnel']} | {c['role_pipeline']} |"
        )
    lines.append("")

    lines += [
        "## Stack software",
        "| Outil | Rôle | Version | Statut décisionnel |",
        "|-------|------|---------|--------------------|",
    ]
    for s in data["stack"]:
        lines.append(
            f"| {s['outil']} | {s['role']} | {s['version']} | {s['statut_decisionnel']} |"
        )
    lines.append("")

    lines += ["## Interactions"]
    for i in data["interactions"]:
        line = f"- {i['source']} → {i['target']} : {i['nature']}"
        if i.get("format"):
            line += f" | {i['format']}"
        if i.get("volume"):
            line += f" | {i['volume']}"
        lines.append(line)
    lines.append("")

    lines += ["## Contraintes", ""]
    for section in data["contraintes"]:
        lines.append(f"### {section['titre']}")
        for crit in section["criteres"]:
            lines.append(f"- {crit['nom']} : {crit['valeur']}")
        lines.append("")

    lines += ["## Contraintes non négociables"]
    for cnn in data["contraintes_non_negociables"]:
        lines.append(f"- {cnn}")
    lines.append("")

    lines += ["## Changements"]
    if changements:
        for c in changements:
            lines.append(f"- {c['date_changement']} : {c['resume']}")
    else:
        lines.append(f"- {today} : Création initiale de la fiche projet")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Questionnaire principal
# ─────────────────────────────────────────────────────────────


def _section_identite(data: dict, llm) -> None:
    _section_header("IDENTITÉ", "Informations de base sur le projet")

    def step_nom(d: dict) -> None:
        while True:
            d["nom_projet"] = _ask("Nom du projet")
            if d["nom_projet"].strip():
                break
            console.print("[red]Le nom du projet ne peut pas être vide.[/red]")

    def step_phase(d: dict) -> None:
        d["phase"] = _choose(
            "Phase actuelle",
            ["exploration", "prototype", "pré-production", "déployé"],
            default=d.get("phase", "prototype"),
        )

    def step_domaine(d: dict) -> None:
        d["domaine"] = _choose(
            "Domaine",
            ["hardware", "software", "hybride"],
            default=d.get("domaine", "hybride"),
        )

    _navigate_steps([step_nom, step_phase, step_domaine], data, allow_back_at_start=True)


def _section_description(data: dict, llm) -> None:
    _section_header(
        "DESCRIPTION",
        "(1) Ce que fait le projet, (2) pour qui / dans quel contexte, "
        "(3) scope concret (durée, environnement, ordres de grandeur).",
    )

    def step(d: dict) -> None:
        d["description"] = _ask_with_enrichment(
            llm, d["nom_projet"],
            section="Description",
            question="Décris le projet en 2-3 phrases, en couvrant les trois axes ci-dessus",
            expectations=_SECTION_GUIDES["Description"],
        )

    _navigate_steps([step], data, allow_back_at_start=True)


def _section_objectifs(data: dict, llm) -> None:
    _section_header(
        "OBJECTIFS ACTIFS",
        "Ce sur quoi la veille va se concentrer. "
        "Chaque objectif doit être quantifié (chiffre + unité + condition) ou binaire vérifiable.",
    )

    objectifs: list[str] = data.get("objectifs", [])
    console.print(
        "[dim]Exemples : 'Tenir 6 mois d'autonomie sur batterie 2000 mAh + solaire 5W', "
        "'Précision T° ±0.5°C en plage -10°C/+50°C', 'Coût matériel < 80€/unité'[/dim]"
    )
    while True:
        item: dict = {}
        # Back interdit sur la 1ère question si on a déjà au moins 1 objectif
        # (l'utilisateur utilise le récap final pour modifier les objectifs précédents).
        # Back autorisé si c'est le tout 1er objectif → remonte à la section précédente.
        try:
            def step(d: dict) -> None:
                d["text"] = _ask_with_enrichment(
                    llm, data["nom_projet"],
                    section="Objectifs actifs",
                    question=f"Objectif {len(objectifs) + 1} (quantifié si possible)",
                    expectations=_SECTION_GUIDES["Objectifs actifs"],
                )
            _navigate_steps([step], item, allow_back_at_start=(len(objectifs) == 0))
        except BackRequested:
            raise  # remonte au caller pour aller à la section précédente
        objectifs.append(item["text"])
        if not Confirm.ask("Ajouter un autre objectif ?", default=False):
            break
    data["objectifs"] = objectifs


def _section_prochain_rendu(data: dict, llm) -> None:
    _section_header(
        "PROCHAIN RENDU",
        "Date limite et nature de la prochaine livraison (soutenance, démo, livraison, release...).",
    )

    rendu: dict = {"date": "N/A", "nature": "N/A", "contenu_attendu": "N/A"}

    def step_date(d: dict) -> None:
        while True:
            date_str = _ask("Date du prochain rendu (YYYY-MM-DD ou N/A)", default="N/A")
            if date_str.lower() == "n/a":
                d["date"] = "N/A"
                d["nature"] = "N/A"
                d["contenu_attendu"] = "N/A"
                return
            if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                d["date"] = date_str
                return
            console.print("[red]Format invalide — YYYY-MM-DD ou N/A.[/red]")

    def step_nature(d: dict) -> None:
        if d.get("date") == "N/A":
            return
        d["nature"] = _choose(
            "Nature du rendu",
            ["démo", "livraison client", "soutenance", "release", "N/A"],
            default=d.get("nature", "démo") if d.get("nature") != "N/A" else "démo",
        )

    def step_contenu(d: dict) -> None:
        if d.get("date") == "N/A":
            return
        d["contenu_attendu"] = _ask_with_enrichment(
            llm, data["nom_projet"],
            section="Contenu attendu rendu",
            question="Contenu attendu pour ce rendu (artefacts concrets + métriques)",
            expectations=_SECTION_GUIDES["Contenu attendu rendu"],
        )

    _navigate_steps([step_date, step_nature, step_contenu], rendu, allow_back_at_start=True)
    data["prochain_rendu"] = rendu


def _section_composants(data: dict, llm) -> None:
    _section_header(
        "COMPOSANTS",
        "Chaque composant physique ou module matériel du projet. "
        "Ajoute aussi régulateurs, antennes et passerelles s'ils sont structurants.",
    )

    composants: list[dict] = data.get("composants", [])
    console.print(
        "[dim]Exemples : ESP32-WROOM-32E, BME280, batterie LiPo 2000 mAh, "
        "panneau solaire 5W 6V, passerelle LoRaWAN Dragino LPS8[/dim]"
    )

    while True:
        comp: dict = {}

        def step_nom(d: dict) -> None:
            while True:
                d["nom"] = _ask(f"Nom du composant {len(composants) + 1}")
                if d["nom"].strip() and d["nom"].strip().lower() != "skip":
                    break
                if d["nom"].strip().lower() == "skip":
                    console.print("[yellow]Le nom du composant est obligatoire.[/yellow]")
                else:
                    console.print("[red]Le nom du composant ne peut pas être vide.[/red]")

        def step_role(d: dict) -> None:
            d["role"] = _ask_with_enrichment(
                llm, data["nom_projet"],
                section="Composant / rôle",
                question=f"  Rôle technique de '{d['nom']}' dans le système",
                expectations=_SECTION_GUIDES["Composant / rôle"],
            )

        def step_statut(d: dict) -> None:
            d["statut_decisionnel"] = _choose(
                "  Statut décisionnel",
                ["figé", "validé", "en évaluation"],
                default=d.get("statut_decisionnel", "validé"),
            )

        def step_pipeline(d: dict) -> None:
            d["role_pipeline"] = _choose(
                "  Rôle pipeline (critique = sans lui le projet ne marche pas)",
                ["critique", "support", "accessoire"],
                default=d.get("role_pipeline", "critique"),
            )

        try:
            _navigate_steps(
                [step_nom, step_role, step_statut, step_pipeline],
                comp,
                allow_back_at_start=(len(composants) == 0),
            )
        except BackRequested:
            raise  # 1er composant + back → remonte à la section précédente
        composants.append(comp)
        if not Confirm.ask("Ajouter un autre composant ?", default=True):
            break
    data["composants"] = composants


def _section_stack(data: dict, llm) -> None:
    _section_header(
        "STACK SOFTWARE",
        "Frameworks, langages, librairies, outils logiciels structurants du projet.",
    )

    stack: list[dict] = data.get("stack", [])
    console.print(
        "[dim]Exemples : ESP-IDF 5.x, Python 3.11, Grafana, InfluxDB, MicroPython 1.22+[/dim]"
    )

    while True:
        item: dict = {}

        def step_outil(d: dict) -> None:
            while True:
                d["outil"] = _ask(f"Outil / framework {len(stack) + 1}")
                if d["outil"].strip() and d["outil"].strip().lower() != "skip":
                    break
                if d["outil"].strip().lower() == "skip":
                    console.print("[yellow]Le nom de l'outil est obligatoire.[/yellow]")
                else:
                    console.print("[red]Le nom de l'outil ne peut pas être vide.[/red]")

        def step_role(d: dict) -> None:
            d["role"] = _ask_with_enrichment(
                llm, data["nom_projet"],
                section="Stack item / rôle",
                question=f"  Rôle de '{d['outil']}' dans le projet",
                expectations=_SECTION_GUIDES["Stack item / rôle"],
            )

        def step_version(d: dict) -> None:
            d["version"] = _ask("  Version (ou N/A)", default=d.get("version", "N/A"))

        def step_statut(d: dict) -> None:
            d["statut_decisionnel"] = _choose(
                "  Statut décisionnel",
                ["figé", "validé", "en évaluation"],
                default=d.get("statut_decisionnel", "validé"),
            )

        try:
            _navigate_steps(
                [step_outil, step_role, step_version, step_statut],
                item,
                allow_back_at_start=(len(stack) == 0),
            )
        except BackRequested:
            raise
        stack.append(item)
        if not Confirm.ask("Ajouter un autre outil ?", default=True):
            break
    data["stack"] = stack


def _section_interactions(data: dict, llm) -> None:
    _section_header(
        "INTERACTIONS",
        "Échanges entre composants ou entre logiciel et matériel. "
        "Format : Source → Cible : nature | format | volume",
    )

    known_names = [c["nom"] for c in data["composants"]] + [s["outil"] for s in data["stack"]]
    console.print(f"[dim]Composants/outils disponibles : {', '.join(known_names)}[/dim]")

    interactions: list[dict] = data.get("interactions", [])
    while True:
        item: dict = {"format": None, "volume": None}

        def step_source(d: dict) -> None:
            d["source"] = _ask(f"  Interaction {len(interactions) + 1} — Source")

        def step_target(d: dict) -> None:
            d["target"] = _ask("    Cible (→)")

        def step_nature(d: dict) -> None:
            d["nature"] = _ask_with_enrichment(
                llm, data["nom_projet"],
                section="Interaction / nature",
                question=f"    Nature de l'échange ({d['source']} → {d['target']})",
                expectations=_SECTION_GUIDES["Interaction / nature"],
            )

        def step_format(d: dict) -> None:
            v = _ask("    Format / protocole (ex. I2C, UART 9600, SPI, HTTP)", default="")
            d["format"] = v or None

        def step_volume(d: dict) -> None:
            v = _ask("    Volume / fréquence (ex. 1 lecture/15 min, continu)", default="")
            d["volume"] = v or None

        try:
            _navigate_steps(
                [step_source, step_target, step_nature, step_format, step_volume],
                item,
                allow_back_at_start=(len(interactions) == 0),
            )
        except BackRequested:
            raise
        interactions.append(item)
        if not Confirm.ask("Ajouter une autre interaction ?", default=True):
            break
    data["interactions"] = interactions


def _section_contraintes(data: dict, llm) -> None:
    _section_header(
        "CONTRAINTES",
        "Regroupe par sous-thème (Énergie, Performance, Connectivité, Budget, Environnementales...). "
        "Chaque critère doit avoir une valeur chiffrée, ou N/A, ou TBD : raison.",
    )

    contraintes: list[dict] = data.get("contraintes", [])
    console.print(
        "[dim]Exemples de sous-sections : Énergie, Performance, Connectivité, "
        "Environnementales, Budget, Robustesse[/dim]"
    )

    while True:
        section_data: dict = {"criteres": []}

        def step_titre(d: dict) -> None:
            while True:
                d["titre"] = _ask(f"Titre de la sous-section {len(contraintes) + 1} (ex. Énergie)")
                if d["titre"].strip():
                    break
                console.print("[red]Le titre ne peut pas être vide.[/red]")

        try:
            _navigate_steps(
                [step_titre], section_data,
                allow_back_at_start=(len(contraintes) == 0),
            )
        except BackRequested:
            raise

        # Boucle interne sur les critères : back support intra-critère
        while True:
            crit: dict = {}

            def step_crit_nom(d: dict) -> None:
                d["nom"] = _ask(
                    f"    Critère {len(section_data['criteres']) + 1} "
                    "(ex. Autonomie cible, Conso max, Précision)"
                )

            def step_crit_val(d: dict) -> None:
                d["valeur"] = _ask_with_enrichment(
                    llm, data["nom_projet"],
                    section="Critère de contrainte / valeur",
                    question=f"    Valeur du critère '{d['nom']}'",
                    expectations=_SECTION_GUIDES["Critère de contrainte / valeur"],
                )

            try:
                _navigate_steps(
                    [step_crit_nom, step_crit_val], crit,
                    allow_back_at_start=False,  # back interdit ici, sinon on annulerait le titre
                )
            except BackRequested:
                # Ne devrait pas arriver vu allow_back_at_start=False, mais par sécurité :
                console.print("[yellow]Reviens en arrière depuis le récap final.[/yellow]")
                continue

            section_data["criteres"].append(crit)
            if not Confirm.ask("    Ajouter un autre critère ?", default=True):
                break

        contraintes.append(section_data)
        if not Confirm.ask("Ajouter une autre sous-section de contraintes ?", default=False):
            break
    data["contraintes"] = contraintes


def _section_cnn(data: dict, llm) -> None:
    _section_header(
        "CONTRAINTES NON NÉGOCIABLES",
        "Contraintes imposées par décision externe (client, certification, stratégie figée). "
        "Une simple préférence n'est pas une contrainte non négociable.",
    )

    cnn: list[str] = data.get("contraintes_non_negociables", [])
    console.print(
        "[dim]Exemples : 'Pas de cloud commercial — passerelle locale obligatoire', "
        "'Code source open-source MIT pour la soutenance'[/dim]"
    )
    while True:
        item: dict = {}

        def step(d: dict) -> None:
            d["text"] = _ask_with_enrichment(
                llm, data["nom_projet"],
                section="Contrainte non négociable",
                question=f"Contrainte non négociable {len(cnn) + 1} (ou 'Aucune' pour terminer)",
                expectations=_SECTION_GUIDES["Contrainte non négociable"],
            )

        try:
            _navigate_steps([step], item, allow_back_at_start=(len(cnn) == 0))
        except BackRequested:
            raise

        if item["text"].strip().lower() in ("aucune", "aucun", "rien", "non"):
            if not cnn:
                cnn.append("Aucune contrainte non négociable identifiée à ce stade")
            break
        cnn.append(item["text"])
        if not Confirm.ask("En ajouter une autre ?", default=False):
            break
    data["contraintes_non_negociables"] = cnn


def run_questionnaire(config: dict) -> dict:
    """
    Lance le questionnaire guidé section par section.

    Navigation :
        - À chaque question texte, l'utilisateur peut taper `back` pour revenir
          à l'étape précédente (au sein d'un item de liste : champ précédent ;
          au début d'une section : section précédente).
        - Les corrections plus larges se font via le récap final.

    Returns:
        Dictionnaire de toutes les données saisies, prêt pour generate_md().
    """
    from src.llm import get_llm

    llm = None
    try:
        llm = get_llm("interviewer", config)
        from langchain_core.messages import HumanMessage as _HM
        _ = llm.invoke([_HM(content="Réponds OK.")])
    except Exception as e:
        llm = None
        console.print(
            f"[yellow]Avertissement : LLM indisponible ({type(e).__name__}). "
            f"L'enrichissement automatique est désactivé — "
            f"sois extra-précis dans tes réponses.[/yellow]"
        )

    console.print()
    console.print(
        Panel.fit(
            "[bold green]INTERVIEW — CRÉATION DE FICHE PROJET[/bold green]\n\n"
            "Je vais te guider section par section.\n"
            "Réponds avec des informations [bold]concrètes et mesurables[/bold] "
            "(chiffres, noms techniques, contraintes chiffrées).\n\n"
            "[bold cyan]Mots-clés disponibles à chaque question texte :[/bold cyan]\n"
            "  • [bold]back[/bold]  — revenir à l'étape précédente (champ ou section).\n"
            "  • [bold]skip[/bold]  — sur les questions de précision uniquement, "
            "conserve ta réponse initiale.\n"
            "  • Le skip est [bold]bloqué[/bold] si ta réponse est trop vague sur une\n"
            "    section critique (Description, Objectifs, Contraintes).\n\n"
            "[dim]Tu pourras aussi tout relire et corriger via le récap final.[/dim]",
            border_style="green",
        )
    )

    data: dict = {}

    # Liste ordonnée des sections. Chaque section gère son propre back interne ;
    # un BackRequested levé au début d'une section remonte ici et fait basculer
    # vers la section précédente avec restauration de l'état.
    sections: list[tuple[str, Callable[[dict, object], None]]] = [
        ("IDENTITÉ", _section_identite),
        ("DESCRIPTION", _section_description),
        ("OBJECTIFS", _section_objectifs),
        ("PROCHAIN RENDU", _section_prochain_rendu),
        ("COMPOSANTS", _section_composants),
        ("STACK", _section_stack),
        ("INTERACTIONS", _section_interactions),
        ("CONTRAINTES", _section_contraintes),
        ("CONTRAINTES NON NÉGOCIABLES", _section_cnn),
    ]

    snapshots: list[dict] = [deepcopy(data)]
    i = 0
    while i < len(sections):
        name, fn = sections[i]
        try:
            fn(data, llm)
            i += 1
            snapshots.append(deepcopy(data))
        except BackRequested:
            if i == 0:
                console.print(
                    "[yellow]Tu es à la première section, rien à corriger en arrière "
                    "— utilise le récap final pour modifier ton choix.[/yellow]"
                )
            else:
                snapshots.pop()
                i -= 1
                data.clear()
                data.update(snapshots[i])
                console.print(f"[dim]Retour à la section : {sections[i][0]}[/dim]")

    nom = data["nom_projet"]
    composants = data["composants"]
    interactions = data["interactions"]
    objectifs = data["objectifs"]
    contraintes = data["contraintes"]

    # ────────────────────────────── Récap + corrections
    console.print()
    console.print(
        Panel.fit(
            f"[green]Saisie terminée.[/green] "
            f"Projet : [bold]{nom}[/bold] | "
            f"{len(composants)} composants | "
            f"{len(interactions)} interactions | "
            f"{len(objectifs)} objectifs\n\n"
            "[dim]Tu peux relire et corriger avant de sauvegarder.[/dim]",
            border_style="green",
        )
    )
    _show_review_and_correct(data)

    # ────────────────────────────── Vérifications post-questionnaire
    _show_post_checks(data, llm)

    return data
