"""norm.note — ghi chú Mẫu 16 (xuất xứ "x" = trong nước)

Revision ID: c7f3a1b2d4e5
Revises: a4d5ffcb0da7
Create Date: 2026-05-29 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c7f3a1b2d4e5'
down_revision: str | Sequence[str] | None = 'a4d5ffcb0da7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('norms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('note', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('norms', schema=None) as batch_op:
        batch_op.drop_column('note')
