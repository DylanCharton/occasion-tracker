"""Session SQLAlchemy et initialisation de la DB.

Supporte deux backends :
- **SQLite** (dev local) : `sqlite:///path/to/db.sqlite`
- **PostgreSQL** (Supabase cloud) : `postgresql+psycopg2://user:pass@host:port/dbname`

Le backend est sélectionné depuis `settings.database_url`.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from scraper.config import settings
from scraper.db.models import Base


def _ensure_sqlite_dir(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        db_path = Path(url[len(prefix):])
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _build_engine(url: str) -> Engine:
    """Configure l'engine selon le dialecte."""
    kwargs: dict[str, Any] = {"future": True}

    if url.startswith("sqlite"):
        # SQLite + threads (scheduler APScheduler) : autoriser le multi-thread
        kwargs["connect_args"] = {"check_same_thread": False}
    elif url.startswith(("postgresql", "postgres")):
        # Supabase peut couper les connexions idle (pooler). pre_ping teste
        # la connexion avant chaque checkout pour éviter les erreurs transientes.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800  # 30 min, sous la fenêtre du pooler Supabase

    return create_engine(url, **kwargs)


_ensure_sqlite_dir(settings.database_url)
engine = _build_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Crée toutes les tables (idempotent).

    Utilisé uniquement en dev local pour un démarrage rapide sans Alembic.
    En production (Supabase), la source de vérité est Alembic (`alembic upgrade head`).
    """
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager : ouvre/commite/rollback/ferme une session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
