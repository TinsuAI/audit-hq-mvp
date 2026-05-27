# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-27, sau session catalog + tiers + i18n):**
> Branch `main` đã push + deploy. Live `audit-hq-demo.tinsu.ai` build `22aaa7b`.
> 406 tests pass. Toàn bộ UI thuần Việt cho cán bộ Hải quan.

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build hiện tại: `22aaa7b` — i18n thuần Việt. Deploy CI tự động (đã fix checkout EACCES).
- 4 DN demo, ranked theo điểm rủi ro:
  - DN_003 Hoa Sen (Dệt may): score 242 — Cần rà soát
  - DN_001 Phương Đông (Điện tử): score 238 — Cần rà soát
  - DN_004 Nam Tiến (Hoá chất): score 97 — Có chênh lệch nhỏ
  - DN_002 Tiên Phong (Cơ khí): score 74 — Có chênh lệch nhỏ
- Ngưỡng tier mới (default sau commit `4977cd4`): **50 / 100 / 300 / 600 / 1000**.
  Admin chỉnh trực tiếp ở `/admin/risk-tiers` — đổi không cần re-run check.

### Trang mới hôm nay
- `/danh-muc-kiem-tra` — toàn bộ 49 kiểm tra theo §4 đề án (16+14+19).
- `/admin/risk-tiers` — chỉnh 5 ngưỡng hạng rủi ro (form 5 ô số, validate tăng dần + cuối = 1000).
- Navbar gọn: dropdown "⚙️ Quản trị" gom 4 mục admin + dropdown user nhỏ.

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite (WAL + busy_timeout=5000).
- AI: OpenAI SDK compat, Gemini 2.5 (primary) + NIM DeepSeek (dự phòng).
- Dev port: **8200** (cố định, match docker-compose + Cloudflare tunnel).
- 406 tests pass, ruff clean.

### Migrations (head: `a4d5ffcb0da7`)
Chuỗi: `da05efe02a74` → `2d66c843ef0e` (findings) → `9fbf36d7f864` (company.risk_score) → `599dbd931e77` (UOM) → `a3c48313dddf` (ai_settings + ai audit) → `b7e91f4d2a13` (users) → `de9eee546b80` (jobs) → `46b3bcaebbe4` (company_year_scores) → `646b92a93768` (check_definitions) → `a4d5ffcb0da7` (**app_settings**).

### Cấu trúc lưu trữ cấu hình runtime
- `ai_settings` — chỉ cho AI assistant (base_url, api_key, model_default/fast/deep, fallback, limits…).
- `app_settings` — generic key/value JSON cho config admin runtime khác. Hiện chỉ có `risk_tier_uppers`.

### Catalog check
- **49 chính thức** (`app/catalog_full.py`) — danh mục §4 đề án, hardcoded, hiển thị ở `/danh-muc-kiem-tra`.
- **16 MVP đã build** (`app/checks/registry.py`) — runable, có rule code Python.
- **Catalog động** (`check_definitions` table) — đặc tả no-exec, admin tạo qua `/admin/checks`.

### Async job runner
- Bảng `jobs` + worker thread trong FastAPI lifespan.
- `/jobs` list, `/jobs/{id}` detail, badge navbar polling 10s.

### Rate-based scoring
- `company_year_scores` cache (DN, năm) → score 0-1000 + tier + breakdown JSON.
- 5 hạng neutral, ngưỡng đọc runtime qua `app.app_settings.get_tiers()`.
- `company.risk_score` = max qua các năm.

### Thư viện tài liệu `/tai-lieu`
- 4 trang: scoring-methodology + TT 38/2015, TT 39/2018, TT 81/2019.

## Recent Changes (2026-05-27 session, từ commit `a702648` → `22aaa7b`)

5 commit, tất cả đã deploy live:
- `e40ea34` feat(catalog): /danh-muc-kiem-tra page + navbar redesign
- `aff9b18` fix(tests): conftest autouse fixture cho default engine schema
- `0dfc2d7` fix(lint): 32 ruff errors pre-existing (E402/I001/F401/B008/E501)
- `4977cd4` feat(scoring): ngưỡng hạng rủi ro configurable + default 50/100/300/600/1000
- `22aaa7b` i18n(ui): rà soát 19 template + STATUS_LABEL sang tiếng Việt thuần

Chi tiết: `.ai/sessions/2026-05-27-catalog-tiers-i18n.md`.

## Next Steps

1. **Edit check spec từ detail page** — hiện read-only, cần thêm edit form (vẫn pending từ session trước).
2. **Demo HQ** — flow 5-10 phút: login → vào DN_003 → xem ranking + findings → mở `/danh-muc-kiem-tra` → mở `/admin/risk-tiers` đổi ngưỡng → quay lại trang DN thấy tier update ngay.
3. **Backlog catalog research** — Bước 2 (gap analysis vs Johnson Phase 3 / BCQT-System / data-hub) + Bước 3 (spec chi tiết per-check) user đã nói lúc đầu session. Chưa làm.
4. **Văn bản pháp lý mở rộng** — NĐ 08/2015, TT 72/2015, TT 06/2024 (defer, ưu tiên thấp).
5. **Verify `item_detail.html`, `job_detail.html`, `login.html`, `_charts.html`** sạch tiếng Anh (sub-agent báo OK, chưa double-check tay).

