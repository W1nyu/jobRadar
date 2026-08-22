"""키워드 관리 REST API. UI는 M8에서 이 API를 사용한다."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.keyword import KeywordCreate, KeywordResponse, KeywordUpdate
from app.services.keywords import KeywordConflictError, KeywordNotFoundError, KeywordService

router = APIRouter(prefix="/api/v1/keywords", tags=["keywords"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[KeywordResponse], summary="키워드 목록")
def list_keywords(session: SessionDependency) -> list[KeywordResponse]:
    """등록된 include/exclude 키워드를 모두 반환한다."""
    return list(KeywordService(session).list())


@router.get("/{keyword_id}", response_model=KeywordResponse, summary="키워드 조회")
def get_keyword(keyword_id: int, session: SessionDependency) -> KeywordResponse:
    """키워드 한 건을 반환한다."""
    return _get_or_404(KeywordService(session), keyword_id)


@router.post(
    "", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED, summary="키워드 생성"
)
def create_keyword(data: KeywordCreate, session: SessionDependency) -> KeywordResponse:
    """새 include 또는 exclude 키워드를 만든다."""
    try:
        return KeywordService(session).create(data)
    except KeywordConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 키워드입니다."
        ) from error


@router.patch("/{keyword_id}", response_model=KeywordResponse, summary="키워드 수정")
def update_keyword(
    keyword_id: int, data: KeywordUpdate, session: SessionDependency
) -> KeywordResponse:
    """키워드 문구·모드·대상 필드·가중치·활성 상태를 부분 수정한다."""
    service = KeywordService(session)
    try:
        return service.update(keyword_id, data)
    except KeywordNotFoundError as error:
        raise _not_found(keyword_id) from error
    except KeywordConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 키워드입니다."
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT, summary="키워드 삭제")
def delete_keyword(keyword_id: int, session: SessionDependency) -> Response:
    """키워드와 연결된 매칭 근거를 삭제한다."""
    try:
        KeywordService(session).delete(keyword_id)
    except KeywordNotFoundError as error:
        raise _not_found(keyword_id) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_or_404(service: KeywordService, keyword_id: int) -> KeywordResponse:
    """도메인 조회 오류를 HTTP 404로 변환한다."""
    try:
        return service.get(keyword_id)
    except KeywordNotFoundError as error:
        raise _not_found(keyword_id) from error


def _not_found(keyword_id: int) -> HTTPException:
    """키워드가 없다는 일관된 API 오류를 만든다."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"키워드가 없습니다: {keyword_id}"
    )
