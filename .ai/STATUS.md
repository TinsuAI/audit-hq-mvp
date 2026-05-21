# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 4 hoàn tất (2026-05-21). Tổng 9/16 MVP check đã cài đặt (Nhóm 1 + 2). Cơ chế đánh dấu finding (`new|confirmed|rejected|noted` + notes) chạy đầu cuối qua HTTP. 43 tests pass, ruff clean. Sẵn sàng tuần 5 (Nhóm 3 + 4 + 5 + 6 MVP, 7 check còn lại).

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). 5 tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`.
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

- **2026-05-21 (khuya)** — Tuần 4: 3 check Nhóm 2 (C2.1 cân bằng M15, C2.2 cân bằng M15a, C2.3 tồn cuối NVL âm). C2.1 phát hiện kèm pattern "tồn ảo" (opening=0, closing>import) ghi vào details. Cơ chế đánh dấu finding: POST `/findings/{id}/status` với 4 trạng thái (new/confirmed/rejected/noted) + ghi chú; UI có inline form trên mỗi row, anchor scroll về row vừa update. +12 unit test (9 C2.x + 3 status route).
- **2026-05-21 (tối)** — Tuần 3: 6 check Nhóm 1 MVP (C1.1-C1.4, C1.6, C1.7) + registry với severity scale (🔴🟡🔵). Finding model (Tầng 2) với evidence_refs JSON. `detect_company_type` heuristic (SXXK/DNCX/Gia công từ mã loại hình BCCT). Pipeline `run_checks` CLI idempotent. UI: `/companies` (bảng tổng quan), `/companies/<code>?year=YYYY` (chi tiết findings group by check_code, collapsible, badge severity). 19 unit test mới cho check + scale + company_type detection.
- **2026-05-21 (chiều)** — Tuần 2: 4 adapters (M15/M15a/M16/BCCT) chuẩn hoá vào dataclass; models Tầng 1; Alembic initial migration; pipeline `discover + ingest` (CLI `python -m app.pipeline.ingest --company HONG_AN --year 2024`); 7 tests mới (4 adapters + 3 discover). Verify HONG_AN 2024 — Công ty Cổ phần Giầy Hồng An, MST 5400273360, ngành giày dép (SXXK loại hình E31/E62).
- **2026-05-21 (sáng)** — Scaffold tuần 1: pyproject, Makefile, Dockerfile, docker-compose, FastAPI hello + login + overview placeholder, alembic init, 5 smoke tests pass.

## Insight nghiệp vụ (tuần 3 + 4)

HONG_AN 2024 chạy 9 check MVP → **0 findings**. Dữ liệu DN này khớp số học rất tốt:
- M15.import_qty == Σ BCCT[E31] theo từng mã (Top 8 NVL kiểm tra: lệch 0.0%)
- Phương trình M15 cân hoàn hảo (diff = 0.0000 mọi mã)
- 0 mã NVL có tồn cuối âm
- 44/44 mã NVL trong BCCT đều có trong M15
- Không có chuyển MĐSD A42

Đây là DN "đẹp" cho dataset baseline. Sẽ cần inject sai phạm chủ đích ở tuần 8 để demo (theo plan §6.3). Kế toán + XNK của Giầy Hồng An làm rất bài bản — tốt cho regression test (đảm bảo rule không false-positive), nhưng không tốt để demo "kịch tính".

## Next Steps

### Tuần 5 — Cài Nhóm 3 + 4 + 5 + 6 MVP (7 check còn lại)

Lộ trình §7.3 đề án: gom MVP của 4 nhóm vào 1 tuần.

1. `app/checks/c3_classify.py` — Phân loại hàng hoá (3 check):
   - **C3.1** — Cùng mã vật tư khai nhiều loại hình mâu thuẫn (NVL E11/E31/E21 + MMTB E13).
   - **C3.2** — Mã HS không nhất quán trong kỳ (cùng `item_code` có ≥2 HS khác). Scale: khác phân nhóm 6 số (Thông tin) · khác nhóm 4 số (Cảnh báo) · khác chương 2 số (Nghiêm trọng).
   - **C3.3** — Đơn vị tính không nhất quán (M15 vs BCCT cùng mã).
2. `app/checks/c4_norm.py` — Định mức M16 (2 MVP):
   - **C4.1** — NVL trong M16 không có nhập + không có tồn đầu.
   - **C4.3** — Σ(định_mức × xuất_khẩu_M15a) > xuất_sản_xuất_M15 (Cảnh báo >5%, Nghiêm trọng >20%).
3. `app/checks/c5_trace.py` — Truy nguồn NVL (1 MVP):
   - **C5.1** — NVL có `xuất_sản_xuất > 0` nhưng nhập_trong_kỳ = 0 và opening = 0.
4. `app/checks/c6_cross_period.py` — Liên kỳ (1 MVP):
   - **C6.1** — Tồn đầu kỳ N ≠ tồn cuối kỳ N-1 cho từng NVL (cần ≥2 năm dữ liệu).
5. Cần ingest thêm HONG_AN 2023 để chạy C6.1.

### Sau tuần 5 (lộ trình §7 đề án)

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
