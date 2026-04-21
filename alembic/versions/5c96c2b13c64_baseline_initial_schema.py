"""baseline initial schema

Revision ID: 5c96c2b13c64
Revises:
Create Date: 2026-04-20 19:54:38.639236

Crée le schéma initial (article, price_snapshot, watch, alert, scheduled_job).
Pour la base SQLite locale déjà existante, utiliser `alembic stamp 5c96c2b13c64`
au lieu de `upgrade` (les tables existent déjà).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5c96c2b13c64"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ext_ref", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_article_ext_ref", "article", ["ext_ref"], unique=True)
    op.create_index("ix_article_category", "article", ["category"])
    op.create_index("ix_article_platform", "article", ["platform"])

    op.create_table(
        "price_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_price_snapshot_article_id", "price_snapshot", ["article_id"])
    op.create_index("ix_snapshot_article_scraped", "price_snapshot", ["article_id", "scraped_at"])

    op.create_table(
        "watch",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("query_json", sa.Text(), nullable=True),
        sa.Column("threshold_price_cents", sa.Integer(), nullable=True),
        sa.Column("threshold_drop_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("watch_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("previous_price_cents", sa.Integer(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("sent_to_discord_at", sa.DateTime(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["watch_id"], ["watch.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_alert_watch_id", "alert", ["watch_id"])

    op.create_table(
        "scheduled_job",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category_slug", sa.String(length=128), nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(length=16), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("category_slug", name="uq_scheduled_job_category"),
    )


def downgrade() -> None:
    op.drop_table("scheduled_job")
    op.drop_index("ix_alert_watch_id", table_name="alert")
    op.drop_table("alert")
    op.drop_table("watch")
    op.drop_index("ix_snapshot_article_scraped", table_name="price_snapshot")
    op.drop_index("ix_price_snapshot_article_id", table_name="price_snapshot")
    op.drop_table("price_snapshot")
    op.drop_index("ix_article_platform", table_name="article")
    op.drop_index("ix_article_category", table_name="article")
    op.drop_index("ix_article_ext_ref", table_name="article")
    op.drop_table("article")
