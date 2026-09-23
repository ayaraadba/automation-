import os


def test_campaign_crud(client, fake_ig):
    r = client.post("/api/campaigns", json={
        "post_id": " 123 ", "keywords": "Guide, guide, , link", "comment_reply": "Sent!",
        "dm_message": "Hi", "name": "Reel"})
    assert r.status_code == 201
    c = r.json()
    assert c["post_id"] == "123"
    assert c["keywords"] == ["Guide", "link"]
    assert c["post_thumbnail_url"] == "https://cdn.example/t.jpg"

    r = client.post(f"/api/campaigns/{c['id']}/toggle")
    assert r.json()["is_active"] is False

    r = client.put(f"/api/campaigns/{c['id']}", json={
        "post_id": "123", "keywords": "free", "comment_reply": "x", "dm_message": "y", "is_active": True})
    assert r.json()["keywords"] == ["free"]

    assert len(client.get("/api/campaigns").json()) == 1
    assert client.delete(f"/api/campaigns/{c['id']}").status_code == 204
    assert client.get(f"/api/campaigns/{c['id']}").status_code == 404


def test_campaign_validation(client, fake_ig):
    r = client.post("/api/campaigns", json={
        "post_id": "1", "keywords": " , ", "comment_reply": "a", "dm_message": "b"})
    assert r.status_code == 422


def test_config_never_returns_token(client):
    r = client.put("/api/config", json={
        "access_token": "EAAGsupersecrettoken1234", "page_id": "p1", "instagram_account_id": "ig1"})
    body = r.json()
    assert "EAAGsupersecrettoken1234" not in r.text
    assert body["access_token_set"] and body["access_token_preview"] == "EAAG…1234"

    # Blank token keeps the saved one.
    client.put("/api/config", json={"access_token": "", "page_id": "p2", "instagram_account_id": "ig1"})
    body = client.get("/api/config").json()
    assert body["access_token_set"] and body["page_id"] == "p2"


def test_dashboard_pages_render(client):
    assert client.get("/dashboard/campaigns").status_code == 200
    r = client.get("/dashboard/settings")
    assert r.status_code == 200 and "/webhook/instagram" in r.text


def test_dashboard_auth(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    assert client.get("/dashboard/campaigns").status_code == 401
    assert client.get("/api/campaigns").status_code == 401
    assert client.get("/api/campaigns", auth=("admin", "pw")).status_code == 200
    # Health + webhook stay public.
    assert client.get("/health").status_code == 200
