# STATUS — Audit-HQ MVP

> **Trạng thái (2026-06-14 — trang showcase công khai):**
> Phiên này dựng **trang giới thiệu tính năng công khai** tại `/showcase`, đã deploy.
> **`main` = `origin/main` = prod = `b7334f4`** (sạch, không ahead/behind, không uncommitted).
> Migration head **`d3e4f5a6b7c8`** (KHÔNG đổi phiên này). Test suite ~533 pass (không động vào).

## Current State

### Git / deploy
- **`main` = `origin/main` = `b7334f4`**, working tree sạch. Prod live `audit-hq-demo.tinsu.ai`
  đang chạy `b7334f4` (đã verify `/healthz`).
- Deploy = push `main` → CI "Test & Deploy to Tinsu" (self-hosted): test+lint → docker build →
  restart → `alembic upgrade head` + seed UOM → healthcheck. Watch: `gh run watch <id> --exit-status`.
- **LƯU Ý sửa note cũ:** STATUS trước ghi "chat redesign `444f5ed` chưa push" — SAI/đã cũ.
  `git fetch` đầu phiên cho thấy `444f5ed` + `b11cf4a` đã ở origin từ trước (đã deploy).

### Trang showcase (MỚI phiên này)
- **URL công khai:** **https://audit-hq-demo.tinsu.ai/showcase** — KHÔNG cần đăng nhập (để gửi mọi người).
- **Route:** `GET /showcase` trong `app/main.py` (không `require_user`) → `FileResponse` file tĩnh.
  Demo KHÔNG có auth ở edge (ingress qua Cloudflare tunnel, auth chỉ ở tầng app) → bỏ `require_user` = public.
- **File:** `app/static/showcase.html` (~1.3 MB, self-contained: CSS inline + ảnh base64 + lightbox JS).
  Sinh từ `.ai/features/2026-06-14-showcase/build_showcase.py` (nén PNG đã commit → JPEG → base64).
- **Phong cách:** ĐỒNG NHẤT với hệ thống — dùng token của `app/static/style.css` (nền sáng `#f6f7f9`,
  header navy `#1d3557` như app, card/button/badge hệ thống, banner "Dữ liệu mẫu" vàng). Sáng, không tối,
  không gradient/emoji lòe loẹt. Tiếng Việt đầy đủ, chuyên nghiệp.
- **Nội dung:** Trợ lý ảo (trọng tâm — 6 nhóm năng lực, KHÔNG nêu tên hàm/tool) · tiếp nhận dữ liệu (AI
  chẩn đoán file, chuẩn hoá ĐƠN VỊ TÍNH, tự nhận loại hình DN, magic-byte) · 16 kiểm tra + 4 tổ hợp ·
  chấm điểm minh bạch · truy nguồn · phân quyền + nhật ký · tài liệu.

### Phần còn lại của sản phẩm (carry, không đổi phiên này)
- Trợ lý AI redesign (trang `/chat`, tool-pill gọn, @mention) — đã deploy.
- Phân quyền theo DN (admin/officer), áp cho cả AI tool + `query_sql` scoped views — đã có.
- Nhật ký truy cập `/admin/audit`, rate-limit login, magic-byte upload — đã có.
- Stack: Python 3.12, FastAPI, SQLAlchemy+Alembic, SQLite (WAL). Dev port **8200**.

## Recent Changes (2026-06-14 — commits `06fe771`..`b7334f4`)
Xem chi tiết: session `2026-06-14-public-showcase-page.md` + proof `.ai/features/2026-06-14-showcase/`.
1. `06fe771` — tạo trang showcase + route public (bản đầu, theme tự chế tối màu).
2. `41cd604` — chụp lại ảnh retina/crop gọn/ẩn banner (sửa ảnh full-page bị li ti).
3. `627be6d` — **làm lại theo phản hồi user:** sáng + đồng bộ style hệ thống; AI trình bày theo
   năng lực (bỏ tên hàm); bỏ phần "Quản trị AI"; viết lại tiếng Việt đầy đủ.
