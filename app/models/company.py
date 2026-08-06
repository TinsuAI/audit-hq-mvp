from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # slug: định danh URL có nghĩa (sinh từ tên). code vẫn là khoá lưu trữ/AI nội bộ.
    slug: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    # Năm đầu tiên DN nộp BCQT — cán bộ nhập tay, KHÔNG suy được từ dữ liệu đã nạp (kỳ sớm
    # nhất trong hệ thống chỉ là biên cửa sổ nạp). NULL = chưa biết.
    first_bcqt_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # Niên độ kế toán: tháng BẮT ĐẦU kỳ, ∈ {1, 4, 7, 10} (điểm a khoản 1 Điều 12 Luật
    # Kế toán 88/2015 — niên độ khác dương lịch phải 12 tháng tròn tính từ đầu quý).
    # 1 = dương lịch. Kỳ lẻ (năm đầu/cuối, chuyển tiếp) dùng override `company_periods`.
    fiscal_start_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Ngày quyết định kiểm tra sau thông quan (thực tế hoặc dự kiến). Mốc DUY NHẤT
    # được lưu của phạm vi KTSTQ: cửa sổ [D − 5 năm, D] tính lúc render, không lưu
    # (ADR #23 T4). NULL → không màn nào đổi.
    audit_decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<Company {self.code} score={self.risk_score}>"