## Blockers

Không có.

## Notes for Next AI Session

### Glossary tiếng Việt (đã áp dụng nhất quán — giữ đồng bộ khi viết text mới)
- Draft/Published/Disabled → Nháp/Đã công bố/Đã tắt
- spec/DSL → đặc tả · kind → loại · tier → hạng · score → điểm
- pipeline → dây chuyền xử lý · fallback → dự phòng · timeout → thời gian chờ
- admin (vai trò) → quản trị viên · upload → tải lên · preview → xem trước
- API Key → Mã API · refresh → nạp lại · debug → gỡ lỗi
- Giữ: BCQT, M15/M15a/M16, BCCT, TKXNK, NVL, TP, HS, MST, A42, E11-E62, AI, JSON, API, HTTP

### Đổi ngưỡng tier
- Mặc định: 50/100/300/600/1000 (hardcoded trong `app.app_settings.DEFAULT_RISK_TIER_UPPERS`).
- Admin sửa runtime ở `/admin/risk-tiers`. Bảng `app_settings` row `risk_tier_uppers`.
- Đổi ngưỡng KHÔNG re-run check — tier compute lúc view qua `tier_for(score)`.

### Local DB
- Đã re-ingest fresh sáng 2026-05-27. 4 DN, 2586 phát hiện, 12 (DN, năm) scored.
- Backup gần nhất: `audit_hq.sqlite.bak-20260525-120743` (18MB, codes DN_001-006 với tên cũ).
- File empty rỗng (trước khi restore): `audit_hq.sqlite.empty-20260527-102310`.
- **Lesson: trước khi `rm audit_hq.sqlite*`, backup trước:** `cp audit_hq.sqlite audit_hq.sqlite.bak-$(date +%Y%m%d-%H%M%S)`.

### Workflow re-ingest fresh local
```bash
# Stop dev server trước (file lock SQLite WAL).
kill $(pgrep -f "uvicorn.*8200")

# 1. Wipe business data, giữ users/ai_settings/app_settings.
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('audit_hq.sqlite')
for t in ['findings','company_year_scores','nvl_balances','sp_balances','norms','declaration_lines','companies']:
    c.execute(f'DELETE FROM {t}')
c.commit()
"

# 2. Ingest + run checks 4 DN whitelist (HONG_AN/GROWATT/KIM_LONG/DO_THANH).
.venv/bin/python -m app.pipeline.run_all

# 3. Anonymize TRƯỚC inject (inject expects DN_003).
.venv/bin/python -m scripts.anonymize

# 4. Inject demo findings vào DN_003 (HONG_AN 2024).
.venv/bin/python -m scripts.inject_findings

# 5. Re-run checks DN_003 2024 + recompute scores.
.venv/bin/python -m app.pipeline.run_checks --company DN_003 --year 2024
.venv/bin/python -m scripts.recompute_all_scores

# 6. Restart dev.
nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8200 > /tmp/uvicorn-8200.log 2>&1 &
```

### Deploy manual (vẫn dùng được nếu CI fail)
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
**CRITICAL**: Sửa migration file → phải `--build` mới có hiệu lực.

### Runner work dir EACCES (fix một lần, có thể tái phát)
Nếu CI `actions/checkout@v5` fail `permission denied unlink db-data/audit_hq.sqlite-shm`:
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
docker run --rm \
  -v ~/actions-runner-audit-hq/_work/audit-hq-mvp/audit-hq-mvp/db-data:/x \
  alpine sh -c "rm -rf /x/*"
```

### Tests
- 406 pass. Conftest có autouse session fixture `create_all` trên default engine — không cần test_smoke chạy trước.

### Recompute scores trên prod
```bash
docker compose exec -T app python -m scripts.recompute_all_scores
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
- Cloudflare tunnel `tinsu-online-server` remotely-managed, không sửa file local.
- WSL ssh broken → dùng `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`.
- Mỗi route module có Jinja2Templates instance riêng (chưa refactor).
- `make lint` chạy `ruff check app tests scripts`, KHÔNG check migrations.
- Test pattern: `_setup_db()/_teardown()` với StaticPool in-memory SQLite; admin cookie via `make_session_cookie()`.

### Disclaimer pháp lý — wording đã chốt
> "Đây là chỉ số rủi ro dữ liệu BCQT do Audit-HQ tính từ phát hiện chênh lệch giữa các báo cáo. KHÔNG phải đánh giá tuân thủ pháp luật theo Thông tư 81/2019/TT-BTC. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan."
