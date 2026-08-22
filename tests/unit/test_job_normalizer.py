"""M4 공고 정규화의 DB-독립 계약을 검증한다."""

from datetime import UTC, datetime

from app.crawlers.base import RawJob
from app.services.normalizer import normalize


def test_공고_정규화는_태그와_공백을_제거해_안정적인_지문을_만든다() -> None:
    raw = RawJob(
        url="https://example.com/jobs/42?from=list",
        title=" [신입]  데이터  분석가 ",
        company="  예시  회사 ",
        description="  분석 업무\n  지원  ",
        deadline_at=datetime(2026, 9, 1, 18, 0),
    )

    job = normalize(source_id=7, raw_job=raw)

    assert job.external_id is None
    assert job.title == "데이터 분석가"
    assert job.company == "예시 회사"
    assert job.description == "분석 업무 지원"
    assert job.deadline_at == datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
    assert (
        job.fingerprint
        == normalize(
            source_id=7,
            raw_job=RawJob(
                url="https://example.com/jobs/42?different=query",
                title="데이터 분석가",
                company="예시 회사",
            ),
        ).fingerprint
    )


def test_공고_정규화는_외부_id가_있어도_내용_해시에서_조회수_같은_raw를_제외한다() -> None:
    base = RawJob(
        external_id="  MSIT-100 ",
        url="https://example.com/jobs/100",
        title="연구원 채용",
        description="연구 개발을 담당합니다.",
        raw={"views": 10, "scrap_count": 1},
    )
    dynamic_only = RawJob(
        external_id="MSIT-100",
        url="https://example.com/jobs/100",
        title="연구원 채용",
        description="연구 개발을 담당합니다.",
        raw={"views": 999, "scrap_count": 50},
    )

    normalized = normalize(source_id=7, raw_job=base)
    normalized_dynamic = normalize(source_id=7, raw_job=dynamic_only)

    assert normalized.external_id == "msit-100"
    assert normalized.fingerprint is None
    assert normalized.content_hash == normalized_dynamic.content_hash
