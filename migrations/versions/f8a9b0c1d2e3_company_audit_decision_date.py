"""companies.audit_decision_date — phạm vi KTSTQ 5 năm là VIEW (ADR #23 T4)

Mốc DUY NHẤT được lưu. Cửa sổ [D − 5 năm, D] tính lúc render, không lưu; không có
state phạm vi nào trên finding. NULL cho mọi DN hiện có → không màn nào đổi.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-07-31 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f8a9b0c1d2e3'
down_revision: str | Sequence[str] | None = 'e7f8a9b0c1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TABLE ADD COLUMN thẳng (không batch): 'companies' là đích của FOREIGN KEY
    # từ bảng khác nên batch mode (DROP + CREATE) bị từ chối trên DB đã có dữ liệu.
    op.add_column('companies', sa.Column('audit_decision_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'audit_decision_date')
