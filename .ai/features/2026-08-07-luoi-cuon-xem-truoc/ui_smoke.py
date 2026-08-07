"""E2E ảnh — lưới cuộn ảo + hai công tắc ở trang xem file (issue #91).

Dựng ba file THẬT trong thư mục dữ liệu throwaway rồi chụp lưới chạy trên chúng:

  sau.xlsx  — 200.000 dòng × 257 cột, có ô công thức ở E3 giữ 28,5 tỷ. File này
              gánh bốn tiêu chí: cuộn hai chiều, tới cột 257, nhảy tới dòng
              200.000, và màn chờ trích xuất (dựng kho mất ~47 giây trên máy dev).
  cu.xls    — BIFF thật. Công tắc công thức phải hiện dòng chữ nói định dạng này
              không đọc được công thức, lưới vẫn đầy dữ liệu.
  ssml.xls  — XML SpreadsheetML mang đuôi `.xls` (38 file trong kho như vậy).
              Trang phải ghi rõ "xem trước được, chưa nạp được".

Chụp:
  01 màn chờ trích xuất — tiến trình + câu nói rõ lần đầu, lần sau tức thì
  02 lưới dựng xong — số dòng dính mép trái, chữ cái cột dính mép trên
  03 cuộn hết sang phải — tới cột thứ 257 (IW)
  04 nhảy tới dòng 200.000 — dòng cuối vẫn đủ 257 cột
  05 công tắc "Hiện cột hệ thống đang đọc" — cột parser đọc + nhãn trường
  06 công tắc "Hiện công thức trong ô" — E3 hiện `=D3*1000` thay vì 28,5 tỷ
  07 file .xls cũ — câu chữ "không đọc được công thức", lưới vẫn có dữ liệu
  08 file XML SpreadsheetML — trạng thái "xem trước được, chưa nạp được"

Đăng nhập bằng COOKIE ký sẵn, không qua biểu mẫu: biểu mẫu có giới hạn số lần và
cookie phiên là Secure/HttpOnly nên đường đó trượt trên http.

Dữ liệu seed là dữ liệu BỊA, DB + thư mục dữ liệu + kho đệm đều nằm trong thư mục
throwaway. KHÔNG đụng DB live hay cổng 8200. Xem cách chạy ở brief.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import xlsxwriter
from playwright.sync_api import sync_playwright

from app.auth import SESSION_COOKIE_NAME, SessionUser, make_session_cookie
from app.database import Base, SessionLocal, engine
from app.models import Company, DataFile
from app.settings import settings

# Ba bộ ghi file thật đã có sẵn ở test — không viết lại bộ ghi BIFF lần thứ hai.
from tests.excel_fixtures import write_biff_xls, write_spreadsheetml

BASE = os.environ.get("M_BASE", "http://127.0.0.1:8377")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

DN = "DEMO_LUOI"
SLUG = "demo-luoi"
ADMIN = "shot_luoi"
YEAR = 2025
REL_DIR = f"{DN}/{YEAR}/HANG_CHI_TIET"
DEEP_ROWS = 200_000
WIDE_COLS = 257
HIDE_CSS = ".demo-banner{display:none!important}"

# Cột parser đọc ở file sâu — nguồn của công tắc "Hiện cột hệ thống đang đọc".
PARSE_DETAIL = {
    "sheet": "Chi tiết",
    "column_map": {
        "material_code": 0, "material_name": 1, "unit": 2,
        "opening_qty": 3, "import_qty": 4,
    },
    "columns": [
        {"field": "material_code", "label": "Mã nguyên liệu", "review": "verified"},
        {"field": "material_name", "label": "Tên nguyên liệu", "review": "verified"},
        {"field": "unit", "label": "Đơn vị tính", "review": "verified"},
        {"field": "opening_qty", "label": "Tồn đầu kỳ", "review": "verified"},
        {"field": "import_qty", "label": "Nhập trong kỳ", "review": "needs_review"},
    ],
}


def _write_deep_wide(path: Path) -> None:
    """200.000 dòng × 257 cột, ghi theo dòng (chế độ bộ nhớ hằng) nên ~11 giây."""
    wb = xlsxwriter.Workbook(str(path), {"constant_memory": True})
    ws = wb.add_worksheet("Chi tiết")
    head = ["Mã nguyên liệu", "Tên nguyên liệu", "ĐVT", "Tồn đầu kỳ", "Nhập trong kỳ"]
    head += [f"Cột {i + 1}" for i in range(len(head), WIDE_COLS)]
    for c, v in enumerate(head):
        ws.write(0, c, v)
    wide_from = DEEP_ROWS - 5
    for r in range(1, wide_from):
        ws.write(r, 0, f"NPL-{r:06d}")
        ws.write(r, 1, "Vải chính khổ 1m50")
        ws.write(r, 2, "MTR")
        ws.write(r, 3, r * 1.5)
        if r == 2:
            # Ô công thức giữ đúng con số 28,5 tỷ của bộ file gộp tay từng làm mất
            # số đó: bộ đọc cũ trả 0 và không kiểm tra nào bắt được.
            ws.write_formula(r, 4, "=D3*1000", None, 28563550970.35)
        else:
            ws.write(r, 4, r * 2.25)
    for r in range(wide_from, DEEP_ROWS):
        for c in range(WIDE_COLS):
            ws.write(r, c, f"D{r + 1}C{c + 1}")
    wb.close()


def seed() -> dict[str, int]:
    Base.metadata.create_all(engine)
    root = Path(settings.raw_data_path) / REL_DIR
    root.mkdir(parents=True, exist_ok=True)

    print("dựng file sâu 200.000 dòng × 257 cột…")
    _write_deep_wide(root / "sau.xlsx")
    write_biff_xls(
        root / "cu.xls",
        [["Mã nguyên liệu", "ĐVT", "Tồn đầu kỳ", "Trị giá"]]
        + [[f"NPL-{i:03d}", "MTR", i * 10.0, i * 1000.0] for i in range(1, 40)],
        sheet_name="BCQT_NPL",
    )
    write_spreadsheetml(
        root / "ssml.xls",
        [["Mã nguyên liệu", "ĐVT", "Tồn đầu kỳ", "Trị giá"]]
        + [[f"NPL-{i:03d}", "MTR", i * 10.0, i * 1000.0] for i in range(1, 40)],
        sheet_name="Chi tiết",
        formulas={(3, 3): "=RC[-1]*1000"},
    )

    with SessionLocal() as db:
        from app.auth_users import create_user, get_user_by_username

        if not get_user_by_username(db, ADMIN):
            create_user(db, ADMIN, "shot12345", "admin")
        company = db.query(Company).filter_by(code=DN).one_or_none()
        if company is None:
            company = Company(
                code=DN, name="Công ty TNHH Dệt May Bình Minh (Demo)",
                tax_id="0100000009", slug=SLUG, industry="Dệt may",
            )
            db.add(company)
            db.flush()
        db.query(DataFile).filter_by(company_id=company.id).delete()
        for name, slot, detail in (
            ("sau.xlsx", "bcct", PARSE_DETAIL),
            ("cu.xls", "m15", None),
            ("ssml.xls", "bcct", None),
        ):
            path = root / name
            db.add(DataFile(
                company_id=company.id, period_year=YEAR, slot=slot,
                original_filename=name, stored_path=f"{REL_DIR}/{name}",
                size_bytes=path.stat().st_size,
                parse_status="parsed" if detail else "pending",
                parse_detail=json.dumps(detail) if detail else None,
            ))
        db.commit()
        return {
            f.original_filename: f.id
            for f in db.query(DataFile).filter_by(company_id=company.id).all()
        }


def _shot(pg, name, *, full=False) -> None:
    pg.add_style_tag(content=HIDE_CSS)
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / name), full_page=full)
    print("shot", name)


def capture(ids: dict[str, int]) -> None:
    cookie = make_session_cookie(SessionUser(name=ADMIN, role="admin"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 950},
                                  device_scale_factor=2, locale="vi-VN")
        ctx.add_cookies([{
            "name": SESSION_COOKIE_NAME, "value": cookie,
            "domain": "127.0.0.1", "path": "/",
        }])
        pg = ctx.new_page()

        deep = f"/companies/{SLUG}/documents/file/{ids['sau.xlsx']}/preview"

        # 01 — màn chờ: kho đệm trống nên máy chủ trả 202 ngay (PREVIEW_WAIT_SECONDS=0),
        # lưới hiện tiến trình và tự hỏi lại. Đợi một nhịp cho số dòng chạy lên.
        pg.goto(f"{BASE}{deep}", wait_until="domcontentloaded")
        pg.wait_for_selector(".cg-overlay-wait")
        pg.wait_for_function(
            "() => { const e = document.querySelector('.cg-overlay-progress');"
            " return e && !/^Đã đọc 0 /.test(e.textContent); }",
            timeout=60_000,
        )
        _shot(pg, "01_man_cho_trich_xuat.png")

        # 02 — lưới dựng xong, KHÔNG cần bấm lại. Trích xuất 200.000 dòng ~47 giây.
        pg.wait_for_selector(".cg-cell", timeout=300_000)
        pg.wait_for_timeout(600)
        _shot(pg, "02_luoi_dong_dau.png")

        # 03 — cuộn hết sang phải: cột thứ 257 là IW, dòng tiêu đề còn dính mép trên.
        pg.evaluate("() => { const b = document.querySelector('.cg-body');"
                    " b.scrollLeft = b.scrollWidth; b.dispatchEvent(new Event('scroll')); }")
        pg.wait_for_function(
            "() => [...document.querySelectorAll('.cg-col-letter')]"
            ".some(e => e.textContent === 'IW')", timeout=30_000)
        pg.wait_for_timeout(400)
        _shot(pg, "03_cot_thu_257.png")

        # 04 — nhảy tới dòng 200.000 (vẫn đang ở mép phải): dòng cuối đủ 257 cột.
        pg.fill("#cg-row-input", str(DEEP_ROWS))
        pg.click("#cg-row-go")
        pg.wait_for_function(
            "() => [...document.querySelectorAll('.cg-cell')]"
            ".some(e => e.textContent === 'D200000C257')", timeout=30_000)
        pg.wait_for_timeout(400)
        _shot(pg, "04_nhay_toi_dong_200000.png")

        # 05 — công tắc cột hệ thống đọc, xem từ dòng 1 để thấy cả tiêu đề file.
        pg.evaluate("() => { const b = document.querySelector('.cg-body');"
                    " b.scrollTop = 0; b.scrollLeft = 0; b.dispatchEvent(new Event('scroll')); }")
        pg.check("#cg-toggle-mapped")
        pg.wait_for_selector(".cg-col-mapped")
        pg.wait_for_timeout(500)
        _shot(pg, "05_cong_tac_cot_he_thong_doc.png")

        # 06 — công tắc công thức: E3 hiện `=D3*1000` thay cho 28.563.550.970,35.
        pg.check("#cg-toggle-formula")
        pg.wait_for_selector(".cg-cell-formula", timeout=30_000)
        pg.wait_for_timeout(500)
        _shot(pg, "06_cong_tac_cong_thuc_trong_o.png")

        # 07 — .xls BIFF: công tắc công thức hiện dòng chữ, lưới VẪN có dữ liệu.
        pg.goto(f"{BASE}/companies/{SLUG}/documents/file/{ids['cu.xls']}/preview",
                wait_until="domcontentloaded")
        pg.wait_for_selector(".cg-cell", timeout=120_000)
        pg.check("#cg-toggle-formula")
        pg.wait_for_selector(".cg-note-warn")
        pg.wait_for_timeout(500)
        _shot(pg, "07_xls_cu_khong_doc_duoc_cong_thuc.png")

        # 08 — XML SpreadsheetML: xem trước được, chưa nạp được.
        pg.goto(f"{BASE}/companies/{SLUG}/documents/file/{ids['ssml.xls']}/preview",
                wait_until="domcontentloaded")
        pg.wait_for_selector(".cg-cell", timeout=120_000)
        pg.wait_for_selector(".cg-note-warn")
        pg.wait_for_timeout(500)
        _shot(pg, "08_spreadsheetml_xem_duoc_chua_nap_duoc.png")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    capture(seed())
