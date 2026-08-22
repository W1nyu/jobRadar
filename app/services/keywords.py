"""키워드 CRUD의 트랜잭션 경계와 도메인 검증."""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Keyword, MatchMode
from app.repositories import KeywordRepository
from app.schemas.keyword import KeywordCreate, KeywordUpdate


class KeywordNotFoundError(LookupError):
    """요청한 키워드가 존재하지 않을 때 발생한다."""


class KeywordConflictError(ValueError):
    """이미 존재하는 키워드 문구를 저장하려 할 때 발생한다."""


class KeywordService:
    """키워드 생성·조회·수정·삭제를 하나의 서비스 경계에서 처리한다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.keywords = KeywordRepository(session)

    def list(self) -> Sequence[Keyword]:
        """관리 API가 표시할 전체 키워드를 기본 키 순서로 반환한다."""
        return self.keywords.list()

    def get(self, keyword_id: int) -> Keyword:
        """식별자로 키워드를 찾고, 없으면 도메인 오류를 낸다."""
        keyword = self.keywords.get(keyword_id)
        if keyword is None:
            raise KeywordNotFoundError(keyword_id)
        return keyword

    def create(self, data: KeywordCreate) -> Keyword:
        """검증된 새 키워드를 저장하고 API 요청 단위로 commit한다."""
        try:
            keyword = self.keywords.create(**data.model_dump())
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise KeywordConflictError(data.term) from error
        return keyword

    def update(self, keyword_id: int, data: KeywordUpdate) -> Keyword:
        """부분 수정 후 최종 정규식 설정을 다시 검증해 저장한다."""
        keyword = self.get(keyword_id)
        values = data.model_dump(exclude_unset=True)
        self._validate_final_regex(
            term=values.get("term", keyword.term),
            match_mode=values.get("match_mode", keyword.match_mode),
        )
        try:
            self.keywords.update(keyword, **values)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise KeywordConflictError(values.get("term", keyword.term)) from error
        return keyword

    def delete(self, keyword_id: int) -> None:
        """키워드와 연결된 매칭 근거를 FK cascade로 함께 제거한다."""
        keyword = self.get(keyword_id)
        self.keywords.delete(keyword)
        self.session.commit()

    @staticmethod
    def _validate_final_regex(*, term: str, match_mode: MatchMode) -> None:
        """부분 수정으로 regex 모드가 되는 경우도 정규식 문법을 확인한다."""
        if match_mode is not MatchMode.REGEX:
            return
        try:
            re.compile(term)
        except re.error as error:
            raise ValueError(f"유효하지 않은 정규식입니다: {error}") from error
