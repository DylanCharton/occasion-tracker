"""CLI principale (Typer).

Exemples :
    python -m scraper.cli init-db
    python -m scraper.cli categories
    python -m scraper.cli fetch jeux-video --pages 3
    python -m scraper.cli fetch consoles/sony --pages 2
    python -m scraper.cli list --limit 20
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from loguru import logger

from scraper.config import settings
from scraper.core.categories import CATEGORIES
from scraper.db.repository import ArticleRepository
from scraper.db.session import init_db, session_scope
from scraper.services.full_scraper import scrape_full, AJAX_QUERIES_JEUX, ALL_AJAX_QUERIES
from scraper.services.scraper_service import scrape_category

app = typer.Typer(add_completion=False, help="Easycash Tracker — CLI de suivi de prix")


def _configure_logs() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(log_path, level=settings.log_level, rotation="10 MB", retention=5, encoding="utf-8")


@app.command("init-db")
def cmd_init_db() -> None:
    """Crée les tables SQLite."""
    _configure_logs()
    init_db()
    typer.echo(f"Base initialisée : {settings.database_url}")


@app.command("categories")
def cmd_categories() -> None:
    """Liste les catégories JV supportées."""
    for cat in CATEGORIES:
        typer.echo(f"  {cat.slug:<45} {cat.label}")


@app.command("fetch")
def cmd_fetch(
    category: str = typer.Argument(..., help="Slug de catégorie (ex: jeux-video, consoles/sony)"),
    pages: int = typer.Option(2, "--pages", "-p", min=1, max=10, help="Pages par catégorie (2 suffit, Easycash répète au-delà)"),
) -> None:
    """Collecte les articles d'une catégorie et les enregistre en base."""
    _configure_logs()
    init_db()
    report = asyncio.run(scrape_category(category, max_pages=pages))

    typer.echo("")
    typer.echo(f"=== Rapport {report.category} ===")
    typer.echo(f"  Pages analysées: {report.pages_fetched}")
    typer.echo(f"  Articles vus   : {report.articles_seen}")
    typer.echo(f"  Créés          : {report.articles_created}")
    typer.echo(f"  Mis à jour     : {report.articles_updated}")
    typer.echo(f"  Snapshots prix : {report.snapshots_written}")


@app.command("fetch-all")
def cmd_fetch_all(
    pages: int = typer.Option(2, "--pages", "-p", min=1, max=10, help="Pages par catégorie (2 suffit)"),
) -> None:
    """Collecte TOUTES les catégories JV (consoles, jeux, rétro, accessoires)."""
    _configure_logs()
    init_db()
    total_seen = 0
    total_created = 0
    for cat in CATEGORIES:
        typer.echo(f"\n--- {cat.label} ({cat.slug}) ---")
        report = asyncio.run(scrape_category(cat.slug, max_pages=pages))
        total_seen += report.articles_seen
        total_created += report.articles_created
        typer.echo(
            f"  {report.articles_seen} vus · {report.articles_created} créés · "
            f"{report.snapshots_written} snapshots"
        )
    typer.echo(f"\n=== Total : {total_seen} articles vus, {total_created} nouveaux ===")


@app.command("full")
def cmd_full(
    jeux_only: bool = typer.Option(False, "--jeux-only", "-j", help="Jeux vidéo uniquement (pas consoles/accessoires)"),
) -> None:
    """Analyse COMPLETE du catalogue (toutes plateformes, tous articles)."""
    _configure_logs()
    init_db()
    queries = AJAX_QUERIES_JEUX if jeux_only else ALL_AJAX_QUERIES
    typer.echo(f"Lancement de l'analyse complète ({len(queries)} plateformes)...")
    report = asyncio.run(scrape_full(queries=queries))

    typer.echo("")
    typer.echo("=== Rapport analyse complète ===")
    typer.echo(f"  Plateformes    : {report.queries_done}/{report.queries_total}")
    typer.echo(f"  Articles uniques: {report.articles_unique}")
    typer.echo(f"  Créés          : {report.articles_created}")
    typer.echo(f"  Mis à jour     : {report.articles_updated}")
    typer.echo(f"  Snapshots prix : {report.snapshots_written}")


@app.command("list")
def cmd_list(limit: int = typer.Option(20, "--limit", "-n", min=1, max=500)) -> None:
    """Liste les derniers articles vus (triés par last_seen)."""
    _configure_logs()
    init_db()
    with session_scope() as session:
        repo = ArticleRepository(session)
        articles = repo.list_recent(limit=limit)
        total = repo.count()
        if not articles:
            typer.echo("Aucun article en base. Lancez `full` ou `fetch` d'abord.")
            return
        typer.echo(f"Total articles en base : {total}")
        typer.echo("")
        for art in articles:
            last = repo.last_snapshot(art.id)
            price = f"{last.price:.2f} €" if last else "—"
            platform = f"[{art.platform}]" if art.platform else ""
            typer.echo(f"  {art.ext_ref}  {price:>10}  {platform:<10}  {art.title[:70]}")


if __name__ == "__main__":
    app()
