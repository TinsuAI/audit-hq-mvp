# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-25, cuối session AI Day 1-6):** Branch `feat/ai-assistant` đã build xong Day 1-6 plan AI assistant (10 commit, +4086 LOC, 168 tests pass). **CHƯA push lên main** — tránh trigger CI deploy half-baked. Prod live `https://audit-hq-demo.tinsu.ai` vẫn chạy build `a9700d0` (Day 0 self-service DN/upload/run-checks). Local dev `http://127.0.0.1:8200` đầy đủ AI assistant (sidebar + admin).

## Current State

### Branch `feat/ai-assistant` đang phát triển (chưa merge/push)
- 10 commit từ Day 1 đến Day 6 + 4 fix + 1 backlog. Chi tiết: `.ai/sessions/2026-05-25-ai-assistant-days-1-6.md`.
- AI assistant V1 đã hoạt động end-to-end với OpenRouter (key OpenRouter của Vương đã lưu trong `audit_hq.sqlite` local, masked qua admin UI).
- 6 tool ready: `search_findings`, `get_finding`, `query_raw_data`, `explain_check`, `list_companies`, `get_legal_context`.
- UI: sidebar FAB 💬 góc dưới phải sau login, panel 420px slide-in với streaming SSE, citation render link, history (📜) + new (+) + expand (⛶) buttons.
- Admin `/admin/ai`: 5 section — kết nối (test connection inline), models (dropdown auto-fetch), giới hạn + retention, flags, audit & cost (KPI today + 20 conv recent).

### Branch `main` (đã deploy prod, build `a9700d0`)
- Day 0 self-service: tạo DN, upload Excel BCQT, chạy lại kiểm tra qua UI.
- 4 DN demo: DN_001 GROWATT, DN_002 KIM_LONG, DN_003 HONG_AN (inject 12 finding + combo, score 3836), DN_004 DO_THANH.
- Banner amber "🧪 Dữ liệu mẫu" + suffix "(Demo)" trong tên DN.

### Stack & infra
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite (PRAGMA foreign_keys=ON từ Day 5+).
- AI: OpenAI SDK 2.38, OpenRouter base URL, prompt cache hỗ trợ Anthropic-style cache_control (chưa đo hit rate).
- Auth: cookie session, 1 user `admin/admin` (multi-user defer trong backlog).
- DB: `audit_hq.sqlite` local. 3 bảng AI mới: `ai_settings` (15 key), `ai_conversations`, `ai_messages` với cost_usd.
- Dev server đang chạy port 8200 (PID xem `lsof -i :8200`, log `/tmp/audit-hq-dev.log`). Reload tự khi sửa code/template.

## Recent Changes

- **2026-05-25 (Day 1-6 AI)** — Build AI assistant branch `feat/ai-assistant`, 10 commit. Detail: `.ai/sessions/2026-05-25-ai-assistant-days-1-6.md`.
- **2026-05-25 (sáng/Day 0)** — Self-service DN + upload + run-checks qua UI. Detail: `.ai/sessions/2026-05-25-user-create-upload-rerun.md`. Deploy live build `a9700d0`.
- **2026-05-25 (sớm)** — Filter 4 DN whitelist + UX polish realistic naming. Build `cbc4c8f`. Detail: `.ai/sessions/2026-05-25-filter-4dn-ux-rename-deploy.md`.
- **2026-05-21** — MVP build 10 tuần + UOM admin + deploy. Build `fd263f6`. Detail: `.ai/sessions/2026-05-21-mvp-build-deploy.md`.

## Next Steps

### Tiếp tục plan V1 (Day 7-8) khi quay lại session

1. **Day 7 — Internal QA**:
   - Chuẩn bị 20-30 câu hỏi điển hình cán bộ HQ (vd: "Tóm tắt DN_003", "Pháp lý cho C2.3", "So sánh DN_001 và DN_003 năm 2024").
   - Đo cache hit rate thực tế qua OpenRouter — verify Anthropic cache_control có route through không. Check `tokens_in` từ turn 2+ có giảm 70% không.
   - Compile prompt regression test set: input → expected tool calls + content marker → tests đảm bảo không drift.
   - Đo cost/conversation, latency p50/p95.
   - Fix prompt khi AI hallucinate / sai citation format.

2. **Day 8 — Deploy prod**:
   - Push `feat/ai-assistant` → main → CI tự deploy `audit-hq-demo.tinsu.ai`.
   - Vào `/admin/ai` prod paste lại OpenRouter API key (env var không seed nữa vì DB đã có default trống).
   - Watch admin/ai audit page 24h.
   - Soft-launch cho 2-3 internal user (Trọng Tín + Tinsu QA) trước, sau đó mở public.

### Backlog (defer khi đến lượt)
- **Multi-user + RBAC + tool-use ẩn cho officer**: chi tiết `.ai/BACKLOG.md`. ~3.5 ngày. Insert sau Day 7-8 hoặc gộp nếu sắp demo cán bộ HQ thật.

