# Activity App Backend

Backend aplikacji Activity App oparty na FastAPI, SQLAlchemy 2.x i PostgreSQL.
Migracje schematu bazy danych są zarządzane przez Alembic.

## Wymagania

- Python 3.11 lub nowszy
- Docker Desktop (jeśli PostgreSQL nie jest już uruchomiony lokalnie)

## Konfiguracja i uruchomienie na macOS

W terminalu VS Code, w katalogu backendu:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edytuj lokalny `.env` i ustaw hasło dla lokalnej bazy. Plik `.env` jest ignorowany
przez Git. `DATABASE_URL` powinien zawierać te same dane logowania, co zmienne
`POSTGRES_USER`, `POSTGRES_PASSWORD` i `POSTGRES_DB`; przykładowo:

```dotenv
DATABASE_URL=postgresql+psycopg://activity_app:twoje-lokalne-haslo@localhost:5432/activity_app
POSTGRES_DB=activity_app
POSTGRES_USER=activity_app
POSTGRES_PASSWORD=twoje-lokalne-haslo
```

Nie zapisuj rzeczywistych danych dostępowych w repozytorium.

### Uruchom PostgreSQL

Jeśli PostgreSQL nie działa już lokalnie, uruchom go przez Docker Compose:

```bash
docker compose up -d db
```

Compose zapisuje dane w nazwanym wolumenie `postgres_data`.

### Zastosuj migracje i uruchom API

```bash
source .venv/bin/activate
alembic upgrade head
python -m uvicorn app.main:app --reload
```

API: <http://127.0.0.1:8000>, dokumentacja Swagger UI: <http://127.0.0.1:8000/docs>.
Endpointy `GET /` i `GET /health` są dostępne bez odpytywania bazy.

## API aktywności

- `POST /activities` — utworzenie aktywności (odpowiedź `201`).
- `GET /activities` — lista od najnowszej aktywności.
- `GET /activities/{id}` — szczegóły albo `404`.
- `DELETE /activities/{id}` — usunięcie (odpowiedź `204`) albo `404`.

Daty wejściowe muszą zawierać strefę czasową i nie mogą wskazywać przyszłości;
wartości są przechowywane jako daty ze strefą czasową.
`rating`, `moodAfter` oraz opcjonalne `moodBefore` przyjmują wartości 1–5.
Kategorie i emocje są wymagane i nie mogą być puste. `activityName` ma limit
100 znaków, `likes` i `dislikes` 200, a `notes` 300.

### Przykładowy POST w Swagger UI

Otwórz <http://127.0.0.1:8000/docs>, rozwiń `POST /activities`, wybierz
**Try it out**, wklej przykładowy JSON i wybierz **Execute**:

```json
{
  "activityName": "Spacer",
  "date": "2025-03-08T14:30:00+01:00",
  "categories": ["Ruch", "Relaks"],
  "locationType": "outdoor",
  "companyType": "alone",
  "moodBefore": 2,
  "moodAfter": 4,
  "rating": 5,
  "emotions": ["spokój", "radość"],
  "likes": "Świeże powietrze",
  "dislikes": null,
  "notes": "Spacer w parku"
}
```

`ActivityEntry` we Flutterze ma pola `rating` i `emotions`, których obecny
formularz dodawania jeszcze nie zbiera (używa `pleasure`). Formularz zapisuje
też `company`/`place`, podczas gdy model definiuje `companyType`/`locationType`.
API odzwierciedla model `ActivityEntry`; Flutter nie jest modyfikowany w tym
etapie. Wartości enumów to `indoor`, `outdoor`, `mixed` dla lokalizacji oraz
`alone`, `withOthers` dla towarzystwa.

## Analiza historii i profil rekomendacyjny

Analiza wykonywana jest w Pythonie na wszystkich wpisach bazy, ponieważ na tym
etapie nie ma uwierzytelniania ani przypisania aktywności do użytkowników. Nie
jest to bezpieczna obsługa wielu użytkowników. Obliczenia opisują obserwowane
zależności; nie dowodzą, że aktywność spowodowała zmianę samopoczucia.

- `GET /statistics` — liczby wpisów i unikalnych aktywności/kategorii, statystyki
  aktywności, kategorii i kontekstów, rozkład `moodAfter` oraz średnia zmiana
  nastroju `moodAfter - moodBefore`.
- `GET /recommendation-profile` — zwięzły profil danych wejściowych dla przyszłego
  modułu rekomendacji LLM, bez wywoływania LLM.

Każda średnia ma pola `mean` i `observations`. Przy braku obserwacji `mean` ma
wartość `null`, a zbiory są puste. Kategorie wielokrotnego wyboru są liczone
osobno dla każdej kategorii w danym wpisie. Rozkład `moodAfter` zawiera tylko
zaobserwowane wartości. Ranking profilu zawiera maksymalnie pięć pozycji i
pomija grupy z mniej niż dwiema obserwacjami; pozostałe średnie i liczebności są
zwracane bez wag ani łącznego wyniku preferencji.

