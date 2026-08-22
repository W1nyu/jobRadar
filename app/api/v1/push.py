"""M9 로그인한 관리자 브라우저의 Web Push 구독 API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.web.admin import require_admin
from app.core.db import get_db
from app.schemas.push import PushSubscriptionCreate
from app.services.push_subscriptions import PushSubscriptionInput, PushSubscriptionService

router = APIRouter(prefix="/api/v1/push", tags=["push"])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.get("/public-key")
def public_key(request: Request) -> dict[str, str]:
    """브라우저 PushManager 구독에 필요한 공개 VAPID 키만 반환한다."""
    require_admin(request)
    key = request.app.state.settings.vapid_public_key
    if not request.app.state.settings.vapid_enabled or key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web Push가 설정되지 않았습니다.",
        )
    return {"public_key": key}


@router.post("/subscribe")
def subscribe(
    request: Request, data: PushSubscriptionCreate, session: SessionDependency
) -> Response:
    """브라우저 구독을 등록하거나 키 회전 값을 갱신한다."""
    require_admin(request)
    subscription, created = PushSubscriptionService(session).upsert(
        PushSubscriptionInput(
            endpoint=data.endpoint,
            p256dh=data.keys.p256dh,
            auth=data.keys.auth,
        )
    )
    return Response(
        status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        headers={"Location": f"/api/v1/push/subscriptions/{subscription.id}"},
    )
