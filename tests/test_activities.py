import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
valid_activity = {
    "activityName": "Spacer",
    "date": "2025-03-08T14:30:00+01:00",
    "categories": ["Ruch", "Relaks"],
    "locationType": "outdoor",
    "companyType": "alone",
    "moodBefore": 2,
    "moodAfter": 4,
    "rating": 5,
    "emotions": ["spokój", "radość"],
    "likes": "Świeże powietrze",
    "dislikes": None,
    "notes": "Spacer w parku",
}


@pytest.fixture(autouse=True)
def prepare_database():
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


def test_create_and_read_activity():
    response = client.post("/activities", json=valid_activity)

    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["activityName"] == "Spacer"
    assert created["categories"] == ["Ruch", "Relaks"]
    assert created["date"] == "2025-03-08T13:30:00Z"

    detail_response = client.get(f"/activities/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json() == created

    list_response = client.get("/activities")
    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_activities_are_listed_newest_first():
    older = {**valid_activity, "activityName": "Starsza", "date": "2025-03-07T10:00:00Z"}
    newer = {**valid_activity, "activityName": "Nowsza", "date": "2025-03-09T10:00:00Z"}

    assert client.post("/activities", json=older).status_code == 201
    assert client.post("/activities", json=newer).status_code == 201

    response = client.get("/activities")
    assert [activity["activityName"] for activity in response.json()] == [
        "Nowsza",
        "Starsza",
    ]


def test_optional_fields_can_be_omitted():
    activity = {
        **valid_activity,
        "moodBefore": None,
        "likes": None,
        "dislikes": None,
        "notes": None,
    }
    activity.pop("moodBefore")
    activity.pop("likes")
    activity.pop("dislikes")
    activity.pop("notes")

    response = client.post("/activities", json=activity)

    assert response.status_code == 201
    assert response.json()["moodBefore"] is None
    assert response.json()["likes"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rating", 0),
        ("rating", 6),
        ("moodAfter", 6),
        ("moodBefore", 0),
        ("activityName", "   "),
        ("categories", []),
        ("emotions", []),
        ("locationType", "unknown"),
        ("companyType", "group"),
        ("date", "2025-03-08T14:30:00"),
        ("date", "2999-03-08T14:30:00Z"),
        ("notes", "x" * 301),
    ],
)
def test_invalid_activity_is_rejected(field, value):
    response = client.post("/activities", json={**valid_activity, field: value})

    assert response.status_code == 422


def test_missing_activity_returns_404():
    response = client.get("/activities/999")

    assert response.status_code == 404


def test_delete_activity():
    created = client.post("/activities", json=valid_activity).json()

    response = client.delete(f"/activities/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/activities/{created['id']}").status_code == 404


def test_delete_missing_activity_returns_404():
    response = client.delete("/activities/999")

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/activities/0", "/activities/-1"])
def test_nonpositive_activity_id_is_rejected(path):
    assert client.get(path).status_code == 422
