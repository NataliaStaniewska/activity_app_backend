"""Add a registry for idempotent demo data imports.

Revision ID: 20261115_02
Revises: 20261115_01
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20261115_02"
down_revision = "20261115_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_import_runs",
        sa.Column("import_key", sa.String(length=100), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("import_key"),
    )


def downgrade() -> None:
    op.drop_table("demo_import_runs")
