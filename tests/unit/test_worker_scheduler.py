"""M6 APScheduler 등록·자동 실행·하트비트 계약을 DB 없이 검증한다."""

from __future__ import annotations

from threading import Event, Lock

from app.models import CrawlTrigger
from app.worker.main import ScheduledSource, WorkerScheduler


class RecordingRunner:
    """스케줄러가 실제로 실행한 횟수만 기록하는 가짜 수집기."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, CrawlTrigger]] = []
        self.lock = Lock()
        self.completed_three_cycles = Event()

    def run_source(self, source_id: int, trigger: CrawlTrigger) -> None:
        with self.lock:
            self.calls.append((source_id, trigger))
            if len(self.calls) >= 3:
                self.completed_three_cycles.set()


def test_워커는_등록된_소스를_자동으로_세_사이클_실행하고_하트비트를_남긴다() -> None:
    runner = RecordingRunner()
    heartbeats: list[None] = []
    worker = WorkerScheduler(
        runner=runner,
        source_loader=lambda: [ScheduledSource(id=42, interval_minutes=0.001)],
        heartbeat=lambda: heartbeats.append(None),
        max_workers=1,
    )

    worker.start()
    try:
        assert runner.completed_three_cycles.wait(timeout=2)
    finally:
        worker.shutdown()

    assert all(trigger is CrawlTrigger.SCHEDULED for _, trigger in runner.calls)
    assert len(heartbeats) >= 1


def test_비활성화되거나_사라진_소스의_스케줄_잡은_제거된다() -> None:
    sources = [ScheduledSource(id=42, interval_minutes=60)]
    worker = WorkerScheduler(
        runner=RecordingRunner(),
        source_loader=lambda: sources,
        heartbeat=lambda: None,
        max_workers=1,
    )

    worker.refresh_jobs()
    assert worker.scheduler.get_job("crawl-source-42") is not None

    sources.clear()
    worker.refresh_jobs()
    assert worker.scheduler.get_job("crawl-source-42") is None
    worker.shutdown()


def test_네개_이상의_활성_소스를_각각_스케줄_잡으로_등록한다() -> None:
    sources = [ScheduledSource(id=source_id, interval_minutes=60) for source_id in (1, 2, 3, 4, 5)]
    worker = WorkerScheduler(
        runner=RecordingRunner(),
        source_loader=lambda: sources,
        heartbeat=lambda: None,
        max_workers=3,
    )

    worker.refresh_jobs()
    try:
        registered_ids = {
            job.id.removeprefix("crawl-source-")
            for job in worker.scheduler.get_jobs()
            if job.id.startswith("crawl-source-")
        }
    finally:
        worker.shutdown()

    assert registered_ids == {"1", "2", "3", "4", "5"}


def test_알림_디스패치와_카카오_토큰_갱신_보존정책도_워커_잡으로_등록한다() -> None:
    worker = WorkerScheduler(
        runner=RecordingRunner(),
        source_loader=lambda: [],
        heartbeat=lambda: None,
        max_workers=1,
        dispatch_notifications=lambda: None,
        refresh_kakao_tokens=lambda: None,
        run_retention=lambda: None,
    )

    worker.start()
    try:
        job_ids = {job.id for job in worker.scheduler.get_jobs()}
        notification_trigger = worker.scheduler.get_job("notification-dispatch").trigger
        refresh_timezone = str(worker.scheduler.get_job("kakao-token-refresh").trigger.timezone)
    finally:
        worker.shutdown()

    assert "notification-dispatch" in job_ids
    assert "kakao-token-refresh" in job_ids
    assert "retention" in job_ids
    assert notification_trigger.fields[5].expressions[0].first == 9
    assert notification_trigger.fields[6].expressions[0].first == 0
    assert str(notification_trigger.timezone) == "Asia/Seoul"
    assert refresh_timezone == "Asia/Seoul"
