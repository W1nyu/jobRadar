"""공고 종료를 위한 연속 미노출 횟수.

Revision ID: b24a4f6d9c1e
Revises: 8c0076e38b48
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b24a4f6d9c1e"
down_revision: str | Sequence[str] | None = "8c0076e38b48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """완전 수집에서만 증가시키는 미노출 카운터를 추가한다."""
    op.add_column(
        "job_postings",
        sa.Column(
            "consecutive_missing_runs",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """M4 종료 판정 상태를 제거한다."""
    op.drop_column("job_postings", "consecutive_missing_runs")
