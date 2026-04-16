"""Service orchestrant un cycle complet de scraping pour une catégorie.

fetch → parse → déduplique → upsert en base → snapshot prix.

Pagination Easycash : quand on dépasse la dernière page réelle, le site
RECYCLE le contenu paginé depuis le début (pas de page vide, pas de 404).
On détecte ce recyclage en comptant les pages consécutives sans aucun
article nouveau (= 100% doublons déjà vus dans cette même session).
Après RECYCLE_THRESHOLD pages consécutives de pur recyclage, on stoppe.
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

# Easycash recycle le contenu paginé après la dernière vraie page.
# On s'arrête quand N pages consécutives n'apportent aucun nouvel article.
# 3 pages de marge pour gérer un éventuel « trou » dans la pagination.
RECYCLE_THRESHOLD = 3


@dataclass(slots=True)
class ScrapeReport:
    category: str
    pages_fetched: int = 0
    articles_unique: int = 0
    articles_created: int = 0
    articles_updated: int = 0
    snapshots_written: int = 0
    articles_skipped_dup: int = 0
    stopped_reason: str = ""
    ext_refs_seen: set[str] = field(default_factory=set)


async def scrape_category(
    category_slug: str,
    *,
    max_pages: int = 10,
    client: EasycashClient | None = None,
    trigger_alerts: bool = True,
) -> ScrapeReport:
    """Scrape toutes les pages (jusqu'à max_pages) d'une catégorie JV.

    Arrêt automatique quand :
    - la page est réellement vide (0 article) ou contient « aucun résultat »
    - RECYCLE_THRESHOLD pages consécutives sans nouvel article (recyclage)
    - max_pages atteint
    """
    report = ScrapeReport(category=category_slug)

    owned_client = client is None
    if client is None:
        client = EasycashClient()

    consecutive_recycled = 0

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

            # Déduplique : ne persister que les articles pas encore vus ce scan
            new_articles = [a for a in articles if a.ext_ref not in report.ext_refs_seen]
            dup_count = len(articles) - len(new_articles)
            report.articles_skipped_dup += dup_count

            if new_articles:
                _persist_articles(new_articles, report)
                consecutive_recycled = 0
            else:
                consecutive_recycled += 1

            # Arrêt : page réellement vide
            if not has_next_page(html, page, len(articles)):
                report.stopped_reason = "page vide"
                logger.info(f"Fin : {path} page {page} — page vide")
                break

            # Arrêt : contenu recyclé (Easycash boucle sur les mêmes articles)
            if consecutive_recycled >= RECYCLE_THRESHOLD:
                report.stopped_reason = "contenu recyclé"
                logger.info(
                    f"Fin : {path} page {page} — {RECYCLE_THRESHOLD} pages "
                    f"consécutives sans nouvel article (recyclage Easycash détecté)"
                )
                break
        else:
            report.stopped_reason = f"max pages atteint ({max_pages})"

    finally:
        if owned_client:
            await client.__aexit__(None, None, None)

    report.articles_unique = len(report.ext_refs_seen)

    logger.info(
        f"[{category_slug}] {report.articles_unique} articles uniques "
        f"({report.articles_created} créés, {report.articles_updated} maj), "
        f"{report.snapshots_written} snapshots, "
        f"{report.articles_skipped_dup} doublons ignorés, "
        f"{report.pages_fetched} page(s). Arrêt : {report.stopped_reason}."
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
