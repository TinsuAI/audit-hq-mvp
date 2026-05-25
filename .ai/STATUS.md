# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-25, cuối session self-service):** Live demo `https://audit-hq-demo.tinsu.ai` đang chạy build `8f7c394` (chưa deploy thay đổi session này). Local dev (`http://127.0.0.1:8200`) đã có 3 luồng self-service: **tạo DN mới**, **upload 4 file BCQT**, **chạy lại kiểm tra**. End-to-end verify với HONG_AN 2024 thật → 1 finding C3.2 / score 3 (khớp baseline). 113 tests pass, ruff clean.

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). Tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`, `findings`, `uom_canonical`, `uom_aliases`.
- Auth: cookie session, default `admin/admin`. Env vars `AUTH_USER`/`AUTH_PASSWORD`/`SESSION_SECRET`.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN. DN mới tạo qua UI sẽ ghi vào cùng folder này theo path `<code>/<year>/{BCQT,DINH_MUC,HANG_CHI_TIET}/`.
- **4 DN demo trên prod**: DN_001 GROWATT (Điện Tử Phương Đông), DN_002 KIM_LONG (Cơ Khí Tiên Phong), DN_003 HONG_AN (May Mặc Hoa Sen), DN_004 DO_THANH (Hoá Chất Nam Tiến).
- Demo banner amber vẫn fire trên mọi page. DN mới tạo qua UI bị ép hậu tố `(Demo)` vào name.
- Runner self-hosted `tinsu-runner-audit-hq` online qua watchdog + crontab `@reboot`.
- Backup DB cũ untracked: `audit_hq.sqlite.bak-20260525-120743` (18M). Xoá khi tiện.

## Recent Changes

- **2026-05-25 (cuối)** — Self-service: tạo DN + upload + chạy lại kiểm tra qua UI.
  - 5 routes mới trong `app/routes/companies.py`: `GET /companies/new`, `POST /companies`, `GET/POST /companies/{code}/upload`, `POST /companies/{code}/run-checks`. Đăng ký TRƯỚC `/companies/{code}` để `new` không bị catch.
  - Templates mới: `new_company.html` (form 4 trường), `upload_data.html` (form 4 slot + year).
  - Cập nhật: `companies_list.html` (nút "+ Thêm DN mới"), `company_detail.html` (nút "📥 Upload dữ liệu" + "🔄 Chạy lại kiểm tra"; empty-state CTA thay vì hint CLI).
  - Helper `_save_upload`: stream 1MB chunk, limit 100MB, wipe sibling cũ trong subdir để discover không pick outdated.
  - Pyproject: thêm `fastapi.File` vào `extend-immutable-calls`.
  - Verify E2E qua httpx: 4 file HONG_AN 2024 → 99 M15 / 75 M15a / 476 norm / 246 BCCT / 1 finding / score 3 — khớp baseline. Tổng upload+ingest+run 0.7s.
  - Chi tiết: `.ai/sessions/2026-05-25-user-create-upload-rerun.md`.
- **2026-05-25 (sáng)** — MVP demo polish: filter 4 DN whitelist, realistic names "(Demo)", banner amber, UX bảng curated. Build `cbc4c8f` live. Chi tiết: `.ai/sessions/2026-05-25-filter-4dn-ux-rename-deploy.md`.
- **2026-05-21 (cuối)** — MVP build xong 10 tuần + UOM admin + deploy. Build `fd263f6` → `cbc4c8f`. Demo public `audit-hq-demo.tinsu.ai` (admin/admin). Chi tiết: `.ai/sessions/2026-05-21-mvp-build-deploy.md`.

## Next Steps

### Ưu tiên ngắn hạn

1. **Test thử bằng tay**: vào `http://127.0.0.1:8200` (đang chạy ở port 8200), login admin/admin, vào `/companies` → "+ Thêm DN mới" → upload 4 file → xem findings. Pipeline đã verify qua API, nhưng test bằng tay để bắt UX bug.
2. **Quyết định deploy hay không**: commit + push main sẽ trigger runner tự build/deploy. Self-service routes không có guard gì thêm so với local — nếu deploy live, ai vào URL admin/admin cũng tạo được DN mới ghi file lên server thật. Cân nhắc đổi password trước.
3. **(Optional) Thêm route delete DN**: hiện chỉ có create. Nếu test sai phải xoá tay qua DB + filesystem.

