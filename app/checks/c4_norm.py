"""Nhóm 4 — Định mức M16 (§4.1 đề án).

Đã dựng: C4.1, C4.3, C4.9. Còn lại (C4.2, C4.4-C4.8) là W.I.P.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.m16 import is_domestic_origin
from app.books import book_label
from app.checks.effective_norms import (
    consumed_materials,
    effective_norms,
    production_intake,
    products_without_norm,
)
from app.checks.norm_gate import is_boundary_period, norm_coverage_gate
from app.checks.not_evaluable import CheckResult
from app.checks.registry import Severity, severity_for
from app.checks.valuation import material_prices_vnd, money_value
from app.models import Finding, Norm, NvlBalance, SpBalance


def check_c4_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """NVL trong M16 không có nhập khẩu và không có tồn đầu kỳ.

    Fire khi: mã NVL có trong M16 nhưng
      (a) không có dòng trong M15, hoặc
      (b) có dòng nhưng `import_qty = 0` VÀ `opening_qty = 0`.

    Loại trừ NVL xuất xứ trong nước (Ghi chú M16 = "x"): hàng nội địa không có
    tờ khai nhập nên không đối chiếu nguồn nhập khẩu (góp ý nghiệp vụ 2026-05-29).

    Phạm vi là HỢP của hai tập: (a) mã khai định mức ĐÚNG kỳ này, (b) mã có tiêu hao
    lý thuyết > 0 trong kỳ theo định mức HIỆU LỰC, kể cả bản khai kỳ trước. Thiếu (b)
    thì mã có định mức kế thừa mà không có dòng M15 không check nào báo: C4.3 đã
    nhường lại cho C4.1 (issue #59) còn C4.1 lọc đúng kỳ nên không thấy. Đo trên
    pilot 06/08/2026: 196 mã rơi vào khoảng hở đó (188 ở DN 8/2025, 8 ở DN 10/2026).
    """
    code_notes = session.execute(
        select(Norm.material_code, Norm.note, Norm.book).where(
            Norm.company_id == company_id,
            Norm.period_year == year,
        ).distinct()
    ).all()
    consumed = consumed_materials(session, company_id, year)

    m15_all = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    # Gộp theo SỔ (book): mỗi sổ quyết toán là ledger riêng — mã M16 của một sổ phải có
    # nguồn M15 TRONG CÙNG SỔ, không được dòng M15 sổ khác che (xem ADR #19). book=None
    # (pháp nhân một sổ) là một nhóm → hành vi cũ không đổi.
    notes_by_book: dict[str | None, list[tuple[str, str | None]]] = defaultdict(list)
    for code, note, book in code_notes:
        notes_by_book[book].append((code, note))
    for book, codes in consumed.items():
        for code, use in codes.items():
            notes_by_book[book].append((code, use.note))
    m15_by_book: dict[str | None, dict[str, NvlBalance]] = defaultdict(dict)
    for r in m15_all:
        m15_by_book[r.book][r.material_code] = r

    same_year_codes = {(book, code) for code, _, book in code_notes}

    findings: list[Finding] = []
    for book in sorted(notes_by_book, key=lambda b: (b is None, b or "")):
        domestic = {code for code, note in notes_by_book[book] if is_domestic_origin(note)}
        m16_codes = {code for code, _ in notes_by_book[book]} - domestic
        m15_rows = m15_by_book.get(book, {})
        for code in sorted(m16_codes):
            m15 = m15_rows.get(code)
            if m15 is None:
                reason = "no_m15"
            elif (m15.import_qty or 0.0) == 0 and (m15.opening_qty or 0.0) == 0:
                reason = "zero_source"
            else:
                continue

            # Mã chỉ vào phạm vi qua đường định mức kế thừa thì kỳ này KHÔNG có dòng
            # norms nào — chứng cứ phải trỏ về kỳ đã khai, nếu không mở ra là bảng rỗng.
            if (book, code) in same_year_codes:
                norm_years = [year]
            else:
                norm_years = list(consumed.get(book, {})[code].source_years)
            norm_filter = {
                "company_id": company_id,
                "period_year__in": norm_years,
                "material_code": code,
            }
            nvl_filter = {"company_id": company_id, "period_year": year, "material_code": code}
            if book is not None:
                norm_filter["book"] = book
                nvl_filter["book"] = book

            findings.append(Finding(
                company_id=company_id,
                period_year=year,
                check_code="C4.1",
                severity=Severity.CRITICAL.value,
                subject_type="material_code",
                subject_key=code,
                book=book,
                title=(
                    f"NVL {code} trong M16 không có nguồn"
                    + (" (không có dòng M15)" if reason == "no_m15" else " (M15.nhập=0 và tồn_đầu=0)")
                ),
                details={
                    "reason": reason,
                    "m15_import": m15.import_qty if m15 else None,
                    "m15_opening": m15.opening_qty if m15 else None,
                    "norm_source_years": norm_years,
                },
                evidence_refs=[
                    {"table": "norms", "filter": norm_filter},
                ] + ([{"table": "nvl_balances", "filter": nvl_filter}] if m15 else []),
            ))
    return findings


def check_c4_3(session: Session, company_id: int, year: int) -> CheckResult:
    """Σ(định_mức × sản_lượng_sản_xuất_M15a) theo NVL > xuất_sản_xuất_M15.

    Tiêu hao lý thuyết = Σ qua các TP: norm(M16) × intake_qty(M15a) — intake_qty là
    lượng SP sản xuất nhập kho trong kỳ (Mẫu 15a), KHÔNG phải lượng xuất khẩu (P-07,
    ../audit-hq/.ai/DECISIONS.md 2026-07-24): cặp so sánh phải cùng biến cố sản xuất,
    dùng xuất khẩu tạo sai số đúng bằng biến động tồn thành phẩm.
    Tiêu hao thực tế = production_out_qty trong M15 cùng mã NVL.
    Ngưỡng: vượt >5% Cảnh báo · >20% Nghiêm trọng (đề án §4.1).

    Bỏ qua mã NVL không có DÒNG M15 nào trong sổ đang xét (issue #59): đó là ca thiếu
    nguồn, C4.1 đã bắt. Mã CÓ dòng M15 mà xuất SX = 0 vẫn fire — đã khai nguồn nhưng
    không xuất cho sản xuất là mâu thuẫn thật.

    Định mức lấy theo bản khai HIỆU LỰC (issue #60) — bản khai có kỳ lớn nhất ≤
    `year` của CHÍNH mã TP đó, lấy trọn bản khai, vì Mẫu 16 kế thừa giữa các kỳ.
    Lọc đúng `period_year == year` làm mất định mức của mọi mã không khai lại.

    Trả `NotEvaluable` thay cho danh sách phát hiện khi (DN, kỳ) vướng cổng độ phủ
    định mức (issue #62): thiếu định mức của một thành phẩm đã sản xuất, hoặc kỳ
    biên chưa xác nhận năm đầu nộp BCQT — xem `app.checks.norm_gate`. Cổng chặn CẢ
    lần chạy kể cả khi chỉ một sổ vướng, vì `check_runs` khoá theo (DN, kỳ).
    """
    gated = norm_coverage_gate(session, company_id, year)
    if gated is not None:
        return gated

    # Không khoanh loại hình: C4.3 nói về NVL đã tiêu hao, không riêng NVL nhập kỳ này —
    # mã có định mức kế thừa có thể chỉ có tờ khai ở kỳ trước trong cùng cửa sổ.
    prices = material_prices_vnd(session, company_id, year)
    norms_by_book = effective_norms(session, company_id, year)
    sp_rows = session.execute(
        select(SpBalance.product_code, SpBalance.intake_qty, SpBalance.book).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
        )
    ).all()
    nvl_rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    # Gộp theo SỔ (book): mỗi sổ quyết toán là ledger riêng — định mức, sản lượng sản
    # xuất và xuất SX của một sổ chỉ đối chiếu TRONG sổ đó, không cộng chéo (ADR #19).
    # book=None (pháp nhân một sổ) là một nhóm → hành vi cũ không đổi.
    sp_by_book: dict[str | None, dict[str, float]] = defaultdict(dict)
    for product_code, intake_qty, book in sp_rows:
        sp_by_book[book][product_code] = intake_qty
    m15_by_book: dict[str | None, dict[str, NvlBalance]] = defaultdict(dict)
    for r in nvl_rows:
        m15_by_book[r.book][r.material_code] = r

    findings: list[Finding] = []
    for book in sorted(norms_by_book, key=lambda b: (b is None, b or "")):
        sp_output = sp_by_book.get(book, {})

        # Mẫu 16 của một số DN lặp lại NGUYÊN KHỐI định mức cho mỗi đợt sản xuất: cùng
        # (mã SP, mã NVL) xuất hiện tới 26 lần, thường cùng một giá trị. Catalog định
        # nghĩa tiêu hao = Σ(định_mức × sản_lượng_sản_xuất) theo mã NVL — mỗi cặp tính
        # MỘT lần. Cộng dồn qua từng DÒNG là nhân số lần lặp vào tiêu hao lý thuyết.
        # `effective_norms` đã gộp về một giá trị mỗi cặp (MAX khi các khối lệch nhau).
        #
        # LƯU Ý cho bố cục Mẫu 16 mở rộng (có cột sản lượng theo khối): ở đó các khối
        # lặp là những ĐỢT SẢN XUẤT khác nhau và phải tính Σ(định_mức_khối × sản_lượng
        # _khối), gộp lại sẽ nuốt mất sản lượng. `Norm` chưa có cột sản lượng nên đường
        # đó chưa dựng được — khi thêm, rẽ nhánh tại đây.
        divergent: dict[str, set[str]] = defaultdict(set)
        theoretical: dict[str, float] = defaultdict(float)
        # Kỳ nguồn của các định mức đã dùng, theo mã NVL — định mức kế thừa nằm ở kỳ
        # KHÁC kỳ phát hiện, nên chứng cứ phải trỏ đúng kỳ đã khai (đề án §5.1).
        norm_years: dict[str, set[int]] = defaultdict(set)
        for (product_code, material_code), norm in norms_by_book[book].items():
            sp_qty = sp_output.get(product_code) or 0.0
            if sp_qty <= 0:
                continue
            theoretical[material_code] += norm.norm_qty * sp_qty
            norm_years[material_code].add(norm.source_year)
            if norm.divergent:
                divergent[material_code].add(product_code)

        m15_rows = m15_by_book.get(book, {})
        for code, theor in theoretical.items():
            if theor <= 0:
                continue
            m15 = m15_rows.get(code)
            if m15 is None:
                # Không có DÒNG M15 nào cho mã này trong sổ đang xét → ca thiếu nguồn,
                # đất của C4.1. Coi như xuất SX = 0 rồi bắn Nghiêm trọng là dán nhầm
                # nhãn: chênh lệch định mức chỉ có nghĩa khi mã có mặt trong M15.
                continue
            actual = m15.production_out_qty or 0.0
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
            years_used = sorted(norm_years.get(code, {year}))
            norm_filter = {
                "company_id": company_id,
                "period_year__in": years_used,
                "material_code": code,
            }
            nvl_filter = {"company_id": company_id, "period_year": year, "material_code": code}
            if book is not None:
                norm_filter["book"] = book
                nvl_filter["book"] = book
            value_vnd = money_value(prices, code, theor - actual)
            findings.append(Finding(
                company_id=company_id,
                period_year=year,
                check_code="C4.3",
                severity=sev.value,
                subject_type="material_code",
                subject_key=code,
                book=book,
                value_vnd=value_vnd,
                title=(
                    f"NVL {code}: tiêu hao lý thuyết M16 ({theor:.2f}) vượt "
                    f"xuất SX M15 ({actual:.2f}) — chênh +{pct:.1f}%"
                ),
                details={
                    "theoretical_consumption": theor,
                    "actual_m15_production_out": actual,
                    "diff_pct": pct,
                    "value_vnd": value_vnd,
                    # Mã SP mà các khối định mức lặp lại KHÔNG khớp nhau — đã lấy MAX.
                    "divergent_norm_products": sorted(divergent.get(code, ())),
                    # Kỳ của các bản khai Mẫu 16 đã dùng. Khác `period_year` nghĩa là
                    # định mức kế thừa từ kỳ trước, DN không khai lại (issue #60).
                    "norm_source_years": years_used,
                },
                evidence_refs=[
                    {"table": "norms", "filter": norm_filter},
                    {"table": "nvl_balances", "filter": nvl_filter},
                ],
            ))
    return findings


def check_c4_9(session: Session, company_id: int, year: int) -> list[Finding]:
    """TP có sản xuất trong kỳ nhưng thiếu định mức M16 (issue #61).

    Fire khi: mã TP có `intake_qty` > 0 trên M15a (sản lượng sản xuất nhập kho)
    mà không có định mức HIỆU LỰC nào trong M16 — kể cả bản khai của các kỳ trước
    (quy tắc kế thừa ở `effective_norms`, issue #60). Một phát hiện MỖI MÃ: cán bộ
    cần danh sách từng mã thiếu định mức, không phải một con số tổng.

    Chiều ngược của C4.2 (M16 → M15a): ở đây đi từ M15a sang M16.

    Gộp theo SỔ quyết toán: định mức khai ở sổ này không phủ sản lượng sản xuất
    của sổ kia (ADR #19). Nhưng nếu mã CÓ định mức ở sổ khác thì nói đúng như vậy,
    không nói "thiếu định mức": hồ sơ có tồn tại, câu hỏi là Mẫu 16 đã nộp vào sổ
    nào. Nói thiếu sẽ đẩy cán bộ đi đòi doanh nghiệp một file đã nộp rồi.

    KHÁC C4.3: ở kỳ biên (kỳ sớm nhất đang giữ, chưa xác nhận năm đầu nộp BCQT)
    C4.3 dừng hẳn, còn C4.9 VẪN liệt kê — danh sách từng mã là thứ cán bộ cần —
    nhưng gắn cờ `boundary_period` để không kết luận doanh nghiệp chưa khai khi có
    thể họ đã khai trước cửa sổ dữ liệu đang có (issue #61 × #62, quyết định Q1).
    """
    missing = products_without_norm(session, company_id, year)
    intake = production_intake(session, company_id, year)
    norms = effective_norms(session, company_id, year)
    boundary = is_boundary_period(session, company_id, year)

    # {mã TP: các sổ KHÁC có khai định mức cho mã đó}
    books_with_norm: dict[str, set[str | None]] = defaultdict(set)
    for book, pairs in norms.items():
        for product_code, _material_code in pairs:
            books_with_norm[product_code].add(book)

    findings: list[Finding] = []
    for book in sorted(missing, key=lambda b: (b is None, b or "")):
        for code in sorted(missing[book]):
            qty = intake.get(book, {}).get(code, 0.0)
            other_books = sorted(
                (b for b in books_with_norm.get(code, ()) if b != book),
                key=lambda b: (b is None, b or ""),
            )
            sp_filter = {"company_id": company_id, "period_year": year, "product_code": code}
            if book is not None:
                sp_filter["book"] = book
            findings.append(Finding(
                company_id=company_id,
                period_year=year,
                check_code="C4.9",
                severity=Severity.WARNING.value,
                subject_type="product_code",
                subject_key=code,
                book=book,
                title=(
                    f"TP {code}: sản xuất nhập kho {qty:.2f} trong kỳ "
                    + (
                        "nhưng định mức M16 khai ở "
                        + ", ".join(book_label(b) for b in other_books)
                        if other_books
                        else "nhưng không có định mức M16 hiệu lực"
                    )
                ),
                details={
                    "intake": qty,
                    "norm_in_other_book": [book_label(b) for b in other_books],
                    "boundary_period": boundary,
                },
                # Trỏ về `norms` CHỈ KHI định mức nằm ở sổ khác — có dòng để mở ra.
                # Ca thiếu hẳn thì chứng cứ là dòng M15a khai sản lượng: chính việc
                # KHÔNG có dòng norms nào cho mã này là nội dung phát hiện.
                evidence_refs=(
                    [{"table": "sp_balances", "filter": sp_filter}]
                    + ([{
                        "table": "norms",
                        "filter": {"company_id": company_id, "product_code": code},
                    }] if other_books else [])
                ),
            ))
    return findings


CHECKS = {
    "C4.1": check_c4_1,
    "C4.3": check_c4_3,
    "C4.9": check_c4_9,
}
