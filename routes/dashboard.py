"""Server-rendered dashboard pages. Data is loaded client-side from /api."""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import auth_enabled, require_dashboard_auth

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_dashboard_auth)])


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def dashboard_home():
    return RedirectResponse("/dashboard/campaigns", status_code=307)


@router.get("/campaigns")
def campaigns_page(request: Request):
    return templates.TemplateResponse(request, "campaigns.html", {"active": "campaigns"})


@router.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(
        request, "settings.html",
        {"active": "settings", "auth_enabled": auth_enabled(),
         "webhook_url": str(request.base_url).rstrip("/") + "/webhook/instagram"},
    )
