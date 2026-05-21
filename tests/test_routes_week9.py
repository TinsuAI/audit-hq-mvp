"""Tests cho route tuần 9: finding detail, data viewer, export Excel."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, DeclarationLine, Finding, NvlBalance


def _setup_db():
    import app.database as dbmod

    new_engine = dbmod.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"user": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _seed_company_with_finding(session) -> tuple[int, int]:
    c = Company(code="DN_T1", tax_id="9999999999", name="Test DN", risk_score=10)
    session.add(c)
    session.flush()

    session.add(NvlBalance(
        company_id=c.id, period_year=2024, material_code="X",
        opening_qty=10, import_qty=100, production_out_qty=80, closing_qty=30, unit="KG",
    ))
    session.add(DeclarationLine(
        company_id=c.id, period_year=2024,
        declaration_no="100000000001",
        declaration_date=date(2024, 6, 15),
        customs_code="E31", item_code="X", hs_code="12345678",
        quantity=100, unit="KG",
    ))
    f = Finding(
        company_id=c.id, period_year=2024,
        check_code="C1.1", severity="warning",
        subject_type="material_code", subject_key="X",
        title="Lệch nhập NVL X",
        details={"m15_import": 100, "bcct_sum": 90, "diff_pct": -10},
        evidence_refs=[
            {"table": "nvl_balances", "filter": {"company_id": c.id, "material_code": "X"}},
            {"table": "declaration_lines", "filter": {"company_id": c.id, "item_code": "X"}},
        ],
    )
    session.add(f)
    session.commit()
    return c.id, f.id


# --- Finding detail ---


def test_finding_detail_renders_with_evidence():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            _, finding_id = _seed_company_with_finding(s)

        client = TestClient(app)
        _login(client)
        response = client.get(f"/findings/{finding_id}")
        assert response.status_code == 200
        text = response.text
        assert "Chứng cứ truy nguồn" in text
        assert "nvl_balances" in text
        assert "declaration_lines" in text
        assert "C1.1" in text
        assert "Lệch nhập NVL X" in text
    finally:
        _teardown(new_engine)


def test_finding_detail_404_when_missing():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        response = client.get("/findings/99999")
        assert response.status_code == 404
    finally:
        _teardown(new_engine)


# --- Data viewer ---


def test_company_data_page_lists_m15():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            _seed_company_with_finding(s)

        client = TestClient(app)
        _login(client)
        response = client.get("/companies/DN_T1/data?year=2024&table=m15")
        assert response.status_code == 200
        assert "Mẫu 15" in response.text
        assert ">X<" in response.text
    finally:
        _teardown(new_engine)


def test_company_data_filter_by_code():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            company_id, _ = _seed_company_with_finding(s)
            s.add(NvlBalance(
                company_id=company_id, period_year=2024, material_code="OTHER",
                opening_qty=5, closing_qty=5,
            ))
            s.commit()

        client = TestClient(app)
        _login(client)
        response = client.get("/companies/DN_T1/data?year=2024&table=m15&q=OTH")
        assert response.status_code == 200
        assert "OTHER" in response.text
    finally:
        _teardown(new_engine)


def test_company_data_invalid_table_returns_400():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            _seed_company_with_finding(s)
        client = TestClient(app)
        _login(client)
        response = client.get("/companies/DN_T1/data?year=2024&table=bogus")
        assert response.status_code == 400
    finally:
        _teardown(new_engine)


# --- Export Excel ---


def test_export_excel_returns_xlsx_with_expected_sheets():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            _seed_company_with_finding(s)

        client = TestClient(app)
        _login(client)
        response = client.get("/companies/DN_T1/export?year=2024")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "DN_T1_2024" in response.headers["content-disposition"]

        wb = load_workbook(BytesIO(response.content))
        expected_sheets = {
            "Tổng quan", "Phát hiện",
            "Chứng cứ M15", "Chứng cứ M15a", "Chứng cứ M16", "Chứng cứ BCCT",
            "Pháp lý",
        }
        assert expected_sheets.issubset(set(wb.sheetnames))

        ws = wb["Phát hiện"]
        assert ws.cell(1, 1).value == "Mã check"
        assert ws.cell(2, 1).value == "C1.1"
        assert ws.cell(2, 4).value == "X"
    finally:
        _teardown(new_engine)


def test_export_404_when_company_missing():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        response = client.get("/companies/NOPE/export?year=2024")
        assert response.status_code == 404
    finally:
        _teardown(new_engine)


# Note: cleanup in fixtures by relying on _teardown when assertions reached.
# Tests that succeed already restore state via the finally clauses where used.
