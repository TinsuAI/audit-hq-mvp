# 2026-05-25 — Plan: AI Assistant cho Audit-HQ MVP

> Spec V1 cho AI assistant tương tác với cán bộ HQ trên web UI. Provider mặc định: **OpenRouter** (OpenAI-compatible). Toàn bộ thông số configurable qua admin UI (DB-backed), không cần redeploy.

## 1. Mục tiêu nghiệp vụ

Cán bộ HQ vừa xem trang findings / dữ liệu vừa hỏi AI:
- "Tại sao C3.2 fire trên mã X-DL? Có gì đáng lo?"
- "Tóm tắt DN_003 năm 2024 trong 3 câu."
- "Pháp lý nào liên quan tới C2.3?"
- "So sánh DN_001 và DN_003 năm 2024."
- "Mã HS 4107 xuất hiện ở đâu, có bất thường gì không?"

AI tra cứu DB read-only, **cite nguồn cụ thể** (`[finding:123]`, `[nvl_balances:row_id=45]`), không bao giờ tự confirm/reject. Quyết định cuối thuộc cán bộ HQ — same policy footer hiện tại đã ghi.

### Non-goals (V1)
- KHÔNG cho AI ghi DB (đổi finding status, xoá data, tạo DN).
- KHÔNG tự động chạy `run_checks` hoặc trigger workflow.
- KHÔNG phân tích file upload mới (chỉ truy vấn dữ liệu đã ingest).
- KHÔNG cross-tenant — V1 chỉ 1 instance demo, không multi-customer isolation.

## 2. UX

### Sidebar chat
- Collapsible bên phải, default collapsed (FAB icon 💬 góc dưới phải sau khi login).
- Mở ra: panel ~400px wide với input box + lịch sử conversation.
- **Page-context auto-inject**: URL hiện tại + DN code/year/finding id đang xem → system message ẩn mỗi turn, không nhìn thấy trong UI.
- Conversation persist trong session cookie (`conv_id`) cho cùng 1 user, reset khi logout. Cross-page: giữ nguyên conversation.
- Suggested prompts khi conversation trống:
  - "Giải thích finding này" (chỉ hiện khi đang xem `/findings/{id}`)
  - "Tóm tắt DN" (chỉ hiện khi đang xem `/companies/{code}`)
  - "Pháp lý nào liên quan tới [check_code]?"
  - "Hệ thống tính điểm rủi ro như thế nào?"

### Response rendering
- Markdown render (tiêu đề, bullet, code block, table nhỏ).
- Citation badges: `[finding:123]` → render thành button "📎 finding 123" click → `/findings/123`. `[nvl_balances:row_id=45]` → render thành link tới data viewer trang đó.
- **Streaming SSE** (better perceived latency 1-3s thay vì block 5-10s). OpenAI SDK hỗ trợ native.
- "Đang suy nghĩ..." skeleton khi chờ token đầu, "Đang tra cứu..." khi đang gọi tool.

### Master switch
- Admin có thể tắt AI toàn cục → sidebar ẩn hoàn toàn (kể cả FAB).

## 3. Stack & SDK

- **SDK**: `openai>=1.40` (Python). Khởi tạo client với `base_url` custom + `api_key` từ DB settings.
- **Provider mặc định**: OpenRouter (`https://openrouter.ai/api/v1`). Lý do:
  - 1 API key dùng được 100+ model (Anthropic Claude, OpenAI GPT, Google Gemini, DeepSeek, open-weight via Together).
  - Dashboard usage + spending limit built-in.
  - Hỗ trợ Anthropic-style `cache_control` cho model Claude (giữ được prompt caching khi cần).
  - Cho phép swap model qua admin UI mà không đổi code.
- **Streaming**: SSE chuẩn OpenAI.
- **Tool calling**: OpenAI function-calling format.

### Khi switch provider khác
User chỉ cần đổi `base_url` + `api_key` + tên model trong `/admin/ai` → reload cache (auto) → next message dùng provider mới.

## 4. Configurable settings (DB-backed)

Bảng `ai_settings` key-value:

```python
class AiSetting(Base):
    __tablename__ = "ai_settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text)       # str-serialized (JSON cho dict)
    updated_at: Mapped[datetime]
    updated_by: Mapped[str]
```

