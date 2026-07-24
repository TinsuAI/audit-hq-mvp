"""Nhóm 3 — Phân loại hàng hoá (§4.1 đề án).

3 MVP check: C3.1, C3.2, C3.3.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.registry import Severity
from app.checks.uom import UomMatch
from app.checks.uom import compare as uom_compare
from app.models import DeclarationLine, Finding, NvlBalance

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
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
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
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
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


def check_c3_3(session: Session, company_id: int, year: int) -> list[Finding]:
    """Đơn vị tính không nhất quán giữa M15 và BCCT cùng mã NVL.

    Severity ladder (qua DB UOM canonical/alias):
    - Cùng canonical (alias resolve identical) → SKIP (không fire).
    - Cùng family (convertible, vd KG↔GAM, M↔CM) → 🔵 Thông tin.
    - Khác family hoặc unknown → 🔴 Nghiêm trọng (sai đơn vị ×1000 nguy hiểm).
    """
    m15_rows = session.execute(
        select(NvlBalance.book, NvlBalance.material_code, NvlBalance.unit).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.unit.is_not(None),
        )
    ).all()
    # Đơn vị M15 theo (SỔ, mã): đối chiếu đơn vị của TỪNG sổ với tờ khai (tờ khai dùng
    # chung cả pháp nhân), không để đơn vị sổ này che sổ kia (xem ADR #19).
    m15_units = {(book, code): unit for book, code, unit in m15_rows}

    bcct_units: dict[str, set[str]] = defaultdict(set)
    bcct_rows = session.execute(
        select(DeclarationLine.item_code, DeclarationLine.unit)
        .where(
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
            DeclarationLine.item_code.is_not(None),
            DeclarationLine.unit.is_not(None),
        )
        .distinct()
    ).all()
    for code, unit in bcct_rows:
        bcct_units[code].add(unit)

    findings: list[Finding] = []
    for (book, code), m15_unit in sorted(
        m15_units.items(), key=lambda kv: (kv[0][1], kv[0][0] is None, kv[0][0] or "")
    ):
        bcct_set = bcct_units.get(code, set())
        if not bcct_set:
            continue

        # So sánh M15 với từng BCCT unit; lấy match yếu nhất (worst case).
        worst_match = UomMatch.EQUIVALENT
        for bcct_unit in bcct_set:
            m = uom_compare(session, m15_unit, bcct_unit)
            if m == UomMatch.DIFFERENT:
                worst_match = UomMatch.DIFFERENT
                break
            if m == UomMatch.SAME_FAMILY and worst_match == UomMatch.EQUIVALENT:
                worst_match = UomMatch.SAME_FAMILY

        if worst_match == UomMatch.EQUIVALENT:
            continue  # Tất cả equivalent — skip.

        if worst_match == UomMatch.SAME_FAMILY:
            severity = Severity.INFO
            title = (
                f"Đơn vị tính NVL {code} dùng nhiều đơn vị cùng họ "
                f"(có thể quy đổi): M15='{m15_unit}', BCCT={sorted(bcct_set)}"
            )
        else:
            severity = Severity.CRITICAL
            title = (
                f"Đơn vị tính NVL {code} không nhất quán: "
                f"M15='{m15_unit}', BCCT={sorted(bcct_set)}"
            )

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
                "bcct_units": sorted(bcct_set),
                "uom_match": worst_match.value,
            },
            evidence_refs=[
                {
                    "table": "nvl_balances",
                    "filter": (
                        {"company_id": company_id, "period_year": year, "material_code": code}
                        | ({"book": book} if book is not None else {})
                    ),
                },
                {
                    "table": "declaration_lines",
                    "filter": {
                        "company_id": company_id,
                        "period_year": year,
                        "item_code": code,
                    },
                },
            ],
        ))
    return findings


CHECKS = {
    "C3.1": check_c3_1,
    "C3.2": check_c3_2,
    "C3.3": check_c3_3,
}
