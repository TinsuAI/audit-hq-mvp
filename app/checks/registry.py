"""Registry và metadata cho các check trong catalog Audit-HQ.

Mỗi check trong §4 đề án có một `CheckSpec`. Pipeline `run_checks` quét
registry để biết check nào đã enable và call function tương ứng.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

# Re-export để nơi dùng registry không phải nhớ hai module cho cùng một khái niệm.
from app.checks.sources import SOURCE_LABEL_VI, SOURCES  # noqa: F401


class Severity(StrEnum):
    CRITICAL = "critical"  # 🔴 Nghiêm trọng
    WARNING = "warning"    # 🟡 Cảnh báo
    INFO = "info"          # 🔵 Thông tin


SEVERITY_LABEL_VI = {
    Severity.CRITICAL: "Nghiêm trọng",
    Severity.WARNING: "Cảnh báo",
    Severity.INFO: "Thông tin",
}

SEVERITY_BADGE = {
    Severity.CRITICAL: "🔴",
    Severity.WARNING: "🟡",
    Severity.INFO: "🔵",
}


@dataclass(frozen=True)
class CheckSpec:
    code: str
    group: int                   # Nhóm (1..12) trong §4 đề án
    title: str
    description: str             # Mô tả ngắn nghiệp vụ
    default_severity: Severity   # Mặc định khi finding fire (rule scale-based có thể override)
    enabled: bool = True
    # Nguồn Tầng 1 check THỰC ĐỌC (fact-audit từ code, không đoán) — ADR #23 T4.
    # Thiếu bất kỳ nguồn nào → `run_checks` trả `not_evaluable` kèm lý do ở
    # `check_runs.status_reason`, thay vì chạy join rỗng rồi báo 0 phát hiện
    # (đọc như "sạch"). Cùng đường với `NotEvaluable` các check tự trả (#58).
    requires: frozenset[str] = frozenset()


# Catalog 16 MVP checks. Bổ sung dần sang W.I.P khi đến tuần đề án quy định.
SPECS: dict[str, CheckSpec] = {}


def register(spec: CheckSpec) -> CheckSpec:
    if spec.code in SPECS:
        raise ValueError(f"Check {spec.code} đã được đăng ký")
    SPECS[spec.code] = spec
    return spec


# --- Nhóm 1 — Số lượng nhập/xuất (6 MVP, C1.5 W.I.P) ---
register(CheckSpec(
    code="C1.1",
    group=1,
    title="Lệch số lượng nhập NVL (M15 vs tờ khai)",
    description=(
        "`nhập_trong_kỳ` (M15) khác Σ tờ khai nhập theo mã. "
        "<5% Thông tin · 5–20% Cảnh báo · >20% Nghiêm trọng."
    ),
    default_severity=Severity.WARNING,
    requires=frozenset({"bcct", "m15"}),
))
register(CheckSpec(
    code="C1.2",
    group=1,
    title="Có tờ khai nhập nhưng không có trong M15",
    description=(
        "Mã NVL có trên BCCT (tờ khai nhập) nhưng không có dòng nào trong M15. "
        "Bỏ sót NVL nhập khỏi BCQT."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"bcct", "m15"}),
))
register(CheckSpec(
    code="C1.3",
    group=1,
    title="Có trong M15 nhưng không có tờ khai",
    description=(
        "`nhập_trong_kỳ` > 0 mà không có tờ khai nhập tương ứng. "
        "M15 không có căn cứ tờ khai."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"bcct", "m15"}),
))
register(CheckSpec(
    code="C1.4",
    group=1,
    title="Lệch số lượng xuất TP (M15a vs tờ khai)",
    description=(
        "`xuất_khẩu` (M15a) khác Σ tờ khai xuất theo mã thành phẩm. "
        "<1% Thông tin · 1–5% Cảnh báo · >5% Nghiêm trọng."
    ),
    default_severity=Severity.WARNING,
    requires=frozenset({"bcct", "m15a"}),
))
register(CheckSpec(
    code="C1.6",
    group=1,
    title="Chuyển mục đích sử dụng không có tờ khai A42",
    description=(
        "`chuyển_mục_đích_sử_dụng` > 0 trong M15 nhưng không có tờ khai A42 tương ứng. "
        "Vi phạm điều kiện miễn thuế."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"bcct", "m15"}),
))
register(CheckSpec(
    code="C1.7",
    group=1,
    title="Tỷ lệ chuyển mục đích sử dụng vượt ngưỡng",
    description=(
        "`chuyển_mục_đích_sử_dụng / (tồn_đầu_kỳ + nhập_trong_kỳ)` cao bất thường. "
        "≥10% Cảnh báo · ≥25% Nghiêm trọng."
    ),
    default_severity=Severity.WARNING,
    requires=frozenset({"m15"}),
))


# --- Nhóm 2 — Cân bằng và tồn kho (4 MVP) ---
register(CheckSpec(
    code="C2.1",
    group=2,
    title="Mất cân bằng phương trình M15 (NVL)",
    description=(
        "`tồn_cuối ≠ tồn_đầu + nhập − tái_xuất − chuyển_MĐSD − xuất_SX − xuất_khác` "
        "(tolerance ±0.01). Bao gồm trường hợp tồn ảo: tồn_đầu = 0 nhưng tồn_cuối > nhập."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15"}),
))
register(CheckSpec(
    code="C2.2",
    group=2,
    title="Mất cân bằng phương trình M15a (TP)",
    description=(
        "`tồn_cuối ≠ tồn_đầu + nhập_kho − chuyển_MĐSD − xuất_khẩu − xuất_khác` "
        "(tolerance ±0.01)."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15a"}),
))
register(CheckSpec(
    code="C2.3",
    group=2,
    title="Tồn cuối NVL âm",
    description="Bất kỳ mã NVL nào có `closing_qty < 0` trên M15 (tolerance ±0.01).",
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15"}),
))
register(CheckSpec(
    code="C2.4",
    group=2,
    title="Tồn cuối TP âm",
    description="Bất kỳ mã thành phẩm nào có `closing_qty < 0` trên M15a (tolerance ±0.01).",
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15a"}),
))


# --- Nhóm 3 — Phân loại hàng hoá (3 MVP) ---
register(CheckSpec(
    code="C3.1",
    group=3,
    title="Cùng mã vật tư khai nhiều loại hình mâu thuẫn",
    description=(
        "Mã có cả tờ khai NVL (E11/E15/E31/E33/E21/E23) và tờ khai MMTB (E13) "
        "trong cùng kỳ. Cặp mâu thuẫn: E11+E13 · E31+E13 · E21+E13."
    ),
    default_severity=Severity.WARNING,
    requires=frozenset({"bcct"}),
))
register(CheckSpec(
    code="C3.2",
    group=3,
    title="Mã HS không nhất quán trong kỳ",
    description=(
        "Cùng mã vật tư có ≥2 mã HS khác nhau trên các tờ khai. "
        "Khác phân nhóm 6 số → Thông tin · khác nhóm 4 số → Cảnh báo · "
        "khác chương 2 số → Nghiêm trọng."
    ),
    default_severity=Severity.WARNING,
    requires=frozenset({"bcct"}),
))
register(CheckSpec(
    code="C3.3",
    group=3,
    title="Đơn vị tính không nhất quán",
    description=(
        "Cùng mã NVL có ≥2 đơn vị khác nhau giữa M15 và BCCT. "
        "Cùng họ (KG↔GAM, M↔CM) → Thông tin; "
        "khác họ (sai ×1000) → Nghiêm trọng."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"bcct", "m15"}),
))


# --- Nhóm 4 — Định mức M16 (3 MVP, còn lại W.I.P) ---
register(CheckSpec(
    code="C4.1",
    group=4,
    title="NVL trong M16 không có nguồn",
    description=(
        "Mã NVL có trong M16 nhưng không có dòng M15, "
        "hoặc M15 có nhưng `nhập_trong_kỳ = 0` và `tồn_đầu_kỳ = 0`. "
        "Phạm vi là hợp của mã khai định mức đúng kỳ này và mã có tiêu hao lý thuyết "
        "> 0 trong kỳ theo định mức HIỆU LỰC (kể cả bản khai kỳ trước) — vế sau là "
        "phần C4.3 nhường lại, gắn với sản lượng sản xuất của kỳ."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15", "m16"}),
))
register(CheckSpec(
    code="C4.3",
    group=4,
    title="Tổng tiêu hao M16 vượt xuất sản xuất M15",
    description=(
        "Σ(định_mức × sản_lượng_sản_xuất_M15a) theo NVL > `xuất_sản_xuất` trong M15. "
        "Vượt >5% Cảnh báo · >20% Nghiêm trọng. Mã NVL không có dòng nào trong M15 "
        "thuộc C4.1 (thiếu nguồn), không xét ở đây. Định mức lấy theo bản khai HIỆU "
        "LỰC — kỳ lớn nhất ≤ kỳ đang xét của cùng cặp TP-NVL trong cùng sổ, vì M16 kế "
        "thừa giữa các kỳ. Vướng cổng độ phủ định mức (thiếu định mức của một TP đã "
        "sản xuất, hoặc kỳ biên chưa xác nhận năm đầu nộp BCQT) thì trả CHƯA ĐÁNH GIÁ "
        "ĐƯỢC cho cả kỳ, không trả 0 phát hiện."
    ),
    default_severity=Severity.WARNING,
))
register(CheckSpec(
    code="C4.9",
    group=4,
    title="TP có sản xuất trong kỳ nhưng thiếu định mức",
    description=(
        "Mã TP có `sản_lượng_sản_xuất_nhập_kho > 0` trong M15a mà không có định mức "
        "hiệu lực nào trong M16, kể cả bản khai của các kỳ trước. Kết quả là danh sách "
        "từng mã thiếu định mức, không phải một con số tổng."
    ),
    default_severity=Severity.WARNING,
    requires=frozenset({"m15", "m15a", "m16"}),
))


# --- Nhóm 5 — Truy nguồn NVL (1 MVP, còn lại W.I.P) ---
register(CheckSpec(
    code="C5.1",
    group=5,
    title="NVL có xuất SX nhưng không có nhập + không tồn đầu",
    description=(
        "M15 có `xuất_sản_xuất > 0` và `nhập_trong_kỳ = 0` và `tồn_đầu_kỳ = 0`. "
        "Tiêu hao từ nguồn không khai báo."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15"}),
))


# --- Nhóm 6 — Liên kỳ (1 MVP, còn lại W.I.P) ---
register(CheckSpec(
    code="C6.1",
    group=6,
    title="Tồn đầu kỳ N khác tồn cuối kỳ N-1 (NVL)",
    description=(
        "M15 tồn đầu kỳ N ≠ M15 tồn cuối kỳ N-1 theo từng mã NVL. "
        "Cần ≥2 kỳ dữ liệu (tolerance ±0.01)."
    ),
    default_severity=Severity.CRITICAL,
    requires=frozenset({"m15"}),
))


# --- Severity scales for rule with thresholds ---


@dataclass(frozen=True)
class _Scale:
    """Scale rules: từ % chênh lệch (>=0) sang severity. Đọc từ thấp đến cao."""

    bands: tuple[tuple[float, Severity | None], ...] = field(default_factory=tuple)


# C1.1: <5% info, 5–20% warning, >20% critical
_C1_1 = _Scale(bands=(
    (5.0, Severity.INFO),
    (20.0, Severity.WARNING),
    (float("inf"), Severity.CRITICAL),
))

# C1.4: <1% info, 1–5% warning, >5% critical
_C1_4 = _Scale(bands=(
    (1.0, Severity.INFO),
    (5.0, Severity.WARNING),
    (float("inf"), Severity.CRITICAL),
))

# C1.7: <10% (no fire), 10–25% warning, >25% critical
_C1_7 = _Scale(bands=(
    (10.0, None),  # không fire dưới 10%
    (25.0, Severity.WARNING),
    (float("inf"), Severity.CRITICAL),
))

# C4.3: <5% (no fire — đã filter ở rule), 5–20% warning, >20% critical
_C4_3 = _Scale(bands=(
    (5.0, None),
    (20.0, Severity.WARNING),
    (float("inf"), Severity.CRITICAL),
))


def severity_for(check_code: str, pct: float) -> Severity | None:
    """Map % chênh lệch tuyệt đối sang severity theo scale của check.

    Trả None nếu pct dưới mọi ngưỡng fire (vd C1.7 dưới 10%).
    """
    scale = {
        "C1.1": _C1_1,
        "C1.4": _C1_4,
        "C1.7": _C1_7,
        "C4.3": _C4_3,
    }.get(check_code)
    if scale is None:
        return SPECS[check_code].default_severity
    abs_pct = abs(pct)
    for limit, sev in scale.bands:
        if abs_pct < limit:
            return sev
    return scale.bands[-1][1]


def missing_sources(check_code: str, available: set[str]) -> tuple[str, ...]:
    """Nguồn check cần mà (DN, kỳ) chưa có. Check không khai `requires` → không bao giờ skip."""
    spec = SPECS.get(check_code)
    if spec is None:
        return ()
    return tuple(sorted(spec.requires - available))


CheckFunction = Callable


def get_check_meta(code: str, session) -> CheckSpec | None:
    """Trả về CheckSpec cho code đã cho, merge built-in + published dynamic checks.

    Built-in có priority; dynamic check phải status=published mới expose.
    Trả None nếu không tìm thấy.
    """
    if code in SPECS:
        return SPECS[code]

    from sqlalchemy import select

    from app.models.check_definition import CheckDefinition, CheckStatus

    row = session.scalar(
        select(CheckDefinition).where(
            CheckDefinition.code == code,
            CheckDefinition.status == CheckStatus.PUBLISHED,
        )
    )
    if row is None:
        return None
    return _dynamic_to_spec(row)


def get_all_specs(session) -> dict[str, CheckSpec]:
    """Dict gộp built-in SPECS + published dynamic checks từ DB.

    Built-in luôn có priority nếu có cùng code (không xảy ra trong thực tế
    vì built-in dùng prefix C và dynamic dùng X).
    """
    from sqlalchemy import select

    from app.models.check_definition import CheckDefinition, CheckStatus

    result: dict[str, CheckSpec] = dict(SPECS)
    rows = session.scalars(
        select(CheckDefinition).where(CheckDefinition.status == CheckStatus.PUBLISHED)
    ).all()
    for row in rows:
        if row.code not in result:
            result[row.code] = _dynamic_to_spec(row)
    return result


def _dynamic_to_spec(row) -> CheckSpec:
    """Chuyển CheckDefinition DB row → CheckSpec (readonly dataclass)."""
    return CheckSpec(
        code=row.code,
        group=row.group,
        title=row.title,
        description=row.description,
        default_severity=Severity(row.default_severity),
        enabled=True,
    )


# --- Check → column registry (WS1, ADR #18) --------------------------------
# Dict TĨNH khai mỗi check đọc `(slot, field)` nào và tiêu thụ ra sao:
#   - ``individual`` — đọc TRỰC TIẾP một cột (không qua tổng cân đối), nên nguồn
#     ``balance-checked`` KHÔNG đủ (đẳng thức không phân biệt hai cột cùng dấu) —
#     cần ``header-matched`` / ``officer-confirmed``.
#   - ``sum`` — chỉ dùng cột như một SỐ HẠNG trong đẳng thức cân đối C2 tự tính lại
#     (bất biến dưới hoán vị cột cùng dấu) → ``balance-checked`` là đủ.
# Cột dùng riêng lẻ (đọc từ code check): production_out (C4.3/C5.1), repurpose M15
# (C1.6/C1.7), export M15a (C1.4), intake M15a (C4.3 — P-07, số nhân là sản lượng
# sản xuất chứ không phải xuất khẩu), định mức thực tế M16 (C4.3). Xem GLOSSARY.
from app.adapters.evidence import (  # noqa: E402 — tránh cycle: evidence không import checks
    BALANCE_CHECKED,
    NEEDS_REVIEW,
    POSITION_ONLY,
    VERIFIED,
)

INDIVIDUAL = "individual"
SUM = "sum"

# (slot, field, consumed_as). Chỉ khai cột GIÁ TRỊ số + cột mã (khoá). name/unit
# (C3.3) và cột BCCT/HS (C3.1/C3.2/C6.1) chưa mô hình hoá ở WS1.
CHECK_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "C1.1": (("m15", "material_code", INDIVIDUAL), ("m15", "import_qty", SUM)),
    "C1.2": (("m15", "material_code", INDIVIDUAL),),
    "C1.3": (("m15", "material_code", INDIVIDUAL), ("m15", "import_qty", SUM)),
    "C1.4": (("m15a", "product_code", INDIVIDUAL), ("m15a", "export_qty", INDIVIDUAL)),
    "C1.6": (("m15", "material_code", INDIVIDUAL), ("m15", "repurpose_qty", INDIVIDUAL)),
    "C1.7": (
        ("m15", "material_code", INDIVIDUAL), ("m15", "repurpose_qty", INDIVIDUAL),
        ("m15", "opening_qty", SUM), ("m15", "import_qty", SUM),
    ),
    "C2.1": (
        ("m15", "opening_qty", SUM), ("m15", "import_qty", SUM),
        ("m15", "reexport_qty", SUM), ("m15", "repurpose_qty", SUM),
        ("m15", "production_out_qty", SUM), ("m15", "other_out_qty", SUM),
        ("m15", "closing_qty", SUM),
    ),
    "C2.2": (
        ("m15a", "opening_qty", SUM), ("m15a", "intake_qty", SUM),
        ("m15a", "repurpose_qty", SUM), ("m15a", "export_qty", SUM),
        ("m15a", "other_out_qty", SUM), ("m15a", "closing_qty", SUM),
    ),
    "C2.3": (("m15", "material_code", INDIVIDUAL), ("m15", "closing_qty", SUM)),
    "C2.4": (("m15a", "product_code", INDIVIDUAL), ("m15a", "closing_qty", SUM)),
    "C4.1": (
        ("m16", "material_code", INDIVIDUAL), ("m15", "material_code", INDIVIDUAL),
        ("m15", "import_qty", SUM), ("m15", "opening_qty", SUM),
    ),
    "C4.3": (
        ("m16", "material_code", INDIVIDUAL), ("m16", "norm_qty", INDIVIDUAL),
        ("m15a", "product_code", INDIVIDUAL), ("m15a", "intake_qty", INDIVIDUAL),
        ("m15", "material_code", INDIVIDUAL), ("m15", "production_out_qty", INDIVIDUAL),
    ),
    # C4.9 đọc cột MÃ TP của M16 (mã nào đã có định mức) chứ không đọc trị định mức.
    # `product_code` của slot m16 chưa có trong mô hình bằng chứng nên không sinh
    # `review_state`; khai ở đây để đổi map cột M16 kéo C4.9 vào diện chạy lại.
    "C4.9": (
        ("m15a", "product_code", INDIVIDUAL), ("m15a", "intake_qty", INDIVIDUAL),
        ("m16", "product_code", INDIVIDUAL),
    ),
    "C5.1": (
        ("m15", "material_code", INDIVIDUAL), ("m15", "production_out_qty", INDIVIDUAL),
        ("m15", "import_qty", SUM), ("m15", "opening_qty", SUM),
    ),
}


def checks_reading(slot: str, field: str) -> list[str]:
    """Mã các check đọc `(slot, field)` — cho banner cổng review nêu check bị ảnh hưởng."""
    return [
        code
        for code, uses in CHECK_COLUMNS.items()
        if any(s == slot and f == field for s, f, _ in uses)
    ]


def checks_reading_slot(slot: str) -> list[str]:
    """Mã các check đọc BẤT KỲ cột nào của slot.

    Dùng khi cột KHOÁ (mã hàng) của slot đổi map trên file đã `parsed`: evidence_refs
    của MỌI finding trên slot lọc theo cột mã (material_code/product_code), nên đổi cột
    mã làm khoá của mọi dòng đổi → mọi check đọc slot phải chạy lại. C2.1/C2.2 đọc mã ở
    evidence NHƯNG không khai cột mã trong registry (chỉ khai cột số dạng tổng); chỉ
    dựa `checks_reading(mã)` sẽ để C2.1/C2.2 lại finding treo."""
    return sorted({
        code
        for code, uses in CHECK_COLUMNS.items()
        if any(s == slot for s, _, _ in uses)
    })


def is_consumed(slot: str, field: str) -> bool:
    """Có check nào đọc `(slot, field)` không."""
    return bool(checks_reading(slot, field))


def is_individually_consumed(slot: str, field: str) -> bool:
    """Có check nào đọc `(slot, field)` TRỰC TIẾP (consumed_as = individual) không."""
    return any(
        s == slot and f == field and how == INDIVIDUAL
        for uses in CHECK_COLUMNS.values()
        for s, f, how in uses
    )


def review_state(slot: str, field: str, evidence: str) -> str:
    """Suy `verified` / `needs_review` cho một cột từ nguồn bằng chứng + registry.

    `needs_review` khi: (a) cột được một check tiêu thụ mà nguồn tốt nhất là
    `position-only`, HOẶC (b) cột dùng RIÊNG LẺ mà nguồn tốt nhất chỉ `balance-checked`.
    Còn lại `verified`.
    """
    if not is_consumed(slot, field):
        return VERIFIED
    if evidence == POSITION_ONLY:
        return NEEDS_REVIEW
    if evidence == BALANCE_CHECKED and is_individually_consumed(slot, field):
        return NEEDS_REVIEW
    return VERIFIED
