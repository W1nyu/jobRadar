"""키워드 CRUD API의 입력·출력 계약."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import KeywordKind, MatchMode

KeywordTargetField = Literal["title", "description"]


class KeywordCreate(BaseModel):
    """새 관심 또는 제외 키워드를 만들 때 허용하는 필드."""

    term: str = Field(min_length=1, max_length=255)
    kind: KeywordKind = KeywordKind.INCLUDE
    match_mode: MatchMode = MatchMode.SUBSTRING
    target_fields: list[KeywordTargetField] = Field(
        default_factory=lambda: ["title", "description"]
    )
    weight: int = Field(default=1, ge=0, le=100)
    is_active: bool = True

    @field_validator("term")
    @classmethod
    def _strip_term(cls, value: str) -> str:
        term = value.strip()
        if not term:
            raise ValueError("키워드는 공백만으로 만들 수 없습니다.")
        return term

    @field_validator("target_fields")
    @classmethod
    def _validate_target_fields(cls, value: list[KeywordTargetField]) -> list[KeywordTargetField]:
        if not value:
            raise ValueError("매칭 대상 필드는 하나 이상이어야 합니다.")
        if len(value) != len(set(value)):
            raise ValueError("매칭 대상 필드는 중복될 수 없습니다.")
        return value

    @model_validator(mode="after")
    def _validate_regex(self) -> KeywordCreate:
        if self.match_mode is MatchMode.REGEX:
            try:
                re.compile(self.term)
            except re.error as error:
                raise ValueError(f"유효하지 않은 정규식입니다: {error}") from error
        return self


class KeywordUpdate(BaseModel):
    """기존 키워드에서 바꿀 필드만 받는 부분 수정 계약."""

    term: str | None = Field(default=None, min_length=1, max_length=255)
    kind: KeywordKind | None = None
    match_mode: MatchMode | None = None
    target_fields: list[KeywordTargetField] | None = None
    weight: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None

    @field_validator("term")
    @classmethod
    def _strip_term(cls, value: str | None) -> str | None:
        if value is None:
            return None
        term = value.strip()
        if not term:
            raise ValueError("키워드는 공백만으로 만들 수 없습니다.")
        return term

    @field_validator("target_fields")
    @classmethod
    def _validate_target_fields(
        cls, value: list[KeywordTargetField] | None
    ) -> list[KeywordTargetField] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("매칭 대상 필드는 하나 이상이어야 합니다.")
        if len(value) != len(set(value)):
            raise ValueError("매칭 대상 필드는 중복될 수 없습니다.")
        return value


class KeywordResponse(BaseModel):
    """키워드 API가 반환하는 영속 상태."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    kind: KeywordKind
    match_mode: MatchMode
    target_fields: list[KeywordTargetField]
    weight: int
    is_active: bool
