"""Chụp badge truy nguồn cách đọc file (M15a mở rộng + M16 ĐM thực tế) trên 004 EPE.

KHÔNG seed dữ liệu DN — chụp thẳng dữ liệu THẬT `PILOT_004_EPE` đã nạp ở DB local
(đã có DataFile.parse_layout/parse_detail sau ingest). Chỉ seed 1 user admin tạm để
đăng nhập, xong xoá user (không đụng dữ liệu 004).

Chạy (server code MỚI, throwaway riêng — ĐỪNG dùng :8200 của user):
    M_BASE=http://127.0.0.1:8322 PYTHONPATH=. .venv/bin/python \
        .ai/features/2026-07-24-m15a-m16-004/ui_smoke.py
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
ADMIN = ("shot_m15a", "shot12345")
DN = "PILOT_004_EPE"
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

        # 01: trang Tài liệu — badge bố cục trên từng file BCQT của 004.
        pg.goto(f"{BASE}/companies/{DN}/documents", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.evaluate("document.querySelectorAll('details.doc-year').forEach(d => d.open = true)")
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / "01_documents_badges.png"), full_page=False)
        print("shot 01_documents_badges")

        # 02: trang Dữ liệu gốc M15a — note đẳng thức + cột xuất khẩu chọn theo nhãn.
        pg.goto(f"{BASE}/companies/{DN}/data?year=2025&table=m15a", wait_until="networkidle")
        pg.add_style_tag(content=HIDE_CSS)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(OUT / "02_data_m15a_parse_note.png"), full_page=False)
        print("shot 02_data_m15a_parse_note")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print("cleaned up shot_m15a user")
