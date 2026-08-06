"""data_files.sheet_override — trang tính do cán bộ chỉ định cho file này

Adapter tự chấm điểm rồi chọn trang tính (`select_sheet`), nhưng trước đây không
ghi lại đã chọn trang nào và cũng không có cách sửa: file BCCT của 006 có 6 trang
(`Tổng hợp`, `Chi tiết`, `Phí vận chuyển`, `lệ phí HQ`, `làm co`, `TK tại chỗ`),
parser đọc `Chi tiết` còn màn review lại xem `Tổng hợp` (trang đầu). Cột này lưu
lựa chọn của cán bộ; NULL = để hệ thống tự chọn.

`op.add_column` thẳng, KHÔNG `batch_alter_table` — cùng lý do các migration trước.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-06 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c8d9e0f1a2b3'
down_revision: str | Sequence[str] | None = 'b7c8d9e0f1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('data_files', sa.Column('sheet_override', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('data_files', 'sheet_override')
