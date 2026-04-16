"""Parser des pages Easycash.

Stratégie : Easycash injecte les données produit dans le `dataLayer` GTM
sous la forme `{"ecommerce":{"impressions":[{...}, ...]}}`. On extrait ce
bloc JSON de façon robuste, puis on matche les URLs vues dans le HTML via
l'ID produit (9 chiffres en fin d'URL).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser


# Un ID produit Easycash est un entier 9 chiffres (padé à gauche par des zéros).
EXT_REF_RE = re.compile(r"(\d{9})(?:[/?#]|$)")
# URL produit : /{categorie}[/sub]/{slug}-{9chiffres}
PRODUCT_URL_RE = re.compile(r"^/[\w\-/]+/[\w\-]+-(\d{9})/?$")


@dataclass(slots=True)
class ParsedArticle:
    ext_ref: str
    title: str
    url: str          # URL absolue si possible, sinon chemin
    category: str     # catégorie Easycash normalisée
    price_cents: int
    currency: str = "EUR"
    brand: str | None = None
    platform: str | None = None
    image_url: str | None = None


def _iter_json_objects_after_key(text: str, key: str) -> list:
    """Trouve toutes les occurrences de `"<key>":[...]` et retourne la liste parsée.

    Utilise JSONDecoder.raw_decode pour gérer proprement les crochets imbriqués.
    """
    results: list = []
    pattern = f'"{key}":'
    decoder = json.JSONDecoder()
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx == -1:
            break
        # Positionne le curseur sur le début de la valeur JSON
        cursor = idx + len(pattern)
        # Skip whitespace
        while cursor < len(text) and text[cursor] in " \t\n\r":
            cursor += 1
        if cursor >= len(text):
            break
        try:
            value, end = decoder.raw_decode(text, cursor)
        except json.JSONDecodeError:
            start = cursor + 1
            continue
        if isinstance(value, list):
            results.extend(value)
        start = end
    return results


def extract_impressions(html: str) -> list[dict]:
    """Extrait la liste des produits depuis le dataLayer GTM."""
    return [item for item in _iter_json_objects_after_key(html, "impressions") if isinstance(item, dict)]


def extract_product_links(html: str, base_url: str = "") -> dict[str, str]:
    """Map ext_ref -> URL absolue trouvée dans le HTML."""
    tree = HTMLParser(html)
    links: dict[str, str] = {}
    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "")
        if not href:
            continue
        # On ne garde que les URLs internes au domaine ou relatives
        path = href
        if href.startswith("http"):
            # Isole le chemin
            try:
                from urllib.parse import urlparse
                parsed = urlparse(href)
                path = parsed.path
            except Exception:
                continue
        m = PRODUCT_URL_RE.match(path)
        if not m:
            # fallback : matcher juste l'ID 9 chiffres en fin de chemin
            m2 = EXT_REF_RE.search(path)
            if not m2:
                continue
            ext_ref = m2.group(1)
        else:
            ext_ref = m.group(1)
        full_url = href if href.startswith("http") else f"{base_url.rstrip('/')}{href}"
        links.setdefault(ext_ref, full_url)
    return links


def _price_to_cents(value: object) -> int | None:
    """Convertit '369.99' ou 369.99 en 36999 centimes."""
    if value is None:
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _guess_platform(name: str, existing: str | None = None) -> str | None:
    """Tente de détecter la plateforme depuis le titre (PS5, PS4, Switch, etc.)."""
    if existing:
        return existing
    upper = name.upper()
    # Ordre : les plus spécifiques d'abord pour éviter que "PS" matche avant "PS5"
    candidates = [
        "PS5 PRO", "PS5 SLIM", "PS5", "PS4 PRO", "PS4 SLIM", "PS4",
        "PS3", "PS2", "PS1", "PSP", "PS VITA",
        "XBOX SERIES X", "XBOX SERIES S", "XBOX SERIES",
        "XBOX ONE X", "XBOX ONE S", "XBOX ONE", "XBOX 360", "XBOX",
        "SWITCH 2", "SWITCH OLED", "SWITCH LITE", "SWITCH",
        "NINTENDO DS", "3DS", "2DS",
        "WII U", "WII",
        "GAMECUBE", "N64",
        "GAME BOY ADVANCE", "GAME BOY",
    ]
    for c in candidates:
        if c in upper:
            return c.title().replace("Ps", "PS").replace("3Ds", "3DS").replace("2Ds", "2DS")
    return None


def parse_listing(html: str, category_slug: str, base_url: str) -> list[ParsedArticle]:
    """Parse une page de listing Easycash -> liste de ParsedArticle.

    Args:
        html: HTML brut de la page
        category_slug: slug de la catégorie utilisée pour le fetch (ex: "jeux-video")
        base_url: préfixe pour construire les URLs absolues (ex: "https://bons-plans.easycash.fr")
    """
    impressions = extract_impressions(html)
    links = extract_product_links(html, base_url=base_url)

    articles: list[ParsedArticle] = []
    seen: set[str] = set()
    for item in impressions:
        ext_ref = str(item.get("id") or "").strip()
        if not ext_ref or ext_ref in seen:
            continue
        # Normaliser l'ID sur 9 chiffres (certains peuvent venir sans padding)
        if ext_ref.isdigit():
            ext_ref = ext_ref.zfill(9)
        seen.add(ext_ref)

        name = str(item.get("name") or "").strip()
        if not name:
            continue

        price_cents = _price_to_cents(item.get("price"))
        if price_cents is None:
            continue

        url = links.get(ext_ref, "")
        brand = (str(item.get("brand")).strip() or None) if item.get("brand") else None
        ds_category = (str(item.get("category")).strip() or None) if item.get("category") else None

        articles.append(
            ParsedArticle(
                ext_ref=ext_ref,
                title=name,
                url=url,
                category=category_slug,
                price_cents=price_cents,
                brand=brand,
                platform=_guess_platform(name),
                image_url=None,  # non exposé dans dataLayer, à enrichir plus tard si besoin
            )
        )

    return articles


def has_next_page(html: str, current_page: int, articles_on_page: int) -> bool:
    """Indique s'il faut tenter la page suivante.

    Heuristique : si on a reçu zéro article, on arrête. On peut aussi chercher
    un lien de pagination dans le HTML, mais une page vide est le signal
    le plus fiable.
    """
    if articles_on_page == 0:
        return False
    # Filet de sécurité : si le HTML contient un indicateur explicite "no results"
    # ou "aucun résultat", on s'arrête aussi.
    lowered = html.lower()
    if "aucun résultat" in lowered or "aucun resultat" in lowered:
        return False
    return True
