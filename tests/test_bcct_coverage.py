"""BCCT-2 (#48, ADR #23 T1) — ingest lưu TRỌN dòng BCCT; ba cảnh báo thay drop.

Dòng ngoài cửa sổ kỳ không còn bị bỏ lúc nạp: lưu dưới nhãn nạp, đếm để BÁO.
Ba số: ngoài cửa sổ · không có ngày · trùng khoá chéo nhãn.
"""

from __future__ import annotations

from datetime import date

from app.models import CompanyPeriod, DeclarationLine
from app.pipeline.coverage import bcct_coverage
from tests.conftest import AppDb, add_decl


def set_period(session, company_id: int, year: int, pf: date, pt: date) -> None:
    session.add(
        CompanyPeriod(
            company_id=company_id, period_year=year,
            period_from=pf, period_to=pt, is_manual=True,
        )
    )
    session.commit()


def add_raw(session, company_id: int, *, year: int, no: str, line_no: int | None,
            item_code: str, day: date | None) -> DeclarationLine:
    row = DeclarationLine(
        company_id=company_id, period_year=year, declaration_no=no,
        declaration_date=day, customs_code="E31", line_no=line_no,
        item_code=item_code, quantity=1.0, unit="PCE",
    )
    session.add(row)
    return row


# --- Ba số của banner ---------------------------------------------------------


def test_clean_period_has_no_warning(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=10, year=2025, declaration_date=date(2025, 6, 1))
    session.commit()
    cov = bcct_coverage(session, company.id, 2025)
    assert (cov.out_of_window, cov.undated, cov.cross_label_duplicates) == (0, 0, 0)
    assert cov.has_warning is False
    assert cov.in_scope == 1


