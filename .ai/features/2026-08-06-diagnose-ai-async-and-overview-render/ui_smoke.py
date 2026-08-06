"""E2E ảnh — `/diagnose-ai` chạy ở hàng đợi + tổng quan AI không đổ JSON thô.

Seed vào DB THROWAWAY rồi chụp. **Không gọi LLM**: hai thứ đang chứng minh nằm ở
tầng hàng đợi và tầng render, không ở lời gọi model.

  Ảnh 01-02 (hàng đợi) — job `ai_diagnose` seed đúng hai trạng thái mà cán bộ gặp:
  vừa xếp xong (request đã trả, LLM chưa chạy) và đã xong (chẩn đoán hiện thành
  khối riêng). Trước đây lời gọi nằm TRONG request nên với bộ file 006 luôn 524.

  Ảnh 03 (parse) — `sections_json` KHÔNG bịa: lấy chuỗi model trả có XUỐNG DÒNG
  THẬT bên trong một chuỗi JSON rồi chạy `parse_sections()` THẬT lên nó. Trước bản
  vá, chính chuỗi này trả None và rơi xuống nhánh in thô. Ảnh chứng minh parse.

  Ảnh 04-05 (xuống cấp) — `sections_json = None` + `content` là khối JSON, đúng
  trạng thái đã chụp được trên màn hình 06/08. Nay hiện câu nói rõ chưa viết được,
  nguyên văn giữ trong <details> chứ không đổ ra giữa trang.

Bảng số liệu trong panel lấy từ `build_stats()` THẬT trên finding đã seed, không
phải số bịa dán vào.

Dữ liệu seed là dữ liệu BỊA. Không đụng DB live hay cổng 8200 của user — server
throwaway riêng (cổng 8334), DB trong scratchpad. Xem brief.md.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.ai.overview_content import finalize_sections, parse_sections
from app.ai.overview_stats import build_stats
from app.auth_users import create_user, get_user_by_username
from app.database import Base, SessionLocal, engine
from app.models import CheckOverview, Company, CompanyYearScore, Finding
from app.models.check_run import CheckRun
from app.models.job import Job, JobKind, JobStatus

BASE = os.environ.get("M_BASE", "http://localhost:8334")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_aidiag", "shot12345")
DN = "DEMO_AI_DIAG"
YEAR = 2025
HIDE_CSS = ".demo-banner{display:none!important}"

# Chuỗi model trả về, có XUỐNG DÒNG THẬT giữa một câu dài trong `nhan_dinh`.
# `json.loads` mặc định `strict=True` từ chối ký tự điều khiển thô trong chuỗi →
# trước bản vá đây là None. Render bằng `white-space: pre-wrap` thì nhìn y hệt JSON
# hợp lệ, nên soi ảnh màn hình không thấy được lỗi.
RAW_OK = (
    '{\n'
    '  "nhan_dinh": "Kiểm tra C1.1 ghi nhận 4 phát hiện lệch số lượng nhập NVL,\n'
    'trong đó 2 nghiêm trọng và 1 cảnh báo.",\n'
    '  "phan_bo": "",\n'
    '  "diem_nong": [\n'
    '    {"subject_key": "NPL-VAI-01", "nhan_xet": "Lệch âm lớn nhất trong kỳ."}\n'
    '  ],\n'
    '  "de_xuat": ["Đối chiếu tờ khai nhập với sổ kho cho các mã lệch âm."]\n'
    '}'
)

# Khối JSON parse KHÔNG được (cụt giữa chừng vì chạm `max_tokens`) — đây là thứ đã
# bị đổ nguyên ra màn hình cán bộ.
RAW_BAD = (
    '{\n'
    '  "nhan_dinh": "Kiểm tra C2.1 ghi nhận 3 phát hiện mất cân đối M15.",\n'
    '  "phan_bo": "Các phát hiện tập trung ở 3 mã nguyên phụ liệu chính.",\n'
    '  "diem_nong": [\n'
    '    {"subject_key": "NPL-VAI-01", "nhan_xet": "Tồn cuối kỳ không khớp phương'
)


def _purge(db) -> None:
    from app.models import User

    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    for c in db.query(Company).filter(Company.code == DN).all():
        db.query(Job).filter(Job.company_id == c.id).delete()
        for m in (Finding, CompanyYearScore, CheckRun, CheckOverview):
            db.query(m).filter(m.company_id == c.id).delete()
        db.delete(c)
    db.commit()


def _findings(db, cid) -> None:
    """4 phát hiện C1.1 + 3 phát hiện C2.1 — đủ để panel có bảng số liệu thật."""
    rows = [
        ("NPL-VAI-01", "critical", -18.4), ("NPL-VAI-02", "critical", -12.1),
        ("NPL-CUC-01", "warning", 6.3), ("NPL-CHI-01", "info", 1.2),
    ]
    for code, sev, diff in rows:
        db.add(Finding(
            company_id=cid, period_year=YEAR, check_code="C1.1", severity=sev,
            subject_type="material_code", subject_key=code,
            title=f"Lệch nhập NVL {code}: chênh {diff:.1f}%",
            details={"m15_column": "import_qty", "unit": "MTR", "diff_pct": diff},
            evidence_refs=[{"table": "nvl_balances", "filter": {
                "company_id": cid, "period_year": YEAR, "material_code": code}}],
        ))
    for code in ("NPL-VAI-01", "NPL-VAI-02", "NPL-CUC-01"):
        db.add(Finding(
            company_id=cid, period_year=YEAR, check_code="C2.1", severity="critical",
            subject_type="material_code", subject_key=code,
            title=f"M15 không cân: NVL {code}",
            details={"unit": "MTR"},
            evidence_refs=[{"table": "nvl_balances", "filter": {
                "company_id": cid, "period_year": YEAR, "material_code": code}}],
        ))


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")

        # AI bật → nút "🔄 Tạo lại" hiện, câu xuống cấp trỏ vào đúng nút đó.
        from app.ai.config import set_setting
        set_setting("enabled", True, ADMIN[0], db=db)
        set_setting("api_key", "sk-demo-khong-dung-that", ADMIN[0], db=db)

        c = Company(
            code=DN, name="Công ty TNHH May Mặc Hồng Phát (Demo)", tax_id="0100000009",
            industry="Dệt may", address="Khu công nghiệp Demo", slug="demo-ai-diag",
        )
        db.add(c)
        db.flush()
        _findings(db, c.id)
        ran = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        for code in ("C1.1", "C2.1"):
            db.add(CheckRun(company_id=c.id, period_year=YEAR, check_code=code,
                            ran_at=ran, status="ok", finding_count=4 if code == "C1.1" else 3))
        db.add(CompanyYearScore(company_id=c.id, period_year=YEAR, score=42,
                                tier="Có chênh lệch nhỏ", breakdown={}))
        db.commit()

        # ── Tổng quan: parse THẬT trên hai chuỗi model, không dán sections bịa ──
        for code, raw in (("C1.1", RAW_OK), ("C2.1", RAW_BAD)):
            stats = build_stats(db, company_id=c.id, period_year=YEAR, check_code=code)
            sections, _ = finalize_sections(parse_sections(raw), stats, set())
            db.add(CheckOverview(
                company_id=c.id, period_year=YEAR, check_code=code,
                content=raw, sections_json=sections, aggregate_json=stats,
                status=CheckOverview.STATUS_DONE, based_on_run_at=ran,
                based_on_data_version=0,
                generated_at=datetime.now(UTC).replace(tzinfo=None),
                model="demo/seed", tokens_in=0, tokens_out=0, cost_usd=0.0,
            ))
        db.commit()
        print("C1.1 sections:", "parse ĐƯỢC" if parse_sections(RAW_OK) else "None")
        print("C2.1 sections:", "parse ĐƯỢC" if parse_sections(RAW_BAD) else "None (đúng ý)")

        # ── Job ai_diagnose đã xong ──
        # KHÔNG seed job `queued`: server này chạy worker AI thật, nó sẽ nhặt job đó
        # chạy mất trước khi kịp chụp. Việc "request trả ngay" là tính chất thời gian,
        # ảnh không chứng minh được — chỗ chứng minh là
        # `test_diagnose_ai_does_not_call_the_llm_inside_the_request`.
        u = get_user_by_username(db, ADMIN[0])
        payload = {"company_code": DN, "year": YEAR, "username": ADMIN[0]}
        db.add(Job(
            kind=JobKind.AI_DIAGNOSE.value, status=JobStatus.DONE.value, payload=payload,
            created_by=u.id, company_id=c.id, period_year=YEAR,
            # Mốc thời gian phải đọc xuôi: tạo → bắt đầu → hoàn tất.
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=4),
            started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=3),
            finished_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1),
            result={
                "company_code": DN, "year": YEAR,
                "ai_result": (
                    "File BCCT không đọc được vì trang tính đầu tiên là bảng tổng hợp "
                    "cấp tờ khai, không phải bảng hàng chi tiết.\n\n"
                    "Dòng tiêu đề nằm ở hàng 5 thay vì hàng 9 như mẫu chuẩn, nên mọi cột "
                    "lệch một ô: cột 24 đang là Đơn giá chứ không phải Tổng số lượng.\n\n"
                    "Cách xử lý: ở trang Tài liệu, ghim trang tính đúng cho file này rồi "
                    "nạp lại. Không cần sửa file."
                ),
            },
        ))
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
        c = db.query(Company).filter_by(code=DN).one()
        done_id = db.query(Job).filter_by(company_id=c.id).order_by(Job.id).first().id

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000},
                                  device_scale_factor=2, locale="vi-VN")
        pg = ctx.new_page()
        _login(pg)

        # 01 — điểm vào: nút nhờ AI chẩn đoán (nay xếp job thay vì chờ trong request),
        # và ô BCCT nhận NHIỀU file kèm câu dặn không gộp tay (PR #78, đã merge).
        _goto(pg, f"/companies/{DN}/upload?year={YEAR}")
        _shot(pg, "01_form_tai_len_bcct_nhieu_file.png")

        # 02 — chẩn đoán xong: khối riêng, xuống dòng giữ nguyên. Trước đây văn bản
        # này bị ép vào một ô bảng dưới nhãn thô `ai_result`.
        _goto(pg, f"/jobs/{done_id}")
        _shot(pg, "02_job_chan_doan_khoi_rieng.png")

        # 03 — C1.1: JSON có xuống dòng thật trong chuỗi nay parse được → bốn mục.
        _goto(pg, f"/companies/{DN}?year={YEAR}&check=C1.1")
        _shot(pg, "03_tong_quan_parse_duoc_bon_muc.png")

        # 04 — C2.1: parse trượt → nói rõ chưa viết được, KHÔNG đổ JSON ra giữa trang.
        _goto(pg, f"/companies/{DN}?year={YEAR}&check=C2.1")
        _shot(pg, "04_tong_quan_khong_do_json_tho.png")

        # 05 — mở <details>: nguyên văn vẫn giữ cho người cần soi, chỉ không mặc định.
        # CHỈ mở <details> trong panel tổng quan — menu điều hướng cũng là <details>,
        # mở tất là hai dropdown bung ra che mất trang.
        pg.evaluate("document.querySelectorAll('.check-overview details').forEach(d => d.open = true)")
        pg.wait_for_timeout(300)
        _shot(pg, "05_tong_quan_nguyen_van_trong_details.png")

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
