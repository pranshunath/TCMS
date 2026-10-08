"""Main entry point for trigger-service and TCMS application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import get_settings, Settings


def verify_startup_safety(settings: Settings) -> None:
    """Enforces safety rule: never allow development authentication against port 3306."""
    if settings.TRIGGER_DEV_AUTH and settings.REPORTING_PORT == 3306:
        raise RuntimeError(
            "CRITICAL SAFETY VIOLATION: Dev auth (TRIGGER_DEV_AUTH=true) cannot connect to port 3306. "
            "Local development must use MySQL on port 3307."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    verify_startup_safety(settings)
    yield


from app.routes.tcms import router as tcms_router
from app.routes.tcms_ui import ui_router
from app.routes.trigger import router as trigger_router

app = FastAPI(
    title="trigger-service",
    description="Test Execution Trigger Service and Test Case Management System (TCMS)",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(tcms_router)
app.include_router(ui_router)
app.include_router(trigger_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "trigger-service"}
