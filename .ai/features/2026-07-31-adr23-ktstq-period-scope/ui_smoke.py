"""E2E ảnh — ADR #23: cửa sổ kỳ, niên độ DN, template builtin, phạm vi KTSTQ 5 năm.

Seed MỘT pháp nhân throwaway `DEMO_KTSTQ` (niên độ tháng 4, đã đặt ngày quyết định
kiểm tra) vào DB THROWAWAY rồi chụp:
  01 trang tài liệu — banner độ phủ: dòng ngoài cửa sổ · không ngày · trùng chéo nhãn
  02 trang tài liệu — khoảng kỳ còn thiếu + cảnh báo chồng lấn kỳ liền kề
  03 cài đặt DN — chọn niên độ kế toán + ngày quyết định kiểm tra
  04 màn xác nhận cột — badge "Khớp mẫu" + cảnh báo cửa sổ kỳ lệch niên độ
  05 trang phát hiện — khối "kiểm tra chưa chạy được vì thiếu nguồn"
  06 trang phát hiện — phát hiện gắn nhãn ngoài phạm vi kiểm tra (hết thời hiệu)
  07 `/scope` — màn độ phủ phạm vi kiểm tra 5 năm

KHÔNG đụng DB live hay server :8200 của user — server throwaway riêng (port 8331),
DB trong scratchpad. Chạy qua runner (xem brief.md).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import Base, SessionLocal, engine
from app.models import (
    CheckRun,
    Company,
    CompanyPeriod,
    CompanyYearScore,
    DataFile,
    DeclarationLine,
    Finding,
    NvlBalance,
)

BASE = os.environ.get("M_BASE", "http://127.0.0.1:8331")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_ktstq", "shot12345")
DN = "DEMO_KTSTQ"
YEAR = 2025
HIDE_CSS = ".demo-banner{display:none!important}"


def _purge(db) -> None:
    from app.models import User

    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    for c in db.query(Company).filter(Company.code == DN).all():
        cid = c.id
        for m in (NvlBalance, DeclarationLine, Finding, CompanyYearScore,
                  CompanyPeriod, CheckRun, DataFile):
            db.query(m).filter(m.company_id == cid).delete()
        db.delete(c)
    db.commit()


def _decl(db, cid, *, label, day, no, item="NPL-001", line_no=1) -> None:
    db.add(DeclarationLine(
        company_id=cid, period_year=label, declaration_no=no, declaration_date=day,
        customs_code="E31", line_no=line_no, item_code=item, hs_code="52081100",
        quantity=120.0, unit="MTR",
    ))


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")

        c = Company(
            code=DN, name="Công ty TNHH Dệt May Tân Tiến (Demo)", tax_id="0303030303",
            industry="Dệt may", address="KCN Demo, Hải Dương", slug="demo-ktstq",
            fiscal_start_month=4, audit_decision_date=date(2026, 8, 1),
        )
        db.add(c)
        db.flush()
        cid = c.id

        # Niên độ 01/04/2025 – 31/03/2026. Kỳ 2024 để chồng lấn 1 quý (kỳ chuyển tiếp).
        db.add_all([
            CompanyPeriod(company_id=cid, period_year=YEAR, period_from=date(2025, 4, 1),
                          period_to=date(2026, 3, 31), is_manual=False, data_version=3),
            CompanyPeriod(company_id=cid, period_year=2024, period_from=date(2024, 1, 1),
                          period_to=date(2025, 6, 30), is_manual=True, data_version=1),
            CompanyPeriod(company_id=cid, period_year=2021, period_from=date(2021, 4, 1),
                          period_to=date(2022, 3, 31), is_manual=False, data_version=1),
            # Kỳ 2026 đọc cửa sổ DƯƠNG LỊCH từ tiêu đề file, lệch niên độ tháng 4 của
            # DN → màn xác nhận cột phải cảnh báo (không tự chọn hộ).
            CompanyPeriod(company_id=cid, period_year=2026, period_from=date(2026, 1, 1),
                          period_to=date(2026, 12, 31), is_manual=False, data_version=1),
        ])

        # Dòng THUỘC kỳ 2025: tháng 4–9/2025 và 1/2026 → thiếu hẳn quý 10–12/2025.
        for i, day in enumerate([
            date(2025, 4, 12), date(2025, 5, 9), date(2025, 6, 21), date(2025, 7, 3),
            date(2025, 8, 18), date(2025, 9, 27), date(2026, 1, 15), date(2026, 2, 6),
            date(2026, 3, 2),
        ]):
            _decl(db, cid, label=YEAR, day=day, no=f"10123456{i:02d}")
        # Dòng nạp ở nhãn 2025 nhưng NGÀY ngoài cửa sổ → vẫn lưu, chỉ cảnh báo.
        _decl(db, cid, label=YEAR, day=date(2025, 2, 14), no="1012345690")
        # Dòng không có ngày tờ khai → quy theo nhãn nạp.
        _decl(db, cid, label=YEAR, day=None, no="1012345691")
        # Trùng khoá chéo nhãn: cùng (số tờ khai, dòng) ở nhãn 2026, ngày trong kỳ 2025.
        _decl(db, cid, label=2026, day=date(2026, 1, 15), no="1012345606")

        # Kỳ 2021 — nằm ngoài cửa sổ [01/08/2021, 01/08/2026] ở đoạn đầu.
        _decl(db, cid, label=2021, day=date(2021, 5, 20), no="1002020201", item="NPL-CU")

        # M15 chỉ có ở kỳ 2025 → kỳ 2021 thiếu nguồn, và M15a/M16 thiếu ở CẢ hai kỳ.
        for i in range(6):
            db.add(NvlBalance(
                company_id=cid, period_year=YEAR, material_code=f"NPL-{i:03d}",
                unit="MTR", opening_qty=10, import_qty=100, production_out_qty=80,
                closing_qty=30,
            ))
        db.add(NvlBalance(company_id=cid, period_year=2021, material_code="NPL-CU",
                          unit="MTR", opening_qty=0, import_qty=50, closing_qty=50))

        # check_runs: hai kiểm tra chạy thật, ba kiểm tra chờ nguồn.
        ran = datetime(2026, 7, 31, 2, 0, 0)
        for code, reason in (
            ("C3.1", None), ("C3.2", None), ("C1.1", None),
            ("C2.2", "missing:m15a"), ("C2.4", "missing:m15a"),
            ("C4.3", "missing:m15a,m16"),
        ):
            db.add(CheckRun(
                company_id=cid, period_year=YEAR, check_code=code, ran_at=ran,
                finding_count=0, status="skipped" if reason else "ok",
                data_version=3, skip_reason=reason,
            ))

        # Phát hiện: kỳ 2025 trong phạm vi; kỳ 2021 ngoài phạm vi (hết thời hiệu).
        for i in range(3):
            db.add(Finding(
                company_id=cid, period_year=YEAR, check_code="C1.1", severity="warning",
                subject_type="material_code", subject_key=f"NPL-{i:03d}",
                title=f"Lệch nhập NVL NPL-{i:03d}: M15=100,00 vs BCCT=120,00 (+20,0%)",
                details={"diff_pct": 20.0},
            ))
        db.add(Finding(
            company_id=cid, period_year=2021, check_code="C1.2", severity="critical",
            subject_type="material_code", subject_key="NPL-CU",
            title="Mã NVL NPL-CU có tờ khai nhập nhưng không có trong M15 (tổng 120,00)",
        ))
        db.add(CompanyYearScore(company_id=cid, period_year=YEAR, score=34,
                                tier="Dữ liệu nhất quán", breakdown={}))

        # File đã đăng ký: một file khớp mẫu builtin, một file chưa khớp.
        db.add_all([
            DataFile(
                company_id=cid, period_year=2026, slot="m15",
                original_filename="TT39_BCQT_NVL_2026.xlsx",
                stored_path=f"{DN}/2026/BCQT/TT39_BCQT_NVL_2026.xlsx",
                size_bytes=182_400, parse_status="ok", row_count=6,
                parse_layout="standard", template_id="m15-tt39-chuan",
                match_source="builtin-template",
                parse_detail=(
                    '{"template_name": "Mẫu 15 TT39 — bố cục chuẩn", "review": "verified",'
                    ' "form_signature": "b7035babb726b641bf1af28751c8a41d",'
                    ' "columns": [{"field": "material_code", "label": "Mã NVL",'
                    ' "evidence": "builtin-template", "evidence_label": "Khớp mẫu có sẵn",'
                    ' "review": "verified"},'
                    ' {"field": "repurpose_qty", "label": "Chuyển MĐSD",'
                    ' "evidence": "builtin-template", "evidence_label": "Khớp mẫu có sẵn",'
                    ' "review": "verified"}],'
                    ' "column_map": {"material_code": 1, "repurpose_qty": 7}}'
                ),
            ),
            DataFile(
                company_id=cid, period_year=YEAR, slot="bcct",
                original_filename="BaoCaoHangChiTiet_2025.xlsx",
                stored_path=f"{DN}/{YEAR}/HANG_CHI_TIET/BaoCaoHangChiTiet_2025.xlsx",
                size_bytes=964_000, parse_status="ok", row_count=12,
            ),
        ])
        db.commit()


def _login(pg) -> None:
    pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
    pg.fill("input[name=user]", ADMIN[0])
    pg.fill("input[name=password]", ADMIN[1])
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")


def _shot(pg, name, *, full=True) -> None:
    pg.add_style_tag(content=HIDE_CSS)
    pg.mouse.move(4, 900)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / name), full_page=full)
    print("shot", name)


def _goto(pg, url) -> None:
    pg.goto(f"{BASE}{url}", wait_until="networkidle")
    pg.wait_for_timeout(500)


def capture() -> None:
    with SessionLocal() as db:
        file_id = db.query(DataFile.id).filter(DataFile.slot == "m15").scalar()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 1100}, device_scale_factor=2)
        pg = ctx.new_page()
        _login(pg)

        # 04 chụp TRƯỚC 01: trang tài liệu chạy `sync_data_files`, mà sync xoá dòng
        # registry không còn file trên đĩa — seed throwaway không có file thật.
        _goto(pg, f"/companies/{DN}/documents/file/{file_id}/review")
        _shot(pg, "04_badge_khop_mau_va_canh_bao_nien_do.png")

        # 01 + 02 — trang tài liệu: banner độ phủ, khoảng thiếu, chồng lấn.
        _goto(pg, f"/companies/{DN}/documents")
        pg.evaluate("document.querySelectorAll('details.doc-year').forEach(d => d.open = true)")
        pg.wait_for_timeout(300)
        _shot(pg, "01_banner_do_phu_bcct.png")
        el = pg.query_selector(".doc-coverage")
        if el:
            el.screenshot(path=str(OUT / "02_khoang_thieu_va_chong_lan.png"))
            print("shot 02_khoang_thieu_va_chong_lan.png")

        # 03 — cài đặt DN: niên độ + ngày quyết định kiểm tra.
        _goto(pg, f"/companies/{DN}/edit")
        _shot(pg, "03_cai_dat_nien_do_va_ngay_kiem_tra.png")

        # 05 — kiểm tra chưa chạy được vì thiếu nguồn.
        _goto(pg, f"/companies/{DN}?year={YEAR}")
        _shot(pg, "05_kiem_tra_chua_chay_thieu_nguon.png")

        # 06 — phát hiện ngoài phạm vi kiểm tra (kỳ 2021).
        _goto(pg, f"/companies/{DN}?year=2021")
        # CHỈ mở nhóm phát hiện — mở mọi <details> làm bung cả menu quản trị trên header.
        pg.evaluate("document.querySelectorAll('details.finding-group').forEach(d => d.open = true)")
        pg.wait_for_timeout(300)
        _shot(pg, "06_phat_hien_ngoai_pham_vi.png")

        # 07 — màn độ phủ phạm vi kiểm tra 5 năm.
        _goto(pg, f"/companies/{DN}/scope")
        _shot(pg, "07_man_do_phu_pham_vi_5_nam.png")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print("đã dọn seed")
