# 2026-05-25 — AI Assistant V1: build Day 1-6 trên branch feat/ai-assistant

> Session marathon implement plan AI assistant (`.ai/sessions/2026-05-25-ai-assistant-plan.md`) — 6 ngày làm việc theo plan compress vào 1 session. Branch `feat/ai-assistant` 10 commit chưa push.

## What Was Done

### Day 1 — DB-backed settings + audit tables + lifespan seed (commit `e167302`)
- Alembic migration `add_ai_settings_and_audit_tables`: 3 bảng `ai_settings` (kv), `ai_conversations`, `ai_messages`.
- `app/ai/config.py` — SETTINGS_REGISTRY 15 keys, get/set với in-memory cache 30s, `bust_cache` khi set, `get_all_settings()` mask api_key, `seed_defaults()` idempotent (đọc env var `AI_<KEY>` làm initial override), `test_connection()` ping `{base_url}/models`.
- FastAPI lifespan hook gọi `seed_defaults()` ở startup.
- 17 unit tests.

### Day 2 — Admin UI `/admin/ai` (commit `e3b95b7` + `39868b4`)
- 5 routes: `GET /admin/ai`, POST `/connection`, `/models`, `/flags`, `/test-connection` (JSON).
- Template `admin_ai.html` 3 section ban đầu (kết nối + models + flags) + read-only debug table.
- API key UX: password input rỗng → giữ key cũ; mask `sk-o•••••fd4a` khi expose.
- Test connection button JS fetch endpoint → render model chip list inline.
- Sau đó (commit `39868b4`): Section 2 từ text input → `<select>` với `<optgroup>` group theo provider prefix. GET handler auto-fetch `/models` list (cache 5 phút), pass vào template. Fallback text input khi key chưa cấu hình. Custom value (không có trong catalog) render vào optgroup riêng để giữ config.

### Day 3 — `/api/chat` JSON endpoint + 2 tool (commit `cf0d489`)
- `app/ai/client.py` — `make_client()` build OpenAI SDK client từ DB settings. `cache_supports_anthropic()` detect OpenRouter/Anthropic compat.
- `app/ai/system_prompt.py` — HEAD 500 token (vai trò, boundary, citation rule) + `cached_catalog()` từ SPECS + COMBO_SPECS (~3-5k token, lru_cache) + page context dynamic. `build_messages_system()` có option enable_cache (Anthropic ephemeral cache_control).
- `app/ai/tools.py` — 2 tool đầu: `search_findings`, `get_finding`. Schema OpenAI function-calling. Run dispatcher truncate result > 4000 chars.
- `app/routes/ai.py` — `POST /api/chat` non-streaming. Resume/create conversation (verify ownership). `_load_history()` đọc 20 msg gần nhất, restore OpenAI format (assistant+tool_calls+tool result). Tool-call loop max 5 iterations.

### Day 4 — 4 tool còn lại + 23 tests (commit `3404278`)
- `query_raw_data(table, company_code, year, filter_field?, filter_value?, limit)` — M15/M15a/M16/BCCT Tầng 1, exclude id/company_id/source_file để tránh leak.
- `explain_check(check_code)` — SPECS hoặc COMBO_SPECS.
- `list_companies()` — DN + risk_score + findings_per_year aggregate.
- `get_legal_context(topic?)` — đọc §1.4 đề án từ `../audit-hq/de-an-audit-hq.md` qua regex section parser, `lru_cache(maxsize=1)`. Fallback static khi file đề án không có.

### Day 5 — Sidebar UI vanilla JS + SSE streaming (commit `9868759`)
- `POST /api/chat/stream` — SSE với 5 event type: `content`, `tool_call`, `tool_result`, `done`, `error`. OpenAI SDK stream=True + stream_options include_usage.
- `GET /api/ai/meta` — `{enabled, configured, model}` cho frontend init.
- `app/templates/_ai_sidebar.html` — partial inject vào base.html khi user logged in. FAB 💬 hidden default; JS toggle sau khi fetch meta.
- `app/static/sidebar.css` — fixed bottom-right panel 420px slide-in, message bubble user/assistant/tool/error styling, streaming cursor blink.
- `app/static/sidebar.js` vanilla JS — page context auto-detect (DN code/year/finding_id), suggested prompts contextual, SSE parser, markdown render qua marked.js CDN + DOMPurify sanitize, citation regex post-process (`[finding:N]` → link, `[table:filter]` → badge), conversation resume qua sessionStorage.

