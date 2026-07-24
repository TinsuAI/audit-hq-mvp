"""WS3 foundation — check_runs + company_periods.data_version

Revision ID: a7b8c9d0e1f2
Revises: b7d2e1f4a3c6
Create Date: 2026-07-24 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: str | Sequence[str] | None = 'b7d2e1f4a3c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'check_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('check_code', sa.String(length=32), nullable=False),
        sa.Column('ran_at', sa.DateTime(), nullable=False),
        sa.Column('finding_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('data_version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id', 'period_year', 'check_code', name='uq_check_run',
        ),
    )
    with op.batch_alter_table('check_runs', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_check_runs_company_id'), ['company_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_check_runs_period_year'), ['period_year'], unique=False,
        )

    with op.batch_alter_table('company_periods', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'data_version', sa.Integer(), nullable=False, server_default='0',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('company_periods', schema=None) as batch_op:
        batch_op.drop_column('data_version')

    with op.batch_alter_table('check_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_check_runs_period_year'))
        batch_op.drop_index(batch_op.f('ix_check_runs_company_id'))

    op.drop_table('check_runs')
