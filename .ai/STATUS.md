# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-26, session catalog động):**
> Branch `main` đã push + deploy. Live trên `audit-hq-demo.tinsu.ai` (build `9c96af2`).
> 374/374 tests pass. Catalog check động (DSL 5 kind, no-exec) đã build và deploy.

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build hiện tại: `9c96af2` — dynamic check catalog (DSL 5 kind). Deploy manual (CI vẫn ổn định sau lần trước).
- 4 DN demo với điểm sau khi rerun checks toàn bộ năm có data:
  - DN_001 Phương Đông: 238/Có chênh lệch nhỏ (2023-2025)
  - DN_003 Hoa Sen: 242/Có chênh lệch nhỏ (2021-2025)
  - DN_004 Nam Tiến: 97/Dữ liệu nhất quán (2024)
  - DN_002 Tiên Phong: 74/Dữ liệu nhất quán (2024-2025)
- Job ID #1-4 đã done (BATCH_RUN cho 4 DN).

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite (WAL + busy_timeout=5000).
- AI: OpenAI SDK compat, Gemini 2.5 (primary) + NIM DeepSeek (fallback).
- Markdown render: `python-markdown` 3.10 (mới session này).
- Dev port: **8200** (cố định, match docker-compose + Cloudflare tunnel).
- 314 tests pass.

### Async job runner (mới session này)
- Bảng `jobs` + worker thread trong FastAPI lifespan, poll 1.5s.
- `JobKind.RUN_CHECKS` (1 năm) + `JobKind.BATCH_RUN` (mọi năm có data).
- `POST /companies/{code}/run-checks` mặc định enqueue BATCH_RUN; có form year → RUN_CHECKS.
- Trang `/jobs` list, `/jobs/{id}` detail (auto-refresh 2s), `/jobs/unread.json` badge.
- Navbar 📋 Công việc badge polling 10s.
- Startup hook recover zombie (status=running > 1h → failed).

### Rate-based scoring (mới session này)
- Bảng `company_year_scores`: (DN, năm) → score 0-1000 + tier + breakdown JSON.
- Formula: `rule_score = min(1, Σpoints/(10×denom)) × 10` per rule, sum 16 rule + 20 combo bonus, rescale 1000/180.
- 5 hạng neutral: 0-100/101-300/301-600/601-850/851-1000 (KHÔNG dùng "Mức N" — tránh nhầm TT 81/2019).
- `company.risk_score` = max qua các năm (cho ranking).
- Legacy `compute_risk_score` (linear sum) vẫn còn cho backward compat.

### Thư viện tài liệu `/tai-lieu` (mới session này)
- 4 trang đã ingest: scoring-methodology + 3 thông tư (TT 38/2015, TT 39/2018, TT 81/2019).
- Index `/tai-lieu` group "Phương pháp luận" + "Văn bản pháp lý".
- Markdown render qua `app/routes/docs.py` + `PUBLIC_DOCS` whitelist 4-tuple `(file, title, description, category)`.
- Navbar 📚 Tài liệu link.
- Disclaimer pháp lý ở `companies_list.html` + `company_detail.html` link tới scoring-methodology.

## Recent Changes (session 2026-05-26 catalog động)

1 commit `9c96af2`, đã push + deploy. 374 tests pass.

**Catalog check động (DSL, no-exec):**
- `CheckDefinition` model (bảng `check_definitions`, status draft/published/disabled). Migration `646b92a93768`.
- `DynamicCheckRunner`: 5 kind DSL — `threshold_compare`, `presence_check`, `aggregate_threshold`, `cross_table_match`, `ratio_threshold`. Full whitelist bảng + cột + agg fn + filter op — không eval/exec code.
- Registry merge: `get_check_meta(code, session)` + `get_all_specs(session)` trả về dict gộp built-in SPECS + published dynamic checks.
- Pipeline: `run_checks` tự load và chạy published X.* checks. Wipe findings X.* khi re-run.
- Admin UI: `/admin/checks` list, `/admin/checks/new`, detail page, publish/disable/revert-draft endpoints. Navbar link "🔬 Kiểm tra mở rộng" cho admin.
- `company_detail.html`: findings X.* hiện "Tuỳ chỉnh" badge, dùng `all_specs` (merged, per-request) thay SPECS global.
- 60 tests mới (5 model, 8 registry, 33 runner, 3 pipeline, 11 admin routes).

---

## Recent Changes (session 2026-05-26 jobs+scoring+docs)

5 commits, đã push + deploy. Chi tiết trong `.ai/sessions/2026-05-26-jobs-scoring-docs.md`.

- `c8c370f` — Async job runner + rate-based scoring + methodology docs
- `c1f65c7` — Docs index `/tai-lieu` + navbar link
- `e7df2ab` — Sửa BCQT terminology (BCQT chứa M15/M15a/M16, không song song)
- `cc0dcc2` — Fix Dockerfile copy `docs/` vào image
- `222bf76` — Ingest 3 văn bản pháp lý (TT 38, TT 39, TT 81) + categorize

Repo `audit-hq` (proposal): commit `b232b5e` `docs(legal): start legal reference library for RAG` (giờ outdated — MVP là canonical cho legal docs từ session này trở đi).

## Next Steps

