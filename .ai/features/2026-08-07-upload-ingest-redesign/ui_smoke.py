"""Ảnh E2E cho loạt vé thiết kế lại luồng tải lên → nạp dữ liệu (#80).

Chạy THẬT: seed DB throwaway, dựng file Excel thật trên đĩa, bật uvicorn ở cổng tự do,
đăng nhập bằng cookie ký sẵn (form login dính rate-limit + cookie Secure trên http),
chụp, rồi kill server theo PID group. KHÔNG đụng DB dev, KHÔNG đụng cổng 8200.

Dữ liệu BỊA hoàn toàn — không phải doanh nghiệp thật.

    .venv/bin/python .ai/features/2026-08-07-upload-ingest-redesign/ui_smoke.py
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "screenshots"
SCRATCH = Path("/tmp/claude-1000/ui-smoke-redesign.sqlite")
RAW = Path("/tmp/claude-1000/ui-smoke-raw")

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


def make_workbook(path: Path, rows: int, cols: int, *, formula_cell: bool = False) -> None:
    """Workbook thật để trang xem trước có cái mà đọc."""
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT"
    ws.append(["STT", "Mã NVL", "Tên hàng", "ĐVT", "Tồn đầu kỳ",
               "Nhập trong kỳ", "Xuất sản xuất", "Tồn cuối kỳ"]
              + [f"Cột {i}" for i in range(9, cols + 1)])
    for r in range(1, rows + 1):
        ws.append([r, f"NPL{r:04d}", "Vải chính", "MTR", 10 * r, 100 * r, 90 * r, 20 * r]
                  + [f"D{r}C{c}" for c in range(9, cols + 1)])
    if formula_cell:
        ws["E3"] = "=SUM(E2:E2)"
    wb.create_sheet("Định mức")
    wb.save(path)


def seed() -> None:
    from app.auth_users import create_user
    from app.database import Base, SessionLocal, engine
    from app.models import (
        CheckRun, Company, CompanyPeriod, CompanyYearScore, DataFile, Finding,
        Norm, NvlBalance, SpBalance,
    )

    Base.metadata.create_all(engine)
    gop = RAW / "DN_MINH_HOA/2025/BCQT/BaoCaoQuyetToan_2025.xlsx"
    make_workbook(gop, rows=120, cols=40, formula_cell=True)
    tokhai = RAW / "DN_MINH_HOA/2025/HANG_CHI_TIET/BaoCaoHangChiTiet_2025.xlsx"
    make_workbook(tokhai, rows=400, cols=20)

    with SessionLocal() as s:
        create_user(s, username="can_bo", password="MatKhau!2026", role="admin")
        c = Company(code="DN_MINH_HOA", name="Công ty TNHH Minh Hoạ", slug="dn-minh-hoa",
                    tax_id="0100000000", risk_score=37)
        c2 = Company(code="DN_THU_HAI", name="Công ty CP Thứ Hai", slug="dn-thu-hai",
                     tax_id="0200000000", risk_score=8)
        s.add_all([c, c2])
        s.flush()

        # --- Kỳ 2025: một workbook phục vụ ba biểu + một file tờ khai riêng ---
        s.add(CompanyPeriod(company_id=c.id, period_year=2025,
                            period_from=date(2025, 1, 1), period_to=date(2025, 12, 31),
                            data_version=4))
        for slot, rc in (("m15", 10_560), ("m15a", 501), ("m16", 113_561)):
            s.add(DataFile(company_id=c.id, period_year=2025, slot=slot,
                           original_filename="BaoCaoQuyetToan_2025.xlsx",
                           stored_path="DN_MINH_HOA/2025/BCQT/BaoCaoQuyetToan_2025.xlsx",
                           size_bytes=gop.stat().st_size, parse_status="ok", row_count=rc,
                           parse_message=("3 liên kết tới workbook ngoài — số có thể lấy "
                                          "từ file khác") if slot == "m15" else None))
        s.add(DataFile(company_id=c.id, period_year=2025, slot="bcct",
                       original_filename="BaoCaoHangChiTiet_2025.xlsx",
                       stored_path="DN_MINH_HOA/2025/HANG_CHI_TIET/BaoCaoHangChiTiet_2025.xlsx",
                       size_bytes=tokhai.stat().st_size, parse_status="ok", row_count=270_505))
        for i in range(40):
            s.add(NvlBalance(company_id=c.id, period_year=2025, row_no=i,
                             material_code=f"NPL{i:03d}", material_name="Vải chính",
                             unit="MTR", opening_qty=10, import_qty=100,
                             production_out_qty=90, closing_qty=20))
        for i in range(12):
            s.add(SpBalance(company_id=c.id, period_year=2025, row_no=i,
                            product_code=f"TP{i:03d}", product_name="Áo sơ mi", unit="PCE",
                            opening_qty=0, intake_qty=500, export_qty=480, closing_qty=20))
        for i in range(30):
            s.add(Norm(company_id=c.id, period_year=2025,
                       product_code=f"TP{i % 12:03d}", material_code=f"NPL{i:03d}",
                       material_unit="MTR", norm_qty=1.5))

        # --- Kỳ 2024: thiếu Mẫu 15a → vướng mắc lớp 1 ---
        s.add(CompanyPeriod(company_id=c.id, period_year=2024,
                            period_from=date(2024, 1, 1), period_to=date(2024, 12, 31),
                            data_version=1))
        for i in range(18):
            s.add(NvlBalance(company_id=c.id, period_year=2024, row_no=i,
                             material_code=f"NPL{i:03d}", material_name="Vải chính",
                             unit="MTR", opening_qty=5, import_qty=50,
                             production_out_qty=45, closing_qty=10))

        # --- Kỳ 2023: niên độ lệch dương lịch ---
        s.add(CompanyPeriod(company_id=c.id, period_year=2023,
                            period_from=date(2023, 4, 1), period_to=date(2024, 3, 31),
                            data_version=0))

        # Kết quả kiểm tra CŨ ở 2025: check_runs ở phiên bản 2, kỳ đã ở 4.
        s.add(CompanyYearScore(company_id=c.id, period_year=2025, score=37,
                               tier="Có chênh lệch"))
        for code, cnt in (("C1.1", 6), ("C2.1", 3), ("C4.1", 12)):
            s.add(CheckRun(company_id=c.id, period_year=2025, check_code=code,
                           finding_count=cnt, status="ok", data_version=2,
                           ran_at=datetime(2026, 8, 6, 14, 20)))
            for i in range(min(cnt, 2)):
                s.add(Finding(company_id=c.id, period_year=2025, check_code=code,
                              severity="Trung bình", title=f"Chênh lệch ở mã NPL{i:03d}",
                              subject_type="material", subject_key=f"NPL{i:03d}",
                              status="new"))

        # DN thứ hai: kết quả còn mới, để đối chiếu ở bảng danh sách.
        s.add(CompanyPeriod(company_id=c2.id, period_year=2025,
                            period_from=date(2025, 1, 1), period_to=date(2025, 12, 31),
                            data_version=1))
        s.add(CompanyYearScore(company_id=c2.id, period_year=2025, score=8, tier="Thấp"))
        s.add(CheckRun(company_id=c2.id, period_year=2025, check_code="C1.1",
                       finding_count=1, status="ok", data_version=1,
                       ran_at=datetime(2026, 8, 7, 9, 0)))
        s.commit()
        return {"file_id": s.query(DataFile).filter_by(slot="m15").first().id}


def shot(pg, name: str, caption: str, *, full: bool = True) -> None:
    path = OUT / f"{name}.png"
    pg.screenshot(path=str(path), full_page=full)
    SHOTS.append((path.name, caption))
    print(f"  {path.name}")


def main() -> int:
    ids = seed()
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
            ctx = br.new_context(viewport={"width": 1500, "height": 1200},
                                 device_scale_factor=2)
            ctx.add_cookies([{"name": SESSION_COOKIE_NAME, "value": cookie,
                              "domain": "127.0.0.1", "path": "/"}])
            pg = ctx.new_page()

            pg.goto(f"{base}/companies/dn-minh-hoa/documents", wait_until="networkidle")
            pg.wait_for_timeout(500)
            shot(pg, "01_man_du_lieu_mot_dn_moi_ky_la_dong",
                 "#86+#87+#90 — một DN, mọi kỳ là dòng; đếm theo kiểm tra; vướng mắc "
                 "xếp theo cách gỡ; tóm tắt theo loại + danh sách file thật")

            pg.goto(f"{base}/companies", wait_until="networkidle")
            pg.wait_for_timeout(400)
            shot(pg, "02_danh_sach_dn_danh_dau_ket_qua_cu",
                 "#90 — điểm rủi ro vẫn nằm trong bảng xếp hạng, kèm dấu kết quả cũ; "
                 "KHÔNG giấu số, KHÔNG loại DN khỏi bảng")

            pg.goto(f"{base}/companies/dn-minh-hoa?year=2025", wait_until="networkidle")
            pg.wait_for_timeout(400)
            shot(pg, "03_man_phat_hien_danh_dau_ket_qua_cu",
                 "#90 — màn phát hiện cũng đánh dấu, kèm nút chạy lại thủ công")

            pg.goto(f"{base}/companies/dn-minh-hoa?year=abc", wait_until="networkidle")
            shot(pg, "04_trang_loi_tham_so_khong_hop_le",
                 "#94 — tham số sai kiểu ra trang tiếng Việt, không phải JSON thô")

            pg.goto(f"{base}/companies/KHONG_TON_TAI", wait_until="networkidle")
            shot(pg, "05_trang_loi_khong_tim_thay",
                 "#94 — mã DN không tồn tại; trước đây cũng đổ JSON thô")

            fid = ids["file_id"]
            pg.goto(f"{base}/companies/dn-minh-hoa/documents/file/{fid}/preview",
                    wait_until="networkidle")
            pg.wait_for_timeout(2500)
            shot(pg, "06_luoi_cuon_xem_truoc",
                 "#83+#91 — lưới cuộn ảo, bỏ hạn mức 100 dòng / 40 cột / 25MB")

            for label in ("Hiện cột hệ thống đang đọc", "Hiện công thức trong ô"):
                try:
                    pg.get_by_label(label).check(timeout=2500)
                    pg.wait_for_timeout(900)
                except Exception as exc:  # noqa: BLE001
                    print(f"  (bỏ qua công tắc {label!r}: {type(exc).__name__})")
            shot(pg, "07_hai_cong_tac_cot_va_cong_thuc",
                 "#83+#91 — hai công tắc: cột hệ thống đang đọc, và công thức trong ô")

            pg.goto(f"{base}/companies/dn-minh-hoa/documents/file/{fid}/review",
                    wait_until="networkidle")
            pg.wait_for_timeout(600)
            shot(pg, "08_xac_nhan_vi_tri_cot",
                 "#84+#95 — màn xác nhận cột: map cán bộ thắng mẫu biểu theo từng trường, "
                 "đẳng thức kiểm lại sau khi áp")
            br.close()
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
        print("server throwaway đã kill theo PID group")

    index = HERE / "screenshots" / "README.md"
    index.write_text(
        "# Ảnh E2E — thiết kế lại luồng tải lên → nạp dữ liệu (#80)\n\n"
        "Sinh bằng `ui_smoke.py` cạnh thư mục này, trên **dữ liệu bịa**.\n\n"
        + "".join(f"- `{n}` — {c}\n" for n, c in SHOTS),
        encoding="utf-8",
    )
    print(f"{len(SHOTS)} ảnh + README ở {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
