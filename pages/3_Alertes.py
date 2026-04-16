"""Page Alertes — historique des alertes + actions."""

from __future__ import annotations

import streamlit as st

from scraper.db.models import Alert
from scraper.services.discord_notifier import send_alert
from scraper.ui.helpers import (
    AlertRepository,
    ArticleRepository,
    ensure_db,
    format_datetime,
    format_price,
    session_scope,
    sidebar_footer,
)

st.set_page_config(page_title="Alertes — Easycash Tracker", layout="wide")

ensure_db()
st.title("Alertes")
st.caption(
    "Historique des baisses détectées et matches de recherche. "
    "L'envoi Discord s'active automatiquement si `DISCORD_WEBHOOK_URL` est défini dans `.env`."
)

with session_scope() as session:
    alert_repo = AlertRepository(session)
    article_repo = ArticleRepository(session)
    alerts = alert_repo.list_recent(limit=100)
    rows = []
    for a in alerts:
        article = article_repo.get(a.article_id) if a.article_id else None
        rows.append(
            {
                "id": a.id,
                "type": a.type,
                "message": a.message,
                "price_cents": a.price_cents,
                "previous_price_cents": a.previous_price_cents,
                "triggered_at": a.triggered_at,
                "sent_discord": a.sent_to_discord_at is not None,
                "read": a.read,
                "article_id": article.id if article else None,
                "article_title": article.title if article else None,
                "article_url": article.url if article else None,
                "article_platform": article.platform if article else None,
            }
        )

if not rows:
    st.info("Aucune alerte déclenchée pour l'instant.")
    sidebar_footer()
    st.stop()


def mark_as_read(alert_id: int) -> None:
    with session_scope() as session:
        AlertRepository(session).mark_read(alert_id)


def resend_to_discord(alert_id: int) -> bool:
    with session_scope() as session:
        alert = session.get(Alert, alert_id)
        if alert is None:
            return False
        article_repo = ArticleRepository(session)
        article = article_repo.get(alert.article_id) if alert.article_id else None
        ok = send_alert(
            alert,
            article_title=article.title if article else None,
            article_url=article.url if article else None,
            article_platform=article.platform if article else None,
        )
        if ok:
            from scraper.db.models import utcnow
            alert.sent_to_discord_at = utcnow()
        return ok


# Compteur en tête
unread = sum(1 for r in rows if not r["read"])
cols = st.columns(3)
cols[0].metric("Total (100 max)", len(rows))
cols[1].metric("Non lues", unread)
cols[2].metric("Envoyées Discord", sum(1 for r in rows if r["sent_discord"]))

st.divider()

for r in rows:
    bg = None if r["read"] else "blue"
    with st.container(border=True):
        cols = st.columns([5, 1, 1, 1])
        title = r["article_title"] or "(article inconnu)"
        url = r["article_url"] or "#"
        prefix = "🔻" if r["type"] == "PRICE_DROP" else ("🆕" if r["type"] == "NEW_MATCH" else "🔔")
        cols[0].markdown(f"{prefix} **[{title}]({url})**")
        type_label = r["type"].replace("_", " ").title()
        cols[1].caption(type_label)
        if r["previous_price_cents"] and r["price_cents"]:
            cols[2].markdown(
                f"~~{format_price(r['previous_price_cents'])}~~ → **{format_price(r['price_cents'])}**"
            )
        else:
            cols[2].markdown(format_price(r["price_cents"]))
        cols[3].caption(format_datetime(r["triggered_at"]))

        if r["message"]:
            st.caption(r["message"])

        action_cols = st.columns([1, 1, 3, 1, 1])
        if r["article_id"]:
            action_cols[0].link_button("Détail", f"/Watchlist?article={r['article_id']}", use_container_width=True)
        if r["sent_discord"]:
            action_cols[1].caption("📨 Discord envoyé")
        else:
            if action_cols[1].button("Envoyer Discord", key=f"send_{r['id']}", use_container_width=True):
                ok = resend_to_discord(r["id"])
                if ok:
                    st.toast("Envoyé sur Discord", icon="✅")
                else:
                    st.toast("Échec Discord (vérifie le webhook)", icon="⚠️")
                st.rerun()
        if not r["read"]:
            if action_cols[4].button("Marquer lu", key=f"read_{r['id']}", use_container_width=True):
                mark_as_read(r["id"])
                st.rerun()
        else:
            action_cols[4].caption("✓ lue")

sidebar_footer()
