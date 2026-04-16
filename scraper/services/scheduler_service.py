"""Service de planification basé sur APScheduler.

Fournit un singleton `SchedulerService` qui orchestre l'exécution périodique
des jobs de scraping définis en base (table `scheduled_job`).

Design :
- Source de vérité : table SQLAlchemy `ScheduledJob`.
- APScheduler est initialisé au démarrage de l'application (Streamlit),
  on charge tous les jobs actifs depuis la DB et on les installe.
- Chaque modification (add/remove/toggle/update) synchronise APScheduler.
- Les callbacks tournent dans un thread APScheduler séparé ; chacun crée
  sa propre session DB pour éviter les conflits avec la session Streamlit.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from scraper.db.repository import ScheduledJobRepository
from scraper.db.session import session_scope
from scraper.services.scraper_service import scrape_category


APS_JOB_PREFIX = "scraper-"


def _aps_job_id(db_job_id: int) -> str:
    return f"{APS_JOB_PREFIX}{db_job_id}"


@dataclass(slots=True)
class JobView:
    """Représentation projetée d'un job (fusion DB + APScheduler)."""

    id: int
    category_slug: str
    interval_hours: int
    max_pages: int
    active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_error: str | None
    next_run_at: datetime | None


def _run_scrape_sync(job_id: int, category_slug: str, max_pages: int) -> None:
    """Callback appelé par APScheduler (thread séparé)."""
    logger.info(f"[scheduler] Job #{job_id} : scraping {category_slug} ({max_pages} pages)")
    try:
        asyncio.run(scrape_category(category_slug, max_pages=max_pages))
        with session_scope() as session:
            ScheduledJobRepository(session).update_run(job_id, status="OK", error=None)
    except Exception as exc:  # noqa: BLE001 — on veut éviter de crash le scheduler
        logger.exception(f"[scheduler] Job #{job_id} erreur : {exc}")
        with session_scope() as session:
            ScheduledJobRepository(session).update_run(job_id, status="ERROR", error=str(exc))


class SchedulerService:
    """Singleton encapsulant un BackgroundScheduler APScheduler."""

    _instance: "SchedulerService | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._started = False

    # ------------------------------------------------------------------ Singleton

    @classmethod
    def get(cls) -> "SchedulerService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = SchedulerService()
                cls._instance.start()
            return cls._instance

    # ------------------------------------------------------------------ Lifecycle

    def start(self) -> None:
        """Démarre le scheduler et installe les jobs actifs."""
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        self._sync_from_db()
        logger.info("[scheduler] Démarré")

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    # ------------------------------------------------------------------ Sync DB

    def _sync_from_db(self) -> None:
        """Reconstitue les jobs APScheduler depuis l'état DB (idempotent)."""
        with session_scope() as session:
            jobs = ScheduledJobRepository(session).list_all()
            views = [
                {
                    "id": j.id,
                    "category_slug": j.category_slug,
                    "interval_hours": j.interval_hours,
                    "max_pages": j.max_pages,
                    "active": j.active,
                }
                for j in jobs
            ]

        # Supprime tous les jobs scraper- pour repartir propre
        for existing in list(self._scheduler.get_jobs()):
            if existing.id.startswith(APS_JOB_PREFIX):
                self._scheduler.remove_job(existing.id)

        for v in views:
            if v["active"]:
                self._schedule_job(v["id"], v["category_slug"], v["interval_hours"], v["max_pages"])

    def _schedule_job(self, job_id: int, category_slug: str, interval_hours: int, max_pages: int) -> None:
        trigger = IntervalTrigger(hours=interval_hours)
        self._scheduler.add_job(
            func=_run_scrape_sync,
            trigger=trigger,
            args=(job_id, category_slug, max_pages),
            id=_aps_job_id(job_id),
            name=f"scrape {category_slug}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )

    # ------------------------------------------------------------------ Public API

    def add_or_update(self, *, category_slug: str, interval_hours: int, max_pages: int) -> int:
        with session_scope() as session:
            repo = ScheduledJobRepository(session)
            job = repo.add(
                category_slug=category_slug,
                interval_hours=interval_hours,
                max_pages=max_pages,
            )
            job_id = job.id
            active = job.active
        if active:
            self._schedule_job(job_id, category_slug, interval_hours, max_pages)
        return job_id

    def remove(self, job_id: int) -> bool:
        try:
            self._scheduler.remove_job(_aps_job_id(job_id))
        except Exception:
            pass  # pas dans APScheduler, on continue quand même
        with session_scope() as session:
            return ScheduledJobRepository(session).remove(job_id)

    def set_active(self, job_id: int, active: bool) -> None:
        with session_scope() as session:
            repo = ScheduledJobRepository(session)
            job = repo.set_active(job_id, active)
            if job is None:
                return
            snapshot = {
                "id": job.id,
                "category_slug": job.category_slug,
                "interval_hours": job.interval_hours,
                "max_pages": job.max_pages,
            }
        if active:
            self._schedule_job(**snapshot)
        else:
            try:
                self._scheduler.remove_job(_aps_job_id(job_id))
            except Exception:
                pass

    def run_now(self, job_id: int) -> None:
        """Déclenche une exécution immédiate (sans attendre le prochain tick)."""
        with session_scope() as session:
            job = ScheduledJobRepository(session).get(job_id)
            if job is None:
                return
            snapshot = (job.id, job.category_slug, job.max_pages)
        # Exécute dans un thread APScheduler pour ne pas bloquer l'UI
        self._scheduler.add_job(
            func=_run_scrape_sync,
            trigger="date",  # immédiat
            args=snapshot,
            id=f"{APS_JOB_PREFIX}runnow-{job_id}-{datetime.utcnow().timestamp()}",
            name=f"run-now {snapshot[1]}",
            max_instances=1,
            misfire_grace_time=60,
        )

    def list_jobs(self) -> list[JobView]:
        with session_scope() as session:
            jobs = ScheduledJobRepository(session).list_all()
            db_jobs = [
                {
                    "id": j.id,
                    "category_slug": j.category_slug,
                    "interval_hours": j.interval_hours,
                    "max_pages": j.max_pages,
                    "active": j.active,
                    "last_run_at": j.last_run_at,
                    "last_run_status": j.last_run_status,
                    "last_error": j.last_error,
                }
                for j in jobs
            ]

        views: list[JobView] = []
        for j in db_jobs:
            aps_job = self._scheduler.get_job(_aps_job_id(j["id"]))
            next_run = aps_job.next_run_time if aps_job else None
            # APScheduler renvoie un datetime aware ; on le passe en naive UTC pour cohérence
            if next_run is not None and next_run.tzinfo is not None:
                from datetime import timezone
                next_run = next_run.astimezone(timezone.utc).replace(tzinfo=None)
            views.append(
                JobView(
                    id=j["id"],
                    category_slug=j["category_slug"],
                    interval_hours=j["interval_hours"],
                    max_pages=j["max_pages"],
                    active=j["active"],
                    last_run_at=j["last_run_at"],
                    last_run_status=j["last_run_status"],
                    last_error=j["last_error"],
                    next_run_at=next_run,
                )
            )
        return views

    def next_runs(self, limit: int = 5) -> list[JobView]:
        """Prochaines exécutions planifiées, triées par date."""
        jobs = [j for j in self.list_jobs() if j.active and j.next_run_at is not None]
        jobs.sort(key=lambda j: j.next_run_at)  # type: ignore[arg-type]
        return jobs[:limit]
