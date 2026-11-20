from fastapi import FastAPI

from app.api.routes.activities import router as activities_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.recommendations import router as recommendations_router

app = FastAPI(
    title="Activity App API",
    description="Backend API for the activity tracking application.",
    version="0.2.0",
)

app.include_router(activities_router)
app.include_router(analytics_router)
app.include_router(recommendations_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Activity App API is running."}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
