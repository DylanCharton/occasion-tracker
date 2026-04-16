"""Client et parser pour l'endpoint AJAX paginé d'Easycash.

Endpoint : /catalog/search/ajax
- Vraie pagination via offset (0, 30, 60, ...)
- 30 articles par requête
- Supporte les filtres : subCategory, vitrineAttribute1 (plateforme)
- Limite de 10 000 résultats par requête (splitter par plateforme)

Chaque carte produit contient un attribut `data-layer-click` dont le JSON
suit exactement le format `{"ecommerce":{"impressions":[{...}]}}`, ce qui
permet de réutiliser `extract_impressions` du parser existant.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from loguru import logger

from scraper.core.client import EasycashClient
from scraper.core.parser import ParsedArticle, extract_impressions, extract_product_links, _price_to_cents, _guess_platform


AJAX_PATH = "/catalog/search/ajax"
PAGE_SIZE = 30


@dataclass(frozen=True, slots=True)
class AjaxQuery:
    """Paramètres pour une requête AJAX Easycash."""

    sub_category: str       # ex: "Jeux Vidéo", "Console jeux vidéo"
    platform: str | None = None  # ex: "PlayStation 5 (PS5)", "Nintendo Switch"
    sort: str = "recent"

    def to_params(self, offset: int = 0) -> dict[str, str]:
        params: dict[str, str] = {
            "filterType": "searchResults",
            "facets[subCategory][0]": self.sub_category,
            "sort": self.sort,
            "page": "1",
            "offset": str(offset),
        }
        if self.platform:
            params["facets[vitrineAttribute1][0]"] = self.platform
        return params

    @property
    def label(self) -> str:
        parts = [self.sub_category]
        if self.platform:
            parts.append(self.platform)
        return " / ".join(parts)


# Mapping : nom court → valeur EXACTE du facet vitrineAttribute1 Easycash
# (récupéré depuis les filtres HTML de /catalog/search/ajax)
PLATFORM_FACETS: dict[str, str] = {
    "PS5": "PlayStation 5 (PS5)",
    "PS4": "PlayStation 4 (PS4)",
    "PS3": "PlayStation 3 (PS3)",
    "PS2": "PlayStation 2 (PS2)",
    "PS1": "PlayStation 1 (PS1)",
    "PSP": "PlayStation Portable (PSP)",
    "PS Vita": "PlayStation Vita (PS Vita)",
    "Switch": "Switch",
    "Switch 2": "Switch 2",
    "3DS": "3DS",
    "DS": "DS",
    "Wii U": "Wii U",
    "Wii": "Wii",
    "GameCube": "Game Cube",
    "Game Boy": "Game Boy",
    "Game Boy Advance": "Game Boy Advance",
    "Game Boy Color": "Game Boy Color",
    "N64": "Nintendo 64",
    "Super Nintendo": "Super Nintendo",
    "NES": "NES/Famicom",
    "Xbox Series X": "Xbox Series X",
    "Xbox One": "Xbox One",
    "Xbox 360": "Xbox 360",
    "Xbox": "Xbox",
    "Dreamcast": "Dreamcast",
    "Megadrive": "Megadrive",
    "Master System": "Master System",
    "Saturn": "Saturn",
    "Neo-Geo": "Neo-Geo",
}

# Inverse : facet → nom court normalisé (pour éviter "PlayStation 5 (PS5)" en base)
_FACET_TO_SHORT: dict[str, str] = {v: k for k, v in PLATFORM_FACETS.items()}

# Requêtes AJAX pré-configurées par type de contenu
def queries_for_platforms(platforms: list[str]) -> list[AjaxQuery]:
    """Construit les requêtes AJAX pour les plateformes choisies."""
    return [
        AjaxQuery(sub_category="Jeux Vidéo", platform=PLATFORM_FACETS[p])
        for p in platforms
        if p in PLATFORM_FACETS
    ]


AJAX_QUERIES_JEUX: list[AjaxQuery] = [
    AjaxQuery(sub_category="Jeux Vidéo", platform=facet)
    for facet in PLATFORM_FACETS.values()
]

AJAX_QUERIES_CONSOLES: list[AjaxQuery] = [
    AjaxQuery(sub_category="Console jeux vidéo"),
]

AJAX_QUERIES_ACCESSOIRES: list[AjaxQuery] = [
    AjaxQuery(sub_category="Acc. de jeux vidéo"),
]

ALL_AJAX_QUERIES: list[AjaxQuery] = (
    AJAX_QUERIES_JEUX + AJAX_QUERIES_CONSOLES + AJAX_QUERIES_ACCESSOIRES
)

# Plateformes disponibles (pour l'UI)
AVAILABLE_PLATFORMS: list[str] = list(PLATFORM_FACETS.keys())


def parse_ajax_response(html: str, query: AjaxQuery, base_url: str) -> list[ParsedArticle]:
    """Parse une réponse AJAX et retourne les articles extraits.

    Réutilise `extract_impressions` car le format JSON est identique
    au dataLayer des pages classiques.
    """
    impressions = extract_impressions(html)
    links = extract_product_links(html, base_url=base_url)

    articles: list[ParsedArticle] = []
    seen: set[str] = set()
    for item in impressions:
        ext_ref = str(item.get("id") or "").strip()
        if not ext_ref or ext_ref in seen:
            continue
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
        category = query.sub_category

        # Normaliser la plateforme : utiliser le nom court même si le facet est long
        short_platform = _FACET_TO_SHORT.get(query.platform, query.platform) if query.platform else None
        articles.append(
            ParsedArticle(
                ext_ref=ext_ref,
                title=name,
                url=url,
                category=category,
                price_cents=price_cents,
                brand=brand,
                platform=_guess_platform(name, short_platform),
            )
        )

    return articles


async def fetch_ajax_page(
    client: EasycashClient,
    query: AjaxQuery,
    offset: int,
    base_url: str,
) -> list[ParsedArticle]:
    """Fetch une page AJAX et retourne les articles parsés."""
    params = query.to_params(offset=offset)
    response = await client.get(AJAX_PATH, **params)
    return parse_ajax_response(response.text, query, base_url)
