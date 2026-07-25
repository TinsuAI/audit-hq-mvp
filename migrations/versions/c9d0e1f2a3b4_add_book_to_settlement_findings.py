"""Add nullable `book` (sổ quyết toán / loại hình) to settlement + findings

Một pháp nhân có thể giữ nhiều sổ quyết toán khác loại hình (xem ADR #19).
`book` = NULL nghĩa là pháp nhân một sổ → hành vi cũ, không đổi.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-25 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: str | Sequence[str] | None = 'b8c9d0e1f2a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ('nvl_balances', 'sp_balances', 'norms', 'findings')


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('book', sa.String(length=32), nullable=True))


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('book')
