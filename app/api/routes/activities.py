from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.activity import ActivityEntry
from app.schemas.activity import ActivityCreate, ActivityRead

router = APIRouter(prefix="/activities", tags=["activities"])


@router.post(
    "",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    activity_data: ActivityCreate,
    db: Session = Depends(get_db),
) -> ActivityEntry:
    activity = ActivityEntry(**activity_data.model_dump())
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@router.get("", response_model=list[ActivityRead])
def list_activities(db: Session = Depends(get_db)) -> list[ActivityEntry]:
    statement = select(ActivityEntry).order_by(
        ActivityEntry.date.desc(),
        ActivityEntry.id.desc(),
    )
    return list(db.scalars(statement).all())


@router.get("/{activity_id}", response_model=ActivityRead)
def get_activity(
    activity_id: int = Path(gt=0),
    db: Session = Depends(get_db),
) -> ActivityEntry:
    activity = db.get(ActivityEntry, activity_id)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )
    return activity


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: int = Path(gt=0),
    db: Session = Depends(get_db),
) -> Response:
    activity = db.get(ActivityEntry, activity_id)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )
    db.delete(activity)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
