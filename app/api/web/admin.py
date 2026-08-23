"""M8 Jinja2 기반 단일 관리자 화면의 공통 라우팅과 인증."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote, urlencode, urlsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.sources import ExecutionServiceDependency
from app.core.db import get_db
from app.models import CrawlTrigger, FetchStrategy, KeywordKind, MatchMode
from app.schemas.keyword import KeywordCreate, KeywordUpdate
from app.services.admin import (
    AdminEntityNotFoundError,
    DashboardService,
    JobAdminService,
    JobSearchFilters,
    SourceAdminService,
    SourceConflictError,
    SourceInput,
    SourceValidationError,
)
from app.services.admin_auth import AdminAuthService
from app.services.crawl_runner import SourceNotFoundError
from app.services.kakao import (
    EncryptedTokenCipher,
    KakaoOAuthClient,
    KakaoOAuthError,
    KakaoTokenService,
)
from app.services.keywords import KeywordConflictError, KeywordNotFoundError, KeywordService
from app.services.notification_history import NotificationHistoryService

templates = Jinja2Templates(directory=str(Path(__file__).parents[2] / "templates"))
auth_router = APIRouter()
admin_router = APIRouter(prefix="/admin")
SessionDependency = Annotated[Session, Depends(get_db)]
_SOURCE_FETCH_STRATEGY_FORM = Form()
_KEYWORD_KIND_FORM = Form()
_KEYWORD_MATCH_MODE_FORM = Form()
_DEFAULT_KEYWORD_KIND_FORM = Form(KeywordKind.INCLUDE)
_DEFAULT_MATCH_MODE_FORM = Form(MatchMode.SUBSTRING)
_DEFAULT_TARGET_FIELDS_FORM = Form(["title", "description"])
_DEFAULT_WEIGHT_FORM = Form(1)
_KST = ZoneInfo("Asia/Seoul")


def format_kst(value: datetime | None) -> str:
    """DB의 UTC 시각을 관리 화면용 한국 표준시 문자열로 변환한다."""
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_KST).strftime("%Y-%m-%d %H:%M KST")


templates.env.filters["kst"] = format_kst


class AdminLoginRequired(Exception):
    """보호된 관리 화면에 비로그인 사용자가 접근한 경우."""

    def __init__(self, request: Request) -> None:
        self.request = request


def require_admin(request: Request) -> None:
    """세션에 인증 표식이 없으면 안전한 로그인 경로로 보낸다."""
    if request.session.get("admin_authenticated") is not True:
        raise AdminLoginRequired(request)


def login_required_response(request: Request) -> RedirectResponse:
    """원래 경로를 보존한 로그인 리다이렉트를 만든다."""
    target = request.url.path
    if request.url.query:
        target = f"{target}?{unquote(request.url.query)}"
    return RedirectResponse(
        url=f"/login?{urlencode({'next': target})}", status_code=status.HTTP_303_SEE_OTHER
    )


@auth_router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str | None = None) -> Response:
    """관리자 로그인 화면을 표시한다."""
    if request.session.get("admin_authenticated") is True:
        return RedirectResponse(url=_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "next": _safe_next(next),
            "auth_configured": request.app.state.settings.admin_auth_enabled,
        },
    )


@auth_router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    next: str = Form("/admin"),
) -> Response:
    """자격 증명이 맞으면 서명 세션에 인증 표식을 저장한다."""
    settings = request.app.state.settings
    if not settings.admin_auth_enabled:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": _safe_next(next), "auth_configured": False},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not AdminAuthService(settings).verify(username=username, password=password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": _safe_next(next),
                "auth_configured": True,
                "error": "로그인 정보를 확인하세요.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session.clear()
    request.session["admin_authenticated"] = True
    return RedirectResponse(url=_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)


@auth_router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    """현재 세션을 비우고 로그인 화면으로 돌아간다."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.get("", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDependency) -> HTMLResponse:
    """소스별 최근 실행 이력과 워커 상태를 대시보드에 표시한다."""
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "dashboard": DashboardService(session).get(),
            "vapid_enabled": request.app.state.settings.vapid_enabled,
        },
    )


