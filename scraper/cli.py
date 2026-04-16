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
from scraper.services.scraper_service import scrape_category

app = typer.Typer(add_completion=False, help="Easycash Tracker — CLI de scraping")


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
    pages: int = typer.Option(3, "--pages", "-p", min=1, max=50, help="Nombre max de pages à parcourir"),
) -> None:
    """Scrape une catégorie et persiste en base."""
    _configure_logs()
    init_db()
    report = asyncio.run(scrape_category(category, max_pages=pages))

    typer.echo("")
    typer.echo(f"=== Rapport {report.category} ===")
    typer.echo(f"  Pages fetchées : {report.pages_fetched}")
    typer.echo(f"  Articles vus   : {report.articles_seen}")
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
            typer.echo("Aucun article en base. Lancez `fetch` d'abord.")
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
