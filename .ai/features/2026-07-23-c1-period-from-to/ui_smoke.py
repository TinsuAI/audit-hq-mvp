"""Chụp trang tài liệu DN với cửa sổ kỳ báo cáo sửa được (C1 period_from/to).

Seed DN tạm `SHOT_C1` + user tạm `shot_c1` (admin) + 2 kỳ:
  - 2025: sửa tay 01/04/2025–31/03/2026 (năm tài chính) → badge "sửa tay" + banner
  - 2024: mặc định dương lịch
Chụp trang /companies/SHOT_C1/documents với form sửa kỳ bung, xong xoá sạch.

Chạy (server code MỚI trên BASE, mặc định :8200):
    C1_BASE=http://127.0.0.1:8321 PYTHONPATH=. .venv/bin/python \
        .ai/features/2026-07-23-c1-period-from-to/ui_smoke.py
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import SessionLocal
from app.models import Company, CompanyPeriod, DeclarationLine, NvlBalance, User

BASE = os.environ.get("C1_BASE", "http://localhost:8200")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_c1", "shot12345")
DN = "SHOT_C1"
HIDE_CSS = ".demo-banner{display:none!important}#ai-fab{display:none!important}"


def _purge(db) -> None:
    comp = db.query(Company).filter(Company.code == DN).one_or_none()
    if comp:
        db.query(DeclarationLine).filter(DeclarationLine.company_id == comp.id).delete()
        db.query(NvlBalance).filter(NvlBalance.company_id == comp.id).delete()
        db.query(CompanyPeriod).filter(CompanyPeriod.company_id == comp.id).delete()
        db.delete(comp)
    for u in db.query(User).filter(User.username.like("shot_c1")).all():
        u.companies = []
        db.delete(u)
    db.commit()


def seed() -> None:
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")
        comp = Company(code=DN, name="Cơ khí Tân Tiến (Demo)", tax_id="0312345678")
        db.add(comp)
        db.flush()
        db.add_all([
            CompanyPeriod(
                company_id=comp.id, period_year=2025,
                period_from=date(2025, 4, 1), period_to=date(2026, 3, 31),
                is_manual=True,
            ),
            CompanyPeriod(
                company_id=comp.id, period_year=2024,
                period_from=date(2024, 1, 1), period_to=date(2024, 12, 31),
                is_manual=False,
            ),
            # Dữ liệu kỳ 2025 để company_detail/item_detail hiện nhãn kỳ tài chính +
            # tờ khai mang ngày SANG NĂM SAU (15/02/2026) dưới nhãn kỳ 2025.
            NvlBalance(
                company_id=comp.id, period_year=2025, material_code="THEP",
                material_name="Thép tấm", unit="KGM", import_qty=1000, closing_qty=700,
            ),
            DeclarationLine(
                company_id=comp.id, period_year=2025, declaration_no="102345",
                declaration_date=date(2026, 2, 15), customs_code="A11", item_code="THEP",
                hs_code="72091500", quantity=300, unit="KGM",
            ),
            DeclarationLine(
                company_id=comp.id, period_year=2025, declaration_no="101200",
                declaration_date=date(2025, 9, 3), customs_code="A11", item_code="THEP",
                hs_code="72091500", quantity=700, unit="KGM",
            ),
        ])
        db.commit()


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1300, "height": 1000}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
        pg.fill("input[name=user]", ADMIN[0])
        pg.fill("input[name=password]", ADMIN[1])
        pg.click("button[type=submit]")
        pg.wait_for_load_state("networkidle")

        pg.goto(f"{BASE}/companies/{DN}/documents", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.evaluate(
            "document.querySelectorAll('details.doc-year, details.doc-period-edit')"
            ".forEach(d => d.open = true)"
        )
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / "01_documents_period_editable.png"), full_page=False)
        print("shot 01_documents_period_editable")

        # 02: company_detail — nhãn kỳ tài chính dưới tab năm.
        pg.set_viewport_size({"width": 1300, "height": 720})
        pg.goto(f"{BASE}/companies/{DN}?year=2025", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(OUT / "02_company_detail_fiscal_label.png"), full_page=False)
        print("shot 02_company_detail_fiscal_label")

        # 03: item_detail — cuộn tới bảng BCCT: tờ khai ngày 15/02/2026 nằm dưới nhãn
        # kỳ 2025 (năm tài chính) — minh hoạ rõ nhất "ngày sang năm sau, quyết toán năm trước".
        pg.set_viewport_size({"width": 1300, "height": 820})
        pg.goto(f"{BASE}/companies/{DN}/items/THEP?year=2025", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.evaluate(
            "const h=[...document.querySelectorAll('h2')].find(e=>e.textContent.includes('Giao dịch BCCT'));"
            "if(h){window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 20);}"
        )
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / "03_item_detail_fiscal_dates.png"), full_page=False)
        print("shot 03_item_detail_fiscal_dates")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print("cleaned up shot_c1 data")
