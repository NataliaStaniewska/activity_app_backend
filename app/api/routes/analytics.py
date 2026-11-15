from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import RecommendationProfile, StatisticsResponse
from app.services.analytics import build_recommendation_profile, build_statistics

router = APIRouter(tags=["analytics"])


@router.get("/statistics", response_model=StatisticsResponse)
def get_statistics(db: Session = Depends(get_db)) -> StatisticsResponse:
    return build_statistics(db)


@router.get("/recommendation-profile", response_model=RecommendationProfile)
def get_recommendation_profile(
    db: Session = Depends(get_db),
) -> RecommendationProfile:
    return build_recommendation_profile(db)
