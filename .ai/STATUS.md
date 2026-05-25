# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-25, cuối session AI + Backlog):**
> Branch `feat/ai-assistant` — 15 commit ahead of main, 190 tests pass.
> AI assistant V1 hoàn chỉnh + multi-user RBAC + tech debt cleared.
> **Sẵn sàng deploy** — chờ user confirm Day 8.

## Current State

### Branch `feat/ai-assistant` (chưa merge/push)
15 commit ahead of main. Tất cả feature đã code + test. Không còn hardcoded TODO nào blocking deploy.

**AI Assistant V1** (Day 1-6):
- 6 tool read-only: `search_findings`, `get_finding`, `query_raw_data`, `explain_check`, `list_companies`, `get_legal_context`.
- Streaming SSE chat, citation parser link đến `/companies/{code}/data`.
- DB-backed settings (15 key), configurable qua `/admin/ai` không cần redeploy.
- Cost tracking + rate limit + daily budget cap + retention cron.
- Guardrails: forbidden phrase redaction + missing citation warning.

**Multi-user RBAC** (Backlog):
- Bảng `users(id, username, password_hash, role, created_at, last_login_at)`. Migration `b7e91f4d2a13`.
- PBKDF2-SHA256 password hash (stdlib, no new dep). Seed admin từ env `AUTH_USER`/`AUTH_PASSWORD`.
- `SessionUser(name, role)` với `is_admin`, `is_officer` property. Cookie stores `{u, r}` signed.
- `require_user` cho officer routes, `require_admin` cho `/admin/*`.
- Officer được: `/companies`, DN creation, upload, run-checks, AI chat.
- Officer KHÔNG thấy: `/admin/units`, `/admin/ai`, `/admin/users`, tool_call/tool_result events trong sidebar.
- Admin UI `/admin/users`: list/create/change-password/delete, guard last-admin + self-delete.

**Tech debt cleared**:
- Tool call cap configurable: `tool_call_cap` DB setting (default 10, admin đổi qua `/admin/ai` Section 3).
- Retention cron: asyncio task 24h interval, xoá conversation + orphan messages theo settings.
- Admin conversation drill-in: `/admin/ai/conversations/{id}` full transcript + cost metadata.
- Citation badge → link `/companies/{code}/data?year=Y&table=m15`.

### Branch `main` (prod live `audit-hq-demo.tinsu.ai`, build `a9700d0`)
- Day 0 self-service. Chưa có AI, chưa có multi-user.
- 4 DN demo: GROWATT, KIM_LONG, HONG_AN (score 3836), DO_THANH.

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite.
- AI: OpenAI SDK 2.38, OpenRouter base URL.
- Auth: itsdangerous signed cookie, role baked-in at login.
- 190 tests pass (15 warnings, no failures).

## Next Steps

### Day 8 — Deploy prod (chờ user confirm)
1. `git checkout main && git merge feat/ai-assistant && git push origin main`
2. CI deploy → `audit-hq-demo.tinsu.ai`.
3. Vào prod `/admin/ai` paste OpenRouter API key (local DB key KHÔNG tự copy lên).
4. Tạo tài khoản cán bộ HQ thử nghiệm qua `/admin/users`.
5. Watch audit page 24h.

### QA trước deploy (optional, không blocking)
- Chuẩn bị 20-30 câu hỏi điển hình cán bộ HQ → chạy thực với OpenRouter key, đo latency/cost.
- Verify citation click đúng trang data.
- Kiểm tra `+` new conv, `⛶` full-screen, tool_call ẩn khi đăng nhập officer.

### Còn nhỏ
- Xoá `audit_hq.sqlite.bak-20260525-120743` (18M untracked) — `rm audit_hq.sqlite.bak-*`.
- Session log chi tiết: viết `.ai/sessions/2026-05-25-ai-backlog-rbac.md`.

## Blockers
Không có.

## Key Files

| Area | Files |
|------|-------|
| AI core | `app/ai/{config,client,system_prompt,tools,cost,limits,guardrails,retention}.py` |
| Routes | `app/routes/{ai,admin_ai,admin_users}.py` |
| Auth | `app/auth.py`, `app/auth_users.py` |
| UI | `app/static/sidebar.{css,js}`, `app/templates/{_ai_sidebar,admin_ai,admin_users}.html` |
| Migrations | `migrations/versions/{a3c48313dddf,b7e91f4d2a13}*.py` |
| Tests | `tests/test_{users_auth,guardrails,smoke,routes_week9,findings_status}.py` |

## Dev Server
- Port `8200`. Log: `/tmp/audit-hq-dev.log`.
- Start: `cd /home/vp/workspace/client/audit-hq-mvp && nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`
- OpenRouter key trong `audit_hq.sqlite` local (masked qua admin UI). `enabled=true`.

## Notes

- Settings: DB > env. Env chỉ seed lần đầu khi bảng trống.
- Tool registry read-only — không có write tool. Confirm/reject finding thuộc người dùng.
- Citation format: `[finding:N]` / `[m15:row_no=88]` / `[check:Cx.y]` — sidebar.js parse regex.
- Role baked-in cookie at login. Stale role → re-login.
- `~anthropic/claude-sonnet-latest` (tilde prefix): OpenRouter alias convention.
- SQLite FK: `PRAGMA foreign_keys=ON` explicit (event listener trong `database.py`).
