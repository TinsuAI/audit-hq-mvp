"""Ảnh + số đo E2E cho loạt thiết kế lại màn gán cột (#118–#128, vé bằng chứng #129).

Bốn thứ KHÔNG seam nào ngoài trình duyệt phủ được, và vé #129 sinh ra để đo bốn thứ đó:

1. **Làm nổi cột có thật sự sáng lên và cuộn tới không.** `cell-grid.js` gắn lớp
   `.cg-col-hi` / `.cg-cell-hi` rồi cuộn ngang. Bộ test đọc mã nguồn JS thấy chuỗi hàm
   nối đúng, nhưng không chạy được nó: lưới dựng bằng JS từ payload `/cells`.
2. **Quan hệ bộ chọn trang tính đã gộp lúc chạy thật** (#124): địa chỉ mang `?sheet=`,
   `aria-current` dời theo, và cú bấm KHÔNG tải lại trang.
3. **Số dòng / số cột do JS đóng vào** (#123): máy chủ khai `aria-rowcount="-1"` (CHƯA
   BIẾT), lưới ghi đè bằng số thật khi cửa sổ đầu về. Không trình duyệt thì không có
   bước ghi đè nào để đo.
4. **Tương phản SAU KHI trình duyệt hợp thành** — `opacity`, thứ tự xếp lớp, nền thừa
   hưởng và màu nửa trong suốt không nằm trong phép tính của `tests/test_static_assets.py`.

Chạy THẬT: seed DB throwaway, dựng workbook trên đĩa, nạp qua handler, bật uvicorn ở
cổng TỰ DO, đăng nhập bằng cookie ký sẵn (form login dính rate-limit + cookie Secure
trên http), đo, chụp, rồi kill server theo PID group. KHÔNG đụng DB dev, KHÔNG đụng
cổng 8200.

Ảnh chụp theo KHUNG NHÌN, không `full_page`: phần tử `sticky` vẽ ở vị trí đang dính rồi
để lại một mảng trắng chỗ nó vốn nằm, và chính nó từng làm chẩn đoán sai một lỗi bố cục.

Dữ liệu BỊA hoàn toàn — không phải doanh nghiệp thật.

    .venv/bin/python .ai/features/2026-08-09-thiet-ke-lai-man-gan-cot/ui_smoke.py
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "screenshots"
SCRATCH = Path("/tmp/claude-1000/ui-smoke-thiet-ke-lai-man-gan-cot.sqlite")
RAW = Path("/tmp/claude-1000/ui-smoke-thiet-ke-lai-man-gan-cot-raw")

OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO))
for suffix in ("", "-wal", "-shm"):
    Path(str(SCRATCH) + suffix).unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{SCRATCH}"
os.environ["RAW_DATA_PATH"] = str(RAW)

SHOTS: list[tuple[str, str]] = []
FAILED: list[str] = []

# Cột 8 mang nhãn không khớp từ khoá → `production_out_qty` chỉ `balance-checked`, tức
# cổng xác nhận cột bật và trang có ô nhập để đo chuỗi làm nổi cột.
M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Cột 8", "Xuất khác", "Tồn cuối kỳ",
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  {'ĐẠT ' if ok else 'HỎNG'} {name}: {got!r}" + ("" if ok else f" (chờ {want!r})"))
    if not ok:
        FAILED.append(name)


def check_at_least(name: str, got: float, floor: float) -> None:
    ok = got >= floor
    print(f"  {'ĐẠT ' if ok else 'HỎNG'} {name}: {got}" + ("" if ok else f" (sàn {floor})"))
    if not ok:
        FAILED.append(name)


def make_m15(path: Path, rows: int = 60) -> None:
    """Workbook Mẫu 15 hai trang tính, trang phụ ĐỨNG TRƯỚC (bố cục workbook ECUS)."""
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Phụ lục"
    ws.append(["Phụ lục kèm theo báo cáo quyết toán"])
    ws.append(["Không phải biểu Mẫu 15"])

    ws2 = wb.create_sheet("BCQT_NVL")
    for _ in range(8):
        ws2.append([None] * len(M15_HEADER))
    ws2.append(M15_HEADER)
    for i in range(rows):
        ws2.append([i + 1, f"NVL{i:03d}", "Vải chính", "MTR", 10, 100, 0, 0, 80, 0, 30])
    wb.save(path)


def seed() -> int | None:
    from app.auth_users import create_user
    from app.database import Base, SessionLocal, engine
    from app.jobs.handlers import ingest_handler
    from app.models import Company, CompanyPeriod, DataFile

    Base.metadata.create_all(engine)
    make_m15(RAW / "DN_MINH_HOA/2025/BCQT/BCQT NVL 2025.xlsx")

    with SessionLocal() as s:
        create_user(s, username="can_bo", password="MatKhau!2026", role="admin")
        c = Company(code="DN_MINH_HOA", name="Công ty TNHH Minh Hoạ", slug="dn-minh-hoa",
                    tax_id="0100000000", risk_score=21)
        s.add(c)
        s.flush()
        s.add(CompanyPeriod(company_id=c.id, period_year=2025,
                            period_from=date(2025, 1, 1), period_to=date(2025, 12, 31),
                            data_version=1))
        s.commit()

    with SessionLocal() as s:
        res = ingest_handler({"company_code": "DN_MINH_HOA", "year": 2025, "gate": True}, s)
        s.commit()
        print(f"  nạp: {res.get('status')} — {str(res.get('note', ''))[:70]}")

    # Bật cấu hình trợ lý AI để `sidebar.js` gắn được listener: `init()` thoát sớm khi
    # `/api/ai/meta` trả `enabled=false`, và khi đó không có đường nào mở thanh trong
    # trình duyệt. KHÔNG có lượt gọi LLM nào ở đây — chỉ mở/đóng thanh, và phần đo
    # (`classList`, `aria-hidden`, `inert`) chạy ĐỒNG BỘ trước mọi `await` của `openPanel`.
    from app.ai.config import set_setting

    with SessionLocal() as s:
        set_setting("enabled", True, user="can_bo", db=s)
        set_setting("api_key", "sk-khong-dung-that", user="can_bo", db=s)
        s.commit()

    with SessionLocal() as s:
        row = s.query(DataFile).filter_by(slot="m15").first()
        return None if row is None else row.id


#: Đo tương phản trên màu ĐÃ HỢP THÀNH, tức sau khi trình duyệt trộn `opacity`, nền thừa
#: hưởng và màu nửa trong suốt — thứ mà phép đo trên stylesheet không thấy được.
CONTRAST_JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const parse = (c) => {
    const m = c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  // Nền hợp thành: đi ngược cây cha cho tới khi gặp một nền đục.
  let bg = {r: 255, g: 255, b: 255, a: 1};
  const chain = [];
  for (let n = el; n; n = n.parentElement) chain.push(n);
  for (const n of chain.reverse()) {
    const c = parse(getComputedStyle(n).backgroundColor);
    if (c && c.a > 0) bg = over(c, bg);
  }
  // Chữ: màu chữ trộn với nền, rồi nhân `opacity` tích luỹ của cả chuỗi cha.
  let alpha = 1;
  for (let n = el; n; n = n.parentElement) alpha *= parseFloat(getComputedStyle(n).opacity);
  const raw = parse(getComputedStyle(el).color) || {r: 0, g: 0, b: 0, a: 1};
  const fg = over({...raw, a: raw.a * alpha}, bg);
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const a = lum(fg), b = lum(bg);
  return Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100;
}
"""


