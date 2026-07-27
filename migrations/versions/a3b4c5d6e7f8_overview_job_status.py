"""Trạng thái sinh + job + lỗi trên dòng tổng quan (ADR #21 mục 5-6)

Sinh tổng quan chuyển sang job nền, nên dòng `check_overviews` tồn tại NGAY khi
cán bộ bấm và mang trạng thái `running` + id job đang chạy, rồi thành `done`
hoặc `failed` kèm lỗi. Dòng cũ (đã sinh xong trước khi có cột) → `done`.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3b4c5d6e7f8'
down_revision: str | Sequence[str] | None = 'f2a3b4c5d6e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('status', sa.String(length=16), nullable=False, server_default='done')
        )
        batch_op.add_column(sa.Column('job_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('error', sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            'fk_check_overviews_job_id', 'jobs', ['job_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('check_overviews', schema=None) as batch_op:
        batch_op.drop_constraint('fk_check_overviews_job_id', type_='foreignkey')
        batch_op.drop_column('error')
        batch_op.drop_column('job_id')
        batch_op.drop_column('status')
