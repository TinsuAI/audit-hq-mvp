"""Nhóm 2 — Cân bằng và tồn kho (§4.1 đề án).

4 MVP check: C2.1, C2.2, C2.3 (tồn cuối NVL âm), C2.4 (tồn cuối TP âm).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.registry import Severity
from app.models import Finding, NvlBalance, SpBalance

# Cho phép sai số làm tròn ±0.01 trên phương trình (theo §4.1).
_TOLERANCE = 0.01


def _nvl_evidence(material_code: str, year: int, company_id: int) -> list[dict]:
    return [{
        "table": "nvl_balances",
        "filter": {"company_id": company_id, "period_year": year, "material_code": material_code},
    }]


def _sp_evidence(product_code: str, year: int, company_id: int) -> list[dict]:
    return [{
        "table": "sp_balances",
        "filter": {"company_id": company_id, "period_year": year, "product_code": product_code},
    }]


def check_c2_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """Mất cân bằng phương trình M15:
        tồn_cuối ≠ tồn_đầu + nhập − tái_xuất − chuyển_MĐSD − xuất_SX − xuất_khác

    Trường hợp đặc biệt "tồn ảo": tồn_đầu = 0 nhưng tồn_cuối > nhập_trong_kỳ — phương
    trình tự động không cân (cho ra số âm bên VP), nên đã được rule này phát hiện.
    Chỉ thêm chú thích "tồn ảo" vào details để cán bộ đọc tiện.
    """
    rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    findings: list[Finding] = []
    for r in rows:
        expected_closing = (
            (r.opening_qty or 0.0)
            + (r.import_qty or 0.0)
            - (r.reexport_qty or 0.0)
            - (r.repurpose_qty or 0.0)
            - (r.production_out_qty or 0.0)
            - (r.other_out_qty or 0.0)
        )
        diff = (r.closing_qty or 0.0) - expected_closing
        if abs(diff) <= _TOLERANCE:
            continue

        ghost = (
            abs(r.opening_qty or 0.0) <= _TOLERANCE
            and (r.closing_qty or 0.0) > (r.import_qty or 0.0) + _TOLERANCE
        )

        details = {
            "opening": r.opening_qty,
            "import": r.import_qty,
            "reexport": r.reexport_qty,
            "repurpose": r.repurpose_qty,
            "production_out": r.production_out_qty,
            "other_out": r.other_out_qty,
            "closing_reported": r.closing_qty,
            "closing_expected": expected_closing,
            "diff": diff,
        }
        if ghost:
            details["ghost_stock"] = True

        ghost_marker = " · TỒN ẢO" if ghost else ""
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C2.1",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=(
                f"M15 không cân: NVL {r.material_code} tồn_cuối={r.closing_qty:.2f} vs "
                f"kỳ vọng {expected_closing:.2f} (chênh {diff:+.2f}){ghost_marker}"
            ),
            details=details,
            evidence_refs=_nvl_evidence(r.material_code, year, company_id),
        ))
    return findings


def check_c2_2(session: Session, company_id: int, year: int) -> list[Finding]:
    """Mất cân bằng phương trình M15a:
        tồn_cuối ≠ tồn_đầu + nhập_kho − chuyển_MĐSD − xuất_khẩu − xuất_khác
    """
    rows = session.scalars(
        select(SpBalance).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
        )
    ).all()

    findings: list[Finding] = []
    for r in rows:
        expected_closing = (
            (r.opening_qty or 0.0)
            + (r.intake_qty or 0.0)
            - (r.repurpose_qty or 0.0)
            - (r.export_qty or 0.0)
            - (r.other_out_qty or 0.0)
        )
        diff = (r.closing_qty or 0.0) - expected_closing
        if abs(diff) <= _TOLERANCE:
            continue

        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C2.2",
            severity=Severity.CRITICAL.value,
            subject_type="product_code",
            subject_key=r.product_code,
            title=(
                f"M15a không cân: TP {r.product_code} tồn_cuối={r.closing_qty:.2f} vs "
                f"kỳ vọng {expected_closing:.2f} (chênh {diff:+.2f})"
            ),
            details={
                "opening": r.opening_qty,
                "intake": r.intake_qty,
                "repurpose": r.repurpose_qty,
                "export": r.export_qty,
                "other_out": r.other_out_qty,
                "closing_reported": r.closing_qty,
                "closing_expected": expected_closing,
                "diff": diff,
            },
            evidence_refs=_sp_evidence(r.product_code, year, company_id),
        ))
    return findings


def check_c2_3(session: Session, company_id: int, year: int) -> list[Finding]:
    """Tồn cuối NVL âm: closing_qty < 0 (với tolerance)."""
    rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.closing_qty < -_TOLERANCE,
        )
    ).all()

    return [
        Finding(
            company_id=company_id,
            period_year=year,
            check_code="C2.3",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=(
                f"NVL {r.material_code} có tồn cuối âm: {r.closing_qty:.2f} {r.unit or ''}"
            ),
            details={
                "closing_qty": r.closing_qty,
                "unit": r.unit,
            },
            evidence_refs=_nvl_evidence(r.material_code, year, company_id),
        )
        for r in rows
    ]


def check_c2_4(session: Session, company_id: int, year: int) -> list[Finding]:
    """Tồn cuối TP âm: closing_qty < 0 (với tolerance). Đối xứng C2.3 cho thành phẩm."""
    rows = session.scalars(
        select(SpBalance).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
            SpBalance.closing_qty < -_TOLERANCE,
        )
    ).all()

    return [
        Finding(
            company_id=company_id,
            period_year=year,
            check_code="C2.4",
            severity=Severity.CRITICAL.value,
            subject_type="product_code",
            subject_key=r.product_code,
            title=(
                f"TP {r.product_code} có tồn cuối âm: {r.closing_qty:.2f} {r.unit or ''}"
            ),
            details={
                "closing_qty": r.closing_qty,
                "unit": r.unit,
            },
            evidence_refs=_sp_evidence(r.product_code, year, company_id),
        )
        for r in rows
    ]


CHECKS = {
    "C2.1": check_c2_1,
    "C2.2": check_c2_2,
    "C2.3": check_c2_3,
    "C2.4": check_c2_4,
}
