"""Unit tests cho C6.1 — Tồn đầu kỳ N ≠ tồn cuối kỳ N-1."""

from __future__ import annotations

from app.checks.c6_cross_period import check_c6_1
from tests.conftest import add_nvl


def test_c6_1_skip_when_no_prev_year(session, company):
    add_nvl(session, company.id, material_code="A", opening=100, year=2024)
    session.commit()
    # Không có dữ liệu 2023 → skip toàn rule
    assert check_c6_1(session, company.id, 2024) == []


def test_c6_1_no_fire_when_match(session, company):
    add_nvl(session, company.id, material_code="A", opening=0, closing=120, year=2023)
    add_nvl(session, company.id, material_code="A", opening=120, year=2024)
    session.commit()
    assert check_c6_1(session, company.id, 2024) == []


def test_c6_1_fires_when_mismatch(session, company):
    add_nvl(session, company.id, material_code="A", opening=0, closing=120, year=2023)
    add_nvl(session, company.id, material_code="A", opening=100, year=2024)  # 100 ≠ 120
    session.commit()
    findings = check_c6_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].check_code == "C6.1"
    assert findings[0].severity == "critical"
    assert findings[0].details["diff"] == -20.0


def test_c6_1_fires_when_new_code_has_opening(session, company):
    # NVL mới xuất hiện 2024 với opening > 0 nhưng 2023 không có
    add_nvl(session, company.id, material_code="OTHER", opening=0, closing=50, year=2023)
    add_nvl(session, company.id, material_code="NEW", opening=30, year=2024)
    session.commit()
    findings = check_c6_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "NEW"
    assert findings[0].details["previous_closing"] is None


def test_c6_1_no_fire_when_new_code_zero_opening(session, company):
    # NVL mới chỉ phát sinh trong 2024 với opening = 0 → hợp lệ
    add_nvl(session, company.id, material_code="OTHER", opening=0, closing=50, year=2023)
    add_nvl(session, company.id, material_code="NEW", opening=0, imported=100, year=2024)
    session.commit()
    assert check_c6_1(session, company.id, 2024) == []
