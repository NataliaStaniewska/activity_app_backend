from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recommendations import GeneratedRecommendations
from app.services.analytics import build_recommendation_profile
from app.services.gemini import (
    RecommendationGenerator,
    get_recommendation_generator,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/generate", response_model=GeneratedRecommendations)
def generate_recommendations(
    db: Session = Depends(get_db),
    generator: RecommendationGenerator = Depends(get_recommendation_generator),
) -> GeneratedRecommendations:
    profile = build_recommendation_profile(db)
    return generator.generate(profile)
