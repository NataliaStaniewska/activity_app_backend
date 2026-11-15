from fastapi import FastAPI

app = FastAPI(
    title="Activity App API",
    description="Backend API for the activity tracking application.",
    version="0.1.0",
)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Activity App API is running."}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
