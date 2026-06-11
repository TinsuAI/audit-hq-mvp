# STATUS — Audit-HQ MVP

> **Trạng thái (2026-06-11 — empower AI Chat Assistant + loạt fix demo, đã deploy live):**
> Branch `main` = origin (sạch), **11 commit session này đã push + deploy live xanh**,
> build live **`11bbcdd`**. **510 tests pass**, ruff clean. Dev local :8200 chạy
> (uvicorn --reload, background). Đã verify nhiều luồng trên prod bằng Playwright.
>
> 🆕 Lớn nhất: **Chat Assistant được "empower"** — thêm 7 tool (query_sql SQL chỉ-đọc
> trên 6 view, export_excel, export_query_excel, propose_check_run, generate_report,
> explain_score) + cảnh báo hallucination luôn-hiện + guardrails. Kèm loạt fix theo
> demo: giải thích điểm đúng rate-based, đếm finding đúng tổng, thẻ breakdown điểm
> trên trang DN, recompute điểm khi đổi status finding, format số nhỏ, từ ngữ
> "bài kiểm tra", fix lỗi gộp args streaming (Gemini), fallback khi 402.

## ⚠️ Việc cần để ý

1. **[ĐÃ XỬ LÝ sau /handoff] Provider → DeepSeek cho đỡ tốn tiền.** User bỏ Claude.
   Live giờ: PRIMARY `deepseek/deepseek-v4-pro` (qua OpenRouter, ~$0.43/$0.87 — rẻ
   ~7–17× Claude Sonnet $3/$15), FALLBACK Gemini free. Verify local + prod, 0 lỗi
   (tool-use song song / SQL / explain_score đều OK, đúng từ ngữ). `deepseek-v4-pro`
   CÓ trong `cost.py` PRICING ($0.50/$1.50) nên dashboard tracking đúng. Chỉ đổi
   config `ai_settings`, không deploy.
2. **[Bớt gấp] `cost.py` thiếu giá Claude.** PRICING vẫn thiếu `anthropic/claude-sonnet-4`
   → rơi `DEFAULT_PRICE=$1/$5`, đếm thiếu ~3× (lý do dashboard từng báo $2.2 trong khi
   thật ~$6.7, đốt ~$5 key bạn + ~$2 key mới). Không còn dùng Claude nên hết nóng; nếu
   sau bật lại Claude thì thêm entry + cờ `pricing_known` cảnh báo khi rơi DEFAULT.

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build **`11bbcdd`**, CI xanh, healthy. 4 DN demo (DN_001..004).
- **AI provider:** PRIMARY OpenRouter → `deepseek/deepseek-v4-pro` (key `sk-or-v1-aca6…`,
  còn ~$7.8/$10; fast=`deepseek-v4-flash`). FALLBACK Gemini `gemini-2.5-flash` (key
  `AQ.Ab8…`, **Google FREE tier** → 429 khi bắn dồn nhiều tool). `fallback_enabled=True`.
  Fallback kích hoạt khi 402/404/408/424/429/5xx/timeout/conn. (Trước đó từng dùng
  Claude Sonnet 4 primary — đã bỏ vì tốn tiền.)
- **AI limits:** `max_tokens`=4096, `tool_call_cap`=10, `rate_limit_per_hour`=300,
  `daily_budget_usd`=100, `request_timeout_s`=120.
- Điểm DN (live, 17-rule): DN_003=168(2022)/148(các năm khác cao nhất), DN_001=120ish,
  DN_002=28, DN_004=46. (DN_003 2025 ~2 sau khi user loại trừ vài finding.)

### Stack
- Python 3.12, FastAPI, SQLAlchemy+Alembic, SQLite (WAL). Dev port **8200**.
- AI: OpenAI SDK compat. Tool-use loop streaming SSE. 12 tool (6 cũ + 6 mới).
- Migrations head: `e1a2c3d4f5b6` (KHÔNG thêm migration session này — view SQL tạo
  runtime idempotent, không qua Alembic).

## Recent Changes (2026-06-11 — session này, 11 commit `12d98ae`→`11bbcdd`)

