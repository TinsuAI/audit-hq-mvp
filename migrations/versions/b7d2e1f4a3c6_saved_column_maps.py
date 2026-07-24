"""saved column maps (officer-confirmed per DN + form signature)

Revision ID: b7d2e1f4a3c6
Revises: f5a6b7c8d9e0
Create Date: 2026-07-24 15:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b7d2e1f4a3c6'
down_revision: str | Sequence[str] | None = 'f5a6b7c8d9e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'saved_column_maps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('slot', sa.String(length=8), nullable=False),
        sa.Column('form_signature', sa.String(length=64), nullable=False),
        sa.Column('column_map', sa.Text(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('confirmed_by', sa.Integer(), nullable=True),
        sa.Column(
            'confirmed_at', sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id', 'slot', 'form_signature', name='uq_saved_column_maps_key',
        ),
    )
    with op.batch_alter_table('saved_column_maps', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_saved_column_maps_company_id'), ['company_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_saved_column_maps_form_signature'), ['form_signature'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('saved_column_maps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_saved_column_maps_form_signature'))
        batch_op.drop_index(batch_op.f('ix_saved_column_maps_company_id'))

    op.drop_table('saved_column_maps')
