"""WS3 overview — check_overviews (AI tổng quan mỗi test + staleness snapshot)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-24 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: str | Sequence[str] | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'check_overviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('check_code', sa.String(length=32), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'generated_at', sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.Column('based_on_run_at', sa.DateTime(), nullable=True),
        sa.Column('based_on_data_version', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=True),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id', 'period_year', 'check_code', name='uq_check_overview',
        ),
    )
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_check_overviews_company_id'), ['company_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_check_overviews_period_year'), ['period_year'], unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_check_overviews_period_year'))
        batch_op.drop_index(batch_op.f('ix_check_overviews_company_id'))

    op.drop_table('check_overviews')