### Danh sách settings

| Key | Default | Mô tả |
|---|---|---|
| `enabled` | `false` | Master switch. Off → sidebar ẩn |
| `base_url` | `https://openrouter.ai/api/v1` | OpenAI-compat endpoint |
| `api_key` | `""` | Mask sau lưu, chỉ show 4 ký tự cuối |
| `extra_headers` | `{"HTTP-Referer":"https://audit-hq-demo.tinsu.ai","X-Title":"Audit-HQ"}` | OpenRouter ranking header |
| `model_default` | `anthropic/claude-sonnet-4` | Chat free-form |
| `model_fast` | `anthropic/claude-haiku-4-5` | Explain/summarize ngắn |
| `model_deep` | `anthropic/claude-opus-4-7` | Gated reasoning sâu (opt-in per request) |
| `temperature` | `0.2` | Analytic |
| `max_tokens` | `1024` | Per response |
| `request_timeout_s` | `60` | API call timeout |
| `daily_budget_usd` | `20.0` | Hard cap, 503 khi vượt |
| `rate_limit_per_hour` | `50` | Msg/user/giờ |
| `history_retention_days` | `30` | User conversation cũ → xoá cron |
| `audit_retention_days` | `365` | Audit log keep |
| `prompt_cache_enabled` | `true` | Auto-detect provider khi support |

### Helper API (`app/ai/config.py`)
```python
def get_setting(key: str, default: Any = None) -> Any
def set_setting(key: str, value: Any, user: str) -> None
def get_all_settings() -> dict[str, Any]   # cho admin UI, mask api_key
def test_connection() -> dict             # ping {base_url}/models
```

In-memory cache: `functools.lru_cache` + `time.time() // 30` segment (TTL ~30s). Bất kỳ `set_setting` nào bust toàn cache.

### Seeding
Migration tạo bảng + insert default values nếu chưa có row. Env vars (`AI_BASE_URL`, `AI_API_KEY`, ...) chỉ làm seed lần đầu khi DB trống — sau đó DB là source of truth.

## 5. Admin UI — `/admin/ai`

5 section trong 1 trang (mỗi section form riêng với nút Lưu độc lập):

### Section 1 — Kết nối
- Base URL (text)
- API Key (password input; mask sau save → `sk-or-v1-•••••abc`; nút "Thay khoá" để edit)
- Extra headers (textarea JSON)
- **🔌 Test connection** button: gọi `GET {base_url}/models` với key hiện tại → return ✅ + list 10 model đầu phát hiện được, hoặc ❌ + error message. Bắt buộc test pass trước khi enable master switch.

### Section 2 — Models
- Model default (text + datalist từ test connection)
- Model fast
- Model deep
- Temperature (number 0-2)
- Max tokens (number 256-4096)

### Section 3 — Giới hạn & Retention
- Daily budget USD
- Rate limit msg/user/giờ
- Request timeout giây
- History retention ngày
- Audit retention ngày

### Section 4 — Flags
- Master enabled (checkbox lớn)
- Prompt caching enabled

### Section 5 — Audit & Cost (read-only)
- KPI cards: cost hôm nay, total tokens hôm nay, msg count hôm nay, active users.
- Bảng top 20 conversation gần nhất: user, started_at, msg count, tokens, est cost, link chi tiết.
- Filter: theo user, theo ngày, theo cost > threshold.
- Trang chi tiết conversation: full transcript với tool calls expanded — dùng để debug AI sai khi user complain.

### Security cho API key
- GET response chỉ trả `api_key_present: bool` + suffix 4 ký tự cuối — không bao giờ leak full key.
- POST update: field trống = giữ key cũ; field có giá trị = replace.
- DB-level: SQLite `/db-data/audit_hq.sqlite` chmod 600. KHÔNG encrypt giai đoạn này (over-engineering cho 1 instance demo). Nếu sau này multi-tenant → thêm Fernet encrypt với key ở env `AI_SETTINGS_ENCRYPTION_KEY`.

## 6. Tools (6 read-only)

Tất cả định nghĩa ở `app/ai/tools.py`, schema OpenAI function-calling:

