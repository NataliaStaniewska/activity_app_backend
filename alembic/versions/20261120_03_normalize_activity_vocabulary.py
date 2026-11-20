"""Normalize stored activity categories and emotions.

Revision ID: 20261120_03
Revises: 20261115_02
"""

import sqlalchemy as sa
from alembic import context, op

from app.activity_vocabulary import CATEGORY_ALIASES, EMOTION_ALIASES, resolve_id

revision = "20261120_03"
down_revision = "20261115_02"
branch_labels = None
depends_on = None

activities = sa.table(
    "activities",
    sa.column("id", sa.Integer()),
    sa.column("categories", sa.JSON()),
    sa.column("emotions", sa.JSON()),
)


def _normalize_list(
    activity_id: int, field: str, values: object, aliases: dict[str, str]
) -> list[str]:
    if not isinstance(values, list) or not values:
        raise RuntimeError(f"Activity {activity_id}: {field} must be a nonempty array")

    identifiers = []
    seen = set()
    for value in values:
        identifier = resolve_id(value, aliases) if isinstance(value, str) else None
        if identifier is None:
            raise RuntimeError(f"Activity {activity_id}: unknown value in {field}")
        if identifier in seen:
            raise RuntimeError(
                f"Activity {activity_id}: duplicate {identifier!r} in {field}"
            )
        identifiers.append(identifier)
        seen.add(identifier)
    return identifiers


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Vocabulary migration requires a live database connection")

    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # Prevent concurrent writes between validation and verification.
        connection.execute(sa.text("LOCK TABLE activities IN SHARE ROW EXCLUSIVE MODE"))

    query = sa.select(activities).order_by(activities.c.id)
    expected = []
    changes = []
    for row in connection.execute(query):
        categories = _normalize_list(
            row.id, "categories", row.categories, CATEGORY_ALIASES
        )
        emotions = _normalize_list(row.id, "emotions", row.emotions, EMOTION_ALIASES)
        expected.append((row.id, categories, emotions))
        if categories != row.categories or emotions != row.emotions:
            changes.append(
                {"activity_id": row.id, "categories": categories, "emotions": emotions}
            )

    if changes:
        connection.execute(
            sa.update(activities).where(activities.c.id == sa.bindparam("activity_id")),
            changes,
        )

    if connection.execute(query).all() != expected:
        raise RuntimeError("Vocabulary migration verification failed; rolling back")


def downgrade() -> None:
    raise RuntimeError(
        "Original labels cannot be reconstructed from IDs. "
        "Restore the pre-migration backup into a separate database."
    )
