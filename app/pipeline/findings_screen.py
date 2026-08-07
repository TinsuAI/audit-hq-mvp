"""Khối "Chưa đánh giá được" của màn phát hiện (#97) — NƠI ĐỌC THỨ HAI của lớp cách gỡ.

Spec mục 2 chốt **một phân loại, hai nơi đọc**: màn dữ liệu tính lớp 1 và 2 trực tiếp
từ DB trước khi chạy kiểm tra lần nào (`app.pipeline.data_screen`), còn màn phát hiện
đọc lớp ĐÃ LƯU ở `check_runs.remedy`. Đây là nửa sau.

**Lớp lấy từ bản ghi, đích tính lại lúc hiển thị.** Lớp là thứ lần chạy đã kết luận —
đọc lại nó bằng bộ phân loại trực tiếp sẽ biến khối này thành bản sao của màn dữ liệu
và giấu mất chỗ hai đường lệch nhau. Đích thì ngược lại: nó đi stale ngay khi cán bộ
nạp thêm file, nên KHÔNG lưu (ADR #24 mục 2) mà gọi lại `predict_check` —
CHÍNH bộ phân loại của màn dữ liệu, không viết bộ thứ hai.

Hai đường đó lệch nhau được, và lệch là bình thường: dữ liệu lên sau lần chạy thì lớp
tính lại có thể đã hết chặn. Khi đó không còn đích, và mục vẫn phải có đường dẫn sang
màn dữ liệu đúng kỳ — mất nút gỡ mới là hỏng.

**Bản ghi trước migration có `remedy` rỗng.** Chúng vào nhóm riêng, KHÔNG suy lớp thay:
gán một lớp cho thứ chưa từng đo được là khẳng định sai, đúng dạng lỗi mà cả spec lẫn
ADR #24 gọi tên. Cách gỡ của nhóm đó là chạy lại kiểm tra để lớp được ghi.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.checks.not_evaluable import (
    REMEDY_CLASSES,
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    TARGET_COMPANY_FIELD,
    TARGET_PERIOD,
    RemedyTarget,
    load_not_evaluable,
)
from app.checks.registry import SPECS
from app.checks.sources import available_sources
from app.models import Company
from app.pipeline.data_screen import (
    COMPANY_FIELD_LABEL_VI,
    COMPANY_FIELDS_ANCHOR,
    GROUP_ORDER,
    GROUP_TITLE_VI,
    period_anchor,
)
from app.pipeline.readiness import predict_check

#: Lớp của một bản ghi ghi TRƯỚC cột `check_runs.remedy` — chưa từng được đo.
REMEDY_UNKNOWN = "unknown"

#: Thứ tự nhóm: ba lớp theo thứ tự việc cán bộ làm được, rồi tới nhóm chưa có lớp.
PANEL_GROUP_ORDER: tuple[str, ...] = (*GROUP_ORDER, REMEDY_UNKNOWN)

PANEL_GROUP_TITLE_VI = {
    **GROUP_TITLE_VI,
    REMEDY_UNKNOWN: "Chưa ghi nhận cách gỡ",
}

# Câu dẫn của mỗi nhóm, viết cho MÀN PHÁT HIỆN. Khác câu của màn dữ liệu: ở đây kiểm
# tra đã chạy và đã kết luận là không kết luận được, nên câu nói về hệ quả trên kết
# quả, không nói về phép đếm "đủ dữ liệu cho N/M kiểm tra".
PANEL_GROUP_HINT_VI = {
    REMEDY_NEED_FILE_THIS_PERIOD: (
        "Thiếu nguồn dữ liệu của chính kỳ này — nạp file của kỳ ở màn dữ liệu rồi "
        "chạy lại kiểm tra."
    ),
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION: (
        "File của kỳ này không gỡ được: cần dữ liệu của một kỳ khác, hoặc một xác "
        "nhận ở mức doanh nghiệp."
    ),
    REMEDY_NOTHING_TO_LOAD: (
        "Đây là kết luận về doanh nghiệp, không phải lỗ hổng dữ liệu — không có gì "
        "nạp thêm để gỡ."
    ),
    REMEDY_UNKNOWN: (
        "Lần chạy này có trước khi hệ thống ghi lớp cách gỡ — chạy lại kiểm tra để "
        "biết gỡ bằng cách nào."
    ),
}

# Mã lớp 3 → mã kiểm tra LIỆT KÊ CHI TIẾT sự việc đó. C4.3 dừng ở cổng độ phủ định
# mức, còn C4.9 vẫn liệt kê TỪNG mã thành phẩm thiếu định mức: cả hai đọc chung
# `products_without_norm`, nên danh sách chi tiết đúng là kết quả của C4.9.
DETAIL_CHECK = {
    "C4.3": "C4.9",
}


def detail_check_for(code: str) -> str | None:
    """Mã kiểm tra liệt kê chi tiết cho một kết luận lớp 3; None nếu chưa có."""
    return DETAIL_CHECK.get(code)


@dataclass(frozen=True)
class RemedyItem:
    """Một mã `not_evaluable` trên màn phát hiện, kèm cách gỡ đúng chỗ."""

    code: str
    title: str
    reason: str
    #: Lớp ĐÃ LƯU ở `check_runs.remedy`. None = không có lớp dùng được: dòng ghi
    #: trước migration, hoặc giá trị nằm ngoài bộ ba.
    remedy: str | None
    #: Đích TÍNH LẠI lúc hiển thị — không đọc từ DB, không ghi xuống DB.
    target: RemedyTarget | None
    #: Đường dẫn gỡ: màn dữ liệu (lớp 1, 2) hoặc kiểm tra liệt kê chi tiết (lớp 3).
    url: str | None
    action_label: str
    #: Lớp 3 — kết luận về doanh nghiệp, không phải lỗ hổng dữ liệu.
    conclusion: bool
    #: Mã kiểm tra liệt kê chi tiết, chỉ có ở lớp 3.
    detail_code: str | None = None


@dataclass(frozen=True)
class RemedyGroup:
    """Một nhóm cách gỡ trong khối "Chưa đánh giá được"."""

    remedy: str
    title: str
    hint: str
    #: Nhóm này là lỗ hổng DỮ LIỆU (nạp thêm thì gỡ được) hay không.
    counted: bool
    conclusion: bool
    items: tuple[RemedyItem, ...] = ()


def _documents_url(slug: str, year: int) -> str:
    """Màn dữ liệu, neo đúng dòng kỳ.

    `add` luôn có mặt: kỳ chưa từng có file/dòng/phát hiện thì chưa phải một dòng, và
    neo trỏ vào chỗ không tồn tại. `build_data_screen` bỏ qua `add` khi kỳ đã có dòng,
    nên một dạng đường dẫn dùng được cho cả hai ca.
    """
    return f"/companies/{slug}/documents?add={year}#{period_anchor(year)}"


def _link(slug: str, year: int, target: RemedyTarget | None) -> tuple[str, str]:
    """(đường dẫn, nhãn nút) của một mục lớp 1 hoặc lớp 2."""
    if target is not None and target.kind == TARGET_COMPANY_FIELD:
        label = COMPANY_FIELD_LABEL_VI.get(str(target.value))
        return (
            f"/companies/{slug}/documents#{COMPANY_FIELDS_ANCHOR}",
            f"Xác nhận {label}" if label else "Xác nhận thuộc tính doanh nghiệp",
        )
    if target is not None and target.kind == TARGET_PERIOD:
        target_year = int(target.value)
        return _documents_url(slug, target_year), f"Mở màn dữ liệu kỳ {target_year}"
    # Đích là loại tài liệu, hoặc không tính lại được đích (dữ liệu đã lên sau lần
    # chạy · kiểm tra mở rộng không dự đoán được). Cả hai gỡ ở chính kỳ này.
    return _documents_url(slug, year), f"Mở màn dữ liệu kỳ {year}"


def _conclusion_link(slug: str, year: int, code: str) -> tuple[str | None, str, str | None]:
    """(đường dẫn, nhãn nút, mã chi tiết) của một mục lớp 3."""
    detail = detail_check_for(code)
    if detail is None:
        return None, "", None
    return f"/companies/{slug}?year={year}&check={detail}", f"Xem chi tiết ở {detail}", detail


def _title(code: str, specs: Mapping[str, object] | None) -> str:
    spec = (specs or {}).get(code) or SPECS.get(code)
    return getattr(spec, "title", None) or code


def not_evaluable_panel(
    session: Session,
    company: Company,
    year: int,
    specs: Mapping[str, object] | None = None,
) -> tuple[RemedyGroup, ...]:
    """Khối "Chưa đánh giá được" của (DN, kỳ), gom theo LỚP CÁCH GỠ ĐÃ LƯU.

    Chỉ trả nhóm có mục. `session` là tham số — hàm KHÔNG mở phiên nào và KHÔNG ghi
    gì: đích được tính lại, không lưu.
    """
    runs = load_not_evaluable(session, company.id, year)
    if not runs:
        return ()

    slug = company.slug or company.code
    present = available_sources(session, company.id, year)

    buckets: dict[str, list[RemedyItem]] = {}
    for code in sorted(runs):
        run = runs[code]
        # Giá trị ngoài bộ ba đi cùng đường với `remedy` rỗng: chỗ đọc không hiểu lớp
        # thì không được dựng nút theo nó, và càng không được BỎ mã khỏi khối. Rơi
        # khỏi danh sách là đúng kiểu hỏng mà cả spec lẫn ADR #24 gọi tên.
        remedy = run.remedy if run.remedy in REMEDY_CLASSES else None
        conclusion = remedy == REMEDY_NOTHING_TO_LOAD

        target: RemedyTarget | None = None
        url: str | None = None
        label = ""
        detail: str | None = None
        if conclusion:
            url, label, detail = _conclusion_link(slug, year, code)
        elif remedy is not None:
            # Đích tính LẠI ở đây, bằng chính bộ phân loại của màn dữ liệu.
            target = predict_check(session, company.id, year, code, present).target
            url, label = _link(slug, year, target)

        buckets.setdefault(remedy or REMEDY_UNKNOWN, []).append(RemedyItem(
            code=code,
            title=_title(code, specs),
            reason=run.reason,
            remedy=remedy,
            target=target,
            url=url,
            action_label=label,
            conclusion=conclusion,
            detail_code=detail,
        ))

    return tuple(
        RemedyGroup(
            remedy=remedy,
            title=PANEL_GROUP_TITLE_VI[remedy],
            hint=PANEL_GROUP_HINT_VI[remedy],
            # Lớp 3 là kết luận về DN; nhóm chưa có lớp thì chưa biết gỡ bằng gì —
            # cả hai không phải "còn thiếu dữ liệu" đếm được.
            counted=remedy not in (REMEDY_NOTHING_TO_LOAD, REMEDY_UNKNOWN),
            conclusion=remedy == REMEDY_NOTHING_TO_LOAD,
            items=tuple(buckets[remedy]),
        )
        for remedy in PANEL_GROUP_ORDER
        if buckets.get(remedy)
    )


__all__ = [
    "DETAIL_CHECK",
    "PANEL_GROUP_HINT_VI",
    "PANEL_GROUP_ORDER",
    "PANEL_GROUP_TITLE_VI",
    "REMEDY_UNKNOWN",
    "RemedyGroup",
    "RemedyItem",
    "detail_check_for",
    "not_evaluable_panel",
]
