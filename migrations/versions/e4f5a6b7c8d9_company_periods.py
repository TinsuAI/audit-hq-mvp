"""company_periods — cửa sổ kỳ báo cáo (from,to) theo (company, period_year)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-24 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e4f5a6b7c8d9'
down_revision: str | Sequence[str] | None = 'd3e4f5a6b7c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'company_periods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_from', sa.Date(), nullable=True),
        sa.Column('period_to', sa.Date(), nullable=True),
        sa.Column('is_manual', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'period_year', name='uq_company_period'),
    )
    op.create_index(op.f('ix_company_periods_company_id'), 'company_periods', ['company_id'])
    op.create_index(op.f('ix_company_periods_period_year'), 'company_periods', ['period_year'])


def downgrade() -> None:
    op.drop_index(op.f('ix_company_periods_period_year'), table_name='company_periods')
    op.drop_index(op.f('ix_company_periods_company_id'), table_name='company_periods')
    op.drop_table('company_periods')
