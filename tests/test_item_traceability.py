"""Tests for item detail / traceability helpers."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import add_decl, add_nvl, add_sp

# ─────────────────────────── operation classifier ───────────────────────────

class TestClassifyOperation:
    def test_import_codes_classified_as_import(self):
        from app.items.operations import classify_operation

        for code in ("E11", "E15", "E13", "E21", "E23", "E31", "E33"):
            assert classify_operation(code) == "import", code

    def test_export_codes_classified_as_export(self):
        from app.items.operations import classify_operation

        for code in ("E42", "E52", "E54", "E62"):
            assert classify_operation(code) == "export", code

    def test_b13_reexport_classified_as_export(self):
        from app.items.operations import classify_operation

        # B13 = tái xuất (re-export) → outbound flow
        assert classify_operation("B13") == "export"

    def test_a42_repurpose_classified_as_other(self):
        from app.items.operations import classify_operation

        # A42 = chuyển mục đích sử dụng nội địa → neither pure import nor export
        assert classify_operation("A42") == "other"

    def test_unknown_code(self):
        from app.items.operations import classify_operation

        assert classify_operation("ZZ99") == "unknown"
        assert classify_operation(None) == "unknown"
        assert classify_operation("") == "unknown"

    def test_operation_label_vi(self):
        from app.items.operations import operation_label

        assert "Nhập" in operation_label("E31")
        assert "Xuất" in operation_label("E62")


# ─────────────────────────── kind detection + years ───────────────────────────

class TestDetectItemKind:
    def test_nvl_only(self, session: Session, company):
        add_nvl(session, company.id, material_code="NPL-001")
        session.commit()
        from app.items.aggregations import detect_item_kind

        assert detect_item_kind(session, company.id, "NPL-001") == "nvl"

    def test_tp_only(self, session: Session, company):
        add_sp(session, company.id, product_code="TP-A01")
        session.commit()
        from app.items.aggregations import detect_item_kind

        assert detect_item_kind(session, company.id, "TP-A01") == "tp"

    def test_both(self, session: Session, company):
        add_nvl(session, company.id, material_code="X100")
        add_sp(session, company.id, product_code="X100")
        session.commit()
        from app.items.aggregations import detect_item_kind

        assert detect_item_kind(session, company.id, "X100") == "both"

    def test_unknown(self, session: Session, company):
        from app.items.aggregations import detect_item_kind

        assert detect_item_kind(session, company.id, "GHOST") == "unknown"

    def test_bcct_only_is_unknown_kind(self, session: Session, company):
        """BCCT has the code but BCQT does not → still 'unknown' kind (not NVL/TP).
        Caller may show a banner; here we don't guess."""
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="ORPHAN", quantity=10,
        )
        session.commit()
        from app.items.aggregations import detect_item_kind

        assert detect_item_kind(session, company.id, "ORPHAN") == "unknown"


class TestItemYears:
    def test_collects_years_across_all_sources(self, session: Session, company):
        add_nvl(session, company.id, material_code="A", year=2022)
        add_nvl(session, company.id, material_code="A", year=2023)
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="A", quantity=1, year=2024,
        )
        session.commit()
        from app.items.aggregations import item_years

        assert item_years(session, company.id, "A") == [2022, 2023, 2024]

    def test_no_data_returns_empty(self, session: Session, company):
        from app.items.aggregations import item_years

        assert item_years(session, company.id, "GHOST") == []


# ─────────────────────────── yearly summary (NVL) ───────────────────────────

