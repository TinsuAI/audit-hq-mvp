# Feature: Async job runner + Catalog kiểm tra động (dev-code + AI-assisted)

> Discover ngày 2026-05-26. Hai feature gộp 1 brief vì job runner là tiền đề để chạy check động (chậm hơn, không dự đoán trước thời gian).

## Scope

**Trong scope:**

1. **Async job runner** thay cho gọi sync trong HTTP handler:
   - Submit job từ UI ("Chạy kiểm tra" → POST tạo Job row, redirect ngay).
   - Trang `/jobs` (và `/jobs/{id}`) để theo dõi: queued / running / done / failed, log gọn, link tới kết quả.
   - Thông báo khi xong: in-app (badge số job done từ session user) ở V1; email/webhook để đó V2.
   - Áp dụng cho: chạy lại checks cho 1 (DN, năm); chạy batch nhiều DN; ingest + check chained; (sau này) preview check động trên sample.

2. **Catalog check động** — mở rộng catalog ngoài 16 MVP đã hardcode:
   - **Luồng A (dev-code)**: giữ shape hiện tại — file `app/checks/cN_*.py`, register vào `SPECS`. Không đổi gì, chỉ document để dev mới biết cách thêm. Đây là path mặc định cho check "chính thức" trong catalog 49 của đề án.
   - **Luồng B (AI-assisted, lưu DB)**: admin mô tả ý tưởng → AI sinh spec (định nghĩa logic + ngưỡng cảnh báo) → preview chạy thử trên sample → admin duyệt → publish. Spec lưu trong bảng `check_definitions`, KHÔNG sinh code Python.
   - Hai luồng chia sẻ chung: model `Finding`, trang kết quả, scoring, evidence_refs.

3. **Hiển thị kết quả đồng nhất** cho built-in lẫn check động:
   - `company_detail.html` group theo `check_code` đã đa hình sẵn — chỉ cần `SPECS` view (static + DB) merge thành 1 source.
   - Mỗi check (built-in lẫn động) có metadata: title, description, severity scale, group → cùng 1 schema.

**Ngoài scope (KHÔNG làm đợt này):**

- Sinh code Python từ AI rồi `exec` — quá rủi ro, không làm (xem Risks).
- Email/Slack/webhook notification — V2.
- Versioning check động + audit trail thay đổi spec — V2 (ghi `updated_by`, `updated_at` trước).
- Multi-tenant job queue (mọi user dùng chung queue) — V1 single-queue.
- Distribute worker ra nhiều process/node — single-process là đủ cho demo HQ.
- Cancel job đang chạy — chỉ cho phép "kill" stale job qua admin.

## Decisions

### Async job — chọn stack

- **Không Celery / RQ / Dramatiq.** AGENTS.md cấm. Hơn nữa demo chạy SQLite + 1 container, không có Redis.
- **Chọn: in-process worker thread + DB queue.** Tạo bảng `jobs` với `status, payload JSON, result JSON, error TEXT, started_at, finished_at`. 1 background thread khởi tạo trong FastAPI lifespan, poll bảng `jobs` mỗi 1-2s, lock row bằng `UPDATE ... WHERE status='queued' RETURNING` (SQLite hỗ trợ qua immediate transaction). Lý do:
  - Không thêm service mới.
  - State persistent: restart không mất job (job đang `running` mà server chết → mark `failed` ở startup nếu `started_at` cũ).
  - Đủ throughput cho 4 DN × 49 check; queue depth thực tế <10.
- **Alternative đã loại**: `BackgroundTasks` của FastAPI — sống trong process lifetime nhưng không persistent, không có trang `/jobs` thật sự (mất state khi reload). `asyncio.create_task` cùng vấn đề.
- **Concurrency SQLite**: WAL mode đã bật (verify). 1 writer thread + N reader = OK. Nếu sau này cần parallel jobs → thêm worker pool 2-3 thread, nhưng giữ serialize write qua 1 `SessionLocal` per worker.

### Async job — UI shape

- Nút "Chạy kiểm tra" hiện tại đổi thành "Đưa vào hàng đợi" → 303 redirect về `/jobs/{id}` (trang chi tiết job, auto-refresh 2s).
- Trang `/jobs` list (filter theo company, status, mine-only) — pagination.
- Badge ở navbar: số job của user đang `running` + số `done` chưa xem (in-app notification dạng inbox).
- Polling phía client: simple `meta refresh` hoặc fetch JSON `/jobs/{id}.json` — không cần SSE/WebSocket cho demo này.

