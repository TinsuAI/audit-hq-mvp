"""E2E ảnh — cổng độ phủ định mức (issue #56, ticket #57–#63) + ba quyết định 06/08.

Seed dữ liệu Tầng 1 vào DB THROWAWAY rồi CHẠY THẬT `run_checks()` — ảnh phải là kết
quả check thật, không phải Finding bịa sẵn. Hai pháp nhân:

  DEMO_DM_DU    — đủ độ phủ định mức. Định mức khai 2024, 2025 không khai lại →
                  C4.3 vẫn tính được nhờ định mức kế thừa (#60).
  DEMO_DM_THIEU — thiếu độ phủ. 2024 là kỳ biên chưa xác nhận năm đầu nộp BCQT
                  (#57 + #62); 2025 có thành phẩm sản xuất mà chưa từng khai định
                  mức → C4.3 `not_evaluable` (#58 + #62). Hai sổ EPE/GC để có ca
                  "định mức khai ở sổ khác".

Chụp:
  01 danh sách DN — cột Độ phủ, tách nhóm: DN đủ độ phủ đứng trên dù điểm THẤP hơn
  02 trang DN thiếu độ phủ — khối "Chưa đánh giá được" + lý do, điểm kèm độ phủ
  03 bảng phát hiện C4.9 — liệt kê TỪNG mã thiếu định mức, không phải một con số
  04 chi tiết C4.9 ca "định mức khai ở sổ khác" — chứng cứ trỏ về dòng M16 sổ kia
  05 trang DN kỳ biên — C4.3 dừng vì chưa xác nhận năm đầu nộp BCQT
  06 bảng phát hiện C4.3 ở DN đủ độ phủ — cột "Kỳ khai định mức đã dùng"
  07 chi tiết C4.3 — chứng cứ định mức trỏ về KỲ ĐÃ KHAI (2024), không phải kỳ 2025
  08 form sửa DN — trường "Năm đầu nộp BCQT"
  09 danh mục kiểm tra — C4.9 trong nhóm 4

Dữ liệu seed là dữ liệu BỊA. Không đụng DB live hay cổng 8200 của user — server
throwaway riêng (cổng 8333), DB trong scratchpad. Chạy qua runner, xem brief.md.
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import Base, SessionLocal, engine
from app.models import (
    Company,
    CompanyYearScore,
    Finding,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.models.check_run import CheckRun
from app.pipeline.run_checks import run_checks

BASE = os.environ.get("M_BASE", "http://localhost:8333")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_dinhmuc", "shot12345")
DN_DU = "DEMO_DM_DU"
DN_THIEU = "DEMO_DM_THIEU"
HIDE_CSS = ".demo-banner{display:none!important}"

SRC_M15 = "Bao cao quyet toan NVL.xlsx"
SRC_M15A = "Bao cao quyet toan TP.xlsx"
SRC_M16 = "Dinh muc.xlsx"


def _purge(db) -> None:
    from app.models import User

    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    for code in (DN_DU, DN_THIEU):
        for c in db.query(Company).filter(Company.code == code).all():
            for m in (NvlBalance, SpBalance, Norm, Finding, CompanyYearScore, CheckRun):
                db.query(m).filter(m.company_id == c.id).delete()
            db.delete(c)
    db.commit()


def _nvl(db, cid, year, code, name, *, opening, imported, prod_out, closing=None, book=None):
    db.add(NvlBalance(
        company_id=cid, period_year=year, book=book, material_code=code,
        material_name=name, unit="MTR", opening_qty=opening, import_qty=imported,
        production_out_qty=prod_out,
        closing_qty=opening + imported - prod_out if closing is None else closing,
        source_file=SRC_M15,
    ))


def _sp(db, cid, year, code, name, *, intake, book=None):
    db.add(SpBalance(
        company_id=cid, period_year=year, book=book, product_code=code,
        product_name=name, unit="PCE", intake_qty=intake, export_qty=intake * 0.95,
        closing_qty=intake * 0.05, source_file=SRC_M15A,
    ))


def _norm(db, cid, year, product, material, qty, *, book=None):
    db.add(Norm(
        company_id=cid, period_year=year, book=book, product_code=product,
        product_unit="PCE", material_code=material, material_unit="MTR",
        norm_qty=qty, source_file=SRC_M16,
    ))


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")

        # --- DN đủ độ phủ. `first_bcqt_year` = 2024 xác nhận 2024 đúng là năm đầu
        # nộp BCQT, nên kỳ 2024 KHÔNG bị coi là kỳ biên (#57 mở khoá #62). ---
        du = Company(
            code=DN_DU, name="Công ty TNHH Dệt May Bình Minh (Demo)", tax_id="0100000001",
            industry="Dệt may", address="Khu công nghiệp Demo", slug="demo-dm-du",
            first_bcqt_year=2024,
        )
        db.add(du)
        db.flush()
        # 2024: khai định mức đầy đủ, tiêu hao lý thuyết KHỚP xuất SX.
        _norm(db, du.id, 2024, "TP-SOMI", "NPL-VAI", 2.5)
        _sp(db, du.id, 2024, "TP-SOMI", "Áo sơ mi nam dài tay", intake=1000)
        _nvl(db, du.id, 2024, "NPL-VAI", "Vải chính 100% cotton", opening=200,
             imported=3000, prod_out=2600)
        # 2025: KHÔNG khai lại Mẫu 16 — định mức 2,5 của 2024 vẫn hiệu lực (#60).
        # Sản lượng tăng gấp đôi nên tiêu hao lý thuyết 5.000 vượt xuất SX 3.000.
        _sp(db, du.id, 2025, "TP-SOMI", "Áo sơ mi nam dài tay", intake=2000)
        _nvl(db, du.id, 2025, "NPL-VAI", "Vải chính 100% cotton", opening=600,
             imported=3500, prod_out=3000)

        # --- DN thiếu độ phủ. `first_bcqt_year` để TRỐNG = chưa biết. ---
        thieu = Company(
            code=DN_THIEU, name="Công ty TNHH Cơ Khí Sao Mai (Demo)", tax_id="0100000002",
            industry="Cơ khí", address="Khu công nghiệp Demo", slug="demo-dm-thieu",
        )
        db.add(thieu)
        db.flush()
        # 2024 — kỳ sớm nhất đang giữ, chưa xác nhận năm đầu nộp BCQT → kỳ biên.
        _norm(db, thieu.id, 2024, "TP-KHUNG", "NPL-THEP", 4.0)
        _sp(db, thieu.id, 2024, "TP-KHUNG", "Khung thép định hình", intake=500)
        _sp(db, thieu.id, 2024, "TP-VO", "Vỏ máy tôn mạ kẽm", intake=300)
        # Tồn âm + lệch phương trình cân đối, để DN này có điểm CAO từ các check
        # KHÁC C4.3. Ảnh 01 phải chứng minh cổng tách nhóm chứ không phải tách theo
        # điểm: DN đủ độ phủ điểm 50 vẫn đứng TRÊN DN thiếu độ phủ điểm ~105.
        _nvl(db, thieu.id, 2024, "NPL-THEP", "Thép tấm cán nguội", opening=0,
             imported=2500, prod_out=2600, closing=-200)
        _nvl(db, thieu.id, 2024, "NPL-SON", "Sơn tĩnh điện", opening=0,
             imported=100, prod_out=180, closing=-150)

        # 2025 — hai sổ. Sổ EPE khai định mức cho TP-VO; sổ GC SẢN XUẤT TP-VO mà
        # không có dòng định mức nào trong sổ GC → "định mức khai ở sổ khác".
        # TP-MOI chưa từng khai định mức ở kỳ nào → cổng độ phủ chặn cả kỳ (#62).
        _norm(db, thieu.id, 2025, "TP-VO", "NPL-TON", 1.8, book="EPE")
        _sp(db, thieu.id, 2025, "TP-VO", "Vỏ máy tôn mạ kẽm", intake=400, book="EPE")
        _nvl(db, thieu.id, 2025, "NPL-TON", "Tôn mạ kẽm", opening=0, imported=900,
             prod_out=700, book="EPE")
        _sp(db, thieu.id, 2025, "TP-VO", "Vỏ máy tôn mạ kẽm", intake=120, book="GC")
        _sp(db, thieu.id, 2025, "TP-MOI", "Giá đỡ cơ khí kiểu mới", intake=250, book="GC")
        _nvl(db, thieu.id, 2025, "NPL-TON", "Tôn mạ kẽm", opening=0, imported=400,
             prod_out=300, book="GC")
        db.commit()

    # Chạy check THẬT — ảnh phải là kết quả check, không phải Finding dựng tay.
    for code, year in ((DN_DU, 2024), (DN_DU, 2025), (DN_THIEU, 2024), (DN_THIEU, 2025)):
        stats = run_checks(code, year)
        print(f"  run_checks {code} {year}: {stats.total} phát hiện, "
              f"chưa đánh giá được: {sorted(stats.not_evaluable)}")


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


def _open_groups(pg) -> None:
    pg.evaluate("document.querySelectorAll('details.finding-group').forEach(d => d.open = true)")
    pg.wait_for_timeout(300)


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000},
                                  device_scale_factor=2, locale="vi-VN")
        pg = ctx.new_page()
        _login(pg)

        # 01 — danh sách DN: cột Độ phủ, và DN đủ độ phủ đứng TRÊN dù điểm thấp hơn.
        _goto(pg, "/companies")
        _shot(pg, "01_danh_sach_do_phu_tach_nhom.png")

        # 02 — DN thiếu độ phủ, kỳ 2025: khối "Chưa đánh giá được" + điểm kèm độ phủ.
        _goto(pg, f"/companies/{DN_THIEU}?year=2025")
        _shot(pg, "02_chua_danh_gia_duoc_va_do_phu.png")

        # 03 — C4.9: liệt kê TỪNG mã thiếu định mức.
        _goto(pg, f"/companies/{DN_THIEU}?year=2025&check=C4.9")
        _open_groups(pg)
        _shot(pg, "03_c49_bang_thieu_dinh_muc_tung_ma.png")

        # 04 — chi tiết C4.9 ca "định mức khai ở sổ khác". Phải neo vào ĐÚNG mã TP-VO:
        # bảng xếp theo mã nên dòng đầu là TP-MOI (ca thiếu hẳn), không phải ca này.
        fid = pg.get_attribute("tbody tr[id^=finding-]:has-text('TP-VO')", "id").split("-")[1]
        _goto(pg, f"/findings/{fid}")
        _shot(pg, "04_c49_chi_tiet_dinh_muc_o_so_khac.png")

        # 05 — kỳ biên: C4.3 dừng vì chưa xác nhận năm đầu nộp BCQT.
        _goto(pg, f"/companies/{DN_THIEU}?year=2024")
        _shot(pg, "05_ky_bien_chua_xac_nhan_nam_dau_bcqt.png")

        # 06 — DN đủ độ phủ: C4.3 chạy nhờ định mức kế thừa, cột "Kỳ khai định mức".
        _goto(pg, f"/companies/{DN_DU}?year=2025&check=C4.3")
        _open_groups(pg)
        _shot(pg, "06_c43_dinh_muc_ke_thua_cot_ky_khai.png")

        # 07 — chứng cứ định mức trỏ về KỲ ĐÃ KHAI (2024), không phải kỳ phát hiện.
        fid = pg.get_attribute("tbody tr[id^=finding-]", "id").split("-")[1]
        _goto(pg, f"/findings/{fid}")
        _shot(pg, "07_chung_cu_dinh_muc_tro_ve_ky_da_khai.png")

        # 08 — form sửa DN: trường "Năm đầu nộp BCQT".
        _goto(pg, f"/companies/{DN_THIEU}/edit")
        _shot(pg, "08_form_nam_dau_nop_bcqt.png")

        # 09 — danh mục: C4.9 trong nhóm 4. KHÔNG chụp full_page: trang liệt kê trọn
        # 50 kiểm tra, ảnh full ra 3,2 MB mà phần cần xem chỉ là nhóm 4. Cuộn tới
        # dòng C4.9 rồi chụp đúng khung nhìn.
        _goto(pg, "/danh-muc-kiem-tra")
        pg.get_by_text("C4.9", exact=True).first.scroll_into_view_if_needed()
        pg.wait_for_timeout(400)
        _shot(pg, "09_danh_muc_c49.png", full=False)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print(f"cleaned up {ADMIN[0]} + {DN_DU} + {DN_THIEU}")
