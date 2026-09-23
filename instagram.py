"""Instagram Graph API client (official API only).

All calls go through `InstagramClient._request`, which logs every response
(with the access token redacted), and retries rate-limit / transient errors
with exponential backoff.

Public helpers matching the dashboard/webhook use cases:
    reply_to_comment(comment_id, message)
    send_dm(instagram_user_id, message)
    send_private_reply(comment_id, message)
    get_post_details(post_id)
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("instagram")
# httpx logs full URLs at INFO, which would include access tokens.
logging.getLogger("httpx").setLevel(logging.WARNING)

GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0")
GRAPH_BASE_URL = os.getenv("GRAPH_BASE_URL", "https://graph.facebook.com")

# Graph API error codes that mean "slow down" or "try again".
# https://developers.facebook.com/docs/graph-api/guides/error-handling
RETRYABLE_ERROR_CODES = {1, 2, 4, 17, 32, 341, 613, 80001, 80002, 80006}


class InstagramAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, code: int | None = None,
                 payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.payload = payload


class InstagramNotConfigured(InstagramAPIError):
    pass


@dataclass
class Credentials:
    access_token: str | None
    page_id: str | None
    instagram_account_id: str | None

    @property
    def is_complete(self) -> bool:
        return bool(self.access_token and self.instagram_account_id)


def load_credentials(db=None) -> Credentials:
    """Dashboard-saved values take precedence; env vars are the fallback."""
    row = None
    if db is not None:
        from models import Config

        row = db.get(Config, 1)
    return Credentials(
        access_token=(row and row.access_token) or os.getenv("INSTAGRAM_ACCESS_TOKEN") or None,
        page_id=(row and row.page_id) or os.getenv("FACEBOOK_PAGE_ID") or None,
        instagram_account_id=(row and row.instagram_account_id)
        or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        or None,
    )


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if "token" in k.lower() or k == "client_secret" else _redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


# Page access tokens derived from a user token, cached per (token, page) for the process lifetime.
_page_token_cache: dict[tuple[str, str], str] = {}


class InstagramClient:
    def __init__(
        self,
        access_token: str | None,
        page_id: str | None = None,
        instagram_account_id: str | None = None,
        *,
        api_version: str = GRAPH_API_VERSION,
        base_url: str = GRAPH_BASE_URL,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.access_token = access_token
        self.page_id = page_id
        self.instagram_account_id = instagram_account_id
        self.base = f"{base_url.rstrip('/')}/{api_version}"
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.timeout = timeout
        self.transport = transport

    @classmethod
    def from_credentials(cls, creds: Credentials, **kwargs) -> "InstagramClient":
        return cls(creds.access_token, creds.page_id, creds.instagram_account_id, **kwargs)

    # ------------------------------------------------------------------ core

    async def _request(self, method: str, path: str, *, params: dict | None = None,
                       json: dict | None = None, token: str | None = None) -> dict:
        token = token or self.access_token
        if not token:
            raise InstagramNotConfigured("Instagram access token is not configured.")
        url = f"{self.base}/{path.lstrip('/')}"
        query = {**(params or {}), "access_token": token}

        attempt = 0
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
            while True:
                try:
                    resp = await http.request(method, url, params=query, json=json)
                except httpx.TransportError as exc:
                    if attempt >= self.max_retries:
                        log.error("%s %s network error, giving up: %s", method, path, exc)
                        raise InstagramAPIError(f"Network error: {exc}") from exc
                    delay = self._delay(attempt)
                    log.warning("%s %s network error (%s); retrying in %.1fs", method, path, exc, delay)
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue

                try:
                    body = resp.json()
                except ValueError:
                    body = {"raw": resp.text}

                log.info("Graph API %s /%s -> %s %s", method, path, resp.status_code, _redact(body))

                if resp.is_success and not (isinstance(body, dict) and "error" in body):
                    return body

                err = body.get("error", {}) if isinstance(body, dict) else {}
                code = err.get("code")
                retryable = (
                    resp.status_code == 429
                    or resp.status_code >= 500
                    or code in RETRYABLE_ERROR_CODES
                    or err.get("is_transient") is True
                )
                if retryable and attempt < self.max_retries:
                    delay = self._delay(attempt, resp.headers.get("Retry-After"))
                    log.warning("%s /%s rate-limited/transient (HTTP %s, code %s); retry %d/%d in %.1fs",
                                method, path, resp.status_code, code, attempt + 1, self.max_retries, delay)
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue

                raise InstagramAPIError(
                    err.get("message") or f"HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    code=code,
                    payload=_redact(body),
                )

    def _delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                pass
        return self.backoff_base * (2 ** attempt)

    async def _messaging_target(self) -> tuple[str, str]:
        """Return (node, token) for the Send API.

        With Facebook Login, IG messaging goes through the linked Facebook Page and needs a
        *Page* access token. We derive it from the user token once and cache it.
        """
        if not self.page_id:
            # Assume the configured token is already a Page token.
            return "me", self.access_token or ""
        key = (self.access_token or "", self.page_id)
        if key not in _page_token_cache:
            try:
                data = await self._request("GET", self.page_id, params={"fields": "access_token"})
                _page_token_cache[key] = data.get("access_token") or self.access_token or ""
            except InstagramAPIError as exc:
                log.warning("Could not derive Page access token (%s); using configured token", exc)
                return self.page_id, self.access_token or ""
        return self.page_id, _page_token_cache[key]

    # ------------------------------------------------------------- endpoints

    async def reply_to_comment(self, comment_id: str, message: str) -> dict:
        """Post a public reply under a comment."""
        return await self._request("POST", f"{comment_id}/replies", params={"message": message})

    async def send_dm(self, instagram_user_id: str, message: str) -> dict:
        """Send a DM to an Instagram-scoped user ID.

        Only succeeds inside Instagram's 24h messaging window (the user messaged you first).
        For comment-triggered DMs prefer `send_private_reply`.
        """
        node, token = await self._messaging_target()
        payload = {"recipient": {"id": instagram_user_id}, "message": {"text": message}}
        return await self._request("POST", f"{node}/messages", json=payload, token=token)

    async def send_private_reply(self, comment_id: str, message: str) -> dict:
        """Send a DM to the author of a comment ("Private Reply").

        Allowed once per comment, within 7 days of the comment, without a prior conversation.
        """
        node, token = await self._messaging_target()
        payload = {"recipient": {"comment_id": comment_id}, "message": {"text": message}}
        return await self._request("POST", f"{node}/messages", json=payload, token=token)

    async def get_post_details(self, post_id: str) -> dict:
        """Fetch caption + thumbnail for dashboard previews."""
        data = await self._request(
            "GET", post_id,
            params={"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"},
        )
        # Videos/Reels expose `thumbnail_url`; images only have `media_url`.
        data["preview_url"] = data.get("thumbnail_url") or data.get("media_url")
        return data

    async def get_account(self) -> dict:
        """Used by the dashboard's "Test connection" button."""
        if not self.instagram_account_id:
            raise InstagramNotConfigured("Instagram Business Account ID is not configured.")
        return await self._request(
            "GET", self.instagram_account_id,
            params={"fields": "id,username,name,profile_picture_url,followers_count"},
        )

    async def list_recent_media(self, limit: int = 12) -> list[dict]:
        if not self.instagram_account_id:
            raise InstagramNotConfigured("Instagram Business Account ID is not configured.")
        data = await self._request(
            "GET", f"{self.instagram_account_id}/media",
            params={"fields": "id,caption,media_type,thumbnail_url,media_url,permalink,timestamp",
                    "limit": limit},
        )
        return data.get("data", [])

    async def exchange_long_lived_token(self, app_id: str, app_secret: str) -> tuple[str, datetime | None]:
        """Exchange the current token for a fresh ~60 day long-lived token."""
        data = await self._request(
            "GET", "oauth/access_token",
            params={"grant_type": "fb_exchange_token", "client_id": app_id,
                    "client_secret": app_secret, "fb_exchange_token": self.access_token},
        )
        expires_at = None
        if data.get("expires_in"):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))
        return data["access_token"], expires_at


# ---------------------------------------------------------------------------
# Module-level helpers: build a client from the saved credentials.

def get_client(db=None, **kwargs) -> InstagramClient:
    return InstagramClient.from_credentials(load_credentials(db), **kwargs)


async def reply_to_comment(comment_id: str, message: str, *, db=None) -> dict:
    return await get_client(db).reply_to_comment(comment_id, message)


async def send_dm(instagram_user_id: str, message: str, *, db=None) -> dict:
    return await get_client(db).send_dm(instagram_user_id, message)


async def send_private_reply(comment_id: str, message: str, *, db=None) -> dict:
    return await get_client(db).send_private_reply(comment_id, message)


async def get_post_details(post_id: str, *, db=None) -> dict:
    return await get_client(db).get_post_details(post_id)
