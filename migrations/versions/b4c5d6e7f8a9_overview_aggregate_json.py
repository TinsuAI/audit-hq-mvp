"""Bảng số liệu tính được, đóng băng trên dòng tổng quan (ADR #21 mục 1-2, 8)

Nửa TÍNH ĐƯỢC của tổng quan lưu ở `check_overviews.aggregate_json`: template
render thẳng, hiện ngay khi cán bộ bấm, không phải chờ LLM. Đóng băng theo mốc
sinh chứ không tính lại lúc mở trang — parse `details` cho mọi nhóm trên màn
hình chính quá đắt, và bảng với nhận định phải mô tả cùng một mốc.

Dòng cũ để NULL: template bỏ qua bảng số liệu, nội dung cũ vẫn hiện.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b4c5d6e7f8a9'
down_revision: str | Sequence[str] | None = 'a3b4c5d6e7f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aggregate_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.drop_column('aggregate_json')
