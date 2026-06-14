"""Chụp ảnh các trang cho trang showcase tính năng — NÉT, crop gọn, ẩn banner.

Khác lần đầu: chụp retina (device_scale_factor=2), crop viewport thay vì full-page
(ảnh đọc được, đồng đều), ẩn `.demo-banner` + `#ai-fab` cho gọn. Seed hội thoại
chat (có tool message) để chụp ảnh Trợ lý AI đồng bộ. Deterministic — KHÔNG gọi LLM.

Seed user tạm `shot_show` (admin) + `shot_off` (officer, gán DN_001) + vài cuộc chat,
chụp xong xoá sạch.

Chạy với dev server :8200 đang chạy:
    PYTHONPATH=. .venv/bin/python .ai/features/2026-06-14-showcase/ui_smoke.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user, get_user_by_username
from app.database import SessionLocal
from app.models import AiConversation, AiMessage, Company, User

BASE = "http://localhost:8200"
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_show", "shot12345")
OFFICER = ("shot_off", "shot12345")

_TOOL_PREVIEW = json.dumps(
    {"count": 6, "companies": [
        {"code": "DN_003", "name": "Công ty TNHH May Mặc Hoa Sen (Demo)", "risk_score": 148},
        {"code": "DN_001", "name": "Công ty TNHH Điện Tử Phương Đông (Demo)", "risk_score": 116},
        {"code": "DN_004", "name": "Công ty TNHH Hoá Chất Nam Tiến (Demo)", "risk_score": 46},
    ]}, ensure_ascii=False,
)

HIDE_CSS = ".demo-banner{display:none!important}#ai-fab{display:none!important}"

# name, url, viewport_height, scroll_to(0,0)?, open_details_selector, who
SHOTS = [
    ("01_overview", "/companies", 880, None, "admin"),
    ("02_company_detail", "/companies/may-mac-hoa-sen?year=2022", 1000, "details.scoring-explainer", "admin"),
    ("03_finding_traceability", "/findings/1357", 1040, None, "admin"),
    ("04_item_detail", "/companies/DN_001/items/BANGDINH", 940, None, "admin"),
    ("05_catalog", "/danh-muc-kiem-tra", 900, None, "admin"),
    ("07_admin_ai", "/admin/ai", 900, None, "admin"),
    ("08_docs_index", "/tai-lieu", 720, None, "admin"),
    ("09_scoring_methodology", "/tai-lieu/scoring-methodology", 900, None, "admin"),
    ("10_upload", "/companies/DN_001/upload", 900, None, "admin"),
    ("11_access_audit", "/admin/audit", 760, None, "admin"),
    ("12_permissions_officer", "/companies", 840, None, "officer"),
]


def _purge(db) -> None:
    for c in db.query(AiConversation).filter(AiConversation.user.like("shot_%")).all():
        db.delete(c)
    for u in db.query(User).filter(User.username.like("shot_%")).all():
        u.companies = []
        db.delete(u)
    db.commit()


def seed() -> dict:
    now = datetime.now()
    ids = {}
    with SessionLocal() as db:
        _purge(db)
        if not get_user_by_username(db, ADMIN[0]):
            create_user(db, *ADMIN, "admin")
        off = get_user_by_username(db, OFFICER[0]) or create_user(db, *OFFICER, "officer")
        dn1 = db.query(Company).filter(Company.code == "DN_001").one_or_none()
        if dn1:
            off.companies = [dn1]
        db.commit()

        conv = AiConversation(user=ADMIN[0], page_url_seed="/companies",
                              title="Top 3 DN rủi ro cao nhất", started_at=now - timedelta(minutes=5))
        db.add(conv); db.flush()
        db.add_all([
            AiMessage(conversation_id=conv.id, role="user", content="Top 3 DN rủi ro cao nhất hiện nay?"),
            AiMessage(conversation_id=conv.id, role="assistant",
                      content="**DN_003** dẫn đầu với 148 điểm, kế đến **DN_001** (116) và "
                              "**DN_004** (46). Điểm là chỉ số rủi ro dữ liệu rate-based, "
                              "không phải tổng số phát hiện."),
            AiMessage(conversation_id=conv.id, role="tool", tool_name="list_companies",
                      tool_call_id="t1", content=_TOOL_PREVIEW),
        ])
        db.add(AiConversation(user=ADMIN[0], page_url_seed="/companies/DN_001?year=2024",
                              title="Rà soát DN_001 năm 2024", started_at=now - timedelta(days=1)))
        db.add(AiConversation(user=ADMIN[0], page_url_seed="/companies",
                              title="DN nào có tồn kho âm?", started_at=now - timedelta(hours=3)))
        db.commit()
        ids["tool_conv"] = conv.id
    return ids


def _login(ctx, creds):
    pg = ctx.new_page()
    pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
    pg.fill("input[name=user]", creds[0])
    pg.fill("input[name=password]", creds[1])
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def _prep(pg, height: int):
    pg.set_viewport_size({"width": 1300, "height": height})
    pg.add_style_tag(content=HIDE_CSS)
    pg.evaluate("window.scrollTo(0, 0)")


def capture(ids: dict) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Context riêng cho mỗi vai — KHÔNG chung cookie (login sau ghi đè login trước).
        ctx_a = browser.new_context(viewport={"width": 1300, "height": 900}, device_scale_factor=2)
        ctx_o = browser.new_context(viewport={"width": 1300, "height": 900}, device_scale_factor=2)
        admin = _login(ctx_a, ADMIN)
        officer = _login(ctx_o, OFFICER)

        for name, url, h, open_sel, who in SHOTS:
            pg = officer if who == "officer" else admin
            try:
                pg.set_viewport_size({"width": 1300, "height": h})
                pg.goto(f"{BASE}{url}", wait_until="networkidle")
                _prep(pg, h)
                if open_sel:
                    pg.evaluate("(s)=>document.querySelectorAll(s).forEach(d=>d.open=true)", open_sel)
                pg.wait_for_timeout(500)
                pg.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
                print("shot", name)
            except Exception as e:  # noqa: BLE001
                print("SKIP", name, url, repr(e))

        # Chat: Trợ lý trả lời + tool pill bung (deep-link cuộc đã seed).
        try:
            admin.set_viewport_size({"width": 1300, "height": 840})
            admin.goto(f"{BASE}/chat/{ids['tool_conv']}", wait_until="networkidle")
            _prep(admin, 840)
            admin.wait_for_selector("#chat-messages .ai-tool-pill.done", timeout=10000)
            admin.click("#chat-messages .ai-tool-pill.done")
            admin.wait_for_selector("#chat-messages .ai-tool-detail:not([hidden])", timeout=4000)
            admin.wait_for_timeout(400)
            admin.screenshot(path=str(OUT / "20_chat_tooluse.png"), full_page=False)
            print("shot 20_chat_tooluse")
        except Exception as e:  # noqa: BLE001
            print("SKIP chat_tooluse", repr(e))

        # Chat: mention @ dropdown.
        try:
            admin.set_viewport_size({"width": 1300, "height": 840})
            admin.goto(f"{BASE}/chat", wait_until="networkidle")
            _prep(admin, 840)
            admin.click("#chat-input")
            admin.type("#chat-input", "@", delay=60)
            admin.wait_for_selector(".ai-mention-pop:not([hidden]) .ai-mention-item", timeout=8000)
            admin.wait_for_timeout(400)
            admin.screenshot(path=str(OUT / "21_chat_mention.png"), full_page=False)
            print("shot 21_chat_mention")
        except Exception as e:  # noqa: BLE001
            print("SKIP chat_mention", repr(e))

        ctx_a.close()
        ctx_o.close()
        browser.close()


def cleanup() -> None:
    with SessionLocal() as db:
        _purge(db)


if __name__ == "__main__":
    ids = seed()
    try:
        capture(ids)
    finally:
        cleanup()
        print("cleaned up shot_* data")
