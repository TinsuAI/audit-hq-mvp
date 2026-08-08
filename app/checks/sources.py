"""Nguồn dữ liệu có mặt cho một (DN, kỳ) — điều kiện dispatch check (ADR #23 T4).

Chạy check khi nguồn nó đọc chưa được nạp thì mọi join rỗng → 0 phát hiện, mà 0
phát hiện đọc như "sạch". Kiểm presence TRƯỚC khi dispatch để phân biệt được
"chưa chạy — thiếu nguồn" với "chạy rồi, không có phát hiện".

Vế BCCT đếm theo `declaration_scope` (cửa sổ ngày), không theo nhãn nạp — cùng tập
dòng mà check thực sự đọc.
"""

from __future__ import annotations

from sqlalchemy import select

from app.adapters.declared_fields import label_of
from app.checks.not_evaluable import (
    REMEDY_NEED_FILE_THIS_PERIOD,
    TARGET_DOCUMENT,
    RemedyClassification,
    RemedyTarget,
)
from app.checks.scope import declaration_scope
from app.models import DataFile, DeclarationLine, Norm, NvlBalance, SpBalance
from app.models.data_file import SLOT_LABEL_VI

# Nguồn Tầng 1. `bcct` = báo cáo hàng chi tiết; ba nguồn còn lại là các mẫu của BCQT. Cùng
# tập khoá với `SLOT_ORDER`, và tên hiển thị lấy ở `SLOT_LABEL_VI` — bảng nhãn riêng
# của module này đã xoá (#98).
SOURCES = ("bcct", "m15", "m15a", "m16")

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
    names = [SLOT_LABEL_VI.get(src, src) for src in missing]
    return "Kỳ này chưa có " + " · ".join(names)


def classify_missing_sources(missing: tuple[str, ...]) -> RemedyClassification:
    """(lớp cách gỡ, đích) của cổng thiếu nguồn — luôn lớp 1 (ADR #24 mục 2).

    Nguồn Tầng 1 khuyết là nguồn của CHÍNH kỳ đang xét, nên file của kỳ này gỡ được.
    Đích là loại tài liệu đầu tiên theo thứ tự đã sắp của `missing` — đủ để dựng nút
    "tải lên loại này", và tính lại được lúc hiển thị nên không cần lưu.
    """
    target = RemedyTarget(TARGET_DOCUMENT, missing[0]) if missing else None
    return REMEDY_NEED_FILE_THIS_PERIOD, target


def absent_fields_for_period(session, company_id: int, year: int) -> dict[str, set[str]]:
    """`{slot: {trường cán bộ xác nhận VẮNG}}` cho một (DN, kỳ).

    Đọc `parse_detail.absent_fields` của các file thuộc CHÍNH kỳ đó — cùng cách
    `review_gate_for_files` gom cột cần soát. Không đọc thẳng `saved_column_maps`: map
    lưu khoá theo (DN, slot, vân tay) nên dùng chung giữa các kỳ, mà một trường vắng ở
    kỳ này không có nghĩa nó vắng ở kỳ khác.
    """
    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company_id,
            DataFile.period_year == year,
        )
    ).all()
    out: dict[str, set[str]] = {}
    for row in rows:
        absent = row.parse_detail_obj.get("absent_fields") or ()
        for field in absent:
            if isinstance(field, str):
                out.setdefault(row.slot, set()).add(field)
    return out


def blocking_absent_fields(
    code: str, absent: dict[str, set[str]]
) -> tuple[tuple[str, str], ...]:
    """Các `(slot, trường)` VẮNG mà `code` khai đọc — rỗng nghĩa là check chạy được.

    Suy bằng `CHECK_COLUMNS` qua chính `checks_reading()` mà cảnh báo trên màn gán cột
    dùng, nên hai bên không thể nói khác nhau: cùng một bảng khai, cùng một hàm tra.
    """
    # Nhập trễ: `registry` tái xuất `SOURCES` từ chính module này, nên nhập ở đầu file
    # là vòng nhập. Hàm này chỉ chạy lúc dispatch nên chi phí không đáng kể.
    from app.checks.registry import checks_reading

    hits = [
        (slot, field)
        for slot, fields in sorted(absent.items())
        for field in sorted(fields)
        if code in checks_reading(slot, field)
    ]
    return tuple(hits)


def absent_fields_reason(pairs: tuple[tuple[str, str], ...]) -> str:
    """Lý do ghi vào `check_runs.status_reason` — nêu ĐÚNG trường nào, ở biểu nào.

    "Thiếu cột" mà không nói cột nào thì cán bộ không biết mở file nào ra sửa.
    """
    names = [
        f"{label_of(slot, field)} ({SLOT_LABEL_VI.get(slot, slot)})"
        for slot, field in pairs
    ]
    return "Cán bộ xác nhận kỳ này không có cột " + " · ".join(names)


def classify_absent_fields(
    pairs: tuple[tuple[str, str], ...],
) -> RemedyClassification:
    """(lớp cách gỡ, đích) của cổng trường vắng — luôn lớp 1, như cổng thiếu nguồn.

    Trường vắng là chuyện của file thuộc CHÍNH kỳ này, nên nạp lại file của kỳ này (sau
    khi sửa cột, hoặc nộp bản có đủ cột) là đường gỡ. Giữ đúng quy tắc đơn điệu ở
    `not_evaluable.py`: còn nạp được thì cách gỡ là nạp.
    """
    target = RemedyTarget(TARGET_DOCUMENT, pairs[0][0]) if pairs else None
    return REMEDY_NEED_FILE_THIS_PERIOD, target


__all__ = [
    "SOURCES",
    "absent_fields_for_period",
    "absent_fields_reason",
    "available_sources",
    "blocking_absent_fields",
    "classify_absent_fields",
    "classify_missing_sources",
    "missing_sources_reason",
]
