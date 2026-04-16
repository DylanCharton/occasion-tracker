"""Configuration centralisée via pydantic-settings.

Charge les valeurs depuis .env, avec des defaults raisonnables.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Discord
    discord_webhook_url: str = ""

    # Rafraîchissement
    default_refresh_interval_hours: int = 6
    default_price_drop_threshold: float = 0.05

    # Rate-limit / HTTP
    request_delay_seconds: float = 1.5
    request_jitter_seconds: float = 0.3
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "EasycashTrackerPerso/1.0"
    )

    # DB
    database_url: str = Field(default=f"sqlite:///{PROJECT_ROOT / 'data' / 'easycash.db'}")

    # Logs
    log_level: str = "INFO"
    log_file: str = str(PROJECT_ROOT / "logs" / "scraper.log")

    # Domaine cible
    base_url: str = "https://bons-plans.easycash.fr"


settings = Settings()
