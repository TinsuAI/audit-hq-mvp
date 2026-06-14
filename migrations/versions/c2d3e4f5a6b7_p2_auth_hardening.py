"""P2 — siết auth: must_change_password + nhật ký truy cập

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-14 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c2d3e4f5a6b7'
down_revision: str | Sequence[str] | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='0')
        )

    op.create_table(
        'access_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('company_code', sa.String(length=32), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_access_events_username', 'access_events', ['username'])
    op.create_index('ix_access_events_action', 'access_events', ['action'])
    op.create_index('ix_access_events_company_code', 'access_events', ['company_code'])
    op.create_index('ix_access_events_created_at', 'access_events', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_access_events_created_at', table_name='access_events')
    op.drop_index('ix_access_events_company_code', table_name='access_events')
    op.drop_index('ix_access_events_action', table_name='access_events')
    op.drop_index('ix_access_events_username', table_name='access_events')
    op.drop_table('access_events')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('must_change_password')
