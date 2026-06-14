"""Chụp ảnh các trang lõi cho trang showcase tính năng.

Deterministic — KHÔNG gọi LLM. Seed 1 admin tạm `shot_show` (role admin) để xem
toàn bộ DN, chụp các trang chính (tổng quan, chi tiết DN, truy nguồn phát hiện,
truy nguồn mã hàng, danh mục kiểm tra, công việc, cấu hình AI, tài liệu), rồi xoá.

Ảnh chat tái dùng từ `.ai/features/2026-06-14-chat-redesign/screenshots/`.

Chạy với dev server :8200 đang chạy:
    PYTHONPATH=. .venv/bin/python .ai/features/2026-06-14-showcase/ui_smoke.py
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import SessionLocal
from app.models import User

BASE = "http://localhost:8200"
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_show", "shot12345")

# (slug, url, full_page, open_selector) — open_selector mở đúng <details> nội dung
# (KHÔNG mở dropdown nav, vốn cũng là <details>). None = không mở gì.
SHOTS = [
    ("01_overview", "/companies", True, None),
    ("02_company_detail", "/companies/may-mac-hoa-sen?year=2022", True, "details.scoring-explainer"),
    ("03_finding_traceability", "/findings/1357", True, None),
    ("04_item_detail", "/companies/DN_001/items/BANGDINH", True, None),
    ("05_catalog", "/danh-muc-kiem-tra", True, None),
    ("07_admin_ai", "/admin/ai", True, None),
    ("08_docs_index", "/tai-lieu", True, None),
    ("09_scoring_methodology", "/tai-lieu/scoring-methodology", True, None),
    ("10_upload", "/companies/DN_001/upload", False, None),
]


def _seed(db) -> None:
    if not get_user_by_username(db, ADMIN[0]):
        create_user(db, ADMIN[0], ADMIN[1], "admin")
        db.commit()


def _purge(db) -> None:
    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        db.delete(u)
    db.commit()


def main() -> None:
    db = SessionLocal()
    _seed(db)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 1024})
            page = ctx.new_page()
            page.goto(f"{BASE}/login")
            page.fill("input[name=user]", ADMIN[0])
            page.fill("input[name=password]", ADMIN[1])
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            for name, url, full, open_selector in SHOTS:
                try:
                    page.goto(f"{BASE}{url}")
                    page.wait_for_load_state("networkidle")
                    if open_selector:
                        page.evaluate(
                            "(sel) => document.querySelectorAll(sel).forEach(d => d.open = true)",
                            open_selector,
                        )
                    page.wait_for_timeout(600)
                    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
                    print("shot", name, "<-", url)
                except Exception as e:  # noqa: BLE001 — best-effort capture
                    print("SKIP", name, url, repr(e))
            browser.close()
    finally:
        _purge(db)
        db.close()


if __name__ == "__main__":
    main()
