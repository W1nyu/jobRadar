"""M9 새 매칭 공고의 배치·중복 방지·방해금지 DB 계약."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import (
    FetchStrategy,
    JobKeywordMatch,
    JobPosting,
    Keyword,
    KeywordKind,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Source,
)
from app.notifications.contracts import NotificationPayload, SendResult
from app.services.dispatcher import DispatchSettings, NotificationDispatcher
from tests.integration.test_database import TEST_DATABASE_URL


class RecordingChannel:
    """DB를 모르는 채널 대역으로 전송된 배치만 기록한다."""

    name = NotificationChannel.WEB_PUSH

    def __init__(self) -> None:
        self.payloads: list[NotificationPayload] = []

    def send(self, payload: NotificationPayload) -> SendResult:
        self.payloads.append(payload)
        return SendResult(succeeded=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text("SELECT to_regclass('public.notifications')")
            ).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")
    if migrated is None:
        pytest.skip("M2 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _matched_postings(session: Session, *, count: int, now: datetime) -> list[JobPosting]:
    keyword = Keyword(term=f"알림테스트-{uuid4().hex}", kind=KeywordKind.INCLUDE, weight=5)
    session.add(keyword)
    session.flush()
    postings: list[JobPosting] = []
    for index in range(count):
        source = Source(
            slug=f"notify-{uuid4().hex}",
            name=f"알림 소스 {index + 1}",
            crawler_key="linkareer",
            base_url="https://example.com",
            fetch_strategy=FetchStrategy.HTML,
        )
        session.add(source)
        session.flush()
        posting = JobPosting(
            source_id=source.id,
            external_id=uuid4().hex,
            fingerprint=uuid4().hex,
            content_hash=f"{index:x}" * 64,
            url=f"https://example.com/jobs/{index}",
            title=f"데이터 분석가 {index + 1}",
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(posting)
        session.flush()
        session.add(
            JobKeywordMatch(
                job_posting_id=posting.id,
                keyword_id=keyword.id,
                matched_field="title",
                matched_snippet="데이터 분석가",
                score=5,
            )
        )
        postings.append(posting)
    session.flush()
    return postings


@pytest.mark.integration
def test_다섯_소스의_신규_매칭은_채널별_한번의_배치로_전송되고_중복되지_않는다(
    db_session: Session,
) -> None:
    now = datetime(2099, 8, 22, 3, 0, tzinfo=UTC)
    postings = _matched_postings(db_session, count=5, now=now)
    channel = RecordingChannel()
    dispatcher = NotificationDispatcher(
        db_session,
        channels=(channel,),
        settings=DispatchSettings(lookback_minutes=10),
    )

    first = dispatcher.dispatch(now=now)
    second = dispatcher.dispatch(now=now)

    notifications = list(
        db_session.scalars(
            select(Notification).where(
                Notification.job_posting_id.in_([item.id for item in postings])
            )
        )
    )
    assert first.sent == 5
    assert second.sent == 0
    assert len(channel.payloads) == 1
    assert len(channel.payloads[0].items) == 5
    assert len(channel.payloads[0].items[:3]) == 3
    assert len(notifications) == 5
    assert {item.status for item in notifications} == {NotificationStatus.SENT}


@pytest.mark.integration
def test_방해금지_시간에는_큐잉하고_종료시각_이후에_전송한다(db_session: Session) -> None:
    quiet_now = datetime(2099, 8, 22, 14, 30, tzinfo=UTC)  # KST 23:30
    posting = _matched_postings(db_session, count=1, now=quiet_now)[0]
    channel = RecordingChannel()
    dispatcher = NotificationDispatcher(
        db_session,
        channels=(channel,),
        settings=DispatchSettings(lookback_minutes=60),
    )

    queued = dispatcher.dispatch(now=quiet_now)
    notification = db_session.scalar(
        select(Notification).where(Notification.job_posting_id == posting.id)
    )

    assert queued.queued == 1
    assert notification is not None
    assert notification.status is NotificationStatus.PENDING
    assert notification.scheduled_at == datetime(2099, 8, 22, 23, 0, tzinfo=UTC)
    assert channel.payloads == []

    sent = dispatcher.dispatch(now=datetime(2099, 8, 22, 23, 1, tzinfo=UTC))  # KST 08:01

    assert sent.sent == 1
    assert len(channel.payloads) == 1