| Tool | Signature | Cost class |
|---|---|---|
| `search_findings` | `(company_code, year?, severity?, check_code?, status?, limit=20)` | low |
| `get_finding` | `(finding_id)` → finding + spec + resolved evidence | low |
| `query_raw_data` | `(table: m15\|m15a\|m16\|bcct, company_code, year, filter_field?, filter_value?, limit=50)` | low |
| `explain_check` | `(check_code)` → SPECS[code] / COMBO_SPECS[code] | cached |
| `list_companies` | `()` → all DN + risk_score | cached |
| `get_legal_context` | `(topic?)` → trích từ §1.4 đề án (load 1 lần từ md, cache forever) | cached |

Dispatcher (`app/ai/tool_runner.py`):
```python
TOOL_REGISTRY = {"search_findings": _search_findings, ...}

def run_tool(name: str, args: dict, db: Session) -> str:
    fn = TOOL_REGISTRY.get(name)
    if fn is None: return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(db, **args), ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
```

Tool result max 4000 chars (truncate + cảnh báo) để không blow context window.

## 7. Prompt strategy

### System prompt cấu trúc (cache aggressive)
```
[Segment 1 — instructions, ~500 tokens] (KHÔNG cache, có thể update nhanh)
- Vai trò: AI assistant tra cứu cho cán bộ Hải quan
- Boundary: quyết định cuối thuộc cán bộ HQ
- Citation: mọi claim concrete phải có [finding:id] hoặc [table:row_id]
- "Không biết" được phép, không bịa pháp lý
- Tiếng Việt full accents, tone formal

[Segment 2 — catalog 49 kiểm tra, ~8000 tokens] (CACHE)
- Mỗi check: code, title, severity, description, pháp lý liên quan
- 4 combo signature
- Hệ thống chấm điểm §2.6

[Segment 3 — tool schema + ví dụ usage, ~3000 tokens] (CACHE)
- 6 tools với param description chi tiết
- 3-5 ví dụ "user hỏi X → tool call Y"

[Segment 4 — page context, ~100 tokens] (KHÔNG cache, đổi mỗi turn)
- URL hiện tại
- DN code/year/finding id nếu đang xem
```

Segment 2+3 = ~11k token → cache với `cache_control: {"type": "ephemeral"}` (Anthropic-via-OpenRouter format). Target cache hit ≥85%.

### Auto-detect cache support
```python
def supports_cache(base_url: str) -> bool:
    return any(p in base_url for p in ["openrouter.ai", "anthropic.com"])
```
Provider không hỗ trợ → silent skip cache_control field (OpenAI SDK pass-through).

### Conversation history
- Giữ tối đa 20 turn cuối (~10 round-trip) trong API call.
- Cũ hơn → summarize qua model fast trước, replace bằng 1 summary message.
- Tool results: keep nếu được reference trong reply gần nhất, drop nếu cũ.

## 8. Guardrails

### In system prompt
1. **Cite source bắt buộc** — refuse trả lời concrete fact nào không có citation
2. **"Tôi không biết" được phép** — encourage decline khi data thiếu
3. **Boundary statement** — repeat "Tôi cung cấp thông tin, quyết định confirm/reject thuộc cán bộ Hải quan"
4. **Ngôn ngữ** — tiếng Việt full accents, tone formal "cán bộ", "phía Hải quan"
5. **PII** — không suy đoán DN thật từ DN_xxx, không infer tax_id

### In code (post-process)
1. **Citation regex check**: nếu response chứa "Theo M15..." mà không có `[nvl_balances:...]` → flag trong audit log.
2. **Forbidden patterns**: regex block "tôi sẽ confirm", "tôi đã reject" — AI không được claim action.
3. **Token sanity**: response > max_tokens → truncate, không retry tự động.

### Out-of-band
- Master switch + per-user disable nếu admin thấy user abuse.
- Spike detection: 1 user > 10 msg/phút → tự throttle.

## 9. Audit log + cost tracking

