"""Repository : accès BDD pour Article, PriceSnapshot, Watch, Alert.

Règles métier clés :
- upsert par ext_ref (id 9 chiffres Easycash).
- un snapshot prix n'est écrit que si le prix a changé ou que le dernier
  snapshot date de plus d'un jour (pour avoir un point récent quand même).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from sqlalchemy import and_, or_, select, func
from sqlalchemy.orm import Session

from scraper.db.models import (
    Alert,
    AlertType,
    Article,
    PriceSnapshot,
    ScheduledJob,
    User,
    Watch,
    WatchType,
    utcnow,
)


# Seuil au-delà duquel on force un nouveau snapshot même si le prix n'a pas bougé.
SNAPSHOT_MIN_INTERVAL = timedelta(hours=23)


class ArticleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ Articles

    def get(self, article_id: int) -> Article | None:
        return self.session.get(Article, article_id)

    def get_by_ext_ref(self, ext_ref: str) -> Article | None:
        return self.session.scalar(select(Article).where(Article.ext_ref == ext_ref))

    def upsert(
        self,
        *,
        ext_ref: str,
        title: str,
        url: str,
        category: str,
        brand: str | None = None,
        platform: str | None = None,
        image_url: str | None = None,
    ) -> tuple[Article, bool]:
        """Insère ou met à jour un article. Retourne (article, created)."""
        article = self.get_by_ext_ref(ext_ref)
        now = utcnow()
        created = False
        if article is None:
            article = Article(
                ext_ref=ext_ref,
                title=title,
                url=url,
                category=category,
                brand=brand,
                platform=platform,
                image_url=image_url,
                first_seen_at=now,
                last_seen_at=now,
                active=True,
            )
            self.session.add(article)
            self.session.flush()
            created = True
        else:
            article.title = title
            article.url = url
            article.category = category
            if brand:
                article.brand = brand
            if platform:
                article.platform = platform
            if image_url:
                article.image_url = image_url
            article.last_seen_at = now
            article.active = True
        return article, created

    def mark_disappeared(self, ext_refs_seen: Iterable[str], category: str) -> int:
        """Marque inactif les articles d'une catégorie non vus lors du dernier scan."""
        seen = set(ext_refs_seen)
        stmt = select(Article).where(Article.category == category, Article.active.is_(True))
        articles = list(self.session.scalars(stmt))
        count = 0
        for article in articles:
            if article.ext_ref not in seen:
                article.active = False
                count += 1
        return count

    def list_recent(self, limit: int = 50) -> Sequence[Article]:
        stmt = select(Article).order_by(Article.last_seen_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(Article)) or 0

    def search(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        platform: str | None = None,
        min_price_cents: int | None = None,
        max_price_cents: int | None = None,
        only_active: bool = True,
        limit: int = 100,
        order_by: str = "last_seen_desc",
    ) -> Sequence[Article]:
        """Recherche filtrée d'articles. Filtre sur le dernier snapshot pour les prix."""
        # Sous-requête : dernier snapshot par article
        last_snap_sq = (
            select(
                PriceSnapshot.article_id.label("aid"),
                func.max(PriceSnapshot.scraped_at).label("last"),
            )
            .group_by(PriceSnapshot.article_id)
            .subquery()
        )

        stmt = (
            select(Article, PriceSnapshot)
            .join(last_snap_sq, last_snap_sq.c.aid == Article.id, isouter=True)
            .join(
                PriceSnapshot,
                and_(
                    PriceSnapshot.article_id == Article.id,
                    PriceSnapshot.scraped_at == last_snap_sq.c.last,
                ),
                isouter=True,
            )
        )

        conditions = []
        if only_active:
            conditions.append(Article.active.is_(True))
        if query:
            like = f"%{query.lower()}%"
            conditions.append(func.lower(Article.title).like(like))
        if category:
            conditions.append(Article.category == category)
        if platform:
            conditions.append(Article.platform == platform)
        if min_price_cents is not None:
            conditions.append(PriceSnapshot.price_cents >= min_price_cents)
        if max_price_cents is not None:
            conditions.append(PriceSnapshot.price_cents <= max_price_cents)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        if order_by == "price_asc":
            stmt = stmt.order_by(PriceSnapshot.price_cents.asc().nullslast())
        elif order_by == "price_desc":
            stmt = stmt.order_by(PriceSnapshot.price_cents.desc().nullslast())
        elif order_by == "title":
            stmt = stmt.order_by(Article.title.asc())
        elif order_by == "first_seen_desc":
            stmt = stmt.order_by(Article.first_seen_at.desc())
        else:
            stmt = stmt.order_by(Article.last_seen_at.desc())

        stmt = stmt.limit(limit)
        rows = self.session.execute(stmt).all()
        # On retourne seulement les Article ; les callers appelleront last_snapshot si besoin
        return [row[0] for row in rows]

    def distinct_platforms(self) -> list[str]:
        stmt = select(Article.platform).where(Article.platform.is_not(None)).distinct()
        return sorted(p for p in self.session.scalars(stmt) if p)

    def distinct_categories(self) -> list[str]:
        stmt = select(Article.category).distinct()
        return sorted(self.session.scalars(stmt))

    # ------------------------------------------------------------------ Snapshots

    def last_snapshot(self, article_id: int) -> PriceSnapshot | None:
        stmt = (
            select(PriceSnapshot)
            .where(PriceSnapshot.article_id == article_id)
            .order_by(PriceSnapshot.scraped_at.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def first_snapshot(self, article_id: int) -> PriceSnapshot | None:
        stmt = (
            select(PriceSnapshot)
            .where(PriceSnapshot.article_id == article_id)
            .order_by(PriceSnapshot.scraped_at.asc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def price_history(self, article_id: int) -> Sequence[PriceSnapshot]:
        stmt = (
            select(PriceSnapshot)
            .where(PriceSnapshot.article_id == article_id)
            .order_by(PriceSnapshot.scraped_at.asc())
        )
        return list(self.session.scalars(stmt))

    def record_price(
        self,
        article: Article,
        *,
        price_cents: int,
        available: bool = True,
        currency: str = "EUR",
    ) -> PriceSnapshot | None:
        """Crée un snapshot si le prix a changé ou si le dernier date d'> 23h.

        Retourne le snapshot créé, ou None s'il a été jugé redondant.
        """
        last = self.last_snapshot(article.id)
        now = utcnow()
        should_write = (
            last is None
            or last.price_cents != price_cents
            or last.available != available
            or (now - last.scraped_at) > SNAPSHOT_MIN_INTERVAL
        )
        if not should_write:
            return None

        snap = PriceSnapshot(
            article_id=article.id,
            price_cents=price_cents,
            currency=currency,
            available=available,
            scraped_at=now,
        )
        self.session.add(snap)
        self.session.flush()
        return snap

    def recent_price_drops(self, limit: int = 10) -> list[tuple[Article, PriceSnapshot, PriceSnapshot]]:
        """Retourne les articles avec une baisse de prix entre les 2 derniers snapshots."""
        # Approche simple : parcourir les articles qui ont au moins 2 snapshots
        stmt = (
            select(Article.id)
            .join(PriceSnapshot, PriceSnapshot.article_id == Article.id)
            .group_by(Article.id)
            .having(func.count(PriceSnapshot.id) >= 2)
        )
        article_ids = list(self.session.scalars(stmt))
        drops: list[tuple[Article, PriceSnapshot, PriceSnapshot]] = []
        for aid in article_ids:
            history = self.price_history(aid)
            if len(history) < 2:
                continue
            previous, latest = history[-2], history[-1]
            if latest.price_cents < previous.price_cents:
                article = self.get(aid)
                if article is not None:
                    drops.append((article, previous, latest))
        drops.sort(key=lambda t: t[2].scraped_at, reverse=True)
        return drops[:limit]


class WatchRepository:
    """Gestion de la watchlist : articles suivis et alertes-recherche.

    Toutes les opérations sont scopées à un `user_id`. Deux utilisateurs
    distincts peuvent avoir chacun une watch sur le même article.
    """

    def __init__(self, session: Session, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    def add_article_watch(
        self,
        article_id: int,
        *,
        threshold_price_cents: int | None = None,
        threshold_drop_pct: float | None = None,
    ) -> Watch:
        """Ajoute un article à la watchlist du user courant (idempotent)."""
        existing = self.session.scalar(
            select(Watch).where(
                Watch.user_id == self.user_id,
                Watch.type == WatchType.ARTICLE.value,
                Watch.article_id == article_id,
                Watch.active.is_(True),
            )
        )
        if existing is not None:
            if threshold_price_cents is not None:
                existing.threshold_price_cents = threshold_price_cents
            if threshold_drop_pct is not None:
                existing.threshold_drop_pct = threshold_drop_pct
            return existing

        watch = Watch(
            user_id=self.user_id,
            type=WatchType.ARTICLE.value,
            article_id=article_id,
            threshold_price_cents=threshold_price_cents,
            threshold_drop_pct=threshold_drop_pct,
            active=True,
        )
        self.session.add(watch)
        self.session.flush()
        return watch

    def update_thresholds(
        self,
        watch_id: int,
        *,
        threshold_price_cents: int | None = None,
        threshold_drop_pct: float | None = None,
    ) -> Watch | None:
        watch = self._get_owned(watch_id)
        if watch is None:
            return None
        watch.threshold_price_cents = threshold_price_cents
        watch.threshold_drop_pct = threshold_drop_pct
        return watch

    def get_article_watch(self, article_id: int) -> Watch | None:
        return self.session.scalar(
            select(Watch).where(
                Watch.user_id == self.user_id,
                Watch.type == WatchType.ARTICLE.value,
                Watch.article_id == article_id,
                Watch.active.is_(True),
            )
        )

    def add_search_watch(
        self,
        query: dict,
        *,
        threshold_price_cents: int | None = None,
    ) -> Watch:
        watch = Watch(
            user_id=self.user_id,
            type=WatchType.SEARCH.value,
            query_json=json.dumps(query, ensure_ascii=False),
            threshold_price_cents=threshold_price_cents,
            active=True,
        )
        self.session.add(watch)
        self.session.flush()
        return watch

    def remove(self, watch_id: int) -> bool:
        watch = self._get_owned(watch_id)
        if watch is None:
            return False
        watch.active = False
        return True

    def remove_article(self, article_id: int) -> int:
        """Désactive les watches du user courant pointant vers cet article."""
        stmt = select(Watch).where(
            Watch.user_id == self.user_id,
            Watch.type == WatchType.ARTICLE.value,
            Watch.article_id == article_id,
            Watch.active.is_(True),
        )
        watches = list(self.session.scalars(stmt))
        for w in watches:
            w.active = False
        return len(watches)

    def is_watched(self, article_id: int) -> bool:
        stmt = select(func.count()).select_from(Watch).where(
            Watch.user_id == self.user_id,
            Watch.type == WatchType.ARTICLE.value,
            Watch.article_id == article_id,
            Watch.active.is_(True),
        )
        return (self.session.scalar(stmt) or 0) > 0

    def list_article_watches(self) -> list[tuple[Watch, Article]]:
        stmt = (
            select(Watch, Article)
            .join(Article, Article.id == Watch.article_id)
            .where(
                Watch.user_id == self.user_id,
                Watch.type == WatchType.ARTICLE.value,
                Watch.active.is_(True),
            )
            .order_by(Watch.created_at.desc())
        )
        return [(w, a) for w, a in self.session.execute(stmt).all()]

    def list_search_watches(self) -> list[Watch]:
        stmt = (
            select(Watch)
            .where(
                Watch.user_id == self.user_id,
                Watch.type == WatchType.SEARCH.value,
                Watch.active.is_(True),
            )
            .order_by(Watch.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def count_active(self) -> int:
        stmt = select(func.count()).select_from(Watch).where(
            Watch.user_id == self.user_id,
            Watch.active.is_(True),
        )
        return self.session.scalar(stmt) or 0

    def _get_owned(self, watch_id: int) -> Watch | None:
        """Retourne la watch seulement si elle appartient au user courant."""
        return self.session.scalar(
            select(Watch).where(Watch.id == watch_id, Watch.user_id == self.user_id)
        )


class AlertRepository:
    """Scopé à un user : on ne voit que ses propres alertes.

    Passer user_id=None explicite pour un contexte système (scheduler,
    detection) qui a besoin d'écrire/lire les alertes de tous les users.
    """

    def __init__(self, session: Session, user_id: int | None) -> None:
        self.session = session
        self.user_id = user_id

    def create(
        self,
        *,
        user_id: int,
        watch_id: int,
        type: AlertType,
        message: str,
        article_id: int | None = None,
        price_cents: int | None = None,
        previous_price_cents: int | None = None,
    ) -> Alert:
        alert = Alert(
            user_id=user_id,
            watch_id=watch_id,
            type=type.value,
            message=message,
            article_id=article_id,
            price_cents=price_cents,
            previous_price_cents=previous_price_cents,
        )
        self.session.add(alert)
        self.session.flush()
        return alert

    def list_recent(self, limit: int = 50) -> Sequence[Alert]:
        stmt = select(Alert).order_by(Alert.triggered_at.desc()).limit(limit)
        if self.user_id is not None:
            stmt = stmt.where(Alert.user_id == self.user_id)
        return list(self.session.scalars(stmt))

    def mark_read(self, alert_id: int) -> bool:
        stmt = select(Alert).where(Alert.id == alert_id)
        if self.user_id is not None:
            stmt = stmt.where(Alert.user_id == self.user_id)
        alert = self.session.scalar(stmt)
        if alert is None:
            return False
        alert.read = True
        return True

    def count_unread(self) -> int:
        stmt = select(func.count()).select_from(Alert).where(Alert.read.is_(False))
        if self.user_id is not None:
            stmt = stmt.where(Alert.user_id == self.user_id)
        return self.session.scalar(stmt) or 0


class UserRepository:
    """Get-or-create par email (flux SSO Streamlit Cloud)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.lower()))

    def get_or_create(self, email: str, *, is_admin: bool = False) -> User:
        email_norm = email.lower().strip()
        user = self.get_by_email(email_norm)
        if user is not None:
            return user
        user = User(email=email_norm, is_admin=is_admin)
        self.session.add(user)
        self.session.flush()
        return user

    def set_discord_webhook(self, user_id: int, url: str | None) -> User | None:
        user = self.session.get(User, user_id)
        if user is None:
            return None
        user.discord_webhook_url = url or None
        return user

    def list_all(self) -> Sequence[User]:
        return list(self.session.scalars(select(User).order_by(User.email.asc())))


class ScheduledJobRepository:
    """CRUD pour les jobs de rafraîchissement planifiés."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *, category_slug: str, interval_hours: int, max_pages: int) -> ScheduledJob:
        existing = self.session.scalar(
            select(ScheduledJob).where(ScheduledJob.category_slug == category_slug)
        )
        if existing is not None:
            existing.interval_hours = interval_hours
            existing.max_pages = max_pages
            existing.active = True
            return existing
        job = ScheduledJob(
            category_slug=category_slug,
            interval_hours=interval_hours,
            max_pages=max_pages,
            active=True,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: int) -> ScheduledJob | None:
        return self.session.get(ScheduledJob, job_id)

    def remove(self, job_id: int) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        self.session.delete(job)
        return True

    def set_active(self, job_id: int, active: bool) -> ScheduledJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.active = active
        return job

    def list_all(self, *, only_active: bool = False) -> Sequence[ScheduledJob]:
        stmt = select(ScheduledJob).order_by(ScheduledJob.category_slug.asc())
        if only_active:
            stmt = stmt.where(ScheduledJob.active.is_(True))
        return list(self.session.scalars(stmt))

    def update_run(
        self,
        job_id: int,
        *,
        status: str,
        error: str | None = None,
        at: "datetime | None" = None,
    ) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.last_run_at = at or utcnow()
        job.last_run_status = status
        job.last_error = error
