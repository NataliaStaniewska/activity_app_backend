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

## Migracja kategorii i emocji na identyfikatory

Rewizja `20261120_03` aktualizuje wyłącznie listy `categories` i `emotions`.
Sprawdza wszystkie rekordy przed zapisem, zachowuje kolejność elementów i
weryfikuje liczbę rekordów, ich ID oraz obie listy przed zatwierdzeniem transakcji.
Nieznana wartość, pusta lista lub duplikat po normalizacji przerywa migrację.
Ponowne uruchomienie pomija wartości już zapisane jako identyfikatory.

### Kopia przed uruchomieniem

Zatrzymaj aplikację i inne procesy zapisujące do bazy. Poniższe polecenia
uruchom w `activity_app_backend` dla lokalnej bazy Docker Compose, gdy
`DATABASE_URL` w `.env` wskazuje na tę samą bazę co usługa `db`.

```bash
umask 077
BACKUP_DIR=$(mktemp -d ../postgres-backup.XXXXXXXX)
BACKUP="$BACKUP_DIR/pre-vocabulary.dump"

docker compose exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD" PGOPTIONS="-c default_transaction_read_only=on"
  exec pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom
' > "$BACKUP" &&
docker compose exec -T db pg_restore --list < "$BACKUP" > "$BACKUP_DIR/archive-list.txt" &&
docker compose exec -T db pg_restore --file=/dev/null < "$BACKUP" &&
shasum -a 256 "$BACKUP"
```

Kontynuuj po pomyślnym zakończeniu wszystkich poleceń. Kopia zawiera dane
użytkownika. Przechowuj ją poza repozytorium. Zachowaj wynik poniższej
kontroli liczności i wersji przed migracją:

```bash
docker compose exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD" PGOPTIONS="-c default_transaction_read_only=on"
  exec psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
    -c "SELECT count(*) AS activity_count FROM activities" \
    -c "SELECT version_num FROM alembic_version"
'
```

### Uruchomienie i kontrola

```bash
source .venv/bin/activate
unset DATABASE_URL
python -m alembic current
python -m alembic upgrade 20261120_03
python -m alembic current
```

Polecenia wczytają adres z `.env`. Przed uruchomieniem spodziewana rewizja
to `20261115_02`, a po udanym uruchomieniu `20261120_03`. Powtórz kontrolę
liczności z poprzedniego kroku. Liczba wpisów ma być identyczna. Migracja
sama sprawdza pełną zgodność list ze słownikiem i zachowanie wszystkich ID.
Przy błędzie sprawdź wskazany rekord przed ponowieniem.

### Odtworzenie kopii

Po zamianie aliasów na ID Alembic nie może odtworzyć ich oryginalnej pisowni.
Aby odzyskać dane sprzed migracji, odtwórz kopię w nowej bazie. Ustaw
`BACKUP` na ścieżkę do pliku kopii, jeśli pracujesz w nowej sesji terminala.
Nazwa `activity_app_pre_vocabulary` musi być wolna, a rola musi mieć prawo
tworzenia baz.

```bash
docker compose exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  exec createdb -h 127.0.0.1 -U "$POSTGRES_USER" activity_app_pre_vocabulary
' &&
docker compose exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  exec pg_restore -h 127.0.0.1 -U "$POSTGRES_USER" -d activity_app_pre_vocabulary \
    --single-transaction --exit-on-error
' < "$BACKUP"
```

Odtworzona baza jest osobnym punktem przywracania. Jeżeli od czasu wykonania
kopii dodano lub edytowano wpisy, uwzględnij je przed przełączeniem aplikacji
na odtworzoną bazę.

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

## Generowanie rekomendacji i porównanie modeli

`POST /recommendations/generate` korzysta z istniejącego profilu
`GET /recommendation-profile` i tego samego promptu `v3` dla obu dostawców.
Domyślnie używany jest model z `RECOMMENDATION_DEFAULT_MODEL`; opcjonalny query
parameter `model` pozwala wybrać jeden ze skonfigurowanych modeli:
`gemini-3.5-flash-lite` lub `openai/gpt-oss-20b` (Groq). Odpowiedź obu zawiera
dokładnie trzy nowe aktywności/hobby z polami `name`, `category` i `reason`.
Wyniki są walidowane wspólnie: muszą zawierać trzy pozycje, niepuste wartości,
unikalne nazwy i nie mogą powtarzać aktywności z profilu.

