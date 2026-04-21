"""Page Watchlist : articles suivis + détail + graphe d'historique."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from scraper.ui.helpers import (
    ArticleRepository,
    WatchRepository,
    current_user_id,
    ensure_db,
    format_datetime,
    format_price,
    is_readonly,
    price_change_pct,
    require_auth,
    session_scope,
    sidebar_footer,
)

st.set_page_config(page_title="Watchlist — Occasion Tracker", layout="wide")

ensure_db()
require_auth()
uid = current_user_id()
st.title("Watchlist")
st.caption("Les articles que tu suis et leur évolution de prix.")

# On utilise ?article=<id> comme paramètre pour ouvrir le détail d'un article.
selected_id_raw = st.query_params.get("article")
selected_article_id: int | None = None
if selected_id_raw:
    try:
        selected_article_id = int(selected_id_raw)
    except (TypeError, ValueError):
        selected_article_id = None


def show_detail(article_id: int) -> None:
    with session_scope() as session:
        repo = ArticleRepository(session)
        watch_repo = WatchRepository(session, user_id=uid)
        article = repo.get(article_id)
        if article is None:
            st.error("Article introuvable.")
            return

        history = repo.price_history(article_id)
        first = history[0] if history else None
        last = history[-1] if history else None
        watch = watch_repo.get_article_watch(article_id)
        is_watched = watch is not None

        # Snapshot des données en dict pour éviter l'accès après fermeture session
        article_view = {
            "id": article.id,
            "ext_ref": article.ext_ref,
            "title": article.title,
            "url": article.url,
            "category": article.category,
            "platform": article.platform,
            "brand": article.brand,
            "first_seen_at": article.first_seen_at,
            "last_seen_at": article.last_seen_at,
            "active": article.active,
        }
        watch_view = None
        if watch is not None:
            watch_view = {
                "id": watch.id,
                "threshold_price_cents": watch.threshold_price_cents,
                "threshold_drop_pct": watch.threshold_drop_pct,
            }
        history_view = [
            {"scraped_at": s.scraped_at, "price_cents": s.price_cents, "available": s.available}
            for s in history
        ]
        first_price = first.price_cents if first else None
        last_price = last.price_cents if last else None

    # Rendu
    top = st.columns([4, 1, 1, 1])
    top[0].markdown(f"### [{article_view['title']}]({article_view['url']})")
    top[1].markdown(f"**{format_price(last_price)}**")
    pct = price_change_pct(first_price, last_price)
    top[2].markdown(f"{pct:+.1%}" if pct is not None else "—")
    ro = is_readonly()
    ro_help = "Désactivé en mode démo" if ro else None
    if is_watched:
        if top[3].button("Retirer", use_container_width=True, disabled=ro, help=ro_help):
            with session_scope() as session:
                watch_repo = WatchRepository(session, user_id=uid)
                watch_repo.remove_article(article_view["id"])
            st.query_params.clear()
            st.rerun()
    else:
        if top[3].button("Suivre", use_container_width=True, disabled=ro, help=ro_help):
            with session_scope() as session:
                watch_repo = WatchRepository(session, user_id=uid)
                watch_repo.add_article_watch(article_view["id"])
            st.rerun()

    meta = st.columns(4)
    meta[0].caption(f"Réf : `{article_view['ext_ref']}`")
    meta[1].caption(f"Catégorie : {article_view['category']}")
    meta[2].caption(f"Plateforme : {article_view['platform'] or '—'}")
    meta[3].caption(f"Statut : {'actif' if article_view['active'] else 'disparu'}")

    st.caption(
        f"Première vue : {format_datetime(article_view['first_seen_at'])}  ·  "
        f"Dernière vue : {format_datetime(article_view['last_seen_at'])}  ·  "
        f"Prix initial : {format_price(first_price)}"
    )

    if watch_view is not None:
        with st.expander("⚙️ Seuils d'alerte", expanded=False):
            st.caption(
                "Une alerte est déclenchée si la baisse dépasse le pourcentage, "
                "ou si le prix descend au seuil absolu (le premier des deux)."
            )
            with st.form(f"thresholds_{watch_view['id']}"):
                c1, c2, c3 = st.columns([2, 2, 1])
                cur_pct = (watch_view["threshold_drop_pct"] or 0.0) * 100
                new_pct = c1.number_input(
                    "Seuil de baisse (%)", min_value=0.0, max_value=100.0, value=float(cur_pct), step=1.0
                )
                cur_abs = (
                    (watch_view["threshold_price_cents"] / 100)
                    if watch_view["threshold_price_cents"]
                    else 0.0
                )
                new_abs = c2.number_input(
                    "Seuil prix max (€)", min_value=0.0, value=float(cur_abs), step=1.0,
                    help="0 = pas de seuil absolu"
                )
                saved = c3.form_submit_button(
                    "Enregistrer",
                    use_container_width=True,
                    disabled=is_readonly(),
                    help="Désactivé en mode démo" if is_readonly() else None,
                )
            if saved:
                with session_scope() as session:
                    watch_repo = WatchRepository(session, user_id=uid)
                    watch_repo.update_thresholds(
                        watch_view["id"],
                        threshold_drop_pct=(new_pct / 100.0) if new_pct > 0 else None,
                        threshold_price_cents=int(new_abs * 100) if new_abs > 0 else None,
                    )
                st.toast("Seuils mis à jour", icon="✅")
                st.rerun()

    if len(history_view) < 2:
        st.info("Pas encore assez de points pour tracer une courbe. Reviens après quelques rafraîchissements.")
    else:
        df = pd.DataFrame(history_view)
        df["price"] = df["price_cents"] / 100
        fig = px.line(
            df,
            x="scraped_at",
            y="price",
            markers=True,
            labels={"scraped_at": "Date", "price": "Prix (€)"},
            title="Historique du prix",
        )
        fig.update_traces(hovertemplate="%{x|%d/%m/%Y %H:%M}<br>%{y:.2f} €")
        st.plotly_chart(fig, use_container_width=True)

    if st.button("← Retour à la watchlist"):
        st.query_params.clear()
        st.rerun()


if selected_article_id is not None:
    show_detail(selected_article_id)
    sidebar_footer()
    st.stop()


# --- Liste watchlist -------------------------------------------------------

with session_scope() as session:
    watch_repo = WatchRepository(session)
    repo = ArticleRepository(session)
    pairs = watch_repo.list_article_watches()
    rows = []
    for watch, art in pairs:
        last = repo.last_snapshot(art.id)
        first = repo.first_snapshot(art.id)
        pct = price_change_pct(first.price_cents if first else None, last.price_cents if last else None)
        rows.append(
            {
                "watch_id": watch.id,
                "article_id": art.id,
                "ext_ref": art.ext_ref,
                "title": art.title,
                "url": art.url,
                "platform": art.platform or "",
                "first_price": first.price_cents if first else None,
                "current_price": last.price_cents if last else None,
                "pct": pct,
                "last_seen_at": art.last_seen_at,
                "active": art.active,
            }
        )

if not rows:
    st.info("Ta watchlist est vide. Va sur la page Recherche pour ajouter des articles.")
    sidebar_footer()
    st.stop()

st.caption(f"{len(rows)} article(s) suivi(s)")

header = st.columns([4, 1, 1, 1, 1, 1])
header[0].markdown("**Article**")
header[1].markdown("**Prix initial**")
header[2].markdown("**Prix actuel**")
header[3].markdown("**Δ**")
header[4].markdown("**Statut**")
header[5].markdown("")

for row in rows:
    cols = st.columns([4, 1, 1, 1, 1, 1])
    plat = f" [{row['platform']}]" if row["platform"] else ""
    cols[0].markdown(f"[{row['title']}]({row['url']}){plat}")
    cols[1].markdown(format_price(row["first_price"]))
    cols[2].markdown(format_price(row["current_price"]))
    pct = row["pct"]
    if pct is None:
        cols[3].markdown("—")
    else:
        cols[3].markdown(f"{pct:+.1%}")
    cols[4].markdown("✅" if row["active"] else "❌")
    cols[5].link_button("Détail", f"?article={row['article_id']}", use_container_width=True)

sidebar_footer()
