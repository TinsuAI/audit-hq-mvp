"""findings.value_vnd — giá trị tiền của chênh lệch, để xếp hạng phát hiện

Sổ yêu cầu dòng 3.1 và 4.1: cán bộ đọc theo thứ tự tiền, không theo thứ tự mã. Cột
nằm ở `findings` chứ không chỉ trong `details` vì bảng phát hiện phân trang bằng SQL —
xếp theo khoá JSON thì trang 1 chỉ xếp trong phạm vi trang.

NULL = chưa quy ra tiền được (mã không có tờ khai để lấy đơn giá, hoặc check chưa quy).
Khác 0: 0 là "đã quy, ra không đáng kể". Xếp hạng đẩy NULL xuống cuối.

`op.add_column` thẳng, KHÔNG `batch_alter_table` — cùng lý do các migration trước.

Revision ID: b7c8d9e0f1a2
Revises: a9b0c1d2e3f4
Create Date: 2026-08-06 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7c8d9e0f1a2'
down_revision: str | Sequence[str] | None = 'a9b0c1d2e3f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('findings', sa.Column('value_vnd', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('findings', 'value_vnd')
