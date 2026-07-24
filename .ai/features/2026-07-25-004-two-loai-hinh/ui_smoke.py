"""E2E: 004 sau collapse hai loại hình — 1 pháp nhân `PILOT_004` (thay 2 row EPE/GC),
findings đã sửa: C1.2 99→4 (bỏ 91 finding "thiếu M15" giả), tổng 187→74.

Chụp trên BẢN COPY đã collapse (DB throwaway trong job tmp), KHÔNG đụng DB live hay
server :8200 của user.

Chạy (server throwaway riêng trỏ vào bản copy — ĐỪNG dùng :8200):
    DATABASE_URL=sqlite:///<workdb> .venv/bin/uvicorn app.main:app --port 8323   # nền
    M_BASE=http://127.0.0.1:8323 DATABASE_URL=sqlite:///<workdb> \
        PYTHONPATH=. .venv/bin/python .ai/features/2026-07-25-004-two-loai-hinh/ui_smoke.py
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import SessionLocal
from app.models import User

BASE = os.environ.get("M_BASE", "http://localhost:8200")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_004collapse", "shot12345")
DN = "PILOT_004"
HIDE_CSS = ".demo-banner{display:none!important}#ai-fab{display:none!important}"


def _purge(db) -> None:
    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    db.commit()


def seed() -> None:
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")
            db.commit()


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1300, "height": 1050}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
        pg.fill("input[name=user]", ADMIN[0])
        pg.fill("input[name=password]", ADMIN[1])
        pg.click("button[type=submit]")
        pg.wait_for_load_state("networkidle")

        # 01: danh sách DN — 004 giờ là MỘT pháp nhân PILOT_004 (trước là 2 row EPE/GC).
        pg.goto(f"{BASE}/companies", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / "01_companies_list.png"), full_page=False)
        print("shot 01_companies_list")

        # 02: trang DN 004 — findings đã sửa (C1.2 = 4, tổng 74) trên 1 pháp nhân.
        pg.goto(f"{BASE}/companies/{DN}", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / "02_company_004_findings.png"), full_page=True)
        print("shot 02_company_004_findings")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print("cleaned up shot_004collapse user")
