import json
import logging
from types import SimpleNamespace

import groq
import httpx
import pytest
from fastapi import HTTPException

from app.schemas.analytics import RecommendationProfile
from app.services.gemini import (
    RecommendationModelSettings,
    get_recommendation_generator,
)
from app.services.groq import (
    GROQ_RESPONSE_JSON_SCHEMA,
    GroqRecommendationGenerator,
)
from app.services.recommendation_prompt import build_recommendation_prompt

MODEL_RESPONSE = {
    "recommendations": [
        {
            "name": "Fotografia przyrodnicza",
            "category": "Kreatywność",
            "reason": "Lubisz spacery na zewnątrz.",
        },
        {
            "name": "Obserwowanie ptaków",
            "category": "Relaks",
            "reason": "Często wybierasz spokojne aktywności.",
        },
        {
            "name": "Warsztaty ceramiczne",
            "category": "Kreatywność",
            "reason": "Rysowanie pojawia się w Twojej historii.",
        },
    ]
}


def _settings(**overrides):
    values = {
        "api_key": "test-groq-key",
        "model": "openai/gpt-oss-20b",
        "prompt_version": "v3",
        "temperature": 0.4,
        "top_p": 0.9,
        "max_output_tokens": 1200,
        "timeout_ms": 15000,
    }
    values.update(overrides)
    return RecommendationModelSettings(**values)


def _profile(client, valid_activity):
    response = client.post("/activities", json=valid_activity)
    assert response.status_code == 201
    response = client.get("/recommendation-profile")
    assert response.status_code == 200
    return RecommendationProfile.model_validate(response.json())


class FakeGroqCompletions:
    def __init__(self, *, content=None, error=None, responses=None):
        self.content = content
        self.error = error
        self.responses = list(responses) if responses is not None else None
        self.request = None
        self.requests = []

    def create(self, **kwargs):
        self.request = kwargs
        self.requests.append(kwargs)
        if self.responses is not None:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        if self.error:
            raise self.error
        return _completion_response(self.content)


class FakeGroqClient:
    def __init__(self, *, content=None, error=None, responses=None, **kwargs):
        self.chat = SimpleNamespace(
            completions=FakeGroqCompletions(
                content=content,
                error=error,
                responses=responses,
            )
        )
        self.options = kwargs
        self.closed = False

    def close(self):
        self.closed = True


def _completion_response(content):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


def _api_status_error(
    error_type,
    status_code,
    *,
    message="provider returned an API error",
    code="provider_error",
    param=None,
):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type(
        message,
        response=response,
        body={
            "error": {
                "message": message,
                "code": code,
                "param": param,
            }
        },
    )


def test_groq_generator_uses_shared_prompt_and_strict_json_schema(
    client, valid_activity, monkeypatch
):
    monkeypatch.delenv("GROQ_MAX_OUTPUT_TOKENS", raising=False)
    profile = _profile(client, valid_activity)

    fake_clients = []

    def fake_factory(**kwargs):
        fake_client = FakeGroqClient(content=json.dumps(MODEL_RESPONSE), **kwargs)
        fake_clients.append(fake_client)
        return fake_client

    monkeypatch.setattr(
        "app.services.groq.groq.Groq",
        fake_factory,
    )

    result = GroqRecommendationGenerator(_settings()).generate(profile)
    fake_client = fake_clients[0]

    assert result.model == "openai/gpt-oss-20b"
    assert result.prompt_version == "v3"
    assert result.generation_config.temperature == 0.4
    assert result.generation_config.top_p == 0.9
    assert result.generation_config.max_output_tokens == 4096
    assert result.elapsed_ms >= 0
    assert len(result.recommendations) == 3
    assert fake_client.closed
    assert fake_client.options["timeout"] == 15

    request = fake_client.chat.completions.request
    assert request["model"] == "openai/gpt-oss-20b"
    assert request["messages"] == [
        {"role": "user", "content": build_recommendation_prompt(profile)}
    ]
    assert request["temperature"] == 0.4
    assert request["top_p"] == 0.9
    assert request["max_completion_tokens"] == 4096
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "activity_recommendations",
            "strict": True,
            "schema": GROQ_RESPONSE_JSON_SCHEMA,
        },
    }


def test_groq_schema_is_strict_and_matches_the_recommendation_contract():
    assert GROQ_RESPONSE_JSON_SCHEMA["required"] == ["recommendations"]
    assert GROQ_RESPONSE_JSON_SCHEMA["additionalProperties"] is False
    recommendation_schema = GROQ_RESPONSE_JSON_SCHEMA["properties"]["recommendations"]
    item_schema = recommendation_schema["items"]
    assert item_schema["required"] == ["name", "category", "reason"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["properties"]) == {"name", "category", "reason"}
    assert all(
        field["type"] == "string" for field in item_schema["properties"].values()
    )
    assert item_schema["properties"]["category"]["enum"] == [
        "Ruch",
        "Relaks",
        "Kreatywność",
        "Spotkania",
        "Nauka",
        "Inne",
    ]


def test_groq_specific_token_limit_overrides_shared_setting(monkeypatch):
    monkeypatch.setenv("GROQ_MAX_OUTPUT_TOKENS", "4096")
    settings = _settings(max_output_tokens=1200)

    generator = GroqRecommendationGenerator(settings)

    assert settings.max_output_tokens == 1200
    assert generator.max_output_tokens == 4096


