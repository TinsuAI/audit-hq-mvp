# Session 2026-05-26 — Async jobs + rate-based scoring + legal docs library

## What Was Done

5 commits trên `main`, đã push + deploy production (`audit-hq-demo.tinsu.ai`):

| SHA | Tóm tắt |
|---|---|
| `c8c370f` | Async job runner + rate-based scoring + scoring methodology page |
| `c1f65c7` | Docs index `/tai-lieu` + navbar link |
| `e7df2ab` | Sửa BCQT terminology (BCQT là báo cáo bao gồm M15/M15a/M16, không phải song song) |
| `cc0dcc2` | Fix Dockerfile copy `docs/` vào image |
| `222bf76` | Ingest 3 văn bản pháp lý cốt lõi (TT 38/2015, TT 39/2018, TT 81/2019) |

### Feature 1 — Async job runner

Trước: nút "Chạy kiểm tra" chạy sync trong HTTP request, blocking. Sau:

- **Model `Job`** (`app/models/job.py`): id, kind, payload JSON, status enum, result JSON, error, created_by, company_id, period_year, started_at, finished_at, viewed_at. 2 index: `(status, created_at)` + `(created_by, status)`. Migration `de9eee546b80`.
- **Dispatch** (`app/jobs/__init__.py`): `register_handler`, `enqueue_job`, `run_job`. Handler signature `(payload, session) -> dict | None`.
- **Worker** (`app/jobs/worker.py`): `JobWorker` class chạy thread trong FastAPI lifespan, poll bảng `jobs` mỗi 1.5s. `claim_next_job` atomic qua SQL UPDATE; race-safe (test verify 2 thread cùng claim → 1 thắng). Recovery: startup hook mark zombie (status=running, started_at < now-1h) → failed.
- **Routes** (`app/routes/jobs.py`): `GET /jobs` (list filter status), `GET /jobs/{id}` (auto-refresh 2s), `GET /jobs/unread.json` (badge JSON).
- **Handlers** (`app/jobs/handlers.py`): `run_checks_handler` (1 năm); `run_batch_handler` (loop mọi năm có data — dùng `find_years_with_data`).
- **UI**: navbar badge "📋 Công việc" + polling mỗi 10s. Button "🔄 Chạy lại tất cả năm" thay vì 1 năm (theo design decision Q3).
- **POST `/companies/{code}/run-checks`**: optional year. Có year → RUN_CHECKS đơn lẻ. Không → BATCH_RUN.
- **SQLite**: thêm WAL + busy_timeout=5000 pragmas trong `app/database.py` cho concurrent writes.
- **Tests**: +25 (model 5, dispatch 5, worker 4, routes 5, batch 6).

### Feature 2 — Rate-based scoring + 5 hạng neutral

Trước: linear sum findings → DN nhiều mã = cao điểm tự động (volume bias).

- **Bảng `company_year_scores`** (`app/models/score.py`): (company_id, year, score 0-1000, tier label, breakdown JSON, computed_at). Unique per (DN, năm). Migration `46b3bcaebbe4`.
- **Denominators** (`app/checks/denominators.py`): `RULE_SCOPE` map mỗi check → scope (`nvl`/`tp`/`m16`). `compute_denominators` đếm distinct mã trong M15/M15a/M16 + BCCT phía nhập/xuất.
- **Scoring** (`app/checks/scoring.py`): GIỮ legacy `compute_risk_score` cho backward compat. Thêm:
  - `compute_rule_score(findings, denominator) -> 0..10` — rate = points / (10×denom), capped.
  - `compute_company_year_score(findings, denominators) -> dict(score, tier, rule_scores, ...)` — score = 1000 × raw / 180.
  - `tier_for(score)`, `tier_css_for(score)` — 5 hạng: Dữ liệu nhất quán (0-100) → Bất thường nghiêm trọng (851-1000).
