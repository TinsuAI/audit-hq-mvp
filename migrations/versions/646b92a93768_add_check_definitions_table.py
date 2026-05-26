"""add_check_definitions_table

Revision ID: 646b92a93768
Revises: 46b3bcaebbe4
Create Date: 2026-05-26 19:29:52.482757

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '646b92a93768'
down_revision: str | Sequence[str] | None = '46b3bcaebbe4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "check_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("group", sa.Integer(), nullable=False, server_default="99"),
        sa.Column("default_severity", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("spec", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    op.create_index("ix_check_definitions_code", "check_definitions", ["code"], unique=True)
    op.create_index("ix_check_definitions_status", "check_definitions", ["status"])
    op.create_index("ix_check_definitions_created_by", "check_definitions", ["created_by"])


def downgrade() -> None:
    op.drop_table("check_definitions")
