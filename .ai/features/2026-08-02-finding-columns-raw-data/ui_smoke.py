"""E2E ảnh — cột số tách khỏi mô tả · nhãn tiếng Việt · link vào dữ liệu gốc.

Ba phản hồi sau buổi demo:
  1. Cán bộ vẫn phải mở Excel để kiểm số → link thẳng vào dữ liệu gốc đã lọc sẵn,
     màn dữ liệu gốc thêm bộ lọc và cột nguồn file.
  2. Mô tả lặp y hệt mọi dòng, số nằm trong chuỗi → bỏ cột mô tả, tách số ra cột.
  3. Nhãn phải là tiếng Việt; % có ký hiệu, tiền có đơn vị, số lớn có phân cách.

Seed một pháp nhân `DEMO_COT_SO` vào DB THROWAWAY rồi chụp:
  01 bảng phát hiện C1.1 — số ở cột riêng, không còn cột mô tả
  02 bảng phát hiện C2.1 — trọn phương trình cân đối thành cột, cột "Tồn ảo"
  03 trang chi tiết phát hiện — nhãn tiếng Việt + khối chứng cứ gọi tên biểu mẫu
  04 dữ liệu gốc BCCT — bộ lọc đầy đủ + cột nguồn file, đã lọc sẵn theo mã
  05 dữ liệu gốc BCCT — lọc thêm theo loại hình + khoảng ngày
  06 dữ liệu gốc Mẫu 15 — đổi tab vẫn giữ bộ lọc mã
  07 trang chi tiết mã — nút "Dữ liệu gốc →" ở từng khối
  08 /admin/hien-thi — chọn quy ước phân cách số
  09 bảng phát hiện sau khi đổi sang quy ước Anh/Mỹ

KHÔNG đụng DB live hay server :8200 của user — server throwaway riêng (port 8332),
DB trong scratchpad. Chạy qua runner (xem brief.md).
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import Base, SessionLocal, engine
from app.models import (
    Company,
    CompanyYearScore,
    DeclarationLine,
    Finding,
    Norm,
    NvlBalance,
    SpBalance,
)

BASE = os.environ.get("M_BASE", "http://localhost:8332")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_cot", "shot12345")
DN = "DEMO_COT_SO"
YEAR = 2025
HIDE_CSS = ".demo-banner{display:none!important}"

# Đường dẫn nguồn cố ý để nguyên dạng đầy đủ — ảnh phải chứng minh màn hình chỉ in
# TÊN FILE, không in đường dẫn máy chủ.
SRC_M15 = "/srv/audit-hq/data/DEMO/2025/BCQT/Bao cao quyet toan NVL 2025.xlsx"
SRC_M15A = "/srv/audit-hq/data/DEMO/2025/BCQT/Bao cao quyet toan TP 2025.xlsx"
SRC_M16 = "/srv/audit-hq/data/DEMO/2025/DINH_MUC/Dinh muc 2025.xlsx"
SRC_BCCT = "/srv/audit-hq/data/DEMO/2025/HANG_CHI_TIET/BaoCaoToKhai 2025.xls"

MATS = [
    # (mã, tên, tồn đầu, nhập, xuất SX, tồn cuối DN khai)
    ("NPL-0231", "Vải chính 100% cotton khổ 1m5", 1200.0, 84250.5, 80000.0, 5450.5),
    ("NPL-0455", "Chỉ may polyester 40/2", 300.0, 12480.0, 11900.0, 880.0),
    ("NPL-0788", "Khoá kéo kim loại 18cm", 0.0, 45600.0, 44000.0, 1600.0),
    ("NPL-1102", "Nhãn dệt satin", 150.0, 9800.0, 9500.0, 450.0),
]


def _purge(db) -> None:
    from app.app_settings import KEY_NUMBER_FORMAT, invalidate_cache
    from app.models import User
    from app.models.app_setting import AppSetting

    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    for c in db.query(Company).filter(Company.code == DN).all():
        for m in (NvlBalance, SpBalance, Norm, DeclarationLine, Finding, CompanyYearScore):
            db.query(m).filter(m.company_id == c.id).delete()
        db.delete(c)
    # Ảnh 09 ghi `number_format=en` vào DB. Không xoá thì lượt chụp SAU bắt đầu từ
    # trạng thái bẩn và mọi ảnh ra số kiểu Anh — đã dính đúng lỗi này một lần.
    db.query(AppSetting).filter(AppSetting.key == KEY_NUMBER_FORMAT).delete()
    db.commit()
    invalidate_cache()


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")

        c = Company(code=DN, name="Công ty TNHH May Tân Tiến (Demo)", tax_id="0303030303",
                    industry="Dệt may", address="KCN Demo", slug="demo-cot-so")
        db.add(c)
        db.flush()

        for i, (code, name, opening, imported, prod_out, closing) in enumerate(MATS, 1):
            db.add(NvlBalance(
                company_id=c.id, period_year=YEAR, row_no=i, material_code=code,
                material_name=name, unit="MTR", opening_qty=opening, import_qty=imported,
                reexport_qty=0.0, repurpose_qty=0.0, production_out_qty=prod_out,
                other_out_qty=0.0, closing_qty=closing, source_file=SRC_M15,
            ))
        db.add(SpBalance(
            company_id=c.id, period_year=YEAR, row_no=1, product_code="TP-A100",
            product_name="Áo sơ mi nam dài tay", unit="PCE", opening_qty=0.0,
            intake_qty=32000.0, export_qty=31500.0, closing_qty=500.0, source_file=SRC_M15A,
        ))
        db.add(Norm(
            company_id=c.id, period_year=YEAR, product_code="TP-A100",
            product_name="Áo sơ mi nam dài tay", product_unit="PCE",
            material_code="NPL-0231", material_name=MATS[0][1], material_unit="MTR",
            norm_qty=2.6314, source_file=SRC_M16,
        ))

        # Tờ khai: hai loại hình, trải các tháng để bộ lọc khoảng ngày có tác dụng.
        decls = [
            ("103010045210", date(YEAR, 2, 18), "E31", "NPL-0231", 40000.0, 0.9125, 1_642_500_000.0),
            ("103012288100", date(YEAR, 6, 4), "E31", "NPL-0231", 30000.0, 0.9450, 1_275_750_000.0),
            ("103015500431", date(YEAR, 11, 22), "E31", "NPL-0231", 14250.0, 0.9600, 615_600_000.0),
            ("103016120987", date(YEAR, 12, 9), "E62", "NPL-0231", 3000.0, 1.1200, 168_000_000.0),
            ("103011002233", date(YEAR, 3, 30), "E31", "NPL-0455", 12480.0, 0.2150, 80_496_000.0),
            ("103014455667", date(YEAR, 9, 15), "E31", "NPL-0788", 45600.0, 0.0850, 116_280_000.0),
        ]
        for no, d, cc, item, qty, price, total in decls:
            db.add(DeclarationLine(
                company_id=c.id, period_year=YEAR, declaration_no=no, declaration_date=d,
                customs_code=cc, line_no=1, item_code=item, item_name=dict(
                    (m[0], m[1]) for m in MATS
                ).get(item), hs_code="52081100", quantity=qty, unit="MTR",
                unit_price=price, currency="USD", value_total=total,
                partner="ABC TEXTILE CO., LTD", source_file=SRC_BCCT,
            ))

        # C1.1 — lệch nhập: số ở cột riêng, kèm cột "Cột M15 đối chiếu".
        # Ba mức lệch khác nhau để ảnh có đủ ba màu mức độ (>20% · 5–20% · <5%).
        for code, m15_import, bcct_sum in (
            ("NPL-0231", 84250.5, 62000.0),
            ("NPL-0455", 12480.0, 11200.0),
            ("NPL-0788", 45600.0, 44779.2),
        ):
            diff_pct = (m15_import - bcct_sum) / bcct_sum * 100
            sev = "critical" if abs(diff_pct) > 20 else (
                "warning" if abs(diff_pct) > 5 else "info")
            db.add(Finding(
                company_id=c.id, period_year=YEAR, check_code="C1.1", severity=sev,
                subject_type="material_code", subject_key=code,
                title=f"Lệch nhập NVL {code}: M15={m15_import:.2f} vs BCCT={bcct_sum:.2f}",
                details={
                    "company_type": "SXXK", "import_codes": ["E31"],
                    "m15_column": "import_qty", "unit": "MTR",
                    "m15_import": m15_import, "bcct_sum": bcct_sum, "diff_pct": diff_pct,
                },
                evidence_refs=[
                    {"table": "nvl_balances", "filter": {
                        "company_id": c.id, "period_year": YEAR, "material_code": code}},
                    {"table": "declaration_lines", "filter": {
                        "company_id": c.id, "period_year": YEAR, "item_code": code,
                        "customs_code__in": ["E31"]}},
                ],
            ))

        # C2.1 — mất cân bằng: trọn phương trình thành cột, có ca "tồn ảo".
        # `reported` phải KHÁC `expected` thì mới là mất cân bằng thật; ca thứ hai
        # tồn đầu = 0 mà tồn cuối > nhập − xuất → tồn ảo.
        for code, opening, imported, prod_out, reported in (
            ("NPL-0231", 1200.0, 84250.5, 80000.0, 7180.0),
            ("NPL-1102", 0.0, 9800.0, 9500.0, 1450.0),
        ):
            expected = opening + imported - prod_out
            details = {
                "opening": opening, "import": imported, "reexport": 0.0, "repurpose": 0.0,
                "production_out": prod_out, "other_out": 0.0,
                "closing_reported": reported, "closing_expected": expected,
                "diff": reported - expected,
            }
            if opening == 0.0 and reported > imported - prod_out:
                details["ghost_stock"] = True
            db.add(Finding(
                company_id=c.id, period_year=YEAR, check_code="C2.1", severity="critical",
                subject_type="material_code", subject_key=code,
                title=f"M15 không cân: NVL {code} tồn_cuối={reported:.2f}",
                details=details,
                evidence_refs=[{"table": "nvl_balances", "filter": {
                    "company_id": c.id, "period_year": YEAR, "material_code": code}}],
            ))

        # C4.3 — tiêu hao lý thuyết vượt xuất SX (tỷ lệ lớn, để thấy dấu %).
        db.add(Finding(
            company_id=c.id, period_year=YEAR, check_code="C4.3", severity="warning",
            subject_type="material_code", subject_key="NPL-0231",
            title="NVL NPL-0231: tiêu hao lý thuyết vượt xuất SX",
            details={
                "theoretical_consumption": 84204.8, "actual_m15_production_out": 80000.0,
                "diff_pct": 5.256, "divergent_norm_products": ["TP-A100"],
            },
            evidence_refs=[
                {"table": "norms", "filter": {
                    "company_id": c.id, "period_year": YEAR, "material_code": "NPL-0231"}},
                {"table": "nvl_balances", "filter": {
                    "company_id": c.id, "period_year": YEAR, "material_code": "NPL-0231"}},
            ],
        ))
        # Một ghi chú cán bộ để ảnh chứng minh ghi chú chuyển sang cột Trạng thái.
        db.flush()   # chưa flush thì query dưới không thấy các Finding vừa add
        noted = db.query(Finding).filter(
            Finding.company_id == c.id, Finding.check_code == "C1.1",
            Finding.subject_key == "NPL-0455",
        ).first()
        if noted is not None:
            noted.status = "noted"
            noted.notes = "Đã hỏi DN, chờ chứng từ bổ sung"

        db.add(CompanyYearScore(company_id=c.id, period_year=YEAR, score=186,
                                tier="Cần rà soát", breakdown={}))
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


def _open_groups(pg) -> None:
    pg.evaluate("document.querySelectorAll('details.finding-group').forEach(d => d.open = true)")
    pg.wait_for_timeout(300)


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # locale vi-VN: `<input type=date>` do TRÌNH DUYỆT vẽ theo locale của máy —
        # để mặc định en-US thì ô ngày hiện `mm/dd/yyyy`, không giống máy cán bộ.
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000},
                                  device_scale_factor=2, locale="vi-VN")
        pg = ctx.new_page()
        _login(pg)

        # Đặt lại quy ước VN QUA GIAO DIỆN. Xoá thẳng trong DB không đủ: server là
        # process riêng, cache setting 30s, nên vẫn trả giá trị `en` mà ảnh 09 lượt
        # trước đã ghi. Ghi qua route thì chính process đó bust cache.
        _goto(pg, "/admin/hien-thi")
        pg.check("input[name=number_format][value=vi]")
        pg.click("form[action='/admin/hien-thi'] button[type=submit]")
        pg.wait_for_load_state("networkidle")

        # 01 — C1.1: số ở cột riêng, không còn cột "Mô tả".
        _goto(pg, f"/companies/{DN}?year={YEAR}&check=C1.1")
        _open_groups(pg)
        _shot(pg, "01_bang_phat_hien_tach_cot_so.png")

        # 02 — C2.1: trọn phương trình cân đối thành cột + cột "Tồn ảo".
        _goto(pg, f"/companies/{DN}?year={YEAR}&check=C2.1")
        _open_groups(pg)
        _shot(pg, "02_c21_phuong_trinh_can_doi_thanh_cot.png")

        # 03 — chi tiết phát hiện: nhãn tiếng Việt + chứng cứ gọi tên biểu mẫu.
        fid = pg.get_attribute("tbody tr[id^=finding-]", "id").split("-")[1]
        _goto(pg, f"/findings/{fid}")
        _shot(pg, "03_chi_tiet_phat_hien_nhan_tieng_viet.png")

        # 04 — dữ liệu gốc BCCT đã lọc sẵn theo mã, có cột nguồn file.
        _goto(pg, f"/companies/{DN}/data?year={YEAR}&table=bcct&q=NPL-0231")
        _shot(pg, "04_du_lieu_goc_bcct_loc_san_theo_ma.png")

        # 05 — lọc thêm loại hình + khoảng ngày.
        _goto(pg, f"/companies/{DN}/data?year={YEAR}&table=bcct&q=NPL-0231"
                  f"&customs=E31&date_from={YEAR}-01-01&date_to={YEAR}-06-30")
        _shot(pg, "05_du_lieu_goc_loc_loai_hinh_va_ngay.png")

        # 06 — đổi tab sang Mẫu 15, bộ lọc mã giữ nguyên.
        pg.click("div.tabs a:has-text('Mẫu 15 —')")
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(400)
        _shot(pg, "06_doi_tab_van_giu_bo_loc.png")

        # 07 — trang chi tiết mã: nút "Dữ liệu gốc →" ở từng khối.
        _goto(pg, f"/companies/{DN}/items/NPL-0231?year={YEAR}")
        _shot(pg, "07_chi_tiet_ma_link_du_lieu_goc.png")

        # 08 — trang chọn quy ước phân cách số.
        _goto(pg, "/admin/hien-thi")
        _shot(pg, "08_admin_dinh_dang_hien_thi.png")

        # 09 — đổi sang quy ước Anh/Mỹ rồi xem lại bảng phát hiện.
        # Selector phải neo vào FORM: nút "Đăng xuất" trên thanh điều hướng cũng là
        # `button[type=submit]` và đứng trước trong DOM.
        pg.check("input[name=number_format][value=en]")
        pg.click("form[action='/admin/hien-thi'] button[type=submit]")
        pg.wait_for_load_state("networkidle")
        _goto(pg, f"/companies/{DN}?year={YEAR}&check=C1.1")
        _open_groups(pg)
        _shot(pg, "09_bang_phat_hien_quy_uoc_anh_my.png")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print(f"cleaned up {ADMIN[0]} + {DN}")
