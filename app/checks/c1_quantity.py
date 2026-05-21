"""Nhóm 1 — Số lượng nhập / xuất (§4.1 đề án).

Implement 6 MVP checks: C1.1, C1.2, C1.3, C1.4, C1.6, C1.7.
C1.5 (tái xuất M15 vs B13) là W.I.P theo §4.1 — chưa implement.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.checks.company_type import (
    detect_company_type,
    export_codes_for,
    import_codes_for,
)
from app.checks.registry import Severity, severity_for
from app.models import DeclarationLine, Finding, NvlBalance, SpBalance


def _evidence_nvl(material_code: str, year: int, company_id: int) -> list[dict]:
    return [{
        "table": "nvl_balances",
        "filter": {"company_id": company_id, "period_year": year, "material_code": material_code},
    }]


def _evidence_sp(product_code: str, year: int, company_id: int) -> list[dict]:
    return [{
        "table": "sp_balances",
        "filter": {"company_id": company_id, "period_year": year, "product_code": product_code},
    }]


def _evidence_decl(item_code: str, year: int, company_id: int, customs_codes: set[str]) -> list[dict]:
    return [{
        "table": "declaration_lines",
        "filter": {
            "company_id": company_id,
            "period_year": year,
            "item_code": item_code,
            "customs_code__in": sorted(customs_codes),
        },
    }]


def _sum_bcct_by_item(
    session: Session,
    company_id: int,
    year: int,
    customs_codes: set[str],
) -> dict[str, float]:
    if not customs_codes:
        return {}
    rows = session.execute(
        select(DeclarationLine.item_code, func.coalesce(func.sum(DeclarationLine.quantity), 0.0))
        .where(
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
            DeclarationLine.customs_code.in_(customs_codes),
            DeclarationLine.item_code.is_not(None),
        )
        .group_by(DeclarationLine.item_code)
    ).all()
    return {code: float(qty or 0.0) for code, qty in rows}


def _pct_diff(actual: float, expected: float) -> float:
    """Chênh lệch % so với `expected`. Trả 0 khi expected ≈ 0 và actual ≈ 0."""
    if abs(expected) < 1e-9:
        return 100.0 if abs(actual) > 1e-9 else 0.0
    return (actual - expected) / abs(expected) * 100.0


def check_c1_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """Lệch số lượng nhập NVL: |M15.import - Σ BCCT| / M15.import."""
    company_type = detect_company_type(session, company_id, year)
    import_codes = import_codes_for(company_type)
    if not import_codes:
        return []

    bcct_sums = _sum_bcct_by_item(session, company_id, year, import_codes)
    findings: list[Finding] = []
    rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    for r in rows:
        if r.import_qty <= 0:
            continue  # C1.1 chỉ áp với NVL có khai nhập trong M15
        bcct_qty = bcct_sums.get(r.material_code, 0.0)
        diff_pct = _pct_diff(bcct_qty, r.import_qty)
        if abs(diff_pct) < 5.0:
            continue  # dưới ngưỡng Thông tin
        sev = severity_for("C1.1", abs(diff_pct))
        if sev is None:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.1",
            severity=sev.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=(
                f"Lệch nhập NVL {r.material_code}: "
                f"M15={r.import_qty:.2f} vs BCCT={bcct_qty:.2f} ({diff_pct:+.1f}%)"
            ),
            details={
                "company_type": company_type.value,
                "import_codes": sorted(import_codes),
                "m15_import": r.import_qty,
                "bcct_sum": bcct_qty,
                "diff_pct": diff_pct,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id)
            + _evidence_decl(r.material_code, year, company_id, import_codes),
        ))
    return findings


def check_c1_2(session: Session, company_id: int, year: int) -> list[Finding]:
    """Có tờ khai nhập nhưng không có dòng nào trong M15."""
    company_type = detect_company_type(session, company_id, year)
    import_codes = import_codes_for(company_type)
    if not import_codes:
        return []

    bcct_codes = set(
        session.scalars(
            select(DeclarationLine.item_code)
            .where(
                DeclarationLine.company_id == company_id,
                DeclarationLine.period_year == year,
                DeclarationLine.customs_code.in_(import_codes),
                DeclarationLine.item_code.is_not(None),
            )
            .distinct()
        ).all()
    )
    m15_codes = set(
        session.scalars(
            select(NvlBalance.material_code).where(
                NvlBalance.company_id == company_id,
                NvlBalance.period_year == year,
            )
        ).all()
    )
    missing = bcct_codes - m15_codes

    findings: list[Finding] = []
    for code in sorted(missing):
        total = session.scalar(
            select(func.coalesce(func.sum(DeclarationLine.quantity), 0.0)).where(
                DeclarationLine.company_id == company_id,
                DeclarationLine.period_year == year,
                DeclarationLine.customs_code.in_(import_codes),
                DeclarationLine.item_code == code,
            )
        ) or 0.0
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.2",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=code,
            title=f"Mã NVL {code} có tờ khai nhập nhưng không có trong M15 (tổng {total:.2f})",
            details={
                "company_type": company_type.value,
                "import_codes": sorted(import_codes),
                "bcct_sum": float(total),
            },
            evidence_refs=_evidence_decl(code, year, company_id, import_codes),
        ))
    return findings


def check_c1_3(session: Session, company_id: int, year: int) -> list[Finding]:
    """M15 có nhập_trong_kỳ > 0 nhưng không có tờ khai nhập tương ứng."""
    company_type = detect_company_type(session, company_id, year)
    import_codes = import_codes_for(company_type)
    if not import_codes:
        return []

    bcct_codes = set(
        session.scalars(
            select(DeclarationLine.item_code)
            .where(
                DeclarationLine.company_id == company_id,
                DeclarationLine.period_year == year,
                DeclarationLine.customs_code.in_(import_codes),
                DeclarationLine.item_code.is_not(None),
            )
            .distinct()
        ).all()
    )
    m15_with_imports = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.import_qty > 0,
        )
    ).all()

    findings: list[Finding] = []
    for r in m15_with_imports:
        if r.material_code in bcct_codes:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.3",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=(
                f"M15 khai nhập NVL {r.material_code} "
                f"({r.import_qty:.2f} {r.unit or ''}) nhưng không có tờ khai"
            ),
            details={
                "company_type": company_type.value,
                "import_codes": sorted(import_codes),
                "m15_import": r.import_qty,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id),
        ))
    return findings


def check_c1_4(session: Session, company_id: int, year: int) -> list[Finding]:
    """Lệch số lượng xuất TP: |M15a.export - Σ BCCT export| / M15a.export."""
    company_type = detect_company_type(session, company_id, year)
    export_codes = export_codes_for(company_type)
    if not export_codes:
        return []

    bcct_sums = _sum_bcct_by_item(session, company_id, year, export_codes)
    findings: list[Finding] = []
    rows = session.scalars(
        select(SpBalance).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
        )
    ).all()

    for r in rows:
        if r.export_qty <= 0:
            continue
        bcct_qty = bcct_sums.get(r.product_code, 0.0)
        diff_pct = _pct_diff(bcct_qty, r.export_qty)
        if abs(diff_pct) < 1.0:
            continue
        sev = severity_for("C1.4", abs(diff_pct))
        if sev is None:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.4",
            severity=sev.value,
            subject_type="product_code",
            subject_key=r.product_code,
            title=(
                f"Lệch xuất TP {r.product_code}: "
                f"M15a={r.export_qty:.2f} vs BCCT={bcct_qty:.2f} ({diff_pct:+.1f}%)"
            ),
            details={
                "company_type": company_type.value,
                "export_codes": sorted(export_codes),
                "m15a_export": r.export_qty,
                "bcct_sum": bcct_qty,
                "diff_pct": diff_pct,
            },
            evidence_refs=_evidence_sp(r.product_code, year, company_id)
            + _evidence_decl(r.product_code, year, company_id, export_codes),
        ))
    return findings


def check_c1_6(session: Session, company_id: int, year: int) -> list[Finding]:
    """M15.chuyển_mục_đích_sử_dụng > 0 nhưng không có tờ khai A42 tương ứng."""
    a42_codes = set(
        session.scalars(
            select(DeclarationLine.item_code)
            .where(
                DeclarationLine.company_id == company_id,
                DeclarationLine.period_year == year,
                DeclarationLine.customs_code == "A42",
                DeclarationLine.item_code.is_not(None),
            )
            .distinct()
        ).all()
    )
    rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.repurpose_qty > 0,
        )
    ).all()

    findings: list[Finding] = []
    for r in rows:
        if r.material_code in a42_codes:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.6",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=(
                f"NVL {r.material_code} chuyển MĐSD {r.repurpose_qty:.2f} {r.unit or ''} "
                f"nhưng không có tờ khai A42"
            ),
            details={
                "m15_repurpose": r.repurpose_qty,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id),
        ))
    return findings


def check_c1_7(session: Session, company_id: int, year: int) -> list[Finding]:
    """Tỷ lệ chuyển MĐSD / nhập trong kỳ vượt ngưỡng (>10% warning, >25% critical)."""
    rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    findings: list[Finding] = []
    for r in rows:
        denom = (r.opening_qty or 0.0) + (r.import_qty or 0.0)
        if denom <= 0 or (r.repurpose_qty or 0.0) <= 0:
            continue
        pct = r.repurpose_qty / denom * 100.0
        sev = severity_for("C1.7", pct)
        if sev is None:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.7",
            severity=sev.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=f"NVL {r.material_code} chuyển MĐSD chiếm {pct:.1f}% tổng nhập",
            details={
                "repurpose": r.repurpose_qty,
                "opening": r.opening_qty,
                "import": r.import_qty,
                "ratio_pct": pct,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id),
        ))
    return findings


CHECKS = {
    "C1.1": check_c1_1,
    "C1.2": check_c1_2,
    "C1.3": check_c1_3,
    "C1.4": check_c1_4,
    "C1.6": check_c1_6,
    "C1.7": check_c1_7,
}
