"""Tests cho SQL tool chỉ-đọc (app/ai/sql_tool).

Trọng tâm an toàn: guard chặn ghi/DDL/multi-statement + chặn cứng bảng nhạy cảm
(users/ai_settings), cap LIMIT, query_only reset sau khi chạy.
"""

from __future__ import annotations

import pytest

from app.ai.sql_tool import ALLOWED_VIEWS, SqlGuardError, ensure_views, run_query, validate_sql
from app.models import Finding

# ─────────────────────────── validate_sql: reject ───────────────────────────

@pytest.mark.parametrize("sql", [
    "INSERT INTO v_findings VALUES (1)",
    "UPDATE v_findings SET status='x'",
    "DELETE FROM v_findings",
    "DROP TABLE findings",
    "ALTER TABLE findings ADD COLUMN x",
    "CREATE TABLE x (a int)",
    "PRAGMA table_info(users)",
    "ATTACH DATABASE 'x.db' AS y",
    "VACUUM",
])
def test_validate_rejects_writes_and_ddl(sql):
    with pytest.raises(SqlGuardError):
        validate_sql(sql)


def test_validate_rejects_multiple_statements():
    with pytest.raises(SqlGuardError):
        validate_sql("SELECT 1 FROM v_findings; DROP TABLE findings")


def test_validate_rejects_non_select_start():
    with pytest.raises(SqlGuardError):
        validate_sql("EXPLAIN SELECT * FROM v_findings")


@pytest.mark.parametrize("table", ["users", "ai_settings", "sqlite_master", "jobs"])
def test_validate_rejects_sensitive_tables(table):
    with pytest.raises(SqlGuardError):
        validate_sql(f"SELECT * FROM {table}")


def test_validate_rejects_sensitive_table_in_subquery():
    # Backstop: bảng nhạy cảm ẩn trong subquery vẫn bị chặn.
    with pytest.raises(SqlGuardError):
        validate_sql("SELECT * FROM v_findings WHERE 1 IN (SELECT id FROM users)")


def test_validate_rejects_non_allowlisted_table():
    with pytest.raises(SqlGuardError):
        validate_sql("SELECT * FROM declaration_lines")


def test_validate_rejects_comment_hidden_injection():
    with pytest.raises(SqlGuardError):
        validate_sql("SELECT * FROM v_findings /* ; */ ; DELETE FROM findings")


# ─────────────────────────── validate_sql: accept ───────────────────────────

def test_validate_accepts_select_on_view_and_wraps_limit():
    display, exec_sql = validate_sql("SELECT * FROM v_findings WHERE company_code='DN_1'", row_cap=50)
    assert display.lower().startswith("select")
    assert "limit 50" in exec_sql.lower()
    # display giữ nguyên câu gốc (không có wrap) để cán bộ đọc.
    assert "_ahq_capped" not in display


def test_validate_accepts_cte():
    display, exec_sql = validate_sql(
        "WITH t AS (SELECT company_code, COUNT(*) n FROM v_findings GROUP BY company_code) "
        "SELECT * FROM t WHERE n > 0"
    )
    assert "limit" in exec_sql.lower()


def test_allowed_views_are_six():
    assert ALLOWED_VIEWS == {"v_findings", "v_m15", "v_m15a", "v_m16", "v_bcct", "v_company_scores"}


# ─────────────────────────── run_query: integration ───────────────────────────

def _seed_findings(session, company):
    session.add_all([
        Finding(company_id=company.id, period_year=2024, check_code="C2.3",
                severity="critical", subject_key="NVL_1", title="Tồn âm", status="new"),
        Finding(company_id=company.id, period_year=2024, check_code="C3.2",
                severity="warning", subject_key="NVL_2", title="HS lệch", status="new"),
        Finding(company_id=company.id, period_year=2023, check_code="C1.1",
                severity="info", subject_key="NVL_3", title="Lệch nhẹ", status="new"),
    ])
    session.commit()


def test_run_query_aggregate_findings(session, company):
    _seed_findings(session, company)
    out = run_query(
        session,
        f"SELECT severity, COUNT(*) AS n FROM v_findings "
        f"WHERE company_code='{company.code}' AND period_year=2024 GROUP BY severity",
    )
    assert "error" not in out
    counts = {r["severity"]: r["n"] for r in out["rows"]}
    assert counts == {"critical": 1, "warning": 1}
    assert "sql" in out  # câu SQL trả lại để cán bộ kiểm chứng


def test_run_query_view_m15(session, company):
    from tests.conftest import add_nvl
    add_nvl(session, company.id, material_code="NVL_A", closing=-5)
    add_nvl(session, company.id, material_code="NVL_B", closing=10)
    session.commit()
    out = run_query(session, f"SELECT material_code, closing_qty FROM v_m15 "
                             f"WHERE company_code='{company.code}' AND closing_qty < 0")
    assert out["row_count"] == 1
    assert out["rows"][0]["material_code"] == "NVL_A"


def test_run_query_blocks_write(session, company):
    _seed_findings(session, company)
    out = run_query(session, "DELETE FROM findings")
    assert "error" in out
    # Dữ liệu không đổi.
    assert session.query(Finding).count() == 3


def test_run_query_caps_rows(session, company):
    session.add_all([
        Finding(company_id=company.id, period_year=2024, check_code="C1.1",
                severity="info", subject_key=f"S{i}", title="t", status="new")
        for i in range(10)
    ])
    session.commit()
    out = run_query(session, "SELECT * FROM v_findings", row_cap=4)
    assert out["row_count"] == 4
    assert out["truncated"] is True


def test_run_query_resets_query_only(session, company):
    # Sau khi chạy SQL chỉ-đọc, session vẫn phải GHI được (query_only đã reset OFF).
    run_query(session, "SELECT 1 AS x FROM v_findings")
    session.add(Finding(
        company_id=company.id, period_year=2024, check_code="C2.3",
        severity="critical", subject_key="W", title="ghi sau query", status="new",
    ))
    session.commit()  # không được raise
    assert session.query(Finding).count() == 1


def test_run_query_guard_error_passthrough(session, company):
    out = run_query(session, "SELECT * FROM users")
    assert "error" in out
    assert "users" in out["error"]


def test_ensure_views_idempotent(session):
    ensure_views(session)
    ensure_views(session)  # gọi lại không lỗi
