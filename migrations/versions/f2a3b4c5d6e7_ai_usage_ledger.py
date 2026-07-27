"""Sổ chi phí AI append-only (ADR #21 mục 10)

Trần chi phí ngày cộng `ai_messages.cost_usd`, nên chi phí sinh tổng quan —
ghi trên `check_overviews` — không vào trần lẫn thống kê. Không mở rộng câu
truy vấn sang bảng đó được: nó upsert MỘT dòng mỗi (DN, năm, mã kiểm tra), sinh
lại ba lần trong ngày chỉ còn chi phí lần cuối.

Seed từ dữ liệu hiện có: mỗi dòng `check_overviews` theo `generated_at`, và
`ai_messages` có chi phí trong ngày chạy migration (trần ngày đúng ngay sau khi
áp; lịch sử chat cũ không cần cho mục đích chặn).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2a3b4c5d6e7'
down_revision: str | Sequence[str] | None = 'e1f2a3b4c5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('ref', sa.String(length=128), nullable=True),
        sa.Column('model', sa.String(length=128), nullable=True),
        sa.Column('tokens_in', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_out', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('user', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_usage_created_at', 'ai_usage', ['created_at'])
    op.create_index('ix_ai_usage_created_kind', 'ai_usage', ['created_at', 'kind'])

    conn = op.get_bind()

    # Seed 1 — mọi tổng quan đã sinh, theo mốc sinh của chính nó.
    conn.execute(sa.text("""
        INSERT INTO ai_usage (kind, ref, model, tokens_in, tokens_out, cost_usd, user, created_at)
        SELECT 'overview',
               'overview:' || o.company_id || ':' || o.period_year || ':' || o.check_code,
               o.model,
               COALESCE(o.tokens_in, 0),
               COALESCE(o.tokens_out, 0),
               COALESCE(o.cost_usd, 0),
               NULL,
               o.generated_at
        FROM check_overviews o
        WHERE COALESCE(o.cost_usd, 0) > 0
    """))

    # Seed 2 — tin nhắn chat có chi phí trong NGÀY chạy migration.
    conn.execute(sa.text("""
        INSERT INTO ai_usage (kind, ref, model, tokens_in, tokens_out, cost_usd, user, created_at)
        SELECT 'chat',
               'conv:' || m.conversation_id,
               m.model,
               COALESCE(m.tokens_in, 0),
               COALESCE(m.tokens_out, 0),
               COALESCE(m.cost_usd, 0),
               c.user,
               m.created_at
        FROM ai_messages m
        LEFT JOIN ai_conversations c ON c.id = m.conversation_id
        WHERE COALESCE(m.cost_usd, 0) > 0
          AND date(m.created_at) = date('now')
    """))


def downgrade() -> None:
    op.drop_index('ix_ai_usage_created_kind', table_name='ai_usage')
    op.drop_index('ix_ai_usage_created_at', table_name='ai_usage')
    op.drop_table('ai_usage')
