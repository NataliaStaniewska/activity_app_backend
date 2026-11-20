from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal
from app.models.activity import ActivityEntry
from app.models.demo_import import DemoImportRun

IMPORT_KEY = "activity-demo-v1"

_DEMO_ACTIVITIES = [
    {
        "name": "Spacer",
        "categories": ["physical_activity", "relaxation"],
        "locations": ["outdoor", "outdoor", "mixed", "outdoor"],
        "companies": ["alone", "alone", "withOthers", "alone"],
        "moods": [4, 5, 3, 4],
        "ratings": [5, 5, 3, 4],
        "moods_before": [2, 3, 2, None],
        "likes": "Lubię świeże powietrze i spokojne tempo.",
        "dislikes": None,
    },
    {
        "name": "Czytanie",
        "categories": ["relaxation", "learning"],
        "locations": ["indoor", "indoor", "indoor", "mixed"],
        "companies": ["alone", "alone", "alone", "alone"],
        "moods": [4, 3, 5, 4],
        "ratings": [4, 3, 5, 4],
        "moods_before": [3, 3, 2, 4],
        "likes": "Najbardziej lubię czytać bez pośpiechu.",
        "dislikes": None,
    },
    {
        "name": "Gotowanie",
        "categories": ["creativity", "relaxation"],
        "locations": ["indoor", "indoor", "indoor", "indoor"],
        "companies": ["alone", "withOthers", "alone", "withOthers"],
        "moods": [3, 4, 4, 2],
        "ratings": [4, 4, 3, 2],
        "moods_before": [3, 3, None, 3],
        "likes": "Eksperymentowanie z nowymi przepisami.",
        "dislikes": "Nie lubię sprzątać po gotowaniu.",
    },
    {
        "name": "Rysowanie",
        "categories": ["creativity", "relaxation"],
        "locations": ["indoor", "indoor", "indoor", "indoor"],
        "companies": ["alone", "alone", "alone", "alone"],
        "moods": [4, 3, 4, 5],
        "ratings": [4, 3, 5, 5],
        "moods_before": [3, 4, 2, 3],
        "likes": "Lubię rysować przy muzyce.",
        "dislikes": None,
    },
    {
        "name": "Joga",
        "categories": ["physical_activity", "relaxation"],
        "locations": ["indoor", "indoor", "outdoor", "indoor"],
        "companies": ["alone", "withOthers", "alone", "alone"],
        "moods": [4, 3, 5, 4],
        "ratings": [4, 3, 5, 4],
        "moods_before": [2, 3, 3, None],
        "likes": "Pomaga mi się wyciszyć po pracy.",
        "dislikes": None,
    },
    {
        "name": "Jazda na rowerze",
        "categories": ["physical_activity", "other"],
        "locations": ["outdoor", "outdoor", "mixed", "outdoor"],
        "companies": ["alone", "withOthers", "alone", "withOthers"],
        "moods": [5, 4, 3, 4],
        "ratings": [5, 4, 3, 4],
        "moods_before": [3, 2, 3, 3],
        "likes": "Lubię odkrywać nowe trasy.",
        "dislikes": "Duży ruch na drodze odbiera mi przyjemność.",
    },
    {
        "name": "Spotkanie ze znajomymi",
        "categories": ["socializing", "relaxation"],
        "locations": ["indoor", "outdoor", "indoor", "mixed"],
        "companies": ["withOthers", "withOthers", "withOthers", "withOthers"],
        "moods": [4, 5, 3, 4],
        "ratings": [5, 5, 3, 4],
        "moods_before": [3, 3, 4, None],
        "likes": "Lubię rozmowy w małym gronie.",
        "dislikes": "Głośne, zatłoczone miejsca.",
    },
    {
        "name": "Nauka języka",
        "categories": ["learning", "creativity"],
        "locations": ["indoor", "indoor", "mixed", "indoor"],
        "companies": ["alone", "alone", "withOthers", "alone"],
        "moods": [3, 4, 3, 5],
        "ratings": [4, 4, 3, 5],
        "moods_before": [3, 2, 3, 3],
        "likes": "Cieszy mnie zauważanie postępów.",
        "dislikes": None,
    },
    {
        "name": "Ogrodnictwo",
        "categories": ["relaxation", "other"],
        "locations": ["outdoor", "mixed", "outdoor", "outdoor"],
        "companies": ["alone", "alone", "withOthers", "alone"],
        "moods": [5, 4, 4, 3],
        "ratings": [5, 4, 4, 3],
        "moods_before": [2, 3, 3, None],
        "likes": "Przyjemnie obserwować, jak rośliny rosną.",
        "dislikes": "Praca w upale bywa męcząca.",
    },
    {
        "name": "Gry planszowe",
        "categories": ["socializing", "creativity"],
        "locations": ["indoor", "indoor", "indoor", "indoor"],
        "companies": ["withOthers", "withOthers", "withOthers", "withOthers"],
        "moods": [4, 3, 5, 4],
        "ratings": [5, 3, 5, 4],
        "moods_before": [3, 3, 2, 4],
        "likes": "Lubię gry kooperacyjne.",
        "dislikes": "Długie oczekiwanie na swoją kolej.",
    },
]


def build_demo_entries() -> list[ActivityEntry]:
    start = datetime(2025, 1, 1, 17, tzinfo=timezone.utc)
    entries = []
    for activity_index, activity in enumerate(_DEMO_ACTIVITIES):
        for occurrence in range(4):
            entries.append(
                ActivityEntry(
                    activity_name=activity["name"],
                    date=start
                    + timedelta(days=activity_index * 18 + occurrence * 40),
                    categories=activity["categories"],
                    location_type=activity["locations"][occurrence],
                    company_type=activity["companies"][occurrence],
                    mood_before=activity["moods_before"][occurrence],
                    mood_after=activity["moods"][occurrence],
                    rating=activity["ratings"][occurrence],
                    emotions=["calm", "joy"]
                    if activity["moods"][occurrence] >= 4
                    else ["focus", "fatigue"],
                    likes=activity["likes"] if occurrence == 0 else None,
                    dislikes=activity["dislikes"] if occurrence == 0 else None,
                    notes=None,
                )
            )
    return entries


def import_demo_data(
    session_factory: sessionmaker[Session] = SessionLocal,
) -> bool:
    try:
        with session_factory.begin() as db:
            if db.get(DemoImportRun, IMPORT_KEY) is not None:
                return False
            db.add(DemoImportRun(import_key=IMPORT_KEY))
            db.flush()
            db.add_all(build_demo_entries())
    except IntegrityError:
        with session_factory() as db:
            if db.get(DemoImportRun, IMPORT_KEY) is not None:
                return False
        raise
    return True


def main() -> None:
    if import_demo_data():
        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(ActivityEntry))
        print(f"Imported 40 demo activities. Total activity records: {total}.")
    else:
        print(f"Demo import {IMPORT_KEY!r} already exists; no records were added.")


if __name__ == "__main__":
    main()
