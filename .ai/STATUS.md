# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-26, cuối session item-detail + AI fallback):**
> Branch `main` đã deploy. Live trên `audit-hq-demo.tinsu.ai` (build `c9605cf`).
> 257/257 tests pass. Trang chi tiết mã NVL/TP đã chạy, AI fallback chain Gemini → NIM DeepSeek đã verify.

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build hiện tại: `c9605cf` — tracking actual model used khi fallback.
- 4 DN demo: GROWATT, KIM_LONG, HONG_AN (score 3836), DO_THANH, DN_003 (HOA SEN).
- Tất cả feature MVP 10 tuần + AI assistant V1 + multi-user RBAC + trang chi tiết mã đang chạy.

### AI Assistant — provider chain
- **Primary**: Google AI Studio Gemini 2.5
  - default: `gemini-2.5-flash`
  - fast: `gemini-2.5-flash-lite`
  - deep: `gemini-2.5-pro`
  - Free tier: 10/15/5 RPM, 250/1000/100 req/ngày
- **Fallback**: NVIDIA NIM (enabled), trigger trên 429/5xx/404/timeout/connection error
  - default + deep: `deepseek-ai/deepseek-v4-pro`
  - fast: `deepseek-ai/deepseek-v4-flash`
  - Free tier: 40 RPM, không giới hạn ngày
- Cost UI ẩn (`show_cost=False`) — set `True` ở route handler để hiện lại.
- `tool_call_cap` = 5 (giảm từ 10 để tiết kiệm quota).

### Trang chi tiết mã NVL/TP (mới session này)
- URL: `/companies/{code}/items/{item_code}?year=<n|all>&kind=nvl|tp`
- Components: hero band + sparkline, year tabs, waterfall cân đối kho, Apex scatter timeline BCCT, Sankey BOM (sort + cap + stack origin), findings filter theo subject_key, AI quick-prompt button.
- Tab "Tất cả năm": heatmap year × metric + bảng cross-year + cờ Lệch.
- Entry points patched: bảng M15/M15a/M16/BCCT cột mã → link; finding subject_key → link; AI citation `[item:CODE]` support.

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite.
- AI: OpenAI SDK 2.38 (compat layer), provider-agnostic qua DB settings.
- Charts: SVG server-render (sparkline/waterfall/sankey) + ApexCharts CDN (timeline + heatmap).
- 257 tests pass (32 warnings, no failures).

## Recent Changes (session 2026-05-25 → 26)

- **Item detail page + traceability**: 6 commits. `app/items/` (operations.py, aggregations.py, charts.py), route + template, cross-page link patches.
- **Sankey readability**: sort qty desc, cap 15 nodes + "+N khác", stack ribbon origins proportionally, min thickness 1.5px (commit `90a1993`).
- **Cache busting**: CSS/JS URLs có `?v={{ app_version }}` để Cloudflare không serve stale (commit `60eb3b3`). Phải propagate `app_version_string` globals sang mọi route's templates env vì mỗi route module có Jinja2Templates instance riêng (commit `32c7760`).
- **Findings groups collapsed default** trên company_detail.
- **Cost UI ẩn** trên `/admin/ai` qua flag `show_cost` (commit `fddd4dd`).
- **Provider switch**: OpenRouter → NIM → Gemini Google AI Studio. Tested NIM chạy được (Llama 3.3 70B feel "ngao ngao" so với Gemini, switch sang Gemini Flash).
- **AI fallback chain** (commits `6911e0c` + `c9605cf`): Gemini fail → tự retry NIM DeepSeek. Settings `fallback_*` trong registry + admin UI Section 2b. `call_with_fallback` returns `(response, model_used)` để tracking đúng provider thực sự trả lời. Verified live: forcing primary 404 → DeepSeek trả lời, log "Primary LLM failed (NotFoundError); falling back to deepseek-ai/deepseek-v4-pro".

## Next Steps

1. **Demo HQ**: chuẩn bị kịch bản 5-10 câu hỏi tiếng Việt khó (audit logic, lệch BCCT, BOM bất thường) để chạy qua AI sidebar. Watch behavior + quota.
2. **Xin NIM rate limit nâng lên 200 RPM** trên `build.nvidia.com` (mặc định 40 RPM, sau khi HQ demo nếu cần scale).
3. **Verify tool calling trên Gemini**: chưa stress-test loại câu hỏi nào trigger nhiều tool call (3+). Có thể cần tăng `tool_call_cap` lại nếu Gemini Flash quá thận trọng.
4. **Code matching BCCT ↔ BCQT exact-match + banner orphan**: hiện tại OK cho demo, nhưng cần build trang `/admin/data-quality` để liệt kê mã orphan giúp DN/Hải Quan thấy phạm vi mismatch thực tế. Sau đó mới quyết alias mapping.
5. **Xoá file `audit_hq.sqlite.bak-20260525-120743`** (18MB untracked, không phải concern blocking nhưng dọn dẹp).
6. **Khi nào HQ feedback cho buổi demo** — bump đề án v11 (ở repo `audit-hq`, không phải đây).

## Notes for Next AI Session

### Repo này vs repo đề án
- Repo MVP code: `~/workspace/client/audit-hq-mvp` (đây). Branch `main`, push triggers CI deploy.
- Repo đề án: `~/workspace/client/audit-hq` (proposal docs, `de-an-audit-hq.md` + HTML). Handoff session log thường ở repo đề án.
- Khi HQ yêu cầu thêm check mới → update đề án TRƯỚC, MVP follow sau.

### CI gotcha
- `make lint` chạy `ruff check app tests scripts` (không check migrations). Pre-commit thường: `make lint && make test` rồi mới push. Lỗi lint thường: E501 (>110 char), I001 (import order), E401 (multi-import).
- Hard refresh CSS bằng `?v={{ app_version_string | urlencode }}` đã wire ở base.html. Mỗi deploy URL thay đổi → Cloudflare miss → fetch fresh.

### Provider config gotchas
- Gemini OpenAI-compat endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/` (có trailing slash).
- NIM endpoint: `https://integrate.api.nvidia.com/v1`.
- Mỗi route module (`companies.py`, `admin.py`, `admin_ai.py`, `admin_users.py`) có Jinja2Templates instance RIÊNG → nếu thêm template global mới phải add vào TẤT CẢ. Lý tưởng: refactor thành shared instance, nhưng chưa cần.

### Cost UI
- Admin/ai Section 5 hiển thị tokens + users + count nhưng KHÔNG hiện $$$. Bật lại bằng `show_cost=True` trong `admin_ai_page` + `admin_ai_conversation` handlers.

### Test scripts
- `/tmp/shoot.py` — Playwright screenshot script. Lưu output ra `/mnt/c/temp/toss/`. Có thể tái sử dụng để chụp ảnh demo cho stakeholder.
- Login cookie jar: `/tmp/lc.txt`.

### Dev server
- Port 8200. Log `/tmp/audit-hq-dev.log`.
- Start: `cd /home/vp/workspace/client/audit-hq-mvp && nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`

## Blockers

Không có blocker hard. Đang chờ:
- HQ confirm thời gian demo.
- Feedback nội bộ Trọng Tín về biểu đồ thác + Sankey (đã gửi screenshot + tin nhắn ở `C:\temp\toss\`).
