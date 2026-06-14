"""UI smoke + screenshots: chat redesign (tool-pill gọn, trang /chat + URL,
mention @DN/@finding, admin xem-tất-cả).

Deterministic — KHÔNG gọi LLM: seed sẵn 1 cuộc có tool message để khi admin mở
lại (replay lịch sử) render pill gọn; mention dùng endpoint DB /api/chat/mentions.
Chỉ đụng dữ liệu `shot_*` trên DB dev thật (DN_001.. có sẵn finding), dọn sau khi xong.

Chạy với dev server :8200 đang chạy + AI bật:
    PYTHONPATH=. .venv/bin/python \
      .ai/features/2026-06-14-chat-redesign/ui_smoke.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user
from app.database import SessionLocal
from app.models import AiConversation, AiMessage, Company, User

BASE = "http://localhost:8200"
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_admin", "shot12345")
OFFICER = ("shot_officer", "shot12345")

_TOOL_PREVIEW = json.dumps(
    {"count": 6, "companies": [
        {"code": "DN_003", "name": "Công ty TNHH May Mặc Hoa Sen (Demo)", "risk_score": 148},
        {"code": "DN_001", "name": "Công ty TNHH Điện Tử Phương Đông (Demo)", "risk_score": 116},
    ]}, ensure_ascii=False,
)


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
        dn1 = db.query(Company).filter(Company.code == "DN_001").one_or_none()
        create_user(db, *ADMIN, "admin")
        officer = create_user(db, *OFFICER, "officer")
        if dn1:
            officer.companies = [dn1]
        db.commit()

        # Cuộc của admin CÓ tool message → replay render pill gọn ✓ list_companies.
        conv = AiConversation(user="shot_admin", page_url_seed="/companies",
                              title="Top 3 DN rủi ro cao nhất", started_at=now - timedelta(minutes=5))
        db.add(conv)
        db.flush()
        db.add_all([
            AiMessage(conversation_id=conv.id, role="user", content="Top 3 DN rủi ro cao nhất hiện nay?"),
            AiMessage(conversation_id=conv.id, role="assistant",
                      content="**DN_003** dẫn đầu với 148 điểm, kế đến **DN_001** (116). "
                              "Điểm là chỉ số rủi ro dữ liệu rate-based, không phải tổng finding."),
            AiMessage(conversation_id=conv.id, role="tool", tool_name="list_companies",
                      tool_call_id="t1", content=_TOOL_PREVIEW),
        ])
        # Vài cuộc khác để list phong phú + 1 cuộc của OFFICER (admin thấy → badge chủ).
        db.add(AiConversation(user="shot_admin", page_url_seed="/companies/DN_001?year=2024",
                              title="Rà soát DN_001 năm 2024", started_at=now - timedelta(days=1)))
        db.add(AiConversation(user="shot_officer", page_url_seed="/companies/DN_001",
                              title="DN_001 có phát hiện nghiêm trọng nào?",
                              started_at=now - timedelta(hours=2)))
        db.commit()
        ids["tool_conv"] = conv.id
    return ids


def cleanup() -> None:
    with SessionLocal() as db:
        _purge(db)


def _login(ctx, user, pw):
    pg = ctx.new_page()
    pg.set_viewport_size({"width": 1366, "height": 900})
    pg.goto(f"{BASE}/login", wait_until="domcontentloaded")
    pg.fill("#user", user)
    pg.fill("#password", pw)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def _shot(pg, name, full=True):
    pg.wait_for_timeout(450)
    pg.screenshot(path=str(OUT / name), full_page=full)
    print("saved", name)


def capture(ids: dict) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        pg = _login(ctx, *ADMIN)

        # 1+2. Tool-pill gọn (deep-link /chat/{id}) — collapsed rồi expanded.
        pg.goto(f"{BASE}/chat/{ids['tool_conv']}", wait_until="networkidle")
        pg.wait_for_selector("#chat-messages .ai-tool-pill.done", timeout=10000)
        _shot(pg, "01_tool_pill_compact.png")
        pg.click("#chat-messages .ai-tool-pill.done")
        pg.wait_for_selector("#chat-messages .ai-tool-detail:not([hidden])", timeout=4000)
        _shot(pg, "02_tool_pill_expanded.png")

        # 3. Trang /chat mới — bố cục 2 cột + danh sách cuộc (admin thấy cả của officer + badge chủ).
        pg.goto(f"{BASE}/chat", wait_until="networkidle")
        pg.wait_for_selector("#chat-list .ai-history-item", timeout=8000)
        _shot(pg, "03_chat_page_admin_all.png")

        # 4. Mention @ autocomplete (DN + finding từ DB, có scope).
        pg.click("#chat-input")
        pg.type("#chat-input", "@", delay=60)
        pg.wait_for_selector(".ai-mention-pop:not([hidden]) .ai-mention-item", timeout=8000)
        _shot(pg, "04_mention_dropdown.png")

        # 5. Regression: sidebar FAB ở trang thường vẫn render pill gọn (lõi chung).
        pg.goto(f"{BASE}/companies", wait_until="networkidle")
        pg.wait_for_selector("#ai-fab:not(.hidden)", timeout=10000)
        pg.click("#ai-fab")
        pg.wait_for_selector(".ai-panel.open", timeout=5000)
        pg.click("#ai-history")
        pg.wait_for_selector(".ai-history-item", timeout=6000)
        pg.click("text=Top 3 DN rủi ro cao nhất")
        pg.wait_for_selector("#ai-messages .ai-tool-pill.done", timeout=6000)
        _shot(pg, "05_sidebar_regression_pill.png", full=False)

        ctx.close()
        browser.close()


if __name__ == "__main__":
    ids = seed()
    try:
        capture(ids)
    finally:
        cleanup()
        print("cleaned up shot_* data")
