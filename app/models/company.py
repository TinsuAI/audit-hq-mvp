from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, index=True)

    def __repr__(self) -> str:
        return f"<Company {self.code} score={self.risk_score}>"