### Catalog động — biểu diễn check spec

- **Không sinh code Python.** Định nghĩa check qua **DSL khai báo**, gồm:
  - `kind`: enum (`threshold_compare`, `cross_table_match`, `aggregate_threshold`, `presence_check`, ...) — bắt đầu với 3-4 kind phổ biến mà AI có thể fill template.
  - `tables`: liệt kê bảng nguồn (`nvl_balances`, `sp_balances`, `declaration_lines`, ...).
  - `metric_expr`: biểu thức an toàn (chỉ + - * / abs, tham chiếu cột bảng) — eval qua `simpleeval` hoặc parser tự viết, KHÔNG `eval()`/`exec()`.
  - `thresholds`: list bands `[{lt: 5, severity: info}, {lt: 20, severity: warning}, {gte: 20, severity: critical}]`.
  - `subject`: cột làm `subject_key` (ví dụ `material_code`).
  - `evidence_template`: cấu trúc dict cho `evidence_refs`.
  - `title_template`, `description_template`: Jinja-safe string (autoescape, không cho `{% %}` block).
- **Lưu DB**: bảng `check_definitions (id, code, kind, spec JSON, status enum[draft/published/disabled], created_by, ...)`. Code có prefix `X.*` để phân biệt với built-in `C1.*` (X = "custom"/"extended").
- **Runtime**: thêm 1 `DynamicCheckRunner` đọc spec, build SQL query qua SQLAlchemy core (KHÔNG raw string), iterate kết quả, emit `Finding`. Chung interface với check built-in (signature `fn(session, company_id, year) -> list[Finding]`).
- **Registry merge**: `registry.get_all_specs(session)` trả về dict gộp `SPECS` (static) + DB rows (dynamic, published). Pipeline `run_checks` đi qua merged dict — không phân biệt built-in/dynamic.

### Catalog động — luồng AI sinh check

- Admin mở `/admin/checks/new` — form: "Mô tả ý tưởng" (textarea tiếng Việt) + chọn DN + năm để preview.
- AI nhận: mô tả + schema các bảng (columns + sample 3 rows) + danh sách `kind` hợp lệ + 2-3 ví dụ spec đã publish. Return JSON spec.
- Spec hiển thị dạng form đã fill — admin có thể chỉnh từng field (threshold, metric_expr, subject) trước khi save.
- Save = `status='draft'`. Nhấn "Chạy thử" → submit job preview → kết quả hiện inline.
- "Publish" → `status='published'`. Tự động xuất hiện ở tab Settings của trang DN, từ run kế tiếp.
- Tất cả gọi AI đi qua provider chain hiện tại (Gemini → DeepSeek fallback). KHÔNG cache spec generation (mỗi request 1 lần, ít gọi).

### Hiển thị kết quả đồng nhất

- `company_detail.html` đã group theo `check_code` + render title/description từ `SPECS[code]`. Đổi `SPECS[code]` → `get_check_meta(code, session)` (helper merge built-in + dynamic).
- Tab phân nhóm: built-in giữ "Nhóm 1 → 12" (theo `group` của CheckSpec); check động vào nhóm mới "Kiểm tra mở rộng" (group=99) hoặc cho phép admin chọn group khi publish.
- Badge "Tuỳ chỉnh" (UI hint) ở header card của dynamic check để cán bộ HQ biết đây là rule mở rộng, không thuộc catalog 49 chính thức.
- Trang `/admin/checks` — list/edit/disable check động, log version history.

## Risks

