# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-26, session preview + migration fix):**
> Branch `main` đã push + deploy. Live trên `audit-hq-demo.tinsu.ai` (build `6acc6ca`).
> 390 tests pass. Check X.1 đã published trên prod, 10 findings cho DN_001/2023.

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build hiện tại: `6acc6ca` — preview endpoint + migration fix. Deploy manual.
- 4 DN demo:
  - DN_001 Phương Đông: score 238 (2023-2025) — có 10 X.1 findings từ BATCH_RUN job #5
  - DN_003 Hoa Sen: score 242 (2021-2025)
  - DN_004 Nam Tiến: score 97 (2024)
  - DN_002 Tiên Phong: score 74 (2024-2025)
- Job #5 done (BATCH_RUN DN_001 với X.1 published). DN_002/003/004 chưa rerun với X.1.
- Check X.1 (`cross_table_match`, NVL import vs BCCT E11/E31) đã PUBLISHED.
- Scores chưa recompute sau X.1 findings.

### Migration cảnh báo quan trọng
Migration `646b92a93768` ban đầu sinh empty (upgrade=`pass`). Đã fix — nhưng cần nhớ:
**Migrations baked vào Docker image.** Nếu sửa migration file, phải rebuild image trước khi chạy `alembic upgrade`. Không thể `git pull` + exec để áp dụng migration file mới.

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite (WAL + busy_timeout=5000).
- AI: OpenAI SDK compat, Gemini 2.5 (primary) + NIM DeepSeek (fallback).
- Dev port: **8200** (cố định, match docker-compose + Cloudflare tunnel).
- 390 tests pass.

### Catalog check động (DSL, no-exec)
- `CheckDefinition` model (bảng `check_definitions`, status draft/published/disabled). Migration `646b92a93768`.
- `DynamicCheckRunner`: 5 kind DSL — `threshold_compare`, `presence_check`, `aggregate_threshold`, `cross_table_match`, `ratio_threshold`. Whitelist bảng + cột + agg fn + filter op.
- Registry merge: `get_check_meta(code, session)` + `get_all_specs(session)`.
- Pipeline: wipe findings X.* khi re-run, load + chạy published X.* checks.
- Admin UI: `/admin/checks` list, `/admin/checks/new` (với AI spec gen), detail page.
- AI spec gen: `POST /admin/checks/generate-spec` → Gemini 2.5 Pro, no fallback, 5-shot.
- Preview: `POST /admin/checks/{id}/preview` → dry-run (company, year), không ghi DB.
- `company_detail.html`: findings X.* hiện "Tuỳ chỉnh" badge.

### Async job runner
- Bảng `jobs` + worker thread trong FastAPI lifespan, poll 1.5s.
- `JobKind.RUN_CHECKS` (1 năm) + `JobKind.BATCH_RUN` (mọi năm có data).
- Trang `/jobs` list, `/jobs/{id}` detail (auto-refresh 2s), `/jobs/unread.json` badge.
- Navbar 📋 Công việc badge polling 10s.

### Rate-based scoring
- Bảng `company_year_scores`: (DN, năm) → score 0-1000 + tier + breakdown JSON.
- 5 hạng neutral: 0-100/101-300/301-600/601-850/851-1000.
- `company.risk_score` = max qua các năm (cho ranking).

### Thư viện tài liệu `/tai-lieu`
- 4 trang: scoring-methodology + TT 38/2015, TT 39/2018, TT 81/2019.
- Navbar 📚 Tài liệu link.

## Next Steps

1. **Rerun BATCH_RUN cho DN_002/003/004** để có X.1 findings trên tất cả DN.
2. **Recompute scores** sau khi có X.1 findings: `docker exec audit-hq-mvp python -m scripts.recompute_all_scores`.
3. **Edit check spec** từ detail page — hiện read-only, cần thêm edit form.
4. **AI spec gen test thật** — cần `model_deep` được cấu hình trong `/admin/ai-settings` (Gemini 2.5 Pro via OpenRouter).
5. **Demo HQ** — flow 5-10 phút: login → tạo check qua AI → preview → publish → rerun DN → xem findings.
6. **Văn bản pháp lý mở rộng** — NĐ 08/2015, TT 72/2015, TT 06/2024 (defer).

## Blockers

Không có blocker hard.

## Notes for Next AI Session

### Deploy manual
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
cd /home/tinsu/actions-runner-audit-hq/_work/audit-hq-mvp/audit-hq-mvp
git pull origin main
DB_DATA_PATH=/home/tinsu/audit-hq-mvp-deploy/db-data \
BUILD_SHA=$(git rev-parse --short HEAD) \
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
AUTH_USER=admin AUTH_PASSWORD=admin \
docker compose up -d --build
```

**CRITICAL**: `DB_DATA_PATH` bắt buộc. Quên → volume rỗng → 0 DN.
**CRITICAL**: Migration file thay đổi → phải `--build` mới có hiệu lực. Không thể chỉ `git pull` + `alembic upgrade`.

### Alembic trên prod
```bash
# Chạy migration (sau rebuild):
docker compose exec -T app alembic upgrade head

# Nếu migration file đã chạy nhưng DDL trống (như bug 646b92a93768):
docker compose exec -T app alembic stamp <previous_revision>
docker compose exec -T app alembic upgrade head
```

### Recompute scores
```bash
docker compose exec -T app python -m scripts.recompute_all_scores [--company DN_001] [--dry-run]
```

### BATCH_RUN cho nhiều DN
```python
# docker compose exec -T app python -c "..."
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

### Hạ tầng cố định
- Cloudflare tunnel `tinsu-online-server` remotely-managed, không sửa file local
- WSL ssh broken → dùng `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`
- Mỗi route module có Jinja2Templates instance riêng (chưa refactor)
- `make lint` chạy `ruff check app tests scripts`, KHÔNG check migrations
- Test pattern: `_setup_db()/_teardown()` với StaticPool in-memory SQLite; admin cookie via `make_session_cookie()`

### Disclaimer pháp lý — wording đã chốt
> "Đây là chỉ số rủi ro dữ liệu BCQT do Audit-HQ tính từ phát hiện chênh lệch giữa các báo cáo. KHÔNG phải đánh giá tuân thủ pháp luật theo Thông tư 81/2019/TT-BTC. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan."
