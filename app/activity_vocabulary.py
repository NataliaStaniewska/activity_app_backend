from unicodedata import normalize

CATEGORY_LABELS = {
    "physical_activity": "Ruch",
    "relaxation": "Relaks",
    "creativity": "Kreatywność",
    "socializing": "Spotkania",
    "learning": "Nauka",
    "other": "Inne",
}

EMOTION_LABELS = {
    "joy": "Radość",
    "calm": "Spokój",
    "satisfaction": "Zadowolenie",
    "excitement": "Ekscytacja",
    "sadness": "Smutek",
    "anger": "Złość",
    "anxiety": "Lęk",
    "frustration": "Frustracja",
    "indifference": "Obojętność",
    "focus": "Skupienie",
    "fatigue": "Zmęczenie",
}


def _alias_key(value: str) -> str:
    return normalize("NFC", value.strip()).casefold()


def _aliases(labels: dict[str, str]) -> dict[str, str]:
    return {
        _alias_key(alias): identifier
        for identifier, label in labels.items()
        for alias in (identifier, label)
    }


CATEGORY_ALIASES = _aliases(CATEGORY_LABELS)
EMOTION_ALIASES = _aliases(EMOTION_LABELS)


def resolve_id(value: str, aliases: dict[str, str]) -> str | None:
    return aliases.get(_alias_key(value))
