"""Ảnh E2E cho màn gán cột theo trường khai (#112, lát 2/3 của #110).

Chạy THẬT: seed DB throwaway, dựng file Excel thật trên đĩa, nạp qua handler để
`parse_detail` có ảnh chụp cột, bật uvicorn ở cổng TỰ DO, đăng nhập bằng cookie ký sẵn
(form login dính rate-limit + cookie Secure trên http), chụp, rồi kill server theo PID
group. KHÔNG đụng DB dev, KHÔNG đụng cổng 8200.

Dữ liệu BỊA hoàn toàn — không phải doanh nghiệp thật.

    .venv/bin/python .ai/features/2026-08-08-man-gan-cot-theo-truong/ui_smoke.py
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
SCRATCH = Path("/tmp/claude-1000/ui-smoke-gan-cot.sqlite")
RAW = Path("/tmp/claude-1000/ui-smoke-gan-cot-raw")

OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO))
for suffix in ("", "-wal", "-shm"):
    Path(str(SCRATCH) + suffix).unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{SCRATCH}"
os.environ["RAW_DATA_PATH"] = str(RAW)

SHOTS: list[tuple[str, str]] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_m16(path: Path, rows: int = 30) -> None:
    """Mẫu 16 bố cục TT39, nhưng KHÔNG có cột ghi chú.

    Đó là bố cục DINHMUC có thật trong kho: `note` không có vị trí mặc định, nên nó tới
    màn ở trạng thái *chưa gán* — đúng ca mà lát 2 sinh ra để xử lý.
    """
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "BCTT39"
    for _ in range(10):
        ws.append([None] * 8)
    ws.append([None, "Mã sản phẩm", "Tên sản phẩm", "ĐVT SP",
               "Mã nguyên liệu", "Tên nguyên liệu", "ĐVT NVL",
               "Lượng NL, VT thực tế sử dụng"])
    for i in range(rows):
        parent = i % 6 == 0
        ws.append([
            i + 1,
            f"TP{i // 6:03d}" if parent else None,
            "Áo sơ mi" if parent else None,
            "PCE" if parent else None,
            f"NPL{i:03d}", "Vải chính", "MTR", 1.5 + i / 100,
        ])
    wb.save(path)


def seed() -> int:
    from app.auth_users import create_user
    from app.database import Base, SessionLocal, engine
    from app.jobs.handlers import ingest_handler
    from app.models import Company, CompanyPeriod, DataFile

    Base.metadata.create_all(engine)
    make_m16(RAW / "DN_MINH_HOA/2025/DINH_MUC/DINHMUC 2025.xlsx")

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
        row = s.query(DataFile).filter_by(slot="m16").first()
        return row.id


def shot(pg, name: str, caption: str, *, full: bool = True) -> None:
    path = OUT / f"{name}.png"
    pg.screenshot(path=str(path), full_page=full)
    SHOTS.append((path.name, caption))
    print(f"  {path.name}")


def main() -> int:
    fid = seed()
    if fid is None:
        print("KHÔNG seed được file m16 — dừng.")
        return 1

    from app.auth import SESSION_COOKIE_NAME, SessionUser, make_session_cookie
    from playwright.sync_api import sync_playwright

    port = free_port()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{SCRATCH}", "RAW_DATA_PATH": str(RAW)}
    proc = subprocess.Popen(
        [str(REPO / ".venv/bin/uvicorn"), "app.main:app", "--port", str(port),
         "--host", "127.0.0.1"],
        cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1)
                break
            except Exception:
                time.sleep(0.25)

        cookie = make_session_cookie(SessionUser(name="can_bo", role="admin"))
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(viewport={"width": 1500, "height": 1400},
                                 device_scale_factor=2)
            ctx.add_cookies([{"name": SESSION_COOKIE_NAME, "value": cookie,
                              "domain": "127.0.0.1", "path": "/"}])
            pg = ctx.new_page()
            url = f"{base}/companies/dn-minh-hoa/documents/file/{fid}"

            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(1200)
            shot(pg, "01_man_gan_cot_theo_truong_khai",
                 "#112 — một dòng mỗi TRƯỜNG KHAI của biểu (8 dòng cho Mẫu 16), kể cả "
                 "trường máy không đặt được; nhãn khoá dòng / bắt buộc theo biểu")

            # Bộ chọn cột: mỗi lựa chọn mang tiêu đề cột + mẫu giá trị thật.
            try:
                pg.select_option('select[name="col_note"]', index=0, timeout=2000)
            except Exception as exc:  # noqa: BLE001
                print(f"  (bỏ qua mở bộ chọn: {type(exc).__name__})")
            opts = pg.eval_on_selector_all(
                'select[name="col_material_code"] option', "els => els.map(e => e.textContent.trim())",
            )
            print("  mẫu lựa chọn cột:", opts[:4])
            shot(pg, "02_bo_chon_cot_kem_tieu_de_va_mau_gia_tri",
                 "#112 — mỗi lựa chọn là «cột N · tiêu đề · mẫu giá trị», chọn bằng mắt "
                 "thay vì đếm cột")

            # Xác nhận `note` không có trong file → trạng thái thứ ba.
            try:
                pg.check('input[name="absent_note"]', timeout=2000)
                pg.wait_for_timeout(300)
                shot(pg, "03_xac_nhan_truong_khong_co_trong_file",
                     "#112 — trạng thái thứ ba: cán bộ xác nhận trường không có trong "
                     "file, cảnh báo thiếu trường có đường đóng")
                pg.get_by_role('button', name='Xác nhận').click()
                pg.wait_for_timeout(1500)
            except Exception as exc:  # noqa: BLE001
                print(f"  (bỏ qua xác nhận vắng: {type(exc).__name__})")

            pg.goto(url, wait_until="networkidle")
            pg.wait_for_timeout(1000)
            shot(pg, "04_sau_khi_xac_nhan_vang",
                 "#112 — sau khi lưu: trường mang trạng thái “Không có trong file”, "
                 "bền vững ở saved_column_maps.absent_fields")
            br.close()
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
        print("server throwaway đã kill theo PID group")

    (OUT / "README.md").write_text(
        "# Ảnh E2E — màn gán cột theo trường khai (#112)\n\n"
        "Sinh bằng `ui_smoke.py` cạnh thư mục này, trên **dữ liệu bịa**.\n\n"
        + "".join(f"- `{n}` — {c}\n" for n, c in SHOTS),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
