import hashlib
import hmac
import json

from database import SessionLocal
from models import Config, ProcessedComment


def sign(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def comment_event(comment_id="c1", text="Send me the GUIDE please", media_id="m1",
                  from_id="u1", account_id="acct"):
    return {
        "object": "instagram",
        "entry": [{
            "id": account_id, "time": 1700000000,
            "changes": [{"field": "comments", "value": {
                "id": comment_id, "text": text,
                "from": {"id": from_id, "username": "fan"},
                "media": {"id": media_id, "media_product_type": "REELS"},
            }}],
        }],
    }


def post_event(client, payload, secret="test-secret"):
    body = json.dumps(payload).encode()
    return client.post("/webhook/instagram", content=body,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(body, secret)})


def make_campaign(client, **overrides):
    data = {"post_id": "m1", "keywords": "guide, link", "comment_reply": "Check DMs!",
            "dm_message": "Here you go", "is_active": True, **overrides}
    r = client.post("/api/campaigns", json=data)
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_verify_challenge(client):
    r = client.get("/webhook/instagram", params={
        "hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
    assert r.status_code == 200 and r.text == "12345"


def test_verify_challenge_wrong_token(client):
    r = client.get("/webhook/instagram", params={
        "hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "12345"})
    assert r.status_code == 403


def test_rejects_bad_signature(client, fake_ig):
    make_campaign(client)
    r = post_event(client, comment_event(), secret="wrong")
    assert r.status_code == 403
    assert not any(c[0] == "reply" for c in fake_ig.calls)


def test_rejects_missing_signature(client):
    r = client.post("/webhook/instagram", json=comment_event())
    assert r.status_code == 403


def test_matching_comment_replies_and_dms(client, fake_ig):
    make_campaign(client)
    fake_ig.calls.clear()
    r = post_event(client, comment_event())
    assert r.status_code == 200
    assert ("reply", "c1", "Check DMs!") in fake_ig.calls
    assert ("private_reply", "c1", "Here you go") in fake_ig.calls
    with SessionLocal() as db:
        rec = db.query(ProcessedComment).one()
        assert (rec.reply_status, rec.dm_status, rec.matched_keyword) == ("sent", "sent", "guide")


def test_duplicate_delivery_fires_once(client, fake_ig):
    make_campaign(client)
    fake_ig.calls.clear()
    post_event(client, comment_event())
    post_event(client, comment_event())
    assert [c[0] for c in fake_ig.calls].count("reply") == 1


def test_no_keyword_match(client, fake_ig):
    make_campaign(client)
    fake_ig.calls.clear()
    post_event(client, comment_event(text="nice video"))
    assert fake_ig.calls == []


def test_untracked_post_and_inactive_campaign(client, fake_ig):
    make_campaign(client, is_active=False)
    make_campaign(client, post_id="other")
    fake_ig.calls.clear()
    post_event(client, comment_event())
    assert fake_ig.calls == []


def test_ignores_own_comments(client, fake_ig):
    make_campaign(client)
    with SessionLocal() as db:
        db.add(Config(id=1, instagram_account_id="me"))
        db.commit()
    fake_ig.calls.clear()
    post_event(client, comment_event(from_id="me"))
    post_event(client, comment_event(comment_id="c2", from_id="acct", account_id="acct"))
    assert fake_ig.calls == []


def test_falls_back_to_direct_dm(client, fake_ig):
    make_campaign(client)
    fake_ig.calls.clear()
    fake_ig.fail.add("private_reply")
    post_event(client, comment_event())
    assert ("dm", "u1", "Here you go") in fake_ig.calls
    with SessionLocal() as db:
        assert db.query(ProcessedComment).one().dm_status == "sent"


def test_records_failures(client, fake_ig):
    make_campaign(client)
    fake_ig.fail.update({"reply", "private_reply", "dm"})
    post_event(client, comment_event())
    rows = client.get("/api/activity").json()
    assert rows[0]["reply_status"] == "failed" and rows[0]["dm_status"] == "failed"
    assert "reply failed" in rows[0]["error"]
