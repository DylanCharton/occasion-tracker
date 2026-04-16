"""Tests du parser dataLayer + extraction liens produits."""

from __future__ import annotations

from pathlib import Path

import pytest

from scraper.core.parser import (
    extract_impressions,
    extract_product_links,
    has_next_page,
    parse_listing,
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "listing_sample.html").read_text(encoding="utf-8")


@pytest.fixture
def empty_html() -> str:
    return (FIXTURES / "listing_empty.html").read_text(encoding="utf-8")


def test_extract_impressions_returns_all_products(listing_html: str) -> None:
    impressions = extract_impressions(listing_html)
    assert len(impressions) == 3
    ids = {item["id"] for item in impressions}
    assert ids == {"005168034", "003938520", "5094885"}


def test_extract_product_links_maps_ext_ref_to_url(listing_html: str) -> None:
    links = extract_product_links(listing_html, base_url="https://bons-plans.easycash.fr")
    assert "005168034" in links
    assert links["005168034"].endswith("/jeux-video/spider-man-2-ps5-005168034")
    # URL absolue déjà absolue doit être conservée
    assert links["005094885"].startswith("https://bons-plans.easycash.fr/")


def test_parse_listing_returns_parsed_articles(listing_html: str) -> None:
    articles = parse_listing(
        listing_html,
        category_slug="jeux-video",
        base_url="https://bons-plans.easycash.fr",
    )
    assert len(articles) == 3
    spidey = next(a for a in articles if a.ext_ref == "005168034")
    assert spidey.title.startswith("Jeux Vidéo Spider-Man 2")
    assert spidey.price_cents == 3499
    assert spidey.category == "jeux-video"
    assert spidey.brand == "SONY"
    assert spidey.platform == "PS5"
    assert spidey.url.endswith("/jeux-video/spider-man-2-ps5-005168034")


def test_parse_listing_pads_short_ids(listing_html: str) -> None:
    articles = parse_listing(
        listing_html,
        category_slug="consoles/sony",
        base_url="https://bons-plans.easycash.fr",
    )
    # L'id "5094885" doit être padé en "005094885"
    paded = next(a for a in articles if a.ext_ref == "005094885")
    assert paded.price_cents == 36999


def test_parse_listing_platform_detection() -> None:
    html = """
    <script>dataLayer.push({"ecommerce":{"impressions":[
      {"id":"000000001","name":"Jeu Zelda Breath of the Wild Switch","price":"29.99","brand":"NINTENDO","category":"Jeux vidéo"},
      {"id":"000000002","name":"Mario Kart 8 Wii U","price":"19.99","brand":"NINTENDO","category":"Jeux vidéo"},
      {"id":"000000003","name":"Halo Xbox Series X","price":"39.99","brand":"MICROSOFT","category":"Jeux vidéo"}
    ]}});</script>
    """
    articles = parse_listing(html, category_slug="jeux-video", base_url="https://example.com")
    platforms = {a.ext_ref: a.platform for a in articles}
    assert platforms["000000001"] == "Switch"
    assert platforms["000000002"] == "Wii U"
    assert platforms["000000003"] == "Xbox Series X"


def test_has_next_page_stops_on_empty(empty_html: str) -> None:
    assert has_next_page(empty_html, current_page=1, articles_on_page=0) is False


def test_has_next_page_stops_on_aucun_resultat(empty_html: str) -> None:
    assert has_next_page(empty_html, current_page=1, articles_on_page=5) is False


def test_has_next_page_continues_when_full() -> None:
    assert has_next_page("<html><body>produits</body></html>", current_page=1, articles_on_page=11) is True


def test_extract_impressions_empty_html_returns_empty(empty_html: str) -> None:
    assert extract_impressions(empty_html) == []


def test_extract_impressions_handles_malformed_json() -> None:
    html = '<script>dataLayer.push({"ecommerce":{"impressions":[{broken json ] } });</script>'
    # Ne doit pas lever d'exception, juste ignorer
    assert extract_impressions(html) == []
