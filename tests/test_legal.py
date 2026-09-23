from datetime import timedelta

from database import SessionLocal
from models import ProcessedComment, prune_processed_comments, utcnow


def test_legal_pages_are_public(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("BUSINESS_NAME", "Acme Fitness")
    monkeypatch.setenv("CONTACT_EMAIL", "privacy@acme.test")
    monkeypatch.setenv("INSTAGRAM_HANDLE", "@acmefit")
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "Acme Fitness" in r.text and "privacy@acme.test" in r.text and "@acmefit" in r.text
    r = client.get("/data-deletion")
    assert r.status_code == 200 and "Data deletion request" in r.text


def _add(comment_id, username, age_days):
    with SessionLocal() as db:
        db.add(ProcessedComment(comment_id=comment_id, commenter_username=username,
                                processed_at=utcnow() - timedelta(days=age_days)))
        db.commit()


def test_retention_prunes_old_records():
    _add("old", "a", 100)
    _add("new", "b", 1)
    with SessionLocal() as db:
        assert prune_processed_comments(db, 90) == 1
        assert [r.comment_id for r in db.query(ProcessedComment)] == ["new"]


def test_delete_user_data(client):
    _add("c1", "fan", 1)
    _add("c2", "fan", 2)
    _add("c3", "other", 1)
    r = client.delete("/api/activity", params={"username": "@fan"})
    assert r.json() == {"deleted": 2}
    assert [row["commenter_username"] for row in client.get("/api/activity").json()] == ["other"]
