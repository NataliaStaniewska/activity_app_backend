import json
import logging
import os
import re
from time import perf_counter

import groq
from fastapi import HTTPException, status

from app.schemas.analytics import RecommendationProfile
from app.schemas.recommendations import GeneratedRecommendations
from app.services.gemini import RecommendationModelSettings
from app.services.recommendation_output import (
    build_generated_recommendations,
    parse_recommendations,
)
from app.services.recommendation_prompt import build_recommendation_prompt

logger = logging.getLogger(__name__)

MAX_JSON_VALIDATION_RETRIES = 1
DEFAULT_GROQ_MAX_OUTPUT_TOKENS = 4096

GROQ_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "Ruch",
                            "Relaks",
                            "Kreatywność",
                            "Spotkania",
                            "Nauka",
                            "Inne",
                        ],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["name", "category", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["recommendations"],
    "additionalProperties": False,
}


def _log_groq_error(
    *,
    category: str,
    error_type: str,
    diagnostic: str,
    status_code: int | None = None,
    provider_error_code: str | None = None,
    provider_error_param: str | None = None,
    attempts: int = 0,
    failed_attempts: int = 0,
    retries: int = 0,
) -> None:
    logger.error(
        "Groq request failed: category=%s error_type=%s "
        "http_status=%s provider_error_code=%s provider_error_param=%s "
        "attempts=%s failed_attempts=%s retries=%s diagnostic=%s",
        category,
        error_type,
        status_code,
        provider_error_code or "unavailable",
        provider_error_param or "unavailable",
        attempts,
        failed_attempts,
        retries,
        diagnostic,
    )


def _log_groq_retry(
    *,
    error_type: str,
    diagnostic: str,
    provider_error_param: str | None,
    attempts: int,
    failed_attempts: int,
    retries: int,
) -> None:
    logger.warning(
        "Groq generation retry: category=json_validate_failed "
        "error_type=%s attempts=%s failed_attempts=%s retries=%s "
        "provider_error_param=%s diagnostic=%s",
        error_type,
        attempts,
        failed_attempts,
        retries,
        provider_error_param or "unavailable",
        diagnostic,
    )


def _safe_groq_diagnostic(
    message: str | None,
    *,
    api_key: str,
    prompt: str,
    profile: RecommendationProfile,
) -> str:
    if not message:
        return "Groq returned an HTTP error without a diagnostic message."

    safe_message = message.replace(prompt, "[profile prompt redacted]")
    safe_message = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        "Authorization: [redacted]",
        safe_message,
    )
    safe_message = safe_message.replace(api_key, "[API key redacted]")
    profile_values = _profile_string_values(profile.model_dump(mode="json"))
    for value in sorted(profile_values, key=len, reverse=True):
        safe_message = safe_message.replace(value, "[profile value redacted]")
    safe_message = re.sub(r"\s+", " ", safe_message).strip()
    return safe_message[:500]


