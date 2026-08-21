"""서비스 계층이 사용하는 공통 CRUD 저장소.

저장소는 세션을 받아 SQL만 수행하고 commit하지 않는다. 한 유스케이스의 트랜잭션 경계를
서비스 계층에 고정해, 여러 저장소 변경을 원자적으로 처리할 수 있게 한다.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base


class CRUDRepository[ModelT: Base]:
    """단일 SQLAlchemy 모델의 기본 생성·조회·수정·삭제를 제공한다."""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get(self, primary_key: Any) -> ModelT | None:
        """기본 키로 한 건을 조회한다."""
        return self.session.get(self.model, primary_key)

    def list(self, *, limit: int | None = None) -> Sequence[ModelT]:
        """기본 키 순서로 목록을 조회한다."""
        statement = select(self.model).order_by(*self.model.__table__.primary_key.columns)
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()

    def create(self, **values: Any) -> ModelT:
        """새 모델을 세션에 추가하고 flush해 DB 제약을 즉시 확인한다."""
        instance = self.model(**values)
        self.session.add(instance)
        self.session.flush()
        return instance

    def update(self, instance: ModelT, **values: Any) -> ModelT:
        """허용된 호출자가 전달한 필드만 변경하고 flush한다."""
        for name, value in values.items():
            setattr(instance, name, value)
        self.session.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        """대상을 현재 트랜잭션에서 삭제한다."""
        self.session.delete(instance)
        self.session.flush()
