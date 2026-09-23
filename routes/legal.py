"""Public legal pages required by Meta App Review (no auth)."""
import os

from fastapi import APIRouter, Request

from routes.dashboard import templates

router = APIRouter(include_in_schema=False)


def _context(request: Request) -> dict:
    base_url = str(request.base_url).rstrip("/")
    return {
        "business_name": os.getenv("BUSINESS_NAME", "Our business"),
        "contact_email": os.getenv("CONTACT_EMAIL", ""),
        "instagram_handle": os.getenv("INSTAGRAM_HANDLE", "").lstrip("@"),
        "retention_days": int(os.getenv("DATA_RETENTION_DAYS", "90")),
        "effective_date": os.getenv("PRIVACY_EFFECTIVE_DATE", ""),
        "privacy_url": f"{base_url}/privacy",
        "deletion_url": f"{base_url}/data-deletion",
    }


@router.get("/privacy")
def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", _context(request))


@router.get("/data-deletion")
def data_deletion(request: Request):
    return templates.TemplateResponse(request, "data_deletion.html", _context(request))
