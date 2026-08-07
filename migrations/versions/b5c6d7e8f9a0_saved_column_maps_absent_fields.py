"""saved_column_maps.absent_fields — trường cán bộ xác nhận không có trong file (#112)

Trạng thái thứ ba của một trường khai, cạnh `đã gán` và `chưa gán`. Lời của cán bộ,
nên phải bền vững; và là thứ cho cảnh báo "thiếu trường bắt buộc" một đường đóng.

KHÔNG dùng `batch_alter_table`: `saved_column_maps` là ĐÍCH của khoá ngoại, mà chế độ
batch dựng bảng mới rồi đổi tên nên cạnh FK trỏ vào bảng cũ đứt (đã đo, xem
`.ai/DECISIONS.md`). `op.add_column` thẳng chạy được trên SQLite cho cột nullable.

NULL cho mọi hàng cũ = chưa ai xác nhận vắng trường nào. Đó đúng là nguyên trạng: một
map đã lưu trước lát này không mang phát biểu nào về trường vắng.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "saved_column_maps",
        sa.Column("absent_fields", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("saved_column_maps", "absent_fields")
