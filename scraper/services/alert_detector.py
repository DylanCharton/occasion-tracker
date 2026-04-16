"""Détection d'alertes après un cycle de scraping.

Deux types :
- **ARTICLE watch** : alerte si le prix a baissé au-delà du seuil (pct ou prix absolu).
- **SEARCH watch** : alerte si un nouvel article matche les critères enregistrés.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from scraper.config import settings
from scraper.db.models import Alert, AlertType, Article, PriceSnapshot, Watch, WatchType, utcnow
from scraper.db.repository import AlertRepository, ArticleRepository
from scraper.db.session import session_scope
from scraper.services.discord_notifier import send_alert


# Fenêtre pendant laquelle on considère qu'un article "nouvellement vu" mérite
# un NEW_MATCH (évite d'alerter sur tout le stock existant au 1er run).
NEW_MATCH_WINDOW = timedelta(hours=24)


@dataclass(slots=True)
class DetectionReport:
    price_drops: int = 0
    new_matches: int = 0
    discord_sent: int = 0
    discord_failed: int = 0


def detect_and_notify(ext_refs_seen: set[str] | None = None) -> DetectionReport:
    """Exécute la détection d'alertes sur tous les watches actifs.

    Args:
        ext_refs_seen: optionnellement, ext_refs observés lors du dernier cycle
            de scraping. Si fourni, la détection ARTICLE se concentre sur ces
            articles (optimisation). Sinon, on parcourt toutes les watches.
    """
    report = DetectionReport()
    dispatch: list[tuple[int, str | None, str | None, str | None]] = []
    # (alert_id, article_title, article_url, platform) — à envoyer sur Discord

    with session_scope() as session:
        # --- ARTICLE watches ---------------------------------------------------
        watches = list(session.scalars(
            select(Watch).where(Watch.type == WatchType.ARTICLE.value, Watch.active.is_(True))
        ))
        art_repo = ArticleRepository(session)
        alert_repo = AlertRepository(session)

        for watch in watches:
            article = art_repo.get(watch.article_id) if watch.article_id else None
            if article is None:
                continue
            if ext_refs_seen is not None and article.ext_ref not in ext_refs_seen:
                # l'article n'a pas été vu ce cycle, inutile de recalculer
                continue

            history = art_repo.price_history(article.id)
            if len(history) < 2:
                continue
            prev_snap = history[-2]
            last_snap = history[-1]
            if last_snap.price_cents >= prev_snap.price_cents:
                continue  # pas de baisse

            threshold_pct = (
                watch.threshold_drop_pct
                if watch.threshold_drop_pct is not None
                else settings.default_price_drop_threshold
            )
            drop_pct = (prev_snap.price_cents - last_snap.price_cents) / prev_snap.price_cents
            hit_pct = drop_pct >= threshold_pct
            hit_abs = (
                watch.threshold_price_cents is not None
                and last_snap.price_cents <= watch.threshold_price_cents
            )
            if not (hit_pct or hit_abs):
                continue

            # Dédoublonnage : ne pas alerter deux fois sur le même couple
            # (watch, article, prix actuel) si déjà notifié récemment.
            already = session.scalar(
                select(Alert).where(
                    Alert.watch_id == watch.id,
                    Alert.article_id == article.id,
                    Alert.type == AlertType.PRICE_DROP.value,
                    Alert.price_cents == last_snap.price_cents,
                )
            )
            if already is not None:
                continue

            message = (
                f"{article.title} : {prev_snap.price_cents / 100:.2f} € "
                f"→ {last_snap.price_cents / 100:.2f} € "
                f"({-drop_pct:.1%})"
            )
            alert = alert_repo.create(
                watch_id=watch.id,
                type=AlertType.PRICE_DROP,
                message=message,
                article_id=article.id,
                price_cents=last_snap.price_cents,
                previous_price_cents=prev_snap.price_cents,
            )
            session.flush()
            report.price_drops += 1
            dispatch.append((alert.id, article.title, article.url, article.platform))

        # --- SEARCH watches ----------------------------------------------------
        search_watches = list(session.scalars(
            select(Watch).where(Watch.type == WatchType.SEARCH.value, Watch.active.is_(True))
        ))
        now = utcnow()
        cutoff = now - NEW_MATCH_WINDOW

        for watch in search_watches:
            try:
                criteria = json.loads(watch.query_json or "{}")
            except json.JSONDecodeError:
                logger.warning(f"SEARCH watch #{watch.id} : query_json invalide")
                continue

            results = art_repo.search(
                query=criteria.get("query"),
                category=criteria.get("category"),
                platform=criteria.get("platform"),
                min_price_cents=criteria.get("min_price_cents"),
                max_price_cents=criteria.get("max_price_cents"),
                only_active=criteria.get("only_active", True),
                limit=200,
                order_by="first_seen_desc",
            )

            for article in results:
                # Ne cible que les articles récemment découverts
                if article.first_seen_at < cutoff:
                    continue
                # Dédoublonnage : déjà notifié pour cette watch ?
                already = session.scalar(
                    select(Alert).where(
                        Alert.watch_id == watch.id,
                        Alert.article_id == article.id,
                        Alert.type == AlertType.NEW_MATCH.value,
                    )
                )
                if already is not None:
                    continue

                last_snap = art_repo.last_snapshot(article.id)
                price_cents = last_snap.price_cents if last_snap else None
                message = (
                    f"Nouveau match : {article.title}"
                    + (f" à {price_cents / 100:.2f} €" if price_cents else "")
                )
                alert = alert_repo.create(
                    watch_id=watch.id,
                    type=AlertType.NEW_MATCH,
                    message=message,
                    article_id=article.id,
                    price_cents=price_cents,
                )
                session.flush()
                report.new_matches += 1
                dispatch.append((alert.id, article.title, article.url, article.platform))

    # --- Envoi Discord (hors session pour ne pas la bloquer) -----------------
    if dispatch and settings.discord_webhook_url:
        for alert_id, title, url, platform in dispatch:
            with session_scope() as session:
                alert = session.get(Alert, alert_id)
                if alert is None:
                    continue
                ok = send_alert(
                    alert,
                    article_title=title,
                    article_url=url,
                    article_platform=platform,
                )
                if ok:
                    alert.sent_to_discord_at = utcnow()
                    report.discord_sent += 1
                else:
                    report.discord_failed += 1

    logger.info(
        f"[alerts] {report.price_drops} baisse(s), {report.new_matches} nouveau(x) match(es), "
        f"{report.discord_sent} envoi(s) Discord OK, {report.discord_failed} échec(s)."
    )
    return report
