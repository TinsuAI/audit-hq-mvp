"""check_runs.status_reason — lý do đi kèm trạng thái not_evaluable / error

Revision ID: d1e2f3a4b5c6
Revises: c5d6e7f8a9b0
Create Date: 2026-08-05 10:00:00.000000

`op.add_column` THẲNG, không `batch_alter_table`: batch mode dựng lại bảng, và
`check_runs` có FK trỏ `companies` — rebuild chết trên DB đã có dữ liệu.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd1e2f3a4b5c6'
down_revision: str | Sequence[str] | None = 'c5d6e7f8a9b0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'check_runs',
        sa.Column('status_reason', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('check_runs', 'status_reason')
