"""companies.first_bcqt_year — năm đầu DN nộp BCQT, cán bộ nhập tay

Mốc để phân biệt "mã chưa từng khai định mức" với "đã khai trước cửa sổ dữ liệu đã nạp".
NULL = chưa biết; T6 (#62) đọc giá trị NULL này để mặc định kỳ sớm nhất là `not_evaluable`.

`op.add_column` thẳng, KHÔNG `batch_alter_table`: batch mode dựng lại bảng bằng DROP +
CREATE, mà `companies` là đích của khoá ngoại từ 14 bảng khác → DROP TABLE fail trên DB
đã có dữ liệu (DB rỗng của test/CI thì đi qua sạch). SQLite ≥ 3.35 ADD COLUMN native.

Revision ID: f1c4a2b7d3e5
Revises: c5d6e7f8a9b0
Create Date: 2026-08-05 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1c4a2b7d3e5'
down_revision: str | Sequence[str] | None = 'c5d6e7f8a9b0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('first_bcqt_year', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'first_bcqt_year')
