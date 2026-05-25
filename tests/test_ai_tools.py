"""Tests cho 6 AI tool — riêng phần Day 3+Day 4.

Test trên in-memory DB + conftest fixtures. Không gọi LLM thật.
"""

from __future__ import annotations

import json

import pytest

from app.ai.tools import (
    TOOL_REGISTRY,
    TOOL_SCHEMAS,
    _load_legal_section,
    run_tool,
)
from app.models import Finding

# ─────────────────────────── search_findings ───────────────────────────

def test_search_findings_returns_company_meta(session, company):
    session.add(Finding(
        company_id=company.id, period_year=2024, check_code="C2.3", severity="critical",
        subject_key="NVL_01", title="Tồn cuối NVL âm", status="new",
    ))
    session.commit()
    result = TOOL_REGISTRY["search_findings"](session, company_code=company.code)
    assert result["count"] == 1
    assert result["company_code"] == "TEST_DN"
    assert result["findings"][0]["check_code"] == "C2.3"


def test_search_findings_filters_by_severity(session, company):
    session.add_all([
        Finding(company_id=company.id, period_year=2024, check_code="C1.1",
                severity="critical", subject_key="x", title="t1", status="new"),
        Finding(company_id=company.id, period_year=2024, check_code="C3.2",
                severity="warning", subject_key="x", title="t2", status="new"),
    ])
    session.commit()
    crit = TOOL_REGISTRY["search_findings"](session, company_code=company.code, severity="critical")
    assert crit["count"] == 1
    assert crit["findings"][0]["check_code"] == "C1.1"


def test_search_findings_unknown_company(session):
    result = TOOL_REGISTRY["search_findings"](session, company_code="NOPE")
    assert "error" in result
    assert result["count"] == 0


# ─────────────────────────── get_finding ───────────────────────────

def test_get_finding_returns_full_detail(session, company):
    f = Finding(
        company_id=company.id, period_year=2024, check_code="C3.2", severity="warning",
        subject_key="X-DL", title="Mã HS không nhất quán",
        notes="Cán bộ ghi chú test", status="new",
        details={"hs_codes": ["41079900", "41151000"]},
        evidence_refs=[{"table": "declaration_lines", "filter": {"item_code": "X-DL"}}],
    )
    session.add(f)
    session.commit()
    result = TOOL_REGISTRY["get_finding"](session, finding_id=f.id)
    assert result["check_code"] == "C3.2"
    assert result["details"]["hs_codes"] == ["41079900", "41151000"]
    assert result["company"]["code"] == "TEST_DN"


def test_get_finding_not_found(session):
    result = TOOL_REGISTRY["get_finding"](session, finding_id=99999)
    assert "error" in result


# ─────────────────────────── query_raw_data ───────────────────────────

def test_query_raw_data_m15_happy_path(session, company):
    from tests.conftest import add_nvl
    add_nvl(session, company.id, material_code="NVL_001", unit="KGM", opening=100)
    add_nvl(session, company.id, material_code="NVL_002", unit="PCE", opening=50)
    session.commit()
    result = TOOL_REGISTRY["query_raw_data"](
        session, table="m15", company_code=company.code, year=2024,
    )
    assert result["count"] == 2
    assert "row_no" in result["columns"]
    # source_file phải bị ẩn (PII / DN gốc).
    assert "source_file" not in result["columns"]


def test_query_raw_data_with_filter(session, company):
    from tests.conftest import add_nvl
    add_nvl(session, company.id, material_code="ALPHA_X", opening=10)
    add_nvl(session, company.id, material_code="BETA_Y", opening=20)
    session.commit()
    result = TOOL_REGISTRY["query_raw_data"](
        session, table="m15", company_code=company.code, year=2024,
        filter_field="material_code", filter_value="ALPHA",
    )
    assert result["count"] == 1
    assert result["rows"][0]["material_code"] == "ALPHA_X"


def test_query_raw_data_invalid_table(session, company):
    result = TOOL_REGISTRY["query_raw_data"](
        session, table="m99", company_code=company.code, year=2024,
    )
    assert "error" in result


def test_query_raw_data_invalid_filter_field(session, company):
    result = TOOL_REGISTRY["query_raw_data"](
        session, table="m15", company_code=company.code, year=2024,
        filter_field="nonexistent_col", filter_value="x",
    )
    assert "error" in result
    assert "nonexistent_col" in result["error"]


def test_query_raw_data_unknown_company(session):
    result = TOOL_REGISTRY["query_raw_data"](
        session, table="m15", company_code="NOPE", year=2024,
    )
    assert "error" in result
    assert result["count"] == 0


# ─────────────────────────── explain_check ───────────────────────────