4. `b7334f4` — **sửa overclaim:** "chuẩn hoá tên hàng hoá" KHÔNG có thật (chỉ trong đề án §5.3) →
   thay bằng "chuẩn hoá đơn vị tính" (thật, `app/checks/uom.py`).

## Next Steps (ưu tiên)
1. Chờ user duyệt trang showcase. Sửa tiếp (bố cục/câu chữ/ảnh) thì: sửa `TEMPLATE` trong
   `build_showcase.py` → chạy lại script → commit → push (CI tự deploy).
2. (Carry) Phân công DN cho officer trên prod (`/admin/users` → "Phân công DN") — thao tác tay.
3. (Carry) Combo +20 điểm tổ hợp — review logic (`app/checks/scoring.py:179`), user "quyết sau".
4. (Carry, polish) admin còn hiện text `code`; tên DN còn hậu tố `(Demo)`; quyết `ZZ_DEMO`.

## Blockers
- Không có. Lưu ý đĩa tinsu ~97% (theo dõi khi deploy lâu dài).

## Notes for Next AI Session

### Showcase — điểm cắm
- **Sửa nội dung/style:** chỉ sửa `TEMPLATE` (string) trong `.ai/features/2026-06-14-showcase/build_showcase.py`,
  rồi `.venv/bin/python .ai/features/2026-06-14-showcase/build_showcase.py` → ghi đè `app/static/showcase.html`.
  KHÔNG sửa tay file HTML đã sinh (sẽ bị ghi đè).
- **Chụp lại ảnh:** `PYTHONPATH=. .venv/bin/python .ai/features/2026-06-14-showcase/ui_smoke.py` (cần dev :8200).
  Seed admin `shot_show` + officer `shot_off` (gán DN_001) + cuộc chat, chụp retina 2× crop gọn ẩn banner,
  rồi xoá. **GOTCHA đã gặp:** mỗi vai PHẢI dùng `browser.new_context()` riêng — chung context = chung cookie,
  login sau ghi đè login trước → trang admin bị 404/từ chối.
- **SOURCES** trong build script chỉ giữ key ĐANG dùng trong template (placeholder no-op nếu thừa, nhưng để sạch).
  Ảnh chụp ở năm DN_003 = 2022 (điểm 148) để khoe bảng tính điểm bung ra.

### CHỐNG OVERCLAIM (quan trọng — user bắt lỗi phiên này)
- **"Chuẩn hoá tên hàng hoá" CHƯA implement** — chỉ trong đề án §5.3. Đối chiếu theo `material_code`, không theo tên.
  Cái CÓ thật: chuẩn hoá **đơn vị tính** (`app/checks/uom.py`, canonical+alias, `/admin/units`, dùng ở C3.3).
- Các claim "thông minh" KHÁC đều đã verify có code: AI ingest doctor `app/ai/ingest_doctor.py`;
  magic-byte `app/routes/companies.py:227`; tự nhận loại hình DN `app/checks/company_type.py`; guardrails AI.
- Bài học: **trước khi viết "tính năng X" lên tài liệu khách → grep code xác minh đã ship**, đừng tin đề án.

### Render / verify nhanh
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8200/showcase` (200, không redirect login).
- Chụp render để soi: Playwright goto `/showcase` full_page. Scratch ảnh → `.tmp-*` (gitignored).

### Môi trường / gotcha (carry)
- Dev :8200 hay chạy sẵn. `curl :8200/healthz` 200 = sống. Shell zsh (dòng `compdef` là noise, bỏ qua).
- DB local = mirror prod (DN_001..005). `convert` (ImageMagick) có sẵn — dùng để nén ảnh showcase.
- Lint scope CI = `app tests scripts` (Makefile); `.ai/` KHÔNG lint (E501 trong build script là bình thường).
- Backup DB trước migrate bằng `sqlite3 .backup` (WAL-safe), KHÔNG `cp` đơn lẻ.

### Văn phong (giữ nguyên)
- Tiếng Việt full accents, tone formal. "bài kiểm tra", "kịch khung", "quy mô dữ liệu".
- Disclaimer: "chỉ số rủi ro dữ liệu BCQT… KHÔNG phải đánh giá tuân thủ theo TT 81/2019/TT-BTC".
