"""수집 계층이 서비스 계층에 전달하는 의미 있는 실패 유형."""


class CrawlParserError(ValueError):
    """마크업 또는 본문을 공고 목록으로 해석하지 못한 경우."""


class CrawlSchemaError(ValueError):
    """응답 구조나 필수 필드가 소스 계약과 다른 경우."""


class CrawlAuthenticationError(ValueError):
    """수집에 필요한 API 키·인증 정보가 없거나 거절된 경우."""
