"""Registry và metadata cho các check trong catalog Audit-HQ.

Mỗi check trong §4 đề án có một `CheckSpec`. Pipeline `run_checks` quét
registry để biết check nào đã enable và call function tương ứng.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


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
))
register(CheckSpec(
    code="C1.7",
    group=1,
    title="Tỷ lệ chuyển mục đích sử dụng vượt ngưỡng",
    description=(
        "`chuyển_mục_đích_sử_dụng` / `nhập_trong_kỳ` cao bất thường. "
        ">10% Cảnh báo · >25% Nghiêm trọng."
    ),
    default_severity=Severity.WARNING,
))


# --- Nhóm 2 — Cân bằng và tồn kho (3 MVP, C2.4 W.I.P) ---
register(CheckSpec(
    code="C2.1",
    group=2,
    title="Mất cân bằng phương trình M15 (NVL)",
    description=(
        "`tồn_cuối ≠ tồn_đầu + nhập − tái_xuất − chuyển_MĐSD − xuất_SX − xuất_khác` "
        "(tolerance ±0.01). Bao gồm trường hợp tồn ảo: tồn_đầu = 0 nhưng tồn_cuối > nhập."
    ),
    default_severity=Severity.CRITICAL,
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
))
register(CheckSpec(
    code="C2.3",
    group=2,
    title="Tồn cuối NVL âm",
    description="Bất kỳ mã NVL nào có `closing_qty < 0` trên M15 (tolerance ±0.01).",
    default_severity=Severity.CRITICAL,
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


def severity_for(check_code: str, pct: float) -> Severity | None:
    """Map % chênh lệch tuyệt đối sang severity theo scale của check.

    Trả None nếu pct dưới mọi ngưỡng fire (vd C1.7 dưới 10%).
    """
    scale = {
        "C1.1": _C1_1,
        "C1.4": _C1_4,
        "C1.7": _C1_7,
    }.get(check_code)
    if scale is None:
        return SPECS[check_code].default_severity
    abs_pct = abs(pct)
    for limit, sev in scale.bands:
        if abs_pct < limit:
            return sev
    return scale.bands[-1][1]


CheckFunction = Callable