### Tech debt nhỏ
- Xoá backup `audit_hq.sqlite.bak-20260525-120743` (18M, untracked).
- Citation `[m15:row_no=88]` chưa link page riêng — có thể đi tới `/companies/{code}/data?year=Y&table=m15&q=` thay vì badge tĩnh.
- Retention cron chưa setup — settings có sẵn `history_retention_days` / `audit_retention_days` chỉ là config, cần daily job.
- Forbidden phrase guard (plan §8.2) chưa implement — defer khi gặp regression.
- Admin conv detail page (drill-in từ section 5 list).

### Verify browser chưa làm
- `+` button hiện input box (đã fix CSS specificity bug).
- `⛶` expand full-screen toggle.
- Citation badge click → redirect đúng.

## Blockers

Không có. Tất cả deliverable Day 1-6 đã hoàn thiện, branch chỉ chờ QA + push.

## Notes for Next AI Session

### Branch + remote
- Đang ở branch `feat/ai-assistant`, 10 commit ahead of main. KHÔNG push trừ khi user yêu cầu / Day 7-8 hoàn tất.
- Main branch ahead remote 4 commit từ session trước (đã deploy `a9700d0`).

### Dev server đang chạy
- Port `8200` (port 8000 conflict với `BCQT-System` local).
- Log: `/tmp/audit-hq-dev.log`.
- Start lại nếu cần: `cd /home/vp/workspace/client/audit-hq-mvp && nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`.

### OpenRouter key đã lưu trong DB local
- Key `sk-or-v1-4a9...fd4a` (Vương) đang trong `audit_hq.sqlite.ai_settings`. SQLite gitignored.
- `enabled=true`, `base_url=openrouter.ai/api/v1`.
- 3 model setting: default `~anthropic/claude-sonnet-latest`, fast `~anthropic/claude-haiku-latest`, deep `anthropic/claude-opus-4.7`. Lưu ý dấu `~` prefix là OpenRouter convention cho alias "latest".
- Khi đổi key qua admin UI: input password rỗng giữ key cũ; nhập có giá trị mới ghi đè.

### File quan trọng cho navigation
- Plan đầy đủ: `.ai/sessions/2026-05-25-ai-assistant-plan.md`.
- Session log AI build: `.ai/sessions/2026-05-25-ai-assistant-days-1-6.md`.
- Backlog defer: `.ai/BACKLOG.md`.
- Code AI core: `app/ai/{config,client,system_prompt,tools,cost,limits}.py`.
- Routes: `app/routes/{ai,admin_ai}.py`.
- UI: `app/static/sidebar.{css,js}`, `app/templates/{_ai_sidebar,admin_ai}.html`.
- Migration: `migrations/versions/a3c48313dddf_add_ai_settings_and_audit_tables.py`.

### Quy ước decisions
- Settings persist DB > env. Env chỉ làm seed lần đầu.
- Tool result truncate > 4000 chars để bảo vệ context window.
- Tool registry KHÔNG có write tool — chỉ read-only DB queries. Quyết định confirm/reject finding thuộc cán bộ HQ.
- Citation format `[finding:N]` / `[m15:row_no=88]` / `[check:Cx.y]` — sidebar.js parse regex.
- Cost estimate fallback DEFAULT_PRICE cho model lạ — log warning trong audit (chưa flag UI, defer).
- Conversation auto-title từ user message đầu tiên (80 ký tự).
- Cache control Anthropic-style segment catalog — `cache_supports_anthropic()` detect OpenRouter/Anthropic URL.

### Quirks đã gặp
- `~anthropic/claude-sonnet-latest` (tilde prefix) cần dùng đúng tên catalog OpenRouter, nếu không sẽ 404.
- SQLite FK enforce phải explicit `PRAGMA foreign_keys=ON` connect event (đã fix).
- E501 Vietnamese text trong system prompt — per-file ignore.
- `fastapi.File` cần thêm vào B008 whitelist pyproject.
- CSS `[hidden]` attribute KHÔNG đè class với `display: flex` — cần selector kết hợp `.X[hidden]`.

### Đề án vẫn là source of truth
- Catalog 49 kiểm tra ở `../audit-hq/de-an-audit-hq.md`. Mọi thay đổi nghiệp vụ → update đề án trước, MVP follow.
- Nội dung §1.4 pháp lý là source cho tool `get_legal_context` — parser regex trong `app/ai/tools.py`.

### Quy trình deploy (chưa chạy cho branch AI)
1. `git push origin feat/ai-assistant` để collaborators xem, OR
2. `git checkout main && git merge feat/ai-assistant && git push origin main` → GitHub Actions tự build + deploy + healthcheck.
3. Sau deploy: vào prod `/admin/ai` paste OpenRouter key. Local DB key KHÔNG tự copy.

### Hạ tầng kỹ thuật chung (unchanged)
- Server: `tinsu` Tailscale 100.84.189.87. WSL `ssh` lỗi → dùng `ssh.exe -F …` (memory `tinsu-server`).
- Cloudflare Tunnel `audit-hq-demo.tinsu.ai` → port 8200.
- Runner watchdog `runner-loop.sh` + cron `@reboot`.