- **Pipeline**: `run_checks.py` sau khi compute findings → upsert `CompanyYearScore`; `company.risk_score = max qua các năm` (ranking).
- **UI**: `company_detail.html` stat "Rủi ro dữ liệu (năm X) {score}/1000 — {tier}" với màu theo tier. `companies_list.html` thêm cột "Mức cảnh báo". Disclaimer pháp lý footer link tới `/tai-lieu/scoring-methodology`.
- **Script**: `scripts/recompute_all_scores.py` — idempotent, tính lại score từ findings hiện có, không re-run checks. Hỗ trợ `--company X`, `--dry-run`.
- **Tests**: +23 (3 score model, 5 denominators, 15 rate-based scoring including volume-invariance test).

### Feature 3 — Thư viện tài liệu

- **Route** `/tai-lieu/{slug}` (`app/routes/docs.py`): markdown file → HTML qua `python-markdown` (extensions: tables, fenced_code, toc, sane_lists). Whitelist `PUBLIC_DOCS` 4-tuple `(file, title, description, category)`. Cache LRU 8 entries.
- **Index** `/tai-lieu`: group theo category (`methodology` + `legal`). Template `docs_index.html` show section + card grid.
- **Navbar**: nút "📚 Tài liệu" cho mọi user đã login.
- **Tài liệu hiện có**:
  - `docs/scoring-methodology.md` — Giải thích cách tính điểm 0-1000, 5 hạng, tham chiếu WCO/OECD/TT 81. 10 sections, ~14KB HTML.
  - `docs/tt-38-2015-tt-btc.md` — Khung pháp lý: định nghĩa BCQT, Mẫu 15/15a/16, mã loại hình E11-E62/A42/B13.
  - `docs/tt-39-2018-tt-btc.md` — Sửa đổi TT 38: bãi bỏ thông báo định mức trước, lưu giữ 5 năm.
  - `docs/tt-81-2019-tt-btc.md` — Quản lý rủi ro, 5 Mức tuân thủ + 9 hạng risk (anchor cho disclaimer).
- **Tests**: +8 (auth required, index lists, sections grouped, navbar link, all 3 legal docs render).

### Feature 4 — Dev port chuẩn hoá

Makefile `dev` đổi `--port 8000` → `--port 8200` (match docker-compose host port + Cloudflare tunnel). Memory `dev-port.md` lưu lại.

## Decisions Made

### Scoring methodology
- **Rate-based với per-rule ceiling** (sau khi research WCO/AEO/OECD): mỗi rule contribute tối đa 10 điểm bất kể có 500 hay 50 findings. Score 0-1000.
- **5 hạng neutral**, KHÔNG dùng "Mức 1-5" để tránh nhầm với TT 81/2019 (5 Mức tuân thủ TCHQ chính thức). Nhãn: Dữ liệu nhất quán → Bất thường nghiêm trọng.
- **Disclaimer bắt buộc** trên mọi page có score: "không phải đánh giá tuân thủ theo TT 81/2019".

### Async job runner
- **In-process worker thread + DB queue**, KHÔNG Celery/Redis (AGENTS.md cấm).
- **2 session per iteration**: 1 claim atomic, 1 execute handler (tách transaction).
- **Job retention**: không auto-purge, admin xóa tay khi cần (Q3 decision).
- **Notification**: in-app badge polling 10s, không email/Web Push (Q5 decision).

### Catalog động (CHƯA BUILD)
Decisions đã chốt trong brief `.ai/features/2026-05-26-async-jobs-and-dynamic-checks.md`:
- 5 kind DSL (`threshold_compare`, `presence_check`, `aggregate_threshold`, `cross_table_match`, `ratio_threshold`)
- Code prefix `X.1`, `X.2`... global counter
- AI sinh spec qua Gemini 2.5 Pro + few-shot 5 ví dụ
- Preview-on-sample: admin chọn (DN, năm)
- Không có cron (V2)

