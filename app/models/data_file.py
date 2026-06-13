from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DataFileStatus(StrEnum):
    """Trạng thái parse của 1 file đã tải lên (bền vững, hiển thị ở trang tài liệu)."""

    PENDING = "pending"   # đã tải lên, chưa nạp dữ liệu
    OK = "ok"             # nạp thành công
    WARNING = "warning"   # nạp được nhưng có cảnh báo (lệch cột nhẹ…)
    ERROR = "error"       # đọc/nạp lỗi — chưa dùng được


# slot → (subdir filesystem, nhãn tiếng Việt). Dùng chung cho registry + UI.
SLOT_SUBDIR: dict[str, str] = {
    "m15": "BCQT",
    "m15a": "BCQT",
    "m16": "DINH_MUC",
    "bcct": "HANG_CHI_TIET",
}

SLOT_LABEL_VI: dict[str, str] = {
    "m15": "Mẫu 15 — Cân đối NVL",
    "m15a": "Mẫu 15a — Cân đối thành phẩm",
    "m16": "Mẫu 16 — Định mức",
    "bcct": "BCCT — Báo cáo hàng chi tiết",
}

# Thứ tự cột hiển thị ở ma trận năm × loại.
SLOT_ORDER: tuple[str, ...] = ("m15", "m15a", "m16", "bcct")


class DataFile(Base):
    """Registry mỗi file BCQT đã tải lên (theo DN × năm × loại).

    Theo dõi trạng thái parse + số dòng bền vững — trang tài liệu đọc thẳng từ
    đây thay vì chỉ suy từ dòng đã ingest. Cho phép nhiều dòng/(company,year,slot)
    vì BCCT có thể tách tờ khai NK / XK thành nhiều file.
    """

    __tablename__ = "data_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[str] = mapped_column(String(8), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Đường dẫn TƯƠNG ĐỐI tới settings.raw_data_path (không lưu path tuyệt đối máy).
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
    )
    parse_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataFileStatus.PENDING,
    )
    parse_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_data_files_company_year", "company_id", "period_year"),
    )

    def __repr__(self) -> str:
        return f"<DataFile {self.company_id}/{self.period_year}/{self.slot} {self.original_filename}>"
