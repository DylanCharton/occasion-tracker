"""Tests du repository : upsert et snapshots de prix."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scraper.db.models import Base
from scraper.db.repository import ArticleRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _upsert(repo: ArticleRepository, **overrides):
    defaults = dict(
        ext_ref="005168034",
        title="Spider-Man 2 PS5",
        url="https://bons-plans.easycash.fr/jeux-video/spider-man-2-ps5-005168034",
        category="jeux-video",
        brand="SONY",
        platform="PS5",
        image_url=None,
    )
    defaults.update(overrides)
    return repo.upsert(**defaults)


def test_upsert_creates_new_article(session):
    repo = ArticleRepository(session)
    article, created = _upsert(repo)
    assert created is True
    assert article.id is not None
    assert article.ext_ref == "005168034"


def test_upsert_updates_existing(session):
    repo = ArticleRepository(session)
    first, _ = _upsert(repo)
    session.commit()
    second, created = _upsert(repo, title="Spider-Man 2 PS5 (MAJ)")
    assert created is False
    assert second.id == first.id
    assert second.title == "Spider-Man 2 PS5 (MAJ)"


def test_record_price_writes_first_snapshot(session):
    repo = ArticleRepository(session)
    article, _ = _upsert(repo)
    snap = repo.record_price(article, price_cents=3499)
    assert snap is not None
    assert snap.price_cents == 3499


def test_record_price_skipped_if_unchanged(session):
    repo = ArticleRepository(session)
    article, _ = _upsert(repo)
    first = repo.record_price(article, price_cents=3499)
    assert first is not None
    second = repo.record_price(article, price_cents=3499)
    assert second is None  # même prix, < 23h => ignoré


def test_record_price_written_on_change(session):
    repo = ArticleRepository(session)
    article, _ = _upsert(repo)
    repo.record_price(article, price_cents=3499)
    snap2 = repo.record_price(article, price_cents=2999)
    assert snap2 is not None
    assert snap2.price_cents == 2999


def test_mark_disappeared_deactivates_unseen_articles(session):
    repo = ArticleRepository(session)
    a1, _ = _upsert(repo, ext_ref="000000001", title="A", url="u1")
    a2, _ = _upsert(repo, ext_ref="000000002", title="B", url="u2")
    session.commit()

    # Seul a1 est revu
    count = repo.mark_disappeared(["000000001"], category="jeux-video")
    assert count == 1
    session.refresh(a1)
    session.refresh(a2)
    assert a1.active is True
    assert a2.active is False
