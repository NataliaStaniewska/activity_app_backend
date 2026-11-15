"""Create activities table.

Revision ID: 20261115_01
Revises:
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20261115_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_name", sa.String(length=100), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("location_type", sa.String(length=20), nullable=False),
        sa.Column("company_type", sa.String(length=20), nullable=False),
        sa.Column("mood_before", sa.Integer(), nullable=True),
        sa.Column("mood_after", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("emotions", sa.JSON(), nullable=False),
        sa.Column("likes", sa.String(length=200), nullable=True),
        sa.Column("dislikes", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="ck_activities_rating",
        ),
        sa.CheckConstraint(
            "mood_before IS NULL OR mood_before BETWEEN 1 AND 5",
            name="ck_activities_mood_before",
        ),
        sa.CheckConstraint(
            "mood_after BETWEEN 1 AND 5",
            name="ck_activities_mood_after",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("activities")