1. **`12d98ae` feat(ai): empower chat assistant.** 5 tool đầu (query_sql, export_excel,
   export_query_excel, propose_check_run, generate_report) + `app/ai/sql_tool.py`
   (6 view `v_findings/v_m15/v_m15a/v_m16/v_bcct/v_company_scores` tạo runtime;
   guard: chỉ SELECT, allowlist view + denylist `users`/`ai_settings`/`sqlite_master`,
   `query_only=ON`, LIMIT cap, timeout) + banner hallucination + chip tải + nút
   xác nhận chạy-check + endpoint `/api/chat/run-checks` & `/api/chat/export-query`.
2. **`edad32a` docs:** §4 tổ hợp mềm hoá (minh hoạ/giả thuyết).
3. **`2cd471d`+`bc83e12` fix(ai): giải thích điểm đúng RATE-BASED.** System prompt
   từng dạy mô hình cộng-dồn sai; viết lại + thêm tool **`explain_score`** (trả
   breakdown thật) + `n_rules`. Fix citation khoảng `[finding:4003-4027]` (badge).
4. **`0eb13d8` fix(ai):** `search_findings`/`query_raw_data` `count` = TỔNG thật
   (func.count), thêm `returned` + note khi cắt (trước báo "20" khi thật 93).
5. **`6ce96a0` feat:** thẻ breakdown điểm trên trang DN (`company_detail.html` +
   CSS) — số thật của DN/năm (raw/max_raw, từng bài, "kịch khung", mẫu số).
6. **`2631618` docs:** đổi "phép" → **"bài kiểm tra"** + bỏ jargon "trần/bão hoà/
   độ phơi nhiễm" (5 nơi: trang DN, danh sách, doc, prompt, explain_score).
7. **`5c6c7fd` feat(scoring): recompute điểm NGAY khi đổi status finding.**
   `app/pipeline/recompute.py::recompute_company_year` (từ findings hiện có, không
   chạy lại check) gọi trong route `POST /findings/{id}/status`.
8. **`afd4006` fix(ui):** `_format_cell` không làm tròn số nhỏ (định mức ~0.0018) về
   "0.00" — dùng `:.6g` cho |v|<0.01.
9. **`cc39228` fix(ai): lỗi gộp args streaming.** Gemini phát tool-call song song
   với index=None → accumulator gộp args thành `{...}{...}` → 400/"Extra data".
   Sửa: khoá theo index→id; `_clean_tool_args` (lấy JSON đầu); `run_tool` parse
   raw_decode khoan dung.
10. **`11bbcdd` fix(ai):** thêm **402 vào `_RETRY_STATUSES`** → OpenRouter hết tiền
    tự rớt sang fallback.

## Next Steps (ưu tiên)

1. **Combo +20 điểm tổ hợp — review logic** (user "note lại, quyết sau"). Flat +20
   cho mọi combo (kể cả combo "chất lượng dữ liệu") + magnitude tuỳ tiện. Cân nhắc:
   badge-không-tính-điểm / có-cấp-có-trần / trọng số khác nhau. (Phân tích đầy đủ ở
   session log + lịch sử chat.)
2. **Disk tinsu** (xem Blockers) — dọn cho an toàn deploy lâu dài.

## Blockers

1. **Đĩa tinsu 97% (8.1G trống).** Đỡ hơn lúc 100% (nhờ rebuild thay image cũ +
   `docker image/builder prune` + xoá 6 backup DB cũ trong session). NHƯNG 47GB
   docker images đều **đang gắn container** (không prune-a được). Deploy tiếp vẫn
   rủi ro nếu lại đầy. Cần user quyết: dừng stack nặng (gitlab 5.8G/onlyoffice 5.7G/
   hermes 4.6G…) hoặc nới đĩa. `sudo` đòi mật khẩu (không passwordless).
2. **GitHub Actions runner chạy bằng SCREEN, không phải systemd service.** Service
   gốc cần `sudo ./svc.sh start` (có mật khẩu). Tôi khởi động tay bằng
   `screen -L -Logfile ~/runner-audit-hq.log -dmS rnr-audithq ~/actions-runner-audit-hq/run.sh`.
   **Lúc handoff `screen -ls` KHÔNG còn session** → runner có thể đã chết. Deploy cuối
   (11bbcdd) vẫn xanh nên lúc đó còn sống. **Trước khi push lần sau: kiểm tra
   `gh api repos/TinsuAI/audit-hq-mvp/actions/runners` online chưa; nếu offline,
   khởi động lại bằng lệnh screen trên** (nhớ đĩa phải còn chỗ, runner ENOSPC sẽ chết ngay).