### Day 5+ — History feature + fix bugs (commit `3bbea5a` + `203dbae` + `4c46459`)
- 3 endpoint mới: `GET /api/chat/conversations` (30 gần nhất), `GET /api/chat/conversations/{id}/messages` (resume full transcript), `DELETE /api/chat/conversations/{id}` (cascade).
- Auto-title: `AiConversation.title = user_message[:80]` khi tạo conv mới.
- Sidebar header thêm 3 nút: `📜 history`, `+ new`, `⛶ expand` (toggle full-screen 100vw, sessionStorage), `×` close.
- History panel overlay chat area, list conv với meta (msg count + ngày). Hover hiện nút 🗑 xoá riêng.

**Bug fixes:**
1. **404 stale conv_id**: client lưu convId sessionStorage; nếu server xoá → request 404. Fix: init load `/messages` để validate, silent clear nếu 404. sendMessage gặp 404 → clear conv + retry 1 lần không có conv_id.
2. **SQLite FK cascade không hoạt động**: enable `PRAGMA foreign_keys=ON` qua `@event.listens_for(Engine, "connect")` trong `app/database.py`. Trước: DELETE conv để lại orphan messages.
3. **conftest UOM seed lỗi sau bật FK**: alias insert trước canonical → FK fail. Fix: `s.flush()` canonical trước add aliases.
4. **History panel `[hidden]` bị `.ai-history-panel { display: flex }` đè**: thêm CSS rule `.ai-history-panel[hidden] { display: none }` selector kết hợp có specificity cao hơn.

### Day 6 — Cost tracking + rate limit + budget + admin audit UI (commit `20aab66`)
- `app/ai/cost.py` — PRICING dict 20+ model phổ biến (Claude 4 series, GPT 4o/5.x, Gemini 3, DeepSeek). `estimate_cost()` ra `CostBreakdown` với `pricing_known` flag. Default $1/$5 per 1M cho model lạ.
- `app/ai/limits.py` — `check_rate_limit(user, db)` (msg/giờ, 0=tắt, vượt→429), `check_daily_budget(db)` (USD/ngày, 0=tắt, vượt→503), `usage_today(db)` KPI aggregate. Cả 3 nhận `db` param và truyền `get_setting(db=db)` để tests isolation.
- `_save_msg` auto-estimate cost cho assistant turn có model + tokens.
- Wire `check_rate_limit` + `check_daily_budget` vào cả `/api/chat` và `/api/chat/stream` ngay sau auth.
- Admin UI Section 3 mới: 5 form field giới hạn + retention. Section 4 (Flags) rename từ Section 3 cũ. Section 5 mới: 5 stat KPI hôm nay + progress bar budget (xanh<50%, vàng 50-80%, đỏ>80%) + bảng 20 conv gần nhất với cost/token.

### Backlog (commit `3431fe5`)
- `.ai/BACKLOG.md` — 3 item user yêu cầu defer: multi-user (`users` table + login), RBAC (`@require_role`), tool-use UI ẩn cho officer. Ước lượng ~3.5 ngày.

## Decisions Made

- **OpenAI-compatible SDK + OpenRouter default**: provider-agnostic, swap qua admin UI. Đổi từ Anthropic SDK trực tiếp theo yêu cầu user. Tradeoff: mất Anthropic extended thinking + citations API, đổi lại multi-provider.

- **Settings DB-backed thay vì env-only**: edit qua `/admin/ai` không cần redeploy. Env var chỉ làm seed lần đầu. Tradeoff: phải có admin UI + security cho API key (mask 4 đầu + 4 cuối).

- **Streaming SSE thay vì JSON-only**: UX tốt hơn (perceived 1-3s vs 5-10s). Day 3 ship JSON, Day 5 thêm SSE riêng (không refactor /chat). Cả 2 endpoint share `_load_history` và `_save_msg`.

- **Tool result max 4000 chars truncate**: tránh blow context window. Truncate marker `{truncated: true, preview, note}` để LLM biết là không phải full.

- **Conversation persist qua sessionStorage (cùng tab)**: không persist cross-tab/cross-browser. Đủ cho demo, không cần Redis/cookie.

- **Markdown CDN marked.js + DOMPurify**: nhanh, an toàn (sanitize trước render). Fallback plain text + `<br>` nếu CDN block.

- **Tool-use UI hiện cho mọi user (V1)**: chấp nhận; user đã ghi vào backlog để defer "ẩn cho officer" sang sprint sau khi có RBAC.

- **Pricing table hardcode + DEFAULT_PRICE fallback**: cost calc approximate cho prod monitor, không cần chính xác đến cent. Provider mới hoặc model lạ → flag `pricing_known=False`, admin biết.

- **Branch `feat/ai-assistant` không push**: tránh trigger CI deploy half-baked feature lên prod. Push khi feature complete + QA pass.

## What Didn't Work / Gotchas

