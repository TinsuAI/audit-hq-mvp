"""check_runs.remedy — lớp cách gỡ đi kèm trạng thái not_evaluable (ADR #24 mục 2)

Revision ID: e2f3a4b5c6d7
Revises: d9e0f1a2b3c4
Create Date: 2026-08-07 11:00:00.000000

Ba giá trị: 'need-file-this-period' · 'need-other-period-or-confirmation' ·
'nothing-to-load'. NULL cho dòng cũ và cho check chạy được — bộ ba kiểm ở tầng
ứng dụng (`app.checks.not_evaluable.REMEDY_CLASSES`), không ràng buộc ở DB.

`op.add_column` THẲNG, không `batch_alter_table`: batch mode dựng lại bảng bằng
DROP + CREATE và repo này đã dính lỗi đó một lần.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e2f3a4b5c6d7'
down_revision: str | Sequence[str] | None = 'd9e0f1a2b3c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'check_runs',
        sa.Column('remedy', sa.String(length=48), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('check_runs', 'remedy')
