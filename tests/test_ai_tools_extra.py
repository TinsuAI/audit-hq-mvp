"""Tests cho tool mới: export_excel, propose_check_run, generate_report, export_query_excel."""

from __future__ import annotations

import io
from urllib.parse import unquote

import openpyxl

from app.ai.tools import TOOL_REGISTRY
from app.models import CompanyYearScore, Finding, Job
from app.pipeline.export import build_query_export

# ─────────────────────────── export_excel ───────────────────────────

def test_export_excel_returns_download_url(session, company):
    session.add(Finding(
        company_id=company.id, period_year=2024, check_code="C2.3",
        severity="critical", subject_key="X", title="t", status="new",
    ))
    session.commit()
    out = TOOL_REGISTRY["export_excel"](session, company_code=company.code, year=2024)
    assert out["download_url"] == f"/companies/{company.code}/export?year=2024"
    assert out["filename"].endswith(".xlsx")
    assert out["findings_count"] == 1


def test_export_excel_unknown_company(session):
    out = TOOL_REGISTRY["export_excel"](session, company_code="NOPE", year=2024)
    assert "error" in out


# ─────────────────────────── propose_check_run ───────────────────────────

def test_propose_check_run_returns_action_and_does_not_enqueue(session, company):
    out = TOOL_REGISTRY["propose_check_run"](session, company_code=company.code, year=2024)
    assert out["_ui_action"] == "run_checks"
    assert out["company_code"] == company.code
    assert out["year"] == 2024
    # KHÔNG được tạo job — chỉ đề xuất.
    assert session.query(Job).count() == 0


def test_propose_check_run_all_years(session, company):
    out = TOOL_REGISTRY["propose_check_run"](session, company_code=company.code)
    assert out["year"] is None
    assert "mọi năm" in out["label"]


def test_propose_check_run_unknown_company(session):
    out = TOOL_REGISTRY["propose_check_run"](session, company_code="NOPE")
    assert "error" in out


# ─────────────────────────── generate_report ───────────────────────────

def test_generate_report_gathers_full_data(session, company):
    session.add_all([
        Finding(company_id=company.id, period_year=2024, check_code="C2.3",
                severity="critical", subject_key="NVL_1", title="Tồn âm", status="new"),
        Finding(company_id=company.id, period_year=2024, check_code="C3.2",
                severity="warning", subject_key="NVL_2", title="HS lệch", status="new"),
        Finding(company_id=company.id, period_year=2024, check_code="COMBO_HS_GAMING",
                severity="warning", subject_key="NVL_2", title="Tổ hợp phân loại sai", status="new"),
    ])
    session.add(CompanyYearScore(
        company_id=company.id, period_year=2024, score=168, tier="Cao", breakdown={},
    ))
    session.commit()

    out = TOOL_REGISTRY["generate_report"](session, company_code=company.code, year=2024)
    assert out["company"]["code"] == company.code
    assert out["score"] == 168
    assert out["tier"] == "Cao"
    assert out["total_findings"] == 3
    assert out["severity_totals"]["critical"] == 1
    assert out["severity_totals"]["warning"] == 2
    # Combo tách riêng khỏi findings_by_group.
    assert len(out["combos_fired"]) == 1
    assert out["combos_fired"][0]["code"] == "COMBO_HS_GAMING"
    # Nhóm 2 (C2.3) + nhóm 3 (C3.2) có mặt.
    assert 2 in out["findings_by_group"]
    assert 3 in out["findings_by_group"]
    assert out["download_url"] == f"/companies/{company.code}/export?year=2024"
    assert len(out["legal_references"]) >= 1
    # top_findings chỉ gồm critical/warning (không combo) và có finding_id để cite.
    assert all("finding_id" in f for f in out["top_findings"])


def test_generate_report_unknown_company(session):
    out = TOOL_REGISTRY["generate_report"](session, company_code="NOPE", year=2024)
    assert "error" in out


# ─────────────────────────── export_query_excel (tùy biến) ───────────────────────────

def test_export_query_excel_returns_encoded_url(session, company):
    sql = "SELECT company_code, COUNT(*) n FROM v_findings GROUP BY company_code"
    out = TOOL_REGISTRY["export_query_excel"](session, sql=sql, title="Tổng hợp theo DN")
    assert out["download_url"].startswith("/api/chat/export-query?sql=")
    assert out["title"] == "Tổng hợp theo DN"
    # SQL được url-encode trong link.
    assert "v_findings" in unquote(out["download_url"])


def test_export_query_excel_rejects_sensitive_table(session):
    out = TOOL_REGISTRY["export_query_excel"](session, sql="SELECT * FROM users")
    assert "error" in out
    assert "download_url" not in out


def test_build_query_export_produces_xlsx(session, company):
    session.add_all([
        Finding(company_id=company.id, period_year=2024, check_code="C2.3",
                severity="critical", subject_key="NVL_1", title="t", status="new"),
        Finding(company_id=company.id, period_year=2024, check_code="C3.2",
                severity="warning", subject_key="NVL_2", title="t", status="new"),
    ])
    session.commit()
    sql = ("SELECT severity, COUNT(*) so_luong FROM v_findings "
           f"WHERE company_code='{company.code}' GROUP BY severity")
    blob = build_query_export(session, sql, title="Phân bố mức độ")
    wb = openpyxl.load_workbook(io.BytesIO(blob))
    ws = wb["Kết quả"]
    # Tiêu đề + câu SQL embed trong file (truy nguồn).
    flat = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "Phân bố mức độ" in flat
    assert "v_findings" in flat        # câu SQL hiển thị
    assert "severity" in flat          # header cột
    assert "so_luong" in flat


def test_build_query_export_raises_on_bad_sql(session):
    import pytest
    with pytest.raises(ValueError):
        build_query_export(session, "SELECT * FROM ai_settings")
