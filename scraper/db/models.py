"""Modèles SQLAlchemy 2.0 (syntaxe Mapped typée).

Un Article représente un modèle de référence Easycash (fiche catalogue).
Chaque scraping successif crée un PriceSnapshot, permettant l'historisation.

Limitations assumées (cf. README) : l'état et le magasin ne sont pas
exposés par Easycash sur le web public, donc ces champs n'existent pas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Retourne un datetime naïf en UTC.

    SQLite ne préserve pas le tzinfo, on évite donc les datetimes aware
    pour que les comparaisons (lecture vs écriture) restent cohérentes.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class WatchType(str, Enum):
    ARTICLE = "ARTICLE"  # suivi d'un article précis
    SEARCH = "SEARCH"    # alerte sur une recherche (catégorie + filtres)


class AlertType(str, Enum):
    PRICE_DROP = "PRICE_DROP"
    NEW_MATCH = "NEW_MATCH"
    DISAPPEARED = "DISAPPEARED"


class User(Base):
    """Compte utilisateur (identifié par email SSO Google/Streamlit Cloud)."""

    __tablename__ = "app_user"  # "user" est un mot réservé en PostgreSQL

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    discord_webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    watches: Mapped[list["Watch"]] = relationship(back_populates="user")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} admin={self.is_admin}>"


class Article(Base):
    __tablename__ = "article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ext_ref : les 9 chiffres en fin d'URL Easycash, clé naturelle
    ext_ref: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    category: Mapped[str] = mapped_column(String(128), index=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="PriceSnapshot.scraped_at.desc()",
    )
    watches: Mapped[list["Watch"]] = relationship(back_populates="article")

    def __repr__(self) -> str:
        return f"<Article id={self.id} ext_ref={self.ext_ref} title={self.title[:40]!r}>"


class PriceSnapshot(Base):
    __tablename__ = "price_snapshot"
    __table_args__ = (
        Index("ix_snapshot_article_scraped", "article_id", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("article.id", ondelete="CASCADE"), index=True
    )
    price_cents: Mapped[int] = mapped_column(Integer)  # en centimes, évite les flottants
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    article: Mapped[Article] = relationship(back_populates="price_snapshots")

    @property
    def price(self) -> float:
        return self.price_cents / 100


class Watch(Base):
    __tablename__ = "watch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(16))  # WatchType
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("article.id", ondelete="CASCADE"), nullable=True
    )
    query_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threshold_drop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="watches")
    article: Mapped[Article | None] = relationship(back_populates="watches")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="watch", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    watch_id: Mapped[int] = mapped_column(ForeignKey("watch.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("article.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32))  # AlertType
    message: Mapped[str] = mapped_column(Text)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_to_discord_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="alerts")
    watch: Mapped[Watch] = relationship(back_populates="alerts")


class ScheduledJob(Base):
    """Job de rafraîchissement périodique d'une catégorie."""

    __tablename__ = "scheduled_job"
    __table_args__ = (
        UniqueConstraint("category_slug", name="uq_scheduled_job_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_slug: Mapped[str] = mapped_column(String(128))
    interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    max_pages: Mapped[int] = mapped_column(Integer, default=3)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "OK" | "ERROR"
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return (
            f"<ScheduledJob id={self.id} cat={self.category_slug} "
            f"every={self.interval_hours}h pages={self.max_pages} active={self.active}>"
        )


__all__ = [
    "Base",
    "User",
    "Article",
    "PriceSnapshot",
    "Watch",
    "Alert",
    "ScheduledJob",
    "WatchType",
    "AlertType",
    "utcnow",
]
