import json

import httpx
import pytest
from fastapi import HTTPException
from google.genai import errors

from app.schemas.analytics import RecommendationProfile
from app.schemas.recommendations import GEMINI_RESPONSE_JSON_SCHEMA
from app.services.gemini import (
    GeminiRecommendationGenerator,
    GeminiSettings,
    get_recommendation_generator,
)
from app.services.recommendation_prompt import (
    PROMPT_VERSION,
    build_recommendation_prompt,
)


MODEL_RESPONSE = {
    "recommendations": [
        {
            "name": "Fotografia przyrodnicza",
            "category": "Kreatywność",
            "reason": "W historii często pojawiają się spacery na zewnątrz.",
        },
        {
            "name": "Obserwowanie ptaków",
            "category": "Relaks",
            "reason": "Profil zawiera pozytywne oceny spokojnych aktywności.",
        },
        {
            "name": "Warsztaty ceramiczne",
            "category": "Kreatywność",
            "reason": "Rysowanie jest wykonywane wielokrotnie.",
        },
    ]
}


def _settings(**overrides):
    values = {
        "api_key": "test-key-not-used",
        "model": "gemini-3.5-flash-lite",
        "prompt_version": "v3",
        "temperature": 0.4,
        "top_p": 0.9,
        "max_output_tokens": 1200,
        "timeout_ms": 30000,
    }
    values.update(overrides)
    return GeminiSettings(**values)


def _profile(client, valid_activity):
    created = client.post("/activities", json=valid_activity)
    assert created.status_code == 201
    response = client.get("/recommendation-profile")
    assert response.status_code == 200
    return RecommendationProfile.model_validate(response.json())


class FakeModels:
    def __init__(self, response_text=None, error=None):
        self.response_text = response_text
        self.error = error
        self.call = None

    def generate_content(self, **kwargs):
        self.call = kwargs
        if self.error:
            raise self.error
        return type("Response", (), {"text": self.response_text})()


class FakeClient:
    def __init__(self, *, response_text=None, error=None, **kwargs):
        self.models = FakeModels(response_text=response_text, error=error)
        self.closed = False
        self.options = kwargs

    def close(self):
        self.closed = True


def test_generate_recommendations_uses_profile_and_validates_json(
    client, valid_activity, monkeypatch
):
    profile = _profile(client, valid_activity)
    fake_client = FakeClient(response_text=json.dumps(MODEL_RESPONSE))
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    result = GeminiRecommendationGenerator(_settings()).generate(profile)

    assert len(result.recommendations) == 3
    assert result.model == "gemini-3.5-flash-lite"
    assert result.prompt_version == "v3"
    assert result.generation_config.temperature == 0.4
    assert result.elapsed_ms >= 0
    assert fake_client.closed
    request = fake_client.models.call
    assert request["model"] == "gemini-3.5-flash-lite"
    assert "Spacer" in request["contents"]
    assert "dokładnie 3" in request["contents"]
    assert request["config"].response_mime_type == "application/json"
    assert request["config"].response_json_schema == GEMINI_RESPONSE_JSON_SCHEMA
    assert request["config"].response_schema is None
    assert request["config"].temperature == 0.4
    assert request["config"].top_p == 0.9
    assert request["config"].max_output_tokens == 1200


def test_recommendation_prompt_is_polish_profile_grounded_and_versioned(
    client, valid_activity
):
    profile = _profile(client, valid_activity)
    prompt = build_recommendation_prompt(profile)

    assert PROMPT_VERSION == "v3"
    assert "Wszystkie wartości pól name, category i reason muszą być napisane po polsku." in prompt
    assert "dokładnie 3" in prompt
    assert "ocenach samopoczucia" in prompt
    assert "zaobserwowanych zmianach samopoczucia" in prompt
    assert "kontekście (kategoria, miejsce," in prompt
    assert "oczywistych synonimów" in prompt
    assert "Nie wymyślaj zainteresowań, preferencji" in prompt
    assert "ostrożnie i eksploracyjnie" in prompt
    assert "w drugiej" in prompt
    assert "naturalnym, przyjaznym językiem" in prompt
    assert "Lubisz..." in prompt
    assert "Często wybierasz..." in prompt
    assert "Ta aktywność może Ci się" in prompt
    assert "analiza profilu wskazuje" in prompt
    assert "bez specjalistycznego" in prompt
    assert "Nie wykluczaj" in prompt
    assert "Ruch, Relaks, Kreatywność, Spotkania, Nauka, Inne" in prompt
    assert "Nie twierdź, że aktywność na pewno poprawi samopoczucie." in prompt
    assert "wyłącznie cytowanymi danymi użytkownika, a nie" in prompt
    assert "Zwróć wyłącznie poprawny obiekt JSON" in prompt
    assert '"activityName":"Spacer"' in prompt
    assert '"likes":"Świeże powietrze"' in prompt


