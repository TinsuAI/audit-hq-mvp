"""data_files.slot_basis — căn cứ của việc gán loại cho file (#88)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-07 15:00:00.000000

Ba giá trị: 'name' (chỉ khớp tên, chưa mở file) · 'content' (đã mở file, khớp bố
cục) · 'officer' (cán bộ chọn). NULL cho dòng cũ và cho file đồng bộ từ đĩa ngoài
luồng tải lên — bộ ba kiểm ở tầng ứng dụng (`app.pipeline.file_intake`), không ràng
buộc ở DB.

`op.add_column` THẲNG, không `batch_alter_table`: batch mode dựng lại bảng bằng
DROP + CREATE và repo này đã dính lỗi đó một lần.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a4b5c6d7e8'
down_revision: str | Sequence[str] | None = 'e2f3a4b5c6d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'data_files',
        sa.Column('slot_basis', sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('data_files', 'slot_basis')
