# 2026-08-07 — Thiết kế lại luồng tải lên → nạp dữ liệu

Từ một câu của owner ("UI UX upload rồi ingest tệ quá") tới 21 vé đã cài, kiểm chứng và gộp.
Spec **issue #80** · **PR #105** (chưa merge) · **PR #96** (tách riêng, deploy độc lập).

## Làm gì

`/grill-with-docs` → 17 quyết định → `/to-spec` → `/to-tickets` → 13 vé + 8 vé phát sinh.
Tôi điều phối; mỗi vé một agent chạy trong git worktree riêng. **Không lấy báo cáo agent làm bằng** —
chạy lại suite trên nhánh của từng vé trước khi gộp, và tự tái hiện những khẳng định then chốt
(guard `_EXTRA_GATES` đỏ được, repro rò teardown, cơ chế flake xlsx).

## Quyết định lớn

**"Đủ dữ liệu" đổi định nghĩa.** Từ "đủ 4 loại tài liệu" thành **"mọi kiểm tra áp dụng được đều có
đủ nguồn Tầng 1"**. Nền của quyết định là một số đo: 10 lần một kiểm tra không kết luận được chia
**1 / 6 / 3** theo ba lớp cách gỡ — tức **9/10 vướng mắc KHÔNG gỡ được bằng file của chính kỳ đó**.
Danh sách phẳng cũ khiến cán bộ đi tìm file không tồn tại. ADR #24.

**Vướng mắc xếp theo cách gỡ, không theo lý do.** Ba lớp, gắn per-instance trên `NotEvaluable`,
lưu ở `check_runs.remedy`. Có **năm** nguồn sinh chứ không phải bốn — bộ điều phối tự ghi trạng
thái mà không dựng đối tượng nào, và đó lại là nguồn của lớp phổ biến nhất.

**Bảng điều khiển và kiểm tra khớp nhau theo cấu trúc.** #85 tách bốn hàm điều kiện ra khỏi chính
các kiểm tra rồi gọi lại, thay vì viết logic song song. Test đối chiếu dự đoán ↔ trạng thái đã lưu
chạy trọn pipeline trên 7 fixture, kèm khẳng định phủ đủ ba lớp nên không xanh giả được.

## Năm lỗi im lặng đang sống trên prod, bắt được khi làm

1. **Không có trình xử lý lỗi nào** — `grep exception_handler app/` rỗng. Mọi lỗi đổ JSON thô cho
   cán bộ, 500 lộ dấu vết ngăn xếp. Đây là cái owner báo (`?year=` rỗng) — nhưng gốc rộng hơn nhiều
   so với một tham số. → PR #96, đo lại trên server thật.
2. **Ghim trang tính làm hỏng bố cục mở rộng** — nhánh đọc mở rộng chỉ chạy khi `sheet is None`, mà
   xác nhận cột thì ghim trang. Nên **chính lượt nạp ngay sau khi cán bộ xác nhận** đọc file mở rộng
   bằng cột cố định, lệch mọi trường, không báo gì. Cán bộ làm đúng thứ giao diện bảo làm thì sinh
   số sai.
3. **`match_source` rỗng 15/15 file** — đọc một khoá mà đường parse không sinh ra; 3/4 nhãn truy
   nguồn chưa bao giờ hiện.
4. **Xoá file không dời `data_version`** — kỳ tiếp tục phục vụ số của bộ file đã biến mất.
5. **Rò teardown giữa test** — `_restore_db` gọi `from app.database import ...` BÊN TRONG hàm nên
   chạy sau khi `_fresh_db()` đã ghi đè, tức khôi phục chính cặp đã vá lên chính nó, ngay sau
   `dispose()`. Thứ tự chữ cái mặc định che nó vì test dùng `app_db` chạy xen vào dọn hộ tình cờ.

## Ba giả định của tôi bị số đo lật ngược

- **Cổng review đã đúng rồi.** Tôi viết vào spec rằng nó dừng ở mọi lượt nạp và cần nối tham số
  `has_saved_map`. Sai: `record_parse_result` đã nâng map lưu lên `officer-confirmed` từ trước, và
  `has_saved_map` là **tham số chết, không lời gọi nào trong sản phẩm**. Không phải sửa ADR #18.
- **Hạn mức 25MB không do chi phí mở file.** `load_workbook(read_only)` trên file 71,3MB mất
  **1,19 giây**. Nút thắt thật là đọc tuần tự **chỉ đi tới** — nhảy tới dòng 200.000 mất **3,87 giây**.
  Một reviewer đoán 28–125 giây; số đo của tôi bác lại. → trích xuất một lần vào kho đệm.
