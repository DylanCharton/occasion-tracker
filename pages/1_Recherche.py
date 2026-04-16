"""Page Recherche : filtres + résultats + suivi rapide."""

from __future__ import annotations

import streamlit as st

from scraper.ui.helpers import (
    ArticleRepository,
    WatchRepository,
    category_options,
    ensure_db,
    format_price,
    session_scope,
    sidebar_footer,
)

st.set_page_config(page_title="Recherche — Easycash Tracker", layout="wide")

ensure_db()
st.title("Recherche")
st.caption("Filtre le catalogue local (seuls les articles déjà scrapés sont visibles).")

# --- Filtres ---------------------------------------------------------------

with session_scope() as session:
    repo = ArticleRepository(session)
    all_categories = repo.distinct_categories()
    all_platforms = repo.distinct_platforms()

with st.form("search_form"):
    col1, col2, col3 = st.columns([3, 2, 2])
    query = col1.text_input("Mots-clés", placeholder="ex: zelda, spider-man, ps5…")
    category = col2.selectbox(
        "Catégorie",
        options=["(toutes)"] + (all_categories or category_options()),
    )
    platform = col3.selectbox("Plateforme", options=["(toutes)"] + all_platforms)

    col4, col5, col6, col7 = st.columns([2, 2, 2, 2])
    min_price = col4.number_input("Prix min (€)", min_value=0.0, value=0.0, step=1.0)
    max_price = col5.number_input("Prix max (€)", min_value=0.0, value=0.0, step=1.0, help="0 = pas de max")
    order_by = col6.selectbox(
        "Tri",
        options=["last_seen_desc", "price_asc", "price_desc", "title", "first_seen_desc"],
        format_func=lambda v: {
            "last_seen_desc": "Dernière mise à jour",
            "price_asc": "Prix croissant",
            "price_desc": "Prix décroissant",
            "title": "Titre (A→Z)",
            "first_seen_desc": "Nouveaux d'abord",
        }[v],
    )
    only_active = col7.checkbox("Actifs uniquement", value=True)
    cols_btn = st.columns([1, 1])
    submitted = cols_btn[0].form_submit_button("Rechercher", use_container_width=True)
    save_submitted = cols_btn[1].form_submit_button(
        "💾 Enregistrer cette recherche (alerte nouveau match)",
        use_container_width=True,
    )

# --- Résultats -------------------------------------------------------------

if save_submitted:
    criteria = {
        "query": query or None,
        "category": None if category == "(toutes)" else category,
        "platform": None if platform == "(toutes)" else platform,
        "min_price_cents": int(min_price * 100) if min_price > 0 else None,
        "max_price_cents": int(max_price * 100) if max_price > 0 else None,
        "only_active": only_active,
    }
    with session_scope() as session:
        watch_repo = WatchRepository(session)
        watch = watch_repo.add_search_watch(criteria)
        watch_id = watch.id
    st.success(
        f"✅ Recherche enregistrée (#{watch_id}). Tu recevras une alerte à chaque nouveau "
        f"match lors des prochains scrapings."
    )

if submitted or True:  # on affiche aussi un premier écran par défaut
    with session_scope() as session:
        repo = ArticleRepository(session)
        watch_repo = WatchRepository(session)
        results = repo.search(
            query=query or None,
            category=None if category == "(toutes)" else category,
            platform=None if platform == "(toutes)" else platform,
            min_price_cents=int(min_price * 100) if min_price > 0 else None,
            max_price_cents=int(max_price * 100) if max_price > 0 else None,
            only_active=only_active,
            limit=200,
            order_by=order_by,
        )

        rows = []
        for art in results:
            last = repo.last_snapshot(art.id)
            watched = watch_repo.is_watched(art.id)
            rows.append(
                {
                    "id": art.id,
                    "ext_ref": art.ext_ref,
                    "title": art.title,
                    "url": art.url,
                    "platform": art.platform or "",
                    "category": art.category,
                    "price_cents": last.price_cents if last else None,
                    "last_seen_at": art.last_seen_at,
                    "active": art.active,
                    "watched": watched,
                }
            )

    st.caption(f"{len(rows)} résultat(s)")

    if not rows:
        st.info("Aucun article ne correspond. Élargis les filtres ou lance un scraping depuis le Dashboard.")
    else:
        for row in rows:
            cols = st.columns([5, 1, 1, 1, 2])
            plat = f" [{row['platform']}]" if row["platform"] else ""
            cols[0].markdown(f"**[{row['title']}]({row['url']})**{plat}")
            cols[1].markdown(format_price(row["price_cents"]))
            cols[2].caption(row["category"])
            cols[3].caption(row["ext_ref"])
            if row["watched"]:
                cols[4].success("✓ Suivi")
            else:
                if cols[4].button("Suivre", key=f"watch_{row['id']}"):
                    with session_scope() as session:
                        watch_repo = WatchRepository(session)
                        watch_repo.add_article_watch(row["id"])
                    st.rerun()

sidebar_footer()
