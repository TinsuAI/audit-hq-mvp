# 00 — Phạm vi audit

**Ngày:** 2026-08-08 · **Đối tượng:** luồng cán bộ hải quan của Audit-HQ MVP.

## Bề mặt được audit

Luồng chính, theo đúng thứ tự cán bộ đi qua:

1. **Tải lên → nạp dữ liệu** — `.ai/features/2026-08-07-upload-ingest-redesign/` (8 ảnh)
2. **Lưới xem trước file** — `.ai/features/2026-08-07-luoi-cuon-xem-truoc/` (8 ảnh)
3. **Gán cột theo trường khai** — `.ai/features/2026-08-08-man-gan-cot-theo-truong/` (4 ảnh)
4. **Độ đầy đủ dữ liệu / vướng mắc** — `.ai/features/2026-08-05-issue-56-data-completeness/` (9 ảnh)
5. **Phát hiện + cột dữ liệu gốc** — `.ai/features/2026-08-02-finding-columns-raw-data/` (9 ảnh)
6. **Phạm vi kỳ KTSTQ** — `.ai/features/2026-07-31-adr23-ktstq-period-scope/` (7 ảnh)

Mã nguồn: `app/templates/*.html`, `app/static/style.css`, `app/static/cell-grid.js`,
`app/pipeline/file_page.py`, `app/pipeline/data_files.py`, `app/routes/companies.py`.

## Người dùng chính và việc chính

**Người dùng:** cán bộ Hải quan làm kiểm tra sau thông quan (KTSTQ). Không phải kế toán
doanh nghiệp, không phải người dùng phổ thông. Đọc tiếng Việt, làm việc trên bảng tính
Excel hàng ngày.

**Việc chính:** đưa hồ sơ quyết toán của một DN vào hệ thống sao cho **mọi con số hệ
thống đọc ra đều truy được về đúng ô trong file gốc**, rồi đọc phát hiện mà không bao
giờ nhầm "chưa đánh giá được" với "đã soát và sạch".

## Ràng buộc

- Tiếng Việt đủ dấu, giọng hành chính — cùng văn phong đề án.
- Không thêm framework front-end: Jinja2 + CSS thuần + JS thuần (`AGENTS.md`).
- Bản dùng thí điểm; quyết định cuối luôn thuộc cán bộ, hệ thống không được kết luận thay.
- Dữ liệu thật là hồ sơ doanh nghiệp — không đưa giá trị thô ra log/thông báo.

## Nguyên tắc nền đã có (không phải phát minh trong lượt audit này)

`.ai/DECISIONS.md` ADR #18 · #23 · #24 · #25 · #28 — thang bằng chứng theo cột, cổng
review, cổng `not_evaluable`, tập trường khai.
