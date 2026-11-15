from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityEntry(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_activities_rating"),
        CheckConstraint(
            "mood_before IS NULL OR mood_before BETWEEN 1 AND 5",
            name="ck_activities_mood_before",
        ),
        CheckConstraint(
            "mood_after BETWEEN 1 AND 5",
            name="ck_activities_mood_after",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False)
    company_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mood_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mood_after: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    emotions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    likes: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dislikes: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