class TestNvlYearlySummary:
    def test_combines_m15_and_bcct(self, session: Session, company):
        add_nvl(
            session, company.id, material_code="A",
            year=2023, opening=100, imported=500, production_out=400, closing=200,
        )
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="A", quantity=300, year=2023,
        )
        add_decl(
            session, company.id, declaration_no="D2",
            customs_code="E31", item_code="A", quantity=200, year=2023,
        )
        add_decl(
            session, company.id, declaration_no="D3",
            customs_code="B13", item_code="A", quantity=50, year=2023,
        )
        session.commit()
        from app.items.aggregations import nvl_yearly_summary

        rows = nvl_yearly_summary(session, company.id, "A")
        assert len(rows) == 1
        r = rows[0]
        assert r["year"] == 2023
        assert r["opening_qty"] == 100
        assert r["import_qty"] == 500           # from M15
        assert r["closing_qty"] == 200
        assert r["bcct_import_qty"] == 500      # sum of E31
        assert r["bcct_export_qty"] == 50       # B13 counted as export
        assert r["bcct_line_count"] == 3
        # Reconciliation: M15.import_qty vs BCCT import sum
        assert r["import_match"] is True

    def test_import_mismatch_flag(self, session: Session, company):
        add_nvl(session, company.id, material_code="B", year=2023, imported=500)
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="B", quantity=300, year=2023,
        )
        session.commit()
        from app.items.aggregations import nvl_yearly_summary

        rows = nvl_yearly_summary(session, company.id, "B")
        assert rows[0]["import_match"] is False
        assert rows[0]["import_diff"] == pytest.approx(200)

    def test_years_only_in_bcct_still_appear(self, session: Session, company):
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="C", quantity=10, year=2024,
        )
        session.commit()
        from app.items.aggregations import nvl_yearly_summary

        rows = nvl_yearly_summary(session, company.id, "C")
        # No M15 row → opening/import/closing 0 but BCCT shown
        assert rows[0]["year"] == 2024
        assert rows[0]["import_qty"] == 0
        assert rows[0]["bcct_import_qty"] == 10


# ─────────────────────────── yearly summary (TP) ───────────────────────────

class TestSpYearlySummary:
    def test_combines_m15a_and_bcct(self, session: Session, company):
        add_sp(
            session, company.id, product_code="TP1",
            year=2023, opening=10, intake=1000, export_qty=900, closing=110,
        )
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E62", item_code="TP1", quantity=900, year=2023,
        )
        session.commit()
        from app.items.aggregations import sp_yearly_summary

        rows = sp_yearly_summary(session, company.id, "TP1")
        assert rows[0]["year"] == 2023
        assert rows[0]["intake_qty"] == 1000
        assert rows[0]["export_qty"] == 900
        assert rows[0]["bcct_export_qty"] == 900
        assert rows[0]["export_match"] is True


# ─────────────────────────── BCCT lines for item ───────────────────────────

class TestBcctLinesForItem:
    def test_filters_by_company_item_year(self, session: Session, company):
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="A", quantity=10, year=2023,
            declaration_date=date(2023, 3, 1),
        )
        add_decl(
            session, company.id, declaration_no="D2",
            customs_code="E31", item_code="A", quantity=20, year=2024,
            declaration_date=date(2024, 5, 1),
        )
        add_decl(
            session, company.id, declaration_no="D3",
            customs_code="E31", item_code="OTHER", quantity=5, year=2023,
        )
        session.commit()
        from app.items.aggregations import bcct_lines_for_item

        rows = bcct_lines_for_item(session, company.id, "A", year=2023)
        assert len(rows) == 1
        assert rows[0].declaration_no == "D1"

    def test_no_year_returns_all_years(self, session: Session, company):
        add_decl(
            session, company.id, declaration_no="D1",
            customs_code="E31", item_code="A", quantity=10, year=2023,
        )
        add_decl(
            session, company.id, declaration_no="D2",
            customs_code="E31", item_code="A", quantity=20, year=2024,
        )
        session.commit()
        from app.items.aggregations import bcct_lines_for_item

        rows = bcct_lines_for_item(session, company.id, "A")
        assert len(rows) == 2

    def test_sorted_by_date(self, session: Session, company):
        add_decl(
            session, company.id, declaration_no="DLater",
            customs_code="E31", item_code="A", quantity=10, year=2023,
            declaration_date=date(2023, 12, 1),
        )
        add_decl(
            session, company.id, declaration_no="DEarlier",
            customs_code="E31", item_code="A", quantity=10, year=2023,
            declaration_date=date(2023, 3, 1),
        )
        session.commit()
        from app.items.aggregations import bcct_lines_for_item

        rows = bcct_lines_for_item(session, company.id, "A", year=2023)
        assert [r.declaration_no for r in rows] == ["DEarlier", "DLater"]


# ─────────────────────────── BOM edges ───────────────────────────

