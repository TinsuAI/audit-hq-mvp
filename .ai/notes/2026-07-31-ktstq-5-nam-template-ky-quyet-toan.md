# Phương án: KTSTQ 5 năm · template cấu trúc lạ · kỳ quyết toán linh động

> Bối cảnh: 2026-08-01 demo cho một công ty sắp bị kiểm tra sau thông quan (KTSTQ).
> Phạm vi KTSTQ = tờ khai đăng ký trong 5 năm trước ngày quyết định → KHÔNG trùng
> trọn các kỳ quyết toán. Ba việc: (1) xử lý cấu trúc file lạ khi up BCQT+BCCT,
> (2) kỳ quyết toán lệch dương lịch + dữ liệu "lẻ", (3) đầu/đuôi cửa sổ 5 năm.
> Trạng thái: **ĐÃ GRILL + CHỐT ADR #23** (2026-07-31, `.ai/DECISIONS.md`) — ADR là bản
> chuẩn khi lệch với note này. Căn cứ pháp lý:
> `.ai/notes/2026-07-31-research-ky-ke-toan-bcqt-ktstq.md`. Chưa code.

## Hiện trạng đã kiểm (2026-07-31)

**Máy móc cấu trúc lạ ĐÃ CÓ (WS1, ADR #18):**
- `app/adapters/layout.py` — dò dòng tiêu đề theo từ khoá trong 25 dòng đầu, chịu
  tiêu đề nhiều tầng + dòng đánh số `(1)(2)`; `find_data_start` suy dòng dữ liệu
  đầu; không dò được thì lùi về hằng số.
- `app/adapters/evidence.py` — nhãn bằng chứng mỗi cột → parse confidence; cột
  thiếu bằng chứng = needs_review → màn xác nhận cột (preview grid + highlight).
- `app/adapters/form_signature.py` — vân tay form: hash (nhãn cột theo thứ tự +
  số cột + dòng đánh số, bỏ chữ số năm).
- `app/pipeline/saved_map.py` — map đã xác nhận lưu theo `(DN, slot, vân tay)`;
  CÙNG DN tái dùng chéo năm; CỐ Ý không kế thừa chéo DN.

**Census cấu trúc 475 file / 976 sheet trong `data/` (11 DN), 2026-07-31:**
- BCCT: **22 vân tay**; family lớn nhất (bản "chi tiết" ECUS, hrow=9/data_start=10)
  phủ **10/11 DN**; family thứ hai (bản "tổng hợp") 13 sheet / 3 DN; ~26 sheet là
  bảng phẳng tiêu đề ở dòng 0 (`data_start=1`). Khác dòng bắt đầu (1 ↔ 10) và khác
  độ rộng cột (11 ↔ ~109) ĐỀU CÓ THẬT trong dữ liệu.
- m15a: family Mẫu 15a chuẩn 27 sheet / 8 DN; một family biến thể phần mềm 55
  sheet / 2 DN (DN03, DN04); đuôi dài one-off từng DN.
- **Caveat:** phân loại slot theo từ khoá ≥2 hit nên phần đuôi lẫn sheet kho/nội bộ
  không phải BCQT; số đuôi là ước lượng trên. Kết luận cấu trúc (ít family lớn +
  đuôi dài per-DN) vẫn đứng. Script + output: scratchpad session (không commit —
  detail JSON chứa tên file thật).

**Defect có thật ở đường kỳ (nền cho việc 2 và 3):**
- `app/pipeline/ingest.py:330` — dòng BCCT ngoài cửa sổ `[period_from, period_to]`
  bị **BỎ ngay lúc nạp**, không lưu. Đếm vào `bcct_other_year` nhưng chỉ in ra CLI
  (`run_all.py:74`, `ingest.py:385`) — **web UI không hiện**.
- Sửa cửa sổ kỳ sau khi nạp (`companies.py:1356`) KHÔNG phục hồi dòng đã bỏ —
  phải re-upload + re-ingest.
- Kịch bản lỗi cụ thể: DN niên độ 01/04/2025–31/03/2026, up BCCT dương lịch 2025
  vào năm 2025 → dòng 01–03/2025 bị bỏ im lặng trên web; dòng 01–03/2026 nằm ở
  file dương lịch 2026, khi nạp vào năm 2026 (cửa sổ 04/2026–03/2027) cũng bị bỏ
  → khoảng 01–03/2026 **không bao giờ vào DB** dù nằm trong FY2025.
- Setting kỳ hiện là per `(DN, năm)` (`company_periods`, sửa tay `is_manual`);
  KHÔNG có default mức DN.

## Phương án — 4 ticket

### T1 — Lưu trọn dòng BCCT, tư cách thuộc kỳ tính lúc query (BLOCKING cho T4)
- Ngừng bỏ dòng ở `ingest.py:330`: lưu đủ mọi dòng kèm `declaration_date` +
  provenance file; tư cách thuộc kỳ suy lúc query từ cửa sổ `company_periods`
  (giữ `period_year` là nhãn nạp — ADR #13 không đổi).
- Sửa cửa sổ → recompute membership, không cần re-upload.
- Cảnh báo phủ dữ liệu mỗi (DN, kỳ): so cửa sổ với min/max ngày tờ khai + đếm
  theo tháng → banner "thiếu 01/01–31/03/2026, nạp thêm file dương lịch 2026".
- Câu hỏi mở (grill): dòng thiếu ngày quy về đâu (hiện quy về kỳ đang nạp);
  17 check đang join theo nhãn `period_year` — chuyển sang lọc cửa sổ ngày ở vế
  BCCT thế nào để không đổi kết quả 3 pilot hiện có.

### T2 — Setting niên độ: mức DN default + per-year override (độc lập, nhỏ)
- Thêm `fiscal_year_end` (ngày/tháng) trên `Company` → sinh cửa sổ default cho
  mọi năm; `company_periods` giữ vai trò exception per-year (đổi niên độ giữa
  chừng → kỳ chuyển tiếp ngắn; năm đầu/cuối hoạt động là kỳ lẻ).
- Trả lời "mỗi năm hay theo DN": **cả hai** — DN là default, năm là override.
  Chỉ per-year như hiện tại thì năm nào quên set sẽ rơi về dương lịch im lặng;
  chỉ per-DN thì không xử lý được kỳ chuyển tiếp.

### T3 — Template registry 2 tầng + đánh dấu file khớp mẫu (độc lập)
- Tầng 1: template builtin curated {tên, slot, (tập) vân tay, column map,
  data_start} — seed từ các family census (BCCT chi tiết ECUS, BCCT tổng hợp,
  Mẫu 15a chuẩn, biến thể DN03/DN04…).
- Tầng 2: map officer-confirmed per-DN (đã có — giữ nguyên tính không kế thừa
  chéo DN).
- Thứ tự resolve khi parse: map đã xác nhận của DN → template builtin khớp vân
  tay → dò từ khoá → gate review. Không đường nào parse im lặng.
- Đánh dấu: lưu `template_id`/`match_source` vào `data_files`; màn review + trang
  tài liệu hiện "Khớp mẫu: …" / "Map đã xác nhận …" / "Không khớp — cần xác nhận
  cột". Fallback hằng số phải hiện nguồn "mặc định" thay vì lặng.
- Câu hỏi mở: template builtin sống ở code (dict kiểu `BALANCE_EXPECT`) hay bảng
  DB có UI quản trị.

### T4 — "Phạm vi kiểm tra" KTSTQ 5 năm (SAU T1)
- Là khái niệm scope/view, KHÔNG phải khoá dữ liệu mới. Setting mức DN: ngày
  quyết định (dự kiến) → cửa sổ `[D−5 năm, D]`.
- Màn độ phủ: chiếu cửa sổ lên các kỳ quyết toán → mỗi kỳ một trạng thái:
  trọn trong phạm vi · cắt đầu · cắt đuôi · chưa có BCQT.
- Kỳ đầu (bị cắt): chạy đủ check trên TRỌN kỳ (đẳng thức cân đối chỉ đúng trên
  trọn kỳ); finding có ngày tờ khai lọc được theo phạm vi khi báo cáo; finding
  cân đối gắn nhãn "kỳ quyết toán rộng hơn phạm vi kiểm tra".
- Đuôi (sau kỳ quyết toán cuối đã nộp → D): chưa có BCQT → chỉ chạy nhóm check
  thuần BCCT trên dòng trong đuôi (khả thi nhờ T1); check cần BCQT hiện "chưa
  đến hạn nộp BCQT" thay vì im lặng.
- Finding ngoài cửa sổ 5 năm vẫn hiện, tag "ngoài phạm vi" (hết thời hiệu,
  tham khảo).
- Câu hỏi mở: một cửa sổ mỗi DN hay nhiều đợt kiểm tra có lịch sử; nhóm check
  thuần BCCT gồm những check nào trong 17 (phải rà từng check).

## Trình tự + route
- T1 trước (nền cho T4). T2, T3 độc lập, chạy song song được. T4 cuối.
- Route: grounding xong (session 2026-07-31) → `/grilling` chốt các quyết định
  mở thành ADR (nặng nhất: T1 đổi ngữ nghĩa lưu trữ, đụng 17 check + staleness
  WS3) → tickets → mỗi ticket `/tdd` + `/rev`.

## Demo 2026-08-01 — cái gì nói được, cái gì tránh
- KHÔNG ticket nào ship kịp. Demo bằng đồ CÓ SẴN:
  - Flow cấu trúc lạ: up file lạ → detect tiêu đề/cột → màn xác nhận → map lưu,
    tái dùng chéo năm. Đây chính là "detect + đánh dấu template" bản per-DN.
  - Kỳ lệch dương lịch: sửa cửa sổ kỳ tay đã có, UI hiện nhãn kỳ ≠ dương lịch.
  - Câu hỏi 5 năm: trả lời bằng phương án màn độ phủ (mô tả, không bấm máy).
- TRÁNH làm live: nạp BCCT dương lịch vào DN đã set kỳ tài chính — dòng ngoài
  cửa sổ bị bỏ im lặng trên web UI (chỉ CLI in số bị loại).
