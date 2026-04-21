"""add user table and scope watch alert

Revision ID: fca536384602
Revises: 5c96c2b13c64
Create Date: 2026-04-20

Crée la table `app_user`, ajoute `user_id` sur watch et alert, backfille
toutes les lignes existantes vers un utilisateur admin par défaut
(email: d.charton@fimainfo.fr).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fca536384602"
down_revision: Union[str, Sequence[str], None] = "5c96c2b13c64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_EMAIL = "d.charton@fimainfo.fr"


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("discord_webhook_url", sa.String(length=512), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"])

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO app_user (email, discord_webhook_url, is_admin, created_at) "
            "VALUES (:email, NULL, :is_admin, CURRENT_TIMESTAMP)"
        ),
        {"email": ADMIN_EMAIL, "is_admin": True},
    )
    admin_id = bind.execute(
        sa.text("SELECT id FROM app_user WHERE email = :email"),
        {"email": ADMIN_EMAIL},
    ).scalar_one()

    with op.batch_alter_table("watch") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_watch_user_id", "app_user", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_watch_user_id", ["user_id"])

    op.execute(
        sa.text("UPDATE watch SET user_id = :aid WHERE user_id IS NULL").bindparams(aid=admin_id)
    )

    with op.batch_alter_table("watch") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("alert") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_alert_user_id", "app_user", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_alert_user_id", ["user_id"])

    op.execute(
        sa.text("UPDATE alert SET user_id = :aid WHERE user_id IS NULL").bindparams(aid=admin_id)
    )

    with op.batch_alter_table("alert") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("alert") as batch:
        batch.drop_index("ix_alert_user_id")
        batch.drop_constraint("fk_alert_user_id", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("watch") as batch:
        batch.drop_index("ix_watch_user_id")
        batch.drop_constraint("fk_watch_user_id", type_="foreignkey")
        batch.drop_column("user_id")

    op.drop_index("ix_app_user_email", table_name="app_user")
    op.drop_table("app_user")
