from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BASE_REVISION = "20261115_02"
VOCABULARY_REVISION = "20261120_03"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def migration_database(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'alembic-test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, BASE_REVISION)
    engine = sa.create_engine(url)
    try:
        yield config, engine, sa.Table("activities", sa.MetaData(), autoload_with=engine)
    finally:
        engine.dispose()


def _insert_activity(engine, activities, activity_id, categories, emotions):
    with engine.begin() as connection:
        connection.execute(
            activities.insert().values(
                id=activity_id,
                activity_name="Spacer",
                date=sa.text("'2025-03-08 13:30:00'"),
                categories=categories,
                location_type="outdoor",
                company_type="withOthers",
                mood_before=None,
                mood_after=4,
                rating=5,
                emotions=emotions,
                likes="Świeże powietrze",
                dislikes=None,
                notes="Oryginalna notatka",
            )
        )


def _snapshot(engine, activities):
    with engine.connect() as connection:
        rows = connection.execute(activities.select().order_by(activities.c.id))
        revision = connection.execute(sa.text("SELECT version_num FROM alembic_version"))
        return [dict(row) for row in rows.mappings()], revision.scalar_one()


def test_upgrade_preserves_order_count_ids_and_other_fields(migration_database):
    config, engine, activities = migration_database
    _insert_activity(
        engine, activities, 4, ["Relaks", "Ruch"], ["radość", "spokój", "zmęczenie"]
    )
    _insert_activity(engine, activities, 19, ["learning"], ["focus"])
    original, _ = _snapshot(engine, activities)
    expected = [
        {
            **original[0],
            "categories": ["relaxation", "physical_activity"],
            "emotions": ["joy", "calm", "fatigue"],
        },
        original[1],
    ]
    command.upgrade(config, VOCABULARY_REVISION)
    assert _snapshot(engine, activities) == (expected, VOCABULARY_REVISION)

    command.upgrade(config, VOCABULARY_REVISION)
    assert _snapshot(engine, activities) == (expected, VOCABULARY_REVISION)

    # Re-run the data step itself against canonical data.
    command.stamp(config, BASE_REVISION)
    command.upgrade(config, VOCABULARY_REVISION)
    assert _snapshot(engine, activities) == (expected, VOCABULARY_REVISION)


@pytest.mark.parametrize(
    ("categories", "emotions", "message"),
    [
        (["Nieznana kategoria"], ["radość"], "unknown value in categories"),
        (["Ruch"], ["Radość", "joy"], "duplicate 'joy' in emotions"),
        (["Ruch", "physical_activity"], ["spokój"], "duplicate 'physical_activity'"),
        (["Ruch"], [], "emotions must be a nonempty array"),
        (["Ruch"], [123], "unknown value in emotions"),
    ],
)
def test_invalid_rows_leave_database_and_revision_unchanged(
    migration_database, categories, emotions, message
):
    config, engine, activities = migration_database
    _insert_activity(engine, activities, 4, ["Relaks"], ["radość"])
    _insert_activity(engine, activities, 19, categories, emotions)
    original = _snapshot(engine, activities)

    with pytest.raises(RuntimeError, match=message):
        command.upgrade(config, VOCABULARY_REVISION)

    assert _snapshot(engine, activities) == original


def test_verification_failure_rolls_back_updates(migration_database):
    config, engine, activities = migration_database
    _insert_activity(engine, activities, 4, ["Relaks"], ["radość"])

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TRIGGER corrupt_emotions AFTER UPDATE ON activities
            BEGIN
                UPDATE activities SET emotions = '["sadness"]' WHERE id = NEW.id;
            END
            """
        )
    original = _snapshot(engine, activities)

    with pytest.raises(RuntimeError, match="verification failed"):
        command.upgrade(config, VOCABULARY_REVISION)

    assert _snapshot(engine, activities) == original
