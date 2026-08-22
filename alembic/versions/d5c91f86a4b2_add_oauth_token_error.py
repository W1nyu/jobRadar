"""카카오 OAuth 재인증 오류 보존.

Revision ID: d5c91f86a4b2
Revises: b24a4f6d9c1e
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5c91f86a4b2"
down_revision: str | Sequence[str] | None = "b24a4f6d9c1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """갱신 실패 사유를 암호문 토큰과 같은 행에 남긴다."""
    op.add_column("oauth_tokens", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    """M9 토큰 오류 설명 컬럼을 되돌린다."""
    op.drop_column("oauth_tokens", "last_error")
