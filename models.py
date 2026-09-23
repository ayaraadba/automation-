"""SQLAlchemy models."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Config(Base):
    """Instagram credentials. Single row (id=1); empty fields fall back to env vars."""

    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instagram_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    post_id: Mapped[str] = mapped_column(String(64), index=True)
    keywords: Mapped[str] = mapped_column(Text)  # comma-separated
    comment_reply: Mapped[str] = mapped_column(Text)
    dm_message: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    post_thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def keyword_list(self) -> list[str]:
        return parse_keywords(self.keywords)

    def matches(self, text: str | None) -> str | None:
        """Return the first keyword found in `text` (case-insensitive, partial match)."""
        haystack = (text or "").lower()
        for kw in self.keyword_list:
            if kw.lower() in haystack:
                return kw
        return None


class ProcessedComment(Base):
    """One row per comment we've acted on. The unique comment_id is the dedup lock."""

    __tablename__ = "processed_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    post_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commenter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commenter_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_keyword: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reply_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|sent|failed
    dm_status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def parse_keywords(raw: str | None) -> list[str]:
    seen: list[str] = []
    for part in (raw or "").split(","):
        kw = part.strip()
        if kw and kw.lower() not in (s.lower() for s in seen):
            seen.append(kw)
    return seen