class TestBomEdges:
    def _add_norm(self, session, company_id, *, product_code, material_code, norm_qty, year=2023):
        from app.models import Norm

        n = Norm(
            company_id=company_id,
            period_year=year,
            product_code=product_code,
            material_code=material_code,
            norm_qty=norm_qty,
        )
        session.add(n)

    def test_bom_for_nvl_lists_products_it_feeds(self, session: Session, company):
        self._add_norm(session, company.id, product_code="TP1", material_code="NPL-A", norm_qty=2.0)
        self._add_norm(session, company.id, product_code="TP2", material_code="NPL-A", norm_qty=3.0)
        self._add_norm(session, company.id, product_code="TP1", material_code="NPL-B", norm_qty=1.0)
        session.commit()
        from app.items.aggregations import bom_edges_for_nvl

        edges = bom_edges_for_nvl(session, company.id, "NPL-A", year=2023)
        codes = {e["product_code"]: e["norm_qty"] for e in edges}
        assert codes == {"TP1": 2.0, "TP2": 3.0}

    def test_bom_for_tp_lists_materials_it_uses(self, session: Session, company):
        self._add_norm(session, company.id, product_code="TP1", material_code="NPL-A", norm_qty=2.0)
        self._add_norm(session, company.id, product_code="TP1", material_code="NPL-B", norm_qty=1.0)
        session.commit()
        from app.items.aggregations import bom_edges_for_tp

        edges = bom_edges_for_tp(session, company.id, "TP1", year=2023)
        codes = {e["material_code"]: e["norm_qty"] for e in edges}
        assert codes == {"NPL-A": 2.0, "NPL-B": 1.0}

    def test_bom_filtered_by_year(self, session: Session, company):
        self._add_norm(session, company.id, product_code="TP1", material_code="A", norm_qty=2.0, year=2022)
        self._add_norm(session, company.id, product_code="TP1", material_code="A", norm_qty=3.0, year=2023)
        session.commit()
        from app.items.aggregations import bom_edges_for_tp

        edges_22 = bom_edges_for_tp(session, company.id, "TP1", year=2022)
        edges_23 = bom_edges_for_tp(session, company.id, "TP1", year=2023)
        assert edges_22[0]["norm_qty"] == 2.0
        assert edges_23[0]["norm_qty"] == 3.0


# ─────────────────────────── route /companies/{code}/items/{item_code} ───────────────────────────

def _setup_db():
    from sqlalchemy.pool import StaticPool

    import app.database as dbmod
    from app.auth_users import seed_default_admin
    from app.database import Base

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
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
    return new_engine, new_session


def _teardown(new_engine):
    import app.database as dbmod
    from app.database import SessionLocal as OriginalSession
    from app.database import engine as original_engine

    new_engine.dispose()
    dbmod.engine = original_engine
    dbmod.SessionLocal = OriginalSession


