"""Ảnh + số đo E2E cho vùng cài đặt đọc file (#124).

Vé khai AC 6 là tồn dư KHÔNG phủ được bằng test: quan hệ bộ chọn đã gộp chỉ đúng lúc
chạy thật. Hai thứ trong số đó không một test nào của repo chạm tới được, và cả hai đứt
thì im lặng:

* nút ghim nằm TRONG biểu mẫu gán cột nhưng gửi biểu mẫu KHÁC qua thuộc tính `form=`
  (biểu mẫu lồng nhau là HTML sai) — `TestClient` không biết trình duyệt gửi cái nào;
* phím Enter ở ô nhập chỉ số cột phải gửi biểu mẫu gán cột, không phải nút ghim. Đó là
  lý do duy nhất khiến nút ghim phải nằm ngoài biểu mẫu chính.

Chạy THẬT: seed DB throwaway, dựng workbook hai trang tính trên đĩa, nạp qua handler,
bật uvicorn ở cổng TỰ DO, đăng nhập bằng cookie ký sẵn (form login dính rate-limit +
cookie Secure trên http), đo, chụp, rồi kill server theo PID group. KHÔNG đụng DB dev,
KHÔNG đụng cổng 8200.

Dữ liệu BỊA hoàn toàn — không phải doanh nghiệp thật.

    .venv/bin/python .ai/features/2026-08-09-cai-dat-doc-file/ui_smoke.py
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
SCRATCH = Path("/tmp/claude-1000/ui-smoke-cai-dat-doc-file.sqlite")
RAW = Path("/tmp/claude-1000/ui-smoke-cai-dat-doc-file-raw")

OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO))
for suffix in ("", "-wal", "-shm"):
    Path(str(SCRATCH) + suffix).unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{SCRATCH}"
os.environ["RAW_DATA_PATH"] = str(RAW)

SHOTS: list[tuple[str, str]] = []
FAILED: list[str] = []

M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
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


def make_m15(path: Path, rows: int = 40) -> None:
    """Workbook Mẫu 15 hai trang tính, trang phụ ĐỨNG TRƯỚC.

    Trang phụ đứng trước là bố cục có thật của workbook kết xuất từ ECUS, và là ca vé
    này sinh ra để phục vụ: parser đọc trang thứ hai, còn cán bộ mở trang thứ nhất lên
    xem thì nút ghim mới có việc.
    """
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
        ws2.append([i + 1, f"NVL{i:03d}", "Vải chính", "MTR",
                    10, 100, 0, 0, 80, 0, 30])
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

    with SessionLocal() as s:
        row = s.query(DataFile).filter_by(slot="m15").first()
        return None if row is None else row.id


def shot(pg, name: str, caption: str, *, full: bool = False) -> None:
    # Kéo vùng cài đặt lên đầu khung trước khi chụp. Ảnh chụp theo KHUNG NHÌN, và vùng
    # này nằm dưới lưới xem trước — chụp ở vị trí cuộn mặc định thì ra ảnh của lưới, tức
    # ảnh không chứng minh điều chú thích nói.
    #
    # Lưới KHÔNG tự cuộn tới đây khi cán bộ đổi trang tính: họ vừa mở một trang lên để
    # NHÌN, kéo màn hình khỏi nó là lấy đi đúng thứ vừa xin. Vùng mở sẵn để khi cuộn
    # xuống thì hành động đã ở đó, không phải bấm thêm một lần.
    try:
        pg.evaluate("""() => {
            const box = document.getElementById('read-settings');
            // Trừ chiều cao thanh điều hướng dính, nếu không thì vùng nằm KHUẤT sau nó.
            const nav = document.querySelector('.topbar, nav.navbar, header');
            const off = (nav ? nav.getBoundingClientRect().height : 0) + 24;
            if (box) window.scrollTo({top: box.getBoundingClientRect().top + window.scrollY - off});
        }""")
        pg.wait_for_timeout(350)
    except Exception:  # noqa: BLE001
        pass
    path = OUT / f"{name}.png"
    pg.screenshot(path=str(path), full_page=full)
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
            posts: list[str] = []
            errors: list[str] = []
            pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))

            # ── 1. Trạng thái đầu: mọi thứ đúng → vùng thu còn một dòng ──────────
            print("\n1. Vùng cài đặt ở trạng thái đã đặt đúng")
            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(1200)
            check("vùng thu lại", pg.eval_on_selector("#read-settings", "e => e.open"), False)
            summary = pg.eval_on_selector(
                "#read-settings > summary", "e => e.textContent.replace(/\\s+/g,' ').trim()")
            print(f"       dòng tóm tắt: {summary!r}")
            check("tóm tắt một dòng", pg.eval_on_selector(
                "#read-settings > summary",
                "e => Math.round(e.getBoundingClientRect().height) <= 48"), True)
            # Bảng gán cột phải nằm trong màn hình đầu tiên — lý do vùng thu lại.
            # Số nền đo trên `main` @ 87ef266 bằng đúng bộ dữ liệu này: hai thẻ cài đặt
            # cũ cao 130px + 167px = 297px, mép trên bảng gán cột ở 1241px — dưới đáy
            # khung nhìn. Đây là DELTA, không phải một số tuyệt đối tự nó có nghĩa.
            top = pg.eval_on_selector(
                ".fieldmap-card", "e => Math.round(e.getBoundingClientRect().top)")
            print(f"       mép trên bảng gán cột: {top}px (nền 1241px, khung nhìn 1000px)")
            check("bảng gán cột trong màn hình đầu", top < 1000, True)
            shot(pg, "01_vung_cai_dat_thu_con_mot_dong",
                 "#124 — trang tính và sổ đã đúng: vùng cài đặt còn một dòng, mép trên "
                 "bảng gán cột 1241px → 974px trên khung nhìn 1000px")

            # ── 2. Bộ chọn duy nhất: đổi trang ĐANG XEM, không tải lại ───────────
            print("\n2. Bộ chọn trang tính đổi khung nhìn tại chỗ")
            picks = pg.eval_on_selector_all(
                ".js-sheet-pick", "els => els.map(e => e.dataset.sheetName)")
            print(f"       bộ chọn: {picks}")
            check("một bộ chọn, đủ trang", picks, ["Phụ lục", "BCQT_NVL"])
            check("không còn <select name=sheet>",
                  pg.eval_on_selector_all('select[name="sheet"]', "e => e.length"), 0)
            pg.evaluate("window.__marker = 'con-nguyen'")
            pg.click('.js-sheet-pick[data-sheet-index="0"]')
            pg.wait_for_timeout(1500)
            check("KHÔNG tải lại trang", pg.evaluate("window.__marker || ''"), "con-nguyen")
            check("địa chỉ mang trang đang xem", pg.url.endswith("?sheet=0"), True)
            check("aria-current dời theo", pg.eval_on_selector_all(
                ".js-sheet-pick", "els => els.map(e => e.getAttribute('aria-current'))"),
                ["true", None])

            # ── 3. Xem trang khác → vùng mở, nút ghim trỏ đúng trang đang xem ────
            print("\n3. Nút ghim ở trạng thái nó có việc")
            check("vùng tự mở", pg.eval_on_selector("#read-settings", "e => e.open"), True)
            check("nút ghim trỏ trang đang xem",
                  pg.eval_on_selector("#sheet-pin", "e => e.value"), "Phụ lục")
            check("nút ghim bấm được",
                  pg.eval_on_selector("#sheet-pin", "e => e.disabled"), False)
            check("nút ghim gửi biểu mẫu riêng",
                  pg.eval_on_selector("#sheet-pin", "e => e.getAttribute('form')"),
                  "fp-sheet-form")
            shot(pg, "02_xem_trang_khac_vung_mo_nut_ghim_hien",
                 "#124 — xem sang trang khác trang hệ thống đọc: vùng tự mở sẵn (cán bộ "
                 "cuộn xuống là thấy), nút ghim trỏ đúng trang đang xem")

            # ── 4. Phím Enter ở ô cột KHÔNG được đi ghim trang ───────────────────
            print("\n4. Phím Enter ở biểu mẫu gán cột")
            posts.clear()
            box = pg.query_selector('input.js-col-pick') or pg.query_selector(
                'input[name^="col_"]:not([type=hidden])')
            if box is None:
                # Bố cục chuẩn dựng `<select>` cho mọi trường; ô nhập chỉ có ở nhóm cột
                # con. Dùng ô mã sổ — cũng là ô chữ trong CÙNG biểu mẫu, cùng câu hỏi.
                box = pg.query_selector("#book-input")
            box.click()
            box.press("Enter")
            pg.wait_for_timeout(1800)
            posted = [u.split("/documents/")[-1] for u in posts]
            print(f"       POST đã gửi: {posted}")
            check("Enter KHÔNG gửi lượt ghim",
                  any(u.endswith("/sheet") for u in posts), False)
            check("Enter gửi biểu mẫu gán cột", len(posts) >= 1, True)

            # ── 5. Nút ghim: `form=` có thật sự gửi biểu mẫu kia không ───────────
            print("\n5. Nút ghim gửi qua thuộc tính `form=`")
            pg.goto(url + "?sheet=0", wait_until="networkidle")
            pg.wait_for_timeout(1200)
            posts.clear()
            pg.click("#sheet-pin")
            pg.wait_for_timeout(2000)
            print(f"       POST đã gửi: {[u.split('/documents/')[-1] for u in posts]}")
            check("gửi đúng địa chỉ ghim",
                  any(u.endswith("/sheet") for u in posts), True)
            check("về dòng kỳ", "/documents" in pg.url and "#ky-2025" in pg.url, True)

            import app.database as dbmod
            from app.models import DataFile
            with dbmod.SessionLocal() as s:
                pinned = s.get(DataFile, fid).sheet_override
            check("trang đã ghim vào DB", pinned, "Phụ lục")

            # ── 6. Đã ghim: nút ghim câm, có nút bỏ ghim ─────────────────────────
            print("\n6. Sau khi ghim")
            pg.goto(url + "?sheet=0", wait_until="networkidle")
            pg.wait_for_timeout(1200)
            check("ghim lại chính trang đó thì không bấm được",
                  pg.eval_on_selector("#sheet-pin", "e => e.disabled"), True)
            check("có nút bỏ ghim",
                  pg.eval_on_selector_all("#sheet-unpin", "e => e.length"), 1)
            summary = pg.eval_on_selector(
                "#read-settings > summary", "e => e.textContent.replace(/\\s+/g,' ').trim()")
            print(f"       dòng tóm tắt: {summary!r}")
            # Ở trạng thái này vùng THU lại đúng theo AC 3 (trang đang xem = trang đã
            # ghim, không còn việc gì). Mở ra để ảnh chụp được hai nút mà phép đo trên
            # vừa khẳng định — ảnh phải hiện đúng thứ chú thích nói.
            pg.eval_on_selector("#read-settings", "e => e.open = true")
            pg.wait_for_timeout(250)
            shot(pg, "03_sau_khi_ghim_co_duong_bo_ghim",
                 "#124 — đã ghim (vùng thu lại theo AC 3, đây là ảnh mở ra): nút ghim "
                 "lại chính trang đó không bấm được, và có đường bỏ ghim")

            # ── 7. Ô mã sổ trong phần đã thu vẫn gửi đi ──────────────────────────
            print("\n7. Ô trong phần đã thu vẫn nằm trong biểu mẫu")
            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(1000)
            pg.eval_on_selector("#read-settings", "e => e.open = true")
            pg.fill("#book-input", "EPE")
            pg.eval_on_selector("#read-settings", "e => e.open = false")
            pg.get_by_role("button", name="Xác nhận").click()
            pg.wait_for_timeout(2500)
            with dbmod.SessionLocal() as s:
                book = s.get(DataFile, fid).book
            check("mã sổ đã thu vẫn lưu được", book, "EPE")

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