Przykładowa odpowiedź `GET /statistics`:

```json
{
  "totalEntries": 3,
  "distinctActivities": 1,
  "distinctCategories": 2,
  "activityOccurrences": [
    {
      "activityName": "Spacer",
      "count": 3,
      "meanMoodAfter": {"mean": 4.0, "observations": 3},
      "meanRating": {"mean": 4.33, "observations": 3}
    }
  ],
  "moodAfterDistribution": [
    {"value": 3, "count": 1},
    {"value": 4, "count": 2}
  ],
  "categories": [
    {
      "name": "Relaks",
      "count": 2,
      "meanMoodAfter": {"mean": 4.5, "observations": 2},
      "meanRating": {"mean": 4.5, "observations": 2}
    },
    {
      "name": "Ruch",
      "count": 2,
      "meanMoodAfter": {"mean": 3.5, "observations": 2},
      "meanRating": {"mean": 4.0, "observations": 2}
    }
  ],
  "locationTypes": [
    {
      "name": "outdoor",
      "count": 3,
      "meanMoodAfter": {"mean": 4.0, "observations": 3},
      "meanRating": {"mean": 4.33, "observations": 3}
    }
  ],
  "companyTypes": [
    {
      "name": "alone",
      "count": 3,
      "meanMoodAfter": {"mean": 4.0, "observations": 3},
      "meanRating": {"mean": 4.33, "observations": 3}
    }
  ],
  "diversity": {"uniqueActivities": 1, "uniqueCategories": 2},
  "meanMoodChange": {"mean": 1.0, "observations": 2}
}
```

Przykładowy kształt odpowiedzi `GET /recommendation-profile` (rankingi pokazują
grupy z co najmniej dwiema obserwacjami):

```json
{
  "summary": {
    "totalEntries": 1,
    "distinctActivities": 1,
    "distinctCategories": 1,
    "meanMoodChange": {"mean": 1.0, "observations": 1}
  },
  "dataVolume": {
    "totalEntries": 1,
    "distinctActivities": 1,
    "distinctCategories": 1,
    "minimumObservationsForRankings": 2
  },
  "frequentlyPerformed": [{"activityName": "Spacer", "occurrences": 1}],
  "activityPreferences": {
    "highestMoodAfter": [],
    "lowestMoodAfter": [],
    "highestRating": [],
    "lowestRating": []
  },
  "categoryPreferences": {
    "highestMoodAfter": [],
    "lowestMoodAfter": [],
    "highestRating": [],
    "lowestRating": []
  },
  "contextPreferences": {
    "categories": {
      "highestMoodAfter": [],
      "lowestMoodAfter": [],
      "highestRating": [],
      "lowestRating": []
    },
    "locationTypes": {
      "highestMoodAfter": [],
      "lowestMoodAfter": [],
      "highestRating": [],
      "lowestRating": []
    },
    "companyTypes": {
      "highestMoodAfter": [],
      "lowestMoodAfter": [],
      "highestRating": [],
      "lowestRating": []
    }
  },
  "userStatements": [
    {
      "activityName": "Spacer",
      "likes": "Lubię świeże powietrze.",
      "dislikes": null
    }
  ],
  "existingActivities": [{"activityName": "Spacer", "occurrences": 1}],
  "limitations": [
    "Profil obejmuje wszystkie wpisy w bazie; aktywności nie są przypisane do użytkowników.",
    "Zwracane są zaobserwowane zależności, a nie wpływ przyczynowy.",
    "Oceny są samoopisowe i mogą zależeć od nieujętego kontekstu.",
    "Rankingi wymagają co najmniej 2 obserwacji; rzadsze grupy są pomijane.",
    "Profil nie przewiduje przyszłego nastroju ani wyniku rekomendacji."
  ]
}
```

Pola `likes` i `dislikes` są zwracane jako dosłowne wypowiedzi przy wpisach,
bez interpretacji. `existingActivities` pozwala przyszłemu modułowi unikać
proponowania aktywności już obecnych w historii.

### Dane demonstracyjne

Importer dodaje 40 syntetycznych wpisów w jednej transakcji. Nie uruchamia się
automatycznie, nie usuwa aktywności, a rejestr importu w osobnej tabeli zapobiega
duplikatom przy ponownym uruchomieniu:

```bash
alembic upgrade head
python -m scripts.import_demo_data
```

## Testy

Testy CRUD, analizy, walidacji i idempotencji importera działają bez PostgreSQL
(na SQLite w pamięci):

```bash
pytest
```
