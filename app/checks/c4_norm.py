"""Nhóm 4 — Định mức M16 (§4.1 đề án).

MVP tuần 5: C4.1 + C4.3. Còn lại (C4.2, C4.4-C4.8) là W.I.P.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.m16 import is_domestic_origin
from app.checks.registry import Severity, severity_for
from app.models import Finding, Norm, NvlBalance, SpBalance


def check_c4_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """NVL trong M16 không có nhập khẩu và không có tồn đầu kỳ.

    Fire khi: mã NVL có trong M16 nhưng
      (a) không có dòng trong M15, hoặc
      (b) có dòng nhưng `import_qty = 0` VÀ `opening_qty = 0`.

    Loại trừ NVL xuất xứ trong nước (Ghi chú M16 = "x"): hàng nội địa không có
    tờ khai nhập nên không đối chiếu nguồn nhập khẩu (góp ý nghiệp vụ 2026-05-29).
    """
    code_notes = session.execute(
        select(Norm.material_code, Norm.note).where(
            Norm.company_id == company_id,
            Norm.period_year == year,
        ).distinct()
    ).all()
    domestic = {code for code, note in code_notes if is_domestic_origin(note)}
    m16_codes = {code for code, _ in code_notes} - domestic

    m15_rows = {
        r.material_code: r
        for r in session.scalars(
            select(NvlBalance).where(
                NvlBalance.company_id == company_id,
                NvlBalance.period_year == year,
            )
        ).all()
    }

    findings: list[Finding] = []
    for code in sorted(m16_codes):
        m15 = m15_rows.get(code)
        if m15 is None:
            reason = "no_m15"
        elif (m15.import_qty or 0.0) == 0 and (m15.opening_qty or 0.0) == 0:
            reason = "zero_source"
        else:
            continue

        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C4.1",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=code,
            title=(
                f"NVL {code} trong M16 không có nguồn"
                + (" (không có dòng M15)" if reason == "no_m15" else " (M15.nhập=0 và tồn_đầu=0)")
            ),
            details={
                "reason": reason,
                "m15_import": m15.import_qty if m15 else None,
                "m15_opening": m15.opening_qty if m15 else None,
            },
            evidence_refs=[
                {
                    "table": "norms",
                    "filter": {
                        "company_id": company_id,
                        "period_year": year,
                        "material_code": code,
                    },
                },
            ] + ([{
                "table": "nvl_balances",
                "filter": {
                    "company_id": company_id,
                    "period_year": year,
                    "material_code": code,
                },
            }] if m15 else []),
        ))
    return findings


def check_c4_3(session: Session, company_id: int, year: int) -> list[Finding]:
    """Σ(định_mức × xuất_khẩu_M15a) theo NVL > xuất_sản_xuất_M15.

    Tiêu hao lý thuyết = Σ qua các TP: norm(M16) × export_qty(M15a).
    Tiêu hao thực tế = production_out_qty trong M15 cùng mã NVL.
    Ngưỡng: vượt >5% Cảnh báo · >20% Nghiêm trọng (đề án §4.1).
    """
    # Map product_code → export_qty (M15a)
    sp_export = dict(session.execute(
        select(SpBalance.product_code, SpBalance.export_qty).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
        )
    ).all())

    # Map material_code → theoretical consumption
    theoretical: dict[str, float] = defaultdict(float)
    norms = session.scalars(
        select(Norm).where(
            Norm.company_id == company_id,
            Norm.period_year == year,
        )
    ).all()
    # Mẫu 16 của một số DN lặp lại NGUYÊN KHỐI định mức cho mỗi đợt sản xuất: cùng
    # (mã SP, mã NVL) xuất hiện tới 26 lần, thường cùng một giá trị. Catalog định
    # nghĩa tiêu hao = Σ(định_mức × xuất_khẩu) theo mã NVL — mỗi cặp tính MỘT lần.
    # Cộng dồn qua từng DÒNG là nhân số lần lặp vào tiêu hao lý thuyết.
    #
    # LƯU Ý cho bố cục Mẫu 16 mở rộng (có cột sản lượng theo khối): ở đó các khối
    # lặp là những ĐỢT SẢN XUẤT khác nhau và phải tính Σ(định_mức_khối × sản_lượng
    # _khối), gộp lại sẽ nuốt mất sản lượng. `Norm` chưa có cột sản lượng nên đường
    # đó chưa dựng được — khi thêm, rẽ nhánh tại đây.
    bom: dict[tuple[str, str], float] = {}
    divergent: dict[str, set[str]] = defaultdict(set)
    for n in norms:
        key = (n.product_code, n.material_code)
        qty = n.norm_qty or 0.0
        prev = bom.get(key)
        if prev is None:
            bom[key] = qty
        elif abs(prev - qty) > 1e-9:
            # Khối lặp lệch định mức — lấy MAX, nhưng ghi lại để hiện ra trong
            # phát hiện thay vì chọn thầm.
            bom[key] = max(prev, qty)
            divergent[n.material_code].add(n.product_code)

    for (product_code, material_code), norm_qty in bom.items():
        sp_qty = sp_export.get(product_code) or 0.0
        if sp_qty <= 0:
            continue
        theoretical[material_code] += norm_qty * sp_qty

    # Compare against M15.production_out_qty
    m15_rows = {
        r.material_code: r
        for r in session.scalars(
            select(NvlBalance).where(
                NvlBalance.company_id == company_id,
                NvlBalance.period_year == year,
            )
        ).all()
    }

    findings: list[Finding] = []
    for code, theor in theoretical.items():
        if theor <= 0:
            continue
        m15 = m15_rows.get(code)
        actual = (m15.production_out_qty or 0.0) if m15 else 0.0
        if actual <= 0:
            # Có tiêu hao lý thuyết nhưng M15 không có xuất SX → mâu thuẫn (nặng).
            pct = 100.0
        else:
            pct = (theor - actual) / actual * 100.0
        if pct <= 5.0:
            continue
        sev = severity_for("C4.3", pct)
        if sev is None:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C4.3",
            severity=sev.value,
            subject_type="material_code",
            subject_key=code,
            title=(
                f"NVL {code}: tiêu hao lý thuyết M16 ({theor:.2f}) vượt "
                f"xuất SX M15 ({actual:.2f}) — chênh +{pct:.1f}%"
            ),
            details={
                "theoretical_consumption": theor,
                "actual_m15_production_out": actual,
                "diff_pct": pct,
                # Mã SP mà các khối định mức lặp lại KHÔNG khớp nhau — đã lấy MAX.
                "divergent_norm_products": sorted(divergent.get(code, ())),
            },
            evidence_refs=[
                {
                    "table": "norms",
                    "filter": {
                        "company_id": company_id,
                        "period_year": year,
                        "material_code": code,
                    },
                },
                {
                    "table": "nvl_balances",
                    "filter": {
                        "company_id": company_id,
                        "period_year": year,
                        "material_code": code,
                    },
                },
            ],
        ))
    return findings


CHECKS = {
    "C4.1": check_c4_1,
    "C4.3": check_c4_3,
}
