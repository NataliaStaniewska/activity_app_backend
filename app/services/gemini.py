from dataclasses import dataclass
import logging
import os
import re
from time import perf_counter
from typing import Protocol

import httpx
from fastapi import HTTPException, status
from google import genai
from google.genai import errors, types

from app.schemas.analytics import RecommendationProfile
from app.schemas.recommendations import GEMINI_RESPONSE_JSON_SCHEMA, GeneratedRecommendations
from app.services.recommendation_prompt import (
    PROMPT_VERSION,
    build_recommendation_prompt,
)
from app.services.recommendation_output import (
    build_generated_recommendations,
    parse_recommendations,
)

logger = logging.getLogger(__name__)


def _safe_diagnostic(message: str | None, *, api_key: str, prompt: str) -> str:
    if not message:
        return "No provider diagnostic message."
    safe_message = message.replace(prompt, "[profile prompt redacted]")
    safe_message = safe_message.replace(api_key, "[API key redacted]")
    safe_message = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"\1[redacted]",
        safe_message,
    )
    safe_message = re.sub(r"\bAIza[0-9A-Za-z_-]{20,}\b", "[API key redacted]", safe_message)
    safe_message = " ".join(safe_message.split())
    return safe_message[:500]


def _classify_api_error(exc: errors.APIError) -> tuple[str, int, str]:
    provider_status = (exc.status or "").upper()
    if exc.code in (401, 403):
        return "authentication", status.HTTP_502_BAD_GATEWAY, "Gemini authentication failed."
    if exc.code == 404 or "MODEL_NOT_FOUND" in provider_status or "NOT_FOUND" in provider_status:
        return "model_unavailable", status.HTTP_502_BAD_GATEWAY, "Configured Gemini model is unavailable."
    if exc.code == 429 or "RESOURCE_EXHAUSTED" in provider_status:
        return "rate_limit", status.HTTP_429_TOO_MANY_REQUESTS, "Gemini rate limit exceeded. Try again later."
    if exc.code in (408, 504):
        return "timeout", status.HTTP_504_GATEWAY_TIMEOUT, "Gemini request timed out."
    if exc.code >= 500:
        return "provider_unavailable", status.HTTP_502_BAD_GATEWAY, "Gemini is temporarily unavailable."
    return "provider_request", status.HTTP_502_BAD_GATEWAY, "Gemini request failed."


def _log_gemini_error(
    *,
    category: str,
    error_type: str,
    diagnostic: str,
    google_http_status: int | None = None,
    google_status: str | None = None,
) -> None:
    logger.error(
        "Gemini request failed: category=%s error_type=%s "
        "google_http_status=%s google_status=%s diagnostic=%s",
        category,
        error_type,
        google_http_status,
        google_status or "unavailable",
        diagnostic,
    )


@dataclass(frozen=True)
class RecommendationModelSettings:
    api_key: str | None
    model: str
    prompt_version: str
    temperature: float
    top_p: float
    max_output_tokens: int
    timeout_ms: int

    @classmethod
    def from_environment(
        cls,
        *,
        model: str | None = None,
        model_env: str = "GEMINI_MODEL",
        api_key_env: str = "GEMINI_API_KEY",
    ) -> "RecommendationModelSettings":
        model = model or os.getenv(model_env)
        if not model:
            raise RuntimeError(f"{model_env} is not set. Configure it in .env.")
        return cls(
            api_key=os.getenv(api_key_env),
            model=model,
            prompt_version=os.getenv(
                "RECOMMENDATION_PROMPT_VERSION",
                os.getenv("GEMINI_PROMPT_VERSION", PROMPT_VERSION),
            ),
            temperature=float(
                os.getenv("RECOMMENDATION_TEMPERATURE", os.getenv("GEMINI_TEMPERATURE", "0.4"))
            ),
            top_p=float(
                os.getenv("RECOMMENDATION_TOP_P", os.getenv("GEMINI_TOP_P", "0.9"))
            ),
            max_output_tokens=int(
                os.getenv(
                    "RECOMMENDATION_MAX_OUTPUT_TOKENS",
                    os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1200"),
                )
            ),
            timeout_ms=int(
                os.getenv(
                    "RECOMMENDATION_TIMEOUT_MS",
                    os.getenv("GEMINI_TIMEOUT_MS", "30000"),
                )
            ),
        )


