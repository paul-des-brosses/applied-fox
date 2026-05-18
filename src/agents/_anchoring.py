"""
Utilitaires partagés d'ancrage projet, utilisés par Éclaireur et Juge.

Centralise la logique de :
    - Construction des `strong_anchors` d'un projet (tokens spécifiques projet,
      hors deny-list générique).
    - Tokenisation et normalisation (strip d'accents, split CamelCase).
    - Dictionnaire de traductions FR/EN pour les concepts d'embarqué.
    - Extraction déterministe des références composants depuis un texte.

Pourquoi un module séparé : l'Éclaireur a besoin de ces utilitaires pour
filtrer en amont (filter_alignment), et le Juge en a besoin pour faire
un deuxième niveau de check au moment du verdict (règle 1bis du prompt
enforcée déterministement).

Conçu pour rester court et auditable. Pas d'I/O, pas de LLM, pas d'état
mutable. Toutes les fonctions sont pures.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import ProjectModel


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

# Longueur minimale d'un token pour être considéré comme un anchor candidat.
# Filtre les bruits du type "v2", "5a", "s3" qui matchent trop largement.
MIN_TOKEN_LEN = 3

# Tokens techniquement courants qui matchent trop largement seul.
# Un finding doit avoir AU MOINS UN token spécifique au projet pour passer ;
# ces tokens-là ne suffisent pas.
# Calibré post-éval Jalon 8 (cf. jalon8_pertinence_multi_projets).
GENERIC_DENY_AS_ANCHOR: set[str] = {
    # Plateformes MCU/SoC très courantes
    "esp32", "stm32", "arduino", "raspberry", "pico", "atmega", "esp8266",
    "esp32s3", "esp32c3", "esp32c6", "esp32p4", "stm32f103", "stm32f4",
    # Concepts trop génériques
    "lora", "wifi", "ble", "mqtt", "spi", "i2c", "uart", "can", "usb",
    "pcb", "mcu", "soc", "iot", "led", "leds", "gpio", "adc", "dac", "pwm",
    "mosfet", "diode", "resistor", "capacitor", "regulator", "buck", "boost",
    # Outils dev très génériques
    "review", "request", "design", "board", "module", "controller", "system",
    "project", "first", "help", "test", "tests", "code", "firmware",
}


# Paires de traduction FR↔EN limitées aux concepts d'embarqué structurants.
# Le pipeline scrape majoritairement des sources anglaises ; sans dictionnaire
# minimal, on rejette des findings parfaitement alignés. Volontairement court
# et limité : pas de mots génériques (sensor, module, system) qui ramèneraient
# du bruit.
FR_EN_PAIRS: dict[str, list[str]] = {
    "batterie": ["battery"],
    "batteries": ["batteries"],
    "pile": ["cell"],
    "piles": ["cells"],
    "cellule": ["cell"],
    "cellules": ["cells"],
    "autonomie": ["autonomy", "lifetime", "runtime"],
    "consommation": ["consumption"],
    "portee": ["range"],
    "poids": ["weight"],
    "humidite": ["humidity", "moisture"],
    "temperature": ["temperature"],
    "pression": ["pressure"],
    "surcharge": ["overcharge", "overcharging"],
    "decharge": ["discharge", "discharging"],
    "surchauffe": ["overheat", "overheating"],
    "surintensite": ["overcurrent"],
    "coupure": ["shutoff", "disconnect", "shutdown", "cutoff"],
    "precision": ["accuracy", "precision"],
    "equilibrage": ["balancing"],
    "arrosage": ["watering", "irrigation"],
    "boitier": ["enclosure", "housing"],
    "etancheite": ["waterproof", "watertight"],
    "antenne": ["antenna"],
    "alimentation": ["powersupply"],
}


# Pattern pour extraire les références composants type BME280, SX1262,
# BQ76940, MAX-M10S, IRFB7430, RAK3172. Heuristique simple : ≥2 lettres
# majuscules suivies de ≥1 chiffre, puis suffixe alphanumérique optionnel.
COMPONENT_REFERENCE_PATTERN = re.compile(
    r"\b[A-Z]{2,}\d+[A-Z\d\-]*\b"
)


# ─────────────────────────────────────────────────────────────
# Tokenisation et normalisation
# ─────────────────────────────────────────────────────────────


def strip_accents(s: str) -> str:
    """Retire les accents : 'précision' → 'precision'.

    Indispensable pour matcher 'précision' projet avec 'precision' EN.
    """
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def camel_split(text: str) -> str:
    """Insère un espace aux frontières CamelCase.

    'SoilMoisureLogger' → 'Soil Moisure Logger'
    Utile pour les noms de repos GitHub sans séparateur, où la tokenisation
    standard regrouperait tout en un seul token illisible.
    """
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)


def tokenize(text: str) -> set[str]:
    """Tokens alphanumériques minuscules, accents retirés, len >= MIN_TOKEN_LEN.

    Applique aussi camel_split en amont pour mieux découper les identifiants
    CamelCase.
    """
    if not text:
        return set()
    normalized = strip_accents(camel_split(text).lower())
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return {t for t in tokens if len(t) >= MIN_TOKEN_LEN}


def normalize_component_name(name: str) -> str:
    """ESP32-S3 → esp32s3, SHT31-D → sht31d, MH-Z19B → mhz19b.

    Strip d'accents + minuscule + suppression de tout caractère non-alphanum.
    Utilisé en complément de tokenize() pour matcher les références composants
    écrites avec ou sans tirets dans les sources.
    """
    n = strip_accents(name.lower())
    return re.sub(r"[^a-z0-9]", "", n)


def is_specific_anchor(anchor: str) -> bool:
    """Un anchor est 'spécifique' s'il contient un chiffre OU fait ≥7 caractères.

    Filtre les ancrages génériques type 'sensor' (6 chars, no digit), 'system'
    (déjà dans deny mais idem), tout en gardant 'sht31', 'capacitive',
    'peristaltique', 'mhz19b', etc.

    Pourquoi 7 : 'sensor' fait 6 chars, 'battery' fait 7. On veut éliminer
    'sensor' mais garder 'battery'. Le seuil 7 est le minimum qui satisfait
    ce trade-off.
    """
    return bool(re.search(r"\d", anchor)) or len(anchor) >= 7


def expand_anchors_with_translations(anchors: set[str]) -> set[str]:
    """Ajoute les traductions EN aux anchors FR détectés. Non destructif."""
    extensions: set[str] = set()
    for fr, en_list in FR_EN_PAIRS.items():
        if fr in anchors:
            extensions.update(en_list)
    return anchors | extensions


# ─────────────────────────────────────────────────────────────
# Construction des anchors d'un projet
# ─────────────────────────────────────────────────────────────


def project_alignment_tokens(project: "ProjectModel") -> set[str]:
    """
    Ensemble complet des tokens "intéressants" du projet, hors deny-list.

    Source des tokens :
        - composants (nom + forme normalisée)
        - stack software (outil + forme normalisée)
        - objectifs actifs (texte libre)
        - contraintes non négociables (texte libre)
        - description du projet
        - natures et formats des interactions (souvent les protocoles)
    """
    anchors: set[str] = set()

    for c in project.composants:
        anchors |= tokenize(c.nom)
        normalized = normalize_component_name(c.nom)
        if len(normalized) >= 4:
            anchors.add(normalized)

    for s in project.stack_software:
        anchors |= tokenize(s.outil)
        normalized = normalize_component_name(s.outil)
        if len(normalized) >= 4:
            anchors.add(normalized)

    for obj in project.objectifs_actifs:
        anchors |= tokenize(obj)

    for cnn in project.contraintes_non_negociables:
        anchors |= tokenize(cnn)

    if project.description:
        anchors |= tokenize(project.description)

    for inter in project.interactions:
        anchors |= tokenize(inter.nature or "")
        anchors |= tokenize(inter.format or "")

    return anchors


def project_strong_anchors(project: "ProjectModel") -> set[str]:
    """
    Sous-ensemble "spécifique" des tokens projet : retire les tokens génériques.

    Ajoute aussi les traductions EN pour les concepts FR détectés.
    Si l'ensemble est vide après filtrage (cas limite : tous les composants
    sont des termes génériques), on retombe sur l'ensemble complet pour
    éviter de tout rejeter.
    """
    full = project_alignment_tokens(project)
    strong = {a for a in full if a not in GENERIC_DENY_AS_ANCHOR}
    if not strong:
        strong = full
    return expand_anchors_with_translations(strong)


# ─────────────────────────────────────────────────────────────
# Détection de composants dans un texte (Niveau 2)
# ─────────────────────────────────────────────────────────────


def extract_mentioned_components(text: str) -> list[str]:
    """
    Détecte les références composants dans un texte (titre + description finding).

    Retourne la liste des matches uniques, conservant l'ordre d'apparition.
    Pattern : ≥2 lettres majuscules suivies de ≥1 chiffre.

    Exemples capturés : BME280, SX1262, BQ76940, MAX-M10S, IRFB7430, RAK3172,
    STM32F103C8T6, INR21700-40T.
    Non capturé : ESP32 (sans chiffre suffisant ? non, capturé), simplement nom
    de marque ("Adafruit", "Bosch") sans référence.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in COMPONENT_REFERENCE_PATTERN.finditer(text):
        token = match.group(0)
        # Conserve la casse d'origine pour lisibilité, mais déduplique en case-insensitive
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def classify_components(
    finding_text: str,
    project: "ProjectModel",
) -> tuple[list[str], list[str]]:
    """
    Sépare les composants mentionnés dans le finding en deux groupes :
        - in_project : références qui matchent un composant du projet
        - new_mentioned : références qui ne matchent aucun composant du projet

    Le matching est normalisé (ESP32-S3 == esp32s3 == ESP32S3) et inclut le
    matching par substring pour absorber les variations (SHT31 vs SHT31-D).

    Returns:
        Tuple (in_project, new_mentioned), chaque liste préservant l'ordre
        d'apparition dans le texte.
    """
    mentions = extract_mentioned_components(finding_text)
    if not mentions:
        return [], []

    # Construit l'ensemble normalisé des composants projet
    project_normalized: set[str] = set()
    for c in project.composants:
        project_normalized.add(normalize_component_name(c.nom))
        for tok in tokenize(c.nom):
            project_normalized.add(tok)
    for s in project.stack_software:
        project_normalized.add(normalize_component_name(s.outil))
        for tok in tokenize(s.outil):
            project_normalized.add(tok)

    in_project: list[str] = []
    new_mentioned: list[str] = []
    for mention in mentions:
        mention_norm = normalize_component_name(mention)
        # Match exact OU substring (SHT31 ⊂ SHT31D, ESP32 ⊂ ESP32S3DEVKITC)
        matched = (
            mention_norm in project_normalized
            or any(mention_norm in p or p in mention_norm
                   for p in project_normalized if len(p) >= 4)
        )
        if matched:
            in_project.append(mention)
        else:
            new_mentioned.append(mention)

    return in_project, new_mentioned
