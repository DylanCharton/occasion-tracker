"""Service orchestrant un cycle complet de scraping pour une catégorie.

fetch → parse → upsert en base → snapshot prix si nécessaire.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from scraper.config import settings
from scraper.core.client import EasycashClient
from scraper.core.parser import ParsedArticle, has_next_page, parse_listing
from scraper.db.repository import ArticleRepository
from scraper.db.session import session_scope
from scraper.services.alert_detector import detect_and_notify


@dataclass(slots=True)
class ScrapeReport:
    category: str
    pages_fetched: int = 0
    articles_seen: int = 0
    articles_created: int = 0
    articles_updated: int = 0
    snapshots_written: int = 0
    ext_refs_seen: set[str] = field(default_factory=set)


async def scrape_category(
    category_slug: str,
    *,
    max_pages: int = 10,
    client: EasycashClient | None = None,
    trigger_alerts: bool = True,
) -> ScrapeReport:
    """Scrape toutes les pages (jusqu'à max_pages) d'une catégorie JV.

    Si `trigger_alerts` est vrai, lance la détection d'alertes à la fin
    (baisses sur les watches ARTICLE + nouveaux matches sur les SEARCH).
    """
    report = ScrapeReport(category=category_slug)

    owned_client = client is None
    if client is None:
        client = EasycashClient()

    try:
        if owned_client:
            await client.__aenter__()

        for page in range(1, max_pages + 1):
            path = f"/{category_slug.lstrip('/')}"
            params: dict[str, str] = {}
            if page > 1:
                params["page"] = str(page)

            logger.info(f"Fetch {path} page={page}")
            response = await client.get(path, **params)
            html = response.text
            articles = parse_listing(html, category_slug=category_slug, base_url=settings.base_url)
            report.pages_fetched += 1

            if articles:
                _persist_articles(articles, report)

            if not has_next_page(html, page, len(articles)):
                logger.info(f"Fin de pagination sur {path} après {page} page(s)")
                break
    finally:
        if owned_client:
            await client.__aexit__(None, None, None)

    logger.info(
        f"[{category_slug}] {report.articles_seen} articles vus "
        f"({report.articles_created} créés, {report.articles_updated} maj), "
        f"{report.snapshots_written} snapshots."
    )

    if trigger_alerts and report.ext_refs_seen:
        try:
            detect_and_notify(ext_refs_seen=report.ext_refs_seen)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Détection d'alertes échouée : {exc}")

    return report


def _persist_articles(articles: list[ParsedArticle], report: ScrapeReport) -> None:
    """Upsert la liste d'articles et écrit les snapshots de prix nécessaires."""
    with session_scope() as session:
        repo = ArticleRepository(session)
        for parsed in articles:
            article, created = repo.upsert(
                ext_ref=parsed.ext_ref,
                title=parsed.title,
                url=parsed.url,
                category=parsed.category,
                brand=parsed.brand,
                platform=parsed.platform,
                image_url=parsed.image_url,
            )
            if created:
                report.articles_created += 1
            else:
                report.articles_updated += 1

            snap = repo.record_price(
                article,
                price_cents=parsed.price_cents,
                available=True,
            )
            if snap is not None:
                report.snapshots_written += 1

            report.ext_refs_seen.add(parsed.ext_ref)
            report.articles_seen += 1
