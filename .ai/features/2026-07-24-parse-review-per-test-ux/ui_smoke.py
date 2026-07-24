"""E2E screenshots WS1→WS3 (parse review + chạy test lẻ + AI tổng quan/staleness).

Chụp trên DN tổng hợp `DN_E2E` (tên/MST giả — an toàn commit, KHÔNG dữ liệu khách).
Dữ liệu do smoke dựng qua LUỒNG THẬT trên server throwaway: upload M15 chuẩn (2025,
verified→parsed) + M15 đổi tên cột (2024, needs_review gate); chạy check 2025 (C2.1×3,
C2.2/C2.3); sinh AI tổng quan bằng LLM thật (deepseek/OpenRouter).

Chạy (server throwaway riêng — ĐỪNG dùng :8200 của user):
    DATABASE_URL=sqlite:///<throwaway>.sqlite RAW_DATA_PATH=<throwaway raw> \
      .venv/bin/uvicorn app.main:app --port 8323   # ở tiến trình khác
    M_BASE=http://127.0.0.1:8323 PYTHONPATH=. .venv/bin/python \
      .ai/features/2026-07-24-parse-review-per-test-ux/ui_smoke.py

Đăng nhập bằng user throwaway `shot_e2e/shot12345` (seed sẵn ở DB throwaway).
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("M_BASE", "http://127.0.0.1:8323")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
USER = ("shot_e2e", "shot12345")
DN = "DN_E2E"
HIDE_CSS = ".demo-banner{display:none!important}#ai-fab{display:none!important}"
VIEW = {"width": 1300, "height": 1400}


def _login(pg) -> None:
    pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
    pg.fill("input[name=user]", USER[0])
    pg.fill("input[name=password]", USER[1])
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")


def _shot(pg, name: str) -> None:
    pg.add_style_tag(content=HIDE_CSS)
    pg.wait_for_timeout(350)
    pg.screenshot(path=str(OUT / name), full_page=True)
    print("shot", name)


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2)
        pg = ctx.new_page()
        pg.set_default_timeout(70_000)
        _login(pg)

        # ── WS1: trang Tài liệu — badge tin cậy parse (2025 "Đã kiểm") + cổng review
        #    (2024 "Cần xác nhận": cột "Xuất sản xuất" đổi tên → position-only) ──
        pg.goto(f"{BASE}/companies/{DN}/documents?year=2025", wait_until="networkidle")
        pg.evaluate("document.querySelectorAll('details.doc-year').forEach(d => d.open = true)")
        _shot(pg, "01_ws1_documents.png")

        # ── WS1: màn xác nhận map cột — nguồn bằng chứng mỗi cột + registry test→cột ──
        pg.goto(f"{BASE}/companies/{DN}/documents/file/2/review", wait_until="networkidle")
        _shot(pg, "02_ws1_review_screen.png")

        # ── WS2: modal "Chọn test chạy" (chạy tập con, gom theo họ C1/C2/…) ──
        pg.goto(f"{BASE}/companies/{DN}?year=2025", wait_until="networkidle")
        pg.click('[data-open-modal="run-tests-modal"]')
        pg.wait_for_timeout(400)
        pg.add_style_tag(content=HIDE_CSS)
        pg.screenshot(path=str(OUT / "03_ws2_run_modal.png"), full_page=True)
        print("shot 03_ws2_run_modal.png")

        # ── WS2: modal "Xuất Excel" (chỉ mã có finding + số phát hiện) ──
        pg.goto(f"{BASE}/companies/{DN}?year=2025", wait_until="networkidle")
        pg.click('[data-open-modal="export-tests-modal"]')
        pg.wait_for_timeout(400)
        pg.add_style_tag(content=HIDE_CSS)
        pg.screenshot(path=str(OUT / "04_ws2_export_modal.png"), full_page=True)
        print("shot 04_ws2_export_modal.png")

        # ── WS3: sinh AI tổng quan cho C2.1 (LLM thật) → panel truy nguồn ──
        pg.goto(f"{BASE}/companies/{DN}?year=2025&check=C2.1", wait_until="networkidle")
        pg.click('button:has-text("Tạo tổng quan")')  # điều hướng sau ~LLM latency
        pg.wait_for_load_state("networkidle")
        pg.goto(f"{BASE}/companies/{DN}?year=2025&check=C2.1", wait_until="networkidle")
        _shot(pg, "05_ws3_overview_fresh.png")

        # ── WS3: staleness — chạy lại C2.3 (đã có overview) → badge "đã cũ" + mốc based_on ──
        pg.goto(f"{BASE}/companies/{DN}?year=2025&check=C2.3", wait_until="networkidle")
        pg.click('button:has-text("Chạy lại C2.3")')  # → /jobs/{id}
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(3000)  # job worker xử lý (dữ liệu nhỏ, <1s)
        pg.goto(f"{BASE}/companies/{DN}?year=2025&check=C2.3", wait_until="networkidle")
        _shot(pg, "06_ws3_overview_stale.png")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    capture()
