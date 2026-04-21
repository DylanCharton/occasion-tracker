"""Page Paramètres — configuration personnelle + section admin."""

from __future__ import annotations

import streamlit as st

from scraper.config import settings
from scraper.ui.helpers import (
    ArticleRepository,
    UserRepository,
    WatchRepository,
    category_format,
    category_options,
    current_user,
    current_user_id,
    ensure_db,
    format_datetime,
    get_scheduler,
    is_admin,
    is_demo_mode,
    require_auth,
    session_scope,
    sidebar_footer,
)

st.set_page_config(page_title="Paramètres — Easycash Tracker", layout="wide")

ensure_db()
require_auth()
uid = current_user_id()
user = current_user()

st.title("Paramètres")

if is_demo_mode():
    st.info(
        "🧪 Mode démo : les paramètres sont désactivés. "
        "[Connecte-toi](/) pour configurer ton webhook Discord et tes alertes."
    )
    sidebar_footer()
    st.stop()

# --- Mes paramètres (tous les users) --------------------------------------

st.subheader("Mes paramètres")
st.caption("Configure ton webhook Discord pour recevoir les alertes sur ton propre serveur.")

with session_scope() as session:
    db_user = UserRepository(session).get_by_email(user.email)
    current_webhook = db_user.discord_webhook_url if db_user else ""

with st.form("user_settings_form"):
    webhook_input = st.text_input(
        "Webhook Discord",
        value=current_webhook or "",
        placeholder="https://discord.com/api/webhooks/...",
        help="Laisse vide pour désactiver les notifications Discord pour tes alertes.",
    )
    saved = st.form_submit_button("Enregistrer", use_container_width=True)

if saved:
    with session_scope() as session:
        UserRepository(session).set_discord_webhook(uid, webhook_input.strip() or None)
    st.success("Webhook mis à jour.")
    st.rerun()

st.divider()

# --- Section admin --------------------------------------------------------

if not is_admin():
    st.info(
        "Seuls les administrateurs peuvent planifier les rafraîchissements et gérer "
        "le catalogue partagé. Contacte l'admin si tu veux qu'une catégorie soit suivie."
    )
    sidebar_footer()
    st.stop()

scheduler = get_scheduler()

st.subheader("⚙️ Admin — Mise à jour automatique")
st.caption(
    "Planifie les rafraîchissements du catalogue partagé. Tous les utilisateurs en bénéficient."
)

with st.form("add_job_form"):
    cols = st.columns([3, 1, 1, 1])
    category = cols[0].selectbox(
        "Catégorie connue", options=category_options(), format_func=category_format
    )
    interval_hours = cols[1].number_input(
        "Intervalle (h)",
        min_value=1,
        max_value=168,
        value=settings.default_refresh_interval_hours,
        step=1,
    )
    max_pages = cols[2].number_input(
        "Pages", min_value=1, max_value=5, value=2, step=1,
        help="2 pages suffit par catégorie (vitrine Easycash).",
    )
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

with st.expander("Ajouter un slug Easycash non listé", expanded=False):
    st.caption(
        "Pour scraper une catégorie hors liste prédéfinie (ex: `meubles`, "
        "`informatique/ordinateurs-portables`). Le slug doit correspondre à une URL "
        "réelle `bons-plans.easycash.fr/<slug>`."
    )
    with st.form("add_custom_job_form"):
        cols = st.columns([3, 1, 1, 1])
        custom_slug = cols[0].text_input("Slug", placeholder="meubles/canapes")
        custom_interval = cols[1].number_input(
            "Intervalle (h)",
            min_value=1,
            max_value=168,
            value=settings.default_refresh_interval_hours,
            step=1,
            key="custom_interval",
        )
        custom_pages = cols[2].number_input(
            "Pages", min_value=1, max_value=5, value=2, step=1, key="custom_pages"
        )
        custom_submitted = cols[3].form_submit_button("Ajouter", use_container_width=True)

    if custom_submitted:
        slug = custom_slug.strip().strip("/")
        if not slug:
            st.error("Le slug ne peut pas être vide.")
        elif slug.startswith("http"):
            st.error("Entre un slug relatif, pas une URL complète.")
        else:
            try:
                scheduler.add_or_update(
                    category_slug=slug,
                    interval_hours=int(custom_interval),
                    max_pages=int(custom_pages),
                )
                st.success(f"Job planifié pour `{slug}`")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Erreur : {exc}")

if st.button(
    "Planifier toutes les catégories JV",
    use_container_width=True,
    help="Crée un job pour chacune des catégories JV connues",
):
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
    for h, label in zip(
        header,
        ["Catégorie", "Intervalle", "Pages", "Dernière exécution", "Prochaine", "Actif", "Run", "×"],
    ):
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

        new_active = cols[5].toggle(
            "", value=job.active, key=f"active_{job.id}", label_visibility="collapsed"
        )
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

# --- Utilisateurs ----------------------------------------------------------

st.subheader("⚙️ Admin — Utilisateurs")
with session_scope() as session:
    all_users = UserRepository(session).list_all()
    users_view = [
        {"id": u.id, "email": u.email, "is_admin": u.is_admin, "has_webhook": bool(u.discord_webhook_url)}
        for u in all_users
    ]

for u in users_view:
    cols = st.columns([4, 1, 1, 1])
    cols[0].markdown(f"**{u['email']}**")
    cols[1].caption("admin" if u["is_admin"] else "user")
    cols[2].caption("🔔 Discord" if u["has_webhook"] else "—")
    cols[3].caption(f"#{u['id']}")

st.caption(
    "La liste des admins se configure via `ADMIN_EMAILS` (CSV) dans `.env` ou `st.secrets`. "
    "Les whitelistées d'accès sont gérées dans le dashboard Streamlit Cloud (Viewer authentication)."
)

st.divider()

# --- Config + BDD ----------------------------------------------------------

st.subheader("⚙️ Admin — Configuration actuelle")
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
        }
    )
with col2:
    st.markdown("**Base & alertes**")
    st.write(
        {
            "default_refresh_interval_hours": settings.default_refresh_interval_hours,
            "default_price_drop_threshold": settings.default_price_drop_threshold,
            "discord_webhook_url (fallback admin)": "(configuré)" if settings.discord_webhook_url else "(non configuré)",
            "database_url": settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
            "log_level": settings.log_level,
        }
    )

with session_scope() as session:
    art_repo = ArticleRepository(session)
    watch_repo = WatchRepository(session, user_id=uid)
    cols = st.columns(3)
    cols[0].metric("Articles (catalogue)", art_repo.count())
    cols[1].metric("Plateformes distinctes", len(art_repo.distinct_platforms()))
    cols[2].metric("Mes watches actives", watch_repo.count_active())

sidebar_footer()
