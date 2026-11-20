from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


from app.activity_vocabulary import CATEGORY_ALIASES, EMOTION_ALIASES, resolve_id


class LocationType(str, Enum):
    indoor = "indoor"
    outdoor = "outdoor"
    mixed = "mixed"


class CompanyType(str, Enum):
    alone = "alone"
    with_others = "withOthers"


class ActivityCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    activity_name: str = Field(alias="activityName", min_length=1, max_length=100)
    date: datetime
    categories: list[str] = Field(min_length=1)
    location_type: LocationType = Field(alias="locationType")
    company_type: CompanyType = Field(alias="companyType")
    mood_before: int | None = Field(default=None, alias="moodBefore", ge=1, le=5)
    mood_after: int = Field(alias="moodAfter", ge=1, le=5)
    rating: int = Field(ge=1, le=5)
    emotions: list[str] = Field(min_length=1)
    likes: str | None = Field(default=None, max_length=200)
    dislikes: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=300)

    @field_validator("activity_name")
    @classmethod
    def activity_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Activity name cannot be empty")
        return value

    @field_validator("categories", "emotions")
    @classmethod
    def normalize_vocabulary(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        aliases = (
            CATEGORY_ALIASES if info.field_name == "categories" else EMOTION_ALIASES
        )
        identifiers = []
        seen = set()
        for value in values:
            identifier = resolve_id(value, aliases)
            if identifier is None:
                raise ValueError(f"{info.field_name} must contain known values")
            if identifier in seen:
                raise ValueError(f"{info.field_name} must be unique after normalization")
            identifiers.append(identifier)
            seen.add(identifier)
        return identifiers

    @field_validator("date")
    @classmethod
    def date_must_be_aware_and_not_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Date must include a timezone")
        if value.astimezone(timezone.utc) > datetime.now(timezone.utc):
            raise ValueError("Date cannot be in the future")
        return value.astimezone(timezone.utc)


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    activity_name: str = Field(alias="activityName")
    date: datetime
    categories: list[str]
    location_type: LocationType = Field(alias="locationType")
    company_type: CompanyType = Field(alias="companyType")
    mood_before: int | None = Field(alias="moodBefore")
    mood_after: int = Field(alias="moodAfter")
    rating: int
    emotions: list[str]
    likes: str | None
    dislikes: str | None
    notes: str | None

    @field_validator("date", mode="before")
    @classmethod
    def normalize_sqlite_datetime(cls, value: datetime) -> datetime:
        # SQLite drops timezone metadata for DateTime(timezone=True); interpret
        # its stored value as UTC for consistent API serialization in tests.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