### Schema
```python
class AiConversation(Base):
    id: int (pk)
    user: str (indexed)
    started_at: datetime (indexed)
    page_url_seed: str       # URL đầu tiên khi tạo conv
    title: str | None        # AI tự đặt sau 3 msg, hiển thị trong admin list

class AiMessage(Base):
    id: int (pk)
    conversation_id: int (fk, cascade)
    role: str                # "user" | "assistant" | "tool"
    content: str             # full text
    tool_call_id: str | None
    tool_name: str | None
    tool_args_json: str | None
    model: str | None        # model dùng cho turn này
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None   # estimate từ pricing table
    latency_ms: int | None
    created_at: datetime (indexed)
```

### Cost estimate
- Pricing table hardcode cho top 10 model phổ biến (claude-sonnet-4, claude-haiku-4-5, gpt-4o, gpt-4o-mini, claude-opus-4-7, ...).
- Mỗi message: `cost = tokens_in * price_in + tokens_out * price_out`.
- Sum trong ngày → compare với `daily_budget_usd` → reject 503 nếu vượt.
- Model lạ không có pricing → estimate $0.01/1k token làm safe fallback + log warning.

### Retention cron
- Daily job (cron in container hoặc app startup background task) xoá:
  - `ai_messages` + `ai_conversations` cũ hơn `history_retention_days` (default 30)
- KHÔNG xoá `ai_messages` audit (giữ riêng nếu retention khác cho audit → consider tách 2 bảng nếu cần)

## 10. DB schema migration

1 migration mới: `add_ai_settings_and_audit_tables`
- `ai_settings` (key-value)
- `ai_conversations`
- `ai_messages`

Seed default settings nếu trống (1-time, idempotent).

## 11. Tradeoffs đáng note

| Quyết định | Trade-off |
|---|---|
| OpenAI-compat SDK | (+) Provider-agnostic / (−) Mất Anthropic extended thinking, citations API |
| OpenRouter mặc định | (+) 1 key đa model + dashboard / (−) Thêm 1 hop, latency +50-100ms, OpenRouter có thể downtime |
| Settings trong DB | (+) Edit không cần redeploy / (−) Phải có admin UI + security cho API key |
| Streaming SSE | (+) UX ~3-5s perceived / (−) Frontend phức tạp hơn, cần error handling stream broken |
| 6 tools read-only | (+) An toàn / (−) AI không thể "show me the data" → phải user chủ động đi tới trang |
| Cache 11k token | (+) Cost giảm ~70% / (−) Chỉ work khi provider hỗ trợ; cần test với OpenRouter+Claude |
| Sidebar persistent | (+) UX liền mạch / (−) State management JS phức tạp hơn modal-per-page |

## 12. Phasing (7-8 ngày làm việc)

### Tuần 1 — Skeleton & Settings

**Day 1**: Settings model + migration + helper.
- Alembic migration `add_ai_settings_and_audit_tables`.
- `app/ai/config.py` với `get_setting/set_setting/test_connection`.
- Seed defaults từ env vars nếu DB trống.
- Unit test: get/set, cache invalidation, mask api_key.

**Day 2**: Admin UI `/admin/ai` — section 1 + 2 + 4 (kết nối + models + flags).
- Form HTML + handler POST mỗi section.
- Nút Test connection: gọi `GET {base_url}/models`, return JSON kết quả vào HTML.
- Mask API key, "Thay khoá" flow.
- Manual test: nhập OpenRouter key thật, test connection pass.

**Day 3**: Endpoint `/api/chat` + 2 tools cơ bản (`search_findings`, `get_finding`).
- `openai` SDK init với DB settings.
- System prompt từ template + page context inject.
- Tool dispatcher.
- Audit log write (chưa cost calc).
- Streaming SSE response.
- E2E test bằng curl/httpx: ask "DN_003 năm 2024 có findings nào?" → AI gọi search_findings → trả lời cite.

### Tuần 2 — Full tools + UI + guardrails

**Day 4**: 4 tools còn lại (`query_raw_data`, `explain_check`, `list_companies`, `get_legal_context`) + load §1.4 đề án từ `../audit-hq/de-an-audit-hq.md` (parse markdown).

**Day 5**: Sidebar UI JS (vanilla, không React).
- FAB toggle.
- Conversation history fetch + render markdown (dùng marked.js hoặc tự parse minimal).
- Streaming token append.
- Citation parser → render thành link.
- Page context auto-inject vào body request.

