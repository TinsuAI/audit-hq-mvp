"""Add nullable `book` to data_files (gán sổ quyết toán per-file ở review WS1)

Ingest book-aware đọc `data_files.book` mỗi file settlement (M15/M15a/M16), gom
theo sổ, ghi lại mọi sổ trong một lượt (ADR #19 Revision — UI + upload). NULL =
pháp nhân một sổ / đường CLI → hành vi cũ không đổi.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-25 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: str | Sequence[str] | None = 'c9d0e1f2a3b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('data_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('book', sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('data_files', schema=None) as batch_op:
        batch_op.drop_column('book')
