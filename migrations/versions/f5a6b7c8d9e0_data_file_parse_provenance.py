"""data_files — bằng chứng cách đọc file (bố cục + chi tiết) cho badge truy nguồn

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-24 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f5a6b7c8d9e0'
down_revision: str | Sequence[str] | None = 'e4f5a6b7c8d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('data_files', sa.Column('parse_layout', sa.String(length=16), nullable=True))
    op.add_column('data_files', sa.Column('parse_detail', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('data_files', 'parse_detail')
    op.drop_column('data_files', 'parse_layout')
