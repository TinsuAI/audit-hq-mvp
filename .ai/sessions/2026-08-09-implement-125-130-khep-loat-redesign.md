# Phiên 2026-08-09 — `/implement 125 → 130`, khép loạt redesign

**Vào phiên:** `main` = `668b6a2`, 7/13 vé của loạt #117 đã merge (#118–#124).
**Ra phiên:** 13/13 vé merge vào `main` **local**, **chưa push**. Bộ test 1.967 + 1 xfail.

Thứ tự làm: **125 → 127 → 128 → 126 → 130 → 129**. Đổi so với kế hoạch cũ
(`125 → 127 → 128 → 126 → 129` + #130 khi rảnh): #130 lên trước #129 vì #129 là vé bằng
chứng, và chụp ảnh trước khi #130 đổi màn dữ liệu thì ảnh stale ngay lúc chụp.

---

## Làm gì ở từng vé

**#125 — đường xác nhận.** Nhãn nút nêu đúng hai việc (ghi vị trí cột + nạp lại dữ liệu
CẢ KỲ), bỏ emoji. Cả hai đường thoát của lượt xác nhận và đường từ chối quay về TRANG
FILE; tiến độ lượt nạp in ngay ở đó. `ingest_status` nhận `reload_to` nên đích tải lại
khi nạp xong là màn đang xem — mặc định (dòng kỳ) sẽ kéo cán bộ khỏi trang vừa được đưa
về. "Kiểm tra chưa chạy" nói ở cả hai màn, một định nghĩa dùng chung (`checks_have_run`).

**#127 — xoá xác CSS.** 43 lớp + 5 tu chỉnh không nơi nào phát ra: xoá. 3 selector khai
trùng giá trị xung khắc: gộp. Bia mộ + bất biến "một bộ chọn, một khai" trong
`test_static_assets.py`.

**#128 — token hoá.** Màu literal ngoài `:root` **85 giá trị → 0**. `font-size` bám thang,
0 khai dưới sàn 12px.

**#126 — nợ tiếp cận.** Skip-link ở mọi trang, `<main>` có `id` + `tabindex="-1"`. Thanh
trợ lý khai `inert` đi cặp `aria-hidden`. Trang file bỏ thanh trợ lý (−104.257 B JS).

**#130 — nghĩa nguồn bằng chứng ở màn dữ liệu.** Bỏ `title`, đưa nghĩa thành chữ, đi theo
NGUỒN chứ không theo cột (11 cột nhưng chỉ 5 nguồn).

**#129 — bằng chứng feature.** `brief.md` + `ui_smoke.py` + 5 ảnh khung nhìn, 30 phép đo
trong Chromium. Chạy lại audit, ghi số làm thông tin.

---

## Review hai trục bắt LỖI THẬT ở bốn vé

Không phải khoản trình bày — bốn cái này đều sai hành vi:

1. **#127 · `.data-table .date` KHÔNG chết.** Tên `date` là phần tử thứ ba của `view_cols`
   trong `companies.py`, ra màn qua `<td class="{{ cls }}">`. Năm kênh quét chỗ gán class
   (`class=`, `classList`, `{ class: … }`, `className`, tham số class) không kênh nào
   thấy được một tên nằm trong dữ liệu Python. Xoá rule đi là cột "Ngày" ở màn dữ liệu
   BCCT và mọi khối bằng chứng phát hiện mất `tabular-nums`, `nowrap`, màu chữ phụ.
   Câu "0 chỗ còn phát ra một class đã xoá" ở commit đầu là SAI — đúng là 42/43.
   Vá: khôi phục rule + `test_table_cell_classes_from_python_data_have_a_rule` hỏi thẳng
   `_TABLE_CONFIG`. Đo bằng đột biến: xoá rule thì test đỏ đúng chỗ.

2. **#126 · `closePanel` làm rơi focus.** Khai `inert` trong lúc focus còn TRONG thanh →
   trình duyệt đẩy focus về `<body>` → vòng tab quay lại đầu trang. Bấm Escape là mất chỗ
   đang đứng, đúng thứ vé đi sửa. Vá: trả focus về `#ai-fab` TRƯỚC khi khai `inert`; test
   khẳng định cả THỨ TỰ hai lời gọi.

3. **#130 · dòng "Nhãn vàng" hiện vô điều kiện.** File mà mọi cột đủ căn cứ vẫn in một
   đoạn tả cái chip vàng không có trên màn. Gate lại — và lượt gate lộ tiếp: chip vàng bật
   theo TỪNG CỘT chứ không theo cờ mức file, hai thứ lệch nhau được.

4. **#125 · test dò chuỗi tiếng Việt.** AC 7 của chính vé ghi "câu chữ tiếng Việt của nhãn
   nút KHÔNG khẳng định bằng test", mà tôi viết bốn khẳng định dò chuỗi. Thay bằng
   `data-checks-run` và đường đi của chuỗi từ chối.

---

## Chỗ tôi suy luận SAI, và cách nó bị lật

