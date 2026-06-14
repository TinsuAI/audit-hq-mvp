"""company.slug — định danh URL có nghĩa, backfill từ tên

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-14 15:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.slugs import slugify_name

revision: str = 'd3e4f5a6b7c8'
down_revision: str | Sequence[str] | None = 'c2d3e4f5a6b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Direct ADD COLUMN + CREATE INDEX (SQLite hỗ trợ) — KHÔNG batch recreate để
    # tránh gãy FK (companies được user_companies/data_files/findings… tham chiếu)
    # và tránh lock khi server đang mở kết nối.
    op.add_column('companies', sa.Column('slug', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_companies_slug'), 'companies', ['slug'], unique=True)

    # Backfill: slug từ tên (fallback code khi tên rỗng), đảm bảo duy nhất.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, code, name FROM companies ORDER BY id")).fetchall()
    seen: set[str] = set()
    for cid, code, name in rows:
        base = slugify_name(name) if name else slugify_name(code)
        candidate, n = base, 1
        while candidate in seen:
            n += 1
            candidate = f"{base}-{n}"
        seen.add(candidate)
        conn.execute(
            sa.text("UPDATE companies SET slug = :slug WHERE id = :id"),
            {"slug": candidate, "id": cid},
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_companies_slug'), table_name='companies')
    op.drop_column('companies', 'slug')