## Notes for Next AI Session

### AI config — set/đọc trên live (không in key ra console)
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
docker exec -e PYTHONPATH=/app -w /app audit-hq-mvp python -c "
from app.ai.config import set_setting, get_setting, test_connection
# vd đảo Gemini lên primary:
# set_setting('base_url','https://generativelanguage.googleapis.com/v1beta/openai/','x')
# set_setting('api_key','<gemini key>','x'); set_setting('model_default','gemini-2.5-flash','x')
print(get_setting('base_url'), get_setting('model_default'), test_connection().ok)"
docker restart audit-hq-mvp   # hoặc chờ 30s cache TTL
```
- Keys (gitignored, nằm trong `ai_settings` DB cả local lẫn live):
  OpenRouter primary `sk-or-v1-aca6…`; Gemini fallback `AQ.Ab8…`.
- Config trong DB `ai_settings` **persist qua deploy rebuild** (không cần set lại).

### Verify AI trên live (curl streaming)
```bash
curl -s -c /tmp/c.txt -b /tmp/c.txt -X POST https://audit-hq-demo.tinsu.ai/login -d "user=admin&password=admin" -o /dev/null
curl -s -N -b /tmp/c.txt -X POST https://audit-hq-demo.tinsu.ai/api/chat/stream -H 'Content-Type: application/json' \
  -d '{"message":"vì sao DN_003 2022 có 168 điểm?","page_context":{"dn_code":"DN_003","year":2022}}'
# kiểm: grep '^event: error' (phải 0); grep '"model"' (xem provider nào trả lời)
```

### Deploy flow
- Push `main` → CI "Test & Deploy" trên **self-hosted runner tinsu** (đang chạy qua
  screen) → job test + job deploy (`docker compose build` + `up -d --no-deps app`).
- Watch: `gh run watch <id> --exit-status`. Lấy run đúng SHA:
  `gh run list --branch main --limit 5 --json databaseId,headSha -q '.[]|select(.headSha|startswith("<sha>"))|.databaseId'`.

### Score recompute thủ công (nếu cần đồng bộ)
- `docker exec -e PYTHONPATH=/app -w /app audit-hq-mvp python -m scripts.recompute_all_scores`
- Helper mới 1 năm: `app.pipeline.recompute.recompute_company_year(session, company_id, year)`.

### SQL tool views
- 6 view `v_*` tạo runtime idempotent (`app/ai/sql_tool.ensure_views`), KHÔNG migration.
  Khoá an toàn: chỉ SELECT, allowlist view, denylist bảng nhạy cảm, query_only, LIMIT, timeout.

### Môi trường / gotcha
- WSL ssh hỏng → `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`. Lệnh nhiều dòng qua
  ssh phải dùng `;` (newline bị nuốt). `pkill uvicorn` trả exit 144 (harness SIGTERM)
  nhưng vẫn kill được.
- Gemini key = **free tier** → 429 khi 1 lượt gọi ≥~6 tool. Đã hạ tool_call_cap=10.
- Dev local :8200 đang chạy `uvicorn --reload` (background) — config = primary
  OpenRouter/Claude + fallback Gemini (giống live).
- Screenshot session này ở `C:\temp\toss\screenshots\2026-06-11-*`.

### Văn phong điểm số (đã chốt — giữ nhất quán)
- "bài kiểm tra" (KHÔNG "phép"), "kịch khung" (KHÔNG "trần/bão hoà"), "quy mô dữ liệu"
  (KHÔNG "độ phơi nhiễm"). Điểm = rate-based, mỗi bài tối đa 10 theo tỷ-lệ-trên-mẫu-số,
  KHÔNG cộng dồn. Finding "Loại trừ" (rejected) không tính + điểm tính lại ngay.

### Disclaimer pháp lý (giữ nguyên)
> "Đây là chỉ số rủi ro dữ liệu BCQT… KHÔNG phải đánh giá tuân thủ theo TT 81/2019/TT-BTC.
> Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan."