**#128 — đơn vị đếm.** Tôi đọc mốc "85 literal" của vé là LẦN XUẤT HIỆN, đo trên `main`
ra 177, kết luận "mốc đã stale vì #118–#127", rồi đặt trần ở 30. Trục Spec đo lại theo
GIÁ TRỊ RỜI RẠC kể cả `rgba()`: **đúng 85, và 18 trùng khít token** — khớp cả hai con số
vé ghi. Tức mốc không hề stale, và đích là 85 − 85 = **0**, không phải 92. Tôi đo lại độc
lập, xác nhận, rồi quét nốt 45 giá trị còn lại. Bài học: khi con số của vé không khớp
phép đo của mình, thử đơn vị đếm khác TRƯỚC khi kết luận vé sai.

**#127 — "44 lớp chết vì #118–#124 khai tử thêm".** Suy đoán, không đo. Đối chiếu tập
class phát ra ở `388cb06` với `main`: đúng MỘT tên (`danger`), và vé giữ nó lại. Chênh
lệch 42 → 44 là do cách đếm (38 tên + 5 tu chỉnh + `danger`).

**#126 — "không đo được phần CDN".** Đo được, một lệnh `curl`: 38.701 + 21.531. Cộng vào
thì con số của vé (103.616 B) chính xác tới byte.

---

## Quyết định đã chốt

- **Tiến độ lượt nạp dùng chung một bản dựng** (`_ingest_slot.html`) cho dòng kỳ và trang
  file; bộ đếm poll đọc địa chỉ TRÊN CHÍNH KHỐI (`data-ingest-url`), dựng sẵn ở máy chủ.
  Ghép địa chỉ trong JS thì mỗi màn thêm một tham số là một nhánh nữa.
- **Điểm cuối trạng thái nhận SỐ HIỆU file, không nhận địa chỉ** — giá trị đó đi thẳng
  vào `location.replace`.
- **`--p-*` là bảng màu THÔ, tách khỏi `--c-*`**: `--c-*` nói vai trò, `--p-*` chỉ đặt tên
  cho giá trị chưa có vai trò. Gộp hai họ xám (slate của `--c-*` và gray) là ĐỔI MÀU trên
  màn, không làm ở vé token hoá.
- **Sắc thái cảnh báo KHÔNG dùng để đánh dấu nguồn yếu** ở màn dữ liệu:
  `balance-checked` cho ra cột `verified` (chip xanh) ở năm trường Mẫu 15, tô nó vàng ở
  danh sách nghĩa là một màn hai nghĩa cho cùng một màu.
- **Chấm lại audit là THÔNG TIN**: 13/30 → 24/30 là hai model chấm hai lần, không phải
  hai phép đo. Bảng 21 dòng số đo mới là phần đọc được.

---

## Cách đo đã dùng, để lần sau chép lại

- **Token hoá không đổi pixel:** phân giải màu của TỪNG khai (đi hết chuỗi `var()`, cả
  fallback, cả alpha) ở `main` và ở HEAD rồi so — 613 khai có màu ở cả hai, 0 khai đổi.
- **Lớp CSS chết:** dò theo chỗ class THẬT SỰ được gán, và bổ sung một phép hỏi thẳng
  cấu hình Python. Dò tên trên toàn văn bản sai cả hai chiều.
- **Đột biến để kiểm test:** mọi bất biến mới đều thử một phép đột biến và xác nhận đỏ
  đúng chỗ.

---

## Vấp phải

- **`rm -f "$SCRATCH"/t.sqlite*` với glob không khớp làm zsh HUỶ nguyên lệnh** nhưng lệnh
  sau vẫn chạy → DB scratch của lượt trước còn nguyên → **13 test đỏ giả**. Chạy lại với
  ba tên tường minh thì xanh. Đúng lớp bẫy đã ghi trong memory; lần này nó làm đỏ giả chứ
  không xanh giả.
- **Một subagent để lại `tests/test_zz_measure_tmp.py`** trong cây làm việc. Xoá trước khi
  commit. Nhớ soát `git status` sau mỗi lượt gọi agent đo đạc.
- **`ui_smoke.py` không mở được thanh trợ lý** vì `sidebar.js` `init()` thoát sớm khi
  `/api/ai/meta` trả `enabled=false`. Bật cấu hình AI trong DB throwaway; không có lượt
  gọi LLM nào (phần đo chạy đồng bộ trước mọi `await` của `openPanel`).

---

## Còn mở

- **Chưa push.** `git push` = deploy lên prod. Loạt này không migration.
- **Chưa đóng vé** #118–#128, #130, #117 trên tracker.
- **Nợ chưa thành vé:** `var(--border)` / `var(--radius)` ở khối `.apex-*` trỏ tới token
  không tồn tại ở bất kỳ file nào được nạp → khối đó render không viền, bo góc 0. Sửa là
  đổi hình dạng trên màn nên phải tách vé.
- **21 vé cũ của PR #105** (#81–88, #91–93, #95, #97, #99–104, #107–108) vẫn mở trên
  tracker dù đã ship — quyết định soát-rồi-đóng hay sửa câu chữ STATUS vẫn treo.
