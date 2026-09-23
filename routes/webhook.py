"""Instagram webhook endpoints.

GET  /webhook/instagram  -> subscription verification handshake
POST /webhook/instagram  -> comment events (signature-verified)
"""
import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import database
import instagram
from models import Campaign, ProcessedComment

log = logging.getLogger("webhook")
router = APIRouter(prefix="/webhook", tags=["webhook"])


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Validate Meta's X-Hub-Signature-256 header (HMAC-SHA256 of the raw body)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


@router.get("/instagram", response_class=PlainTextResponse)
def verify_subscription(
    mode: str | None = Query(None, alias="hub.mode"),
    token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str | None = Query(None, alias="hub.challenge"),
):
    expected = os.getenv("WEBHOOK_VERIFY_TOKEN")
    if not expected:
        log.error("WEBHOOK_VERIFY_TOKEN is not set; cannot verify webhook subscription")
        raise HTTPException(status_code=503, detail="Webhook verify token not configured")
    if mode == "subscribe" and token and hmac.compare_digest(token, expected) and challenge:
        log.info("Webhook subscription verified")
        return challenge
    log.warning("Webhook verification failed (mode=%s)", mode)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/instagram")
async def receive_event(request: Request, background: BackgroundTasks):
    app_secret = os.getenv("FACEBOOK_APP_SECRET")
    if not app_secret:
        log.error("FACEBOOK_APP_SECRET is not set; rejecting webhook (cannot verify signature)")
        raise HTTPException(status_code=503, detail="Webhook signature secret not configured")

    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), app_secret):
        log.warning("Rejected webhook with invalid X-Hub-Signature-256")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if payload.get("object") not in ("instagram", "page"):
        return {"status": "ignored"}

    queued = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "comments" and isinstance(change.get("value"), dict):
                # Respond to Meta immediately; do the Graph API work after the response.
                background.add_task(process_comment, change["value"], str(entry.get("id", "")))
                queued += 1
    return {"status": "received", "queued": queued}


async def process_comment(value: dict, entry_account_id: str = "") -> str:
    """Handle one comment event. Returns a short outcome string (handy for tests/logs)."""
    comment_id = str(value.get("id") or "")
    text = value.get("text") or ""
    sender = value.get("from") or {}
    sender_id = str(sender.get("id") or "")
    username = sender.get("username")
    media_id = str((value.get("media") or {}).get("id") or "")

    if not comment_id or not media_id:
        log.info("Comment event missing id/media; skipping: %s", value)
        return "invalid"

    db = database.SessionLocal()
    try:
        creds = instagram.load_credentials(db)
        own_ids = {i for i in (creds.instagram_account_id, entry_account_id) if i}
        if sender_id and sender_id in own_ids:
            # Our own replies fire comment webhooks too; never respond to ourselves.
            return "own_comment"

        campaigns = db.scalars(
            select(Campaign)
            .where(Campaign.post_id == media_id, Campaign.is_active.is_(True))
            .order_by(Campaign.id)
        ).all()
        campaign, keyword = None, None
        for c in campaigns:
            keyword = c.matches(text)
            if keyword:
                campaign = c
                break
        if not campaign:
            log.debug("Comment %s on %s matched no active campaign", comment_id, media_id)
            return "no_match"

        # Claim the comment. The unique constraint makes this safe against Meta's retries
        # and concurrent deliveries: only one insert can win.
        record = ProcessedComment(
            comment_id=comment_id, campaign_id=campaign.id, post_id=media_id,
            commenter_id=sender_id or None, commenter_username=username,
            comment_text=text[:2000], matched_keyword=keyword,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            log.info("Comment %s already processed; skipping duplicate", comment_id)
            return "duplicate"

        log.info("Comment %s by @%s matched '%s' (campaign %s)", comment_id, username, keyword, campaign.id)
        client = instagram.get_client(db)
        errors = []

        try:
            await client.reply_to_comment(comment_id, campaign.comment_reply)
            record.reply_status = "sent"
        except instagram.InstagramAPIError as exc:
            record.reply_status = "failed"
            errors.append(f"reply: {exc}")
            log.error("Reply to comment %s failed: %s", comment_id, exc)

        try:
            # Private Reply works without a prior conversation (within 7 days of the comment).
            await client.send_private_reply(comment_id, campaign.dm_message)
            record.dm_status = "sent"
        except instagram.InstagramAPIError as exc:
            log.warning("Private reply for %s failed (%s); trying direct DM", comment_id, exc)
            try:
                if not sender_id:
                    raise exc
                await client.send_dm(sender_id, campaign.dm_message)
                record.dm_status = "sent"
            except instagram.InstagramAPIError as exc2:
                record.dm_status = "failed"
                errors.append(f"dm: {exc2}")
                log.error("DM for comment %s failed: %s", comment_id, exc2)

        record.error = "; ".join(errors) or None
        db.commit()
        return "processed"
    finally:
        db.close()
