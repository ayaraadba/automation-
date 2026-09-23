"""FastAPI entry point: `uvicorn main:app --reload`."""
import asyncio
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
from database import SessionLocal, init_db  # noqa: E402
from models import prune_processed_comments  # noqa: E402
from routes import api, dashboard, legal, webhook  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "90"))


async def retention_loop() -> None:
    """Delete old activity records at startup and then once a day."""
    while True:
        try:
            with SessionLocal() as db:
                deleted = prune_processed_comments(db, RETENTION_DAYS)
            if deleted:
                log.info("Retention: deleted %d activity records older than %d days", deleted, RETENTION_DAYS)
        except Exception:
            log.exception("Retention cleanup failed")
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    for var in ("FACEBOOK_APP_SECRET", "WEBHOOK_VERIFY_TOKEN"):
        if not os.getenv(var):
            log.warning("%s is not set — webhooks will be rejected until it is.", var)
    if not auth_enabled():
        log.warning("DASHBOARD_PASSWORD is not set — the dashboard is unprotected. "
                    "Set it before deploying publicly.")
    cleanup = asyncio.create_task(retention_loop())
    yield
    cleanup.cancel()


app = FastAPI(title="Instagram Comment-to-DM Automation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(webhook.router)
app.include_router(api.router)
app.include_router(dashboard.router)
app.include_router(legal.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/campaigns")
