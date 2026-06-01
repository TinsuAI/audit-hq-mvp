# Session 2026-06-01 — Mẫu 16 xuất xứ "x" + phân tích góp ý nghiệp vụ

## Bối cảnh

Nhận góp ý nghiệp vụ từ chị (chuyên gia KTSTQ) gồm 5 điểm. Nhiệm vụ: phân tích,
clarify cái mơ hồ, cái nào làm được ngay thì làm, cái nào cần thêm thông tin thì
soạn câu hỏi + đưa vào đề án.

## What Was Done

### Phân tích 5 điểm góp ý (đối chiếu code + dữ liệu thực 6 DN)

1. **"x" ở cột Ghi chú Mẫu 16 = xuất xứ trong nước → loại khỏi rà soát lệch nhập.**
   ✅ Verify: Mẫu 16 TT39 có cột "Ghi chú" tại index 8 (col "(9)"), adapter
   trước đây bỏ qua. Dữ liệu thực: 22 file có "x", phân bố theo DN/năm:
   DO_THANH 2023/2024, HONG_AN 2020-2022/2024/2025, HONG_PHUC 2024.
   → **ĐÃ IMPLEMENT** (xem dưới).

2. **Định mức ngành để rà tính hợp lý.** Đã có sẵn = C7.1 (catalog group 7),
   phase 2/conditional, cần ≥30 DN/ngành. Ta chỉ có 6 DN khác ngành → không tự
   tính được. Nguồn benchmark là input ngoài (hiệp hội + nội bộ HQ). → CẦN HỎI.

3. **BTP/phế liệu giải thích lệch + ưu tiên "điểm then chốt" theo số thuế.**
   - (a) BTP/phế liệu: đã có group 8 (phế liệu) + group 9 (BTP), phase 2,
     conditional, cần data bổ sung. Chưa làm được ngay.
   - (b) Trọng yếu theo số thuế: severity hiện CHỈ tính theo % lệch, chưa có
     chiều giá trị/thuế. `declaration_lines` có `value_total`, `tax_total`.
     Làm được nhưng cần làm rõ cách quy "số thuế truy thu". → CẦN HỎI.

4. **Kiểm thuật toán để không lỗi trường thông tin.** ✅ Verify: file chuẩn
   `BCQT_NPL` (m15) ở cả 6 DN layout giống hệt, mapping đúng (kiểm cân đối số dư
   133+30−163=0). KHÔNG có bug mapping. Rủi ro thật = chọn nhầm file biến thể
   (mỗi DN nhiều bản draft/fn/check lại/__dup). `discover.py` đã lọc hợp lý.

5. **KXDĐM (vật tư tiêu hao không định mức) vẫn phải quyết toán lượng M15.**
   ✅ Verify: quét 98 file Mẫu 16 → **0 file dùng "KXDĐM"** (6 DN không theo
   quy ước này). Inverse HONG_AN 2024: 63 mã M15 không có norm M16; không check
   MVP nào phạt nhóm này, C2.1 vẫn cân đối lượng → không false-positive.

### Implement điểm 1 (commit `9d5bd06`, đã push main)

- `app/adapters/m16.py`: đọc Ghi chú (TT39 col 8) → `M16Row.note`; helper
  `is_domestic_origin(note)` (note.strip().lower()=="x"). DINHMUC format không
  có cột này (xuất xứ nằm trong prefix mã code) → `note=None`.
- `app/models/bcqt.py` + migration `c7f3a1b2d4e5`: thêm cột `norms.note` String(64).
- `app/pipeline/ingest.py`: truyền `note=r.note` khi ghi `Norm`.
- `app/checks/c4_norm.py`: C4.1 build set `domestic` từ (material_code, note),
  loại khỏi `m16_codes` trước khi soi "không có nguồn nhập".
- Tests: `is_domestic_origin`, C4.1 bỏ "x", C4.1 vẫn fire khi không nội địa,
  adapter assert đọc được `note`. **435 pass (+3), ruff sạch.**

### Đo impact trên DB dev (re-ingest + rerun 8 cặp)

| DN/năm | C4.1 trước | sau | bỏ FP |
|---|---:|---:|---:|
| DO_THANH 2023 | 12 | 0 | 12 |
| DO_THANH 2024 | 7 | 0 | 7 |
| HONG_AN 2020 | ~178 | 3 | ~175 |
| HONG_AN 2021 | 71 | 25 | 46 |
| HONG_AN 2022 | 93 | 42 | 51 |
| HONG_AN 2024 | 0 | 0 | 0 |
| HONG_AN 2025 | 2 | 2 | 0 |
| HONG_PHUC 2024 | 5 | 0 | 5 |

**Tổng ~296 finding C4.1 false-positive bị loại (~80%).**

## Decisions Made

- **Phạm vi loại "x" = chỉ C4.1** (đối chiếu nguồn nhập). C4.3 (tiêu hao hợp lý)
  VẪN áp dụng cho hàng nội địa vì vẫn tiêu hao thực. Đây là câu hỏi #1 gửi chị —
  sẽ mở rộng nếu chị muốn loại hẳn khỏi mọi kiểm tra định mức.
- **Đánh dấu material là nội địa nếu BẤT KỲ dòng norm nào có note "x"** (giảm
  false-positive tối đa cho C4.1).
- **Chỉ đọc note ở TT39**; DINHMUC không có cột Ghi chú nên `note=None`.
- Push thẳng `main` (theo workflow repo, deploy live) theo yêu cầu — không branch.

## What Didn't Work / Red herrings

- Lần mở file đầu tưởng HONG_AN dùng sheet "Sheet1" layout khác → SAI. Do
  `find | head -1` bốc nhầm file biến thể; file chuẩn `BCQT_NPL` layout nhất quán.
- Tưởng "KXDĐM" có trong data → KHÔNG (0/98 file). 6 DN không dùng quy ước này.
- HONG_AN 2024 file mà `discover` chọn (`BCDM_TT39_HA_2024.xls`, 9 cột) KHÔNG có
  "x", trong khi bản BCDM khác cùng năm CÓ → biến thể file đánh dấu xuất xứ khác
  nhau, củng cố rủi ro điểm 4.

## Open Items

- **Đã soạn 4 câu hỏi clarify gửi chị** (chờ trả lời):
  1. Phạm vi loại "x": chỉ check nhập khẩu hay mọi check định mức?
  2. Nguồn định mức ngành cho demo (bộ tham chiếu hay ô nhập tay)?
  3. Số thuế truy thu: có sẵn trên dòng tờ khai hay ước tính (lượng×đơn giá×thuế suất)?
  4. KXDĐM: DN ghi chú vật tư tiêu hao thế nào (KXDĐM / để trống / không liệt kê)?
- Điểm 2 (C7.1 định mức ngành), 3a (BTP+phế liệu), 3b (trọng yếu theo thuế):
  chờ chị trả lời rồi đưa vào đề án `../audit-hq/de-an-audit-hq.md`.
- Điểm 4 — heuristic `_DRAFT_HINTS` trong `discover.py` coi `"fn"` (final?) là
  draft → có thể ưu tiên ngược file final. Rà lại nếu cần.
- Live `tinsu` CHƯA re-ingest/rerun (chỉ DB dev). Khi muốn cập nhật demo cần
  rerun trên DB tinsu.
