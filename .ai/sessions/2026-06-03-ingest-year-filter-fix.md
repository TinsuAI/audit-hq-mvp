# Session 2026-06-03 — Fix bug ingest/evidence tờ khai lệch kỳ

> Session chạy trên Gemini CLI (Claude Code hết hạn giữa chừng). Tài liệu này
> được Claude viết lại từ log Gemini cho đúng format handoff.

## Bối cảnh

Bạn của user phát hiện bug trên live: finding kỳ 2025 hiển thị evidence là tờ
khai ngày 29/08/2023 (`/findings/8011`); trang
`/companies/DN_001/data?year=2024&table=bcct` hiện cả tờ khai năm khác.

## What Was Done

### Bug & nguyên nhân
- File BCCT (báo cáo chi tiết tờ khai) thường gộp nhiều năm trong 1 file
  (2023–2025). Khâu `ingest` gán **cứng** mọi dòng vào `period_year` đang nạp.
- Hệ quả: evidence tờ khai lạc kỳ; sai tổng lượng đối chiếu Mẫu 15 (C1.1/C1.4
  cộng dồn cả tờ khai năm cũ); trang Data lẫn năm.

### Fix
- `app/pipeline/ingest.py`: khi ghi `DeclarationLine`, chỉ nạp dòng
  `r.declaration_date is None or r.declaration_date.year == year`.
- Mỗi (DN, năm) ingest riêng nên tờ khai 2023 vẫn được nạp khi chạy kỳ 2023 →
  **không mất dữ liệu**. Verify HONG_AN: file 2267 dòng → 2023:180, 2024:246,
  2025:1512 (tổng 1938 sau khi loại trùng/ngoài phạm vi). GROWATT: cùng 1 file
  8945 dòng phân về 2023:5474, 2024:3471, 2025:0 (DN chưa phát sinh 2025 → đúng).
- Commit `ad68837`, push `main`, CI build + deploy.

### Dọn dữ liệu live (surgical, không re-ingest)
Live không có Excel raw (policy bảo mật/dung lượng) nên không re-ingest được:
- Khôi phục bảng `declaration_lines` từ backup 27/05.
- Chạy script lọc bỏ dòng `declaration_date.year != period_year`.
- Xoá ~**20.671 dòng** tờ khai lạc kỳ trên live.
- Rerun toàn bộ 16 check cho DN_001→DN_004 + `recompute_all_scores`.

### Kết quả
- Risk score: **DN_001 296→127**, **DN_002 125→62** (loại tờ khai sai kỳ làm
  số đối chiếu chính xác hơn). DN_003 263, DN_004 97 không đổi đáng kể.
- Findings: 2025 = 880, 2024 = 283.
- 435 tests pass, ruff clean.

## Decisions Made

- **Lọc theo `declaration_date.year`, không thêm cột mới.** User chất vấn tại
  sao ingest gán `period_year` riêng thay vì dùng cột ngày — kết luận: vẫn giữ
  `period_year` (các check/query phụ thuộc nó) nhưng nạp đúng dòng theo ngày.
- **Dòng `declaration_date is None` vẫn được nạp** (không loại) để tránh mất
  tờ khai thiếu ngày.
- **Live: khôi phục-từ-backup + lọc SQL**, không `run_all` (không có Excel raw).

## What Didn't Work / Đã loại

- Bản ingest.py trung gian thêm logic đếm + `print` số dòng bị lọc theo năm:
  đã bỏ, quay về generator gọn (đúng style dự án, tránh log thừa). Filter giữ
  nguyên.

## Open Items

- ⚠️ **Chưa chắc fix C4.1 "x" (06-01) đã hiệu lực trên live.** Live 06-03 chỉ
  khôi phục `declaration_lines`, không re-ingest `norms` → cột `note` có thể
  toàn NULL → C4.1 không loại hàng nội địa. Cần kiểm `norms.note` trên tinsu;
  nếu NULL thì re-ingest M16 hoặc backfill note rồi rerun C4.1.
- Vẫn chờ chị trả lời 4 câu hỏi clarify M16 (xem session 2026-06-01) cho
  điểm 2/3 góp ý nghiệp vụ.
- Verify UI live: phần junk `.`/E13 chưa smoke-test (phần evidence lệch kỳ đã
  verify xong).
