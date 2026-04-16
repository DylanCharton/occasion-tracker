"""Helpers partagés par les pages Streamlit."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Iterable

import streamlit as st

from scraper.config import settings
from scraper.core.categories import CATEGORIES
from scraper.db.models import Article, PriceSnapshot
from scraper.db.repository import (
    AlertRepository,
    ArticleRepository,
    ScheduledJobRepository,
    WatchRepository,
)
from scraper.db.session import init_db, session_scope
from scraper.services.scheduler_service import SchedulerService
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


def run_scrape(category_slug: str, pages: int) -> dict:
    """Lance un scraping synchrone depuis Streamlit."""
    report = asyncio.run(scrape_category(category_slug, max_pages=pages))
    return {
        "category": report.category,
        "pages": report.pages_fetched,
        "seen": report.articles_seen,
        "created": report.articles_created,
        "updated": report.articles_updated,
        "snapshots": report.snapshots_written,
    }


def category_options() -> list[str]:
    return [c.slug for c in CATEGORIES]


def category_label(slug: str) -> str:
    for c in CATEGORIES:
        if c.slug == slug:
            return c.label
    return slug


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
