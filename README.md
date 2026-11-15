# Activity App Backend

Minimalny backend aplikacji do rejestrowania aktywności, oparty na FastAPI.

## Uruchomienie na macOS

W terminalu VS Code, w katalogu backendu:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

API będzie dostępne pod adresem <http://127.0.0.1:8000>. Interaktywną dokumentację
można otworzyć pod adresem <http://127.0.0.1:8000/docs>.

## Endpointy

- `GET /` — informacja o działaniu API.
- `GET /health` — status aplikacji.
