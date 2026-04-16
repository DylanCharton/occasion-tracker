"""Helpers partagés par les pages Streamlit."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Iterable

import streamlit as st

from scraper.config import settings
from scraper.core.categories import CATEGORIES, CATEGORIES_BY_SLUG
from scraper.db.models import Article, PriceSnapshot
from scraper.db.repository import (
    AlertRepository,
    ArticleRepository,
    ScheduledJobRepository,
    WatchRepository,
)
from scraper.db.session import init_db, session_scope
from scraper.services.scheduler_service import SchedulerService
from scraper.core.ajax import AVAILABLE_PLATFORMS, queries_for_platforms
from scraper.services.full_scraper import scrape_full, FullScrapeReport
from scraper.services.scraper_service import scrape_category


def ensure_db() -> None:
    """Initialise la DB (idempotent) au démarrage d'une page."""
    init_db()


@st.cache_resource(show_spinner=False)
def get_scheduler() -> SchedulerService:
    """Singleton scheduler, persistant entre les reruns Streamlit.

    `cache_resource` garantit qu'un seul scheduler tourne pour toute la
    durée du process Streamlit.
    """
    return SchedulerService.get()


def format_price(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"{cents / 100:.2f} €"


def format_pct(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1%}"


def format_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


def price_change_pct(first_cents: int | None, last_cents: int | None) -> float | None:
    if first_cents is None or last_cents is None or first_cents == 0:
        return None
    return (last_cents - first_cents) / first_cents


def run_full_scrape(platforms: list[str] | None = None) -> dict:
    """Lance un scraping AJAX (plateformes choisies ou toutes)."""
    queries = queries_for_platforms(platforms) if platforms else None
    report = asyncio.run(scrape_full(queries=queries))
    return {
        "unique": report.articles_unique,
        "created": report.articles_created,
        "updated": report.articles_updated,
        "snapshots": report.snapshots_written,
        "queries": report.queries_done,
    }


def run_scrape(category_slug: str, pages: int) -> dict:
    """Lance un scraping synchrone depuis Streamlit."""
    report = asyncio.run(scrape_category(category_slug, max_pages=pages))
    return {
        "category": report.category,
        "pages": report.pages_fetched,
        "unique": report.articles_unique,
        "created": report.articles_created,
        "updated": report.articles_updated,
        "snapshots": report.snapshots_written,
        "skipped_dup": report.articles_skipped_dup,
        "stopped_reason": report.stopped_reason,
    }


def category_options() -> list[str]:
    return [c.slug for c in CATEGORIES]


def category_label(slug: str) -> str:
    for c in CATEGORIES:
        if c.slug == slug:
            return c.label
    return slug


def category_format(slug: str) -> str:
    """Renvoie 'label (slug)' pour les selectbox."""
    cat = CATEGORIES_BY_SLUG.get(slug)
    if cat is None:
        return slug
    return f"{cat.label}  —  {slug}"


def sidebar_footer() -> None:
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Easycash Tracker — {settings.base_url}")
    st.sidebar.caption(f"DB : `{settings.database_url.split('///')[-1]}`")


__all__ = [
    "ensure_db",
    "get_scheduler",
    "format_price",
    "format_pct",
    "format_datetime",
    "price_change_pct",
    "run_scrape",
    "category_options",
    "category_label",
    "sidebar_footer",
    "session_scope",
    "ArticleRepository",
    "WatchRepository",
    "AlertRepository",
    "ScheduledJobRepository",
    "SchedulerService",
    "Article",
    "PriceSnapshot",
]
