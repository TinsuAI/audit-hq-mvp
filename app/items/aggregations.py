"""Aggregation helpers cho trang chi tiết mã NVL/TP.

Mọi truy vấn drill-in theo (company_id, item_code [, year]) đi qua đây
để giữ logic match consistent (exact match, không fuzzy).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.items.operations import classify_operation
from app.models import DeclarationLine, Norm, NvlBalance, SpBalance

ItemKind = Literal["nvl", "tp", "both", "unknown"]

# Sai số chấp nhận được khi đối chiếu BCCT vs BCQT (đơn vị giống nhau).
RECON_ABS_TOL = 0.5
RECON_REL_TOL = 0.01  # 1%


def detect_item_kind(session: Session, company_id: int, item_code: str) -> ItemKind:
    has_nvl = session.scalar(
        select(func.count())
        .select_from(NvlBalance)
        .where(NvlBalance.company_id == company_id, NvlBalance.material_code == item_code)
    ) or 0
    has_tp = session.scalar(
        select(func.count())
        .select_from(SpBalance)
        .where(SpBalance.company_id == company_id, SpBalance.product_code == item_code)
    ) or 0
    if has_nvl and has_tp:
        return "both"
    if has_nvl:
        return "nvl"
    if has_tp:
        return "tp"
    return "unknown"


def item_years(session: Session, company_id: int, item_code: str) -> list[int]:
    """Tập năm có dữ liệu cho mã này, gộp từ M15 + M15a + BCCT."""
    years: set[int] = set()
    for stmt in (
        select(NvlBalance.period_year).where(
            NvlBalance.company_id == company_id, NvlBalance.material_code == item_code
        ),
        select(SpBalance.period_year).where(
            SpBalance.company_id == company_id, SpBalance.product_code == item_code
        ),
        select(DeclarationLine.period_year).where(
            DeclarationLine.company_id == company_id, DeclarationLine.item_code == item_code
        ),
    ):
        years.update(session.scalars(stmt).all())
    return sorted(years)


def _bcct_yearly_io(session: Session, company_id: int, item_code: str) -> dict[int, dict]:
    """Tổng hợp BCCT theo năm cho 1 mã: qty nhập / xuất / line count."""
    rows = session.execute(
        select(
            DeclarationLine.period_year,
            DeclarationLine.customs_code,
            func.coalesce(func.sum(DeclarationLine.quantity), 0.0),
            func.count(),
        )
        .where(
            DeclarationLine.company_id == company_id,
            DeclarationLine.item_code == item_code,
        )
        .group_by(DeclarationLine.period_year, DeclarationLine.customs_code)
    ).all()

    by_year: dict[int, dict] = {}
    for year, code, qty, n in rows:
        bucket = by_year.setdefault(
            year, {"bcct_import_qty": 0.0, "bcct_export_qty": 0.0, "bcct_line_count": 0}
        )
        kind = classify_operation(code)
        if kind == "import":
            bucket["bcct_import_qty"] += float(qty or 0)
        elif kind == "export":
            bucket["bcct_export_qty"] += float(qty or 0)
        bucket["bcct_line_count"] += int(n)
    return by_year


def _match(a: float, b: float) -> bool:
    diff = abs(a - b)
    if diff <= RECON_ABS_TOL:
        return True
    scale = max(abs(a), abs(b), 1.0)
    return (diff / scale) <= RECON_REL_TOL


def nvl_yearly_summary(session: Session, company_id: int, material_code: str) -> list[dict]:
    """Mỗi năm: M15 balance fields + BCCT aggregate + reconciliation flags."""
    m15_rows = session.scalars(
        select(NvlBalance)
        .where(NvlBalance.company_id == company_id, NvlBalance.material_code == material_code)
        .order_by(NvlBalance.period_year)
    ).all()
    bcct = _bcct_yearly_io(session, company_id, material_code)
    years = sorted(set([r.period_year for r in m15_rows]) | set(bcct.keys()))

    m15_by_year = {r.period_year: r for r in m15_rows}
    out: list[dict] = []
    for y in years:
        m = m15_by_year.get(y)
        bc = bcct.get(y, {"bcct_import_qty": 0.0, "bcct_export_qty": 0.0, "bcct_line_count": 0})
        m15_import = float(m.import_qty) if m else 0.0
        row = {
            "year": y,
            "unit": m.unit if m else None,
            "opening_qty": float(m.opening_qty) if m else 0.0,
            "import_qty": m15_import,
            "reexport_qty": float(m.reexport_qty) if m else 0.0,
            "repurpose_qty": float(m.repurpose_qty) if m else 0.0,
            "production_out_qty": float(m.production_out_qty) if m else 0.0,
            "other_out_qty": float(m.other_out_qty) if m else 0.0,
            "closing_qty": float(m.closing_qty) if m else 0.0,
            "has_m15": m is not None,
            **bc,
            "import_diff": m15_import - bc["bcct_import_qty"],
            "import_match": _match(m15_import, bc["bcct_import_qty"]),
        }
        # Reconciliation phương trình kho: opening + import − (reexport + repurpose + prod_out + other) = closing
        if m is not None:
            expected_closing = (
                row["opening_qty"] + row["import_qty"]
                - row["reexport_qty"] - row["repurpose_qty"]
                - row["production_out_qty"] - row["other_out_qty"]
            )
            row["balance_diff"] = expected_closing - row["closing_qty"]
            row["balance_match"] = _match(expected_closing, row["closing_qty"])
        else:
            row["balance_diff"] = 0.0
            row["balance_match"] = True
        out.append(row)
    return out


def sp_yearly_summary(session: Session, company_id: int, product_code: str) -> list[dict]:
    m15a_rows = session.scalars(
        select(SpBalance)
        .where(SpBalance.company_id == company_id, SpBalance.product_code == product_code)
        .order_by(SpBalance.period_year)
    ).all()
    bcct = _bcct_yearly_io(session, company_id, product_code)
    years = sorted(set([r.period_year for r in m15a_rows]) | set(bcct.keys()))

    by_year = {r.period_year: r for r in m15a_rows}
    out: list[dict] = []
    for y in years:
        m = by_year.get(y)
        bc = bcct.get(y, {"bcct_import_qty": 0.0, "bcct_export_qty": 0.0, "bcct_line_count": 0})
        m_export = float(m.export_qty) if m else 0.0
        row = {
            "year": y,
            "unit": m.unit if m else None,
            "opening_qty": float(m.opening_qty) if m else 0.0,
            "intake_qty": float(m.intake_qty) if m else 0.0,
            "repurpose_qty": float(m.repurpose_qty) if m else 0.0,
            "export_qty": m_export,
            "other_out_qty": float(m.other_out_qty) if m else 0.0,
            "closing_qty": float(m.closing_qty) if m else 0.0,
            "has_m15a": m is not None,
            **bc,
            "export_diff": m_export - bc["bcct_export_qty"],
            "export_match": _match(m_export, bc["bcct_export_qty"]),
        }
        if m is not None:
            expected_closing = (
                row["opening_qty"] + row["intake_qty"]
                - row["repurpose_qty"] - row["export_qty"] - row["other_out_qty"]
            )
            row["balance_diff"] = expected_closing - row["closing_qty"]
            row["balance_match"] = _match(expected_closing, row["closing_qty"])
        else:
            row["balance_diff"] = 0.0
            row["balance_match"] = True
        out.append(row)
    return out


def bcct_lines_for_item(
    session: Session,
    company_id: int,
    item_code: str,
    year: int | None = None,
) -> list[DeclarationLine]:
    stmt = select(DeclarationLine).where(
        DeclarationLine.company_id == company_id,
        DeclarationLine.item_code == item_code,
    )
    if year is not None:
        stmt = stmt.where(DeclarationLine.period_year == year)
    stmt = stmt.order_by(
        DeclarationLine.declaration_date.is_(None),
        DeclarationLine.declaration_date,
        DeclarationLine.declaration_no,
    )
    return list(session.scalars(stmt).all())


def bom_edges_for_nvl(
    session: Session, company_id: int, material_code: str, year: int
) -> list[dict]:
    """NVL → các TP nó cấu thành (định mức năm đó)."""
    rows = session.scalars(
        select(Norm)
        .where(
            Norm.company_id == company_id,
            Norm.material_code == material_code,
            Norm.period_year == year,
        )
        .order_by(Norm.product_code)
    ).all()
    return [
        {
            "product_code": r.product_code,
            "product_name": r.product_name,
            "norm_qty": float(r.norm_qty or 0),
            "material_unit": r.material_unit,
            "product_unit": r.product_unit,
        }
        for r in rows
    ]


def bom_edges_for_tp(
    session: Session, company_id: int, product_code: str, year: int
) -> list[dict]:
    """TP → các NVL cấu thành (BOM năm đó)."""
    rows = session.scalars(
        select(Norm)
        .where(
            Norm.company_id == company_id,
            Norm.product_code == product_code,
            Norm.period_year == year,
        )
        .order_by(Norm.material_code)
    ).all()
    return [
        {
            "material_code": r.material_code,
            "material_name": r.material_name,
            "norm_qty": float(r.norm_qty or 0),
            "material_unit": r.material_unit,
            "product_unit": r.product_unit,
        }
        for r in rows
    ]
