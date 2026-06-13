"""data_files — registry file BCQT đã tải lên (DN × năm × loại)

Revision ID: f2b3c4d5e6a7
Revises: e1a2c3d4f5b6
Create Date: 2026-06-13 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'f2b3c4d5e6a7'
down_revision: str | Sequence[str] | None = 'e1a2c3d4f5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'data_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('slot', sa.String(length=8), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_path', sa.String(length=500), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'uploaded_at', sa.DateTime(), nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('parse_status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('parse_message', sa.Text(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('data_files', schema=None) as batch_op:
        batch_op.create_index('ix_data_files_company_id', ['company_id'], unique=False)
        batch_op.create_index('ix_data_files_company_year', ['company_id', 'period_year'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('data_files', schema=None) as batch_op:
        batch_op.drop_index('ix_data_files_company_year')
        batch_op.drop_index('ix_data_files_company_id')
    op.drop_table('data_files')