def test_gemini_json_schema_is_supported_and_requires_exact_recommendation_shape():
    supported_keywords = {
        "$id",
        "$defs",
        "$ref",
        "$anchor",
        "type",
        "format",
        "title",
        "description",
        "enum",
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "anyOf",
        "oneOf",
        "properties",
        "additionalProperties",
        "required",
        "propertyOrdering",
    }

    def assert_supported_schema(schema):
        assert set(schema).issubset(supported_keywords)
        assert "additional_properties" not in schema
        assert "additionalProperties" not in schema
        if "properties" in schema:
            for child in schema["properties"].values():
                assert_supported_schema(child)
        if "items" in schema:
            assert_supported_schema(schema["items"])

    assert_supported_schema(GEMINI_RESPONSE_JSON_SCHEMA)
    assert GEMINI_RESPONSE_JSON_SCHEMA["required"] == ["recommendations"]
    recommendations = GEMINI_RESPONSE_JSON_SCHEMA["properties"]["recommendations"]
    assert recommendations["type"] == "array"
    assert recommendations["minItems"] == recommendations["maxItems"] == 3
    item_schema = recommendations["items"]
    assert item_schema["type"] == "object"
    assert item_schema["required"] == ["name", "category", "reason"]
    assert all(
        field_schema["type"] == "string"
        for field_schema in item_schema["properties"].values()
    )
    assert set(item_schema["properties"]) == {"name", "category", "reason"}


@pytest.mark.parametrize(
    "response_text",
    [
        "not json",
        json.dumps({"recommendations": MODEL_RESPONSE["recommendations"][:2]}),
        json.dumps(
            {
                "recommendations": [
                    *MODEL_RESPONSE["recommendations"][:2],
                    {"name": "Brak pola", "category": "Test"},
                ]
            }
        ),
        json.dumps(
            {
                "recommendations": [
                    *MODEL_RESPONSE["recommendations"][:2],
                    {
                        "name": "Niepoprawne",
                        "category": "Test",
                        "reason": "ok",
                        "extra": "forbidden",
                    },
                ]
            }
        ),
    ],
)
def test_invalid_model_json_returns_502(
    client, valid_activity, monkeypatch, response_text
):
    profile = _profile(client, valid_activity)
    fake_client = FakeClient(response_text=response_text)
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502
    assert fake_client.closed


def test_existing_or_duplicate_recommendations_are_rejected(
    client, valid_activity, monkeypatch
):
    profile = _profile(client, valid_activity)
    existing_name = "Spacer"
    response = {
        "recommendations": [
            {"name": existing_name, "category": "Relaks", "reason": "reason"},
            MODEL_RESPONSE["recommendations"][1],
            MODEL_RESPONSE["recommendations"][2],
        ]
    }
    fake_client = FakeClient(response_text=json.dumps(response))
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502

    duplicate_response = {
        "recommendations": [
            MODEL_RESPONSE["recommendations"][0],
            MODEL_RESPONSE["recommendations"][0],
            MODEL_RESPONSE["recommendations"][2],
        ]
    }
    fake_client = FakeClient(response_text=json.dumps(duplicate_response))
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_category"),
    [
        (errors.APIError(401, {"message": "invalid credential"}), 502, "authentication"),
        (errors.APIError(403, {"message": "permission denied"}), 502, "authentication"),
        (
            errors.APIError(404, {"error": {"status": "NOT_FOUND", "message": "model missing"}}),
            502,
            "model_unavailable",
        ),
        (errors.APIError(429, {"message": "rate limited"}), 429, "rate_limit"),
        (errors.APIError(503, {"message": "upstream unavailable"}), 502, "provider_unavailable"),
        (httpx.ReadTimeout("timeout"), 504, "timeout"),
        (httpx.ConnectError("unavailable"), 502, "network"),
    ],
)
def test_gemini_errors_are_mapped_without_leaking_provider_messages(
    client,
    valid_activity,
    monkeypatch,
    caplog,
    exception,
    expected_status,
    expected_category,
):
    profile = _profile(client, valid_activity)
    fake_client = FakeClient(error=exception)
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == expected_status
    assert "rate limited" not in str(error.value.detail)
    assert fake_client.closed
    assert f"category={expected_category}" in caplog.text
    if isinstance(exception, errors.APIError):
        assert f"google_http_status={exception.code}" in caplog.text
    assert "test-key-not-used" not in caplog.text
    assert "Spacer" not in caplog.text


