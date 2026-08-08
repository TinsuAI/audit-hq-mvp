# 02 — Bảng điểm (Dieter Rams, 0–3 mỗi nguyên tắc)

Luật đã áp: **chấm ca XẤU NHẤT, không chấm trung bình**; **phân vân thì lấy điểm thấp hơn**;
không trọng số, không điểm thưởng.

**1. Đổi mới — 2/3**
Bằng chứng: bảng gán cột chuyển vị hiện luôn dòng dữ liệu thật đọc qua cột đang chọn, cộng
thang bằng chứng theo từng cột (`evidence.py:45-51`) và cổng `not_evaluable` hai mức
(`sources.py:104-122`) — không thấy ở trình nhập liệu ETL thông thường.
Lý do không phải 3: đây là làm mới một khuôn mẫu đã có (màn ánh xạ cột), và điều kiện
"ships it with restraint" không đạt — 10 bộ từ vựng nhãn, 21 badge trên một màn (§A, §D).

**2. Hữu dụng — 2/3**
Bằng chứng: việc chính hoàn thành trong 5 bước; 8+ khi cổng cột bắn (§A).
Lý do không phải 3: bề mặt kế bên thêm bước — xác nhận lần đầu không kéo theo chạy check
(`companies.py:1680`) nên vẫn phải bấm riêng; và cả một tính năng làm nổi cột trên lưới
chết hẳn vì `cell-grid.js:486` bắt class không template nào phát.

**3. Thẩm mỹ — 1/3**
Bằng chứng: có hệ token (459 lần dùng `var(--c-*)`) nhưng bị vượt mặt ở quy mô lớn — 85
literal màu ngoài `:root`, 49 khai `font-size` lệch thang / 26 giá trị rời rạc, 15 giãn
cách lệch thang (§B).
Lý do không phải 2: mốc 2 là "≤2 điểm không nhất quán"; ca xấu nhất (bảng phát hiện) mã hoá
mức độ nghiêm trọng ba lần trên một dòng với hai bán kính bo cạnh nhau. Không phải 0 vì hệ
token có thật và phần lớn màn vẫn tuân theo.

**4. Dễ hiểu — 1/3**
Bằng chứng: `Khớp đẳng thức`, `Chỉ theo vị trí`, `Đã gán`/`Chưa gán` không có định nghĩa nào
ngay trên màn đang dùng; cẩm nang có nhưng không màn nào liên kết tới (§C).
Lý do không phải 0: hành động chính vẫn nhận ra được. Không phải 2 vì số nhãn mù vượt xa
mốc "1 điều khiển cần tooltip".

**5. Kín đáo — 1/3**
Bằng chứng: 21 badge cho 8 trường; `Đã gán` và `Đã kiểm` cùng `.badge.info`, cùng màu, cạnh
nhau ở MỌI cột (§D).
Lý do không phải 2: trang trí đang cạnh tranh với nội dung, không chỉ "hiện diện nhưng im".

**6. Trung thực — 0/3**  ← nguyên tắc chịu lực
Bằng chứng, đã tự kiểm lại chứ không tin subagent: (a) lời khai "Không có trong file" không
tới adapter — `grep -rn "absent" app/adapters/` trả **0**, `templates.py:210` luôn trộn lại
cột mặc định, nên cột đó vẫn nạp vào Tầng 1 trong khi check báo "chưa đánh giá được";
(b) gửi biểu mẫu từ file cũ **xoá sạch lời khai vắng đã lưu, không báo gì**
(`companies.py:1719` + `document_file.html:224` + `saved_map.py:101`); (c) "— chưa gán —"
bị gán lại âm thầm và giao diện quay về "Đã gán"; (d) "Đã kiểm" hiện cạnh "Chỉ theo vị trí".
Lý do là 0 chứ không phải 1: không có dark pattern thương mại nào, nhưng nguyên tắc này hỏi
"có hứa điều nó không làm không". Ở đây **lời khai của cán bộ bị hệ thống lặng lẽ phủ nhận,
và màn hình hiển thị điều ngược lại** — trong chính sản phẩm mà lý do tồn tại là không để
cán bộ bị dẫn dắt sai. Ba lời hứa sai đã kiểm chứng, ca xấu nhất là mất dữ liệu im lặng.

**7. Bền theo thời gian — 2/3**
Bằng chứng: navy + slate, không gradient thời thượng, không skeuomorph; nhưng emoji dùng làm
biểu tượng ở khắp nơi (8 nút công cụ, nút lưu hình đĩa mềm, dấu tick trên nút chính, §B).
Lý do: đúng 1 dấu hiệu lỗi thời → mốc 2.

**8. Kỹ tới chi tiết cuối — 1/3**
Bằng chứng: **disabled không có một rule nào** (ô khoá nhìn y hệt ô sửa được); `.empty-state`
có markup nhưng **không có rule CSS nào**; focus trên form dùng `outline:none` + box-shadow
tương phản **1.34**, dưới ngưỡng 3:1 (§B).
Lý do: 3 trạng thái thiếu hoặc thô → mốc 1.

**9. Thân thiện tài nguyên — 2/3**
Bằng chứng: 126 KB JS giải nén, **83% là thanh AI không dùng ở màn này**; `style.css` dùng
17,1%; `/jobs/unread.json` poll mỗi 10 giây vĩnh viễn; nhưng **0 animation lúc nghỉ** (§D).
Lý do: dưới 500 KB và chuyển động không chạy khi nghỉ → mốc 2; không phải 3 vì không có dark
mode và `prefers-reduced-motion` chỉ phủ 2/4 animation, 0/19 transition.

**10. Càng ít thiết kế càng tốt — 1/3**
Bằng chứng: 42 class CSS chết, 13 selector khai trùng giá trị xung khắc, một tính năng làm
nổi cột chết hoàn toàn, 4 cách render cùng một trường `col_`, 10 bộ từ vựng nhãn cho một
không gian khái niệm khoảng 3 (§A).
Lý do không phải 0: trang vẫn không bị trang trí lấn át. Không phải 2 vì số phần tử bỏ đi
được vượt xa mốc "≤2".

---

## Tổng: **13/30**
