"""Scraping complet via l'endpoint AJAX paginé.

Parcourt toutes les plateformes définies dans ajax.py via l'endpoint
/catalog/search/ajax avec offset. Chaque plateforme est scrapée
intégralement (bien en dessous du cap de 10K items).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from scraper.config import settings
from scraper.core.ajax import (
    ALL_AJAX_QUERIES,
    AJAX_QUERIES_JEUX,
    AjaxQuery,
    PAGE_SIZE,
    fetch_ajax_page,
)
from scraper.core.client import EasycashClient
from scraper.core.parser import ParsedArticle
from scraper.db.repository import ArticleRepository
from scraper.db.session import session_scope
from scraper.services.alert_detector import detect_and_notify


MAX_OFFSET = 10_000  # Limite Easycash
EMPTY_PAGES_STOP = 2  # Pages vides consécutives avant d'arrêter une plateforme


@dataclass(slots=True)
class FullScrapeReport:
    queries_done: int = 0
    queries_total: int = 0
    articles_unique: int = 0
    articles_created: int = 0
    articles_updated: int = 0
    snapshots_written: int = 0
    ext_refs_seen: set[str] = field(default_factory=set)
    current_query: str = ""


async def scrape_query(
    query: AjaxQuery,
    *,
    client: EasycashClient,
    report: FullScrapeReport,
) -> int:
    """Scrape une requête AJAX (une plateforme) en entier. Retourne le nb d'articles uniques."""
    query_unique = 0
    consecutive_empty = 0

    for offset in range(0, MAX_OFFSET, PAGE_SIZE):
        articles = await fetch_ajax_page(client, query, offset, settings.base_url)

        if not articles:
            consecutive_empty += 1
            if consecutive_empty >= EMPTY_PAGES_STOP:
                break
            continue

        # Déduplique au niveau global (cross-plateformes)
        new_articles = [a for a in articles if a.ext_ref not in report.ext_refs_seen]
        if not new_articles:
            consecutive_empty += 1
            if consecutive_empty >= EMPTY_PAGES_STOP:
                break
            continue

        consecutive_empty = 0
        _persist(new_articles, report)
        query_unique += len(new_articles)

        # Si la page est incomplète, c'est la dernière
        if len(articles) < PAGE_SIZE:
            break

    logger.info(f"[full] {query.label} : {query_unique} articles uniques")
    return query_unique


async def scrape_full(
    *,
    queries: list[AjaxQuery] | None = None,
    trigger_alerts: bool = True,
    progress_callback: object | None = None,
) -> FullScrapeReport:
    """Scrape complet de toutes les plateformes via AJAX.

    Args:
        queries: liste de requêtes AJAX à exécuter (défaut : toutes).
        trigger_alerts: lancer la détection d'alertes à la fin.
        progress_callback: callable(query_label, queries_done, queries_total)
            pour mettre à jour une barre de progression (Streamlit).
    """
    if queries is None:
        queries = ALL_AJAX_QUERIES

    report = FullScrapeReport(queries_total=len(queries))

    async with EasycashClient() as client:
        for i, query in enumerate(queries):
            report.current_query = query.label
            if progress_callback:
                progress_callback(query.label, i, len(queries))

            logger.info(f"[full] Début {query.label} ({i + 1}/{len(queries)})")
            await scrape_query(query, client=client, report=report)
            report.queries_done = i + 1

    report.articles_unique = len(report.ext_refs_seen)

    logger.info(
        f"[full] Terminé : {report.articles_unique} articles uniques "
        f"({report.articles_created} créés, {report.articles_updated} maj), "
        f"{report.snapshots_written} snapshots, "
        f"{report.queries_done}/{report.queries_total} requêtes."
    )

    if trigger_alerts and report.ext_refs_seen:
        try:
            detect_and_notify(ext_refs_seen=report.ext_refs_seen)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Détection d'alertes échouée : {exc}")

    return report


def _persist(articles: list[ParsedArticle], report: FullScrapeReport) -> None:
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
