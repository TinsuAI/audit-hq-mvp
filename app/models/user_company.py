"""Bảng nối user ↔ company — phân quyền theo DN (nhiều-nhiều).

1 officer phụ trách N DN, 1 DN có thể nhiều officer cùng phụ trách. Admin KHÔNG
cần dòng nào ở đây — admin thấy tất cả DN (xem app/scoping.py).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Table

from app.database import Base

user_companies = Table(
    "user_companies",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("company_id", ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
)
