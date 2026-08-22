"""PostgreSQL 영속 모델.

모든 모델은 SQLAlchemy 2.0의 typed ORM 문법으로 정의한다. 크롤러와 알림 채널은 이
모듈을 직접 알지 않고, 각각 서비스 계층을 통해서만 데이터를 다룬다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """모든 테이블이 공유하는 SQLAlchemy 메타데이터."""


class FetchStrategy(StrEnum):
    API = "api"
    RSS = "rss"
    JSON = "json"
    HTML = "html"
    BROWSER = "browser"


class KeywordKind(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class MatchMode(StrEnum):
    SUBSTRING = "substring"
    WORD = "word"
    REGEX = "regex"


class CrawlTrigger(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class CrawlStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationChannel(StrEnum):
    KAKAO = "kakao"
    WEB_PUSH = "web_push"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


def _enum_type(enum_class: type[Enum], name: str) -> SAEnum:
    """PostgreSQL enum에 파이썬 enum의 소문자 value를 저장한다."""
    return SAEnum(
        enum_class,
        name=name,
        values_callable=lambda enum: [member.value for member in enum],
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    crawler_key: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    fetch_strategy: Mapped[FetchStrategy] = mapped_column(
        _enum_type(FetchStrategy, "fetch_strategy"), nullable=False
    )
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_postings: Mapped[list[JobPosting]] = relationship(back_populates="source")
    crawl_runs: Mapped[list[CrawlRun]] = relationship(back_populates="source")


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_job_postings_source_external_id"),
        UniqueConstraint("source_id", "fingerprint", name="uq_job_postings_source_fingerprint"),
        Index("ix_job_postings_source_first_seen_at", "source_id", text("first_seen_at DESC")),
        Index(
            "ix_job_postings_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_job_postings_deadline_at_open",
            "deadline_at",
            postgresql_where=text("is_open"),
        ),
        Index(
            "ix_job_postings_first_seen_at_open",
            text("first_seen_at DESC"),
            postgresql_where=text("is_open"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    consecutive_missing_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship(back_populates="job_postings")
    revisions: Mapped[list[JobPostingRevision]] = relationship(back_populates="job_posting")
    keyword_matches: Mapped[list[JobKeywordMatch]] = relationship(back_populates="job_posting")
    notifications: Mapped[list[Notification]] = relationship(back_populates="job_posting")


class JobPostingRevision(Base):
    __tablename__ = "job_posting_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    changed_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    old_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    new_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job_posting: Mapped[JobPosting] = relationship(back_populates="revisions")


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    kind: Mapped[KeywordKind] = mapped_column(
        _enum_type(KeywordKind, "keyword_kind"), nullable=False, default=KeywordKind.INCLUDE
    )
    match_mode: Mapped[MatchMode] = mapped_column(
        _enum_type(MatchMode, "match_mode"), nullable=False, default=MatchMode.SUBSTRING
    )
    target_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        default=lambda: ["title", "description"],
        server_default=text("ARRAY['title', 'description']::varchar[]"),
    )
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    job_matches: Mapped[list[JobKeywordMatch]] = relationship(back_populates="keyword")


class JobKeywordMatch(Base):
    __tablename__ = "job_keyword_matches"
    __table_args__ = (
        UniqueConstraint(
            "job_posting_id", "keyword_id", name="uq_job_keyword_matches_posting_keyword"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False
    )
    matched_field: Mapped[str] = mapped_column(String(50), nullable=False)
    matched_snippet: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    job_posting: Mapped[JobPosting] = relationship(back_populates="keyword_matches")
    keyword: Mapped[Keyword] = relationship(back_populates="job_matches")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[CrawlTrigger] = mapped_column(
        _enum_type(CrawlTrigger, "crawl_trigger"), nullable=False
    )
    status: Mapped[CrawlStatus] = mapped_column(
        _enum_type(CrawlStatus, "crawl_status"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    items_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    http_status_summary: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    source: Mapped[Source] = relationship(back_populates="crawl_runs")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("job_posting_id", "channel", name="uq_notifications_posting_channel"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        _enum_type(NotificationChannel, "notification_channel"), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        _enum_type(NotificationStatus, "notification_status"),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_posting: Mapped[JobPosting] = relationship(back_populates="notifications")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