GeminiSettings = RecommendationModelSettings


class RecommendationGenerator(Protocol):
    def generate(
        self, profile: RecommendationProfile
    ) -> GeneratedRecommendations: ...


class GeminiRecommendationGenerator:
    def __init__(self, settings: RecommendationModelSettings):
        self.settings = settings

    def generate(
        self, profile: RecommendationProfile
    ) -> GeneratedRecommendations:
        if not self.settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini is not configured. Set GEMINI_API_KEY.",
            )

        prompt = build_recommendation_prompt(profile)
        started = perf_counter()
        client = None
        try:
            client = genai.Client(
                api_key=self.settings.api_key,
                http_options=types.HttpOptions(timeout=self.settings.timeout_ms),
            )
            response = client.models.generate_content(
                model=self.settings.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.settings.temperature,
                    top_p=self.settings.top_p,
                    max_output_tokens=self.settings.max_output_tokens,
                    response_mime_type="application/json",
                    response_json_schema=GEMINI_RESPONSE_JSON_SCHEMA,
                ),
            )
        except (TimeoutError, httpx.TimeoutException) as exc:
            _log_gemini_error(
                category="timeout",
                error_type=type(exc).__name__,
                diagnostic="The request exceeded the configured timeout.",
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Gemini request timed out.",
            ) from exc
        except httpx.NetworkError as exc:
            _log_gemini_error(
                category="network",
                error_type=type(exc).__name__,
                diagnostic="The Gemini API could not be reached.",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini could not be reached.",
            ) from exc
        except errors.APIError as exc:
            category, http_status, public_message = _classify_api_error(exc)
            _log_gemini_error(
                category=category,
                error_type=type(exc).__name__,
                diagnostic=_safe_diagnostic(
                    exc.message,
                    api_key=self.settings.api_key,
                    prompt=prompt,
                ),
                google_http_status=exc.code,
                google_status=exc.status,
            )
            raise HTTPException(
                status_code=http_status,
                detail=public_message,
            ) from exc
        except Exception as exc:
            _log_gemini_error(
                category="client_error",
                error_type=type(exc).__name__,
                diagnostic="The Gemini client failed before returning a response.",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini request failed.",
            ) from exc
        finally:
            if client is not None:
                client.close()

        elapsed_ms = round((perf_counter() - started) * 1000)
        recommendations = parse_recommendations(
            profile,
            response.text,
            provider="Gemini",
            log_failure=lambda error_type, diagnostic: _log_gemini_error(
                category="response_validation",
                error_type=error_type,
                diagnostic=diagnostic,
            ),
        )
        return build_generated_recommendations(
            model=self.settings.model,
            prompt_version=self.settings.prompt_version,
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            max_output_tokens=self.settings.max_output_tokens,
            elapsed_ms=elapsed_ms,
            recommendations=recommendations,
        )


def get_recommendation_generator(
    model: str | None = None,
) -> RecommendationGenerator:
    gemini_model = os.getenv("GEMINI_MODEL")
    groq_model = os.getenv("GROQ_MODEL")
    configured_default = (
        os.getenv("RECOMMENDATION_DEFAULT_MODEL") or gemini_model or groq_model
    )
    selected_model = model or configured_default
    if not selected_model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No recommendation model is configured.",
        )

    if selected_model == gemini_model and gemini_model:
        settings = RecommendationModelSettings.from_environment(model=selected_model)
        return GeminiRecommendationGenerator(settings)
    if selected_model == groq_model and groq_model:
        settings = RecommendationModelSettings.from_environment(
            model=selected_model,
            model_env="GROQ_MODEL",
            api_key_env="GROQ_API_KEY",
        )
        from app.services.groq import GroqRecommendationGenerator

        return GroqRecommendationGenerator(settings)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Requested model is not configured.",
    )
