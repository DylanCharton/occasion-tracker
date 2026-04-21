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


def is_demo_mode() -> bool:
    """Vrai si l'URL contient ?demo=1 (mode vitrine readonly public).

    Court-circuite l'auth : force un user démo factice, masque toutes les
    actions d'écriture (scrape, watches, alerts, webhooks, admin).
    """
    try:
        return st.query_params.get("demo") == "1"
    except Exception:
        return False


def _is_logged_in() -> bool:
    """Vrai si st.user.is_logged_in (Streamlit ≥ 1.42, auth OIDC native)."""
    user = getattr(st, "user", None)
    if user is None:
        return False
    try:
        return bool(getattr(user, "is_logged_in", False))
    except Exception:
        return False


def _authenticated_email() -> str | None:
    """Retourne l'email du viewer loggé via st.login, ou None si pas loggé."""
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
    """Email effectif du user : démo, SSO Streamlit, sinon fallback dev."""
    if is_demo_mode():
        return settings.demo_user_email
    email = _authenticated_email()
    if email:
        return email
    return settings.dev_user_email


def is_readonly() -> bool:
    """Vrai si le user courant ne doit pas pouvoir écrire (mode démo)."""
    return is_demo_mode()


def require_auth() -> None:
    """Gate d'authentification à appeler au début de chaque page.

    - Mode démo (?demo=1) : laisse passer, readonly.
    - Auth désactivée (settings.require_auth=False) : laisse passer (dev local).
    - Sinon : exige st.login("google") + whitelist allowed_emails.

    En cas d'échec, stoppe le rendu avec st.stop().
    """
    if is_demo_mode():
        return

    if not settings.require_auth:
        return

    if not _is_logged_in():
        st.title("🔒 Easycash Tracker")
        st.markdown(
            "Cette application est réservée à un cercle privé. "
            "Connecte-toi avec ton compte Google pour y accéder."
        )
        cols = st.columns(2)
        if cols[0].button("Se connecter avec Google", type="primary", use_container_width=True):
            st.login("google")
        cols[1].link_button(
            "Voir la démo publique", "?demo=1", use_container_width=True
        )
        st.stop()

    email = (_authenticated_email() or "").lower().strip()
    allowed = settings.allowed_emails_set
    if allowed and email not in allowed:
        st.title("🚫 Accès refusé")
        st.error(
            f"L'email `{email}` n'est pas autorisé. "
            f"Contacte l'admin pour être ajouté à la whitelist."
        )
        if st.button("Se déconnecter"):
            st.logout()
        st.stop()


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
    if is_demo_mode():
        st.sidebar.warning("🧪 Mode démo (lecture seule)")
        st.sidebar.link_button("Quitter la démo", "/", use_container_width=True)
    else:
        badge = " · admin" if user.is_admin else ""
        st.sidebar.caption(f"Connecté : **{user.email}**{badge}")
        if _is_logged_in():
            if st.sidebar.button("Se déconnecter", use_container_width=True):
                st.logout()
    st.sidebar.caption(f"Easycash Tracker — {settings.base_url}")


__all__ = [
    "ensure_db",
    "current_user",
    "current_user_id",
    "is_admin",
    "is_demo_mode",
    "is_readonly",
    "require_auth",
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
