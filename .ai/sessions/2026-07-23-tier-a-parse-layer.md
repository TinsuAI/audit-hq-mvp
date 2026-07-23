# Session 2026-07-23 — Tier A parse layer + B1 + ADR 15 (Mẫu 15 mở rộng)

Phiên dài, hai repo (`audit-hq-mvp` + `audit-hq-pilot`), 4 lần deploy prod. Khởi đầu từ yêu
cầu "xem công việc xử lý bộ data mới của bên audit-hq-pilot" và kết thúc với 002/006 nạp được
qua sản phẩm, 004 nạp được Mẫu 15, và trang finding/tài liệu dùng được ở quy mô thật.

## What Was Done

Bộ dữ liệu mới: cán bộ HQ cung cấp 3 DN (002/004/006, `audit-hq-pilot`), bố cục khác 6 DN đang
chạy. `audit-hq-pilot/notes/12` liệt kê lỗi sản phẩm. Phiên này implement Tier A + B1 + ADR 15.

**Tầng parse (`fix/tier-a-parse-layer` → merge `65c88cf`), 8 commit:**
- **P-01** (`a7f685a`): `_norm` gập `đ`/`Đ` (U+0111/U+0110 — ký tự độc lập, NFD không tách)
  trước NFD + chuẩn hoá từ khoá. `_find_header_columns` trước đó CHƯA BAO GIỜ khớp trên file thật.
- **A1+A2** (`e8dbea3`): `app/adapters/sheet_select.py` — chọn sheet chấm điểm nhãn cột đúng
  vị trí, phá hoà theo kỳ. `app/adapters/layout.py` — dò dòng dữ liệu thay hằng số.
  `SheetNotFound` thay vì lấy sheet 0 im lặng.
- **A1 m16/bcct + discover** (`8c69f0b`): `discover` thôi bỏ file không phân loại được theo
  tên; một workbook phục vụ nhiều slot; BCCT chọn sheet chi tiết thay tổng hợp.
- **A3** (`3d98e4f`): `_common.py` — đếm ô lỗi Excel (qua openpyxl/xlrd, pandas nuốt thành NaN)
  + liên kết workbook ngoài, cảnh báo không đổi số.
- **B1** (`d6b1bf1`): `c4_norm.py` — C4.3 tính mỗi cặp BOM 1 lần thay vì 1 lần/khối lặp Mẫu 16.
- **ADR 15 doc** (`2847724`), **sửa /rev** (`665e315`+`216afd3`): 6 lỗi review.

**UI (`feat/finding-list-paging` → merge `5b0de04`), 2 commit:**
- **Phân trang** (`f09116b`): trang DN gộp finding theo check + phân trang. Đo trên
  PILOT_006: 18,7 MB → 294 KB, 5,2s → 1,8s.
- **Fix trang tài liệu** (`41794d7`): registry đăng ký file theo nội dung (khớp `discover`, có
  cache), hết cảnh "chưa có file" khi dữ liệu đã nạp.

**ADR 15 Mẫu 15 (`feat/extended-layout-m15` → merge `c82ffa9`), 1 commit:**
- **Bố cục mở rộng** (`56c54bd`): `app/adapters/extended_layout.py` — suy map cột từ dòng đánh
  số + số biểu→trường CỐ ĐỊNH của Mẫu 15, chứng minh bằng đẳng thức `(11)=(5)+(6)-(7)-(8)-(9)-(10)`
  ≥98% dòng. Chỉ chạy khi `select_sheet` trượt. 004 nạp được M15 (EPE 104 dòng, GC 37).

**Nạp dữ liệu mới vào local DB:** tạo symlink tree `data/PILOT_{002,004_EPE,004_GC,006}/`,
ingest → local DB có 4 company pilot. Đã backup `audit_hq.sqlite.bak-pre-reingest-20260722-191258`
(WAL-safe qua `VACUUM INTO`) trước khi nạp.

**Đính chính `audit-hq-pilot/notes/12`** (`7e8e438` repo pilot): 4 khẳng định đã bị đo lại là sai.

## Decisions Made

- **Map cột từ file, chứng minh bằng đẳng thức — KHÔNG spec theo DN, KHÔNG tin nhãn/AI.** File
  tự mang map (dòng đánh số + công thức cân đối tự ghi). Kiểu hỏng nguy hiểm là "map trông hợp
  lý nhưng ra số sai âm thầm" — đã xảy ra thật (HONG_AN đọc `Sheet1` là bảng tồn kho 9 cột suốt
  nhiều kỳ). Nên đẳng thức là trọng tài. ADR #15.
