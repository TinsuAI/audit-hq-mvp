"""E2E ảnh — chat gắn doanh nghiệp (ADR #20) + tổng quan AI v2 (ADR #21).

Seed hai pháp nhân `DEMO_CHAT_A` / `DEMO_CHAT_B` + cuộc trò chuyện đã gắn nhãn +
ba dòng tổng quan ở ba trạng thái (xong / đang chạy / cần đối chiếu) vào DB
THROWAWAY, rồi chụp:
  01 `/chat` nhóm theo doanh nghiệp — header section là DN, số đếm, "Chưa gán" cuối
  02 hộp thoại đổi doanh nghiệp của một cuộc
  03 sidebar: chip phạm vi + bộ lọc doanh nghiệp trong lịch sử
  04 sidebar: báo lệch phạm vi (cuộc gắn A, trang đang xem B)
  05 trang DN: bảng số liệu + nhận định bốn mục + nút gộp cả năm
  06 trạng thái đang viết nhận định (⏳ + link công việc)
  07 badge "cần đối chiếu" khi số trong nhận định không khớp bảng
  08 `/admin/ai`: chi tiêu + lời gọi tách theo loại (chat / tổng quan)

KHÔNG đụng DB live hay server :8200 của user — server throwaway riêng (port 8327),
DB trong scratchpad. Chạy qua runner (xem brief.md):
    DATABASE_URL=sqlite:///<workdb> \
        .venv/bin/uvicorn app.main:app --port 8327 --no-access-log &   # nền, kill theo PID
    M_BASE=http://127.0.0.1:8327 DATABASE_URL=sqlite:///<workdb> PYTHONPATH=. \
        .venv/bin/python .ai/features/2026-07-27-chat-scope-overview-v2/ui_smoke.py
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.ai.config import bust_cache, set_setting
from app.auth_users import create_user, get_user_by_username
from app.database import Base, SessionLocal, engine
from app.models import (
    AiConversation,
    AiMessage,
    AiUsage,
    CheckOverview,
    Company,
    CompanyYearScore,
    Finding,
    Job,
    NvlBalance,
)
from app.models.job import JobKind, JobStatus

BASE = os.environ.get("M_BASE", "http://localhost:8327")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_tq", "shot12345")
DN_A, DN_B = "DEMO_CHAT_A", "DEMO_CHAT_B"
YEAR = 2025
HIDE_CSS = ".demo-banner{display:none!important}"

_NOW = datetime.now(UTC).replace(tzinfo=None)


def _purge(db) -> None:
    from app.models import User

    for u in db.query(User).filter(User.username == ADMIN[0]).all():
        u.companies = []
        db.delete(u)
    for c in db.query(Company).filter(Company.code.in_([DN_A, DN_B])).all():
        cid = c.id
        for conv in db.query(AiConversation).filter(AiConversation.company_id == cid).all():
            db.query(AiMessage).filter(AiMessage.conversation_id == conv.id).delete()
            db.delete(conv)
        for m in (NvlBalance, Finding, CompanyYearScore, CheckOverview, Job):
            db.query(m).filter(m.company_id == cid).delete()
        db.delete(c)
    db.query(AiUsage).delete()
    db.commit()


def _conv(db, *, title, company_id, minutes_ago, msgs=2):
    at = _NOW - timedelta(minutes=minutes_ago)
    c = AiConversation(user=ADMIN[0], title=title, company_id=company_id, started_at=at)
    db.add(c)
    db.flush()
    for i in range(msgs):
        db.add(AiMessage(
            conversation_id=c.id, role="user" if i % 2 == 0 else "assistant",
            content="Nội dung minh hoạ.", created_at=at,
        ))
    return c


def _stats(total, *, distinct=8, top5=61.8, cover=6, prev_total=30):
    return {
        "check_code": "C1.6", "title": "Chuyển mục đích sử dụng", "year": YEAR,
        "total_findings": total,
        "severity_totals": {"critical": 30, "warning": 10, "info": 2},
        "concentration": {
            "distinct_subjects": distinct, "top5_share_pct": top5,
            "subjects_covering_80pct": cover,
            "top_subjects": [
                {"subject_key": "NPL-X12", "count": 9},
                {"subject_key": "MC50", "count": 7},
            ],
        },
        "numeric_fields": [{
            "key": "m15_repurpose", "is_pct": False, "n": total,
            "min": 1.0, "p50": 25.0, "p90": 300.0, "max": 900.0,
            "higher": total - 2, "lower": 2, "zero": 0,
        }],
        "previous_year": {
            "available": True, "year": YEAR - 1, "total": prev_total,
            "delta": total - prev_total, "new_subjects_count": 3,
            "new_subjects": ["NPL-X12"],
        },
    }


_SECTIONS = {
    "nhan_dinh": "Kiểm tra ghi nhận 42 phát hiện trên 8 mã nguyên liệu trong năm 2025.",
    "phan_bo": "5 mã lớn nhất chiếm 61,8% số phát hiện; 6 mã đã phủ 80% tổng số. "
               "So với năm 2024, số phát hiện tăng 12.",
    "diem_nong": [
        {"subject_key": "NPL-X12", "nhan_xet": "Lượng chuyển mục đích lớn nhất kỳ, cần đối chiếu chứng từ."},
        {"subject_key": "MC50", "nhan_xet": "Xuất hiện đều ở nhiều tờ khai, đề nghị rà soát định mức."},
    ],
    "de_xuat": [
        "Đối chiếu chứng từ chuyển mục đích sử dụng của hai mã nêu trên.",
        "Rà soát lại định mức tiêu hao của nhóm nguyên liệu liên quan.",
    ],
}


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")
        # Trợ lý phải BẬT thì /chat và sidebar mới render danh sách.
        bust_cache()
        set_setting("enabled", True, "smoke", db=db)
        set_setting("api_key", "sk-smoke", "smoke", db=db)
        set_setting("daily_budget_usd", 20.0, "smoke", db=db)

        a = Company(code=DN_A, name="Công ty TNHH An Phát (Demo)", tax_id="0101010101",
                    industry="Dệt may", address="KCN Demo A", slug="demo-chat-a")
        b = Company(code=DN_B, name="Công ty CP Bình Minh (Demo)", tax_id="0202020202",
                    industry="Điện tử", address="KCN Demo B", slug="demo-chat-b")
        db.add_all([a, b])
        db.flush()

        for i in range(40):
            db.add(NvlBalance(company_id=a.id, period_year=YEAR, material_code=f"NPL-{i:03d}",
                              unit="MTR", opening_qty=10, import_qty=100,
                              production_out_qty=80, closing_qty=30))

        # ── Cuộc trò chuyện: 3 của An Phát, 1 của Bình Minh, 1 chưa gán ──
        _conv(db, title="Vì sao C1.6 của An Phát nhiều phát hiện?", company_id=a.id, minutes_ago=8)
        _conv(db, title="So sánh tồn kho An Phát hai kỳ gần nhất", company_id=a.id, minutes_ago=90)
        _conv(db, title="Giải thích điểm rủi ro năm 2025", company_id=a.id, minutes_ago=300)
        _conv(db, title="Bình Minh có tờ khai nào bất thường?", company_id=b.id, minutes_ago=45)
        _conv(db, title="Hệ thống chấm điểm rủi ro như thế nào?", company_id=None, minutes_ago=200)

        # ── Phát hiện + điểm cho trang doanh nghiệp ──
        for check, sev, n in (("C1.6", "critical", 30), ("C1.1", "warning", 10), ("C4.3", "info", 2)):
            for i in range(n):
                db.add(Finding(
                    company_id=a.id, period_year=YEAR, check_code=check, severity=sev,
                    subject_type="material_code", subject_key=f"NPL-{i:03d}",
                    title=f"{check} NPL-{i:03d}: chênh lệch cần rà soát",
                    details={"m15_repurpose": 25.0 + i},
                ))
        db.add(CompanyYearScore(company_id=a.id, period_year=YEAR, score=214,
                                tier="Có dấu hiệu bất thường", breakdown={}))

        # ── Ba dòng tổng quan: xong · đang chạy · cần đối chiếu ──
        db.add(CheckOverview(
            company_id=a.id, period_year=YEAR, check_code="C1.6",
            content="", sections_json=_SECTIONS, aggregate_json=_stats(42),
            status=CheckOverview.STATUS_DONE, based_on_data_version=0,
            generated_at=_NOW, model="anthropic/claude-haiku-4-5",
            tokens_in=900, tokens_out=210, cost_usd=0.0021, latency_ms=1800,
        ))
        job = Job(kind=JobKind.AI_OVERVIEW.value,
                  payload={"company_code": DN_A, "year": YEAR, "check_code": "C1.1"},
                  status=JobStatus.RUNNING.value, created_by=1,
                  company_id=a.id, period_year=YEAR, started_at=_NOW)
        db.add(job)
        db.flush()
        db.add(CheckOverview(
            company_id=a.id, period_year=YEAR, check_code="C1.1",
            content="", aggregate_json=_stats(10, distinct=4, top5=100.0, cover=3, prev_total=6),
            status=CheckOverview.STATUS_RUNNING, job_id=job.id, based_on_data_version=0,
            generated_at=_NOW,
        ))
        db.add(CheckOverview(
            company_id=a.id, period_year=YEAR, check_code="C4.3",
            content="", aggregate_json=_stats(2, distinct=2, top5=100.0, cover=2, prev_total=1),
            sections_json={
                "nhan_dinh": "Kiểm tra ghi nhận 2 phát hiện, tỉ lệ lệch tới 137% so với định mức.",
                "phan_bo": "",
                "diem_nong": [{"subject_key": "NPL-X12", "nhan_xet": "Lệch định mức đáng kể."}],
                "de_xuat": ["Đối chiếu lại bảng định mức đã nộp."],
            },
            needs_review=True, unsupported_numbers="137",
            status=CheckOverview.STATUS_DONE, based_on_data_version=0, generated_at=_NOW,
        ))

        # ── Sổ chi phí: có cả chat lẫn tổng quan để /admin/ai tách được hai loại ──
        for kind, cost, n in ((AiUsage.KIND_CHAT, 0.0034, 6), (AiUsage.KIND_OVERVIEW, 0.0021, 3)):
            for _ in range(n):
                db.add(AiUsage(kind=kind, ref="demo", model="anthropic/claude-haiku-4-5",
                               tokens_in=900, tokens_out=210, cost_usd=cost,
                               user=ADMIN[0], created_at=_NOW))
        db.commit()


def _login(pg) -> None:
    pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
    pg.fill("input[name=user]", ADMIN[0])
    pg.fill("input[name=password]", ADMIN[1])
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")


def _shot(pg, name, *, full=True) -> None:
    pg.add_style_tag(content=HIDE_CSS)
    pg.mouse.move(4, 900)   # rời khỏi menu/nút để không dính trạng thái hover
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT / name), full_page=full)
    print("shot", name)


def _goto(pg, url) -> None:
    pg.goto(f"{BASE}{url}", wait_until="networkidle")
    pg.wait_for_timeout(700)   # danh sách cuộc / panel tải qua JS


def capture() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
        pg = ctx.new_page()
        _login(pg)

        # 01 — /chat nhóm theo doanh nghiệp.
        _goto(pg, "/chat")
        _shot(pg, "01_chat_nhom_theo_doanh_nghiep.png")

        # 02 — hộp thoại đổi doanh nghiệp của một cuộc.
        pg.hover(".ai-history-item")
        pg.click(".ai-history-item .h-move")
        pg.wait_for_timeout(500)
        _shot(pg, "02_doi_doanh_nghiep_cua_cuoc.png", full=False)
        pg.keyboard.press("Escape")

        # 03 — sidebar trên trang DN: chip phạm vi + bộ lọc lịch sử.
        _goto(pg, f"/companies/{DN_A}?year={YEAR}")
        pg.click("#ai-fab")
        pg.wait_for_timeout(900)
        pg.click("#ai-history")
        pg.wait_for_timeout(800)
        _shot(pg, "03_sidebar_chip_pham_vi_va_loc.png", full=False)

        # 04 — lệch phạm vi: mở một cuộc CỦA AN PHÁT rồi sang trang Bình Minh.
        # Phải chọn đúng cuộc đã gắn An Phát — cuộc chưa gắn DN thì không lệch.
        pg.click(".ai-history-item:has-text('An Phát')")
        pg.wait_for_timeout(800)
        _goto(pg, f"/companies/{DN_B}?year={YEAR}")
        pg.click("#ai-fab")
        pg.wait_for_timeout(1500)
        _shot(pg, "04_bao_lech_pham_vi.png", full=False)

        # 05 — trang DN: bảng số liệu + nhận định bốn mục + nút gộp.
        _goto(pg, f"/companies/{DN_A}?year={YEAR}&check=C1.6")
        pg.evaluate("document.querySelectorAll('details.finding-group').forEach(d => d.open = true)")
        pg.wait_for_timeout(400)
        _shot(pg, "05_bang_so_lieu_va_nhan_dinh.png")

        # 06 — đang viết nhận định (⏳ + link công việc).
        _goto(pg, f"/companies/{DN_A}?year={YEAR}&check=C1.1")
        pg.evaluate("document.querySelectorAll('details.finding-group').forEach(d => d.open = true)")
        pg.wait_for_timeout(400)
        _shot(pg, "06_dang_viet_nhan_dinh.png")

        # 07 — badge "cần đối chiếu".
        _goto(pg, f"/companies/{DN_A}?year={YEAR}&check=C4.3")
        pg.evaluate("document.querySelectorAll('details.finding-group').forEach(d => d.open = true)")
        pg.wait_for_timeout(400)
        _shot(pg, "07_badge_can_doi_chieu.png")

        # 08 — /admin/ai: lời gọi tách theo loại.
        _goto(pg, "/admin/ai")
        _shot(pg, "08_admin_ai_tach_theo_loai.png")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    seed()
    try:
        capture()
    finally:
        with SessionLocal() as db:
            _purge(db)
        print(f"cleaned up {ADMIN[0]} + {DN_A}/{DN_B}")