### Legal library
- Lưu trong `audit-hq-mvp/docs/` (gần code, copy vào Docker image qua Dockerfile).
- Copy TT 81/2019 từ `audit-hq/.ai/legal/` sang đây (proposal repo giờ outdated — nên sync 1 chiều: MVP là canonical).
- Format: frontmatter + sections (thông tin cơ bản, phạm vi, điều quan trọng, áp dụng cho Audit-HQ, nguồn).
- Source: thuvienphapluat.vn (free read), vanban.chinhphu.vn (official). Luật Việt là public domain.

## What Didn't Work

### CI/CD bị tắc giữa session
- GitHub Actions API trả `HTTP 500` cho push event của commit `222bf76` (legal docs ingest). Cả `gh workflow run` cũng 500.
- **Workaround**: SSH tinsu → `git pull` trong runner work dir → `docker compose build && up -d`.
- **Bug khi deploy manual**: quên set env `DB_DATA_PATH=/home/tinsu/audit-hq-mvp-deploy/db-data`. Docker dùng default `./db-data` → tạo volume rỗng trong runner work dir → app hiển thị 0 DN.
- **Fix**: `docker compose down` rồi up lại với env đúng. DB thật vẫn an toàn ở `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite` (26MB).
- **Lesson**: lệnh deploy manual chuẩn phải bao gồm `DB_DATA_PATH`. Đã ghi vào session này.

### URL conflict /docs vs /tai-lieu
- Lần đầu route ở `/docs/scoring-methodology` xung đột với FastAPI Swagger UI `/docs`. Đổi sang `/tai-lieu/{slug}` (tiếng Việt, không xung đột).
- Swagger UI `/docs` vẫn public (chưa disable) — chưa thấy cần.

### URL fetch lần đầu
- WebFetch URL guess cho TT 38/2015 và TT 39/2018 → trả về document khác (TT 44/2014 và QĐ 160/UBND). Phải search + verify URL thật trước khi fetch.

## Open Items

### Phải làm trước demo HQ
1. **Manual browser smoke test** trên `audit-hq-demo.tinsu.ai`: login, vào /tai-lieu, /jobs, /companies, vào DN_001 → bấm "🔄 Chạy lại tất cả năm" → xem job page. (Tôi chỉ test qua curl + TestClient.)
2. **Update đề án** ở `audit-hq` repo §2.6 — đồng bộ giải thích scoring rate-based (per CLAUDE.md, AI không tự đụng đề án).
3. **Build SHA hiện hiển thị `222bf76` đúng** sau khi deploy manual. CI tự động chạy lại sẽ override với SHA mới (nếu sự cố GitHub Actions hết).

### Feature backlog
4. **Catalog động luồng A + B** (brief đã chốt, chưa code): khoảng 3-4 ngày work.
5. **AI assistant integrate legal docs**: hiện 3 văn bản chỉ render HTML, chưa được AI sidebar truy cập. Tích hợp keyword search hoặc retrieve-by-slug khi cán bộ HQ hỏi về luật.
6. **Văn bản pháp lý còn lại trong backlog INDEX.md**: NĐ 08/2015, TT 72/2015, TT 06/2024, QĐ 2218/QĐ-TCHQ, Luật Hải quan 54/2014. User đã giảm scope chỉ làm 3 quan trọng nhất; phần còn lại defer.

### Tech debt
7. **Disable FastAPI Swagger UI** `/docs`, `/redoc`, `/openapi.json` cho production (currently public). Hoặc move sau auth. Không urgent.
8. **`company.risk_score`** giờ là max qua các năm. UI có thể confusing — thực ra hiển thị "điểm cao nhất" nhưng label cũ vẫn là "Điểm rủi ro DN". Có thể đổi label.
9. **Multiple Jinja2Templates instances** (mỗi route module có instance riêng) → khi thêm template global mới phải add vào tất cả. Refactor thành shared instance khi nào có thời gian.
