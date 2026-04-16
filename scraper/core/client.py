"""Client HTTP asynchrone pour Easycash.

Respect du site :
- User-Agent identifié (pas de mimétisme agressif)
- délai minimum entre deux requêtes (avec jitter)
- retry exponentiel sur 429 / 5xx
- timeout par requête
"""

from __future__ import annotations

import asyncio
import random
from typing import Self

import httpx
from loguru import logger

from scraper.config import settings


class EasycashClient:
    """Client httpx async rate-limité et robuste."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        delay: float | None = None,
        jitter: float | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = base_url or settings.base_url
        self.delay = delay if delay is not None else settings.request_delay_seconds
        self.jitter = jitter if jitter is not None else settings.request_jitter_seconds
        self.timeout = timeout if timeout is not None else settings.request_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.max_retries
        self._client: httpx.AsyncClient | None = None
        self._last_request_monotonic: float = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
            },
            follow_redirects=True,
            http2=True,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _respect_rate_limit(self) -> None:
        """Attend le délai requis depuis la dernière requête (thread-safe)."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_monotonic
            wait_target = self.delay + random.uniform(0, self.jitter)
            if elapsed < wait_target:
                await asyncio.sleep(wait_target - elapsed)
            self._last_request_monotonic = asyncio.get_event_loop().time()

    async def get(self, path: str, **params: object) -> httpx.Response:
        """GET avec rate-limit et retry exponentiel."""
        if self._client is None:
            raise RuntimeError("Client non initialisé, utiliser `async with EasycashClient()`")

        attempt = 0
        backoff = 2.0
        while True:
            await self._respect_rate_limit()
            try:
                response = await self._client.get(path, params=params or None)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                attempt += 1
                if attempt > self.max_retries:
                    logger.error(f"GET {path} : échec après {attempt} tentatives ({exc})")
                    raise
                logger.warning(f"GET {path} : tentative {attempt} échouée ({exc}), retry dans {backoff}s")
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code in (429, 502, 503, 504):
                attempt += 1
                if attempt > self.max_retries:
                    logger.error(f"GET {path} : {response.status_code} après {attempt} tentatives")
                    response.raise_for_status()
                # Respecter Retry-After si présent
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                logger.warning(f"GET {path} : {response.status_code}, retry dans {wait}s")
                await asyncio.sleep(wait)
                backoff *= 2
                continue

            response.raise_for_status()
            return response
