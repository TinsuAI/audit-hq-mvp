"""Nhận định JSON bốn mục + cờ cần đối chiếu (ADR #21 mục 3-4)

Nhận định chuyển từ một khối văn xuôi sang bốn mục cố định (`nhan_dinh`,
`phan_bo`, `diem_nong`, `de_xuat`). `content` giữ nguyên phản hồi thô để xuống
cấp khi JSON hỏng. `needs_review` bật khi có con số trong nhận định không khớp
chuỗi nào của bảng số liệu — gắn cờ, KHÔNG publish âm thầm.

Dòng cũ: `sections_json` NULL → template render `content` như trước.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c5d6e7f8a9b0'
down_revision: str | Sequence[str] | None = 'b4c5d6e7f8a9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sections_json', sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.text('0'))
        )
        batch_op.add_column(sa.Column('unsupported_numbers', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.drop_column('unsupported_numbers')
        batch_op.drop_column('needs_review')
        batch_op.drop_column('sections_json')
