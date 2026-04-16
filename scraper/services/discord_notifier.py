"""Envoi d'alertes Discord via webhook.

La fonction `send_alert` est tolérante : si le webhook n'est pas configuré
ou si l'envoi échoue, on log l'erreur mais on ne lève pas — le reste du
pipeline (persistance DB, scheduler) ne doit pas être bloqué par Discord.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from discord_webhook import DiscordEmbed, DiscordWebhook
from loguru import logger

from scraper.config import settings
from scraper.db.models import AlertType


class AlertLike(Protocol):
    """Ce qu'on attend pour construire un message (compat avec DB Alert + dataclass)."""

    type: str
    message: str
    price_cents: int | None
    previous_price_cents: int | None
    triggered_at: datetime


# Couleurs des embeds Discord (hex)
COLOR_DROP = "2ecc71"         # vert
COLOR_NEW_MATCH = "3498db"    # bleu
COLOR_DISAPPEARED = "95a5a6"  # gris


def _price(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"{cents / 100:.2f} €"


def _color_for(alert_type: str) -> str:
    if alert_type == AlertType.PRICE_DROP.value:
        return COLOR_DROP
    if alert_type == AlertType.NEW_MATCH.value:
        return COLOR_NEW_MATCH
    if alert_type == AlertType.DISAPPEARED.value:
        return COLOR_DISAPPEARED
    return "7f8c8d"


def _title_for(alert_type: str, article_title: str | None) -> str:
    if alert_type == AlertType.PRICE_DROP.value:
        prefix = "🔻 Baisse de prix"
    elif alert_type == AlertType.NEW_MATCH.value:
        prefix = "🆕 Nouveau match"
    elif alert_type == AlertType.DISAPPEARED.value:
        prefix = "🚫 Article retiré"
    else:
        prefix = "🔔 Alerte"
    if article_title:
        return f"{prefix} — {article_title[:200]}"
    return prefix


def send_alert(
    alert: AlertLike,
    *,
    article_title: str | None = None,
    article_url: str | None = None,
    article_platform: str | None = None,
    webhook_url: str | None = None,
) -> bool:
    """Envoie une alerte sur Discord. Retourne True si envoyé, False sinon."""
    url = webhook_url or settings.discord_webhook_url
    if not url:
        logger.debug("Discord webhook non configuré, skip envoi")
        return False

    try:
        webhook = DiscordWebhook(url=url, rate_limit_retry=True)
        embed = DiscordEmbed(
            title=_title_for(alert.type, article_title),
            description=alert.message[:4000] if alert.message else "",
            color=_color_for(alert.type),
        )

        if alert.previous_price_cents is not None and alert.price_cents is not None:
            old = alert.previous_price_cents
            new = alert.price_cents
            pct = ((new - old) / old * 100) if old else 0.0
            embed.add_embed_field(
                name="Prix",
                value=f"~~{_price(old)}~~ → **{_price(new)}**  ({pct:+.1f}%)",
                inline=False,
            )
        elif alert.price_cents is not None:
            embed.add_embed_field(name="Prix", value=_price(alert.price_cents), inline=True)

        if article_platform:
            embed.add_embed_field(name="Plateforme", value=article_platform, inline=True)

        if article_url:
            embed.add_embed_field(name="Lien", value=article_url, inline=False)

        embed.set_timestamp(alert.triggered_at.isoformat())
        embed.set_footer(text="Easycash Tracker")

        webhook.add_embed(embed)
        response = webhook.execute()
        # discord-webhook renvoie une Response ou une liste ; on gère les deux
        if isinstance(response, list):
            ok = all(r.status_code in (200, 204) for r in response)
        else:
            ok = response.status_code in (200, 204)
        if not ok:
            logger.warning(f"Envoi Discord : statut inattendu ({response})")
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Envoi Discord échoué : {exc}")
        return False