def shot(pg, name: str, caption: str, *, anchor: str | None = None) -> None:
    """Chụp theo KHUNG NHÌN. `anchor` là bộ chọn cần kéo lên đầu khung trước khi chụp."""
    if anchor:
        try:
            pg.evaluate(
                """(sel) => {
                    const box = document.querySelector(sel);
                    const nav = document.querySelector('.app-header');
                    const off = (nav ? nav.getBoundingClientRect().height : 0) + 24;
                    if (box) window.scrollTo({top: box.getBoundingClientRect().top + window.scrollY - off});
                }""",
                anchor,
            )
            pg.wait_for_timeout(350)
        except Exception:  # noqa: BLE001
            pass
    path = OUT / f"{name}.png"
    pg.screenshot(path=str(path), full_page=False)
    SHOTS.append((path.name, caption))
    print(f"  ✎ {path.name}")


def main() -> int:  # noqa: C901
    fid = seed()
    if fid is None:
        print("KHÔNG seed được file m15 — dừng.")
        return 1

    from playwright.sync_api import sync_playwright

    from app.auth import SESSION_COOKIE_NAME, SessionUser, make_session_cookie

    port = free_port()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{SCRATCH}", "RAW_DATA_PATH": str(RAW)}
    proc = subprocess.Popen(
        [str(REPO / ".venv/bin/uvicorn"), "app.main:app", "--port", str(port),
         "--host", "127.0.0.1"],
        cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    base = f"http://127.0.0.1:{port}"
    url = f"{base}/companies/dn-minh-hoa/documents/file/{fid}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)

        cookie = make_session_cookie(SessionUser(name="can_bo", role="admin"))
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(viewport={"width": 1440, "height": 1000},
                                 device_scale_factor=2)
            ctx.add_cookies([{"name": SESSION_COOKIE_NAME, "value": cookie,
                              "domain": "127.0.0.1", "path": "/"}])
            pg = ctx.new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            # ── 1. Số dòng / số cột do JS đóng vào (#123) ────────────────────────
            print("\n1. Lưới khai hình dạng của chính nó")
            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(2000)
            check("máy chủ khai CHƯA BIẾT rồi lưới ghi đè",
                  pg.eval_on_selector("#cell-grid", "e => e.getAttribute('aria-rowcount')") != "-1",
                  True)
            rowcount = int(pg.eval_on_selector(
                "#cell-grid", "e => e.getAttribute('aria-rowcount')"))
            colcount = int(pg.eval_on_selector(
                "#cell-grid", "e => e.getAttribute('aria-colcount')"))
            print(f"       aria-rowcount={rowcount} · aria-colcount={colcount}")
            check("số dòng đúng bộ dữ liệu (9 tiêu đề + 60 dòng)", rowcount, 69)
            check("số cột đúng biểu", colcount, 11)
            check("lưới có tên khả truy cập",
                  bool(pg.eval_on_selector("#cell-grid", "e => e.getAttribute('aria-label')")),
                  True)
            check("khai `table`, không khai `grid`",
                  pg.eval_on_selector("#cell-grid", "e => e.getAttribute('role')"), "table")
            shot(pg, "01_luoi_khai_hinh_dang", anchor=".fp-grid",
                 caption="#123 — lưới ghi đè `aria-rowcount`/`aria-colcount` bằng số thật "
                         f"khi cửa sổ đầu về: {rowcount} dòng × {colcount} cột")

            # ── 2. Làm nổi cột: có sáng lên và có cuộn tới không (#122) ──────────
            print("\n2. Chuỗi làm nổi cột")
            pg.evaluate("""() => {
                const box = document.querySelector('.fieldmap-card');
                if (box) box.scrollIntoView({block: 'center'});
            }""")
            pg.wait_for_timeout(300)
            before = pg.eval_on_selector(".cg-body", "e => e.scrollLeft")
            pick = pg.query_selector('select.js-col-pick[name="col_closing_qty"]')
            check("bộ chọn cột có phát lớp nối", pick is not None, True)
            if pick is not None:
                pick.focus()
                pick.select_option("10")
                pg.wait_for_timeout(900)
                lit_cols = pg.eval_on_selector_all(".cg-col-hi", "e => e.length")
                lit_cells = pg.eval_on_selector_all(".cg-cell-hi", "e => e.length")
                after = pg.eval_on_selector(".cg-body", "e => e.scrollLeft")
                print(f"       .cg-col-hi={lit_cols} · .cg-cell-hi={lit_cells} · "
                      f"scrollLeft {before} → {after}")
                check("cột tiêu đề sáng lên", lit_cols >= 1, True)
                check_at_least("ô trong cột sáng lên", lit_cells, 1)
                check("lưới cuộn ngang tới cột", after > before, True)
                shot(pg, "02_lam_noi_cot_sang_va_cuon", anchor=".fp-grid",
                     caption="#122 — chọn “Tồn cuối kỳ” (cột 10): cột sáng lên trong lưới "
                             f"và lưới cuộn ngang tới nó ({before}px → {after}px)")
                pick.evaluate("e => e.blur()")
                pg.wait_for_timeout(600)
                check("rời ô thì tắt đèn",
                      pg.eval_on_selector_all(".cg-col-hi", "e => e.length"), 0)

            # ── 3. Bộ chọn trang tính đã gộp, lúc chạy thật (#124) ───────────────
            print("\n3. Quan hệ bộ chọn trang tính")
            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(1500)
            picks = pg.eval_on_selector_all(
                ".js-sheet-pick", "els => els.map(e => e.dataset.sheetName)")
            check("một bộ chọn duy nhất, đủ trang", picks, ["Phụ lục", "BCQT_NVL"])
            check("không còn bộ chọn thứ hai",
                  pg.eval_on_selector_all('select[name="sheet"]', "e => e.length"), 0)
            pg.evaluate("window.__marker = 'con-nguyen'")
            pg.click('.js-sheet-pick[data-sheet-index="0"]')
            pg.wait_for_timeout(1500)
            check("bấm KHÔNG tải lại trang", pg.evaluate("window.__marker || ''"), "con-nguyen")
            check("địa chỉ mang trang đang xem", pg.url.endswith("?sheet=0"), True)
            check("aria-current dời theo", pg.eval_on_selector_all(
                ".js-sheet-pick", "els => els.map(e => e.getAttribute('aria-current'))"),
                ["true", None])
            check("vùng cài đặt tự mở khi xem trang khác",
                  pg.eval_on_selector("#read-settings", "e => e.open"), True)
            shot(pg, "03_bo_chon_trang_tinh_da_gop", anchor=".fp-grid",
                 caption="#124 — một bộ chọn: bấm đổi trang ĐANG XEM tại chỗ, địa chỉ mang "
                         "`?sheet=0`, `aria-current` dời theo, vùng cài đặt tự mở")

            # ── 4. Tương phản SAU khi trình duyệt hợp thành (#118, #128) ─────────
            print("\n4. Tương phản trên màu đã hợp thành")
            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(1500)
            for name, sel, floor in [
                ("câu căn cứ ở dòng trường", ".fm-evi", 4.5),
                ("dòng trạng thái dưới lưới", ".fp-status", 4.5),
                ("gợi ý trong vùng cài đặt", ".fp-set .form-hint", 4.5),
                ("nhãn ở dòng trường", ".fm-fname", 4.5),
                ("chữ trong ô lưới", ".cg-cell", 4.5),
            ]:
                ratio = pg.evaluate(CONTRAST_JS, sel)
                if ratio is None:
                    print(f"  BỎ QUA {name}: không có phần tử {sel}")
                    continue
                check_at_least(f"tương phản — {name}", ratio, floor)

            # Dòng đã khai vắng: chỗ #121 thay `opacity: .55` (đo được 2,55) bằng nền
            # `--c-surface-alt`. Bật một ô khai vắng để đo đúng trạng thái đó.
            absent = pg.query_selector('input[name^="absent_"]')
            if absent is not None:
                absent.check()
                pg.wait_for_timeout(200)
                pg.evaluate("""() => {
                    const box = document.querySelector('input[name^="absent_"]');
                    const row = box ? box.closest('tr') : null;
                    if (row) row.classList.add('fm-row-absent');
                }""")
                ratio = pg.evaluate(CONTRAST_JS, ".fm-row-absent .fm-evi")
                if ratio is not None:
                    check_at_least("tương phản — dòng đã khai vắng", ratio, 4.5)

            # ── 5. Skip-link và thanh trợ lý (#126) ─────────────────────────────
            print("\n5. Đường đi của bàn phím")
            check("trang file KHÔNG tải thanh trợ lý",
                  pg.eval_on_selector_all("#ai-panel", "e => e.length"), 0)
            pg.goto(f"{base}/companies", wait_until="networkidle")
            pg.wait_for_timeout(600)
            pg.keyboard.press("Tab")
            pg.wait_for_timeout(200)
            check("chặng tab đầu là skip-link",
                  pg.evaluate("() => document.activeElement.className"), "skip-link")
            check("skip-link hiện ra khi nhận focus",
                  pg.eval_on_selector(".skip-link", "e => e.getBoundingClientRect().top >= 0"),
                  True)
            shot(pg, "04_skip_link_hien_khi_nhan_focus",
                 caption="#126 — chặng tab đầu tiên của trang là liên kết nhảy tới nội "
                         "dung; nó chỉ hiện khi nhận focus")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(400)
            check("bấm skip-link thì focus vào vùng nội dung",
                  pg.evaluate("() => document.activeElement.id"), "noi-dung-chinh")
            # Thanh trợ lý đóng phải NGOÀI chuỗi tab.
            check("thanh trợ lý đóng khai `inert`",
                  pg.eval_on_selector("#ai-panel", "e => e.hasAttribute('inert')"), True)
            reachable = pg.evaluate("""() => {
                const panel = document.getElementById('ai-panel');
                const els = panel.querySelectorAll('button, a[href], input, select, textarea');
                let n = 0;
                for (const el of els) { el.focus(); if (document.activeElement === el) n++; }
                return n;
            }""")
            check("không điều khiển nào của thanh đóng nhận được focus", reachable, 0)
            pg.click("#ai-fab")
            pg.wait_for_timeout(1200)
            check("mở thanh thì gỡ `inert`",
                  pg.eval_on_selector("#ai-panel", "e => e.hasAttribute('inert')"), False)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(500)
            check("đóng bằng Escape thì khai lại `inert`",
                  pg.eval_on_selector("#ai-panel", "e => e.hasAttribute('inert')"), True)
            check("đóng xong focus về nút mở, không rơi về <body>",
                  pg.evaluate("() => document.activeElement.id"), "ai-fab")

            # ── 6. Màn dữ liệu: nghĩa hiện thành chữ (#130) ──────────────────────
            print("\n6. Nghĩa nguồn bằng chứng ở màn dữ liệu")
            pg.goto(f"{base}/companies/dn-minh-hoa/data?year=2025&table=m15",
                    wait_until="networkidle")
            pg.wait_for_timeout(800)
            rows = pg.eval_on_selector_all(".evidence-key-row", "e => e.length")
            check_at_least("số dòng nghĩa hiện ra", rows, 1)
            check("nghĩa hiện được mà không rê chuột", pg.eval_on_selector(
                ".evidence-key", "e => getComputedStyle(e).display !== 'none'"), True)
            ratio = pg.evaluate(CONTRAST_JS, ".evidence-key dd")
            if ratio is not None:
                check_at_least("tương phản — câu nghĩa", ratio, 4.5)
            shot(pg, "05_man_du_lieu_nghia_thanh_chu", anchor=".parse-note",
                 caption="#130 — màn dữ liệu: chip giữ nhãn ngắn, nghĩa của từng nguồn "
                         f"hiện thành chữ ngay dưới ({rows} dòng), không nằm trong tooltip")

            check("không lỗi JavaScript", errors, [])
            br.close()
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)

    print("\n" + "─" * 70)
    for name, caption in SHOTS:
        print(f"{name}\n    {caption}")
    if FAILED:
        print(f"\nHỎNG {len(FAILED)}: {', '.join(FAILED)}")
        return 1
    print("\nMọi phép đo ĐẠT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
