"""Nhóm 1 — Số lượng nhập / xuất (§4.1 đề án).

Implement 6 MVP checks: C1.1, C1.2, C1.3, C1.4, C1.6, C1.7.
C1.5 (tái xuất M15 vs B13) là W.I.P theo §4.1 — chưa implement.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.checks.company_type import (
    PAIRING,
    CompanyType,
    Pairing,
    detect_company_type,
    mixed_book_pairings,
)
from app.checks.registry import Severity, severity_for
from app.checks.scope import declaration_scope
from app.checks.uom import normalize, resolve_canonical
from app.models import DeclarationLine, Finding, NvlBalance, SpBalance


def _evidence_nvl(material_code: str, year: int, company_id: int, book: str | None = None) -> list[dict]:
    f = {"company_id": company_id, "period_year": year, "material_code": material_code}
    if book is not None:
        f["book"] = book
    return [{"table": "nvl_balances", "filter": f}]


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
            declaration_scope(session, company_id, year),
            DeclarationLine.customs_code.in_(customs_codes),
            DeclarationLine.item_code.is_not(None),
        )
        .group_by(DeclarationLine.item_code)
    ).all()
    return {code: float(qty or 0.0) for code, qty in rows}


def _unit_key(session: Session, unit: str | None) -> str | None:
    """Khoá so khớp đơn vị: canonical nếu resolve được, không thì raw đã chuẩn hoá."""
    return resolve_canonical(session, unit) or normalize(unit)


def _sum_bcct_by_item_unit(
    session: Session,
    company_id: int,
    year: int,
    customs_codes: set[str],
) -> dict[tuple[str, str | None], float]:
    """Như _sum_bcct_by_item nhưng tách theo đơn vị đã chuẩn hoá."""
    if not customs_codes:
        return {}
    rows = session.execute(
        select(
            DeclarationLine.item_code,
            DeclarationLine.unit,
            func.coalesce(func.sum(DeclarationLine.quantity), 0.0),
        )
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.customs_code.in_(customs_codes),
            DeclarationLine.item_code.is_not(None),
        )
        .group_by(DeclarationLine.item_code, DeclarationLine.unit)
    ).all()
    out: dict[tuple[str, str | None], float] = {}
    for code, unit, qty in rows:
        key = (code, _unit_key(session, unit))
        out[key] = out.get(key, 0.0) + float(qty or 0.0)
    return out


def _unit_targets(
    code: str,
    slices: list[tuple[str | None, float]],
    sums_by_item: dict[str, float],
    sums_by_item_unit: dict[tuple[str, str | None], float],
) -> list[tuple[str | None, float, float]]:
    """Chọn lát đơn vị nào của một mã được đem đối chiếu với tờ khai.

    `slices` đã khoá theo đơn vị CHUẨN HOÁ, cùng hệ khoá với `sums_by_item_unit`.

    - Mã chỉ có MỘT đơn vị: giữ nguyên hành vi cũ (so với tổng tờ khai của mã).
    - Mã có NHIỀU đơn vị (cùng một lượng ghi lại ở đơn vị thứ hai): chỉ so lát nào
      khớp đơn vị tờ khai, so với tổng của chính đơn vị đó.
    - Nhiều đơn vị nhưng không lát nào khớp (gồm cả trường hợp không có tờ khai):
      báo MỘT lần bằng lát lớn nhất, so với tổng của mã.
    """
    if len(slices) == 1:
        unit, qty = slices[0]
        return [(unit, qty, sums_by_item.get(code, 0.0))]

    matched = [
        (unit, qty, sums_by_item_unit[(code, unit)])
        for unit, qty in slices
        if (code, unit) in sums_by_item_unit
    ]
    if matched:
        return matched

    unit, qty = max(slices, key=lambda s: s[1])
    return [(unit, qty, sums_by_item.get(code, 0.0))]


def _one_row_per_material(
    rows: list[NvlBalance],
    weight: Callable[[NvlBalance], float],
) -> list[NvlBalance]:
    """Gộp theo (sổ, mã), giữ dòng có `weight` lớn nhất, trả theo thứ tự (mã, sổ).

    Một mã ghi ở nhiều đơn vị là MỘT vật tư ghi lại, không phải nhiều vật tư — check
    emit theo dòng (C1.3/C1.6/C1.7) chỉ được ra một finding cho mỗi (sổ, mã).
    """
    best: dict[tuple[str | None, str], NvlBalance] = {}
    for r in rows:
        key = (r.book, r.material_code)
        cur = best.get(key)
        if cur is None or weight(r) > weight(cur):
            best[key] = r
    return [best[k] for k in sorted(best, key=lambda k: (k[1], k[0] is None, k[0] or ""))]


def _pct_diff(actual: float, expected: float) -> float:
    """Chênh lệch % so với `expected`. Trả 0 khi expected ≈ 0 và actual ≈ 0."""
    if abs(expected) < 1e-9:
        return 100.0 if abs(actual) > 1e-9 else 0.0
    return (actual - expected) / abs(expected) * 100.0


def _book_filter(model, book: str | None):
    return model.book.is_(None) if book is None else model.book == book


def _per_scope(
    session: Session,
    company_id: int,
    year: int,
    fn: Callable[..., list[Finding]],
    nvl: bool,
) -> list[Finding]:
    """Chạy `fn` một lượt cho cả pháp nhân, hoặc một lượt MỖI SỔ khi các sổ khác loại hình.

    `mixed_book_pairings` trả None cho pháp nhân một sổ và cho pháp nhân nhiều sổ
    cùng loại hình → đường cũ y nguyên, DN đang chạy không đổi kết quả. Chỉ pháp
    nhân giữ hai sổ KHÁC loại hình (SXXK + thuê gia công nước ngoài) mới tách,
    vì gộp lại thì cân đối sổ này bị đem so với tờ khai của sổ kia.
    """
    per_book = mixed_book_pairings(session, company_id, year)
    if per_book is None:
        company_type = detect_company_type(session, company_id, year)
        pairing = PAIRING.get(company_type)
        if pairing is None:
            return []
        return fn(session, company_id, year, None, False, company_type, pairing)

    findings: list[Finding] = []
    by_pairing = {p: t for t, p in PAIRING.items()}
    for book, pairing in per_book.items():
        findings += fn(
            session, company_id, year, book, True,
            by_pairing.get(pairing, CompanyType.UNKNOWN), pairing,
        )
    return findings


def check_c1_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """Lệch số lượng nhập NVL: |M15.import - Σ BCCT| / M15.import."""
    return _per_scope(session, company_id, year, _c1_1_scope, nvl=True)


def _c1_1_scope(
    session: Session, company_id: int, year: int,
    book: str | None, scoped: bool, company_type: CompanyType, pairing: Pairing,
) -> list[Finding]:
    import_codes = set(pairing.nvl_codes)
    if not import_codes:
        return []
    column = pairing.nvl_column

    bcct_sums = _sum_bcct_by_item(session, company_id, year, import_codes)
    q = select(NvlBalance).where(
        NvlBalance.company_id == company_id,
        NvlBalance.period_year == year,
    )
    if scoped:
        q = q.where(_book_filter(NvlBalance, book))
    rows = session.scalars(q).all()

    # Gộp import_qty theo (mã, đơn vị CHUẨN HOÁ): một mã có thể có NHIỀU dòng M15 khi
    # pháp nhân giữ nhiều sổ (đa loại hình) hoặc khai cùng mã ở hai đơn vị. Cộng across
    # sổ VÀ across các cách viết cùng một đơn vị ('MTR' với 'METRES'), KHÔNG cộng across
    # hai đơn vị khác nhau. Giữ đơn vị thô để báo cáo (truy nguồn về dòng biểu gốc).
    agg: dict[tuple[str, str | None], float] = {}
    display_unit: dict[tuple[str, str | None], str] = {}
    for r in rows:
        key = (r.material_code, _unit_key(session, r.unit))
        agg[key] = agg.get(key, 0.0) + getattr(r, column)
        display_unit.setdefault(key, r.unit)

    slices_by_code: dict[str, list[tuple[str | None, float]]] = {}
    for (code, unit), imported in agg.items():
        if imported <= 0:
            continue  # C1.1 chỉ áp với NVL có khai nhập trong M15
        slices_by_code.setdefault(code, []).append((unit, imported))

    # Chỉ cần tổng tách theo đơn vị khi có mã ghi ở nhiều hơn một đơn vị.
    bcct_by_unit = (
        _sum_bcct_by_item_unit(session, company_id, year, import_codes)
        if any(len(v) > 1 for v in slices_by_code.values())
        else {}
    )

    findings: list[Finding] = []
    for code in sorted(slices_by_code):
        targets = _unit_targets(
            code,
            sorted(slices_by_code[code], key=lambda s: (s[0] or "")),
            bcct_sums,
            bcct_by_unit,
        )
        for unit, imported, bcct_qty in targets:
            diff_pct = _pct_diff(bcct_qty, imported)
            if abs(diff_pct) < 0.5:
                continue  # floor 0.5% — coi như khớp (lọc nhiễu làm tròn).
            sev = severity_for("C1.1", abs(diff_pct))
            if sev is None:
                continue
            findings.append(Finding(
                company_id=company_id,
                period_year=year,
                check_code="C1.1",
                severity=sev.value,
                subject_type="material_code",
                subject_key=code,
                book=book if scoped else None,
                title=(
                    f"Lệch nhập NVL {code}: "
                    f"M15={imported:.2f} vs BCCT={bcct_qty:.2f} ({diff_pct:+.1f}%)"
                ),
                details={
                    "company_type": company_type.value,
                    "import_codes": sorted(import_codes),
                    "m15_column": column,
                    "unit": display_unit.get((code, unit)),
                    "m15_import": imported,
                    "bcct_sum": bcct_qty,
                    "diff_pct": diff_pct,
                },
                evidence_refs=_evidence_nvl(code, year, company_id, book if scoped else None)
                + _evidence_decl(code, year, company_id, import_codes),
            ))
    return findings


def check_c1_2(session: Session, company_id: int, year: int) -> list[Finding]:
    """Có tờ khai nhập nhưng không có dòng nào trong M15."""
    return _per_scope(session, company_id, year, _c1_2_scope, nvl=True)


def _c1_2_scope(
    session: Session, company_id: int, year: int,
    book: str | None, scoped: bool, company_type: CompanyType, pairing: Pairing,
) -> list[Finding]:
    import_codes = set(pairing.nvl_codes)
    if not import_codes:
        return []

    bcct_codes = set(
        session.scalars(
            select(DeclarationLine.item_code)
            .where(
                declaration_scope(session, company_id, year),
                DeclarationLine.customs_code.in_(import_codes),
                DeclarationLine.item_code.is_not(None),
            )
            .distinct()
        ).all()
    )
    # Mã "thiếu trong M15" phải so với M15 của MỌI sổ, kể cả khi đang chạy theo sổ:
    # mã nằm ở sổ khác thì không phải là thiếu, chỉ là thuộc sổ khác.
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
                declaration_scope(session, company_id, year),
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
    return _per_scope(session, company_id, year, _c1_3_scope, nvl=True)


def _c1_3_scope(
    session: Session, company_id: int, year: int,
    book: str | None, scoped: bool, company_type: CompanyType, pairing: Pairing,
) -> list[Finding]:
    import_codes = set(pairing.nvl_codes)
    if not import_codes:
        return []
    column = pairing.nvl_column

    bcct_codes = set(
        session.scalars(
            select(DeclarationLine.item_code)
            .where(
                declaration_scope(session, company_id, year),
                DeclarationLine.customs_code.in_(import_codes),
                DeclarationLine.item_code.is_not(None),
            )
            .distinct()
        ).all()
    )
    q = select(NvlBalance).where(
        NvlBalance.company_id == company_id,
        NvlBalance.period_year == year,
        getattr(NvlBalance, column) > 0,
    )
    if scoped:
        q = q.where(_book_filter(NvlBalance, book))
    m15_with_imports = session.scalars(q).all()

    findings: list[Finding] = []
    for r in _one_row_per_material(
        [r for r in m15_with_imports if r.material_code not in bcct_codes],
        lambda r: getattr(r, column),
    ):
        qty = getattr(r, column)
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.3",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            book=r.book,
            title=(
                f"M15 khai nhập NVL {r.material_code} "
                f"({qty:.2f} {r.unit or ''}) nhưng không có tờ khai"
            ),
            details={
                "company_type": company_type.value,
                "import_codes": sorted(import_codes),
                "m15_column": column,
                "m15_import": qty,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id, r.book),
        ))
    return findings


def check_c1_4(session: Session, company_id: int, year: int) -> list[Finding]:
    """Lệch số lượng xuất TP: |M15a.export - Σ BCCT export| / M15a.export."""
    return _per_scope(session, company_id, year, _c1_4_scope, nvl=False)


def _c1_4_scope(
    session: Session, company_id: int, year: int,
    book: str | None, scoped: bool, company_type: CompanyType, pairing: Pairing,
) -> list[Finding]:
    export_codes = set(pairing.sp_codes)
    if not export_codes:
        return []
    column = pairing.sp_column

    bcct_sums = _sum_bcct_by_item(session, company_id, year, export_codes)
    q = select(SpBalance).where(
        SpBalance.company_id == company_id,
        SpBalance.period_year == year,
    )
    if scoped:
        q = q.where(_book_filter(SpBalance, book))
    rows = session.scalars(q).all()

    # Gộp export_qty theo (mã, đơn vị CHUẨN HOÁ) — như C1.1.
    agg: dict[tuple[str, str | None], float] = {}
    display_unit: dict[tuple[str, str | None], str] = {}
    for r in rows:
        key = (r.product_code, _unit_key(session, r.unit))
        agg[key] = agg.get(key, 0.0) + getattr(r, column)
        display_unit.setdefault(key, r.unit)

    slices_by_code: dict[str, list[tuple[str | None, float]]] = {}
    for (code, unit), exported in agg.items():
        if exported <= 0:
            continue
        slices_by_code.setdefault(code, []).append((unit, exported))

    # Chỉ cần tổng tách theo đơn vị khi có mã ghi ở nhiều hơn một đơn vị.
    bcct_by_unit = (
        _sum_bcct_by_item_unit(session, company_id, year, export_codes)
        if any(len(v) > 1 for v in slices_by_code.values())
        else {}
    )

    findings: list[Finding] = []
    for code in sorted(slices_by_code):
        targets = _unit_targets(
            code,
            sorted(slices_by_code[code], key=lambda s: (s[0] or "")),
            bcct_sums,
            bcct_by_unit,
        )
        for unit, exported, bcct_qty in targets:
            diff_pct = _pct_diff(bcct_qty, exported)
            if abs(diff_pct) < 0.1:
                continue  # floor 0.1% — coi như khớp (lọc nhiễu làm tròn).
            sev = severity_for("C1.4", abs(diff_pct))
            if sev is None:
                continue
            findings.append(Finding(
                company_id=company_id,
                period_year=year,
                check_code="C1.4",
                severity=sev.value,
                subject_type="product_code",
                subject_key=code,
                book=book if scoped else None,
                title=(
                    f"Lệch xuất TP {code}: "
                    f"M15a={exported:.2f} vs BCCT={bcct_qty:.2f} ({diff_pct:+.1f}%)"
                ),
                details={
                    "company_type": company_type.value,
                    "export_codes": sorted(export_codes),
                    "m15a_column": column,
                    "unit": display_unit.get((code, unit)),
                    "m15a_export": exported,
                    "bcct_sum": bcct_qty,
                    "diff_pct": diff_pct,
                },
                evidence_refs=_evidence_sp(code, year, company_id)
                + _evidence_decl(code, year, company_id, export_codes),
            ))
    return findings


def check_c1_6(session: Session, company_id: int, year: int) -> list[Finding]:
    """M15.chuyển_mục_đích_sử_dụng > 0 nhưng không có tờ khai A42 tương ứng."""
    a42_codes = set(
        session.scalars(
            select(DeclarationLine.item_code)
            .where(
                declaration_scope(session, company_id, year),
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
    for r in _one_row_per_material(
        [r for r in rows if r.material_code not in a42_codes],
        lambda r: r.repurpose_qty,
    ):
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C1.6",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            book=r.book,
            title=(
                f"NVL {r.material_code} chuyển MĐSD {r.repurpose_qty:.2f} {r.unit or ''} "
                f"nhưng không có tờ khai A42"
            ),
            details={
                "m15_repurpose": r.repurpose_qty,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id, r.book),
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

    # Các lát đơn vị của cùng một mã tỉ lệ thuận nên cho cùng tỉ số; giữ lát có
    # mẫu số (tồn đầu + nhập) lớn nhất.
    def _denom(r: NvlBalance) -> float:
        return (r.opening_qty or 0.0) + (r.import_qty or 0.0)

    findings: list[Finding] = []
    for r in _one_row_per_material(
        [r for r in rows if _denom(r) > 0 and (r.repurpose_qty or 0.0) > 0],
        _denom,
    ):
        pct = r.repurpose_qty / _denom(r) * 100.0
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
            book=r.book,
            title=(
                f"NVL {r.material_code} chuyển MĐSD chiếm {pct:.1f}% "
                f"(tồn đầu + nhập trong kỳ)"
            ),
            details={
                "repurpose": r.repurpose_qty,
                "opening": r.opening_qty,
                "import": r.import_qty,
                "ratio_pct": pct,
            },
            evidence_refs=_evidence_nvl(r.material_code, year, company_id, r.book),
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
