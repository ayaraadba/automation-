"""FastAPI entry point: `uvicorn main:app --reload`."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("main")

from auth import auth_enabled  # noqa: E402
from database import init_db  # noqa: E402
from routes import api, dashboard, webhook  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    for var in ("FACEBOOK_APP_SECRET", "WEBHOOK_VERIFY_TOKEN"):
        if not os.getenv(var):
            log.warning("%s is not set — webhooks will be rejected until it is.", var)
    if not auth_enabled():
        log.warning("DASHBOARD_PASSWORD is not set — the dashboard is unprotected. "
                    "Set it before deploying publicly.")
    yield


app = FastAPI(title="Instagram Comment-to-DM Automation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(webhook.router)
app.include_router(api.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/campaigns")
