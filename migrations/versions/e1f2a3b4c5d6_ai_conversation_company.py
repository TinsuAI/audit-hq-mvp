"""Gắn doanh nghiệp cho cuộc trò chuyện AI (ADR #20)

Cột `ai_conversations.company_id` nullable + index `(user, company_id, started_at)`.
Nhãn LƯU trên dòng thay vì suy từ `page_url_seed` lúc đọc — suy lúc đọc hỏng khi
trang seed không phải `/companies/...` và khi finding id không sống qua re-run.

Backfill 3 nhánh theo `page_url_seed`:
1. `/companies/{ident}` khớp `companies.slug` hoặc `companies.code` → gán DN đó.
2. `/findings/{id}` mà finding CÒN tồn tại → gán `findings.company_id`.
3. Còn lại → NULL.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: str | Sequence[str] | None = 'd0e1f2a3b4c5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_ai_conversations_company_id', 'companies', ['company_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_ai_conversations_user_company_started',
            ['user', 'company_id', 'started_at'],
        )

    conn = op.get_bind()

    # Nhánh 1 — seed dạng /companies/{slug|code}. Khớp slug trước (URL người dùng
    # dùng slug), rồi code (link nội bộ/AI cũ). Chỉ gán khi khớp ĐÚNG một DN.
    conn.execute(sa.text("""
        UPDATE ai_conversations
        SET company_id = (
            SELECT c.id FROM companies c
            WHERE c.slug = substr(
                replace(ai_conversations.page_url_seed, '/companies/', ''), 1,
                CASE
                    WHEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '/') > 0
                    THEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '/') - 1
                    WHEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '?') > 0
                    THEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '?') - 1
                    ELSE length(replace(ai_conversations.page_url_seed, '/companies/', ''))
                END
            )
            OR c.code = substr(
                replace(ai_conversations.page_url_seed, '/companies/', ''), 1,
                CASE
                    WHEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '/') > 0
                    THEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '/') - 1
                    WHEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '?') > 0
                    THEN instr(replace(ai_conversations.page_url_seed, '/companies/', ''), '?') - 1
                    ELSE length(replace(ai_conversations.page_url_seed, '/companies/', ''))
                END
            )
            LIMIT 1
        )
        WHERE company_id IS NULL
          AND page_url_seed LIKE '/companies/%'
    """))

    # Nhánh 2 — seed dạng /findings/{id}, finding còn sống.
    conn.execute(sa.text("""
        UPDATE ai_conversations
        SET company_id = (
            SELECT f.company_id FROM findings f
            WHERE f.id = CAST(
                substr(
                    replace(ai_conversations.page_url_seed, '/findings/', ''), 1,
                    CASE
                        WHEN instr(replace(ai_conversations.page_url_seed, '/findings/', ''), '/') > 0
                        THEN instr(replace(ai_conversations.page_url_seed, '/findings/', ''), '/') - 1
                        WHEN instr(replace(ai_conversations.page_url_seed, '/findings/', ''), '?') > 0
                        THEN instr(replace(ai_conversations.page_url_seed, '/findings/', ''), '?') - 1
                        ELSE length(replace(ai_conversations.page_url_seed, '/findings/', ''))
                    END
                ) AS INTEGER
            )
        )
        WHERE company_id IS NULL
          AND page_url_seed LIKE '/findings/%'
    """))

    # Nhánh 3 — không làm gì: phần còn lại giữ NULL.


def downgrade() -> None:
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_conversations_user_company_started')
        batch_op.drop_constraint('fk_ai_conversations_company_id', type_='foreignkey')
        batch_op.drop_column('company_id')