def test_counts_rows_labelled_here_but_dated_outside_window(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_raw(session, company.id, year=2025, no="1", line_no=1, item_code="A",
            day=date(2025, 6, 1))
    add_raw(session, company.id, year=2025, no="2", line_no=1, item_code="B",
            day=date(2025, 1, 5))
    session.commit()
    cov = bcct_coverage(session, company.id, 2025)
    assert cov.out_of_window == 1
    assert cov.in_scope == 1
    assert cov.has_warning is True


def test_counts_undated_rows(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_raw(session, company.id, year=2025, no="1", line_no=1, item_code="A", day=None)
    session.commit()
    cov = bcct_coverage(session, company.id, 2025)
    assert cov.undated == 1
    assert cov.in_scope == 1  # không ngày → quy theo nhãn, vẫn thuộc kỳ
    assert cov.has_warning is True


def test_counts_cross_label_duplicate_by_declaration_and_line(session, company):
    """Đếm DÒNG (không phải khoá): cả hai bản đều nằm trong kỳ và đều cộng vào tổng."""
    set_period(session, company.id, 2025, date(2025, 1, 1), date(2025, 12, 31))
    set_period(session, company.id, 2026, date(2026, 1, 1), date(2026, 12, 31))
    add_raw(session, company.id, year=2025, no="9001", line_no=1, item_code="A",
            day=date(2025, 6, 1))
    # Cùng (số tờ khai, dòng) ở nhãn kỳ khác — hai bản export chồng nhau.
    add_raw(session, company.id, year=2026, no="9001", line_no=1, item_code="A",
            day=date(2025, 6, 1))
    session.commit()
    cov = bcct_coverage(session, company.id, 2025)
    assert cov.cross_label_duplicates == 2
    assert cov.has_warning is True
    # Không dedup: cả hai dòng còn nguyên trong DB.
    assert session.query(DeclarationLine).count() == 2
    # Kỳ 2026 không có dòng nào (cả hai đều mang ngày 06/2025).
    assert bcct_coverage(session, company.id, 2026).cross_label_duplicates == 0


def test_cross_label_duplicate_falls_back_to_item_code_when_line_no_null(session, company):
    set_period(session, company.id, 2025, date(2025, 1, 1), date(2025, 12, 31))
    add_raw(session, company.id, year=2025, no="9001", line_no=None, item_code="A",
            day=date(2025, 6, 1))
    add_raw(session, company.id, year=2024, no="9001", line_no=None, item_code="A",
            day=date(2025, 6, 1))
    # Cùng số tờ khai nhưng KHÁC mã hàng → không phải bản trùng.
    add_raw(session, company.id, year=2024, no="9002", line_no=None, item_code="B",
            day=date(2025, 6, 1))
    add_raw(session, company.id, year=2025, no="9002", line_no=None, item_code="C",
            day=date(2025, 6, 1))
    session.commit()
    cov = bcct_coverage(session, company.id, 2025)
    assert cov.in_scope == 4
    assert cov.cross_label_duplicates == 2


def test_same_label_duplicate_is_not_cross_label(session, company):
    set_period(session, company.id, 2025, date(2025, 1, 1), date(2025, 12, 31))
    add_raw(session, company.id, year=2025, no="9001", line_no=1, item_code="A",
            day=date(2025, 6, 1))
    add_raw(session, company.id, year=2025, no="9001", line_no=1, item_code="A",
            day=date(2025, 6, 1))
    session.commit()
    assert bcct_coverage(session, company.id, 2025).cross_label_duplicates == 0


def test_coverage_never_counts_other_companies(session, company):
    from app.models import Company

    other = Company(code="OTHER_DN", tax_id="8888888888", name="DN khác", address="Hà Nội")
    session.add(other)
    session.commit()
    set_period(session, company.id, 2025, date(2025, 1, 1), date(2025, 12, 31))
    add_raw(session, other.id, year=2024, no="9001", line_no=1, item_code="A",
            day=date(2024, 6, 1))
    add_raw(session, company.id, year=2025, no="9001", line_no=1, item_code="A",
            day=date(2025, 6, 1))
    session.commit()
    cov = bcct_coverage(session, company.id, 2025)
    assert cov.cross_label_duplicates == 0
    assert cov.out_of_window == 0


# --- Ingest lưu trọn ----------------------------------------------------------


def test_ingest_stores_rows_dated_outside_the_period_window(app_db: AppDb, tmp_path):
    """Dòng ngoài cửa sổ KHÔNG bị bỏ nữa: lưu dưới nhãn nạp, đếm để báo."""
    from sqlalchemy import select

    from app.models import Company
    from app.pipeline.ingest import ingest
    from tests.test_ingest_book import _write_bcct, _write_m15

    base = tmp_path / "DN_WIN" / "2024"
    _write_m15(base / "BCQT" / "NVL.xlsx", ["A"])
    # Hai dòng: 15/06/2024 trong kỳ dương lịch 2024, 20/02/2025 ngoài kỳ.
    _write_bcct(
        base / "HANG_CHI_TIET" / "BCCT.xlsx", ["A", "B"],
        dates=[date(2024, 6, 15), date(2025, 2, 20)],
    )

    stats = ingest("DN_WIN", 2024, raw_root=tmp_path)

    assert stats.bcct_rows == 2                # LƯU cả hai
    assert stats.bcct_out_of_window == 1       # báo một dòng ngoài cửa sổ
    assert stats.bcct_undated == 0

    with app_db.SessionLocal() as db:
        c = db.scalar(select(Company).where(Company.code == "DN_WIN"))
        rows = db.scalars(
            select(DeclarationLine).where(DeclarationLine.company_id == c.id)
        ).all()
        assert len(rows) == 2
        assert {r.period_year for r in rows} == {2024}   # cùng nhãn nạp
        assert bcct_coverage(db, c.id, 2024).out_of_window == 1
        # Dòng ngoài cửa sổ không thuộc kỳ 2024 lúc query.
        assert bcct_coverage(db, c.id, 2024).in_scope == 1


def test_reingest_is_still_idempotent_after_storing_everything(app_db: AppDb, tmp_path):
    from sqlalchemy import func, select

    from app.models import Company
    from app.pipeline.ingest import ingest
    from tests.test_ingest_book import _write_bcct, _write_m15

    base = tmp_path / "DN_IDEM" / "2024"
    _write_m15(base / "BCQT" / "NVL.xlsx", ["A"])
    _write_bcct(
        base / "HANG_CHI_TIET" / "BCCT.xlsx", ["A", "B"],
        dates=[date(2024, 6, 15), date(2025, 2, 20)],
    )

    ingest("DN_IDEM", 2024, raw_root=tmp_path)
    ingest("DN_IDEM", 2024, raw_root=tmp_path)

    with app_db.SessionLocal() as db:
        c = db.scalar(select(Company).where(Company.code == "DN_IDEM"))
        n = db.scalar(
            select(func.count()).select_from(DeclarationLine).where(
                DeclarationLine.company_id == c.id
            )
        )
        assert n == 2
