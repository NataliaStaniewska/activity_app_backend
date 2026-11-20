from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.activity_vocabulary import CATEGORY_LABELS
from app.db.base import Base
from app.models.activity import ActivityEntry
from app.models.demo_import import DemoImportRun
from scripts.import_demo_data import (
    IMPORT_KEY,
    build_demo_entries,
    import_demo_data,
)


def _create_activity(client, valid_activity, **overrides):
    payload = {**deepcopy(valid_activity), **overrides}
    response = client.post("/activities", json=payload)
    assert response.status_code == 201
    return response.json()


def test_statistics_and_profile_for_empty_database(client):
    statistics = client.get("/statistics")
    profile = client.get("/recommendation-profile")

    assert statistics.status_code == 200
    assert statistics.json()["totalEntries"] == 0
    assert statistics.json()["activityOccurrences"] == []
    assert statistics.json()["categories"] == []
    assert statistics.json()["meanMoodChange"] == {
        "mean": None,
        "observations": 0,
    }

    assert profile.status_code == 200
    assert profile.json()["existingActivities"] == []
    assert profile.json()["frequentlyPerformed"] == []
    assert profile.json()["userStatements"] == []


def test_single_activity_and_missing_mood_before(client, valid_activity):
    _create_activity(client, valid_activity, moodBefore=None)

    statistics = client.get("/statistics").json()
    profile = client.get("/recommendation-profile").json()

    assert statistics["totalEntries"] == 1
    assert statistics["distinctActivities"] == 1
    assert statistics["activityOccurrences"][0]["count"] == 1
    assert statistics["activityOccurrences"][0]["meanMoodAfter"] == {
        "mean": 4.0,
        "observations": 1,
    }
    assert statistics["meanMoodChange"] == {"mean": None, "observations": 0}
    assert profile["activityPreferences"]["highestRating"] == []
    assert profile["userStatements"][0]["likes"] == "Świeże powietrze"


def test_statistics_aggregate_repeated_activities_and_multi_select_categories(
    client, valid_activity, db_session
):
    legacy = ActivityEntry(
        activity_name="Spacer",
        date=datetime(2025, 3, 8, 13, 30, tzinfo=timezone.utc),
        categories=["Ruch", "physical_activity", "Relaks", "Kategoria historyczna"],
        emotions=["spokój", "radość"],
        location_type="outdoor",
        company_type="alone",
        mood_before=2,
        mood_after=4,
        rating=5,
    )
    db_session.add(legacy)
    db_session.commit()
    _create_activity(
        client,
        valid_activity,
        date="2025-03-09T14:30:00Z",
        moodAfter=2,
        rating=3,
        moodBefore=None,
        categories=["physical_activity", "socializing"],
        likes="Lubię kontakt z naturą.",
        dislikes="Nie lubię deszczu.",
    )
    _create_activity(
        client,
        valid_activity,
        date="2025-03-10T14:30:00Z",
        moodAfter=5,
        rating=4,
        moodBefore=4,
        categories=["relaxation"],
        likes=None,
        notes=None,
    )

    statistics = client.get("/statistics").json()
    profile_response = client.get("/recommendation-profile")
    profile = profile_response.json()

    assert statistics["totalEntries"] == 3
    assert statistics["distinctActivities"] == 1
    assert statistics["distinctCategories"] == 4
    assert statistics["diversity"]["uniqueCategories"] == 4
    activity = statistics["activityOccurrences"][0]
    assert activity["count"] == 3
    assert activity["meanMoodAfter"] == {"mean": 3.67, "observations": 3}
    assert activity["meanRating"] == {"mean": 4.0, "observations": 3}

    categories = {item["name"]: item for item in statistics["categories"]}
    assert categories["physical_activity"]["count"] == 2
    assert categories["physical_activity"]["meanMoodAfter"] == {
        "mean": 3.0,
        "observations": 2,
    }
    assert categories["relaxation"]["count"] == 2
    assert categories["relaxation"]["meanRating"] == {
        "mean": 4.5,
        "observations": 2,
    }
    assert categories["socializing"]["count"] == 1
    assert categories["Kategoria historyczna"]["count"] == 1
    db_session.refresh(legacy)
    assert legacy.categories == [
        "Ruch", "physical_activity", "Relaks", "Kategoria historyczna"
    ]
    assert legacy.emotions == ["spokój", "radość"]

    assert statistics["moodAfterDistribution"] == [
        {"value": 2, "count": 1},
        {"value": 4, "count": 1},
        {"value": 5, "count": 1},
    ]
    assert statistics["meanMoodChange"] == {"mean": 1.5, "observations": 2}
    assert profile_response.status_code == 200
    assert profile["activityPreferences"]["highestRating"][0]["occurrences"] == 3
    rankings = profile["categoryPreferences"]["highestRating"]
    assert [(item["name"], item["occurrences"]) for item in rankings] == [
        ("relaxation", 2),
        ("physical_activity", 2),
    ]
    assert profile["contextPreferences"]["categories"]["highestRating"] == rankings
    assert profile["userStatements"][-1] == {
        "activityName": "Spacer",
        "likes": "Lubię kontakt z naturą.",
        "dislikes": "Nie lubię deszczu.",
    }


def test_demo_import_is_repeatable_without_duplicates():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        assert len(build_demo_entries()) == 40
        assert import_demo_data(factory) is True
        assert import_demo_data(factory) is False

        with factory() as db:
            activities = db.scalars(select(ActivityEntry)).all()
            assert len(activities) == 40
            categories = {value for entry in activities for value in entry.categories}
            emotions = {value for entry in activities for value in entry.emotions}
            assert categories == set(CATEGORY_LABELS)
            assert emotions == {"calm", "joy", "focus", "fatigue"}
            assert db.scalar(select(func.count()).select_from(DemoImportRun)) == 1
            assert db.get(DemoImportRun, IMPORT_KEY) is not None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
