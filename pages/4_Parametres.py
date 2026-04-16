"""Page Paramètres — configuration + gestion des jobs planifiés."""

from __future__ import annotations

import streamlit as st

from scraper.config import settings
from scraper.ui.helpers import (
    ArticleRepository,
    WatchRepository,
    category_format,
    category_options,
    ensure_db,
    format_datetime,
    get_scheduler,
    session_scope,
    sidebar_footer,
)

st.set_page_config(page_title="Paramètres — Easycash Tracker", layout="wide")

ensure_db()
scheduler = get_scheduler()

st.title("Paramètres")

# --- Section Planification -------------------------------------------------

st.subheader("Mise à jour automatique")
st.caption(
    "Ajoute des tâches pour rafraîchir automatiquement certaines catégories à intervalle "
    "régulier. Le planificateur tourne en arrière-plan tant que l'application est ouverte."
)

with st.form("add_job_form"):
    cols = st.columns([3, 1, 1, 1])
    category = cols[0].selectbox("Catégorie", options=category_options(), format_func=category_format)
    interval_hours = cols[1].number_input(
        "Intervalle (h)", min_value=1, max_value=168, value=settings.default_refresh_interval_hours, step=1
    )
    max_pages = cols[2].number_input("Pages", min_value=1, max_value=5, value=2, step=1,
                                     help="2 pages suffit par catégorie (vitrine Easycash).")
    add_submitted = cols[3].form_submit_button("Ajouter / maj", use_container_width=True)

if add_submitted:
    try:
        scheduler.add_or_update(
            category_slug=category,
            interval_hours=int(interval_hours),
            max_pages=int(max_pages),
        )
        st.success(f"Job planifié : {category} toutes les {interval_hours}h ({max_pages} pages)")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erreur : {exc}")

if st.button("Planifier toutes les catégories JV", use_container_width=True, help="Crée un job pour chacune des 11 catégories"):
    count = 0
    for cat in category_options():
        scheduler.add_or_update(
            category_slug=cat,
            interval_hours=int(interval_hours),
            max_pages=int(max_pages),
        )
        count += 1
    st.success(f"✅ {count} jobs planifiés toutes les {interval_hours}h ({max_pages} pages/catégorie)")
    st.rerun()

# --- Liste des jobs --------------------------------------------------------

jobs = scheduler.list_jobs()

if not jobs:
    st.info("Aucun job planifié pour l'instant.")
else:
    header = st.columns([3, 1, 1, 2, 2, 1, 1, 1])
    for h, label in zip(header, ["Catégorie", "Intervalle", "Pages", "Dernière exécution", "Prochaine", "Actif", "Run", "×"]):
        h.markdown(f"**{label}**")

    for job in jobs:
        cols = st.columns([3, 1, 1, 2, 2, 1, 1, 1])
        cols[0].markdown(f"`{job.category_slug}`")
        cols[1].caption(f"{job.interval_hours} h")
        cols[2].caption(str(job.max_pages))
        if job.last_run_at:
            badge = "✅" if job.last_run_status == "OK" else "⚠️"
            cols[3].caption(f"{badge} {format_datetime(job.last_run_at)}")
        else:
            cols[3].caption("—")
        cols[4].caption(format_datetime(job.next_run_at) if job.next_run_at else "—")

        new_active = cols[5].toggle("", value=job.active, key=f"active_{job.id}", label_visibility="collapsed")
        if new_active != job.active:
            scheduler.set_active(job.id, new_active)
            st.rerun()

        if cols[6].button("▶", key=f"run_{job.id}", help="Exécuter maintenant"):
            scheduler.run_now(job.id)
            st.toast(f"Exécution lancée pour {job.category_slug}", icon="▶")

        if cols[7].button("🗑", key=f"del_{job.id}", help="Supprimer"):
            scheduler.remove(job.id)
            st.rerun()

        if job.last_error:
            st.caption(f":red[Dernière erreur : {job.last_error[:200]}]")

st.divider()

# --- Configuration (lecture seule) -----------------------------------------

st.subheader("Configuration actuelle")
st.caption("Édite `.env` pour modifier ces valeurs, puis relance Streamlit.")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Scraping**")
    st.write(
        {
            "base_url": settings.base_url,
            "request_delay_seconds": settings.request_delay_seconds,
            "request_jitter_seconds": settings.request_jitter_seconds,
            "request_timeout_seconds": settings.request_timeout_seconds,
            "max_retries": settings.max_retries,
            "user_agent": settings.user_agent,
        }
    )
with col2:
    st.markdown("**Rafraîchissement & alertes**")
    st.write(
        {
            "default_refresh_interval_hours": settings.default_refresh_interval_hours,
            "default_price_drop_threshold": settings.default_price_drop_threshold,
            "discord_webhook_url": "(configuré)" if settings.discord_webhook_url else "(non configuré)",
            "database_url": settings.database_url,
            "log_level": settings.log_level,
        }
    )

st.divider()

st.subheader("Base de données")
with session_scope() as session:
    art_repo = ArticleRepository(session)
    watch_repo = WatchRepository(session)
    cols = st.columns(3)
    cols[0].metric("Articles", art_repo.count())
    cols[1].metric("Plateformes distinctes", len(art_repo.distinct_platforms()))
    cols[2].metric("Watches actives", watch_repo.count_active())

st.divider()

st.info(
    "• Les champs **état**, **magasin** et **commentaire vendeur** ne sont pas disponibles : "
    "Easycash ne les expose pas sur le web public.\n\n"
    "• Le planificateur **s'arrête quand l'application se ferme** (voulu : exécution uniquement "
    "quand l'app tourne).\n\n"
    "• La détection de baisses et les notifications Discord sont actives si le webhook est configuré."
)

sidebar_footer()
