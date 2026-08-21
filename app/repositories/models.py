"""각 M2 모델에 대응하는 타입 안전한 기본 저장소."""

from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    CrawlRun,
    JobKeywordMatch,
    JobPosting,
    JobPostingRevision,
    Keyword,
    Notification,
    OAuthToken,
    PushSubscription,
    Source,
)
from app.repositories.base import CRUDRepository


class SourceRepository(CRUDRepository[Source]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Source)


class JobPostingRepository(CRUDRepository[JobPosting]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobPosting)


class JobPostingRevisionRepository(CRUDRepository[JobPostingRevision]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobPostingRevision)


class KeywordRepository(CRUDRepository[Keyword]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Keyword)


class JobKeywordMatchRepository(CRUDRepository[JobKeywordMatch]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobKeywordMatch)


class CrawlRunRepository(CRUDRepository[CrawlRun]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlRun)


class NotificationRepository(CRUDRepository[Notification]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Notification)


class PushSubscriptionRepository(CRUDRepository[PushSubscription]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, PushSubscription)


class OAuthTokenRepository(CRUDRepository[OAuthToken]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OAuthToken)


class AppSettingRepository(CRUDRepository[AppSetting]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AppSetting)