def test_groq_retries_json_validation_once_with_identical_request(
    client, valid_activity, monkeypatch, caplog
):
    profile = _profile(client, valid_activity)
    validation_error = _api_status_error(
        groq.BadRequestError,
        400,
        message="Failed to validate JSON.",
        code="json_validate_failed",
    )
    fake_client = FakeGroqClient(
        responses=[
            validation_error,
            _completion_response(json.dumps(MODEL_RESPONSE)),
        ]
    )
    monkeypatch.setattr("app.services.groq.groq.Groq", lambda **kwargs: fake_client)

    with caplog.at_level(logging.INFO, logger="app.services.groq"):
        result = GroqRecommendationGenerator(_settings()).generate(profile)

    requests = fake_client.chat.completions.requests
    assert len(requests) == 2
    assert requests[0] == requests[1]
    assert len(result.recommendations) == 3
    assert "attempts=1 failed_attempts=1 retries=1" in caplog.text
    assert "attempts=2 failed_attempts=1 retries=1" in caplog.text


def test_groq_does_not_retry_json_validation_more_than_once(
    client, valid_activity, monkeypatch, caplog
):
    profile = _profile(client, valid_activity)
    fake_client = FakeGroqClient(
        responses=[
            _api_status_error(
                groq.BadRequestError,
                400,
                message="Failed to validate JSON.",
                code="json_validate_failed",
            ),
            _api_status_error(
                groq.BadRequestError,
                400,
                message="Failed to validate JSON again.",
                code="json_validate_failed",
            ),
        ]
    )
    monkeypatch.setattr("app.services.groq.groq.Groq", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GroqRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502
    assert len(fake_client.chat.completions.requests) == 2
    assert "category=request_validation" in caplog.text
    assert "attempts=2 failed_attempts=2 retries=1" in caplog.text


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_category"),
    [
        (
            _api_status_error(groq.RateLimitError, 429),
            429,
            "rate_limit",
        ),
        (
            groq.APITimeoutError(
                request=httpx.Request(
                    "POST", "https://api.groq.com/openai/v1/chat/completions"
                )
            ),
            504,
            "timeout",
        ),
        (
            groq.APIConnectionError(
                request=httpx.Request(
                    "POST", "https://api.groq.com/openai/v1/chat/completions"
                )
            ),
            502,
            "network",
        ),
        (
            _api_status_error(groq.AuthenticationError, 401),
            502,
            "authentication",
        ),
        (
            _api_status_error(groq.NotFoundError, 404),
            502,
            "model_unavailable",
        ),
        (
            _api_status_error(groq.InternalServerError, 500),
            502,
            "provider_unavailable",
        ),
    ],
)
def test_groq_errors_are_mapped_and_logged_without_sensitive_data(
    client, valid_activity, monkeypatch, caplog, exception, expected_status,
    expected_category
):
    profile = _profile(client, valid_activity)
    fake_client = FakeGroqClient(error=exception)
    monkeypatch.setattr("app.services.groq.groq.Groq", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GroqRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == expected_status
    assert f"category={expected_category}" in caplog.text
    assert "test-groq-key" not in caplog.text
    assert "Spacer" not in caplog.text
    assert fake_client.closed


def test_groq_bad_request_logs_provider_diagnostic_safely(
    client, valid_activity, monkeypatch, caplog
):
    profile = _profile(client, valid_activity)
    activity_name = profile.existing_activities[0].activity_name
    exception = _api_status_error(
        groq.BadRequestError,
        400,
        message=(
            f"Invalid request for activity '{activity_name}' using "
            "Authorization: Bearer test-groq-key."
        ),
        code="invalid_request_error",
        param="response_format",
    )
    fake_client = FakeGroqClient(error=exception)
    monkeypatch.setattr("app.services.groq.groq.Groq", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GroqRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502
    assert "category=request_validation" in caplog.text
    assert "http_status=400" in caplog.text
    assert "invalid_request_error" in caplog.text
    assert "response_format" in caplog.text
    assert "Invalid request" in caplog.text
    assert activity_name not in caplog.text
    assert "test-groq-key" not in caplog.text
    assert "Authorization: Bearer" not in caplog.text
    assert len(fake_client.chat.completions.requests) == 1


def test_groq_invalid_response_uses_shared_validation(
    client, valid_activity, monkeypatch, caplog
):
    profile = _profile(client, valid_activity)
    fake_client = FakeGroqClient(content=json.dumps({"recommendations": []}))
    monkeypatch.setattr("app.services.groq.groq.Groq", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GroqRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502
    assert "category=response_validation" in caplog.text


def test_model_selection_uses_configured_default_and_supports_both_models(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("RECOMMENDATION_DEFAULT_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    default_generator = get_recommendation_generator()
    groq_generator = get_recommendation_generator(model="openai/gpt-oss-20b")
    gemini_generator = get_recommendation_generator(model="gemini-3.5-flash-lite")

    assert default_generator.settings.model == "gemini-3.5-flash-lite"
    assert groq_generator.settings.model == "openai/gpt-oss-20b"
    assert groq_generator.settings.api_key == "test-groq-key"
    assert gemini_generator.settings.model == "gemini-3.5-flash-lite"


def test_unknown_model_is_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")

    with pytest.raises(HTTPException) as error:
        get_recommendation_generator(model="unknown/model")

    assert error.value.status_code == 422


def test_endpoint_model_query_selects_groq(
    client, valid_activity, monkeypatch
):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("RECOMMENDATION_DEFAULT_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GROQ_MAX_OUTPUT_TOKENS", "4096")
    fake_client = FakeGroqClient(content=json.dumps(MODEL_RESPONSE))
    monkeypatch.setattr("app.services.groq.groq.Groq", lambda **kwargs: fake_client)

    response = client.post(
        "/recommendations/generate",
        params={"model": "openai/gpt-oss-20b"},
    )

    assert response.status_code == 200
    assert response.json()["model"] == "openai/gpt-oss-20b"
    assert response.json()["promptVersion"] == "v3"
    assert response.json()["generationConfig"]["max_output_tokens"] == 4096
    assert len(response.json()["recommendations"]) == 3

