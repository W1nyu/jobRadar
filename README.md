# jobRadar

관심 채용 사이트를 주기적으로 확인해, **내 키워드와 일치하는 새 공고만** 골라 알려주는 개인용 채용공고 모니터링 서비스.

```text
채용 사이트 → 주기 수집 → 신규 탐지 → 키워드 매칭 → DB 저장 → 알림
```

- 상세 설계: [세부기획서.md](./세부기획서.md)
- 초기 기획: [기획.md](./기획.md)

## 현재 상태

| 마일스톤 | 상태 |
|---|---|
| M0 사전 준비 | 진행 중 — [docs/M0-checklist.md](./docs/M0-checklist.md) |
| M1 프로젝트 기본 환경 | 진행 중 |
| M2 ~ M12 | 대기 |

## 기술 스택

Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 · Alembic · httpx · APScheduler · Nginx · systemd

## 개발 환경 설정

Python 버전과 의존성은 [uv](https://docs.astral.sh/uv/)가 관리한다. `.python-version`에 3.12가 고정되어 있어 별도 설치 없이 uv가 맞춰준다.

```bash
uv sync                 # 가상환경 생성 + 의존성 설치
cp .env.example .env    # 값을 채운다
uv run uvicorn app.main:create_app --factory --reload
```

`uv`가 PATH에 없으면 `py -3 -m uv`로 호출한다.

### 확인

```bash
curl http://127.0.0.1:8000/healthz
```

### 테스트 · 린트

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 라이선스

개인 프로젝트. 수집한 채용 데이터는 재배포하지 않는다.
