"""check_definitions — cột cho check SQL/Python soạn từ NL

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6a7
Create Date: 2026-06-13 00:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a3c4d5e6f7b8'
down_revision: str | Sequence[str] | None = 'f2b3c4d5e6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_COLUMNS = (
    ('scope', sa.String(length=8)),
    ('subject_table', sa.String(length=32)),
    ('subject_col', sa.String(length=64)),
    ('sql_snippet', sa.Text()),
    ('detail_query', sa.Text()),
    ('code_snippet', sa.Text()),
    ('nl_prompt', sa.Text()),
    ('analysis', sa.Text()),
    ('plan', sa.JSON()),
    ('self_review', sa.JSON()),
)


def upgrade() -> None:
    with op.batch_alter_table('check_definitions', schema=None) as batch_op:
        for name, type_ in _NEW_COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('check_definitions', schema=None) as batch_op:
        for name, _type in reversed(_NEW_COLUMNS):
            batch_op.drop_column(name)
