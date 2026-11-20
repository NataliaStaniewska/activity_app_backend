import logging
from collections.abc import Callable

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.schemas.analytics import RecommendationProfile
from app.schemas.recommendations import (
    GeneratedRecommendations,
    GenerationConfig,
    Recommendation,
    RecommendationList,
)

logger = logging.getLogger(__name__)


def parse_recommendations(
    profile: RecommendationProfile,
    response_text: str | None,
    *,
    provider: str,
    log_failure: Callable[[str, str], None],
) -> list[Recommendation]:
    if not response_text:
        log_failure("EmptyResponse", f"{provider} returned no response text.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{provider} returned an empty response.",
        )
    try:
        parsed = RecommendationList.model_validate_json(response_text)
    except (ValidationError, ValueError) as exc:
        log_failure(
            type(exc).__name__,
            f"{provider} response did not match the required JSON schema.",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{provider} returned an invalid recommendation JSON response.",
        ) from exc

    existing_names = {
        entry.activity_name.casefold()
        for entry in profile.existing_activities
    }
    returned_names = [item.name.casefold() for item in parsed.recommendations]
    if len(set(returned_names)) != 3:
        log_failure(
            "DuplicateRecommendations",
            f"{provider} returned duplicate recommendation names.",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{provider} returned duplicate recommendations.",
        )
    if existing_names.intersection(returned_names):
        log_failure(
            "ExistingActivityRecommendation",
            f"{provider} recommended an activity already in the profile.",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{provider} recommended an activity already in the profile.",
        )
    return parsed.recommendations


def build_generated_recommendations(
    *,
    model: str,
    prompt_version: str,
    temperature: float,
    top_p: float,
    max_output_tokens: int,
    elapsed_ms: int,
    recommendations: list[Recommendation],
) -> GeneratedRecommendations:
    return GeneratedRecommendations(
        model=model,
        promptVersion=prompt_version,
        generationConfig=GenerationConfig(
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_output_tokens,
        ),
        elapsedMs=elapsed_ms,
        recommendations=recommendations,
    )
