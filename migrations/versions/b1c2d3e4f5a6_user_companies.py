"""user_companies — phân quyền officer ↔ DN (nhiều-nhiều)

Revision ID: b1c2d3e4f5a6
Revises: a3c4d5e6f7b8
Create Date: 2026-06-14 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b1c2d3e4f5a6'
down_revision: str | Sequence[str] | None = 'a3c4d5e6f7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_companies',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'company_id'),
    )


def downgrade() -> None:
    op.drop_table('user_companies')
