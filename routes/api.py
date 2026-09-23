"""REST API used by the dashboard. Credentials are never returned in full."""
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

import instagram
from auth import require_dashboard_auth
from database import get_db
from models import Campaign, Config, ProcessedComment, parse_keywords

log = logging.getLogger("api")
router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(require_dashboard_auth)])


# ----------------------------------------------------------------- schemas

class ConfigIn(BaseModel):
    # Blank access_token means "keep the saved one" so the form never needs the real value.
    access_token: str | None = None
    page_id: str | None = None
    instagram_account_id: str | None = None


class CampaignIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    post_id: str = Field(..., min_length=1, max_length=64)
    keywords: str
    comment_reply: str = Field(..., min_length=1, max_length=2200)
    dm_message: str = Field(..., min_length=1, max_length=1000)
    is_active: bool = True

    @field_validator("post_id", "comment_reply", "dm_message")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, v: str) -> str:
        kws = parse_keywords(v)
        if not kws:
            raise ValueError("at least one keyword is required")
        return ", ".join(kws)


def mask(token: str | None) -> str | None:
    if not token:
        return None
    return f"{token[:4]}…{token[-4:]}" if len(token) > 12 else "••••"


def campaign_out(c: Campaign) -> dict:
    return {
        "id": c.id, "name": c.name, "post_id": c.post_id, "keywords": c.keyword_list,
        "comment_reply": c.comment_reply, "dm_message": c.dm_message, "is_active": c.is_active,
        "post_thumbnail_url": c.post_thumbnail_url, "post_caption": c.post_caption,
        "post_permalink": c.post_permalink,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def get_or_create_config(db: Session) -> Config:
    row = db.get(Config, 1)
    if not row:
        row = Config(id=1)
        db.add(row)
    return row


def _api_error(exc: instagram.InstagramAPIError) -> HTTPException:
    status = 400 if isinstance(exc, instagram.InstagramNotConfigured) else 502
    return HTTPException(status_code=status, detail=str(exc))


# ------------------------------------------------------------------ config

@router.get("/config")
def read_config(db: Session = Depends(get_db)):
    row = db.get(Config, 1)
    creds = instagram.load_credentials(db)
    return {
        "access_token_set": bool(creds.access_token),
        "access_token_preview": mask(creds.access_token),
        "access_token_source": "dashboard" if row and row.access_token else ("env" if creds.access_token else None),
        "page_id": creds.page_id,
        "instagram_account_id": creds.instagram_account_id,
        "token_expires_at": row.token_expires_at.isoformat() if row and row.token_expires_at else None,
        "webhook_secret_configured": bool(os.getenv("FACEBOOK_APP_SECRET")),
        "verify_token_configured": bool(os.getenv("WEBHOOK_VERIFY_TOKEN")),
        "token_refresh_available": bool(os.getenv("FACEBOOK_APP_ID") and os.getenv("FACEBOOK_APP_SECRET")),
    }


@router.put("/config")
def save_config(data: ConfigIn, db: Session = Depends(get_db)):
    row = get_or_create_config(db)
    if data.access_token and data.access_token.strip():
        row.access_token = data.access_token.strip()
        row.token_expires_at = None
    if data.page_id is not None:
        row.page_id = data.page_id.strip() or None
    if data.instagram_account_id is not None:
        row.instagram_account_id = data.instagram_account_id.strip() or None
    db.commit()
    return read_config(db)


@router.post("/config/test")
async def test_connection(db: Session = Depends(get_db)):
    try:
        account = await instagram.get_client(db).get_account()
    except instagram.InstagramAPIError as exc:
        raise _api_error(exc)
    return {"ok": True, "account": account}


@router.post("/config/refresh-token")
async def refresh_token(db: Session = Depends(get_db)):
    app_id, app_secret = os.getenv("FACEBOOK_APP_ID"), os.getenv("FACEBOOK_APP_SECRET")
    if not (app_id and app_secret):
        raise HTTPException(400, "Set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET to enable token refresh.")
    try:
        token, expires_at = await instagram.get_client(db).exchange_long_lived_token(app_id, app_secret)
    except instagram.InstagramAPIError as exc:
        raise _api_error(exc)
    row = get_or_create_config(db)
    row.access_token = token
    row.token_expires_at = expires_at
    db.commit()
    return read_config(db)


# --------------------------------------------------------------- campaigns

async def _attach_post_preview(c: Campaign, db: Session) -> None:
    """Best effort: cache the post thumbnail/caption for the campaign list."""
    try:
        post = await instagram.get_client(db).get_post_details(c.post_id)
    except instagram.InstagramAPIError as exc:
        log.info("Could not fetch preview for post %s: %s", c.post_id, exc)
        return
    c.post_thumbnail_url = post.get("preview_url")
    c.post_caption = post.get("caption")
    c.post_permalink = post.get("permalink")


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    return [campaign_out(c) for c in db.scalars(select(Campaign).order_by(Campaign.id.desc()))]


@router.post("/campaigns", status_code=201)
async def create_campaign(data: CampaignIn, db: Session = Depends(get_db)):
    c = Campaign(**data.model_dump())
    await _attach_post_preview(c, db)
    db.add(c)
    db.commit()
    return campaign_out(c)


def _get_campaign(db: Session, campaign_id: int) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    return campaign_out(_get_campaign(db, campaign_id))


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, data: CampaignIn, db: Session = Depends(get_db)):
    c = _get_campaign(db, campaign_id)
    post_changed = c.post_id != data.post_id
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    if post_changed or not c.post_thumbnail_url:
        await _attach_post_preview(c, db)
    db.commit()
    return campaign_out(c)


@router.post("/campaigns/{campaign_id}/toggle")
def toggle_campaign(campaign_id: int, db: Session = Depends(get_db)):
    c = _get_campaign(db, campaign_id)
    c.is_active = not c.is_active
    db.commit()
    return campaign_out(c)


@router.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: int, db: Session = Depends(get_db)):
    db.delete(_get_campaign(db, campaign_id))
    db.commit()


# ------------------------------------------------------------ posts/activity

@router.get("/posts/recent")
async def recent_posts(limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db)):
    try:
        media = await instagram.get_client(db).list_recent_media(limit)
    except instagram.InstagramAPIError as exc:
        raise _api_error(exc)
    return [{**m, "preview_url": m.get("thumbnail_url") or m.get("media_url")} for m in media]


@router.get("/posts/{post_id}")
async def post_preview(post_id: str, db: Session = Depends(get_db)):
    try:
        return await instagram.get_client(db).get_post_details(post_id.strip())
    except instagram.InstagramAPIError as exc:
        raise _api_error(exc)


@router.delete("/activity")
def delete_user_data(username: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    """Fulfil a data deletion request: remove every record for an Instagram username."""
    rows = db.scalars(select(ProcessedComment).where(
        ProcessedComment.commenter_username == username.strip().lstrip("@"))).all()
    for r in rows:
        db.delete(r)
    db.commit()
    return {"deleted": len(rows)}


@router.get("/activity")
def activity(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(ProcessedComment).order_by(ProcessedComment.id.desc()).limit(limit))
    return [
        {
            "comment_id": r.comment_id, "campaign_id": r.campaign_id, "post_id": r.post_id,
            "commenter_username": r.commenter_username, "comment_text": r.comment_text,
            "matched_keyword": r.matched_keyword, "reply_status": r.reply_status,
            "dm_status": r.dm_status, "error": r.error,
            "processed_at": r.processed_at.isoformat() if isinstance(r.processed_at, datetime) else None,
        }
        for r in rows
    ]
