from pydantic import BaseModel, ConfigDict, Field, field_validator


GEMINI_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "category", "reason"],
            },
        }
    },
    "required": ["recommendations"],
}


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("name", "category", "reason")
    @classmethod
    def values_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Recommendation fields cannot be blank")
        return value


class RecommendationList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[Recommendation] = Field(min_length=3, max_length=3)


class GenerationConfig(BaseModel):
    temperature: float
    top_p: float
    max_output_tokens: int


class GeneratedRecommendations(BaseModel):
    model: str
    prompt_version: str = Field(alias="promptVersion")
    generation_config: GenerationConfig = Field(alias="generationConfig")
    elapsed_ms: int = Field(alias="elapsedMs", ge=0)
    recommendations: list[Recommendation] = Field(min_length=3, max_length=3)
