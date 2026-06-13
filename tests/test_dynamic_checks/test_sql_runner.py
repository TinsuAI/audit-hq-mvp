"""Tests — sql_runner: chạy check SQL/Python tự do (read-only) → Finding.

Chạy trên in-memory SQLite qua conftest `session` + `company`.
"""

from __future__ import annotations

import pytest

from app.checks.sql_runner import (
    CheckRunError,
    dry_run,
    run_check,
    validate_check_definition,
    validate_sql_is_select_only,
)
from app.models.check_definition import CheckDefinition
from tests.conftest import add_nvl

_SQL_NEG = (
    "SELECT 'critical' AS severity, material_code AS subject_key, "
    "'Tồn âm ' || material_code AS title, 'c=' || closing_qty AS detail "
    "FROM nvl_balances WHERE company_id = :company_id AND period_year = :period_year "
    "AND closing_qty < -0.01"
)


def _sql_def(**kw):
    base = dict(
        code="X.1", kind="sql", title="t", description="", group=99,
        default_severity="critical", spec={}, sql_snippet=_SQL_NEG,
        subject_table="nvl_balances", subject_col="material_code", scope="nvl",
    )
    base.update(kw)
    return CheckDefinition(**base)


class TestRunSql:
    def test_fires_and_builds_evidence(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-5)
        add_nvl(session, company.id, material_code="NVL002", closing=10)
        session.commit()
        findings = run_check(_sql_def(), session, company.id, 2024)
        assert len(findings) == 1
        f = findings[0]
        assert f.check_code == "X.1"
        assert f.severity == "critical"
        assert f.subject_key == "NVL001"
        assert f.subject_type == "material_code"
        assert f.evidence_refs == [{
            "table": "nvl_balances",
            "filter": {"company_id": company.id, "period_year": 2024, "material_code": "NVL001"},
        }]

    def test_scoped_to_company_and_year(self, session, company):
        add_nvl(session, company.id, material_code="A", closing=-5, year=2024)
        add_nvl(session, company.id, material_code="B", closing=-5, year=2023)
        session.commit()
        f2024 = run_check(_sql_def(), session, company.id, 2024)
        f2023 = run_check(_sql_def(), session, company.id, 2023)
        assert {f.subject_key for f in f2024} == {"A"}
        assert {f.subject_key for f in f2023} == {"B"}

    def test_severity_from_case_expression(self, session, company):
        add_nvl(session, company.id, material_code="BIG", closing=5000)
        add_nvl(session, company.id, material_code="SMALL", closing=10)
        session.commit()
        sql = (
            "SELECT CASE WHEN closing_qty > 1000 THEN 'warning' ELSE 'info' END AS severity, "
            "material_code AS subject_key, material_code AS title, '' AS detail "
            "FROM nvl_balances WHERE company_id = :company_id AND period_year = :period_year"
        )
        findings = run_check(_sql_def(sql_snippet=sql), session, company.id, 2024)
        sev = {f.subject_key: f.severity for f in findings}
        assert sev == {"BIG": "warning", "SMALL": "info"}

    def test_invalid_severity_falls_back_to_default(self, session, company):
        add_nvl(session, company.id, material_code="X", closing=-5)
        session.commit()
        sql = _SQL_NEG.replace("'critical' AS severity", "'bogus' AS severity")
        findings = run_check(_sql_def(sql_snippet=sql, default_severity="warning"), session, company.id, 2024)
        assert findings[0].severity == "warning"

    def test_missing_columns_raises(self, session, company):
        add_nvl(session, company.id, material_code="X", closing=-5)
        session.commit()
        bad = "SELECT material_code FROM nvl_balances WHERE company_id=:company_id AND period_year=:period_year"  # noqa: E501
        with pytest.raises(CheckRunError):
            run_check(_sql_def(sql_snippet=bad), session, company.id, 2024)


class TestRunPython:
    def test_python_fires_and_builds_evidence(self, session, company):
        add_nvl(session, company.id, material_code="P1", closing=-3)
        session.commit()
        code = (
            "def run(conn, company_id, period_year):\n"
            "    rows = conn.execute('SELECT material_code, closing_qty FROM nvl_balances "
            "WHERE company_id=? AND period_year=? AND closing_qty < -0.01', (company_id, period_year)).fetchall()\n"  # noqa: E501
            "    return [{'severity':'critical','subject_key':r['material_code'],"
            "'title':'py '+r['material_code'],'detail':str(r['closing_qty'])} for r in rows]\n"
        )
        d = _sql_def(kind="python", code_snippet=code, sql_snippet=None)
        findings = run_check(d, session, company.id, 2024)
        assert len(findings) == 1
        assert findings[0].subject_key == "P1"
        assert findings[0].evidence_refs[0]["table"] == "nvl_balances"

    def test_python_write_is_blocked(self, session, company):
        add_nvl(session, company.id, material_code="X", closing=-5)
        session.commit()
        code = "def run(conn, company_id, period_year):\n    conn.execute('DELETE FROM nvl_balances')\n    return []\n"  # noqa: E501
        d = _sql_def(kind="python", code_snippet=code, sql_snippet=None)
        with pytest.raises(CheckRunError):
            run_check(d, session, company.id, 2024)


class TestValidation:
    def test_deny_write_keyword(self):
        assert validate_sql_is_select_only("UPDATE x SET y=1") is not None
        assert validate_sql_is_select_only("DELETE FROM x") is not None
        assert validate_sql_is_select_only("SELECT 1") is None

    def test_deny_keyword_in_comment(self):
        assert validate_sql_is_select_only("SELECT 1 -- DROP TABLE x") is None
        assert validate_sql_is_select_only("/* drop */ SELECT 1") is None

    def test_validate_requires_company_id(self):
        err = validate_check_definition(
            kind="sql", sql="SELECT 1 AS severity", code=None,
            subject_table="nvl_balances", scope="nvl",
        )
        assert err and "company_id" in err

    def test_validate_rejects_bad_scope(self):
        assert validate_check_definition(
            kind="sql", sql=_SQL_NEG, code=None, subject_table="nvl_balances", scope="bogus",
        ) is not None

    def test_validate_ok(self):
        assert validate_check_definition(
            kind="sql", sql=_SQL_NEG, code=None, subject_table="nvl_balances", scope="nvl",
        ) is None


class TestDryRun:
    def test_dry_run_sql_with_detail(self, session, company):
        add_nvl(session, company.id, material_code="D1", closing=-7)
        session.commit()
        dq = ("SELECT material_code, closing_qty FROM nvl_balances "
              "WHERE company_id=:company_id AND period_year=:period_year AND closing_qty < -0.01 LIMIT 5")
        res = dry_run(
            session, kind="sql", sql=_SQL_NEG, detail_query=dq,
            company_id=company.id, year=2024, subject_table="nvl_balances",
            subject_col="material_code", default_severity="critical",
        )
        assert res["ok"] is True
        assert res["count"] == 1
        assert res["sample_rows"][0]["subject_key"] == "D1"
        assert "material_code" in res["matched_columns"]
        assert len(res["matched_rows"]) == 1

    def test_dry_run_reports_sql_error(self, session, company):
        res = dry_run(
            session, kind="sql", sql="SELECT nope FROM nowhere WHERE company_id=:company_id AND period_year=:period_year",  # noqa: E501
            company_id=company.id, year=2024,
        )
        assert res["ok"] is False
        assert res["error"]
