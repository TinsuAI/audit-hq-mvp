# STATUS — Audit-HQ MVP

> **Trạng thái (2026-06-14 — redesign UX tài liệu + thay DSL gen-check bằng SQL/Python từ NL):**
> `main` = origin (sạch, đã push), **deploy live xanh** `build_sha=ca387cb`. 4 commit phiên này
> (`3319bca`→`ca387cb`). **492 test pass**, ruff sạch. Migration head **`a3c4d5e6f7b8`**.
> Dev local :8200 đang chạy (`uvicorn --reload`, nền — hay bị thu hồi giữa phiên, bật lại khi cần).
>
> Hai việc lớn: (1) **Tạo DN + quản lý tài liệu** — mã DN tự sinh, trang tài liệu accordion theo
> năm, bảng `DataFile` registry. (2) **Soạn check từ ngôn ngữ tự nhiên** — bỏ hẳn DSL, thay bằng
> **SQL/Python tự do + agentic loop** (port BCQT-System): tool-use, dry-run, oracle retry,
> self-review, dynamic few-shot. Kèm fix `test_connection` (báo OK giả vì /models public).

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build **`ca387cb`**, CI "Test & Deploy to Tinsu" success, healthz ok. 4 DN demo DN_001..004
  (prod có file thật → trang tài liệu hiện đầy đủ). Live smoke: `/companies/DN_001/documents`,
  `/admin/checks/new` đều 200.
- **AI provider:** OpenRouter → `deepseek/deepseek-v4-pro` (primary, key `sk-or-v1-8…b629`),
  fallback Gemini. Key này **chung cho cả prod lẫn local** (đã đảo về local phiên này).

### Stack / DB
- Python 3.12, FastAPI, SQLAlchemy+Alembic, SQLite (WAL). Dev port **8200**.
- Migration head **`a3c4d5e6f7b8`** (2 migration mới phiên này: `f2b3c4d5e6a7` data_files,
  `a3c4d5e6f7b8` check_definitions cột SQL/Python).

## Recent Changes (2026-06-14, 4 commit)
1. **`3319bca` feat(checks):** thay DSL bằng SQL/Python soạn từ NL. `app/checks/sql_runner.py`
   (RO + SAVEPOINT + auto evidence_refs), `spec_gen.py` viết lại agentic (tool-loop + dry-run +
   oracle retry + self_review + dynamic few-shot). `CheckDefinition` + cột mới. Scoring nhận
   `rule_scope` mở rộng (`extended_rule_scope`). Gỡ `dynamic_runner.py`. Test mới.
2. **`6a28cb2` feat(companies):** mã DN tự sinh `DN_NNN` (bỏ khỏi form), bảng `DataFile` +
   `data_files.py`, trang tài liệu **accordion theo năm** (nhãn trạng thái thống nhất, file dạng
   dòng), dropdown chọn/thêm năm.
3. **`f8ef83d` style(ui):** CSS tài liệu + authoring/preview; fix overlay spinner luôn-hiện
   (`.draft-overlay[hidden]{display:none}`).
4. **`ca387cb` fix(ai):** `test_connection(verify_auth=True)` gọi 1 completion 1-token để xác
   thực key thật (`/models` public nên báo OK giả); `available_models` dùng `verify_auth=False`.

## Next Steps (ưu tiên)
1. **Hỏi user xoá/giữ dữ liệu test local:** DN throwaway `ZZ_DEMO` + check nháp `X.1` (chỉ local).
2. **Combo +20 điểm tổ hợp — review logic** (carry, user "quyết sau"): flat +20 mọi combo +
   magnitude tuỳ tiện. Cân nhắc badge-không-điểm / có-trần / trọng số.
3. (Tuỳ) xoá nhánh `feat/document-ux-and-nl-check-authoring` (đã merge main).

## Blockers
- Không có blocker chặn. Lưu ý đĩa tinsu ~97% (theo dõi khi deploy lâu dài).

## Notes for Next AI Session

### AI config (set/đọc trên live — không in key)
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
docker exec -e PYTHONPATH=/app -w /app audit-hq-mvp python -c "
from app.ai.config import get_setting, test_connection
print(get_setting('base_url'), get_setting('model_default'), test_connection().ok)"
docker restart audit-hq-mvp   # hoặc chờ 30s cache TTL
```
- Key OpenRouter `sk-or-v1-8…b629` (primary, live + local). Local cũ `sk-or-v1-aca…11fa` đã chết.
- **`test_connection()` giờ làm completion thật** (verify_auth mặc định True) → báo đúng key
  sống/chết. `GET /models` của OpenRouter PUBLIC nên key chết vẫn liệt kê model được.

### Soạn check từ NL (mới)
- `/admin/checks/new` → prompt + picker DN/năm tham chiếu → POST `/admin/checks/draft` (agentic
  loop, ~10-40s) → preview → Lưu nháp → Publish. Check chạy qua `app.checks.sql_runner.run_check`.
- Check SQL: SELECT trả cột `severity, subject_key, title, detail` (+ optional evidence_json),
  PHẢI lọc `:company_id` + `:period_year`. Khai `scope` (nvl/tp/m16) + `subject_table`/`subject_col`
  để tự dựng evidence + tính điểm. Python: `def run(conn, company_id, period_year)`.

### Quản lý tài liệu
- `/companies/{code}/documents` accordion. `sync_data_files` chạy mỗi lần xem (reconcile fs).
- **DB local = mirror prod (DN_001..004) nhưng `data/` symlink trỏ tên thật (GROWATT…)** → DN
  demo KHÔNG có file trên đĩa local (đúng, không phải bug). Test upload bằng DN throwaway, dọn sau
  (`rm -rf data/<CODE>` + xoá rows DB). Demo data curated ở `demo-data/…(Demo)/<năm>/`.

### Môi trường / gotcha
- Dev server nền hay bị thu hồi giữa lượt → bật lại:
  `nohup .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`
- WSL ssh: `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`. Lệnh python nhiều dòng qua ssh →
  dùng base64 (`exec(base64.b64decode('...').decode())`), newline bị nuốt.
- Runner GitHub Actions tinsu chạy qua screen; phiên này **online** + deploy OK.
- Ảnh demo UI phiên này: `C:\temp\audit-hq-shots\2026-06-13\` (documents/authoring/preview/admin-ai…).

### Deploy flow
- Push `main` → CI "Test & Deploy to Tinsu" (self-hosted runner) → test + `docker compose build`
  + `up -d`. Watch: `gh run watch <id> --exit-status`.

### Văn phong điểm / disclaimer (giữ nguyên)
- "bài kiểm tra" (KHÔNG "phép"), "kịch khung", "quy mô dữ liệu". Điểm rate-based, mỗi bài tối đa
  10 theo tỷ lệ trên mẫu số, không cộng dồn. Finding "Loại trừ" không tính + recompute ngay.
- Disclaimer: "chỉ số rủi ro dữ liệu BCQT… KHÔNG phải đánh giá tuân thủ theo TT 81/2019/TT-BTC".