def test_explain_check_returns_spec_for_known_code(session):
    # Use any code that exists in SPECS — pick the first one
    from app.checks.registry import SPECS
    code = sorted(SPECS.keys())[0]
    result = TOOL_REGISTRY["explain_check"](session, check_code=code)
    assert result["kind"] == "check"
    assert result["code"] == code
    assert "title" in result


def test_explain_check_returns_combo(session):
    from app.checks.combos import COMBO_SPECS
    code = next(iter(COMBO_SPECS))
    result = TOOL_REGISTRY["explain_check"](session, check_code=code)
    assert result["kind"] == "combo"
    assert "triggers" in result


def test_explain_check_unknown(session):
    result = TOOL_REGISTRY["explain_check"](session, check_code="C99.99")
    assert "error" in result
    assert "available_check_codes" in result


# ─────────────────────────── list_companies ───────────────────────────

def test_list_companies_empty(session):
    result = TOOL_REGISTRY["list_companies"](session)
    assert result["count"] == 0
    assert result["companies"] == []


def test_list_companies_sorted_by_risk(session):
    from app.models import Company
    session.add_all([
        Company(code="DN_A", name="A", risk_score=10),
        Company(code="DN_B", name="B", risk_score=500),
        Company(code="DN_C", name="C", risk_score=100),
    ])
    session.commit()
    result = TOOL_REGISTRY["list_companies"](session)
    codes = [c["code"] for c in result["companies"]]
    assert codes == ["DN_B", "DN_C", "DN_A"]


def test_list_companies_with_findings_per_year(session, company):
    session.add_all([
        Finding(company_id=company.id, period_year=2024, check_code="C1.1",
                severity="critical", subject_key="x", title="t", status="new"),
        Finding(company_id=company.id, period_year=2024, check_code="C2.3",
                severity="warning", subject_key="y", title="t", status="new"),
        Finding(company_id=company.id, period_year=2023, check_code="C3.2",
                severity="info", subject_key="z", title="t", status="new"),
    ])
    session.commit()
    result = TOOL_REGISTRY["list_companies"](session)
    fpy = result["companies"][0]["findings_per_year"]
    assert fpy[2024]["critical"] == 1
    assert fpy[2024]["warning"] == 1
    assert fpy[2023]["info"] == 1


# ─────────────────────────── get_legal_context ───────────────────────────

def test_get_legal_context_full(session):
    """Skip nếu file đề án không có (CI runner chỉ checkout audit-hq-mvp)."""
    if _load_legal_section() is None:
        pytest.skip("Đề án không có trong môi trường này")
    result = TOOL_REGISTRY["get_legal_context"](session)
    assert "full_section" in result
    assert "Luật Hải quan" in result["full_section"]


def test_get_legal_context_topic_match(session):
    if _load_legal_section() is None:
        pytest.skip("Đề án không có")
    result = TOOL_REGISTRY["get_legal_context"](session, topic="Hải quan")
    assert result["topic"] == "Hải quan"
    assert result["matched_count"] >= 1


def test_get_legal_context_topic_no_match(session):
    if _load_legal_section() is None:
        pytest.skip("Đề án không có")
    result = TOOL_REGISTRY["get_legal_context"](session, topic="xxxNOMATCHxxx")
    assert result["matched_count"] == 0
    assert "full_section" in result  # fallback


# ─────────────────────────── run_tool dispatcher ───────────────────────────

def test_run_tool_dispatches_all_6_tools(session, company):
    # Sanity check: all 6 tools registered + schemas match registry keys.
    schema_names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert schema_names == set(TOOL_REGISTRY.keys())
    assert len(schema_names) == 6


def test_run_tool_unknown_tool_returns_json_error(session):
    out = run_tool("nonexistent_tool", "{}", session)
    payload = json.loads(out)
    assert "error" in payload
    assert "Unknown tool" in payload["error"]


def test_run_tool_bad_args_returns_json_error(session):
    out = run_tool("search_findings", "{not json}", session)
    payload = json.loads(out)
    assert "error" in payload


def test_run_tool_truncates_large_result(session, company):
    # Tạo nhiều norms để query_raw_data trả về > 4000 chars
    from app.models import Norm
    session.add_all([
        Norm(
            company_id=company.id, period_year=2024,
            product_code=f"P{i:03d}", product_name=f"Product {i} " * 5,
            material_code=f"M{i:03d}", material_name=f"Mat {i} " * 5,
            norm_qty=1.5,
        )
        for i in range(50)
    ])
    session.commit()
    out = run_tool(
        "query_raw_data",
        json.dumps({"table": "m16", "company_code": company.code, "year": 2024, "limit": 50}),
        session,
    )
    payload = json.loads(out)
    # Truncate kích hoạt khi result raw > 4000 chars. Output cuối có thể hơi to
    # hơn 4000 do JSON wrap + escape Unicode → assert truncate flag thay vì byte.
    assert payload.get("truncated") is True
    assert "preview" in payload
    assert len(payload["preview"]) <= 3800
