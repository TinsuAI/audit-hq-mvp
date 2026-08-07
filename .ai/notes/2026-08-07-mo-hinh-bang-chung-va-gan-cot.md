# Mô hình bằng chứng + gán cột — việc cho phiên sau

Owner nêu 2026-08-07 sau khi xem trang file trên prod. **Chưa làm gì. Cần grill trước khi code** —
đây là thiết kế lại cả logic lẫn giao diện, không phải một vé sửa lỗi.

Khởi nguồn: **issue #109** (Mẫu 16 đọc mã thành phẩm theo vị trí, không bằng chứng, không sửa được).
#109 là *một ca* của vấn đề chung dưới đây; đừng đóng #109 rồi tưởng xong.

## Ba việc owner yêu cầu

### 1. Rà lại toàn bộ, không riêng Mẫu 16

Mô hình bằng chứng (ADR #18) hiện phủ **không đều** giữa các biểu. Đã đo được ở Mẫu 16:
`evidence_m16` chỉ sinh bằng chứng cho `material_code` và `norm_qty`, trong khi adapter đọc và ghi
7 trường. Bốn trường (`product_name`, `product_unit`, `material_name`, `material_unit`) và quan
trọng nhất là **`product_code`** không có bằng chứng nào.

Phải rà **cả bốn slot** (m15 · m15a · m16 · bcct): với mỗi slot, liệt kê trường adapter ĐỌC, trường
có BẰNG CHỨNG, và chênh lệch. Chênh lệch chính là chỗ đọc sai im lặng được.

Manh mối đã có: `app/checks/registry.py:471` ghi chú vòng tránh cho đúng ca m16 — tìm xem còn ghi
chú vòng tránh nào tương tự không.

### 2. Cán bộ phải GÁN được trường ↔ cột, không chỉ "xác nhận"

Màn hiện tại chỉ cho sửa **chỉ số cột của những trường hệ thống đã biết**. Cán bộ không làm được:

- gán một trường mà hệ thống hoàn toàn không nhận ra ở file này;
- nói "cột này không phải trường nào cả";
- xử lý file mà thứ tự/tập cột lệch hẳn chuẩn.

Tức mô hình hiện tại giả định "hệ thống đã map gần đúng, cán bộ chỉ chỉnh". Ca thật vi phạm giả
định đó — và khi vi phạm thì **không có đường gỡ**, file kẹt vĩnh viễn (đã gặp đúng dạng này ở #95
với bố cục mở rộng).

Cần thiết kế lại thành: **bảng gán hai chiều** — mỗi trường hệ thống cần ↔ chọn cột nào trong file.

### 3. Thiếu trường bắt buộc thì phải CẢNH BÁO

Hiện không có khái niệm "biểu này cần đủ những trường nào". File thiếu hẳn một trường bắt buộc vẫn
nạp trôi, và hậu quả chỉ lộ ra ở tầng kiểm tra — hoặc không lộ.

Cần: khai **tập trường bắt buộc mỗi slot**, đối chiếu với tập gán được, thiếu thì cảnh báo ngay ở
màn gán cột chứ không đợi tới lúc chạy kiểm tra.

## Số đo đã có (đừng đo lại)

- Mẫu 16 bố cục cha-con, mã SP **điền xuôi** xuống các dòng NVL bên dưới (`app/adapters/m16.py:101`).
  Nên đọc lệch cột mã SP hỏng **cả nhóm**, không phải một ô.
- Dữ liệu hiện có: **4.613 mã thành phẩm → 270.385 dòng định mức**, trung bình **58,6 dòng/mã**.
- Bốn nhánh nghiệp vụ đứng trên `product_code` của m16: `effective_norms.py` · `norm_gate.py` ·
  `c4_norm.py` · `denominators.py` — tức định mức hiệu lực, cổng độ phủ ĐM, nhóm C4, mẫu số chấm điểm.
- Kho file thật: 493 file = 268 xlsx · 185 xls · **38 file đuôi `.xls` thật ra là XML SpreadsheetML** ·
  2 hỏng. **52/170 trang tính vượt 40 cột**, rộng nhất **257 cột** — bảng gán cột phải chịu được bề rộng đó.

## Ràng buộc phải giữ

- **Không gán cứng `HEADER_MATCHED` để cổng review khỏi bắn.** Tiêu đề không khớp thì `position-only`
  là câu trả lời đúng và cổng bắn là hành vi đúng. Đây là chỗ dễ "sửa" sai nhất.
- Giữ mô hình nguồn bằng chứng của ADR #18 (`officer-confirmed` > `header-matched` >
  `balance-checked` > `position-only`) — mở rộng chứ đừng thay.
- ADR #25: map cột diễn đạt được **nhóm cột** (`list[int]`) cho bố cục mở rộng; bảng gán mới phải
  chịu được một trường ↔ nhiều cột.
- Khoá map lưu là `(DN, slot, chữ ký cấu trúc)` và **cố ý không mở rộng liên DN** (ADR #24 mục 5).

## Bắt đầu từ đâu

`/grill-with-docs` trên chính ba mục trên. Đừng vào code trước — mục 2 và 3 đổi mô hình miền
(khái niệm "trường bắt buộc mỗi biểu" hiện **không tồn tại**), nên phải chốt từ vựng và ghi ADR
trước khi có gì để cài.
