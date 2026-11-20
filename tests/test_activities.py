import pytest

from app.models.activity import ActivityEntry


def test_create_and_read_activity(client, valid_activity, db_session):
    response = client.post("/activities", json=valid_activity)

    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["activityName"] == "Spacer"
    assert created["categories"] == ["physical_activity", "relaxation"]
    assert created["emotions"] == ["calm", "joy"]
    assert created["locationType"] == "outdoor"
    assert created["companyType"] == "alone"
    stored = db_session.get(ActivityEntry, created["id"])
    assert stored.categories == created["categories"]
    assert stored.emotions == created["emotions"]
    assert created["date"] == "2025-03-08T13:30:00Z"

    detail_response = client.get(f"/activities/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json() == created

    list_response = client.get("/activities")
    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_create_accepts_ids_and_polish_aliases_in_order(client, valid_activity):
    response = client.post(
        "/activities",
        json={
            **valid_activity,
            "categories": ["creativity", "  SPOTKANIA  ", "Nauka", "Inne"],
            "emotions": [
                "joy", "Spokój", "Zadowolenie", "Ekscytacja", "Smutek", "Złość",
                "Lęk", "Frustracja", "Obojętność", "  SKUPIENIE  ", "zmęczenie",
            ],
            "companyType": "withOthers",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["categories"] == ["creativity", "socializing", "learning", "other"]
    assert created["emotions"] == [
        "joy", "calm", "satisfaction", "excitement", "sadness", "anger",
        "anxiety", "frustration", "indifference", "focus", "fatigue",
    ]
    assert created["companyType"] == "withOthers"


def test_activities_are_listed_newest_first(client, valid_activity):
    older = {**valid_activity, "activityName": "Starsza", "date": "2025-03-07T10:00:00Z"}
    newer = {**valid_activity, "activityName": "Nowsza", "date": "2025-03-09T10:00:00Z"}

    assert client.post("/activities", json=older).status_code == 201
    assert client.post("/activities", json=newer).status_code == 201

    response = client.get("/activities")
    assert [activity["activityName"] for activity in response.json()] == [
        "Nowsza",
        "Starsza",
    ]


def test_optional_fields_can_be_omitted(client, valid_activity):
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
        ("categories", ["unknown"]),
        ("categories", ["Ruch", "physical_activity"]),
        ("emotions", []),
        ("emotions", [" "]),
        ("emotions", ["relaxation"]),
        ("emotions", ["Radość", "joy"]),
        ("locationType", "unknown"),
        ("companyType", "group"),
        ("date", "2025-03-08T14:30:00"),
        ("date", "2999-03-08T14:30:00Z"),
        ("notes", "x" * 301),
    ],
)
def test_invalid_activity_is_rejected(client, valid_activity, field, value):
    response = client.post("/activities", json={**valid_activity, field: value})

    assert response.status_code == 422


def test_missing_activity_returns_404(client):
    response = client.get("/activities/999")

    assert response.status_code == 404


def test_delete_activity(client, valid_activity):
    created = client.post("/activities", json=valid_activity).json()

    response = client.delete(f"/activities/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/activities/{created['id']}").status_code == 404


def test_delete_missing_activity_returns_404(client):
    response = client.delete("/activities/999")

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/activities/0", "/activities/-1"])
def test_nonpositive_activity_id_is_rejected(client, path):
    assert client.get(path).status_code == 422
