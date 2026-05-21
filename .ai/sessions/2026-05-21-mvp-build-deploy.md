# Session 2026-05-21 — MVP build tuần 1-10 + deploy + UOM system

Session marathon từ "scaffold tuần 1" tới "live deploy + UOM admin UI". 15 commits, 113 tests, 1 demo public.

## What Was Done

**Tuần 1-2 — Scaffold + adapters Excel**
- Khởi tạo `audit-hq-mvp` repo, FastAPI + basic-auth + SQLite + Alembic + Docker scaffold.
- 4 adapters (M15/M15a/M16/BCCT) chuẩn hoá Excel TT39 vào dataclass, hỗ trợ cả format TT39 và DINHMUC fallback cho M16, M16 forward-fill parent-child.
- ORM models Tầng 1, Alembic initial migration, pipeline `discover + ingest`.
- HONG_AN 2024 load thành công: 99 NVL · 75 SP · 476 norm · 246 BCCT (E31/E62 SXXK).

**Tuần 3-6 — 16 MVP check + scoring + combo**
- Nhóm 1 (C1.1-1.4, 1.6, 1.7): 6 check số lượng nhập/xuất với severity scale.
- Nhóm 2 (C2.1-2.3): cân bằng phương trình + tồn âm + tồn ảo edge case.
- Cơ chế đánh dấu finding qua UI (status pill 4 trạng thái + ghi chú).
- Nhóm 3-6: 7 check còn lại (HS scale chương/nhóm/phân nhóm, định mức M16, truy nguồn, liên kỳ).
- Tuần 6: scoring (10/3/1 + combo +20) + 4 combo signature (FORGED_NORM, UNDECLARED_SOURCE, ACCOUNTING_INCONSISTENT, HS_GAMING) + CLI `run_all` orchestrate ingest + check toàn bộ 6 DN × 11 năm.

**Tuần 7-8 — Anonymize + inject demo data**
- `scripts/anonymize.py` 6 DN → DN_001-006 (mapping cố định), 96 NCC → NCC_xxx, MST 10 số SHA256(original), idempotent + revertable via mapping file.
- `scripts/inject_findings.py` 4 sai phạm chủ đích DN_003 2024 (DG/KHUY/DD-2/HDG) → từ 1 finding lên 12 + combo `COMBO_ACCOUNTING_INCONSISTENT`. `clean_dn_005()` bulk reject 201 critical → DN_005 score 1290 → 3 (mô phỏng cán bộ review).
- Ranking final: DN_003=7896, DN_002=2020, ..., DN_005=3 — đúng tinh thần §6.3.

**Tuần 9 — UI polish + Excel export**
- `/findings/{id}` chi tiết với chứng cứ Tầng 1 resolved live (hỗ trợ `field__in` filter syntax).
- `/companies/{code}/data` viewer M15/M15a/M16/BCCT với tabs + filter + pagination.
- `/companies/{code}/export` xuất .xlsx 7 sheet (Tổng quan + Phát hiện severity-color + 4 chứng cứ + Pháp lý) bằng xlsxwriter.

**UI redesign Modern Government** (4 iterations self-screenshot Playwright)
- v1 → v4 trên `/companies`: từ rowspan layout sparse → 1-DN-1-row với year chips inline severity dot + rank-badge circle navy filled.
- Design system tokens (color/spacing/typo/radius/shadow), font Inter + JetBrains Mono qua Google Fonts (chú ý wght=800 phải thêm vào URL).
- Install `fonts-noto-color-emoji` Ubuntu để emoji render đúng (Inter không có glyph).
- Print-friendly `@media print`.

**Tuần 10 — Versioning + CI/CD + deploy live**
- `VERSION` file root + `app/version.py` (env override > git local > fallback). Footer `v{V} · build {SHA} · {ISO time}`. `/healthz` trả full metadata.
- Dockerfile production: ARG BUILD_SHA/TIME, locale C.UTF-8, TZ Asia/Ho_Chi_Minh, entrypoint chạy alembic + seed_uom.
- docker-compose: bind `127.0.0.1:${HOST_PORT:-8200}:8000`, volume `${DB_DATA_PATH}`, healthcheck 30s.
- GitHub Actions self-hosted runner Tinsu (label `tinsu-prod`) — workflow test (uv venv + pytest + ruff) → deploy (docker build + restart + wait healthcheck + show version).
- Cloudflare Tunnel ingress `audit-hq-demo.tinsu.ai` → port 8200 (port 8000 đã có erpnext-frontend) via API. DNS CNAME add qua `cloudflared tunnel route dns`.
- DB persistent `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite` (18MB scp từ local đã anonymize + inject).

**UOM system + finding 782 fix**
- Tham khảo data-hub 2-layer: `uom_canonical` (code/family/base_factor) + `uom_aliases` (raw → canonical). Bỏ client_overrides của data-hub vì audit-hq không cần.
- 25 canonical + 129 alias seed (`scripts/seed_uom.py`). Helper `resolve_canonical/get_family/compare` với cache in-memory.
- C3.3 severity ladder: EQUIVALENT skip · SAME_FAMILY → 🔵 Info · DIFFERENT → 🔴 Critical.
- Compound separator (`Cái/Chiếc` = PCE/PCE → equiv): `resolve_canonical` split text `[/,;|]+`, lenient với unknown parts.
- Admin UI `/admin/units` (route `app/routes/admin.py` + template) — list grouped by family, alias chips, form thêm alias + canonical mới, cache invalidate sau sửa.
- Live re-run C3.3 sau fix: từ 250+ false-positive → 4 real (3 INFO + 1 CRITICAL trên DN_003 2025).