**Day 6**: Guardrails + rate limit + budget.
- Cost calc với pricing table.
- Rate limit middleware (count msg/giờ qua DB).
- Budget cap middleware.
- Post-process citation regex + forbidden phrase check.
- Admin section 3 (limits) + section 5 (audit log preview).

### Tuần 3 — QA + ship

**Day 7**: Internal QA — Trọng Tín + Tinsu chạy 20-30 câu hỏi điển hình cán bộ HQ sẽ hỏi.
- Compile prompt regression set.
- Fix system prompt nếu AI sai pattern.
- Đo cache hit rate, cost/conversation, latency p50/p95.

**Day 8**: Deploy production + monitor 24h trước demo HQ.
- Update Cloudflare Tunnel/env nếu cần.
- Watch admin/ai audit page liên tục.
- Soft-launch: bật cho 2-3 internal user trước, sau đó mở public.

## 13. Phạm vi file thay đổi

### Mới
- `app/ai/__init__.py`
- `app/ai/config.py` — settings helpers
- `app/ai/client.py` — OpenAI SDK wrapper
- `app/ai/system_prompt.py` — segments builder
- `app/ai/tools.py` — 6 tool definitions
- `app/ai/tool_runner.py` — dispatcher
- `app/ai/cost.py` — pricing table + estimator
- `app/ai/guardrails.py` — post-process checks
- `app/routes/ai.py` — `/api/chat` endpoint
- `app/routes/admin_ai.py` — `/admin/ai` page
- `app/models/ai_settings.py`, `app/models/ai_conversation.py`
- `app/templates/admin_ai.html`
- `app/static/sidebar.js`, `app/static/sidebar.css`
- `migrations/versions/xxxx_add_ai.py`
- `tests/test_ai/*.py` (10-15 tests)

### Sửa
- `app/templates/base.html` — inject sidebar partial sau header
- `app/main.py` — include 2 router mới
- `pyproject.toml` — add `openai>=1.40`
- `.env.example` — document env defaults

## 14. Open risks / quyết định pending

1. **Demo timing**: Phase 1 ship TRƯỚC hay SAU demo HQ?
   - Trước → wow factor cao nhưng risk AI sai trước mặt sếp HQ.
   - Sau → an toàn nhưng demo HQ chỉ thấy 16 check tĩnh, AI sẽ là "feature mới" round 2.
   - **Default đề xuất**: SAU demo HQ — round 1 chốt MVP, round 2 add AI sau khi HQ duyệt nguyên tắc.

2. **Anthropic Claude qua OpenRouter và caching**: cần benchmark thật. OpenRouter docs nói hỗ trợ `cache_control`, nhưng có một số model không pass through. Day 7 phải đo cache hit rate cụ thể.

3. **Tool call loop limit**: model có thể gọi tool nhiều lần liên tiếp → cần cap (max 5 tool call/turn) để tránh runaway cost.

4. **Conversation context window**: với Sonnet 4 (~200k), 20 turn × ~2k token = 40k → còn rộng. Với model nhỏ (Haiku 4.5 ~200k cũng OK). Nếu user pick model 8k context → phải truncate aggressive hơn → cảnh báo trong /admin/ai.

5. **Logout = drop conversation?** Hay keep và resume khi login lại? Default đề xuất: keep 30 ngày qua user field, user thấy lại trong sidebar mục "Cuộc trò chuyện cũ".

6. **Tiếng Anh fallback?**: nếu HQ gửi query tiếng Anh → AI trả lời tiếng Anh hay luôn tiếng Việt? Default đề xuất: detect language input, reply same language.

## Defaults chốt (nếu không có override sau)

| Câu hỏi | Default |
|---|---|
| Provider V1 | OpenRouter |
| Streaming | Yes (SSE) |
| Demo timing | Sau demo HQ |
| Conversation retention | 30 ngày |
| Audit retention | 365 ngày |
| Resume conversation sau logout | Có, qua user field |
| Tool call cap/turn | 5 |
| Reply language | Detect input |

---

**Next action**: nếu ông OK plan này → tạo branch `feat/ai-assistant` + bắt đầu Day 1 (settings model + admin UI section kết nối). Nếu cần grill thêm điểm nào → /grill-me hoặc nói ra mục cụ thể.
