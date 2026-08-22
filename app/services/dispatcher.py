"""M9 신규 관심 공고의 배치·방해금지·중복 방지 디스패처."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import (
    JobPosting,
    KeywordKind,
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.notifications.contracts import (
    NotificationItem,
    NotificationPayload,
    NotificationSender,
    SendResult,
)
from app.repositories import (
    JobPostingRepository,
    NotificationRepository,
    PushSubscriptionRepository,
)


@dataclass(frozen=True, slots=True)
class DispatchSettings:
    """한 번의 알림 디스패치에 필요한 운영 정책."""

    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "08:00"
    timezone: str = "Asia/Seoul"
    lookback_minutes: int = 10
    retry_attempts: int = 3
    app_base_url: str = ""


@dataclass(frozen=True, slots=True)
class DispatchSummary:
    """워커 로그와 테스트가 확인할 디스패치 결과."""

    queued: int = 0
    sent: int = 0
    failed: int = 0


class NotificationDispatcher:
    """알림 이력의 유일성 제약을 기준으로 채널 발송을 조율한다."""

    def __init__(
        self,
        session: Session,
        *,
        channels: Sequence[NotificationSender],
        settings: DispatchSettings,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session
        self.channels = tuple(channels)
        self.settings = settings
        self.sleep = sleep
        self.postings = JobPostingRepository(session)
        self.notifications = NotificationRepository(session)
        self.subscriptions = PushSubscriptionRepository(session)

    def dispatch(self, *, now: datetime | None = None) -> DispatchSummary:
        """신규 공고를 큐잉하고 전송 가능 시점의 이력을 채널별 한 번씩 발송한다."""
        now = now or datetime.now(UTC)
        queued = sent = failed = 0
        scheduled_at = _quiet_end(now, self.settings)
        for channel in self.channels:
            queued += self._queue_new(channel.name, now=now, scheduled_at=scheduled_at)
        self.session.commit()

        if scheduled_at is not None:
            return DispatchSummary(queued=queued)

        for channel in self.channels:
            due = self.notifications.list_due(channel=channel.name, now=now)
            if not due:
                continue
            result, attempts = self._send_with_retry(channel, _payload_from_notifications(due))
            for notification in due:
                notification.attempt_count += attempts
                if result.succeeded:
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = now
                else:
                    notification.status = NotificationStatus.FAILED
                    notification.payload = {
                        **notification.payload,
                        "delivery_error": result.error_message,
                    }
            self._apply_web_push_result(result)
            self.session.commit()
            if result.succeeded:
                sent += len(due)
            else:
                failed += len(due)
        return DispatchSummary(queued=queued, sent=sent, failed=failed)

    def _queue_new(
        self,
        channel: NotificationChannel,
        *,
        now: datetime,
        scheduled_at: datetime | None,
    ) -> int:
        candidates = self.postings.list_notification_candidates(
            channel=channel,
            since=now - timedelta(minutes=self.settings.lookback_minutes),
        )
        for posting in candidates:
            self.notifications.create(
                job_posting_id=posting.id,
                channel=channel,
                status=NotificationStatus.PENDING,
                payload=_posting_payload(posting, app_base_url=self.settings.app_base_url),
                scheduled_at=scheduled_at,
            )
        return len(candidates)

    def _send_with_retry(
        self, channel: NotificationSender, payload: NotificationPayload
    ) -> tuple[SendResult, int]:
        result = SendResult(succeeded=False, error_message="전송을 시작하지 못했습니다.")
        attempts = max(self.settings.retry_attempts, 1)
        for attempt in range(1, attempts + 1):
            result = channel.send(payload)
            if result.succeeded:
                return result, attempt
            if attempt < attempts:
                self.sleep(float(2 ** (attempt - 1)))
        return result, attempts

    def _apply_web_push_result(self, result: SendResult) -> None:
        """404/410은 즉시 비활성화하고 기타 실패는 다섯 번까지 누적한다."""
        for endpoint in result.invalid_endpoints:
            if subscription := self.subscriptions.get_by_endpoint(endpoint):
                subscription.is_active = False
        for endpoint in result.failed_endpoints:
            if subscription := self.subscriptions.get_by_endpoint(endpoint):
                subscription.failure_count += 1
                if subscription.failure_count >= 5:
                    subscription.is_active = False


def _quiet_end(now: datetime, settings: DispatchSettings) -> datetime | None:
    """현재가 방해금지 구간이면 다음 종료 시각을 UTC로 반환한다."""
    timezone = ZoneInfo(settings.timezone)
    local_now = now.astimezone(timezone)
    start = _parse_time(settings.quiet_hours_start)
    end = _parse_time(settings.quiet_hours_end)
    if start == end:
        return None
    local_time = local_now.timetz().replace(tzinfo=None)
    is_quiet = start <= local_time < end if start < end else local_time >= start or local_time < end
    if not is_quiet:
        return None
    end_date = local_now.date()
    if start >= end and local_time >= start:
        end_date += timedelta(days=1)
    return datetime.combine(end_date, end, tzinfo=timezone).astimezone(UTC)


def _parse_time(value: str) -> clock_time:
    """환경 설정의 HH:MM 값을 시간 비교 가능한 객체로 바꾼다."""
    return clock_time.fromisoformat(value)


def _posting_payload(posting: JobPosting, *, app_base_url: str) -> dict[str, object]:
    """전송 재시도에도 DB 조인 없이 쓸 수 있는 최소 공고 스냅샷을 만든다."""
    matches = sorted(
        (match for match in posting.keyword_matches if match.keyword.kind is KeywordKind.INCLUDE),
        key=lambda match: (-match.score, match.keyword_id),
    )
    return {
        "title": posting.title,
        "source_name": posting.source.name,
        "url": f"{app_base_url}/admin/jobs/{posting.id}",
        "keywords": [match.keyword.term for match in matches],
        "deadline": posting.deadline_at.date().isoformat() if posting.deadline_at else None,
        "score": sum(match.score for match in matches),
    }


def _payload_from_notifications(notifications: Sequence[Notification]) -> NotificationPayload:
    """여러 notifications 행을 사용자에게 보낼 알림 한 건으로 묶는다."""
    ordered = sorted(
        notifications, key=lambda item: int(item.payload.get("score", 0)), reverse=True
    )
    items = tuple(
        NotificationItem(
            posting_id=notification.job_posting_id,
            title=str(notification.payload["title"]),
            source_name=str(notification.payload["source_name"]),
            url=str(notification.payload["url"]),
            keywords=tuple(str(value) for value in notification.payload.get("keywords", [])),
            deadline=(
                str(notification.payload["deadline"])
                if notification.payload.get("deadline") is not None
                else None
            ),
        )
        for notification in ordered
    )
    count = len(items)
    return NotificationPayload(
        title=f"새 채용공고 {count}건",
        body=(f"{items[0].title} 외 {count - 1}건" if count > 1 else items[0].title),
        url=f"{notifications[0].payload['url'].split('/admin/jobs/')[0]}/admin/jobs?matched=true",
        items=items,
    )
