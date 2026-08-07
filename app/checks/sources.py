"""Nguồn dữ liệu có mặt cho một (DN, kỳ) — điều kiện dispatch check (ADR #23 T4).

Chạy check khi nguồn nó đọc chưa được nạp thì mọi join rỗng → 0 phát hiện, mà 0
phát hiện đọc như "sạch". Kiểm presence TRƯỚC khi dispatch để phân biệt được
"chưa chạy — thiếu nguồn" với "chạy rồi, không có phát hiện".

Vế BCCT đếm theo `declaration_scope` (cửa sổ ngày), không theo nhãn nạp — cùng tập
dòng mà check thực sự đọc.
"""

from __future__ import annotations

from sqlalchemy import select

from app.checks.not_evaluable import (
    REMEDY_NEED_FILE_THIS_PERIOD,
    TARGET_DOCUMENT,
    RemedyClassification,
    RemedyTarget,
)
from app.checks.scope import declaration_scope
from app.models import DeclarationLine, Norm, NvlBalance, SpBalance

# Nguồn Tầng 1. `bcct` = tờ khai chi tiết; ba nguồn còn lại là các mẫu của BCQT.
SOURCES = ("bcct", "m15", "m15a", "m16")

SOURCE_LABEL_VI = {
    "bcct": "Báo cáo chi tiết tờ khai (BCCT)",
    "m15": "Mẫu 15 — Cân đối NVL",
    "m15a": "Mẫu 15a — Cân đối thành phẩm",
    "m16": "Mẫu 16 — Định mức",
}

_SETTLEMENT_MODELS = {"m15": NvlBalance, "m15a": SpBalance, "m16": Norm}


def available_sources(session, company_id: int, year: int) -> set[str]:
    """Tập nguồn CÓ ÍT NHẤT một dòng cho (DN, kỳ).

    Hỏi "có dòng nào không" bằng `SELECT id … LIMIT 1`, KHÔNG bằng `COUNT(*)`:
    `LIMIT` không cắt được aggregate, nên `COUNT(*) … LIMIT 1` vẫn quét trọn bảng —
    với BCCT là hàng trăm nghìn dòng mỗi lần chạy kiểm tra.
    """
    present: set[str] = set()

    if session.scalar(
        select(DeclarationLine.id)
        .where(declaration_scope(session, company_id, year))
        .limit(1)
    ):
        present.add("bcct")

    for name, model in _SETTLEMENT_MODELS.items():
        if session.scalar(
            select(model.id)
            .where(model.company_id == company_id, model.period_year == year)
            .limit(1)
        ):
            present.add(name)
    return present


def missing_sources_reason(missing: tuple[str, ...]) -> str:
    """Lý do ghi vào `check_runs.status_reason` — câu tiếng Việt cho cán bộ.

    Đi chung đường với `NotEvaluable` các check tự trả (#58): một trạng thái
    `not_evaluable`, một cột lý do. Không có cột `skip_reason` riêng.
    """
    names = [SOURCE_LABEL_VI.get(src, src) for src in missing]
    return "Kỳ này chưa có " + " · ".join(names)


def classify_missing_sources(missing: tuple[str, ...]) -> RemedyClassification:
    """(lớp cách gỡ, đích) của cổng thiếu nguồn — luôn lớp 1 (ADR #24 mục 2).

    Nguồn Tầng 1 khuyết là nguồn của CHÍNH kỳ đang xét, nên file của kỳ này gỡ được.
    Đích là loại tài liệu đầu tiên theo thứ tự đã sắp của `missing` — đủ để dựng nút
    "tải lên loại này", và tính lại được lúc hiển thị nên không cần lưu.
    """
    target = RemedyTarget(TARGET_DOCUMENT, missing[0]) if missing else None
    return REMEDY_NEED_FILE_THIS_PERIOD, target


__all__ = [
    "SOURCES",
    "SOURCE_LABEL_VI",
    "available_sources",
    "classify_missing_sources",
    "missing_sources_reason",
]
