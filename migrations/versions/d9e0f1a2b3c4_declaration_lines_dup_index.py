"""declaration_lines: index (company_id, declaration_no, line_no) cho đếm trùng khoá

Trang tài liệu đếm `cross_label_duplicates` bằng một EXISTS tương quan chạy MỖI dòng
của kỳ. Với kỳ 270.505 dòng của 006, các index đơn cột sẵn có (`declaration_no`,
`period_year`) không đủ: trang mất hơn 125 giây và Cloudflare cắt ở 100 giây (đo trên
prod 06/08/2026 với `pilot-006/documents` → 524; `dn-006/documents` ít dòng trả 200
trong 0,48 giây). Index phủ đúng ba cột của khoá so trùng.

`IF NOT EXISTS` vì DB dev có thể đã được tạo tay index này lúc đo.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-06 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'd9e0f1a2b3c4'
down_revision: str | Sequence[str] | None = 'c8d9e0f1a2b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_declaration_lines_company_decl_line "
        "ON declaration_lines (company_id, declaration_no, line_no)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_declaration_lines_company_decl_line")
