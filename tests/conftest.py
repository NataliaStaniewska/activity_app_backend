import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.demo_import import DemoImportRun  # noqa: F401

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


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def prepare_database():
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def valid_activity():
    return {
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