1. **Manual browser smoke test** trên live demo — kịch bản: login → /tai-lieu → click 4 cards → /companies → click DN_001 → click "🔄 Chạy lại tất cả năm" → xem job progress → quay về company detail xem score mới.
2. **Demo HQ** — chuẩn bị flow 5-10 phút với câu hỏi nghiệp vụ tiếng Việt khó. Watch behavior + quota Gemini/NIM.
3. **Update đề án §2.6** ở repo `audit-hq` — đồng bộ giải thích scoring rate-based với HQ-facing language (AI không tự đụng per CLAUDE.md — chờ user).
4. **Catalog động (luồng A + B)** — feature brief đã chốt trong `.ai/features/2026-05-26-async-jobs-and-dynamic-checks.md`. Ước tính 3-4 ngày. Defer cho session sau.
5. **AI assistant integrate legal docs** — hiện 3 văn bản chỉ render HTML. Tích hợp retrieve-by-slug hoặc keyword search khi cán bộ hỏi về luật.
6. **Văn bản pháp lý mở rộng** — NĐ 08/2015, TT 72/2015, TT 06/2024, QĐ 2218/QĐ-TCHQ, Luật Hải quan 54/2014. User chốt chỉ làm 3 quan trọng nhất; phần còn lại defer.

## Blockers

Không có blocker hard. GitHub Actions API có episode 500 ở giữa session — đã workaround bằng deploy manual; nếu vẫn 500 lúc cần CI thì retry hoặc dùng deploy manual (xem Notes).

## Notes for Next AI Session

### Deploy manual (khi CI hỏng)
```bash
ssh tinsu  # qua ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
cd /home/tinsu/actions-runner-audit-hq/_work/audit-hq-mvp/audit-hq-mvp
git pull origin main
DB_DATA_PATH=/home/tinsu/audit-hq-mvp-deploy/db-data \
BUILD_SHA=$(git rev-parse --short HEAD) \
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
AUTH_USER=admin AUTH_PASSWORD=admin \
docker compose up -d --build
```

**Cảnh báo**: BẮT BUỘC set `DB_DATA_PATH=/home/tinsu/audit-hq-mvp-deploy/db-data`. Nếu quên → docker dùng default `./db-data` trong runner work dir → tạo volume rỗng → app hiển thị 0 DN. (Đã bị bug này trong session, fix bằng `docker compose down` + up lại với env đúng.)

### Recompute scores trên prod
```bash
ssh tinsu
docker exec audit-hq-mvp python -m scripts.recompute_all_scores [--company DN_001] [--dry-run]
```

Idempotent. Tính lại CompanyYearScore từ findings hiện có, không re-run checks. Dùng sau khi đổi công thức scoring hoặc reset score manual.

### Rerun checks all years cho 4 DN (BATCH_RUN qua Python)
```python
# docker exec audit-hq-mvp python -c "..."
from app.database import SessionLocal
from app.jobs import enqueue_job
from app.models import Company, User
from app.models.job import JobKind
from sqlalchemy import select

with SessionLocal() as s:
    admin = s.scalar(select(User).where(User.username=='admin'))
    for code in ['DN_001','DN_002','DN_003','DN_004']:
        c = s.scalar(select(Company).where(Company.code==code))
        enqueue_job(s, kind=JobKind.BATCH_RUN, payload={'company_code': code},
                    created_by=admin.id, company_id=c.id, period_year=None)
```

Worker thread tự pick up. Theo dõi qua `/jobs`.

### Catalog động — open questions đã chốt
Trong brief `.ai/features/2026-05-26-async-jobs-and-dynamic-checks.md`:
- 5 kind DSL ban đầu (threshold_compare, presence_check, aggregate_threshold, cross_table_match, ratio_threshold)
- Code prefix `X.1, X.2...` global counter; group=99 hoặc admin chọn
- AI Gemini 2.5 Pro + few-shot 5 ví dụ; bypass fallback NIM cho spec gen
- Preview-on-sample admin chọn (DN, năm); cache by spec_hash
- Không cron (V2)
- Không auto-purge job, admin dọn tay
- In-app badge only (no email/Web Push)

### Disclaimer pháp lý — đã chốt wording
> "Đây là chỉ số rủi ro dữ liệu BCQT do Audit-HQ tính từ phát hiện chênh lệch giữa các báo cáo. KHÔNG phải đánh giá tuân thủ pháp luật theo Thông tư 81/2019/TT-BTC. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan."

Đặt ở footer mọi trang có score. Link "Xem cách tính điểm →" tới `/tai-lieu/scoring-methodology`.

### Test patterns mới
- File-based SQLite fixture `tests/test_jobs/test_worker.py::file_db` cho concurrency test (in-memory không share giữa thread).
- TestClient flow: `_setup_db()` → seed admin → `_login()` → assertions. Pattern reuse 4 test files trong test_jobs/.
- HANDLERS dict global → autouse fixture `_clear_handlers` để cô lập tests.

### Memory lưu lại (session này)
- `dev-port.md` — port 8200 cố định cho dev local

### Hạ tầng đã ghi nhớ từ sessions trước (vẫn áp dụng)
- Cloudflare tunnel `tinsu-online-server` remotely-managed, không sửa file local
- WSL ssh broken → dùng `ssh.exe -F` từ Windows path
- Mỗi route module có Jinja2Templates instance riêng (chưa refactor)
- `make lint` chạy `ruff check app tests scripts`, KHÔNG check migrations