- **Code injection**: nếu AI sinh code Python → admin có thể publish rule độc hại (vô tình hoặc cố ý) → RCE trong process server. **Mitigation**: DSL khai báo, không bao giờ `exec`/`eval` string từ DB. `metric_expr` chạy qua AST parser whitelist toán tử số học + tên cột; reject mọi gì khác.
- **SQL injection qua dynamic check**: spec build SQL phải đi qua SQLAlchemy core/ORM với param binding, KHÔNG concat string. Tên bảng/cột whitelist từ metadata, không trust input.
- **AI sinh spec sai logic** → false positive/false negative đầy bảng cho HQ. Mitigation: bắt buộc preview-on-sample trước khi publish; show diff số findings vs check tương tự built-in.
- **SQLite lock contention**: worker thread write findings cùng lúc user query trang → có thể timeout. Mitigation: WAL mode (đã có), batch insert findings 1 transaction/check, set `busy_timeout=5000`.
- **Job zombie**: server chết khi đang `running` → trạng thái kẹt. Mitigation: startup hook scan `running` job với `started_at < now - 1h` → mark `failed` với error "interrupted".
- **Catalog đề án vs MVP drift**: thêm check động trong MVP nhưng đề án vẫn 49 → cán bộ HQ nhầm scope. Mitigation: tag UI "Kiểm tra mở rộng (ngoài catalog)" rõ ràng; mục Notes for HQ trong handoff khi demo.
- **Quyền publish**: chỉ role `admin` được publish; `auditor` chỉ xem & comment. Hiện auth có RBAC ([app/auth.py]) — cần verify check role.
- **Threshold UX**: admin Vietnamese không quen với JSON band → form nhập 3 ô (info<x, warning<y, critical>=y) là đủ cho `kind=threshold_compare`. Kind khác mỗi loại có form riêng.
- **Performance check động**: build SQL ad-hoc có thể không có index. Đợt này chấp nhận; nếu có check chậm → admin thấy `duration_ms` trong job log, optimize sau.

## Decisions chốt (2026-05-26)

| # | Quyết định | Ghi chú thực thi |
|---|---|---|
| Q1 | **5 kind DSL ban đầu**: `threshold_compare`, `presence_check`, `aggregate_threshold`, `cross_table_match`, `ratio_threshold` | Mỗi kind 1 form admin riêng. JSON Schema validate phía server trước khi save spec. Few-shot AI có ví dụ cho cả 5 kind. |
| Q2 | **Code prefix `X.1`, `X.2`...** global counter | Group=99 mặc định "Kiểm tra mở rộng"; admin có thể override group khi publish. Counter atomic qua `SELECT max(code) ...` trong transaction. |
| Q3 | **Không auto-purge**, admin dọn tay | Trang `/admin/jobs` có nút "Xóa job cũ hơn N ngày" + filter status=`done\|failed`. Không scheduler purge. |
| Q4 | **Preview-on-sample**: admin chọn (DN, năm) | Cache kết quả preview theo `(spec_hash, company_id, year)` → reload spec edit thấy "đã preview lần trước: N findings". Cache cùng connection lifetime, bảng `check_preview_runs` |
| Q5 | **In-app badge** ở navbar + `/jobs` | Polling `meta refresh` mỗi 2s ở trang `/jobs/{id}`; badge fetch JSON `/jobs/unread.json` mỗi 10s ở navbar. Không SMTP/Web Push. |
| Q6 | **Không cron** (V2) | Không thêm field `cron_expr` vào schema. Tránh debt sớm. |
| Q7 | **Không đưa check động vào đề án** | Catalog 49 giữ là source of truth chính thức. Check `X.*` chỉ tồn tại trong MVP, UI có badge "Kiểm tra mở rộng (ngoài catalog)" để cán bộ HQ không nhầm. Đề án không bump v11 cho feature này. |
| Q8 | **Gemini 2.5 Pro (deep)** + few-shot **5 ví dụ** | Spec gen ít gọi (admin nhập tay từng cái) → quota 100/ngày dư xài. Few-shot 5 ví dụ phủ 5 kind. Bypass fallback NIM cho spec gen (nếu Pro fail → return error rõ, không silent downgrade). |

## Open Questions còn lại

Không. Các điểm chưa biết sẽ phát sinh khi implement — xử lý inline qua TDD.

## Next step

1. **`/tdd` cho async job runner** — model `Job`, worker thread, 2 trang UI. Mục tiêu: chuyển nút "Chạy kiểm tra" sang luồng job + trang `/jobs` chạy được. 0.5-1 ngày.
2. **Catalog động luồng A (dev-code)** — helper `get_check_meta(code, session)` + docstring "Cách thêm check built-in". <0.5 ngày.
3. **Catalog động luồng B (AI-assisted)** — DSL 5 kind, `DynamicCheckRunner`, admin UI tạo + preview + publish, AI spec gen với Pro + few-shot 5. 2-3 ngày.

Đề xuất kick off bước 1 ngay; bước 2-3 mở session riêng sau khi bước 1 deploy.
