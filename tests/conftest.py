import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set before the app modules are imported.
os.environ["DATABASE_URL"] = "sqlite:///" + str(ROOT / "tests" / "test.db")
os.environ["FACEBOOK_APP_SECRET"] = "test-secret"
os.environ["WEBHOOK_VERIFY_TOKEN"] = "verify-me"
for var in ("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ACCOUNT_ID", "FACEBOOK_PAGE_ID",
            "FACEBOOK_APP_ID", "DASHBOARD_PASSWORD"):
    os.environ[var] = ""

import database  # noqa: E402
import instagram  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


class FakeInstagram:
    """Stands in for InstagramClient; records calls and can be told to fail."""

    def __init__(self):
        self.calls = []
        self.fail = set()

    async def _call(self, name, *args):
        self.calls.append((name, *args))
        if name in self.fail:
            raise instagram.InstagramAPIError(f"{name} failed", status_code=400, code=10)
        return {"id": "ok"}

    async def reply_to_comment(self, comment_id, message):
        return await self._call("reply", comment_id, message)

    async def send_private_reply(self, comment_id, message):
        return await self._call("private_reply", comment_id, message)

    async def send_dm(self, user_id, message):
        return await self._call("dm", user_id, message)

    async def get_post_details(self, post_id):
        await self._call("post", post_id)
        return {"id": post_id, "caption": "My reel", "preview_url": "https://cdn.example/t.jpg",
                "permalink": "https://instagram.com/p/x", "media_type": "VIDEO"}


@pytest.fixture(autouse=True)
def fresh_db():
    import models  # noqa: F401

    database.Base.metadata.drop_all(database.engine)
    database.Base.metadata.create_all(database.engine)
    yield


@pytest.fixture
def fake_ig(monkeypatch):
    fake = FakeInstagram()
    monkeypatch.setattr(instagram, "get_client", lambda db=None, **kw: fake)
    return fake


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
