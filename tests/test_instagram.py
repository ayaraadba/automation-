import asyncio
import json

import httpx
import pytest

from instagram import InstagramAPIError, InstagramClient


def make_client(handler, **kw):
    return InstagramClient("TOKEN", page_id=kw.pop("page_id", None), instagram_account_id="ig",
                           transport=httpx.MockTransport(handler), backoff_base=0, **kw)


def test_retries_on_rate_limit_then_succeeds():
    attempts = []

    def handler(req):
        attempts.append(req)
        if len(attempts) < 3:
            return httpx.Response(400, json={"error": {"message": "Too many calls", "code": 4}})
        return httpx.Response(200, json={"id": "reply1"})

    result = asyncio.run(make_client(handler).reply_to_comment("c1", "hi"))
    assert result == {"id": "reply1"}
    assert len(attempts) == 3
    assert attempts[0].url.path.endswith("/c1/replies")
    assert attempts[0].url.params["message"] == "hi"


def test_gives_up_after_max_retries():
    def handler(req):
        return httpx.Response(429, json={"error": {"message": "slow down", "code": 613}})

    with pytest.raises(InstagramAPIError) as exc:
        asyncio.run(make_client(handler, max_retries=2).reply_to_comment("c1", "hi"))
    assert exc.value.code == 613


def test_non_retryable_error_raises_immediately():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(400, json={"error": {"message": "Invalid token", "code": 190}})

    with pytest.raises(InstagramAPIError):
        asyncio.run(make_client(handler).get_post_details("m1"))
    assert len(calls) == 1


def test_private_reply_uses_page_token():
    seen = []

    def handler(req):
        seen.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"access_token": "PAGE_TOKEN", "id": "page1"})
        return httpx.Response(200, json={"recipient_id": "u1", "message_id": "mid"})

    asyncio.run(make_client(handler, page_id="page1").send_private_reply("c9", "hello"))
    post = seen[-1]
    assert post.url.path.endswith("/page1/messages")
    assert post.url.params["access_token"] == "PAGE_TOKEN"
    assert json.loads(post.content) == {"recipient": {"comment_id": "c9"}, "message": {"text": "hello"}}


def test_post_details_preview_url():
    def handler(req):
        return httpx.Response(200, json={"id": "m1", "media_url": "https://x/v.mp4",
                                         "thumbnail_url": "https://x/t.jpg", "caption": "c"})

    data = asyncio.run(make_client(handler).get_post_details("m1"))
    assert data["preview_url"] == "https://x/t.jpg"