- **Đuôi file nói dối.** 493 file = 268 xlsx thật · 185 xls thật · **38 file đuôi `.xls` thật ra là
  XML SpreadsheetML** (190,8MB) · 2 hỏng. Khớp ghi chú "40 file không mở được" có sẵn trong mã.
  Nhận dạng nay theo byte đầu.

## Lỗi trong phương pháp kiểm chứng của chính tôi

`.venv` **không có `pytest-randomly`**, mà `pytest -p no:<plugin-không-có>` được nhận **im lặng**.
Nên chỉ thị "chạy cả thứ tự ngẫu nhiên lẫn `-p no:randomly`" tôi viết vào #99 và #101 thực chất là
**một kiểu chạy hai lần** — bằng chứng độc lập thứ tự ở hai vé đó yếu hơn tôi tưởng. Agent #101 nêu
ra. → #106 thêm `--shuffle` / `--shuffle-seed=N` viết trong repo, in seed để tái hiện; #107 sửa lỗi
mà seed 777777 lộ ra.

Bài học: **một chỉ thị kiểm chứng cũng phải được kiểm chứng.** Cờ sai không báo lỗi thì bằng chứng
trông như thật.

## Agent bác lại tôi, và đúng

- **#98** — tôi gợi ý gom hai adapter về helper chung. Nó dẫn docstring của helper: nhánh bố cục mở
  rộng **không** đi qua đó, "dọn" như tôi bảo sẽ ghi đè provenance `MATCH_EXTENDED` thành
  `MATCH_KEYWORD` — hồi quy chứ không phải dọn. Nó cũng tìm ra **năm** tên nhãn trên màn cán bộ chứ
  không phải hai như vé viết.
- **#104** — tôi gợi ý chứng minh bằng "kích thước + một ô". Nó đo: hai lần dựng cùng workbook cho
  **cùng 4821 byte** mà khác byte, nên kích thước không phân biệt được. Dùng ô mốc.
- **#102** — tôi cho hai phương án. Nó loại phương án 1 vì vòng lặp import, rồi tìm tín hiệu tốt hơn
  cả hai: codebase **đã tự khai** khả năng có cổng qua kiểu trả về (`CheckResult` vs `list[Finding]`),
  đúng 3/16 mã. Guard đối chiếu hai chiều.
- **#93** — tôi viết sai tiền đề vé ("cột sổ rỗng cả 15 file"). PILOT_004 có **0** bản ghi file; 15
  là tổng của cả 7 DN.

## Cố ý không làm, có lý do

- **Không tự chạy lại kiểm tra sau khi nạp.** `run_checks` xoá rồi dựng lại `Finding` nên trạng thái
  và ghi chú cán bộ đã đánh bị về `new`. Phơi nhiễm hiện **bằng 0** (15.356 finding đều `new`), thành
  thật ngay khi thí điểm bắt đầu.
- **Không giấu điểm rủi ro khi kết quả cũ.** DN rơi khỏi bảng xếp hạng vì có người tải file lên là
  đúng sai lầm issue #65 — đánh dấu, không loại.
- **Không mở rộng khoá map cột ra liên DN.** Chữ ký cấu trúc không phải định danh đầy đủ của bố cục;
  tin nhau xuyên DN biến một lần xác nhận sai thành cột đọc lệch im lặng trên cả đội.

## Việc cần người chạy

1. **Merge PR #96 TRƯỚC, PR #105 SAU** — commit trang lỗi nằm ở cả hai.
2. **#93**: DB dev cần `alembic upgrade head` (đang ở `e2f3a4b5c6d7`, head là `f3a4b5c6d7e8`), và
   phải dựng `data/PILOT_004/2025/` trước khi gán lại sổ. Quy trình đầy đủ ở
   `docs/gan-lai-so-quyet-toan.md`, đã kiểm chứng end-to-end trên môi trường scratch.
3. **#108** còn mở: hai file test vá `app.database` không khôi phục — rò **im lặng**, không nổ.

## Số đo nền

`first_bcqt_year` rỗng **cả 7 DN** (chặn kỳ sớm nhất của mọi DN) · `audit_decision_date` rỗng cả 7
(màn phạm vi 5 năm 404 với mọi DN) · **52/170 trang tính vượt 40 cột**, rộng nhất 257 · 11/493 file
vượt 25MB · trích xuất lần đầu: xlsx 71,3MB **164,6 s** (vượt ngưỡng Cloudflare 100 s → phải có
trạng thái chờ), XML 64,5MB 5,4 s, xls 39,3MB 7,1 s; cửa sổ sau đó 2–5 ms · `row_count` ghi theo
LOẠI rồi chép lên mọi file cùng loại → hai file BCCT của một kỳ cùng mang 270.505 trong khi cả kỳ
có đúng 270.505 dòng.
