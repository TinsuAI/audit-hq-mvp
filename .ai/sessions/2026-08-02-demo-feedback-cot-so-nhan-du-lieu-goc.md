# 2026-08-02 — Ba phản hồi sau demo: cột số, nhãn tiếng Việt, link dữ liệu gốc

Nhánh `feat/finding-columns-raw-data` (tách từ `main` @ `0b9e3b2`), 4 commit,
**chưa push, chưa merge, chưa deploy**. 956 test xanh, ruff sạch.

## Yêu cầu

Tú Anh đi demo về, ba phản hồi:

1. Cán bộ ngồi nhìn số trên hệ thống vẫn phải bật Excel lên kiểm xem có đúng không
   → cần link thẳng vào dữ liệu gốc trên hệ thống, mã đã lọc sẵn theo năm. Trang
   chi tiết từng mã đã nhiều thông tin nhưng cần hữu ích hơn; view dữ liệu gốc cần
   đa năng hơn.
2. Mô tả lặp đi lặp lại, mã đã có ở cột "Đối tượng" mà mô tả nhắc lại, các số nằm
   trong chuỗi mô tả nên đọc rất khó → tách số ra các cột tương ứng.
3. Rà lại toàn bộ nhãn hiển thị: phải là tên tiếng Việt chứ không phải tên biến /
   tên cột; phần trăm phải có `%`, tiền tệ phải có đơn vị, số lớn phải có phân cách
   theo cấu hình.

## Quyết định đã chốt với owner trước khi code

| Quyết định | Chốt |
|---|---|
| Quy ước số | Mặc định kiểu VN `1.234,56`, có setting admin đổi sang `1,234.56` |
| Cột "Mô tả" trong bảng phát hiện | **Bỏ hẳn** — bảng gom theo check nên mô tả giống nhau mọi dòng |
| Phạm vi màn dữ liệu gốc | Bộ lọc đầy đủ + cột nguồn file + link sâu |
| Nhánh | Nhánh mới từ `main`, chấp nhận conflict với `feat/adr23-ktstq-period-scope` sau này |

## Đã làm

**`app/formatting.py`** — một chỗ duy nhất quyết định dấu phân cách. Ba loại số ba
luật riêng: `qty` bỏ `,00` khi tròn và giữ 6 chữ số có nghĩa khi rất nhỏ; `pct` luôn
kèm dấu và `%`; `money` không phần thập phân, luôn kèm mã tiền tệ. Setting
`number_format` trong `app_settings`, trang `/admin/hien-thi`.

**`app/checks/detail_labels.py`** — nhãn tiếng Việt + kiểu định dạng cho từng khoá
`finding.details`, bảng tra giá trị enum, và **bộ cột cho từng check**. Bảng phát
hiện gọi `finding_columns(code)` / `finding_cells(code, details)` để dựng cột động
theo nhóm.

**Link dữ liệu gốc** — từ mỗi dòng phát hiện, mỗi khối chứng cứ, mỗi khối trên trang
chi tiết mã. Màn dữ liệu gốc thêm lọc số tờ khai / loại hình (nhận cả tập) / khoảng
ngày / sổ, giữ bộ lọc khi đổi tab, thêm cột `Nguồn file`.

**E2E** — `.ai/features/2026-08-02-finding-columns-raw-data/` (brief + `ui_smoke.py`
+ 9 ảnh), server throwaway 8332, tự dọn, kill theo PID.

## Bắt được cái gì trong lúc làm

**1. Tiêu đề cột C1.1 nói sai về con số nằm dưới nó.** Test AST bắt hai khoá chưa có
nhãn: `m15_column` / `m15a_column` (thêm ở `0b9e3b2`), giá trị là **tên cột DB**
(`import_qty`, `production_out_qty`). Đọc ra thì với DN thuê gia công ở nước ngoài,
cột M15 đem đối chiếu là `xuất kho để sản xuất` chứ không phải `nhập trong kỳ`
(`company_type.py:PAIRING`) — nghĩa là tiêu đề "M15 nhập" đặt trên con số lấy từ cột
khác. Đổi tiêu đề C1.1/C1.3 thành "Số M15 đối chiếu" và thêm cột nêu tên cột thật.

**2. `recompute_company_year` nuốt mất trạng thái cán bộ vừa ghi.**
`test_update_finding_status_persists_status_and_notes` đỏ sẵn trên `main` từ trước
session này. Nguyên nhân: `tier_for` → `get_tiers()` không truyền db, cache trống thì
tự mở `SessionLocal()`; session lồng đó `close()` phát ROLLBACK. Khi hai session dùng
chung một connection (SQLite in-memory + StaticPool) thì UPDATE đang treo bị huỷ theo.
**Sản phẩm chạy pool thường nên mỗi session một connection → không dính**; nhưng
pattern "hàm setting tự mở session giữa transaction của caller" là thật và còn ở
`get_combos_enabled`, `get_number_format`. Sửa bằng cách nạp cache bằng chính session
của caller trước khi chấm điểm, kèm test hồi quy gọi thẳng hàm.

**3. Bảng C2.1 tràn ngang, nút thao tác bị đẩy khỏi màn hình.** Ảnh E2E bắt được.
Bản đầu trải trọn phương trình cân đối thành 10 cột số → 14 cột. Rút còn `tồn cuối DN
khai / tồn cuối tính lại / chênh lệch / tồn ảo`; đầu vào vẫn đủ ở trang chi tiết.

**4. `ui_smoke.py` để lại setting bẩn giữa hai lượt.** Ảnh 09 ghi `number_format=en`
mà `_purge` không xoá → lượt sau ra số kiểu Anh ở toàn bộ ảnh. Xoá thẳng trong DB
cũng chưa đủ vì server là process riêng, cache 30s — phải đặt lại **qua giao diện**.

## Không làm được / cố ý không làm

- **`finding.title` giữ nguyên**, không sửa cách sinh tiêu đề trong các check. Tiêu đề
  đã lưu trong DB, đổi cách sinh thì phải chạy lại toàn bộ kiểm tra mới cập nhật, mà
  `title` còn là đầu vào của tìm kiếm, công cụ AI và `ai/overview.py` (gom theo title).
  Bảng bỏ cột mô tả là việc ở tầng render; trang chi tiết vẫn in tiêu đề gốc.
- **Ảnh E2E chụp trên dữ liệu seed**, chứng minh cách render — không chứng minh
  adapter đọc đúng cột từ file Excel thật.
- Cột `m15_column` sẽ hiện `—` trên các finding chạy TRƯỚC `0b9e3b2` (DB local đang
  vậy). Chạy lại kiểm tra thì đầy.

## Việc còn mở

1. **Chưa push / chưa mở PR / chưa deploy.**
2. Nhánh này tách từ `main` nên **sẽ conflict với `feat/adr23-ktstq-period-scope`**
   ở `app/routes/companies.py`, `company_detail.html`, `finding_detail.html` — owner
   đã biết và chấp nhận khi chọn nhánh.
3. `app/adapters/bcct.py` **vẫn chưa commit** (+71 dòng, dò cột theo nhãn tiêu đề).
   Việc khác, session này không đụng vào.
4. Bản xuất Excel kiến nghị (`app/pipeline/export.py`) **chưa** dùng lớp `fmt_*` và
   chưa tách số ra cột — cùng vấn đề, khác mặt trận.
5. `get_combos_enabled` / `get_number_format` vẫn theo pattern "tự mở session khi
   cache trống". Ở đường render (sau commit) thì vô hại, nhưng nếu có nơi gọi giữa
   transaction ghi thì lại đúng lỗi #2.