@admin_router.get("/jobs", response_class=HTMLResponse)
def job_list(
    request: Request,
    session: SessionDependency,
    query: str | None = None,
    source_id: int | None = None,
    matched: bool = False,
    open_state: str = "open",
    first_seen_from: str | None = None,
    first_seen_to: str | None = None,
    deadline_soon: bool = False,
    page: int = 1,
) -> HTMLResponse:
    """공고 검색·필터·페이지네이션 화면을 렌더링한다."""
    require_admin(request)
    filters = JobSearchFilters(
        query=query,
        source_id=source_id,
        matched_only=matched,
        is_open={"open": True, "closed": False, "all": None}.get(open_state, True),
        first_seen_from=_optional_date(first_seen_from),
        first_seen_to=_optional_date(first_seen_to),
        deadline_soon=deadline_soon,
        page=page,
    )
    service = JobAdminService(session)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "job_page": service.list(filters),
            "filters": filters,
            "sources": SourceAdminService(session).list(),
        },
    )


@admin_router.get("/jobs/{posting_id}", response_class=HTMLResponse)
def job_detail(request: Request, posting_id: int, session: SessionDependency) -> HTMLResponse:
    """선택한 공고와 키워드 매칭 근거를 표시한다."""
    require_admin(request)
    try:
        posting = JobAdminService(session).get(posting_id)
    except AdminEntityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="공고가 없습니다."
        ) from error
    return templates.TemplateResponse(request, "job_detail.html", {"posting": posting})


@admin_router.get("/sources", response_class=HTMLResponse)
def source_list(request: Request, session: SessionDependency) -> HTMLResponse:
    """등록 소스를 수집 정책과 함께 표시한다."""
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"sources": SourceAdminService(session).list()},
    )


@admin_router.get("/sources/new", response_class=HTMLResponse)
def source_new_form(request: Request, session: SessionDependency) -> HTMLResponse:
    """새 수집 소스 등록 폼을 보여 준다."""
    require_admin(request)
    return _source_form_response(request, SourceAdminService(session), source=None)


@admin_router.post("/sources")
def source_create(
    request: Request,
    session: SessionDependency,
    slug: str = Form(),
    name: str = Form(),
    crawler_key: str = Form(),
    base_url: str = Form(),
    fetch_strategy: FetchStrategy = _SOURCE_FETCH_STRATEGY_FORM,
    interval_minutes: int = Form(),
    rate_limit_per_min: int = Form(),
    config_json: str = Form("{}"),
    is_active: str | None = Form(None),
) -> Response:
    """유효한 공개 소스 설정을 저장하고 다음 스케줄 주기에 반영한다."""
    require_admin(request)
    service = SourceAdminService(session)
    data = _source_input(
        slug=slug,
        name=name,
        crawler_key=crawler_key,
        base_url=base_url,
        fetch_strategy=fetch_strategy,
        interval_minutes=interval_minutes,
        rate_limit_per_min=rate_limit_per_min,
        config_json=config_json,
        is_active=is_active is not None,
    )
    try:
        service.create(data)
    except (SourceValidationError, SourceConflictError) as error:
        return _source_form_response(
            request, service, source=None, values=data, error=str(error), status_code=422
        )
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.get("/sources/{source_id}/edit", response_class=HTMLResponse)
def source_edit_form(request: Request, source_id: int, session: SessionDependency) -> HTMLResponse:
    """기존 소스의 공개 수집 설정 편집 폼을 보여 준다."""
    require_admin(request)
    service = SourceAdminService(session)
    try:
        source = service.get(source_id)
    except AdminEntityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="소스가 없습니다."
        ) from error
    return _source_form_response(request, service, source=source)


@admin_router.post("/sources/{source_id}")
def source_update(
    request: Request,
    source_id: int,
    session: SessionDependency,
    slug: str = Form(),
    name: str = Form(),
    crawler_key: str = Form(),
    base_url: str = Form(),
    fetch_strategy: FetchStrategy = _SOURCE_FETCH_STRATEGY_FORM,
    interval_minutes: int = Form(),
    rate_limit_per_min: int = Form(),
    config_json: str = Form("{}"),
    is_active: str | None = Form(None),
) -> Response:
    """소스 공개 설정을 검증한 뒤 변경한다."""
    require_admin(request)
    service = SourceAdminService(session)
    data = _source_input(
        slug=slug,
        name=name,
        crawler_key=crawler_key,
        base_url=base_url,
        fetch_strategy=fetch_strategy,
        interval_minutes=interval_minutes,
        rate_limit_per_min=rate_limit_per_min,
        config_json=config_json,
        is_active=is_active is not None,
    )
    try:
        service.update(source_id, data)
    except AdminEntityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="소스가 없습니다."
        ) from error
    except (SourceValidationError, SourceConflictError) as error:
        return _source_form_response(
            request, service, source=None, values=data, error=str(error), status_code=422
        )
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/sources/{source_id}/delete")
def source_delete(request: Request, source_id: int, session: SessionDependency) -> RedirectResponse:
    """사용자가 확인한 소스를 삭제한다."""
    require_admin(request)
    try:
        SourceAdminService(session).delete(source_id)
    except AdminEntityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="소스가 없습니다."
        ) from error
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/sources/{source_id}/crawl", response_class=HTMLResponse)
def source_manual_crawl(
    request: Request, source_id: int, execution: ExecutionServiceDependency
) -> HTMLResponse:
    """HTMX 요청으로 단일 소스 수집을 실행하고 즉시 결과를 돌려준다."""
    require_admin(request)
    try:
        result = execution.run_source(source_id, CrawlTrigger.MANUAL)
    except SourceNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="소스가 없습니다."
        ) from error
    return templates.TemplateResponse(request, "_crawl_result.html", {"result": result})