- **A1 trước A2, KHÔNG song song** (`notes/12` ghi sai). A2 dò dòng của sheet adapter ĐANG đọc;
  nếu A1 chưa sửa sheet sai thì A2 kéo thêm dòng rác. Đo: A2 một mình +20 finding CRITICAL giả.
- **Fail-loud:** không sheet nào khớp → `SheetNotFound`, không nạp bừa. UI chẩn đoán trước khi
  ingest nên không thành 500.
- **M15a của 004 CHƯA làm — cố ý.** Số biểu M15a không ổn định giữa DN, map `export_qty` phải
  theo nhãn phân mảnh → rủi ro C4.3 ra số sai âm thầm. 004 nạp không M15a, C4.3/C1.4 không chạy
  (đúng — thà không có hơn sai).
- **B2/B4/hệ số nhân C4.3 chặn bởi đề án** — mâu thuẫn `de-an-audit-hq.md:228`
  (`Σ(định_mức × xuất_khẩu_M15a)`), phải update `../audit-hq/` trước. Chỉ làm B1 (khôi phục
  đúng catalog, không đổi định nghĩa).
- **KHÔNG re-ingest prod** — prod dùng tên anonymize, năm 2024/2025 (không dính lỗi đã sửa),
  10/14 DN không có file nguồn. Re-ingest vô ích + rủi ro. Fix áp cho lần upload sau.
- **`--no-ff` mọi merge** — Tier A revert được bằng 1 commit (`git revert -m 1`).

## What Didn't Work

- **Đếm ô lỗi ở tầng giá trị đã parse:** pandas đổi ô lỗi thành NaN TRƯỚC khi adapter thấy, nên
  quét giá trị parsed ra 0 lỗi. Phải quét ở tầng openpyxl/xlrd theo `cell.data_type == 'e'`.
- **Quét ô lỗi chỉ ở cột số:** 006 có 276 `#N/A` ở cột `product_unit` (text) → phải quét MỌI
  cột adapter đọc.
- **Số hạng đầu công thức không dấu:** regex `([+-])(\d+)` bỏ mất `(5)` trong `(5)+(6)-...`.
  004 GC "lọt" giả vì tồn đầu toàn 0. Cổng đẳng thức bắt được. Sửa: số hạng đầu không dấu = cộng.
- **Dò dòng đánh số theo "chữ số trần":** dòng dữ liệu thật cũng đầy số nguyên nhỏ → nuốt dòng
  dữ liệu đầu. Phải BẮT BUỘC có ngoặc `(\d+)`.
- **Registry probe mọi file:** `sync_data_files` chạy mọi lần GET trang tài liệu → mở lại từng
  workbook. Test suite 66s → 600s+. Fix: cache theo (path,mtime,size) + chỉ probe slot mà tên
  không lấp được.
- **`select_sheet` bỏ `year`:** chẩn đoán và ingest chọn khác sheet (HONG_PHUC 2025: chẩn đoán
  sheet 2026, ingest 2025). Fix: thread `year`. Và `covers()` boolean nhập nhằng năm tài chính
  (01/04–31/03 vừa "bắt đầu 2025" vừa "chứa 2026") → đổi thành rank.
- **Nạp pilot bằng loader của pilot repo:** đọc từ `pilot.sqlite`, KHÔNG qua adapter mvp → không
  chứng minh được gì về A1. Phải ingest qua đường sản phẩm thật.

## Open Items

- **M15a mở rộng + cột M16 của 004** (việc tiếp ADR 15): map M15a theo nhãn + cổng đẳng thức
  riêng; sửa M16 đọc c8 (ĐM thực tế) thay c7. Mở khoá C4.3/C1.4 cho 004.
- **Đề án chặn B2/B4/hệ số nhân C4.3** — cần user chốt quy trình 3 repo trước khi code.
- **B3** (đọc cột Ghi chú) cần migration.
- **Tầng C chờ họp:** `period_from`/`period_to`, `NOT_EVALUABLE`, xếp hạng finding theo lượng
  + ngưỡng severity (đã phân trang, còn ranking).
- **Banner "dữ liệu mẫu"** phủ tên/MST thật ở local DB — chặn đưa pilot lên demo. `anonymize.py`
  chỉ sửa DB không sửa file Excel.
- **Dev server còn chạy** `http://127.0.0.1:8200`.
