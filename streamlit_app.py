"""Occasion Tracker — Dashboard.

Lancement : streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from scraper.ui.helpers import (
    category_format,
    category_options,
    current_user_id,
    dashboard_data,
    ensure_db,
    format_datetime,
    format_price,
    get_scheduler,
    is_admin,
    is_demo_mode,
    is_readonly,
    next_runs_view,
    price_change_pct,
    require_auth,
    run_full_scrape,
    run_scrape,
    AVAILABLE_PLATFORMS,
    sidebar_footer,
)


st.set_page_config(
    page_title="Occasion Tracker",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_db()
require_auth()
# Démarre le scheduler (idempotent, singleton via cache_resource)
scheduler = get_scheduler()

st.title("Occasion Tracker")
st.caption("Suivi de prix sur site d'occasion — jeu vidéo")

if is_demo_mode():
    st.info(
        "🧪 **Mode démo** — tu consultes la vitrine publique en lecture seule. "
        "[Connecte-toi](/) pour accéder à ta propre watchlist et tes alertes."
    )

# --- Métriques principales -------------------------------------------------

uid = current_user_id()
data = dashboard_data(uid)
drops_view = data["drops_view"]
recents_view = data["recents_view"]

c1, c2, c3 = st.columns(3)
c1.metric("Articles en base", data["total_articles"])
c2.metric("Articles suivis", data["total_watches"])
c3.metric("Alertes non lues", data["total_unread_alerts"])

st.divider()

# --- Rafraîchissement manuel (admin-only) ---------------------------------

if is_admin() and not is_readonly():
    st.subheader("⚙️ Analyse du catalogue")
    st.caption(
        "Collecte **tous** les articles du catalogue pour les plateformes sélectionnées. "
        "Les prix sont historisés à chaque passage."
    )

    DEFAULT_PLATFORMS = ["PS5", "PS4", "DS", "3DS", "Switch", "Switch 2"]
    with st.form("full_scrape_form"):
        selected_platforms = st.multiselect(
            "Plateformes",
            options=AVAILABLE_PLATFORMS,
            default=[p for p in DEFAULT_PLATFORMS if p in AVAILABLE_PLATFORMS],
        )
        launch_submitted = st.form_submit_button(
            "Lancer l'analyse",
            use_container_width=True,
            type="primary",
        )

    if launch_submitted:
        if not selected_platforms:
            st.warning("Sélectionne au moins une plateforme.")
        else:
            with st.spinner(f"Collecte de {len(selected_platforms)} plateforme(s) en cours..."):
                try:
                    result = run_full_scrape(selected_platforms)
                    dashboard_data.clear()
                    next_runs_view.clear()
                    st.success(
                        f"✅ **{result['unique']}** articles uniques · "
                        f"{result['created']} nouveaux · {result['updated']} mis à jour · "
                        f"{result['snapshots']} snapshots · {result['queries']} plateforme(s)"
                    )
                except Exception as exc:
                    st.error(f"Erreur : {exc}")

    with st.expander("Rafraîchissement rapide d'une catégorie (vitrine)", expanded=False):
        with st.form("refresh_form"):
            col1, col2 = st.columns([4, 1])
            category = col1.selectbox(
                "Catégorie",
                options=category_options(),
                index=category_options().index("jeux-video"),
                format_func=category_format,
            )
            pages = col2.number_input("Pages", min_value=1, max_value=5, value=2, step=1)
            submitted = st.form_submit_button("Rafraîchir", use_container_width=True)

        if submitted:
            with st.spinner(f"Scraping de {category}..."):
                try:
                    result = run_scrape(category, int(pages))
                    dashboard_data.clear()
                    next_runs_view.clear()
                    st.success(
                        f"✅ **{result['unique']}** articles uniques · "
                        f"{result['created']} nouveaux · {result['updated']} mis à jour"
                    )
                except Exception as exc:
                    st.error(f"Erreur : {exc}")

    st.divider()

# --- Prochaines exécutions planifiées -------------------------------------

next_runs = next_runs_view(limit=5)
if next_runs:
    st.subheader("Prochaines exécutions planifiées")
    for job in next_runs:
        cols = st.columns([3, 1, 1, 2])
        cols[0].markdown(f"**{job['category_slug']}**")
        cols[1].caption(f"tous les {job['interval_hours']}h")
        cols[2].caption(f"{job['max_pages']} pages")
        cols[3].caption(f"⏰ {format_datetime(job['next_run_at'])}")
    st.caption("Gère la planification depuis la page **Paramètres**.")
else:
    st.info(
        "Aucun rafraîchissement automatique planifié. "
        "Ajoute un job depuis la page **Paramètres** pour lancer le scheduler."
    )

st.divider()

# --- Dernières baisses de prix --------------------------------------------

st.subheader("Dernières baisses de prix")
if not drops_view:
    st.info("Aucune baisse détectée pour l'instant. Rafraîchis plusieurs fois pour constituer un historique.")
else:
    for d in drops_view:
        pct = price_change_pct(d["prev"], d["latest"])
        platform = f" [{d['platform']}]" if d["platform"] else ""
        cols = st.columns([5, 1, 1, 2])
        cols[0].markdown(f"**[{d['title']}]({d['url']})**{platform}")
        cols[1].markdown(f"~~{format_price(d['prev'])}~~")
        cols[2].markdown(f"**{format_price(d['latest'])}**")
        cols[3].markdown(f"{pct:+.1%}" if pct is not None else "—")

st.divider()

# --- Derniers articles vus -------------------------------------------------

st.subheader("Derniers articles vus")
if not recents_view:
    st.info("Rien en base. Utilise le rafraîchissement ci-dessus pour remplir.")
else:
    for r in recents_view:
        cols = st.columns([5, 1, 1, 2])
        plat = f" [{r['platform']}]" if r["platform"] else ""
        cols[0].markdown(f"**[{r['title']}]({r['url']})**{plat}")
        cols[1].markdown(format_price(r["price"]))
        cols[2].caption(r["ext_ref"])
        cols[3].caption(format_datetime(r["last_seen_at"]))

sidebar_footer()