@admin_router.get("/keywords", response_class=HTMLResponse)
def keyword_list(request: Request, session: SessionDependency) -> HTMLResponse:
    """키워드 생성·수정·삭제를 한 화면에서 제공한다."""
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "keywords.html",
        {
            "keywords": KeywordService(session).list(),
            "keyword_kinds": tuple(KeywordKind),
            "match_modes": tuple(MatchMode),
        },
    )


@admin_router.post("/keywords")
def keyword_create(
    request: Request,
    session: SessionDependency,
    term: str = Form(),
    kind: KeywordKind = _DEFAULT_KEYWORD_KIND_FORM,
    match_mode: MatchMode = _DEFAULT_MATCH_MODE_FORM,
    target_fields: list[str] = _DEFAULT_TARGET_FIELDS_FORM,
    weight: int = _DEFAULT_WEIGHT_FORM,
    is_active: str | None = Form(None),
) -> Response:
    """새 키워드를 저장한다."""
    require_admin(request)
    service = KeywordService(session)
    try:
        service.create(
            KeywordCreate(
                term=term,
                kind=kind,
                match_mode=match_mode,
                target_fields=target_fields,
                weight=weight,
                is_active=is_active is not None,
            )
        )
    except (ValidationError, ValueError, KeywordConflictError) as error:
        return _keyword_list_response(request, service, error=str(error), status_code=422)
    return RedirectResponse(url="/admin/keywords", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/keywords/{keyword_id}")
def keyword_update(
    request: Request,
    keyword_id: int,
    session: SessionDependency,
    term: str = Form(),
    kind: KeywordKind = _KEYWORD_KIND_FORM,
    match_mode: MatchMode = _KEYWORD_MATCH_MODE_FORM,
    target_fields: list[str] = _DEFAULT_TARGET_FIELDS_FORM,
    weight: int = Form(),
    is_active: str | None = Form(None),
) -> Response:
    """한 키워드의 현재 값 전체를 수정한다."""
    require_admin(request)
    service = KeywordService(session)
    try:
        service.update(
            keyword_id,
            KeywordUpdate(
                term=term,
                kind=kind,
                match_mode=match_mode,
                target_fields=target_fields,
                weight=weight,
                is_active=is_active is not None,
            ),
        )
    except KeywordNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="키워드가 없습니다."
        ) from error
    except (ValidationError, ValueError, KeywordConflictError) as error:
        return _keyword_list_response(request, service, error=str(error), status_code=422)
    return RedirectResponse(url="/admin/keywords", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/keywords/{keyword_id}/delete")
def keyword_delete(
    request: Request, keyword_id: int, session: SessionDependency
) -> RedirectResponse:
    """선택한 키워드를 삭제한다."""
    require_admin(request)
    try:
        KeywordService(session).delete(keyword_id)
    except KeywordNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="키워드가 없습니다."
        ) from error
    return RedirectResponse(url="/admin/keywords", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.get("/notifications", response_class=HTMLResponse)
def notification_history(request: Request, session: SessionDependency) -> HTMLResponse:
    """채널별 발송·실패·큐잉 이력과 카카오 재인증 상태를 보여 준다."""
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {
            "history": NotificationHistoryService(session).get(),
            "kakao_enabled": request.app.state.settings.kakao_enabled,
            "oauth_status": request.query_params.get("oauth"),
            "oauth_reason": request.query_params.get("reason"),
        },
    )