Ustaw oba klucze w lokalnym `.env` (nigdy nie commituj tego pliku):

```dotenv
GEMINI_API_KEY=your-google-ai-api-key
GEMINI_MODEL=gemini-3.5-flash-lite
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-20b
GROQ_MAX_OUTPUT_TOKENS=4096
RECOMMENDATION_DEFAULT_MODEL=gemini-3.5-flash-lite
RECOMMENDATION_PROMPT_VERSION=v3
RECOMMENDATION_TEMPERATURE=0.4
RECOMMENDATION_TOP_P=0.9
RECOMMENDATION_MAX_OUTPUT_TOKENS=1200
RECOMMENDATION_TIMEOUT_MS=30000
```

`RECOMMENDATION_MAX_OUTPUT_TOKENS` pozostaje ustawieniem Gemini. Groq używa
osobnego `GROQ_MAX_OUTPUT_TOKENS` (domyślnie `4096` dla GPT-OSS-20B); wartość
faktycznie użyta przez wybrany model jest zwracana w `generationConfig`.
Wersja promptu i parametry generowania są zapisywane z wynikami eksperymentu.
Oba modele korzystają z tego samego profilu i promptu v3. Groq GPT-OSS-20B
używa strict JSON Schema, a odpowiedzi obu modeli przechodzą tę samą walidację
po stronie API.

W Swagger UI (`/docs`) rozwiń `POST /recommendations/generate`. Pole `model` jest
opcjonalne; pozostawienie go pustego użyje modelu domyślnego. Możesz też wybrać
konkretny model przez `curl`:

```bash
curl -X POST 'http://127.0.0.1:8000/recommendations/generate?model=gemini-3.5-flash-lite'
curl -X POST 'http://127.0.0.1:8000/recommendations/generate?model=openai%2Fgpt-oss-20b'
```

Odpowiedź zawiera `model`, `promptVersion`, `generationConfig`, `elapsedMs` i
`recommendations`, np. Dla Groq log serwera rejestruje również `attempts`,
`failed_attempts` i `retries`, żeby można było porównać niezawodność generowania.

```json
{
  "model": "openai/gpt-oss-20b",
  "promptVersion": "v3",
  "generationConfig": {
    "temperature": 0.4,
    "top_p": 0.9,
    "max_output_tokens": 4096
  },
  "elapsedMs": 820,
  "recommendations": [
    {
      "name": "Fotografia przyrodnicza",
      "category": "Kreatywność",
      "reason": "W historii często pojawiają się spacery na zewnątrz; fotografia może połączyć ruch z kreatywnością."
    },
    {
      "name": "Obserwowanie ptaków",
      "category": "Relaks",
      "reason": "Profil zawiera pozytywne oceny spokojnych aktywności na świeżym powietrzu."
    },
    {
      "name": "Warsztaty ceramiczne",
      "category": "Kreatywność",
      "reason": "Rysowanie jest wykonywane wielokrotnie, a profil pokazuje zainteresowanie aktywnościami twórczymi."
    }
  ]
}
```

To jedynie przykład formatu — nie rzeczywista odpowiedź modelu. Rzeczywista
odpowiedź nie obiecuje poprawy nastroju. Brak klucza zwraca `503`, limit API
`429`, timeout `504`, a błąd lub niepoprawne dane modelu `502`.

Przy błędzie sprawdź terminal, w którym działa Uvicorn. Serwis zapisuje wpis
`Gemini request failed` lub `Groq request failed` z kategorią
(`authentication`, `model_unavailable`, `rate_limit`, `timeout`, `network`,
`provider_unavailable`, `response_validation` lub `client_error`), typem
wyjątku, kodem HTTP dostawcy (jeśli API go zwróciło), statusem i bezpiecznym
komunikatem diagnostycznym.
Odpowiedź HTTP zawiera jedynie ogólny opis. Klucz, nagłówki autoryzacji,
odpowiedź modelu i profil użytkownika nie są logowane.

Uruchamiaj serwer bez wyciszania logów, aby zobaczyć diagnostykę:

```bash
python -m uvicorn app.main:app --reload --log-level info
```

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
