"""data_files.template_id + match_source — template registry 2 tầng (ADR #23 T3)

Ghi họ biểu đã curate mà file khớp, và bằng gì parser chọn được cột. NULL cho dòng
cũ (nạp trước khi có registry) → trang tài liệu hiện "chưa rõ", không đoán ngược.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-31 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a9b0c1d2e3f4'
down_revision: str | Sequence[str] | None = 'f8a9b0c1d2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('data_files', sa.Column('template_id', sa.String(length=64), nullable=True))
    op.add_column('data_files', sa.Column('match_source', sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column('data_files', 'match_source')
    op.drop_column('data_files', 'template_id')
