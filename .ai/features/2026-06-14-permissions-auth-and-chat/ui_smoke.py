"""UI smoke + screenshots: per-DN permissions, auth hardening, chat redesign.

Self-contained: seeds throwaway data (admin + officer scoped to 2 DN, audit
events, chat history), captures 8 screenshots, then cleans up. Uses the LOCAL
dev DB (real DN_001..004) for realistic shots; only `shot_*` rows are touched.

Run with the dev server up on :8200 (AI enabled so the chat FAB shows):
    PYTHONPATH=. .venv/bin/python \
      .ai/features/2026-06-14-permissions-auth-and-chat/ui_smoke.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.auth_users import create_user
from app.database import SessionLocal
from app.models import AccessEvent, AiConversation, AiMessage, Company, User

BASE = "http://localhost:8200"
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
ADMIN = ("shot_admin", "shot12345")
OFFICER = ("shot_officer", "shot12345")


def _purge(db) -> None:
    for c in db.query(AiConversation).filter(AiConversation.user.like("shot_%")).all():
        db.delete(c)
    db.query(AccessEvent).filter(AccessEvent.username.like("shot_%")).delete(
        synchronize_session=False
    )
    for u in db.query(User).filter(User.username.like("shot_%")).all():
        u.companies = []
        db.delete(u)
    db.commit()


def seed() -> int:
    now = datetime.now()
    with SessionLocal() as db:
        _purge(db)
        comps = {c.code: c for c in db.query(Company).filter(
            Company.code.in_(["DN_001", "DN_003"])).all()}
        create_user(db, *ADMIN, "admin")
        officer = create_user(db, *OFFICER, "officer")
        officer.companies = [comps["DN_001"], comps["DN_003"]]
        db.commit()

        for user, action, code, detail, mins in [
            ("shot_officer", "download", "DN_001", "M15_NVL_2024.xlsx", 4),
            ("shot_officer", "export", "DN_001", "year=2024", 9),
            ("shot_admin", "run_checks", "DN_003", "batch", 22),
            ("shot_admin", "export_query", None,
             "SELECT company_code, COUNT(*) FROM v_findings GROUP BY 1", 60),
            ("shot_officer", "download", "DN_003", "BCCT_2024.xlsx", 120),
            ("shot_admin", "export", "DN_001", "year=2023", 300),
        ]:
            db.add(AccessEvent(username=user, action=action, company_code=code,
                               detail=detail, created_at=now - timedelta(minutes=mins)))

        # Insert oldest->newest so id DESC (list order) = newest first.
        convs = [
            ("Rà soát tổng thể DN_001 năm 2024",
             "/companies/DN_001?year=2024", now - timedelta(days=20)),
            ("Vì sao DN_003 điểm rủi ro cao?",
             "/companies/DN_003?year=2024", now - timedelta(days=1)),
            ("Giải thích định mức M16 mã X-DL",
             "/companies/DN_003/items/X-DL?year=2024", now - timedelta(hours=3)),
            ("Top doanh nghiệp rủi ro cao nhất",
             "/companies", now - timedelta(minutes=12)),
        ]
        for title, seed_url, started in convs:
            conv = AiConversation(user="shot_admin", page_url_seed=seed_url,
                                  title=title, started_at=started)
            db.add(conv)
            db.flush()
            db.add(AiMessage(conversation_id=conv.id, role="user", content=title))
            db.add(AiMessage(conversation_id=conv.id, role="assistant", content="(demo)"))
        db.commit()
        return db.query(User).filter(User.username == "shot_officer").one().id


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
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT / name), full_page=full)
    print("saved", name)


def capture(officer_id: int) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        octx = browser.new_context()
        opg = _login(octx, *OFFICER)
        opg.goto(f"{BASE}/companies", wait_until="networkidle")
        _shot(opg, "01_permissions_officer_scoped.png")
        octx.close()

        actx = browser.new_context()
        apg = _login(actx, *ADMIN)
        apg.goto(f"{BASE}/companies", wait_until="networkidle")
        _shot(apg, "02_permissions_admin_all.png")
        apg.goto(f"{BASE}/admin/users", wait_until="networkidle")
        _shot(apg, "03_permissions_user_admin.png")
        apg.goto(f"{BASE}/admin/users/{officer_id}/scope", wait_until="networkidle")
        _shot(apg, "04_permissions_assign_dn.png")
        apg.goto(f"{BASE}/admin/audit", wait_until="networkidle")
        _shot(apg, "05_auth_access_audit.png")
        apg.goto(f"{BASE}/change-password", wait_until="networkidle")
        _shot(apg, "06_auth_change_password.png")

        apg.goto(f"{BASE}/companies/DN_001?year=2024", wait_until="networkidle")
        apg.wait_for_selector("#ai-fab:not(.hidden)", timeout=10000)
        apg.click("#ai-fab")
        apg.wait_for_selector(".ai-panel.open", timeout=5000)
        _shot(apg, "07_chat_page_context.png", full=False)
        apg.click("#ai-history")
        apg.wait_for_selector(".ai-history-item", timeout=6000)
        _shot(apg, "08_chat_history.png", full=False)
        actx.close()
        browser.close()


if __name__ == "__main__":
    oid = seed()
    try:
        capture(oid)
    finally:
        cleanup()
        print("cleaned up shot_* data")
