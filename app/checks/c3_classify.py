"""Nhóm 3 — Phân loại hàng hoá (§4.1 đề án).

3 MVP check: C3.1, C3.2, C3.3.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.not_evaluable import CheckResult, NotEvaluable, RemedyClassification
from app.checks.registry import Severity
from app.checks.scope import declaration_scope
from app.checks.sources import classify_missing_sources
from app.checks.uom import UomMatch, resolve_canonical
from app.checks.uom import compare as uom_compare
from app.models import DeclarationLine, Finding, Norm, NvlBalance

# Loại hình NVL theo từng kiểu DN (§4.0 đề án).
_NVL_CODES = {"E11", "E15", "E31", "E33", "E21", "E23"}
# Mã loại hình máy móc thiết bị miễn thuế.
_MMTB_CODES = {"E13"}


def _evidence_for_codes(item_code: str, year: int, company_id: int, codes: set[str]) -> dict:
    return {
        "table": "declaration_lines",
        "filter": {
            "company_id": company_id,
            "period_year": year,
            "item_code": item_code,
            "customs_code__in": sorted(codes),
        },
    }


def check_c3_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """Cùng mã vật tư khai trên cả tờ khai NVL (E11/E31/E21) và MMTB (E13).

    Cặp mâu thuẫn cụ thể (đề án §4.1): E11+E13 · E31+E13 · E21+E13.
    """
    rows = session.execute(
        select(DeclarationLine.item_code, DeclarationLine.customs_code)
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.item_code.is_not(None),
            DeclarationLine.customs_code.in_(_NVL_CODES | _MMTB_CODES),
        )
        .distinct()
    ).all()

    codes_per_item: dict[str, set[str]] = defaultdict(set)
    for item_code, customs_code in rows:
        codes_per_item[item_code].add(customs_code)

    findings: list[Finding] = []
    for item_code, codes in sorted(codes_per_item.items()):
        nvl_overlap = codes & _NVL_CODES
        mmtb_overlap = codes & _MMTB_CODES
        if not nvl_overlap or not mmtb_overlap:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C3.1",
            severity=Severity.WARNING.value,
            subject_type="item_code",
            subject_key=item_code,
            title=(
                f"Mã {item_code} khai cả NVL ({', '.join(sorted(nvl_overlap))}) "
                f"và MMTB ({', '.join(sorted(mmtb_overlap))})"
            ),
            details={
                "nvl_codes": sorted(nvl_overlap),
                "mmtb_codes": sorted(mmtb_overlap),
            },
            evidence_refs=[
                _evidence_for_codes(item_code, year, company_id, nvl_overlap),
                _evidence_for_codes(item_code, year, company_id, mmtb_overlap),
            ],
        ))
    return findings


def _hs_divergence_level(hs_codes: set[str]) -> str | None:
    """So sánh 2+ mã HS để biết khác ở mức nào.

    Trả `chapter` (chương = 2 số đầu), `heading` (nhóm = 4 số),
    `subheading` (phân nhóm = 6 số), hoặc None nếu giống nhau hoặc HS không đủ số.
    """
    cleaned = {h for h in hs_codes if h and len(h) >= 2}
    if len(cleaned) < 2:
        return None
    chapters = {h[:2] for h in cleaned}
    headings = {h[:4] for h in cleaned if len(h) >= 4}
    subheadings = {h[:6] for h in cleaned if len(h) >= 6}
    if len(chapters) > 1:
        return "chapter"
    if len(headings) > 1:
        return "heading"
    if len(subheadings) > 1:
        return "subheading"
    return None


_HS_SEVERITY = {
    "subheading": Severity.INFO,
    "heading": Severity.WARNING,
    "chapter": Severity.CRITICAL,
}

_HS_LEVEL_LABEL = {
    "subheading": "phân nhóm 6 số",
    "heading": "nhóm 4 số",
    "chapter": "chương 2 số",
}


def check_c3_2(session: Session, company_id: int, year: int) -> list[Finding]:
    """Mã HS không nhất quán trong kỳ (cùng mã vật tư): ≥2 mã HS khác nhau."""
    rows = session.execute(
        select(DeclarationLine.item_code, DeclarationLine.hs_code)
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.item_code.is_not(None),
            DeclarationLine.hs_code.is_not(None),
        )
        .distinct()
    ).all()

    hs_per_item: dict[str, set[str]] = defaultdict(set)
    for item_code, hs in rows:
        hs_per_item[item_code].add(hs)

    findings: list[Finding] = []
    for item_code, hs_set in sorted(hs_per_item.items()):
        if len(hs_set) < 2:
            continue
        level = _hs_divergence_level(hs_set)
        if level is None:
            continue
        severity = _HS_SEVERITY[level]
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C3.2",
            severity=severity.value,
            subject_type="item_code",
            subject_key=item_code,
            title=(
                f"Mã {item_code} có {len(hs_set)} mã HS khác nhau "
                f"(khác {_HS_LEVEL_LABEL[level]}): {', '.join(sorted(hs_set))}"
            ),
            details={
                "hs_codes": sorted(hs_set),
                "divergence": level,
            },
            evidence_refs=[{
                "table": "declaration_lines",
                "filter": {
                    "company_id": company_id,
                    "period_year": year,
                    "item_code": item_code,
                },
            }],
        ))
    return findings


# Thứ tự "xấu dần". UNRESOLVED nằm DƯỚI DIFFERENT: một mã vừa có đơn vị lệch thật
# vừa có đơn vị không tra được thì phát hiện vẫn phải mang mức của cái lệch thật,
# nếu không thì thêm một chuỗi rác vào file là hạ được mức của phát hiện thật.
_MATCH_RANK = {
    UomMatch.EQUIVALENT: 0,
    UomMatch.SAME_FAMILY: 1,
    UomMatch.UNRESOLVED: 2,
    UomMatch.DIFFERENT: 3,
}

_NO_COMPARISON_UNITS = (
    "Kỳ này không có đơn vị tính nào để đối chiếu với Mẫu 15 — chưa có tờ "
    "khai trong cửa sổ kỳ, cũng chưa có Mẫu 16."
)


def comparison_units_gate(
    session: Session, company_id: int, year: int
) -> tuple[str, RemedyClassification] | None:
    """(lý do, (lớp, đích)) khi C3.3 không còn vế nào để đối chiếu; None nếu còn.

    `registry.requires` chỉ khai được quan hệ VÀ, mà vế đối chiếu của C3.3 là tờ khai
    HOẶC Mẫu 16 — nên cổng nằm ở đây. Hỏi bằng `LIMIT 1` với ĐÚNG bộ lọc mà thân check
    dùng để dựng hai tập đơn vị (`item_code`/`unit` không rỗng trong cửa sổ kỳ;
    `material_unit` không rỗng ở Mẫu 16), để hai đường không trả lời khác nhau.
    """
    has_bcct = session.scalar(
        select(DeclarationLine.id)
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.item_code.is_not(None),
            DeclarationLine.unit.is_not(None),
        )
        .limit(1)
    )
    has_m16 = session.scalar(
        select(Norm.id)
        .where(
            Norm.company_id == company_id,
            Norm.period_year == year,
            Norm.material_unit.is_not(None),
        )
        .limit(1)
    )
    if has_bcct or has_m16:
        return None
    # Lớp 1: cả hai vế đối chiếu đều là file của CHÍNH kỳ này (ADR #24 mục 2).
    return _NO_COMPARISON_UNITS, classify_missing_sources(("bcct", "m16"))


def check_c3_3(session: Session, company_id: int, year: int) -> CheckResult:
    """Đơn vị tính không nhất quán giữa M15, M16 và BCCT cùng mã NVL.

    Severity ladder (qua DB UOM canonical/alias):
    - Cùng canonical (alias resolve identical) → SKIP (không fire).
    - Cùng family (convertible, vd KG↔GAM, M↔CM) → 🔵 Thông tin.
    - Khác family hoặc unknown → 🔴 Nghiêm trọng (sai đơn vị ×1000 nguy hiểm).

    Vế M16 (sổ yêu cầu dòng 2.6, ADR đề án 06/08): C4.3 nhân định mức với sản lượng
    rồi so với `xuất_sản_xuất` của M15 — hai vế lệch đơn vị thì tiêu hao lý thuyết
    sai đúng bằng hệ số quy đổi, C4.3 chỉ thấy một con số vượt ngưỡng.

    Neo vẫn là mã CÓ dòng M15: mã chỉ có ở M16 mà không có dòng M15 là ca thiếu
    nguồn của C4.1, không phải chuyện đơn vị tính.
    """
    gated = comparison_units_gate(session, company_id, year)
    if gated is not None:
        # Thiếu cả hai vế mà vẫn chạy tiếp thì ra 0 phát hiện, đọc như "đơn vị nhất quán".
        reason, (remedy, _target) = gated
        return NotEvaluable(reason, remedy=remedy)

    m15_rows = session.execute(
        select(NvlBalance.book, NvlBalance.material_code, NvlBalance.unit).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.unit.is_not(None),
        )
    ).all()
    # Đơn vị M15 theo (SỔ, mã): đối chiếu đơn vị của TỪNG sổ với tờ khai (tờ khai dùng
    # chung cả pháp nhân), không để đơn vị sổ này che sổ kia (xem ADR #19).
    # Gom thành TẬP đơn vị: một mã có thể ghi ở hai đơn vị (cùng một lượng ghi lại),
    # nếu ghi đè thì đơn vị khớp tờ khai bị đơn vị kia che, kết quả phụ thuộc thứ tự dòng.
    m15_units: dict[tuple[str | None, str], set[str]] = defaultdict(set)
    for book, code, unit in m15_rows:
        m15_units[(book, code)].add(unit)

    bcct_units: dict[str, set[str]] = defaultdict(set)
    bcct_rows = session.execute(
        select(DeclarationLine.item_code, DeclarationLine.unit)
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.item_code.is_not(None),
            DeclarationLine.unit.is_not(None),
        )
        .distinct()
    ).all()
    for code, unit in bcct_rows:
        bcct_units[code].add(unit)

    # Đơn vị M16 theo (SỔ, mã) — cùng khoá với M15: định mức của sổ nào chỉ so với
    # tồn kho của sổ đó (ADR #19). Một mã khai ở nhiều dòng định mức có thể mang
    # nhiều đơn vị, gom thành tập giống M15.
    m16_units: dict[tuple[str | None, str], set[str]] = defaultdict(set)
    for book, code, unit in session.execute(
        select(Norm.book, Norm.material_code, Norm.material_unit).where(
            Norm.company_id == company_id,
            Norm.period_year == year,
            Norm.material_unit.is_not(None),
        ).distinct()
    ).all():
        m16_units[(book, code)].add(unit)

    findings: list[Finding] = []
    for (book, code), unit_set in sorted(
        m15_units.items(), key=lambda kv: (kv[0][1], kv[0][0] is None, kv[0][0] or "")
    ):
        bcct_set = bcct_units.get(code, set())
        m16_set = m16_units.get((book, code), set())
        if not bcct_set and not m16_set:
            continue

        # Với TỪNG đơn vị M15: so với mọi đơn vị đối chiếu (tờ khai + định mức), lấy
        # match yếu nhất (worst case). Giữa các đơn vị M15 của cùng một mã: lấy match
        # TỐT NHẤT — chỉ cần một đơn vị khớp là sổ đó nhất quán, các đơn vị còn lại
        # ghi lại cùng lượng đó.
        def _worst_against(candidate: str, others: set[str]) -> UomMatch:
            result = UomMatch.EQUIVALENT
            for other in others:
                m = uom_compare(session, candidate, other)
                if _MATCH_RANK[m] > _MATCH_RANK[result]:
                    result = m
                if result == UomMatch.DIFFERENT:
                    return result  # đã chạm mức xấu nhất, không cần so tiếp
            return result

        worst_match = UomMatch.DIFFERENT
        m15_unit = sorted(unit_set)[0]
        for candidate in sorted(unit_set):
            candidate_worst = _worst_against(candidate, bcct_set | m16_set)
            if _MATCH_RANK[candidate_worst] < _MATCH_RANK[worst_match]:
                worst_match = candidate_worst
                m15_unit = candidate

        if worst_match == UomMatch.EQUIVALENT:
            continue  # Có đơn vị khớp cả tờ khai lẫn định mức — skip.

        # Nguồn nào lệch với đơn vị đã chọn — tiêu đề phải chỉ đúng chỗ phải sửa.
        diverging = [
            label
            for label, units in (("BCCT", bcct_set), ("M16", m16_set))
            if units and _worst_against(m15_unit, units) != UomMatch.EQUIVALENT
        ]

        # Mã ghi ở nhiều đơn vị thì nêu cả tập, đừng để tiêu đề chỉ hiện một đơn vị
        # trong khi bằng chứng trả về nhiều dòng khác đơn vị.
        m15_label = f"'{m15_unit}'" if len(unit_set) == 1 else str(sorted(unit_set))
        others_label = ", ".join(
            f"{label}={sorted(units)}"
            for label, units in (("M16", m16_set), ("BCCT", bcct_set))
            if units
        )

        unresolved_units: list[str] = []
        if worst_match == UomMatch.SAME_FAMILY:
            severity = Severity.INFO
            title = (
                f"Đơn vị tính NVL {code} dùng nhiều đơn vị cùng họ "
                f"(có thể quy đổi): M15={m15_label}, {others_label}"
            )
        elif worst_match == UomMatch.UNRESOLVED:
            # Chưa đo được, không phải đã đo ra lệch — mức phải nói đúng điều đó.
            # Cách gỡ nằm trong tay cán bộ: khai bí danh ở /admin/units rồi chạy lại.
            unresolved_units = sorted(
                u for u in (unit_set | bcct_set | m16_set)
                if resolve_canonical(session, u) is None
            )
            severity = Severity.WARNING
            title = (
                f"Đơn vị tính NVL {code} chưa đối chiếu được — "
                f"{', '.join(unresolved_units)} không có trong bảng đơn vị chuẩn: "
                f"M15={m15_label}, {others_label}"
            )
        else:
            severity = Severity.CRITICAL
            title = (
                f"Đơn vị tính NVL {code} không nhất quán "
                f"({' và '.join(diverging)} lệch M15): M15={m15_label}, {others_label}"
            )

        evidence_refs = [
            {
                "table": "nvl_balances",
                "filter": (
                    {"company_id": company_id, "period_year": year, "material_code": code}
                    | ({"book": book} if book is not None else {})
                ),
            },
        ]
        if m16_set:
            evidence_refs.append({
                "table": "norms",
                "filter": (
                    {"company_id": company_id, "period_year": year, "material_code": code}
                    | ({"book": book} if book is not None else {})
                ),
            })
        if bcct_set:
            evidence_refs.append({
                "table": "declaration_lines",
                "filter": {
                    "company_id": company_id,
                    "period_year": year,
                    "item_code": code,
                },
            })

        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C3.3",
            severity=severity.value,
            subject_type="material_code",
            subject_key=code,
            book=book,
            title=title,
            details={
                "m15_unit": m15_unit,
                "m15_units": sorted(unit_set),
                "m16_units": sorted(m16_set),
                "bcct_units": sorted(bcct_set),
                "diverging_sources": diverging,
                "uom_match": worst_match.value,
                "unresolved_units": unresolved_units,
            },
            evidence_refs=evidence_refs,
        ))
    return findings


CHECKS = {
    "C3.1": check_c3_1,
    "C3.2": check_c3_2,
    "C3.3": check_c3_3,
}

__all__ = [
    "CHECKS",
    "check_c3_1",
    "check_c3_2",
    "check_c3_3",
    "comparison_units_gate",
]
