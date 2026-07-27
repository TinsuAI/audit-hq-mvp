"""Nửa TÍNH ĐƯỢC của tổng quan mỗi kiểm tra (ADR #21 mục 1-2, 8).

Số liệu tính bằng Python và lưu vào `check_overviews.aggregate_json`; template
render thẳng. LLM chỉ ĐỌC bảng này rồi viết phần nhận định (TQ-4).

Vì sao tách: số do model phát không đưa vào báo cáo khách được (sinh lại có thể
đổi số trong khi dữ liệu đứng yên); bảng số liệu vẫn hiện khi LLM lỗi/tắt/chậm;
và nhận định ngắn hơn vì thôi kể lại con số đã cho.

**KHÔNG cộng tuyệt đối chéo đơn vị.** Mỗi mã một `unit` (Cái/Chiếc, Lon/Can,
kg…) nên tổng lệch chéo đơn vị là số vô nghĩa. Độ lớn báo bằng phần trăm và
ĐẾM; số tuyệt đối chỉ đứng trong mục điểm nóng theo từng mã. Phân vị dưới đây là
thống kê THỨ TỰ trên từng mã, không phải tổng.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.books import book_label, is_multi_book
from app.checks.registry import SPECS
from app.models import Finding

# Trường số mang TÍN HIỆU của mỗi kiểm tra. Khai tường minh thay vì quét mọi khoá
# số trong `details`: phần lớn khoá là lượng thô theo đơn vị của từng mã (opening,
# import, closing…), phân vị trên đó trộn đơn vị và không đọc được.
# `pct=True` → trình bày theo phần trăm.
PERCENTILE_KEYS: dict[str, tuple[tuple[str, bool], ...]] = {
    "C1.1": (("diff_pct", True),),
    "C1.4": (("diff_pct", True),),
    "C1.6": (("m15_repurpose", False),),
    "C1.7": (("ratio_pct", True),),
    "C2.1": (("diff", False),),
    "C2.2": (("diff", False),),
    "C2.3": (("closing_qty", False),),
    "C2.4": (("closing_qty", False),),
    "C3.2": (("divergence", False),),
    "C4.3": (("diff_pct", True), ("theoretical_consumption", False)),
    "C6.1": (("diff", False),),
}

TOP_N_CONCENTRATION = 5
COVERAGE_TARGET = 0.8
SEVERITIES = ("critical", "warning", "info")


def _percentile(sorted_values: list[float], q: float) -> float:
    """Phân vị theo hạng gần nhất — không nội suy (dữ liệu rời rạc, ít dòng)."""
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, round(q * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _concentration(subject_counts: list[tuple[str, int]], total: int) -> dict:
    """Tập trung: bao nhiêu mã, top-5 chiếm bao nhiêu, bao nhiêu mã phủ 80%."""
    counts = sorted((n for _, n in subject_counts), reverse=True)
    distinct = len(counts)
    top_share = round(100 * sum(counts[:TOP_N_CONCENTRATION]) / total, 1) if total else 0.0
    covering = 0
    running = 0
    for n in counts:
        if total and running / total >= COVERAGE_TARGET:
            break
        running += n
        covering += 1
    return {
        "distinct_subjects": distinct,
        "top5_share_pct": top_share,
        "subjects_covering_80pct": covering,
        "top_subjects": [
            {"subject_key": k, "count": n}
            for k, n in sorted(subject_counts, key=lambda x: -x[1])[:TOP_N_CONCENTRATION]
        ],
    }


def _numeric_fields(rows: list[Finding], check_code: str) -> list[dict]:
    """Phân vị `n/min/p50/p90/max` + chiều lệch cho từng trường tín hiệu."""
    out = []
    for key, is_pct in PERCENTILE_KEYS.get(check_code, ()):
        values = []
        for f in rows:
            v = _numeric((f.details or {}).get(key))
            if v is not None:
                values.append(v)
        if not values:
            continue
        values.sort()
        out.append({
            "key": key,
            "is_pct": is_pct,
            "n": len(values),
            "min": round(values[0], 2),
            "p50": round(_percentile(values, 0.5), 2),
            "p90": round(_percentile(values, 0.9), 2),
            "max": round(values[-1], 2),
            # Chiều lệch: bao nhiêu mã cao hơn, bao nhiêu thấp hơn. Đọc được mà
            # không phải cộng lượng chéo đơn vị.
            "higher": sum(1 for v in values if v > 0),
            "lower": sum(1 for v in values if v < 0),
            "zero": sum(1 for v in values if v == 0),
        })
    return out


def _by_book(rows: list[Finding]) -> list[dict]:
    counts: dict[str | None, int] = {}
    for f in rows:
        counts[f.book] = counts.get(f.book, 0) + 1
    return [
        {"book": b, "label": book_label(b), "count": n}
        for b, n in sorted(counts.items(), key=lambda x: (x[0] is None, x[0] or ""))
    ]


def _previous_year(
    db: Session, company_id: int, period_year: int, check_code: str,
    subjects_now: set[str],
) -> dict:
    """So với năm trước: tổng, chênh lệch, mã mới xuất hiện.

    Không có kỳ trước thì nói rõ — hiện 0 sẽ đọc thành "năm ngoái sạch".
    """
    prev = period_year - 1
    has_prev = bool(
        db.scalar(
            select(func.count()).select_from(Finding).where(
                Finding.company_id == company_id, Finding.period_year == prev
            )
        )
    )
    if not has_prev:
        return {"available": False, "year": prev}

    rows = db.execute(
        select(Finding.subject_key, func.count()).where(
            Finding.company_id == company_id,
            Finding.period_year == prev,
            Finding.check_code == check_code,
        ).group_by(Finding.subject_key)
    ).all()
    prev_total = sum(n for _, n in rows)
    prev_subjects = {k for k, _ in rows if k}
    new_subjects = sorted(subjects_now - prev_subjects)
    return {
        "available": True,
        "year": prev,
        "total": prev_total,
        "delta": None,  # điền ở build_stats khi đã biết tổng năm nay
        "new_subjects_count": len(new_subjects),
        "new_subjects": new_subjects[:TOP_N_CONCENTRATION],
    }


def build_stats(
    db: Session, *, company_id: int, period_year: int, check_code: str
) -> dict:
    """Bảng số liệu của (DN, năm, mã kiểm tra) — đóng băng vào dòng tổng quan.

    ĐÓNG BĂNG chứ không tính live: tính live nghĩa là parse `details` mỗi lần
    load trang doanh nghiệp cho MỌI nhóm có tổng quan (C1.6 tới 7.446 dòng), và
    bảng với nhận định phải mô tả cùng một mốc — nếu không cán bộ đọc "8 mã" ở
    bảng và "12 mã" ở câu dưới, cả hai đều đúng ở hai thời điểm khác nhau.
    """
    spec = SPECS.get(check_code)
    rows = db.scalars(
        select(Finding).where(
            Finding.company_id == company_id,
            Finding.period_year == period_year,
            Finding.check_code == check_code,
        )
    ).all()
    total = len(rows)

    severity_totals = dict.fromkeys(SEVERITIES, 0)
    subject_counts: dict[str, int] = {}
    for f in rows:
        if f.severity in severity_totals:
            severity_totals[f.severity] += 1
        if f.subject_key:
            subject_counts[f.subject_key] = subject_counts.get(f.subject_key, 0) + 1

    previous = _previous_year(
        db, company_id, period_year, check_code, set(subject_counts)
    )
    if previous["available"]:
        previous["delta"] = total - previous["total"]

    stats = {
        "check_code": check_code,
        "title": spec.title if spec else check_code,
        "year": period_year,
        "total_findings": total,
        "severity_totals": severity_totals,
        "concentration": _concentration(list(subject_counts.items()), total),
        "numeric_fields": _numeric_fields(rows, check_code),
        "previous_year": previous,
    }
    # Mục theo sổ chỉ có nghĩa với pháp nhân nhiều sổ quyết toán.
    if is_multi_book(db, company_id, period_year):
        stats["by_book"] = _by_book(rows)
    return stats