@admin_router.get("/kakao/connect")
def kakao_connect(request: Request) -> RedirectResponse:
    """로그인 세션에 묶은 state와 함께 카카오 talk_message 동의로 이동한다."""
    require_admin(request)
    settings = request.app.state.settings
    if not settings.kakao_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="카카오 OAuth 설정이 완료되지 않았습니다.",
        )
    state = secrets.token_urlsafe(32)
    request.session["kakao_oauth_state"] = state
    client = KakaoOAuthClient(
        rest_api_key=settings.kakao_rest_api_key or "",
        redirect_uri=settings.kakao_redirect_uri or "",
        client_secret=settings.kakao_client_secret,
    )
    try:
        url = client.authorization_url(state=state)
    finally:
        client.close()
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@auth_router.get("/oauth/kakao/callback")
def kakao_callback(
    request: Request,
    session: SessionDependency,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """카카오 인가 코드를 암호화 토큰으로 교환하고 관리 화면으로 돌아간다."""
    require_admin(request)
    expected_state = request.session.pop("kakao_oauth_state", None)
    if error:
        return RedirectResponse(
            url="/admin/notifications?oauth=failed&reason=consent",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if not code or not expected_state or not secrets.compare_digest(expected_state, state or ""):
        return RedirectResponse(
            url="/admin/notifications?oauth=failed&reason=state",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    settings = request.app.state.settings
    if not settings.kakao_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="카카오 OAuth 설정이 완료되지 않았습니다.",
        )
    client = KakaoOAuthClient(
        rest_api_key=settings.kakao_rest_api_key or "",
        redirect_uri=settings.kakao_redirect_uri or "",
        client_secret=settings.kakao_client_secret,
    )
    try:
        token_set = client.exchange_code(code)
        KakaoTokenService(
            session,
            cipher=EncryptedTokenCipher(settings.fernet_key or ""),
            client=client,
        ).save(token_set)
    except KakaoOAuthError as error:
        return RedirectResponse(
            url=f"/admin/notifications?oauth=failed&reason={error.reason}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception:
        return RedirectResponse(
            url="/admin/notifications?oauth=failed&reason=token_exchange",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    finally:
        client.close()
    return RedirectResponse(
        url="/admin/notifications?oauth=connected", status_code=status.HTTP_303_SEE_OTHER
    )


def _safe_next(value: str | None) -> str:
    """외부 URL 리다이렉트를 막고 관리자 내부 경로만 보존한다."""
    if not value:
        return "/admin"
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not value.startswith("/") or value.startswith("//"):
        return "/admin"
    return value


def _source_input(**values: object) -> SourceInput:
    """폼 값에서 서비스가 받는 불변 입력 객체를 만든다."""
    return SourceInput(**values)  # type: ignore[arg-type]


def _source_form_response(
    request: Request,
    service: SourceAdminService,
    *,
    source: object | None,
    values: SourceInput | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """신규·수정 폼과 검증 오류를 같은 템플릿으로 렌더링한다."""
    config_json = (
        values.config_json
        if values is not None
        else json.dumps(getattr(source, "config", {}), ensure_ascii=False, indent=2)
    )
    return templates.TemplateResponse(
        request,
        "source_form.html",
        {
            "source": source,
            "values": values,
            "config_json": config_json,
            "crawler_choices": service.crawler_choices(),
            "fetch_strategies": tuple(FetchStrategy),
            "error": error,
        },
        status_code=status_code,
    )


def _keyword_list_response(
    request: Request, service: KeywordService, *, error: str, status_code: int
) -> HTMLResponse:
    """키워드 입력 오류에도 사용자가 현재 목록을 확인하게 한다."""
    return templates.TemplateResponse(
        request,
        "keywords.html",
        {
            "keywords": service.list(),
            "keyword_kinds": tuple(KeywordKind),
            "match_modes": tuple(MatchMode),
            "error": error,
        },
        status_code=status_code,
    )


def _optional_date(value: str | None):
    """빈 쿼리 값은 필터 미지정으로, 잘못된 값은 422로 처리한다."""
    if not value:
        return None
    try:
        from datetime import date

        return date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="날짜 형식 오류"
        ) from error


@admin_router.get("/{path:path}", response_class=HTMLResponse)
def unknown_admin_path(request: Request, path: str) -> HTMLResponse:
    """아직 없는 관리 경로도 로그인 세션을 먼저 요구한다."""
    require_admin(request)
    return HTMLResponse(
        status_code=status.HTTP_404_NOT_FOUND, content="관리 화면을 찾을 수 없습니다."
    )
