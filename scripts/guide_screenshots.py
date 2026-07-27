"""Chụp ảnh minh hoạ cho cẩm nang `app/static/docs/huong-dan/index.html`.

Ảnh ghi vào cùng thư mục với cẩm nang (tham chiếu tương đối, copy sang host tĩnh khác
là chạy). Đây là ảnh SẢN PHẨM của tài liệu, khác với ảnh chứng E2E ở
`.ai/features/<slug>/screenshots/`.

Mỗi ảnh mang **khung đỏ + số thứ tự** do `annotate()` vẽ vào DOM trước khi chụp; số phải
khớp `<ol>` bước của thẻ hướng dẫn tương ứng trong `index.html` — sửa một bên thì sửa cả
hai. Selector không khớp thì script DỪNG, không để lọt ảnh thiếu chú số.

Kịch bản chạy trên DB THROWAWAY (bản sao DB dev đã `alembic upgrade head`) và server
riêng — KHÔNG đụng DB live hay cổng 8200 của user. Hai nửa:

  A. Quy trình nhập liệu — tạo DN mới rồi tải file thật từ `demo-data/`, nạp, chạy
     kiểm tra. Mọi màn hình bước 1-3 chụp từ luồng này.
  B. Đọc kết quả — dùng dữ liệu pilot có sẵn trong bản sao (nhiều phát hiện, 2 sổ
     quyết toán ở PILOT_004) cho màn hình bước 4-6 và trang quản trị.

Chạy (đầy đủ ở `.ai/features/2026-07-28-user-guide-screenshots/brief.md`):

    SCRATCH=<thư mục tạm>                 # bản sao DB + thư mục file thô của lượt chụp
    # 1. sao DB dev bằng Connection.backup() (an toàn với WAL) sang $SCRATCH/guide.sqlite
    # 2. DATABASE_URL="sqlite:///$SCRATCH/guide.sqlite" .venv/bin/alembic upgrade head
    # 3. tạo user hdsd_admin / hdsd_canbo (mật khẩu hdsd12345) trong bản sao
    # 4. chạy uvicorn cổng 8342 với DATABASE_URL + RAW_DATA_PATH trỏ vào $SCRATCH
    G_BASE=http://127.0.0.1:8342 DATABASE_URL="sqlite:///$SCRATCH/guide.sqlite" \
        RAW_DATA_PATH="$SCRATCH/data" PYTHONPATH=. \
        .venv/bin/python scripts/guide_screenshots.py

`G_STAGES=bc` chỉ chạy một phần. Ảnh trợ lý và tổng quan AI gọi LLM THẬT ở lần đầu;
lần chạy sau dùng lại bản ghi đã có trong DB nên không tốn thêm lời gọi.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("G_BASE", "http://127.0.0.1:8342")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "docs" / "huong-dan"
DEMO_SRC = ROOT / "demo-data" / "Công ty TNHH May Mặc Hoa Sen (Demo)" / "2024"

ADMIN = ("hdsd_admin", "hdsd12345")
OFFICER = ("hdsd_canbo", "hdsd12345")
NEW_COMPANY = "Công ty TNHH May Mặc Hoa Sen"
NEW_YEAR = 2024

# Dữ liệu pilot sẵn có trong bản sao — dùng cho phần đọc kết quả.
PILOT = "PILOT_006"        # nhiều phát hiện, 2 kỳ
PILOT_YEAR = 2025
TWO_BOOKS = "PILOT_004"    # DNCX giữ 2 sổ quyết toán (EPE + GC)
OVERVIEW_CHECK = "C1.2"    # bài kiểm tra ít phát hiện — sinh tổng quan nhanh
SCOPED_TO_OFFICER = ("PILOT_002", "PILOT_004")  # phạm vi của tài khoản cán bộ mẫu
CHAT_QUESTION = (
    "Liệt kê các phát hiện nghiêm trọng của DEMO_004 năm 2025 theo từng bài kiểm tra, "
    "kèm số lượng."
)

VIEWPORT = {"width": 1440, "height": 900}


_ANNOTATE_JS = """
(marks) => {
  document.querySelectorAll('.ahq-anno').forEach(e => e.remove());
  const layer = document.createElement('div');
  layer.className = 'ahq-anno';
  Object.assign(layer.style, {
    position: 'absolute', left: '0', top: '0', width: '0', height: '0',
    zIndex: '2147483000', pointerEvents: 'none',
  });
  document.body.appendChild(layer);
  const br = document.body.getBoundingClientRect();
  const missing = [];
  for (const m of marks) {
    const el = document.querySelector(m.sel);
    if (!el) { missing.push(m.sel); continue; }
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) { missing.push(m.sel); continue; }
    const pad = m.pad === undefined ? 4 : m.pad;
    const box = document.createElement('div');
    Object.assign(box.style, {
      position: 'absolute',
      left: (r.left - br.left - pad) + 'px',
      top: (r.top - br.top - pad) + 'px',
      width: (r.width + pad * 2) + 'px',
      height: (r.height + pad * 2) + 'px',
      border: '2.5px solid #e11d48',
      borderRadius: '8px',
      boxShadow: '0 0 0 2px rgba(255,255,255,.9)',
    });
    const tag = document.createElement('div');
    tag.textContent = m.n;
    const side = m.side || 'left';
    Object.assign(tag.style, {
      position: 'absolute', top: '-14px',
      [side]: '-14px',
      width: '27px', height: '27px', borderRadius: '50%',
      background: '#e11d48', color: '#fff',
      font: '700 15px/27px ui-sans-serif, system-ui, sans-serif',
      textAlign: 'center', letterSpacing: '0',
      boxShadow: '0 1px 5px rgba(225,29,72,.55)',
    });
    box.appendChild(tag);
    layer.appendChild(box);
  }
  return missing;
}
"""


def annotate(page: Page, marks: list) -> None:
    """Vẽ khung đỏ + số thứ tự lên các phần tử — số khớp bước trong hướng dẫn.

    `marks` là list `(selector, số)` hoặc `(selector, số, tuỳ chọn)`; tuỳ chọn nhận
    `{"pad": 4, "side": "right"}`. Selector dùng cú pháp Playwright (kể cả
    `:has-text()`), phần tử được đánh dấu bằng thuộc tính tạm rồi mới vẽ. Không khớp
    thì DỪNG — không để lọt ảnh thiếu chú số.
    """
    payload = []
    for i, m in enumerate(marks):
        sel, n = m[0], m[1]
        opts = m[2] if len(m) > 2 else {}
        loc = page.locator(sel).first
        if not loc.count():
            raise AssertionError(f"chú số {n}: không có phần tử khớp {sel!r}")
        loc.evaluate("(el, key) => el.setAttribute('data-ahq-mark', key)", str(i))
        payload.append({"sel": f'[data-ahq-mark="{i}"]', "n": n, **opts})
    missing = page.evaluate(_ANNOTATE_JS, payload)
    if missing:
        raise AssertionError(f"chú số không dựng được khung: {missing}")


def clear_annotations(page: Page) -> None:
    page.evaluate(
        "() => { document.querySelectorAll('.ahq-anno').forEach(e => e.remove());"
        " document.querySelectorAll('[data-ahq-mark]')"
        ".forEach(e => e.removeAttribute('data-ahq-mark')); }"
    )


def shot(page: Page, name: str, *, full: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    print(f"  → {path.relative_to(ROOT)}")


def shot_el(page: Page, selector: str, name: str) -> None:
    el = page.locator(selector).first
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    el.screenshot(path=str(path))
    print(f"  → {path.relative_to(ROOT)}")


def shot_clip(page: Page, selector: str, name: str, margin: int = 44) -> None:
    """Chụp vùng quanh một phần tử — giữ được chú số nằm ngoài mép phần tử."""
    box = page.locator(selector).first.bounding_box()
    if box is None:
        raise AssertionError(f"không lấy được khung của {selector!r}")
    clip = {
        "x": max(0, box["x"] - margin),
        "y": max(0, box["y"] - margin),
        "width": box["width"] + margin * 2,
        "height": box["height"] + margin * 2,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), clip=clip)
    print(f"  → {path.relative_to(ROOT)}")


def login(page: Page, creds: tuple[str, str]) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill("input[name=user]", creds[0])
    page.fill("input[name=password]", creds[1])
    page.click('form[action="/login"] button[type=submit]')
    page.wait_for_load_state("networkidle")
    assert "Đăng nhập" not in page.title(), f"login trượt: {page.title()}"


def logout(page: Page) -> None:
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    page.evaluate(
        "() => { const f = document.querySelector('form[action=\"/logout\"]');"
        " if (f) f.submit(); }"
    )
    page.wait_for_load_state("networkidle")


def reset_demo_company() -> None:
    """Xoá DN minh hoạ của lượt chụp trước để chạy lại cho ra cùng kết quả.

    Chỉ chạm DN có tên `NEW_COMPANY` — chạy trên DB throwaway (bản sao).
    """
    import sqlalchemy as sa

    from app.database import SessionLocal

    with SessionLocal() as db:
        row = db.execute(
            sa.text("select id, code from companies where name like :n"),
            {"n": f"{NEW_COMPANY}%"},
        ).first()
        if row is None:
            return
        cid, ccode = row
        for table in (
            "findings", "check_runs", "company_year_scores", "data_files",
            "nvl_balances", "sp_balances", "norms", "declaration_lines",
            "company_periods", "user_companies", "jobs", "check_overviews",
        ):
            db.execute(sa.text(f"delete from {table} where company_id = :c"), {"c": cid})
        db.execute(sa.text("delete from companies where id = :c"), {"c": cid})
        db.commit()
        print(f"  reset: xoá DN cũ {ccode}")
    stored = Path(os.environ.get("RAW_DATA_PATH", "./data")) / ccode
    if stored.exists():
        for p in sorted(stored.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        stored.rmdir()


def company_slug(page: Page, name: str) -> str:
    """Mã/slug của DN vừa tạo — đọc từ link trong danh sách."""
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    href = (
        page.locator(f'a[href^="/companies/"]:has-text("{name}")')
        .first.get_attribute("href")
    )
    return href.rsplit("/", 1)[-1]


def wait_job_done(page: Page, job_url: str, timeout_s: int = 240) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        page.goto(job_url, wait_until="networkidle")
        body = page.inner_text("body")
        if "Hoàn tất" in body or "Thất bại" in body:
            return
        page.wait_for_timeout(2000)
    raise TimeoutError(f"job chưa xong sau {timeout_s}s: {job_url}")


# ── Phần A: quy trình nhập liệu trên DN mới ──────────────────────────────────


def part_a_ingest_flow(page: Page) -> str:
    print("A. Quy trình nhập liệu")
    reset_demo_company()
    page.goto(f"{BASE}/login", wait_until="networkidle")
    annotate(page, [("#user", 1), ("#password", 2),
                    ('form[action="/login"] button[type=submit]', 3)])
    shot_clip(page, ".login-card", "00-dang-nhap")
    login(page, ADMIN)

    # thanh điều hướng
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    page.wait_for_timeout(800)
    annotate(page, [
        ('.header-link[href="/chat"]', 1),
        ('.header-link[href="/danh-muc-kiem-tra"]', 2),
        ('.header-link[href="/tai-lieu"]', 3),
        ("#jobs-badge-link", 4),
        (".nav-dropdown:not(.nav-user-dropdown) > summary", 5),
        (".nav-user-dropdown > summary", 6, {"side": "right"}),
    ])
    shot_clip(page, ".app-header", "00b-thanh-dieu-huong", margin=26)

    # 01 danh sách DN (trước khi thêm) — xếp theo điểm rủi ro giảm dần
    clear_annotations(page)
    annotate(page, [
        ("#dn-search", 1),
        ("#dn-tier-filter", 2),
        ('#companies-table th[data-sort-key="score"]', 3),
        ("#companies-table tbody tr:first-child .tier-pill", 4),
        ("#companies-table tbody tr:first-child td:last-child", 5),
        ('a[href="/companies/new"].btn-primary', 6, {"side": "right"}),
    ])
    shot(page, "01-danh-sach-doanh-nghiep")

    # 02 form thêm DN, đã điền
    page.goto(f"{BASE}/companies/new", wait_until="networkidle")
    page.fill("#name", NEW_COMPANY)
    page.fill("#industry", "Dệt may")
    page.fill("#tax_id", "0312779955")
    page.fill("#address", "KCN Tân Tạo, Q. Bình Tân, TP.HCM")
    annotate(page, [("#name", 1), ("#industry", 2), ("#tax_id", 3), ("#address", 4),
                    ('form[action="/companies"] button[type=submit]', 5, {"side": "right"})])
    shot(page, "02-them-doanh-nghiep")
    clear_annotations(page)
    page.click('form[action="/companies"] button[type=submit]')
    page.wait_for_load_state("networkidle")

    slug = company_slug(page, NEW_COMPANY)
    docs_url = f"{BASE}/companies/{slug}/documents"

    # 03 trang tài liệu rỗng → thêm năm
    page.goto(docs_url, wait_until="networkidle")
    annotate(page, [
        ("select#add", 1),
        ('.doc-addyear button[type=submit]', 2),
        ('a[href$="/upload"].btn', 3, {"side": "right"}),
    ])
    shot(page, "03-tai-lieu-chua-co-file")

    # tải cả 4 loại trong một lần qua màn hình "Tải lên nhiều file"
    uploads = {
        "m15": DEMO_SRC / "BCQT" / f"Mau15_NVL_{NEW_YEAR}.xlsx",
        "m15a": DEMO_SRC / "BCQT" / f"Mau15a_SP_{NEW_YEAR}.xlsx",
        "m16": DEMO_SRC / "BCQT" / f"Mau16_DinhMuc_{NEW_YEAR}.xlsx",
        "bcct": DEMO_SRC / "HANG_CHI_TIET" / f"BCCT_{NEW_YEAR}.xlsx",
    }
    page.goto(f"{BASE}/companies/{slug}/upload?year={NEW_YEAR}", wait_until="networkidle")
    for slot, src in uploads.items():
        assert src.exists(), f"thiếu file mẫu {src}"
        page.locator(f"#file_{slot}").set_input_files(str(src))
    page.select_option("#year", str(NEW_YEAR))
    page.wait_for_timeout(200)
    annotate(page, [
        ("#year", 1),
        ('label[for="file_m15"]', 2),
        ('label[for="file_m15a"]', 3),
        ('label[for="file_m16"]', 4),
        ('label[for="file_bcct"]', 5),
        ('form[action*="/upload"] button[type=submit]', 6, {"side": "right"}),
    ])
    shot(page, "04-tai-len-nhieu-file")
    clear_annotations(page)
    page.click('form[action*="/upload"] button[type=submit]')
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)

    # 04b trang tài liệu sau khi tải đủ 4 loại
    page.goto(docs_url, wait_until="networkidle")
    annotate(page, [
        (".doc-year-summary .badge", 1),
        ('.doc-year-actions form[action*="/documents/ingest"] button', 2),
        ('.doc-year-actions form[action*="/run-checks"] button', 3),
        ('.doc-file-row:first-child .doc-file-badge:first-child', 4),
        ('.doc-file-row:first-child .badge:has-text("Đã kiểm")', 5),
        ('.doc-file-row:first-child a:has-text("Sửa cột")', 6, {"side": "right"}),
    ])
    shot(page, "04b-tai-lieu-da-tai-len", full=True)

    # 05 xem nhanh nội dung file Excel
    prev = page.locator('a[href*="/documents/file/"][href$="/preview"]').first
    if prev.count():
        page.goto(BASE + prev.get_attribute("href"), wait_until="networkidle")
        shot(page, "05-xem-nhanh-file")

    # 07 màn hình xác nhận / sửa map cột
    page.goto(docs_url, wait_until="networkidle")
    rev = page.locator('a[href*="/documents/file/"][href$="/review"]').first
    if rev.count():
        page.goto(BASE + rev.get_attribute("href"), wait_until="networkidle")
        annotate(page, [
            ("#review-grid thead", 1),
            ("#review-grid tbody", 2),
            ("#book-input", 3),
            ('form[action$="/review"] table.data-table tbody', 4),
            ('form[action$="/review"] button[type=submit]', 5),
        ])
        shot(page, "07-xac-nhan-map-cot", full=True)

    # chạy kiểm tra → trang công việc
    page.goto(f"{BASE}/companies/{slug}?year={NEW_YEAR}", wait_until="networkidle")
    page.locator('form[action*="/run-checks"] button[type=submit]').first.click()
    page.wait_for_load_state("networkidle")
    job_url = page.url
    shot(page, "09-cong-viec-dang-chay")

    wait_job_done(page, job_url)
    shot(page, "10-cong-viec-hoan-tat")

    page.goto(f"{BASE}/jobs", wait_until="networkidle")
    annotate(page, [
        (".jobs-filter a:first-child, .tabs a:first-child, nav a:has-text('Tất cả')", 1),
        ("table tbody tr:first-child td:nth-child(4)", 2),
        ("table tbody tr:first-child a:has-text('Xem')", 3, {"side": "right"}),
    ])
    shot(page, "11-hang-doi-cong-viec")

    # chụp lại danh sách DN sau khi DN mới đã có điểm — ảnh 01 khớp phần còn lại
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    annotate(page, [
        ("#dn-search", 1),
        ("#dn-tier-filter", 2),
        ('#companies-table th[data-sort-key="score"]', 3),
        ("#companies-table tbody tr:first-child .tier-pill", 4),
        ("#companies-table tbody tr:first-child td:last-child", 5),
        ('a[href="/companies/new"].btn-primary', 6, {"side": "right"}),
    ])
    shot(page, "01-danh-sach-doanh-nghiep")

    return slug


# ── Phần B: đọc kết quả trên dữ liệu pilot ───────────────────────────────────


def part_b_results(page: Page) -> None:
    print("B. Đọc kết quả")

    # 12 hồ sơ DN: điểm + thống kê mức độ + tab năm
    page.goto(f"{BASE}/companies/{PILOT}?year={PILOT_YEAR}", wait_until="networkidle")
    annotate(page, [
        ('.btn-group form[action*="/run-checks"] button', 1),
        (".stat.tier-stat", 2),
        (".stat.critical", 3),
        (".score-breakdown summary", 4),
        (".tabs", 5),
        ("details.finding-group", 6),
    ])
    shot(page, "12-ho-so-doanh-nghiep")
    clear_annotations(page)

    # 13 bảng giải thích cách tính điểm (mở accordion)
    page.click(".score-breakdown summary")
    page.wait_for_timeout(300)
    annotate(page, [
        (".se-formula", 1),
        (".score-bd-table tbody tr:first-child td:last-child", 2),
        (".bd-denom", 3),
    ])
    shot_el(page, ".score-breakdown", "13-cach-tinh-diem")
    clear_annotations(page)

    # 14 nhóm phát hiện theo bài kiểm tra (mở nhóm đầu tiên)
    grp = page.locator("details.finding-group").first
    grp.locator("summary").click()
    page.wait_for_timeout(300)
    grp.locator("summary").scroll_into_view_if_needed()
    page.mouse.wheel(0, -80)
    page.wait_for_timeout(300)
    annotate(page, [
        ("details.finding-group summary .group-meta", 1),
        ('details.finding-group .group-actions form[action*="/run-checks"] button', 2),
        ("details.finding-group tbody tr:first-child .code-cell", 3),
        ("details.finding-group tbody tr:first-child .status-form-inline", 4),
        ("details.finding-group tbody tr:first-child a:has-text('Chi tiết')", 5,
         {"side": "right"}),
    ])
    shot(page, "14-nhom-phat-hien")
    clear_annotations(page)

    # 15 hộp thoại chọn test để chạy
    page.goto(f"{BASE}/companies/{PILOT}?year={PILOT_YEAR}", wait_until="networkidle")
    if page.locator('[data-open-modal="run-tests-modal"]').count():
        page.click('[data-open-modal="run-tests-modal"]')
        page.wait_for_timeout(400)
        annotate(page, [
            ('#run-tests-modal [data-check-all]', 1),
            ("#run-tests-modal .test-pick-list", 2),
            ("#run-tests-modal [data-submit]", 3, {"side": "right"}),
        ])
        shot(page, "15-chon-test-de-chay")
        clear_annotations(page)
        page.keyboard.press("Escape")

    # 16 hộp thoại xuất Excel
    if page.locator('[data-open-modal="export-tests-modal"]').count():
        page.click('[data-open-modal="export-tests-modal"]')
        page.wait_for_timeout(400)
        annotate(page, [
            ("#export-tests-modal .test-pick input[name=check]", 1),
            ("#export-tests-modal .test-pick-count", 2),
            ("#export-tests-modal [data-submit]", 3, {"side": "right"}),
        ])
        shot(page, "16-xuat-excel-kien-nghi")
        clear_annotations(page)
        page.keyboard.press("Escape")

    # 17 chi tiết phát hiện + chứng cứ truy nguồn
    href = page.locator('a[href^="/findings/"]').first.get_attribute("href")
    page.goto(BASE + href, wait_until="networkidle")
    annotate(page, [
        (".page-header .badge", 1),
        (".card:has-text('Mô tả nghiệp vụ')", 2),
        (".card:has(.kv-table)", 3),
        (".card:has(.evidence-block)", 4),
        (".card:has(form[action*='/status'])", 5),
    ])
    shot(page, "17-chi-tiet-phat-hien", full=True)
    clear_annotations(page)

    # 18 cập nhật trạng thái phát hiện
    annotate(page, [
        (".card:has(form[action*='/status']) select[name=status]", 1),
        (".card:has(form[action*='/status']) textarea[name=notes]", 2),
        (".card:has(form[action*='/status']) button[type=submit]", 3, {"side": "right"}),
    ])
    shot_el(page, ".card:has(form[action*='/status'])", "18-cap-nhat-trang-thai")
    clear_annotations(page)

    # 19 trang chi tiết mã hàng
    item = page.locator('a[href*="/items/"]').first
    if item.count():
        page.goto(BASE + item.get_attribute("href"), wait_until="networkidle")
        page.wait_for_timeout(1000)
        annotate(page, [
            (".item-hero-metrics", 1),
            (".card.item-section:has-text('Cân đối kho')", 2),
            (".card.item-section:has-text('Là đầu vào của thành phẩm')", 3),
            (".card.item-section:has-text('Phát hiện liên quan')", 4),
        ])
        shot(page, "19-chi-tiet-ma-hang", full=True)
        clear_annotations(page)

    # 20 tra cứu dữ liệu gốc Tầng 1
    page.goto(
        f"{BASE}/companies/{PILOT}/data?year={PILOT_YEAR}&table=m15",
        wait_until="networkidle",
    )
    shot(page, "20-du-lieu-goc")

    # 21 DN giữ 2 sổ quyết toán: dải tổng quan + bộ lọc theo sổ
    page.goto(f"{BASE}/companies/{TWO_BOOKS}?year={PILOT_YEAR}", wait_until="networkidle")
    annotate(page, [
        (".book-strip-cell", 1),
        (".book-strip-chung", 2, {"side": "right"}),
        (".book-filter", 3),
    ])
    shot(page, "21-hai-so-quyet-toan")
    clear_annotations(page)

    # 22 sửa kỳ báo cáo (năm tài chính lệch dương lịch)
    page.goto(f"{BASE}/companies/{TWO_BOOKS}/documents", wait_until="networkidle")
    if page.locator(".doc-period-toggle").count():
        page.locator(".doc-period-toggle").first.click()
        page.wait_for_timeout(300)
        annotate(page, [
            (".doc-period-view > .badge", 1),
            ('.doc-period-form input[name=period_from]', 2),
            ('.doc-period-form input[name=period_to]', 3),
            (".doc-period-form button[type=submit]", 4, {"side": "right"}),
        ])
        shot_el(page, ".doc-period", "22-ky-bao-cao")
        clear_annotations(page)

    # 22b tổng quan AI cho một bài kiểm tra — GỌI LLM THẬT (mô hình nhanh, vài giây)
    ov_url = f"{BASE}/companies/{TWO_BOOKS}?year={PILOT_YEAR}&check={OVERVIEW_CHECK}"
    page.goto(ov_url, wait_until="networkidle")
    group = page.locator(f'[id="group-{OVERVIEW_CHECK}"]')
    if group.count() and not group.locator(".check-overview").count():
        btn = group.locator('form[action$="/overview"] button[type=submit]').first
        if btn.count():
            btn.click()
            page.wait_for_load_state("networkidle")
            deadline = time.time() + 240
            while time.time() < deadline:
                page.goto(ov_url, wait_until="networkidle")
                if page.locator(".ov-sections, .check-overview .text-danger").count():
                    break
                page.wait_for_timeout(3000)
    if page.locator(".check-overview").count():
        annotate(page, [
            (".ov-stats", 1),
            (".ovc-lead", 2),
            (".ovc-list", 3),
            (".ovc-disclaimer", 4),
            ('.check-overview form[action$="/overview"] button', 5, {"side": "right"}),
        ])
        shot_el(page, ".check-overview", "22b-tong-quan-ai")
        clear_annotations(page)


# ── Phần C: trợ lý AI + quản trị ─────────────────────────────────────────────


def part_c_ai_admin(page: Page) -> None:
    print("C. Trợ lý AI + quản trị")

    # 23 trang trợ lý với một lượt hỏi–đáp THẬT. Cuộc cũ còn trong DB thì mở lại,
    # không hỏi lại — chạy lại script không tốn thêm lời gọi LLM.
    page.goto(f"{BASE}/chat", wait_until="networkidle")
    page.wait_for_timeout(1500)
    existing = page.locator("#chat-list .ai-history-item, #chat-list [data-conv-id]").first
    if existing.count():
        existing.click()
        page.wait_for_timeout(2000)
    else:
        page.fill("#chat-input", CHAT_QUESTION)
        page.click("#chat-submit")
        for _ in range(90):
            page.wait_for_timeout(2000)
            if page.locator(".ai-msg-foot").count():
                break
        page.wait_for_timeout(1500)
    # Đặt khung nhìn ở câu hỏi cuối: ảnh thấy cả câu hỏi lẫn đầu câu trả lời.
    page.evaluate(
        "() => { const q = document.querySelectorAll('#chat-messages .ai-msg.user');"
        " const m = document.getElementById('chat-messages');"
        " if (q.length && m) m.scrollTop = q[q.length - 1].offsetTop - m.offsetTop - 8; }"
    )
    page.wait_for_timeout(600)
    annotate(page, [
        ("#chat-list", 1),
        ("#chat-messages .ai-msg.user", 2),
        ("#chat-messages .tool-pill, #chat-messages .ai-tool, #chat-messages code", 3),
        ("#chat-input", 4),
    ])
    shot(page, "23-tro-ly-ai")
    clear_annotations(page)

    # 23b khung trợ lý mở ngay trên trang doanh nghiệp (không rời trang đang xem)
    page.goto(f"{BASE}/companies/{PILOT}?year={PILOT_YEAR}", wait_until="networkidle")
    fab = page.locator("#ai-fab, .ai-fab").first
    if fab.count():
        fab.click()
        page.wait_for_timeout(1200)
        annotate(page, [
            ("#ai-scope-bar", 1),
            ("#ai-history", 2),
            ("#ai-expand", 3, {"side": "right"}),
        ])
        shot(page, "23b-tro-ly-ben-trang")
        clear_annotations(page)

    page.goto(f"{BASE}/danh-muc-kiem-tra", wait_until="networkidle")
    shot(page, "24-danh-muc-kiem-tra")

    page.goto(f"{BASE}/tai-lieu", wait_until="networkidle")
    shot(page, "25-thu-vien-tai-lieu")

    page.goto(f"{BASE}/admin/users", wait_until="networkidle")
    shot(page, "26-quan-tri-nguoi-dung")

    # Phân công thật cho tài khoản cán bộ — ảnh 33 sau đó cho thấy danh sách bị thu hẹp.
    scope_href = (
        page.locator(f'tr:has-text("{OFFICER[0]}") a[href$="/scope"]')
        .first.get_attribute("href")
    )
    page.goto(BASE + scope_href, wait_until="networkidle")
    for code in SCOPED_TO_OFFICER:
        page.locator(f'label:has-text("{code}") input.scope-cb').first.check()
    annotate(page, [
        (f'label:has-text("{SCOPED_TO_OFFICER[0]}")', 1),
        ('form[action$="/scope"] button[type=submit]', 2, {"side": "right"}),
    ])
    shot(page, "27-phan-cong-doanh-nghiep")
    clear_annotations(page)
    page.click('form[action$="/scope"] button[type=submit]')
    page.wait_for_load_state("networkidle")

    page.goto(f"{BASE}/admin/risk-tiers", wait_until="networkidle")
    shot(page, "28-nguong-hang-rui-ro")

    page.goto(f"{BASE}/admin/units", wait_until="networkidle")
    shot(page, "29-don-vi-tinh")

    page.goto(f"{BASE}/admin/ai", wait_until="networkidle")
    # Che 4 ký tự cuối của mã API — ảnh nằm dưới /static, phục vụ không cần đăng nhập.
    page.evaluate(
        "() => document.querySelectorAll('#api_key')[0]"
        "?.previousElementSibling?.querySelectorAll('strong')"
        ".forEach(el => { el.textContent = 'sk-o••••••••'; })"
    )
    annotate(page, [
        ("#base_url", 1),
        ("#api_key", 2),
        ('button:has-text("Thử kết nối")', 3, {"side": "right"}),
        ("#model_default", 4),
    ])
    shot(page, "30-cau-hinh-ai")
    clear_annotations(page)

    page.goto(f"{BASE}/admin/audit", wait_until="networkidle")
    shot(page, "31-nhat-ky-truy-cap")

    page.goto(f"{BASE}/admin/checks", wait_until="networkidle")
    annotate(page, [
        ('a:has-text("Tạo kiểm tra mới")', 1),
        ('form[action*="combos-toggle"]', 2),
        ("table tbody tr:first-child td:nth-child(4)", 3),
    ])
    shot(page, "32-kiem-tra-mo-rong")
    clear_annotations(page)


def part_d_officer(page: Page) -> None:
    """Góc nhìn cán bộ: thanh điều hướng không có nhóm quản trị."""
    print("D. Góc nhìn cán bộ")
    logout(page)
    login(page, OFFICER)
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    shot(page, "33-goc-nhin-can-bo")


def main() -> None:
    # G_STAGES=bc để chụp lại một phần mà không chạy lại toàn bộ luồng nạp liệu.
    stages = os.environ.get("G_STAGES", "abcd")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="vi-VN")
        page = ctx.new_page()
        if "a" in stages:
            part_a_ingest_flow(page)
        else:
            login(page, ADMIN)
        if "b" in stages:
            part_b_results(page)
        if "c" in stages:
            part_c_ai_admin(page)
        if "d" in stages:
            part_d_officer(page)
        ctx.close()
        browser.close()
    print(f"xong — ảnh ở {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
