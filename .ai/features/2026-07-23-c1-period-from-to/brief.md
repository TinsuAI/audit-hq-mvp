# Feature: C1 — `period_from`/`period_to` cho kỳ báo cáo (custom date)

> Đường RẺ (notes/12 khuyến nghị, đường ĐẦY ĐỦ bị `notes/12` "KHÔNG làm" #4 loại). Full-stack:
> backend đổi lọc BCCT theo cửa sổ kỳ + frontend cho **sửa kỳ** (mặc định tự đọc, sửa được).
> User ĐÃ CHỐT LÀM (STATUS Next Steps 0).

## Scope

**Backend:**
- Bảng `company_periods(company_id, period_year, period_from, period_to, is_manual)`, unique
  `(company_id, period_year)`. Ghi lúc ingest.
- Suy bounds lúc ingest theo ưu tiên: **giá trị `is_manual` đã lưu** > `CompanyHeader.period_from/to`
  (đọc sẵn từ tiêu đề, `_common.py:211-225`) > **default dương lịch** `[year-01-01, year-12-31]`.
- Đổi lọc BCCT tại 2 điểm `ingest.py:91-93` (stats/dry-run) và `:181-186` (insert): range
  `period_from ≤ declaration_date ≤ period_to` thay `== year`.
- `DeclarationLine.period_year` = **nhãn kỳ** (`year`, thư mục whitelist), KHÔNG còn
  `declaration_date.year`. Tách kỳ khỏi mốc giao dịch — hoàn tất ý ADR #13.

**Frontend** (trang `company_documents.html`, mỗi dòng năm):
- Hiện cửa sổ kỳ: "Kỳ 01/04/2024 – 31/03/2025" khi khác dương lịch; "Năm 2024" khi mặc định.
- Form sửa kỳ (2 ô ngày) → `POST /companies/{code}/documents/period` → upsert `is_manual=True`.
  Có nút "Về mặc định" (xoá row / `is_manual=False`) để ingest sau tự suy lại.
- Sau khi sửa: banner "Kỳ đã đổi — bấm **Nạp dữ liệu** rồi **Chạy kiểm tra** để áp dụng".
  Tái dùng nút + route sẵn có (`documents_ingest_year` giờ đọc bounds đã lưu). KHÔNG tự nạp lại
  ngầm — giữ ingest tường minh (đúng nguyên tắc không hộp đen).

**KHÔNG làm:**
- KHÔNG thêm `period_from/to` vào 4 bảng Tầng 1 (đường ĐẦY ĐỦ, 214 tham chiếu — đã loại).
- KHÔNG đổi chữ ký/logic 17 check. Verify: `app/checks/` KHÔNG chỗ nào suy năm từ
  `declaration_date` — đều join `period_year` (vẫn là khoá join, ADR #13).
- KHÔNG sửa đề án (catalog): đổi *dòng BCCT nào lọt vào kỳ* + schema, KHÔNG đổi mô tả check.
- KHÔNG tự động nạp lại + chạy kiểm tra ngay khi sửa kỳ (tường minh 2 bước, tái dùng route cũ).

## Decisions

1. **Grain = per `(company, period_year)`.** DN đổi năm tài chính giữa kỳ vẫn đúng; ingest đã
   per `(company, year)`; bounds đọc riêng mỗi kỳ.
2. **`is_manual` cần thiết:** phân biệt kỳ user sửa tay với kỳ suy tự động. Re-ingest phải TÔN
   TRỌNG `is_manual=True`, không ghi đè bằng header/default.
3. **Chỉ dùng kỳ tuỳ ý khi CÓ ĐỦ cả `from` lẫn `to`.** Thiếu một → rơi về default dương lịch.
4. **Default dương lịch giữ 6 DN whitelist KHÔNG đổi** (đều dương lịch / header.year == folder
   year). 006 dương lịch → mất 0 dòng, y như cũ. Tiêu chí: harness vẫn **419 finding**.
5. **Range partition sạch giữ tính chống rò ADR #13:** kỳ FY không chồng nhau → mỗi
   `declaration_date` rơi tối đa 1 kỳ; dòng 2023 file gộp vẫn ngoài cửa sổ FY2024 → vẫn loại.
6. **Re-apply tường minh** qua nút Nạp/Chạy sẵn có, không auto. Sửa kỳ chỉ lưu bounds + hiện
   banner; user chủ động nạp lại. Nhất quán với luồng 2 nút hiện tại.

## Risks

- **Re-ingest cần file nguồn.** Sửa kỳ chỉ có tác dụng phục hồi dòng khi nạp lại từ file gốc.
  Prod 10/14 DN KHÔNG có file → sửa kỳ chỉ đổi nhãn, không phục hồi dòng. Pilot 002/004 CÓ file
  local → hoạt động. Xử lý: nếu discover không thấy BCCT, lưu kỳ + cảnh báo "cần file nguồn để
  áp dụng".
- **Cửa sổ kỳ chồng nhau do sửa tay/header sai** → 1 `declaration_date` khớp 2 kỳ, đếm trùng
  chéo kỳ. Mitigation: validate `from ≤ to`; log cảnh báo khi 2 kỳ cùng DN chồng khoảng.
- **Sheet-select tie-break** (`extended_layout.py:192-195`) so `header.period_from.year == year`;
  DN năm tài chính có `period_from.year == folder year` → không đổi. Xác nhận khi test 002/004.
- **Dữ liệu 002/004 phải có BCCT phủ đủ cửa sổ FY trong thư mục năm đó** — nếu dòng Jan–Mar nằm
  ở file thuộc thư mục năm sau, discover per-year không thấy. Kiểm layout `PILOT_002/004` khi đo.
- **Migration mới** trên head `d3e4f5a6b7c8`, chỉ thêm 1 bảng → rủi ro thấp.
- **ADR #16 cần ghi:** quy tắc BCCT đổi từ "`period_year` = `declaration_date.year`" sang
  "`period_year` = nhãn kỳ; dòng chọn theo `[from,to]`; user sửa được".

## Status — ✅ XONG (2026-07-24, ADR #16)

7 lát + **pass hiển thị nhất quán DN năm tài chính** xong. Full suite xanh, harness nghiệm thu đạt.
Ảnh: `screenshots/{01_documents_period_editable, 02_company_detail_fiscal_label, 03_item_detail_fiscal_dates}.png`.
Chưa commit. Giới hạn còn lại: cảnh báo cửa sổ sửa tay chồng lấn chéo năm (manual-only, hoãn).

**Hiển thị (review "Năm X" mơ hồ cho DN năm tài chính):** thêm `load_period_windows()` (chỉ trả
kỳ ≠ dương lịch), truyền vào company_detail + item_detail. Nhãn kỳ tài chính hiện ở: tab năm
(sup "TC" + tooltip), dòng chú "kỳ quyết toán, không phải dương lịch, tờ khai có thể sang năm sau"
dưới tab, phụ đề 2 section item_detail, tooltip cột "Năm" bảng toàn cảnh. DN dương lịch KHÔNG đổi.

## Open Questions (đã giải)

1. ~~002/004 phục hồi bao nhiêu dòng?~~ → PILOT_002 phục hồi **đúng 3.014/11.115** (window tự
   đọc 2025-04-01..2026-03-31), bcct_other_year = 0. Đạt tiêu chí.
2. ~~"Về mặc định" xoá row hay set `is_manual=False`?~~ → **set `is_manual=False`** (đã làm): giữ
   bounds để hiển thị, ingest sau tự cập nhật.

## Slices (`/v_tdd` từng lát)

1. Model + migration `company_periods`.
2. `resolve_period_bounds(session, company_id, year, header)` — ưu tiên manual > header > dương
   lịch; upsert (tôn trọng `is_manual`).
3. Đổi 2 điểm lọc BCCT sang range + ghi `period_year=year`. Fixture năm tài chính + dương lịch.
4. Đo harness (419 finding 6 DN giữ nguyên) + số phục hồi PILOT_002.
5. Route `POST .../documents/period` (validate, upsert `is_manual`, "về mặc định").
6. Template: hiện cửa sổ kỳ + form sửa + banner "nạp lại để áp dụng". `ui_smoke.py` chụp.
7. `/rev` + ghi ADR #16.
