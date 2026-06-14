# Session 2026-06-14 — Slug URL có nghĩa cho DN

**Commit:** `398f546 → 5eef7c5` (3 commit) trên `main`, đã push + deploy live `build_sha=5eef7c5`.
**Test:** 523 pass, ruff sạch. **Migration head:** `d3e4f5a6b7c8`.

## Bối cảnh / yêu cầu

User: trang DN đang hiển thị **mã DN tự sinh** (`DN_001`, `DN_002`) — vô nghĩa. Yêu cầu:
1. Hiển thị **tên** thay mã.
2. **URL slug** liên quan đến công ty (vd `dien-tu-phuong-dong`) thay `DN_001`.
3. "cần chạy backfill hết lại".

## What Was Done

### Mô hình định danh tách đôi (slug ⟂ code)
- **`code`** (DN_xxx) giữ nguyên làm khoá lưu trữ NỘI BỘ: thư mục `data/{code}/…`, `stored_path`,
  khoá lớp AI (`company_code`, view `v_*`, prompt), job payload, access log, CLI `--company`. KHÔNG hiển thị.
- **`slug`** mới: định danh URL + hiển thị, sinh từ tên.

### Thay đổi cụ thể
- `app/slugs.py` (mới): `slugify_name()` (fold dấu tiếng Việt, đ→d, bỏ ngoặc "(Demo)", bỏ tiền tố pháp lý
  "Công ty TNHH/Cổ phần…") + `unique_slug()` (chống trùng, nối `-2`).
- `app/models/company.py`: cột `slug` (String 64, unique, index, nullable).
- Migration `d3e4f5a6b7c8`: add column + unique index **TRỰC TIẾP** (`op.add_column`/`op.create_index`,
  KHÔNG `batch_alter_table`) + backfill slug cho mọi DN trong cùng migration (chạy tự động khi deploy).
- `app/scoping.py`: `get_company_or_404(db, ident, user)` resolve **slug HOẶC code** (ưu tiên slug).
- `app/routes/companies.py`: param URL nay mang slug; mọi thao tác storage/AI/job/log/export đổi sang
  `company.code`. `create_company` sinh slug; `update_company` KHÔNG đổi slug (cố định). Redirect/filename
  dùng `slug or code`.
- Templates (list, detail, data, documents, upload, preview, edit, item, finding): hiển thị `name or code`,
  href `slug or code`. List: tên là link chính (`.dn-name-link`), bỏ cột mã. Edit form: hiện slug (URL) +
  mã lưu trữ (code) read-only. Subtitle bỏ "Mã: DN_xxx", thay bằng MST/ngành.
- `app/static/style.css`: `.dn-name-link`.

### Kiểm chứng
- Backfill local: `dien-tu-phuong-dong / co-khi-tien-phong / may-mac-hoa-sen / hoa-chat-nam-tien /
  hoa-sung / demo-tai-lieu`.
- Render DB thật qua user tạm `shot_review` (TestClient, DB thật): list ra link slug + tên, KHÔNG còn
  "DN_001"; `/companies/dien-tu-phuong-dong` → 200, h1 = tên; `/companies/DN_001` (legacy) → 200 (fallback).
- Deploy: CI test+deploy xanh; demo healthz `build_sha=5eef7c5`; entrypoint `set -euo pipefail` chạy
  `alembic upgrade head` trước uvicorn → healthcheck xanh ⇒ migration + backfill đã áp prod.

## Decisions Made

1. **Thêm `slug`, GIỮ `code` (thay vì đổi code→slug một định danh).** User chọn (AskUserQuestion).
   Lý do: phương án 1-định-danh phải `mv` thư mục raw-data trên volume prod + sửa `stored_path` → rủi ro
   dữ liệu cao. Tách đôi đạt 100% yêu cầu UI/URL với rủi ro ~0 (không đụng file prod).
2. **Resolver slug-or-code + template href `slug or code`.** Để link nội bộ cũ (jobs/log/AI dùng DN_xxx)
   không gãy, và DN chưa có slug (test fixtures, edge) vẫn ra URL hợp lệ. Đây là củng cố thật, không phải lách test.
3. **Slug cố định khi sửa tên.** Tránh gãy bookmark/link khi admin đổi tên DN.
4. **Migration ADD COLUMN trực tiếp, không batch recreate.** `companies` bị nhiều FK trỏ tới
   (user_companies/data_files/findings/scores) → batch recreate (drop+rename) sẽ gãy FK + lock server đang chạy.

## What Didn't Work / Tránh lặp lại

- `make dev` ban đầu fail "Address already in use" — server :8200 đã chạy sẵn (`--reload`). Không cần bật lại;
  chỉ verify healthz.
- `ruff check app migrations` báo 24 lỗi → là ở **migration cũ**; lint scope chuẩn (Makefile) = `app tests
  scripts`. File migration mới tự sạch.
- Test ban đầu fail (scoping/companies_list/item_traceability) vì assert URL/chuỗi theo `code` cũ
  (`/companies/DN_001`, text "DN_001"). Fix bằng template `slug or code` → fixtures không-slug fallback về
  code, test xanh lại mà KHÔNG phải nới lỏng assertion bảo mật của test scoping.

## Open Items

- Trang admin (`admin_user_scope.html`, `admin_checks_new.html`) vẫn hiển thị `code` text. `admin_checks_new`
  option `value=code` BẮT BUỘC giữ (backend dùng làm company_code); chỉ phần text có thể đổi sang tên nếu muốn.
- Tên hiển thị còn hậu tố `(Demo)` (đúng demo-mode hiện tại) — user có thể yêu cầu bỏ.
- Backlog cũ còn nguyên: phân công DN officer trên prod; review logic combo +20 (`scoring.py:179`).
