"""E2E ảnh — UI + ingest theo sổ quyết toán (5 ticket 2SỔ, ADR #19 Revision).

Seed MỘT pháp nhân nhiều sổ `DEMO_004` (EPE 104 mã · GC 37 mã · Chung) vào DB
THROWAWAY (trong job tmp), rồi chụp: strip theo sổ, dòng split per-check, pill book,
lọc segmented (EPE / GC sổ-sạch / Chung), finding_detail field "Sổ quyết toán", và
selector chọn sổ ở màn review WS1.

KHÔNG đụng DB live hay server :8200 của user — server throwaway riêng (port 8324),
DB + raw root trong $CLAUDE_JOB_DIR/tmp. Chạy qua runner (xem brief.md):
    DATABASE_URL=sqlite:///<workdb> RAW_DATA_PATH=<rawdir> \
        .venv/bin/uvicorn app.main:app --port 8324 --no-access-log &   # nền, kill theo PID
    M_BASE=http://127.0.0.1:8324 DATABASE_URL=sqlite:///<workdb> RAW_DATA_PATH=<rawdir> \
        PYTHONPATH=. .venv/bin/python .ai/features/2026-07-25-2so-ui-ingest/ui_smoke.py
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

from openpyxl import Workbook
from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import Base, SessionLocal, engine
from app.models import (
    Company,
    CompanyYearScore,
    DataFile,
    DataFileStatus,
    Finding,
    NvlBalance,
)
from app.settings import settings

BASE = os.environ.get("M_BASE", "http://localhost:8324")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_2so", "shot12345")
DN = "DEMO_004"
YEAR = 2025
HIDE_CSS = ".demo-banner{display:none!important}#ai-fab{display:none!important}"

_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]


def _m15_xlsx(codes: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    for i, code in enumerate(codes):
        ws.append([i + 1, code, "Vật tư " + code, "MTR", 10, 100, 0, 0, 80, 0, 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _purge(db) -> None:
    from app.models import User
    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    for c in db.query(Company).filter(Company.code == DN).all():
        cid = c.id
        for m in (NvlBalance, Finding, CompanyYearScore, DataFile):
            db.query(m).filter(m.company_id == cid).delete()
        db.delete(c)
    db.commit()


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")

        c = Company(code=DN, name="Công ty TNHH Chế Xuất & Gia Công (Demo)",
                    tax_id="0901051747", industry="Dệt may", address="KCN (Demo)")
        db.add(c)
        db.flush()

        # Balances theo sổ: EPE 104 mã NVL, GC 37 mã NVL (số neo ADR #19).
        for i in range(104):
            db.add(NvlBalance(company_id=c.id, period_year=YEAR, book="EPE",
                              material_code=f"EPE-{i:03d}", unit="MTR",
                              opening_qty=10, import_qty=100, production_out_qty=80, closing_qty=30))
        for i in range(37):
            db.add(NvlBalance(company_id=c.id, period_year=YEAR, book="GC",
                              material_code=f"GC-{i:03d}", unit="MTR",
                              opening_qty=5, import_qty=50, production_out_qty=40, closing_qty=15))

        # Findings: EPE 34 (nội-sổ) · GC 0 (sổ sạch) · Chung 40 (cross-layer, book=NULL) = 74.
        def add_findings(check, sev, book, n, prefix):
            for i in range(n):
                db.add(Finding(company_id=c.id, period_year=YEAR, check_code=check,
                               severity=sev, book=book, subject_type="material_code",
                               subject_key=f"{prefix}-{i:03d}",
                               title=f"{check} {prefix}-{i:03d}: chênh lệch cần rà soát"))
        add_findings("C4.3", "warning", "EPE", 14, "EPE")   # nội-sổ
        add_findings("C4.1", "warning", "EPE", 12, "EPE")
        add_findings("C6.1", "info", "EPE", 8, "EPE")
        add_findings("C1.1", "warning", None, 22, "CHUNG")  # cross-layer → Chung
        add_findings("C1.2", "critical", None, 18, "CHUNG")

        db.add(CompanyYearScore(company_id=c.id, period_year=YEAR, score=30,
                                tier="Có dấu hiệu bất thường", breakdown={}))

        # File settlement m15 (sổ EPE) cho màn review → selector chọn sổ hiện lên.
        raw = Path(settings.raw_data_path)
        rel = f"{DN}/{YEAR}/BCQT/NVL_EPE_{YEAR}.xlsx"
        fpath = raw / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_bytes(_m15_xlsx([f"EPE-{i:03d}" for i in range(8)]))
        detail = {
            "form_signature": "sig_demo_m15_epe",
            "layout": "labeled",
            "column_map": {"material_code": 1, "unit": 3, "opening_qty": 4,
                           "import_qty": 5, "production_out_qty": 8, "closing_qty": 10},
            "columns": [
                {"field": "material_code", "label": "Mã NVL", "evidence": "header-matched",
                 "evidence_label": "Khớp tiêu đề", "review": "verified"},
                {"field": "production_out_qty", "label": "Xuất sản xuất",
                 "evidence": "balance-checked", "evidence_label": "Khớp đẳng thức",
                 "review": "needs_review"},
            ],
        }
        db.add(DataFile(company_id=c.id, period_year=YEAR, slot="m15", book="EPE",
                        original_filename=f"NVL_EPE_{YEAR}.xlsx", stored_path=rel,
                        parse_status=DataFileStatus.OK, parse_layout="labeled",
                        parse_detail=json.dumps(detail, ensure_ascii=False)))
        db.commit()


def _login(pg) -> None:
    pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
    pg.fill("input[name=user]", ADMIN[0])
    pg.fill("input[name=password]", ADMIN[1])
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")


def _shot(pg, url, name, full=True, open_details=True):
    pg.goto(f"{BASE}{url}", wait_until="networkidle")
    pg.add_style_tag(content=HIDE_CSS)
    if open_details:
        pg.evaluate(
            "document.querySelectorAll('details.finding-group').forEach(d => d.open = true)"
        )
    pg.wait_for_timeout(450)
    pg.screenshot(path=str(OUT / name), full_page=full)
    print("shot", name)


def capture() -> None:
    with SessionLocal() as db:
        c = db.query(Company).filter(Company.code == DN).first()
        fid = db.query(Finding).filter(Finding.company_id == c.id,
                                       Finding.book == "EPE").first().id
        df_id = db.query(DataFile).filter(DataFile.company_id == c.id).first().id

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1300, "height": 1050}, device_scale_factor=2)
        pg = ctx.new_page()
        _login(pg)

        # 01 — trang DN: strip theo sổ + dòng split per-check + pill book (branch A).
        _shot(pg, f"/companies/{DN}?year={YEAR}", "01_company_strip_split_pills.png")
        # 02 — lọc segmented: chỉ sổ EPE.
        _shot(pg, f"/companies/{DN}?year={YEAR}&book=EPE", "02_filter_epe.png")
        # 03 — lọc sổ GC (sổ sạch): empty-state "đã được đánh giá — 0 phát hiện trên 37 mã NVL".
        _shot(pg, f"/companies/{DN}?year={YEAR}&book=GC", "03_filter_gc_clean_empty_state.png")
        # 04 — lọc Chung (phát hiện liên sổ, book=NULL).
        _shot(pg, f"/companies/{DN}?year={YEAR}&book=chung", "04_filter_chung.png")
        # 05 — finding_detail: field "Sổ quyết toán".
        _shot(pg, f"/findings/{fid}", "05_finding_detail_book_field.png")
        # 06 — màn review WS1: selector chọn sổ (branch B).
        _shot(pg, f"/companies/{DN}/documents/file/{df_id}/review",
              "06_review_book_selector.png")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print("cleaned up shot_2so user + DEMO_004")
