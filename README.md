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

## Testy

Testy CRUD i walidacji można uruchomić bez PostgreSQL:

```bash
pytest
```