### Trước demo HQ

1. **Tổng duyệt nội bộ Trọng Tín + Tinsu** — chạy kịch bản 5 phút §6.3.
2. **Convert runner sang systemd** (hiện watchdog + cron, không phải systemd thật).
3. **Generate password mạnh** thay admin/admin.

### Sau demo HQ (§7.7 đề án)

- Thí điểm Chi Cục Hải Quan Khu vực IV với dữ liệu thực.
- Cài 14 W.I.P còn lại (C1.5, C2.4, C4.2/4-8, C5.2-3, C6.2-5).
- Mở Giai đoạn II (Nhóm 8-12, 16 check cần dữ liệu bổ sung).
- Tích hợp VNACCS trực tiếp thay vì Excel.

## Notes for Next AI Session

### Dev server đang chạy

- Port `8200` (port 8000 conflict với `BCQT-System` local). Log: `/tmp/audit-hq-dev.log`. Start lại: `nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`.
- Process PID có thể xem bằng `lsof -i :8200`. Reload tự khi sửa `app/**/*.py` hoặc template.

### Self-service flow vừa thêm

- File: chỉ sửa `app/routes/companies.py` (thêm 5 routes + helper, không tách module mới), `app/templates/*.html`, `pyproject.toml`. Không động vào pipeline/models/checks.
- Demo posture: vẫn ép `(Demo)` suffix + giữ banner. Nếu chuyển sang prod thật, sửa hằng `DEMO_SUFFIX` ở `companies.py` hoặc gắn env-var toggle.
- File size limit 100MB ở `MAX_UPLOAD_BYTES` (companies.py:67). BCCT đa kỳ có thể vượt.
- Filename stem cố định khi save (`M15_NVL_<year>.xlsx`, v.v.) — không preserve tên gốc. Đổi nếu cần audit trail bằng tên gốc.

### Đề án vẫn là source of truth

- Catalog 49 kiểm tra ở `../audit-hq/de-an-audit-hq.md`. Mọi thay đổi nghiệp vụ phải update đề án TRƯỚC, MVP follow.
- Demo plan chi tiết: `../audit-hq/.ai/sessions/2026-05-21-demo-plan.md`.

### Quy trình deploy

1. Edit code + commit + push main → GitHub Actions tự trigger
2. Job `test`: uv venv, pytest, ruff
3. Job `deploy` (chỉ chạy khi test pass): docker build với BUILD_SHA/TIME, restart container, wait healthcheck
4. Footer ở UI cập nhật phiên bản tự động: `v{VERSION} · build {SHA} · {TIME}`
5. Local manual: `make deploy`.

### Constraint sau anonymize

DB hiện ở **mode demo** (Company.code = DN_xxx). DN mới tạo qua UI sẽ có code do user nhập (validate regex `^[A-Z][A-Z0-9_-]{1,30}$`).

- **Không re-ingest filesystem path "HONG_AN"** trừ khi `python -m scripts.restore` trước.
- `python -m app.pipeline.run_checks --company DN_003 --year 2024` vẫn hoạt động bình thường.
- `python -m app.pipeline.run_all` nếu chạy lại sẽ tạo Company mới với code "HONG_AN" → duplicate. Cần restore + run_all + anonymize lại.

### Hạ tầng kỹ thuật

- Server: `tinsu` (Tailscale 100.84.189.87). WSL `ssh` lỗi → dùng `ssh.exe -F …` (xem memory `tinsu-server`).
- Cloudflare Tunnel `audit-hq-demo.tinsu.ai` → port 8200 (port 8000 conflict erpnext-frontend).
- Runner watchdog `runner-loop.sh` + cron `@reboot`. KHÔNG dùng systemd vì cần sudo password.

## Blockers

Không có. Sẵn sàng deploy nếu user duyệt; hoặc tiếp tục thêm tính năng (delete DN, edit DN, UOM tự seed cho DN mới).
