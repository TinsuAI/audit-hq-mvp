# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 3 hoàn tất (2026-05-21). 6 check Nhóm 1 MVP cài đặt đầu cuối (C1.1 → C1.7 trừ C1.5 W.I.P). UI bảng tổng quan + trang chi tiết DN render được. Pipeline `run_checks` chạy trên HONG_AN 2024 → 0 findings (DN sạch). 31 tests pass (24 unit + 7 integration), ruff clean.

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). 5 tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`.
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

- **2026-05-21 (tối)** — Tuần 3: 6 check Nhóm 1 MVP (C1.1-C1.4, C1.6, C1.7) + registry với severity scale (🔴🟡🔵). Finding model (Tầng 2) với evidence_refs JSON. `detect_company_type` heuristic (SXXK/DNCX/Gia công từ mã loại hình BCCT). Pipeline `run_checks` CLI idempotent. UI: `/companies` (bảng tổng quan), `/companies/<code>?year=YYYY` (chi tiết findings group by check_code, collapsible, badge severity). 19 unit test mới cho check + scale + company_type detection.
- **2026-05-21 (chiều)** — Tuần 2: 4 adapters (M15/M15a/M16/BCCT) chuẩn hoá vào dataclass; models Tầng 1; Alembic initial migration; pipeline `discover + ingest` (CLI `python -m app.pipeline.ingest --company HONG_AN --year 2024`); 7 tests mới (4 adapters + 3 discover). Verify HONG_AN 2024 — Công ty Cổ phần Giầy Hồng An, MST 5400273360, ngành giày dép (SXXK loại hình E31/E62).
- **2026-05-21 (sáng)** — Scaffold tuần 1: pyproject, Makefile, Dockerfile, docker-compose, FastAPI hello + login + overview placeholder, alembic init, 5 smoke tests pass.

## Insight nghiệp vụ (tuần 3)

HONG_AN 2024 chạy 6 check MVP → 0 findings. Dữ liệu DN này khớp số học rất tốt:
- M15.import_qty == Σ BCCT[E31] theo từng mã (Top 8 NVL kiểm tra: lệch 0.0%)
- 44/44 mã NVL trong BCCT đều có trong M15
- Không có chuyển MĐSD A42

Đây là DN "đẹp" cho dataset baseline. Sẽ cần inject sai phạm chủ đích ở tuần 8 để demo (theo plan §6.3).

## Next Steps

### Tuần 4 — Cài Nhóm 2 (3 check MVP) + đánh dấu

1. `app/checks/c2_balance.py`:
   - **C2.1** — Mất cân bằng phương trình M15: `tồn_cuối ≠ tồn_đầu + nhập − tái_xuất − chuyển_MĐSD − xuất_SX − xuất_khác`. Severity critical (chênh khác 0, tolerance ±0.01). Trường hợp đặc biệt: `tồn_đầu = 0` nhưng `tồn_cuối > nhập_trong_kỳ` (tồn ảo).
   - **C2.2** — Mất cân bằng M15a: `tồn_cuối ≠ tồn_đầu + nhập_kho − chuyển_MĐSD − xuất_khẩu − xuất_khác`.
   - **C2.3** — Tồn cuối NVL âm (M15): bất kỳ mã nào `closing_qty < 0`.
2. Cơ chế đánh dấu cán bộ (xác nhận / loại trừ / ghi chú) — model `Finding.status` đã có (`new|confirmed|rejected|noted`). Thêm route POST `/findings/<id>/status` + form trên trang chi tiết.
3. Test fixtures: 6 unit test (3 fire + 3 no-fire cho 3 rule).

### Sau tuần 4 (lộ trình §7 đề án)

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
