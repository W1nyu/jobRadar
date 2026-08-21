"""서비스 계층이 사용할 데이터 접근 객체."""

from app.repositories.base import CRUDRepository
from app.repositories.models import (
    AppSettingRepository,
    CrawlRunRepository,
    JobKeywordMatchRepository,
    JobPostingRepository,
    JobPostingRevisionRepository,
    KeywordRepository,
    NotificationRepository,
    OAuthTokenRepository,
    PushSubscriptionRepository,
    SourceRepository,
)

__all__ = [
    "AppSettingRepository",
    "CRUDRepository",
    "CrawlRunRepository",
    "JobKeywordMatchRepository",
    "JobPostingRepository",
    "JobPostingRevisionRepository",
    "KeywordRepository",
    "NotificationRepository",
    "OAuthTokenRepository",
    "PushSubscriptionRepository",
    "SourceRepository",
]