def test_api_error_diagnostic_redacts_api_key_and_profile_prompt(
    client, valid_activity, monkeypatch, caplog
):
    profile = _profile(client, valid_activity)
    prompt = build_recommendation_prompt(profile)
    message = (
        "API key test-key-not-used failed; request was "
        f"{prompt}; Authorization: Bearer secret-header"
    )
    fake_client = FakeClient(
        error=errors.APIError(
            401,
            {"error": {"status": "UNAUTHENTICATED", "message": message}},
        )
    )
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502
    assert "test-key-not-used" not in caplog.text
    assert "secret-header" not in caplog.text
    assert '"activityName":"Spacer"' not in caplog.text
    assert "[API key redacted]" in caplog.text
    assert "[profile prompt redacted]" in caplog.text
    assert "google_status=UNAUTHENTICATED" in caplog.text


def test_invalid_response_logs_category_without_response_body(
    client, valid_activity, monkeypatch, caplog
):
    profile = _profile(client, valid_activity)
    private_response = "private-user-text-not-for-logs"
    fake_client = FakeClient(response_text=private_response)
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **kwargs: fake_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings()).generate(profile)

    assert error.value.status_code == 502
    assert "category=response_validation" in caplog.text
    assert "private-user-text-not-for-logs" not in caplog.text


def test_missing_api_key_returns_503_without_creating_client(
    client, valid_activity, monkeypatch
):
    profile = _profile(client, valid_activity)

    def unexpected_client(**kwargs):
        raise AssertionError("Client should not be constructed without an API key")

    monkeypatch.setattr("app.services.gemini.genai.Client", unexpected_client)

    with pytest.raises(HTTPException) as error:
        GeminiRecommendationGenerator(_settings(api_key=None)).generate(profile)

    assert error.value.status_code == 503


def test_gemini_configuration_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "do-not-print")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("RECOMMENDATION_PROMPT_VERSION", "comparison-v3")
    monkeypatch.setenv("RECOMMENDATION_TEMPERATURE", "0.25")
    monkeypatch.setenv("RECOMMENDATION_TOP_P", "0.8")
    monkeypatch.setenv("RECOMMENDATION_MAX_OUTPUT_TOKENS", "900")
    monkeypatch.setenv("RECOMMENDATION_TIMEOUT_MS", "15000")

    settings = GeminiSettings.from_environment()

    assert settings.model == "gemini-3.5-flash-lite"
    assert settings.prompt_version == "comparison-v3"
    assert settings.temperature == 0.25
    assert settings.top_p == 0.8
    assert settings.max_output_tokens == 900
    assert settings.timeout_ms == 15000


def test_gemini_model_must_be_configured(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_MODEL is not set"):
        GeminiSettings.from_environment()


def test_generate_endpoint_uses_recommendation_profile_service(
    client, valid_activity, monkeypatch
):
    profile = _profile(client, valid_activity)

    class FakeGenerator:
        def generate(self, received_profile):
            assert received_profile.summary.total_entries == 1
            from app.schemas.recommendations import (
                GeneratedRecommendations,
                GenerationConfig,
                Recommendation,
            )

            return GeneratedRecommendations(
                model="gemini-3.5-flash-lite",
                promptVersion="v3",
                generationConfig=GenerationConfig(
                    temperature=0.4,
                    top_p=0.9,
                    max_output_tokens=1200,
                ),
                elapsedMs=42,
                recommendations=[
                    Recommendation(**recommendation)
                    for recommendation in MODEL_RESPONSE["recommendations"]
                ],
            )

    from app.main import app

    app.dependency_overrides[get_recommendation_generator] = lambda: FakeGenerator()
    try:
        response = client.post("/recommendations/generate")
    finally:
        app.dependency_overrides.pop(get_recommendation_generator, None)

    assert response.status_code == 200
    body = response.json()
    assert body["promptVersion"] == "v3"
    assert body["elapsedMs"] == 42
    assert len(body["recommendations"]) == 3