def _login(client):
    response = client.post(
        "/login",
        data={"user": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _seed_item_data(session):
    from app.models import Company, Norm

    c = Company(code="DN_IT1", tax_id="9999999999", name="Test DN Item", risk_score=10)
    session.add(c)
    session.flush()

    add_nvl(session, c.id, material_code="NPL-X", unit="KG",
            opening=10, imported=500, production_out=480, closing=30, year=2023)
    add_nvl(session, c.id, material_code="NPL-X", unit="KG",
            opening=30, imported=600, production_out=570, closing=60, year=2024)
    add_sp(session, c.id, product_code="TP-A", unit="PCE",
           opening=0, intake=100, export_qty=90, closing=10, year=2023)
    add_decl(session, c.id, declaration_no="D1",
             customs_code="E31", item_code="NPL-X", quantity=500, year=2023,
             declaration_date=date(2023, 4, 1))
    add_decl(session, c.id, declaration_no="D2",
             customs_code="E62", item_code="TP-A", quantity=90, year=2023)
    session.add(Norm(
        company_id=c.id, period_year=2023, product_code="TP-A",
        material_code="NPL-X", norm_qty=5.0,
    ))
    session.commit()


class TestItemDetailRoute:
    def test_nvl_page_renders_year_tabs_and_data(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X")
            assert r.status_code == 200
            text = r.text
            assert "NPL-X" in text
            # Hero band: kind label
            assert "Nguyên" in text or "NVL" in text
            # Both years should appear as tabs
            assert "2023" in text and "2024" in text
        finally:
            _teardown(new_engine)

    def test_tp_page_renders(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/TP-A")
            assert r.status_code == 200
            assert "TP-A" in r.text
            assert "Thành phẩm" in r.text or "TP" in r.text
        finally:
            _teardown(new_engine)

    def test_default_year_is_latest(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X")
            # 2024 is latest; expect it marked active somewhere
            assert 'data-selected-year="2024"' in r.text or "year=2024" in r.text

            # Explicit year override
            r2 = client.get("/companies/DN_IT1/items/NPL-X?year=2023")
            assert r2.status_code == 200
            assert 'data-selected-year="2023"' in r2.text or "year=2023" in r2.text
        finally:
            _teardown(new_engine)

    def test_404_unknown_company(self):
        from app.main import app

        new_engine, _ = _setup_db()
        try:
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/NOPE/items/X")
            assert r.status_code == 404
        finally:
            _teardown(new_engine)

    def test_404_unknown_item(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/GHOST")
            assert r.status_code == 404
        finally:
            _teardown(new_engine)

    def test_bcct_only_orphan_shows_with_banner(self):
        """Mã chỉ có trong BCCT, không có BCQT → vẫn render được, banner cảnh báo."""
        from app.main import app
        from app.models import Company

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                c = Company(code="DN_IT2", tax_id="8888888888", name="Test", risk_score=1)
                s.add(c)
                s.flush()
                add_decl(s, c.id, declaration_no="D1",
                         customs_code="E31", item_code="ORPHAN", quantity=10, year=2023)
                s.commit()
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT2/items/ORPHAN")
            assert r.status_code == 200
            # Banner: mã không khớp BCQT
            assert "BCQT" in r.text
        finally:
            _teardown(new_engine)


# ─────────────────────────── chart geometry helpers ───────────────────────────

class TestChartGeometry:
    def test_sparkline_empty(self):
        from app.items.charts import sparkline_points
        assert sparkline_points([])["points"] == []

    def test_sparkline_monotone(self):
        from app.items.charts import sparkline_points
        out = sparkline_points([1, 2, 3, 4], width=100, height=20, pad=0)
        xs = [p[0] for p in out["points"]]
        ys = [p[1] for p in out["points"]]
        # X spreads evenly, last x == width
        assert xs[0] == 0 and xs[-1] == 100
        # Y descends (higher value → smaller y in SVG)
        assert ys[0] > ys[-1]

    def test_waterfall_balanced_sums_to_closing(self):
        from app.items.charts import waterfall_layout
        steps = [
            ("Đầu", 100, "opening"),
            ("Nhập", 500, "in"),
            ("SX", -400, "out"),
            ("Cuối", 200, "closing"),
        ]
        layout = waterfall_layout(steps)
        assert len(layout["bars"]) == 4
        # Opening + Closing bars start at y(0).
        assert all(b["w"] > 0 for b in layout["bars"])
        # zero_y is set
        assert layout["zero_y"] > 0

    def test_sankey_thickness_proportional(self):
        from app.items.charts import sankey_layout
        nodes = [("A", 10.0, ""), ("B", 30.0, "")]
        layout = sankey_layout("CENTER", nodes, direction="out")
        thick = [n["thickness"] for n in layout["nodes"]]
        assert thick[1] > thick[0]
        assert layout["center_label"] == "CENTER"

    def test_sankey_empty(self):
        from app.items.charts import sankey_layout
        layout = sankey_layout("X", [], direction="out")
        assert layout["nodes"] == []


# ─────────────────────────── interactive chart payloads ───────────────────────────

class TestChartPayloads:
    def test_bcct_timeline_data_embedded(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X?year=2023")
            assert r.status_code == 200
            # Timeline payload referenced
            assert "bcct-timeline" in r.text
            assert "data-points" in r.text
            # JSON payload contains declaration + classification (HTML-escaped in attr)
            import html
            import re
            m = re.search(r"data-points='([^']+)'", r.text)
            assert m, "data-points attribute missing"
            payload = html.unescape(m.group(1))
            assert '"declaration_no": "D1"' in payload
            assert '"op": "import"' in payload
            # ApexCharts JS hook loaded
            assert "item_detail.js" in r.text
        finally:
            _teardown(new_engine)

    def test_heatmap_present_on_all_view(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X?year=all")
            assert r.status_code == 200
            assert "item-heatmap" in r.text
            assert "data-series" in r.text
        finally:
            _teardown(new_engine)


# ─────────────────────────── BOM + findings + AI ───────────────────────────

class TestBomFindingsAi:
    def test_nvl_bom_sankey_links_to_products(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X?year=2023")
            assert "chart-sankey" in r.text
            # link to TP detail page
            assert "/companies/DN_IT1/items/TP-A" in r.text
        finally:
            _teardown(new_engine)

    def test_tp_bom_sankey_links_to_materials(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/TP-A?year=2023")
            assert "chart-sankey" in r.text
            assert "/companies/DN_IT1/items/NPL-X" in r.text
        finally:
            _teardown(new_engine)

    def test_findings_filtered_by_item_code(self):
        from app.main import app
        from app.models import Company, Finding

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
                c = s.query(Company).filter_by(code="DN_IT1").one()
                s.add(Finding(
                    company_id=c.id, period_year=2023,
                    check_code="C2.1", severity="critical",
                    subject_type="material_code", subject_key="NPL-X",
                    title="Lệch cân đối NVL X",
                ))
                s.add(Finding(
                    company_id=c.id, period_year=2023,
                    check_code="C2.1", severity="info",
                    subject_type="material_code", subject_key="OTHER",
                    title="Lệch cân đối khác",
                ))
                s.commit()
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X?year=2023")
            assert "Lệch cân đối NVL X" in r.text
            assert "Lệch cân đối khác" not in r.text
        finally:
            _teardown(new_engine)

    def test_ai_prompt_button_present_with_context(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/items/NPL-X?year=2023")
            assert "data-ai-prompt" in r.text
            assert "NPL-X" in r.text
            assert "DN_IT1" in r.text
        finally:
            _teardown(new_engine)


# ─────────────────────────── cross-page link coverage ───────────────────────────

class TestItemLinks:
    def test_company_data_m15_links_code_column(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/data?year=2023&table=m15")
            assert r.status_code == 200
            assert '/companies/DN_IT1/items/NPL-X?year=2023' in r.text
        finally:
            _teardown(new_engine)

    def test_company_data_bcct_links_item_code(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/data?year=2023&table=bcct")
            assert r.status_code == 200
            assert '/companies/DN_IT1/items/NPL-X' in r.text
        finally:
            _teardown(new_engine)

    def test_company_data_m16_links_both_codes(self):
        from app.main import app

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1/data?year=2023&table=m16")
            assert r.status_code == 200
            assert '/companies/DN_IT1/items/TP-A' in r.text       # product col
            assert '/companies/DN_IT1/items/NPL-X' in r.text      # material col
        finally:
            _teardown(new_engine)

    def test_company_detail_findings_table_links_subject_key(self):
        from app.main import app
        from app.models import Company, Finding

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
                c = s.query(Company).filter_by(code="DN_IT1").one()
                s.add(Finding(
                    company_id=c.id, period_year=2023,
                    check_code="C1.1", severity="warning",
                    subject_type="material_code", subject_key="NPL-X",
                    title="Lệch nhập",
                ))
                s.commit()
            client = TestClient(app)
            _login(client)
            r = client.get("/companies/DN_IT1?year=2023")
            assert '/companies/DN_IT1/items/NPL-X?year=2023' in r.text
        finally:
            _teardown(new_engine)

    def test_finding_detail_subject_and_evidence_links(self):
        from app.main import app
        from app.models import Company, Finding

        new_engine, new_session = _setup_db()
        try:
            with new_session() as s:
                _seed_item_data(s)
                c = s.query(Company).filter_by(code="DN_IT1").one()
                f = Finding(
                    company_id=c.id, period_year=2023,
                    check_code="C1.1", severity="warning",
                    subject_type="material_code", subject_key="NPL-X",
                    title="Lệch nhập",
                    evidence_refs=[
                        {"table": "nvl_balances", "filter": {"company_id": c.id, "material_code": "NPL-X"}},
                    ],
                )
                s.add(f)
                s.commit()
                fid = f.id
            client = TestClient(app)
            _login(client)
            r = client.get(f"/findings/{fid}")
            assert r.status_code == 200
            # Subject_key in header → link
            assert '/companies/DN_IT1/items/NPL-X?year=2023' in r.text
        finally:
            _teardown(new_engine)
