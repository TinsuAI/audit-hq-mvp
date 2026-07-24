"""WS2-1 foundation — combos_enabled toggle + combo recompute mọi lần chạy.

- `combos_enabled` mặc định OFF (ADR #18 Revision — WS2): `run_checks` full KHÔNG
  sinh COMBO_*.
- ON → combo recompute trên MỌI lần chạy, đọc TOÀN finding-set của (DN, năm), kể cả
  khi chạy lẻ (`only=`). Sửa lỗi WS1: chạy lẻ xoá COMBO mà không dựng lại.
- `run_checks_handler` chuyển `only` từ payload xuống pipeline.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.app_settings import get_combos_enabled, invalidate_cache, set_combos_enabled
from app.models import Finding
from app.pipeline.run_checks import run_checks
from tests.conftest import add_nvl


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Cache app_settings là process-global; DB in-memory mới mỗi test. Xoá cache
    hai đầu để cờ combos_enabled không rò rỉ qua các test."""
    invalidate_cache()
    yield
    invalidate_cache()


def _seed_trigger(session, company_id, code, subject="MAT_X"):
    f = Finding(
        company_id=company_id, period_year=2024, check_code=code, severity="critical",
        subject_type="material_code", subject_key=subject, title=f"{code} {subject}",
    )
    session.add(f)
    return f


def test_get_set_combos_enabled_roundtrip(session):
    assert get_combos_enabled(db=session) is False  # default OFF
    set_combos_enabled(True, updated_by="tester", db=session)
    assert get_combos_enabled(db=session) is True
    set_combos_enabled(False, updated_by="tester", db=session)
    assert get_combos_enabled(db=session) is False


def test_combos_off_by_default_no_combo_findings(session, company):
    _seed_trigger(session, company.id, "C2.3")
    _seed_trigger(session, company.id, "C4.3")
    add_nvl(session, company.id, material_code="MAT_X", closing=-5)
    session.commit()

    run_checks(company.code, 2024, only={"C1.1"}, session=session)

    combos = session.scalars(
        select(Finding).where(
            Finding.company_id == company.id, Finding.check_code.like("COMBO_%")
        )
    ).all()
    assert combos == []


def test_combos_on_recomputes_from_full_set_on_scoped_run(session, company):
    """Chạy lẻ (`only=`) đọc TOÀN finding-set → combo bắc cầu giữa 2 check không chạy."""
    set_combos_enabled(True, updated_by="tester", db=session)
    _seed_trigger(session, company.id, "C2.3")
    _seed_trigger(session, company.id, "C4.3")
    add_nvl(session, company.id, material_code="MAT_X", closing=-5)
    session.commit()

    # only={"C1.1"} không đụng C2.3/C4.3, nhưng combo vẫn phải dựng từ full set.
    run_checks(company.code, 2024, only={"C1.1"}, session=session)

    codes = {
        c.check_code
        for c in session.scalars(
            select(Finding).where(
                Finding.company_id == company.id, Finding.check_code.like("COMBO_%")
            )
        ).all()
    }
    assert "COMBO_FORGED_NORM" in codes


def test_scoped_run_rebuilds_combo_not_permanently_wiped(session, company):
    """Regression WS1: chạy lẻ xoá COMBO_* rồi KHÔNG dựng lại → combo biến mất tới
    lần full kế. Sau fix: recompute mọi lần chạy → combo vẫn còn."""
    set_combos_enabled(True, updated_by="tester", db=session)
    _seed_trigger(session, company.id, "C2.3")
    _seed_trigger(session, company.id, "C4.3")
    add_nvl(session, company.id, material_code="MAT_X", closing=-5)
    session.commit()

    def _combo_count() -> int:
        return len(session.scalars(
            select(Finding).where(
                Finding.company_id == company.id, Finding.check_code.like("COMBO_%")
            )
        ).all())

    run_checks(company.code, 2024, only={"C1.1"}, session=session)  # scoped: build combo
    assert _combo_count() >= 1

    # Chạy lẻ lần 2 (code khác, không đụng trigger): xoá COMBO_* rồi PHẢI dựng lại.
    # Trước fix WS1: xoá mà không dựng → combo biến mất.
    run_checks(company.code, 2024, only={"C5.1"}, session=session)
    assert _combo_count() >= 1


def test_run_checks_handler_forwards_only(session, company, monkeypatch):
    import app.jobs.handlers as handlers

    captured = {}

    def _fake_pipeline(company_code, year, only=None, session=None):
        captured["only"] = only
        from app.checks.company_type import CompanyType
        from app.pipeline.run_checks import RunStats
        return RunStats(company_code=company_code, period_year=year,
                        company_type=CompanyType.DNCX)

    monkeypatch.setattr(handlers, "run_checks_pipeline", _fake_pipeline)

    handlers.run_checks_handler(
        {"company_code": company.code, "year": 2024, "only": ["C1.1", "C4.3"]}, session
    )
    assert captured["only"] == {"C1.1", "C4.3"}

    handlers.run_checks_handler({"company_code": company.code, "year": 2024}, session)
    assert captured["only"] is None