## Decisions Made

| # | Quyết định | Lý do |
|---|---|---|
| 1 | Repo MVP riêng `audit-hq-mvp` (không monorepo audit-hq) | audit-hq là docs only (CLAUDE.md cấm .py); MVP có code khác hẳn |
| 2 | SQLite cho cả dev + demo | Đơn giản, 1 file, đề án §5.2 cho phép; demo 5 DN không cần Postgres |
| 3 | Basic-auth cookie (không OAuth) | Demo 1 URL share cán bộ HQ, không multi-tenant |
| 4 | Approach A (dữ liệu thực anonymize) | Tiết kiệm tuần 7-8 sim thuần, demo trung thực hơn |
| 5 | Adapter trả dataclass thuần (không Pydantic/DataFrame) | Type-safe, dễ test, swap pandas dễ |
| 6 | Pipeline idempotent (delete + insert) | Dev re-run liên tục, audit qua git/snapshot |
| 7 | M16 hỗ trợ 2 format song song | DN nộp cả TT39 (BCTT39 sheet) lẫn DINHMUC (Sheet1) |
| 8 | Severity = string column, không enum DB | SQLite không ENUM native; portable |
| 9 | Detect company_type bằng count BCCT | Auto, HQ không khai báo; safe per §4.0 |
| 10 | Evidence_refs là JSON filter, không FK | 1 finding trỏ nhiều rows; tránh orphan khi re-ingest |
| 11 | Symlink data/ (không duplicate) | 500MB raw, source of truth duy nhất |
| 12 | Score string "low/mid/high" 3-tier | Đề án §6.3 mô tả ranking, không cần tier nhiều hơn |
| 13 | Inject chỉ DN_003 (không 4 DN khác) | Data thực HONG_AN đẹp nhất cho demo; DN khác đã có findings tự nhiên do thiếu BCCT |
| 14 | DN_005 bulk reject (không inject sạch) | Sạch thực sự phải có quá ít data — không demo được; reject 201 critical mô phỏng cán bộ review |
| 15 | Modern Government design (không SaaS dashboard) | Audit-HQ tool cho cơ quan nhà nước, authority tone |
| 16 | CSS tokens thuần (không Tailwind/framework) | Control tốt, không CDN dep, light |
| 17 | uv venv (không python3 -m venv) trong CI | Ubuntu 24.04 / Python 3.13 chưa có python3-venv default |
| 18 | Port 8200 thay vì 8000 trên Tinsu | Port 8000 đã có erpnext-frontend |
| 19 | UOM cache in-memory invalidate-on-write (không Redis) | Single instance, write hiếm |
| 20 | UOM compound separator lenient (ignore unknown parts) | Trade-off less false-positive vs precision |

## What Didn't Work

- **`python -m venv .venv` trên Tinsu**: Ubuntu chưa có `python3.13-venv` package, cần sudo apt install. Switch sang `uv venv` không cần.
- **`python3 -m scripts.anonymize` write mapping JSON vào `data/`**: `data/` là symlink → ghi vào `audit-hq/data/raw/` (gitignored ở repo audit-hq nhưng làm bẩn). Fix: lưu vào `db-data/` (gitignored ở repo audit-hq-mvp).
- **Port 8000 cho container**: conflict erpnext-frontend trên Tinsu. Fix: port 8200.
- **`font-weight: 800` rank-top**: Inter Google Fonts URL chỉ load 400-700, fallback về 700 → ranks #1-#3 trông giống ranks #4+. Fix: rank-badge circle với background color tier (navy filled/100/50).
- **Inter từ Google Fonts không có emoji glyphs**: `□ admin`, `□ Cách tính điểm`. Fix: install `fonts-noto-color-emoji` Ubuntu + thêm vào font-family fallback.
- **`session.scalars(select(UomCanonical.code)).c.code`**: scalar trả string, không có `.code` attribute. Fix: `set(session.scalars(...).all())` trực tiếp.
- **C3.3 với `Cái/Chiếc` compound**: alias dict lookup direct fail. Fix: `_SEP_RE` split + check từng phần.
- **`import app.models` sau `from app.main import app`**: rebind biến `app` → module thay vì FastAPI instance → `TestClient(app)` lỗi. Fix: reorder import.

## Open Items

1. **Runner persistence**: hiện nohup, không systemd. Cần sudo password Tinsu để convert systemd service.
2. **Auth credentials prod**: vẫn admin/admin. Cần gen random + set GitHub secrets `AUTH_USER`/`AUTH_PASSWORD`/`SESSION_SECRET`.
3. **C3.3 còn 4 real findings DN_003 2025** — chờ cán bộ review (3 INFO PR/PCE mix + 1 CRITICAL UNA vs Chai/Lọ/Tuýp).
4. **DN_002/004/006 score cao do thiếu BCCT** — parser KIM_LONG/DO_THANH/HIEP_QUANG file M15 fail, C4.1 fire nhiều false. Khi demo HQ cần note "DN_005 sạch là minh chứng đúng pattern; DN khác score cao do dataset không đầy đủ".
5. **Self-screenshot tooling** (`playwright + chromium-headless-shell` đã install trong .venv): script `/tmp/screenshot.py` chưa wrap thành `make screenshots`. Có thể đáng làm sau.
6. **Test warnings SAWarning** Identity map already had identity: cosmetic, không fail tests; có thể dùng `session.expunge_all()` trong inject test fixtures sau.
