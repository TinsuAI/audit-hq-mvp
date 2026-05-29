# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-27, sau session audit + fix vòng 1):**
> Branch `main` đã push + deploy. Live `audit-hq-demo.tinsu.ai` build `01db20d`.
> 432 tests pass, ruff clean. 7 bug check rule + dynamic runner đã audit;
> 6 fix, 1 defer (Bug #6 — dynamic check scope fallback).

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build hiện tại: `01db20d` — audit fix vòng 1. CI 2m23s.
- DB tinsu đã clean junk + rerun checks. 11 (DN, năm) pair, 3416 findings.
- 4 DN demo, score sau rerun (rate-based, max qua các năm):
  - DN_001 Phương Đông (Điện tử): **296** — Cần rà soát
  - DN_003 Hoa Sen (Dệt may): **263** — Cần rà soát
  - DN_002 Tiên Phong (Cơ khí): **125** — Có chênh lệch nhỏ
  - DN_004 Nam Tiến (Hoá chất): **97** — Có chênh lệch nhỏ
- Ngưỡng tier (default sau `4977cd4`): **50 / 100 / 300 / 600 / 1000**.
  Admin chỉnh ở `/admin/risk-tiers` — đổi không cần re-run check.

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite (WAL + busy_timeout=5000).
- AI: OpenAI SDK compat, Gemini 2.5 (primary) + NIM DeepSeek (dự phòng).
- Dev port: **8200** (cố định, match docker-compose + Cloudflare tunnel).
- **432 tests pass** (was 406, +26 mới hoặc đã từng skip), ruff clean.

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

## Recent Changes (2026-05-27 audit + fix vòng 1, từ commit `22aaa7b` → `01db20d`)

6 commit, tất cả đã push + deploy + rerun DB tinsu:
- `b4d2737` fix(adapters): `normalize_code` reject placeholder values
- `233da3f` fix(checks): xoá E13 khỏi `IMPORT_CODES[DNCX]`
- `b81e442` fix(checks): C1.1/C1.4 emit INFO band như description đã hứa
- `c36a3e1` fix(checks): C1.7 thống nhất denominator giữa code, registry, catalog
- `8c3f33c` fix(dynamic_runner): `_eval_threshold` AND semantics trong cùng band
- `01db20d` fix(dynamic_runner): dynamic finding có `evidence_refs` và `subject_type` đúng

Tổng impact đo trên DB demo sau rerun:
- Junk subject_key (`.`, `-`, …) **0** (was 23+).
- C1.2 E13-only false positive **0/240** (was ~93/333 = 28%).
- C1.1 distribution: 16 INFO + 17 WARN + 527 CRIT (INFO band giờ fire đúng).
- Toàn bộ dynamic check finding tương lai sẽ có evidence + subject_type chuẩn.

Chi tiết: `.ai/sessions/2026-05-27-checks-audit-round-1.md`.

## Next Steps

1. **Verify UI tay trên live** — mở 1 finding bất kỳ ở `audit-hq-demo.tinsu.ai`,
   xác nhận evidence hiển thị đúng năm + đúng đối tượng + đã sạch junk
   `.`/E13. Smoke test này chưa làm.
2. **Bug #6 (defer)** — dynamic check denominator fallback `"nvl"` trong
   `denominators.RULE_SCOPE`. Khi có dynamic check đầu tiên publish trên
   `declaration_lines`, sẽ méo điểm. Fix sạch cần thêm `scope` field vào
   `CheckDefinition` model + migration + UI form. Ưu tiên thấp.
3. **C6.1 UX** — display 2 năm evidence có thể gây nhầm dù logic đúng.
   Cân nhắc thêm note "so sánh với kỳ N-1" ở `finding_detail.html` cho
   C6.1, hoặc group evidence theo năm với header.
4. **C2.4 (tồn cuối TP âm)** vẫn W.I.P theo §4.1 — symmetric với C2.3 cho TP.
   Có thể clone `c2_balance.check_c2_3` sang dùng SpBalance.
5. **Edit check spec từ detail page** — hiện read-only, cần thêm edit form
   (pending từ session trước trước nữa).
6. **Demo HQ flow** — login → vào DN_003 → xem ranking + findings →
   `/danh-muc-kiem-tra` → `/admin/risk-tiers` đổi ngưỡng → quay lại DN
   thấy tier update ngay.
7. **Backlog catalog research** — Bước 2 (gap analysis vs Johnson Phase 3
   / BCQT-System / data-hub) + Bước 3 (spec chi tiết per-check). Pending
   từ session catalog-tiers-i18n.
8. **Văn bản pháp lý mở rộng** — NĐ 08/2015, TT 72/2015, TT 06/2024
   (defer, ưu tiên thấp).

## Blockers

Không có.

## Notes for Next AI Session

### Audit fix vòng 1 — đã làm gì
- Đọc 6 module check (c1..c6) + dynamic_runner + scoring + denominators +
  company_type + registry + `_resolve_evidence` + `finding_detail.html`.
- Tìm 7 bug, fix 6, defer 1. Bug C6.1 cross-year evidence user nghi không
  phải bug — C6.1 là check liên kỳ, theo thiết kế phải show 2 năm.
- `IMPORT_CODES[DNCX]` giờ chỉ `{E11, E15}` — KHÔNG có E13. E13 ở
  `MMTB_CODES` public, dùng cho C3.1 và check MMTB tương lai. Detect
  company type dùng `_DETECT_IMPORT_CODES` (gồm E13) — KHÔNG dùng cho
  rule check.
- `_make_finding` trong dynamic_runner giờ require `subject_type`
  argument. Mọi runner pass `subject_col_name` của spec (hoặc cột join).
- C1.1 / C1.4 / C1.7 ngưỡng + title đã đồng bộ giữa code, registry, catalog.
  Nếu sửa 1 chỗ → cập nhật cả 3.

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
- Sau audit fix: 2504 phát hiện local (DB sạch junk + rerun với code mới).
- Backup: `audit_hq.sqlite.bak-pre-audit-fix-20260527-201520` (26MB, state cũ trước fix).
- File empty rỗng (trước khi restore): `audit_hq.sqlite.empty-20260527-102310`.
- **Lesson: trước khi `rm audit_hq.sqlite*`, backup trước:** `cp audit_hq.sqlite audit_hq.sqlite.bak-$(date +%Y%m%d-%H%M%S)`.

### Tinsu DB (sau audit fix)
- 3416 findings (was 3182). Backup pre-fix:
  `~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite.bak-pre-audit-fix-20260527-232133`.
- Cleanup + rerun chạy qua `docker exec audit-hq-mvp python -c "..."`.

### Workflow rerun checks trên tinsu (không full re-ingest)
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu

# Backup
cp ~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite \
   ~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite.bak-$(date +%Y%m%d-%H%M%S)

# Inline cleanup + rerun
docker exec audit-hq-mvp python -c "
from app.pipeline.run_checks import run_checks
pairs = [('DN_001',2023),('DN_001',2024),('DN_001',2025),
         ('DN_002',2024),('DN_002',2025),
         ('DN_003',2021),('DN_003',2022),('DN_003',2023),('DN_003',2024),('DN_003',2025),
         ('DN_004',2024)]
for code, year in pairs:
    s = run_checks(code, year)
    print(f'{code} {year}: {s.total} findings score={s.risk_score}')
"
```

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
- 432 pass. Conftest có autouse session fixture `create_all` trên default engine — không cần test_smoke chạy trước.
- Test mới sau audit fix vòng 1:
  - `tests/test_normalize_code.py` (21 parametrize)
  - `test_c1_2_ignores_mmtb_E13_for_dncx`
  - `test_c1_1_fires_info_when_diff_under_5pct` + `_under_floor`
  - `test_c1_4_fires_info_when_diff_under_1pct` + `_under_floor`
  - `test_range_band_and_semantics` (dynamic runner)
  - `test_finding_has_evidence_and_subject_type` (dynamic runner)

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
