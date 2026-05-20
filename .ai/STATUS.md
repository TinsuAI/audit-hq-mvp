# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 2 hoàn tất (2026-05-21). 4 adapters + Tầng 1 model + pipeline ingest chạy đầu cuối trên HONG_AN 2024 (99 NVL / 75 SP / 476 định mức / 246 dòng BCCT). 12 tests pass, ruff clean. Sẵn sàng tuần 3.

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). 5 tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`.
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

- **2026-05-21 (PM)** — Tuần 2: 4 adapters (M15/M15a/M16/BCCT) chuẩn hoá vào dataclass; models Tầng 1; Alembic initial migration; pipeline `discover + ingest` (CLI `python -m app.pipeline.ingest --company HONG_AN --year 2024`); 7 tests mới (4 adapters + 3 discover). Verify HONG_AN 2024 — Công ty Cổ phần Giầy Hồng An, MST 5400273360, ngành giày dép (SXXK loại hình E31/E62).
- **2026-05-21 (AM)** — Scaffold tuần 1: pyproject, Makefile, Dockerfile, docker-compose, FastAPI hello + login + overview placeholder, alembic init, 5 smoke tests pass.

## Next Steps

### Tuần 3 — Cài Nhóm 1 (6 check MVP)

1. `app/checks/c1_quantity.py` — implement C1.1, C1.2, C1.3, C1.4, C1.6, C1.7 (xem `../audit-hq/de-an-audit-hq.md` §4.1 Nhóm 1).
2. `app/checks/registry.py` — đăng ký mã check, mức độ 🔴🟡🔵, ngưỡng, mô tả ngắn.
3. Model `Finding` (Tầng 2): id, company_id, period_year, check_code, severity, subject_key (vd material_code), details (JSON), evidence_refs (FK list).
4. `app/pipeline/run_checks.py` — orchestrate: chạy hết check trên 1 (company, year) → ghi Findings.
5. UI: trang `/companies/<code>/findings` list findings group by check_code (basic, chưa polish).
6. Test: mock M15 + BCCT đơn giản (3-5 dòng) verify từng rule fire/no-fire.

### Sau tuần 3 (lộ trình §7 đề án)

- Tuần 3-4 — Cài Nhóm 1 + Nhóm 2 (9 check MVP).
- Tuần 5-6 — Cài Nhóm 3 + 4 + 5 + 6 MVP (7 check) + scoring.
- Tuần 7 — Anonymize 5 DN demo. Map: GROWATT→DN_001, KIM_LONG→DN_002, HONG_AN→DN_003, DO_THANH→DN_004, HONG_PHUC→DN_005 (sạch). HIEP_QUANG dự bị (giữ data full để regression test rule liên kỳ).
- Tuần 8 — Inject sai phạm chủ đích cho DN_001-004 theo §6.3 kịch bản.
- Tuần 9-10 — UI bảng tổng quan + trang chi tiết + xuất Excel + demo HQ.

## Notes

### Đề án là source of truth

- Catalog 49 kiểm tra, mức độ 🔴🟡🔵, ngưỡng, mô tả pháp lý — tất cả ở `../audit-hq/de-an-audit-hq.md`.
- Khi nghiệp vụ có thay đổi → update đề án trước, MVP follow.
- Demo plan chi tiết: `../audit-hq/.ai/sessions/2026-05-21-demo-plan.md`.

### Deploy demo

- Server: Tinsu VPS (`tinsu` Tailscale 100.84.189.87).
- URL: `audit-hq-demo.tinsu.ai` (Cloudflare Tunnel, basic-auth).
- Setup ingress: `audit-hq/deploy/scripts/add-ingress.py` (script ở repo đề án).
- Sẽ wire `make publish` ở tuần 9-10.

## Blockers

Không có. Sẵn sàng đi tuần 2.