def _profile_string_values(value: object) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, dict):
        return set().union(*(_profile_string_values(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_profile_string_values(item) for item in value))
    return set()


def _provider_error_details(
    exc: groq.APIStatusError,
) -> tuple[str | None, str | None, str | None]:
    body = exc.body
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return body, None, None

    if not isinstance(body, dict):
        return None, None, None

    error = body.get("error", body)
    if not isinstance(error, dict):
        return None, None, None

    message = error.get("message")
    code = error.get("code")
    param = error.get("param")
    return (
        message if isinstance(message, str) else None,
        code if isinstance(code, str) else None,
        param if isinstance(param, str) else None,
    )


class GroqRecommendationGenerator:
    def __init__(self, settings: RecommendationModelSettings):
        self.settings = settings
        self.max_output_tokens = int(
            os.getenv(
                "GROQ_MAX_OUTPUT_TOKENS",
                str(DEFAULT_GROQ_MAX_OUTPUT_TOKENS),
            )
        )

    def generate(
        self, profile: RecommendationProfile
    ) -> GeneratedRecommendations:
        if not self.settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Groq is not configured. Set GROQ_API_KEY.",
            )

        prompt = build_recommendation_prompt(profile)
        client = None
        started = perf_counter()
        attempts = 0
        failed_attempts = 0
        retries = 0
        try:
            client = groq.Groq(
                api_key=self.settings.api_key,
                timeout=self.settings.timeout_ms / 1000,
            )
            request_options = {
                "model": self.settings.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.settings.temperature,
                "top_p": self.settings.top_p,
                "max_completion_tokens": self.max_output_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "activity_recommendations",
                        "strict": True,
                        "schema": GROQ_RESPONSE_JSON_SCHEMA,
                    },
                },
            }
            while True:
                attempts += 1
                try:
                    response = client.chat.completions.create(**request_options)
                    break
                except Exception as exc:
                    failed_attempts += 1
                    if not isinstance(exc, groq.APIStatusError):
                        raise

                    provider_message, provider_code, provider_param = (
                        _provider_error_details(exc)
                    )
                    if (
                        provider_code != "json_validate_failed"
                        or retries >= MAX_JSON_VALIDATION_RETRIES
                    ):
                        raise

                    retries += 1
                    diagnostic = _safe_groq_diagnostic(
                        provider_message,
                        api_key=self.settings.api_key,
                        prompt=prompt,
                        profile=profile,
                    )
                    safe_provider_param = (
                        _safe_groq_diagnostic(
                            provider_param,
                            api_key=self.settings.api_key,
                            prompt=prompt,
                            profile=profile,
                        )
                        if provider_param
                        else None
                    )
                    _log_groq_retry(
                        error_type=type(exc).__name__,
                        diagnostic=diagnostic,
                        provider_error_param=safe_provider_param,
                        attempts=attempts,
                        failed_attempts=failed_attempts,
                        retries=retries,
                    )
        except groq.RateLimitError as exc:
            _log_groq_error(
                category="rate_limit",
                error_type=type(exc).__name__,
                diagnostic="Groq rate limit exceeded.",
                status_code=exc.status_code,
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Groq rate limit exceeded. Try again later.",
            ) from exc
        except groq.APITimeoutError as exc:
            _log_groq_error(
                category="timeout",
                error_type=type(exc).__name__,
                diagnostic="The request exceeded the configured timeout.",
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Groq request timed out.",
            ) from exc
        except groq.APIConnectionError as exc:
            _log_groq_error(
                category="network",
                error_type=type(exc).__name__,
                diagnostic="The Groq API could not be reached.",
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Groq could not be reached.",
            ) from exc
        except groq.AuthenticationError as exc:
            _log_groq_error(
                category="authentication",
                error_type=type(exc).__name__,
                diagnostic="Groq rejected the configured credentials.",
                status_code=exc.status_code,
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Groq authentication failed.",
            ) from exc
        except groq.NotFoundError as exc:
            _log_groq_error(
                category="model_unavailable",
                error_type=type(exc).__name__,
                diagnostic="The configured Groq model was not found.",
                status_code=exc.status_code,
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Configured Groq model is unavailable.",
            ) from exc
        except groq.APIStatusError as exc:
            http_status = exc.status_code
            provider_message, provider_code, provider_param = (
                _provider_error_details(exc)
            )
            diagnostic = _safe_groq_diagnostic(
                provider_message,
                api_key=self.settings.api_key,
                prompt=prompt,
                profile=profile,
            )
            safe_provider_code = (
                _safe_groq_diagnostic(
                    provider_code,
                    api_key=self.settings.api_key,
                    prompt=prompt,
                    profile=profile,
                )
                if provider_code
                else None
            )
            safe_provider_param = (
                _safe_groq_diagnostic(
                    provider_param,
                    api_key=self.settings.api_key,
                    prompt=prompt,
                    profile=profile,
                )
                if provider_param
                else None
            )
            if http_status in (408, 504):
                category = "timeout"
                public_status = status.HTTP_504_GATEWAY_TIMEOUT
                public_detail = "Groq request timed out."
            elif http_status == 429:
                category = "rate_limit"
                public_status = status.HTTP_429_TOO_MANY_REQUESTS
                public_detail = "Groq rate limit exceeded. Try again later."
            elif http_status >= 500:
                category = "provider_unavailable"
                public_status = status.HTTP_502_BAD_GATEWAY
                public_detail = "Groq is temporarily unavailable."
            else:
                category = (
                    "request_validation"
                    if http_status == 400
                    else "provider_request"
                )
                public_status = status.HTTP_502_BAD_GATEWAY
                public_detail = "Groq request failed."
            _log_groq_error(
                category=category,
                error_type=type(exc).__name__,
                diagnostic=diagnostic,
                status_code=http_status,
                provider_error_code=safe_provider_code,
                provider_error_param=safe_provider_param,
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=public_status,
                detail=public_detail,
            ) from exc
        except Exception as exc:
            _log_groq_error(
                category="client_error",
                error_type=type(exc).__name__,
                diagnostic="The Groq client failed before returning a response.",
                attempts=attempts,
                failed_attempts=failed_attempts,
                retries=retries,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Groq request failed.",
            ) from exc
        finally:
            if client is not None:
                client.close()

        elapsed_ms = round((perf_counter() - started) * 1000)
        response_text = None
        if response.choices:
            response_text = response.choices[0].message.content
        recommendations = parse_recommendations(
            profile,
            response_text,
            provider="Groq",
            log_failure=lambda error_type, diagnostic: _log_groq_error(
                category="response_validation",
                error_type=error_type,
                diagnostic=diagnostic,
                attempts=attempts,
                failed_attempts=failed_attempts + 1,
                retries=retries,
            ),
        )
        logger.info(
            "Groq generation completed: model=%s attempts=%s "
            "failed_attempts=%s retries=%s elapsed_ms=%s",
            self.settings.model,
            attempts,
            failed_attempts,
            retries,
            elapsed_ms,
        )
        return build_generated_recommendations(
            model=self.settings.model,
            prompt_version=self.settings.prompt_version,
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            max_output_tokens=self.max_output_tokens,
            elapsed_ms=elapsed_ms,
            recommendations=recommendations,
        )
