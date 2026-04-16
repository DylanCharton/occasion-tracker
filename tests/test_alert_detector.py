"""Tests du détecteur d'alertes : baisses (ARTICLE) + nouveaux matches (SEARCH)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scraper.db.models import (
    Alert,
    AlertType,
    Article,
    Base,
    PriceSnapshot,
    Watch,
    WatchType,
    utcnow,
)


@pytest.fixture
def patch_session(monkeypatch):
    """Remplace session_scope dans alert_detector par une SQLite en mémoire partagée."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    from contextlib import contextmanager

    @contextmanager
    def scope():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # Patche les deux imports qui utilisent session_scope
    import scraper.services.alert_detector as mod

    monkeypatch.setattr(mod, "session_scope", scope)
    yield SessionLocal
    engine.dispose()


def _create_article(session, **kwargs) -> Article:
    defaults = dict(
        ext_ref="000000001",
        title="Jeu test",
        url="https://example.com/jeu",
        category="jeux-video",
        platform="PS5",
        brand="TEST",
    )
    defaults.update(kwargs)
    article = Article(**defaults)
    session.add(article)
    session.flush()
    return article


def _add_snapshot(session, article: Article, price_cents: int, offset_minutes: int = 0) -> PriceSnapshot:
    snap = PriceSnapshot(
        article_id=article.id,
        price_cents=price_cents,
        currency="EUR",
        available=True,
        scraped_at=utcnow() + timedelta(minutes=offset_minutes),
    )
    session.add(snap)
    session.flush()
    return snap


def test_price_drop_triggers_alert_above_threshold(patch_session):
    """Baisse de 20% avec seuil à 5% → alerte créée."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session)
    _add_snapshot(session, article, price_cents=5000, offset_minutes=-10)
    _add_snapshot(session, article, price_cents=4000, offset_minutes=0)
    watch = Watch(
        type=WatchType.ARTICLE.value,
        article_id=article.id,
        threshold_drop_pct=0.05,
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report = detect_and_notify()

    assert report.price_drops == 1

    session = patch_session()
    alerts = session.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].type == AlertType.PRICE_DROP.value
    assert alerts[0].previous_price_cents == 5000
    assert alerts[0].price_cents == 4000


def test_price_drop_below_threshold_no_alert(patch_session):
    """Baisse de 2% avec seuil à 5% → pas d'alerte."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session)
    _add_snapshot(session, article, price_cents=5000, offset_minutes=-10)
    _add_snapshot(session, article, price_cents=4900, offset_minutes=0)  # -2%
    watch = Watch(
        type=WatchType.ARTICLE.value,
        article_id=article.id,
        threshold_drop_pct=0.05,
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report = detect_and_notify()

    assert report.price_drops == 0


def test_price_drop_absolute_threshold_triggers(patch_session):
    """Prix descend au seuil absolu (même si la baisse pct est petite) → alerte."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session)
    _add_snapshot(session, article, price_cents=3100, offset_minutes=-10)
    _add_snapshot(session, article, price_cents=3000, offset_minutes=0)  # seulement -3%
    watch = Watch(
        type=WatchType.ARTICLE.value,
        article_id=article.id,
        threshold_drop_pct=0.10,  # 10%, non atteint
        threshold_price_cents=3000,  # mais le seuil absolu, oui
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report = detect_and_notify()

    assert report.price_drops == 1


def test_price_drop_not_duplicated(patch_session):
    """Appelé deux fois de suite, ne crée pas de doublon pour le même prix."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session)
    _add_snapshot(session, article, price_cents=5000, offset_minutes=-10)
    _add_snapshot(session, article, price_cents=4000, offset_minutes=0)
    watch = Watch(
        type=WatchType.ARTICLE.value,
        article_id=article.id,
        threshold_drop_pct=0.05,
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report1 = detect_and_notify()
        report2 = detect_and_notify()

    assert report1.price_drops == 1
    assert report2.price_drops == 0

    session = patch_session()
    assert session.query(Alert).count() == 1


def test_inactive_watch_does_not_trigger(patch_session):
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session)
    _add_snapshot(session, article, price_cents=5000, offset_minutes=-10)
    _add_snapshot(session, article, price_cents=4000, offset_minutes=0)
    watch = Watch(
        type=WatchType.ARTICLE.value,
        article_id=article.id,
        threshold_drop_pct=0.05,
        active=False,  # inactif
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report = detect_and_notify()

    assert report.price_drops == 0


def test_search_watch_matches_new_article(patch_session):
    """Un SEARCH watch match un article nouvellement découvert."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session, title="Zelda Breath of the Wild Switch", platform="Switch")
    _add_snapshot(session, article, price_cents=2999, offset_minutes=0)
    watch = Watch(
        type=WatchType.SEARCH.value,
        query_json='{"query": "zelda", "platform": "Switch"}',
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report = detect_and_notify()

    assert report.new_matches == 1

    session = patch_session()
    alert = session.query(Alert).first()
    assert alert is not None
    assert alert.type == AlertType.NEW_MATCH.value


def test_search_watch_skips_old_articles(patch_session):
    """Un article vu > 24h ne doit PAS déclencher de NEW_MATCH."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = Article(
        ext_ref="000000042",
        title="Zelda Ocarina of Time 3DS",
        url="https://example.com",
        category="jeux-video",
        platform="3DS",
        first_seen_at=utcnow() - timedelta(days=5),
        last_seen_at=utcnow(),
        active=True,
    )
    session.add(article)
    session.flush()
    _add_snapshot(session, article, price_cents=1999, offset_minutes=0)
    watch = Watch(
        type=WatchType.SEARCH.value,
        query_json='{"query": "zelda"}',
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        report = detect_and_notify()

    assert report.new_matches == 0


def test_search_watch_not_duplicated(patch_session):
    """Deux passes consécutives ne créent pas deux alertes pour le même article."""
    from scraper.services.alert_detector import detect_and_notify

    session = patch_session()
    article = _create_article(session, title="Mario Odyssey Switch", platform="Switch")
    _add_snapshot(session, article, price_cents=2999, offset_minutes=0)
    watch = Watch(
        type=WatchType.SEARCH.value,
        query_json='{"query": "mario", "platform": "Switch"}',
        active=True,
    )
    session.add(watch)
    session.commit()
    session.close()

    with patch("scraper.services.alert_detector.send_alert", return_value=False):
        r1 = detect_and_notify()
        r2 = detect_and_notify()

    assert r1.new_matches == 1
    assert r2.new_matches == 0
