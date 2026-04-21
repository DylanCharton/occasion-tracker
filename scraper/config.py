"""Configuration centralisée via pydantic-settings.

Hiérarchie de résolution (la plus prioritaire en premier) :
1. Variables d'environnement (`os.environ`)
2. `st.secrets` (Streamlit Cloud — fichier `.streamlit/secrets.toml`)
3. Fichier `.env` (dev local)
4. Valeurs par défaut du code

En prod (Streamlit Cloud) : on configure les secrets dans le dashboard
(DATABASE_URL, DISCORD_WEBHOOK_URL) → lus via `st.secrets`.
En local : on utilise `.env` comme avant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class StreamlitSecretsSource(PydanticBaseSettingsSource):
    """Source pydantic-settings qui lit depuis `st.secrets` si disponible.

    Silencieuse si Streamlit n'est pas installé ou si aucun `secrets.toml`
    n'est présent (cas CLI, tests, etc.).
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._secrets = self._load_secrets()

    @staticmethod
    def _load_secrets() -> dict[str, Any]:
        try:
            import streamlit as st
        except ImportError:
            return {}
        try:
            return {k: st.secrets[k] for k in st.secrets}
        except Exception:
            # Pas de secrets.toml en local hors contexte Streamlit → OK
            return {}

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # On tolère les clés en UPPER_SNAKE (convention toml) et en snake_case.
        for key in (field_name, field_name.upper()):
            if key in self._secrets:
                return self._secrets[key], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name, field in self.settings_cls.model_fields.items():
            value, _, _ = self.get_field_value(field, name)
            if value is not None:
                data[name] = value
        return data


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

    # Auth / multi-user
    # Liste d'emails admins (CSV). Ces users reçoivent is_admin=True à la création.
    admin_emails: str = "d.charton@fimainfo.fr"
    # Email utilisé quand Streamlit tourne en local sans SSO (pas de st.user).
    dev_user_email: str = "d.charton@fimainfo.fr"

    @property
    def admin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            StreamlitSecretsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


settings = Settings()