- **OpenRouter dùng `~` prefix cho "latest" alias** (`~anthropic/claude-sonnet-latest`): registry default ban đầu là `anthropic/claude-sonnet-4` (sai). Phải update DB qua set_setting để model fire đúng. Template render fallback optgroup khi value không khớp catalog (giữ config).

- **SQLite FK constraint không enforce mặc định**: phát hiện khi xoá conv để lại orphan messages. Fix bằng `PRAGMA foreign_keys=ON` event hook. Cascade hoạt động sau đó. UMO conftest break vì alias insert trước canonical — fix `flush()` giữa 2 add_all.

- **Lint E501 cho Vietnamese text dài**: prompt strings không wrap được ở word boundary. Per-file ignore `app/ai/system_prompt.py` trong pyproject.

- **`asyncio.run(request.json())` trong sync function**: lần đầu code SSE endpoint, dùng sync function nhưng cần đọc async body. Đổi sang `async def` clean hơn.

- **B008 `File(default=None)` trong function defaults**: phải whitelist `fastapi.File` trong `extend-immutable-calls` pyproject (tương tự `Form/Depends/Query/Header` đã có).

- **CSS `[hidden]` attribute spec không thắng class với `display: flex`**: phải dùng selector kết hợp `.ai-history-panel[hidden]` để raise specificity.

- **Test isolation cho settings cache**: `check_rate_limit` ban đầu gọi `get_setting()` không truyền `db` → dùng SessionLocal thật, không phải test session. Fix: pass `db=db` parameter qua. Generic pattern: bất kỳ helper test cần dùng `get_setting` phải truyền db.

- **Token usage cao hơn dự kiến**: 11-17k token/turn (Day 4 sau khi có 6 tool schema). Cache control chưa verify thực tế hit rate qua OpenRouter — defer Day 7.

## Open Items

### Tiếp tục plan V1 (Day 7-8)
1. **Day 7 — Internal QA**: 20-30 câu hỏi điển hình cán bộ HQ sẽ hỏi. Đo cache hit rate qua OpenRouter (verify supports Anthropic cache_control). Đo cost/conversation, latency p50/p95. Fix prompt regression. Compile prompt regression test set.
2. **Day 8 — Deploy prod**: push branch lên main → CI tự deploy `audit-hq-demo.tinsu.ai`. Watch admin/ai audit page 24h. Soft-launch cho 2-3 internal user trước, sau đó mở public.

### Backlog (defer)
- **Multi-user + RBAC + tool-use ẩn**: chi tiết `.ai/BACKLOG.md`. ~3.5 ngày. Có thể insert sau Day 7-8 hoặc gộp nếu sắp demo cán bộ HQ thật.

### Tech debt nhỏ
- **Backup DB file `audit_hq.sqlite.bak-20260525-120743` untracked**: 18M, cũ. Xoá khi tiện.
- **Citation post-process regex `[finding:N]` hiện chỉ link tới `/findings/N`**: cho `[m15:row_no=88]` v.v. chỉ render badge — chưa có page truy thẳng row. Có thể link tới `/companies/{code}/data?year=Y&table=m15&q=row_no` nếu cần.
- **Retention cron chưa setup**: settings `history_retention_days` + `audit_retention_days` chỉ là cấu hình, chưa có cron xoá. Day 7 hoặc Day 8 thêm: daily job trong container hoặc app startup background task.
- **Forbidden phrase post-process**: plan mention "tôi sẽ confirm" / "tôi đã reject" guard. Chưa implement — defer khi gặp regression.
- **Admin conv detail page**: section 5 list 20 conv nhưng chưa có drill-in xem full transcript. Có thể thêm route `/admin/ai/conversations/{id}` cho admin debug.

### Verify trên browser (chưa test sạch lần cuối)
- Sidebar `+ Mới` button — bug `[hidden]` đã fix nhưng chưa verify visual sau commit.
- Nút `⛶` expand full-screen — chưa user test.
- Admin section 5 audit bảng render — đã test render text marker, chưa visual.
- Citation badge click → `/findings/N` redirect — chưa user click test.

## Số liệu cuối session

- Branch `feat/ai-assistant`: 10 commit (Day 1-6 + 4 fixes + 1 backlog).
- LOC: +4086 / -2 over main (25 files changed: 6 app/ai/* + 2 admin route/template + 2 model + 4 test + sidebar JS/CSS/HTML + migration).
- Tests: 168 pass (+57 từ Day 1, +23 từ Day 4, +15 từ Day 6). Ruff clean.
- Latency E2E: ~12-26s per turn (cold, 6 tool schema). Tool dispatch chính xác 3/3 questions.
- Cost tracking: $0.0375 per turn (Sonnet 10k+500 token). 50% budget cảnh báo vàng.
- OpenRouter API: 50 model phát hiện, latency `/models` 199ms.
