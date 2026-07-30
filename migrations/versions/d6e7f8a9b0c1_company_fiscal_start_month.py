"""Niên độ kế toán mức DN: companies.fiscal_start_month (ADR #23 T2)

Tháng bắt đầu niên độ ∈ {1, 4, 7, 10}; 1 = dương lịch. `server_default='1'` nên mọi
DN hiện có giữ nguyên hành vi — KHÔNG backfill theo dữ liệu.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-31 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd6e7f8a9b0c1'
down_revision: str | Sequence[str] | None = 'c5d6e7f8a9b0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TABLE ADD COLUMN thẳng (không batch): batch mode dựng lại bảng bằng
    # DROP + CREATE, mà 'companies' đang là đích của FOREIGN KEY từ bảng khác nên
    # DROP bị từ chối trên DB đã có dữ liệu. SQLite ≥ 3.35 hỗ trợ ADD/DROP COLUMN.
    op.add_column(
        'companies',
        sa.Column(
            'fiscal_start_month', sa.Integer(), nullable=False, server_default=sa.text('1')
        ),
    )


def downgrade() -> None:
    op.drop_column('companies', 'fiscal_start_month')
