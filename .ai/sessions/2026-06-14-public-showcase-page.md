# Session 2026-06-14 — Trang showcase tính năng công khai

## What Was Done

Dựng một **trang web giới thiệu đầy đủ tính năng** của Audit-HQ, nhấn mạnh các tính năng
thông minh / AI / trợ lý, để gửi công khai cho mọi người. Đầu ra: một file HTML self-contained,
deploy chung host với demo, có URL công khai.

- **URL:** https://audit-hq-demo.tinsu.ai/showcase (KHÔNG cần đăng nhập).
- **Route:** `GET /showcase` trong `app/main.py` — không `require_user`, trả `FileResponse`
  `app/static/showcase.html`. Xác nhận demo không có auth ở edge (Cloudflare tunnel; auth chỉ tầng
  app), nên bỏ `require_user` là đủ để public. Các route khác giữ nguyên (đã verify `/companies` vẫn
  303 về `/login`).
- **File HTML:** `app/static/showcase.html` (~1.3 MB) — self-contained: CSS inline, ảnh nhúng base64,
  lightbox JS nhỏ. Sinh tự động từ `.ai/features/2026-06-14-showcase/build_showcase.py`.
- **Proof + reproducible:** `.ai/features/2026-06-14-showcase/` gồm `brief.md`, `build_showcase.py`
  (nén PNG đã commit → JPEG qua ImageMagick `convert` → base64 → template), `ui_smoke.py` (chụp ảnh),
  `screenshots/` (PNG nguồn, retina).
- **Ảnh:** chụp bằng `ui_smoke.py` — seed admin tạm `shot_show` + officer `shot_off` (gán DN_001) +
  cuộc chat có tool message, chụp 13 trang (tổng quan, chi tiết DN, truy nguồn finding/mã hàng, danh mục,
  upload, tài liệu, nhật ký, góc nhìn officer, chat tool-use, chat @mention), rồi xoá. Deterministic,
  không gọi LLM.

Đã deploy 4 lần (mỗi lần push `main` → CI): `06fe771` → `41cd604` → `627be6d` → `b7334f4` (live).

## Decisions Made

- **Self-contained 1 file HTML (ảnh base64)** thay vì HTML + ảnh rời: user yêu cầu "1 file html đầy đủ";
  cũng tiện gửi/lưu. Đánh đổi: file ~1.3 MB committed — chấp nhận cho repo demo.
- **Build script tự sinh từ PNG đã commit** (không phụ thuộc thư mục scratch) → tái lập được từ asset commit.
- **Phong cách = đồng nhất với chính hệ thống** (sau phản hồi user): dùng lại design token của
  `app/static/style.css` (nền sáng `#f6f7f9`, header navy `#1d3557`, card/button/badge hệ thống, banner
  "Dữ liệu mẫu" vàng). KHÔNG tự chế landing style riêng. Sáng sủa, không tối, không gradient/emoji.
- **Trình bày AI theo NĂNG LỰC, không theo tool** (sau phản hồi user): 6 nhóm năng lực mô tả cho cán bộ
  (Tra cứu phát hiện / Tổng hợp–so sánh / Giải thích nghiệp vụ / Dẫn chiếu pháp lý / Soạn–xuất báo cáo /
  Tôn trọng thẩm quyền). Bỏ hết tên hàm (`search_findings`, `query_sql`…) và khái niệm "tool use" —
  cán bộ HQ không cần biết.
- **Bỏ phần "Quản trị AI"** (cấu hình model/hạn mức): đó là màn cấu hình dev/admin, không phải tính năng
  cho cán bộ → không đưa lên showcase.
- **Chụp ảnh retina (2×) + crop viewport + ẩn banner**: bản đầu chụp full-page nhồi vào khung nhỏ → chữ
  li ti, mờ, lặp banner vàng. Sửa thành crop gọn, nét, không banner.
- **Deploy = merge nhánh vào `main` + push**: user chốt. Hoá ra push chỉ deploy đúng commit showcase
  (chat redesign đã ở origin từ trước), không "ship kèm" gì.

## What Didn't Work

- **Theme tối tự chế (bản `06fe771`/`41cd604`):** dùng navy đậm làm nền chủ đạo + gradient → user chê
  "màu mè"/"màu tối nhìn ngu". Bài học: bám theo style hệ thống (sáng), đừng sáng tạo theme.
- **Ảnh full-page (`06fe771`):** screenshot cả trang dài nhồi vào khung → không đọc được. → chuyển crop viewport.
- **Chụp 2 vai chung 1 browser context:** login officer ghi đè cookie admin → mọi trang admin bị 404/từ chối
  (ảnh trắng có JSON `{"detail":"..."}`). Fix: `browser.new_context()` riêng cho mỗi vai.
- **Overclaim "chuẩn hoá tên hàng hoá":** user hỏi "có thật không?" — grep code: KHÔNG có (chỉ trong đề án
  §5.3). Cái thật là chuẩn hoá ĐƠN VỊ TÍNH (`app/checks/uom.py`). Đã sửa bullet (`b7334f4`).

## Open Items

- Chờ user duyệt cuối. Nếu chỉnh tiếp: sửa `TEMPLATE` trong `build_showcase.py` → chạy script → push.
- (Không thuộc phiên này, carry) phân công DN cho officer trên prod; review logic combo +20 điểm;
  polish hiển thị `code`/hậu tố `(Demo)`/quyết `ZZ_DEMO`.
