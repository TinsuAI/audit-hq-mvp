"""TQ-3 (ADR #21 mục 1-2, 8) — bảng số liệu TÍNH ĐƯỢC của tổng quan.

Số học trên fixture: tập trung, phân vị, chiều lệch, so kỳ trước. Nửa này phải
đúng độc lập với LLM — nó là thứ đi vào báo cáo khách.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.overview_stats import build_stats
from app.database import Base
from app.models import Company, Finding, NvlBalance


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as s:
        yield s
    engine.dispose()


@pytest.fixture
def company(db):
    c = Company(code="DN_S", slug="dn-s", name="Stats Co", tax_id="1")
    db.add(c)
    db.commit()
    return c


def _f(company, *, year=2025, code="C1.1", sev="critical", subject="M1",
       details=None, book=None):
    return Finding(
        company_id=company.id, period_year=year, check_code=code, severity=sev,
        subject_key=subject, title=f"{code} {subject}", details=details or {}, book=book,
    )


# ───────────────────────── tổng + mức ─────────────────────────

def test_totals_by_severity(db, company):
    db.add_all([
        _f(company, sev="critical", subject="A"),
        _f(company, sev="critical", subject="B"),
        _f(company, sev="warning", subject="C"),
        _f(company, sev="info", subject="D"),
    ])
    db.commit()
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.1")
    assert st["total_findings"] == 4
    assert st["severity_totals"] == {"critical": 2, "warning": 1, "info": 1}


def test_empty_check_does_not_crash(db, company):
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.1")
    assert st["total_findings"] == 0
    assert st["concentration"]["distinct_subjects"] == 0
    assert st["concentration"]["top5_share_pct"] == 0.0
    assert st["numeric_fields"] == []


# ───────────────────────── tập trung ─────────────────────────

def test_concentration_top5_share_and_80pct_coverage(db, company):
    # 10 phát hiện: A=5, B=2, C=1, D=1, E=1, F=1 → 11 dòng trên 6 mã.
    plan = {"A": 5, "B": 2, "C": 1, "D": 1, "E": 1, "F": 1}
    for key, n in plan.items():
        db.add_all([_f(company, subject=key) for _ in range(n)])
    db.commit()
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.1")
    conc = st["concentration"]
    assert conc["distinct_subjects"] == 6
    # 5 mã lớn nhất = 5+2+1+1+1 = 10 trên tổng 11.
    assert conc["top5_share_pct"] == pytest.approx(90.9, abs=0.1)
    # Cộng dồn 5 → 7 → 8 → 9; tới mã thứ TƯ mới vượt 80% của 11 (8.8).
    assert conc["subjects_covering_80pct"] == 4
    assert conc["top_subjects"][0] == {"subject_key": "A", "count": 5}


def test_single_subject_covers_everything(db, company):
    db.add_all([_f(company, subject="A") for _ in range(3)])
    db.commit()
    conc = build_stats(
        db, company_id=company.id, period_year=2025, check_code="C1.1"
    )["concentration"]
    assert conc["distinct_subjects"] == 1
    assert conc["top5_share_pct"] == 100.0
    assert conc["subjects_covering_80pct"] == 1


# ───────────────────────── phân vị + chiều lệch ─────────────────────────

def test_percentiles_and_direction(db, company):
    values = [-30.0, -10.0, 0.0, 5.0, 20.0, 40.0, 60.0, 80.0, 90.0, 100.0]
    db.add_all([
        _f(company, subject=f"M{i}", details={"diff_pct": v})
        for i, v in enumerate(values)
    ])
    db.commit()
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.1")
    nf = st["numeric_fields"][0]
    assert nf["key"] == "diff_pct"
    assert nf["is_pct"] is True
    assert nf["n"] == 10
    assert nf["min"] == -30.0
    assert nf["max"] == 100.0
    assert nf["p50"] == 20.0    # hạng gần nhất: index round(0.5*9)=4 (đã sort)
    assert nf["p90"] == 90.0    # index round(0.9*9)=8
    # >0: 5, 20, 40, 60, 80, 90, 100 = 7 mã · <0: -30, -10 = 2 · =0: 1
    assert (nf["higher"], nf["lower"], nf["zero"]) == (7, 2, 1)


def test_check_without_numeric_field_skips_percentiles(db, company):
    """C1.2 không có trường số nào trong bản đồ → bỏ mục, không lỗi."""
    db.add_all([_f(company, code="C1.2", subject="A", details={"import_codes": ["E11"]})])
    db.commit()
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.2")
    assert st["numeric_fields"] == []


def test_missing_or_non_numeric_values_are_skipped(db, company):
    db.add_all([
        _f(company, subject="A", details={"diff_pct": 10.0}),
        _f(company, subject="B", details={}),                    # thiếu khoá
        _f(company, subject="C", details={"diff_pct": None}),
        _f(company, subject="D", details={"diff_pct": "n/a"}),   # chuỗi
    ])
    db.commit()
    nf = build_stats(
        db, company_id=company.id, period_year=2025, check_code="C1.1"
    )["numeric_fields"][0]
    assert nf["n"] == 1


def test_check_with_two_numeric_fields(db, company):
    db.add_all([
        _f(company, code="C4.3", subject="P1",
           details={"diff_pct": 12.0, "theoretical_consumption": 500.0}),
        _f(company, code="C4.3", subject="P2",
           details={"diff_pct": -8.0, "theoretical_consumption": 700.0}),
    ])
    db.commit()
    fields = build_stats(
        db, company_id=company.id, period_year=2025, check_code="C4.3"
    )["numeric_fields"]
    assert [f["key"] for f in fields] == ["diff_pct", "theoretical_consumption"]
    assert fields[0]["is_pct"] is True
    assert fields[1]["is_pct"] is False


# ───────────────────────── so kỳ trước ─────────────────────────

def test_previous_year_delta_and_new_subjects(db, company):
    db.add_all([
        _f(company, year=2024, subject="A"),
        _f(company, year=2024, subject="B"),
    ])
    db.add_all([
        _f(company, year=2025, subject="A"),
        _f(company, year=2025, subject="C"),
        _f(company, year=2025, subject="D"),
    ])
    db.commit()
    prev = build_stats(
        db, company_id=company.id, period_year=2025, check_code="C1.1"
    )["previous_year"]
    assert prev["available"] is True
    assert prev["year"] == 2024
    assert prev["total"] == 2
    assert prev["delta"] == 1
    assert prev["new_subjects_count"] == 2      # C, D
    assert prev["new_subjects"] == ["C", "D"]


def test_no_previous_period_says_so_instead_of_zero(db, company):
    """Không có kỳ trước phải NÓI RÕ — hiện 0 sẽ đọc thành "năm ngoái sạch"."""
    db.add(_f(company, year=2025, subject="A"))
    db.commit()
    prev = build_stats(
        db, company_id=company.id, period_year=2025, check_code="C1.1"
    )["previous_year"]
    assert prev["available"] is False
    assert "total" not in prev
    assert prev["year"] == 2024


def test_previous_period_with_zero_findings_for_this_check(db, company):
    """Kỳ trước CÓ dữ liệu nhưng kiểm tra này không bắn → 0 là con số thật."""
    db.add(_f(company, year=2024, code="C1.4", subject="X"))
    db.add(_f(company, year=2025, code="C1.1", subject="A"))
    db.commit()
    prev = build_stats(
        db, company_id=company.id, period_year=2025, check_code="C1.1"
    )["previous_year"]
    assert prev["available"] is True
    assert prev["total"] == 0
    assert prev["delta"] == 1


# ───────────────────────── tách theo sổ ─────────────────────────

def test_single_book_company_has_no_book_section(db, company):
    db.add(_f(company, subject="A"))
    db.commit()
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.1")
    assert "by_book" not in st


def test_multi_book_company_splits_by_book(db, company):
    # `is_multi_book` đọc sổ từ nvl/sp/norms — nguồn độc lập với finding.
    db.add_all([
        NvlBalance(company_id=company.id, period_year=2025, material_code="M1",
                   book="EPE", row_no=1),
        NvlBalance(company_id=company.id, period_year=2025, material_code="M2",
                   book="GC", row_no=2),
    ])
    db.add_all([
        _f(company, subject="A", book="EPE"),
        _f(company, subject="B", book="EPE"),
        _f(company, subject="C", book="GC"),
        _f(company, subject="D", book=None),
    ])
    db.commit()
    st = build_stats(db, company_id=company.id, period_year=2025, check_code="C1.1")
    got = {b["book"]: b["count"] for b in st["by_book"]}
    assert got == {"EPE": 2, "GC": 1, None: 1}
    # Nhóm liên sổ (book=NULL) xếp cuối và có nhãn đọc được.
    assert st["by_book"][-1]["book"] is None
    assert st["by_book"][-1]["label"]
