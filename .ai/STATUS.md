# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 1 đang khởi tạo. Repo vừa scaffold (2026-05-21). Khung FastAPI + basic-auth chạy được, smoke test pass. Chưa có adapter, chưa có check.

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite cho cả dev + demo (theo quyết định 2026-05-21).
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

- **2026-05-21** — Scaffold tuần 1: pyproject, Makefile, Dockerfile, docker-compose, FastAPI hello + login + overview placeholder, alembic init, 5 smoke tests pass.

## Next Steps

### Tuần 2 — Adapters đọc Excel (mục tiêu)

1. `app/adapters/m15.py` — đọc Mẫu 15 NVL (cấu trúc cột: mã NVL, đơn vị, tồn đầu, nhập, xuất sản xuất, xuất tái xuất, chuyển mục đích sử dụng, xuất khác, tồn cuối).
2. `app/adapters/m15a.py` — Mẫu 15a thành phẩm (tồn đầu, nhập kho, xuất khẩu, chuyển mục đích sử dụng, xuất khác, tồn cuối).
3. `app/adapters/m16.py` — Mẫu 16 định mức (mã SP, mã NVL, định mức, đơn vị).
4. `app/adapters/bcct.py` — Báo cáo hàng chi tiết NK/XK từ ECUS (số tờ khai, ngày, mã loại hình, mã NVL/SP, số lượng, đơn vị, mã HS, NCC).
5. Pilot dataset: **HONG_AN 2024** (đầy đủ nhất).
6. Models + migration (Alembic autogenerate).
7. Pipeline ingest: command `python -m app.pipeline.ingest --company HONG_AN --year 2024 --path data/HONG_AN/2024/`.
8. Smoke test: load 1 năm vào SQLite, query theo mã NVL ra số dòng kỳ vọng.

### Sau tuần 2 (lộ trình §7 đề án)

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
