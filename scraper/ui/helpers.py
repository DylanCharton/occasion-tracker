"""Helpers partagés par les pages Streamlit."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Iterable

import streamlit as st

from scraper.config import settings
from scraper.core.categories import CATEGORIES, CATEGORIES_BY_SLUG
from scraper.db.models import Article, PriceSnapshot, User
from scraper.db.repository import (
    AlertRepository,
    ArticleRepository,
    ScheduledJobRepository,
    UserRepository,
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


def _authenticated_email() -> str | None:
    """Retourne l'email du viewer Streamlit Cloud, ou None si pas loggé.

    Supporte les deux APIs (st.user récent et st.experimental_user plus ancien).
    Renvoie None en local (pas de Viewer authentication configurée).
    """
    for attr in ("user", "experimental_user"):
        user = getattr(st, attr, None)
        if user is None:
            continue
        try:
            email = getattr(user, "email", None)
        except Exception:
            email = None
        if email:
            return str(email)
    return None


def _resolve_email() -> str:
    """Email effectif du user : SSO Streamlit, sinon fallback dev."""
    email = _authenticated_email()
    if email:
        return email
    return settings.dev_user_email


@st.cache_data(ttl=60, show_spinner=False)
def _user_snapshot(email: str) -> tuple[int, str, bool]:
    """Get-or-create le user et mémorise (id, email, is_admin) 60s.

    Cache-friendly : évite un roundtrip DB à chaque rerun Streamlit. La TTL
    de 60s permet qu'une promotion admin soit visible rapidement.
    """
    email_norm = email.lower().strip()
    is_admin = email_norm in settings.admin_emails_set
    with session_scope() as session:
        user = UserRepository(session).get_or_create(email_norm, is_admin=is_admin)
        # Assure la promotion si l'email vient d'être ajouté à admin_emails
        if is_admin and not user.is_admin:
            user.is_admin = True
        return user.id, user.email, user.is_admin


def current_user_id() -> int:
    """Id du user courant (SSO Streamlit Cloud ou fallback local)."""
    uid, _, _ = _user_snapshot(_resolve_email())
    return uid


def current_user() -> User:
    """Objet User courant (détaché — sûr à utiliser hors session)."""
    uid, email, is_admin = _user_snapshot(_resolve_email())
    user = User(id=uid, email=email, is_admin=is_admin)
    return user


def is_admin() -> bool:
    _, _, admin = _user_snapshot(_resolve_email())
    return admin


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
    user = current_user()
    badge = " · admin" if user.is_admin else ""
    st.sidebar.caption(f"Connecté : **{user.email}**{badge}")
    st.sidebar.caption(f"Easycash Tracker — {settings.base_url}")


__all__ = [
    "ensure_db",
    "current_user",
    "current_user_id",
    "is_admin",
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
    "UserRepository",
    "SchedulerService",
    "Article",
    "PriceSnapshot",
    "User",
]
