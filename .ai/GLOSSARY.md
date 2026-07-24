# Glossary — Audit-HQ MVP

Ngôn ngữ chung của dự án. Chỉ định nghĩa thuật ngữ — không phải spec, không chi tiết cài đặt.
Định danh giữ tiếng Anh; prose tiếng Việt.

## Parse review (WS1)

**Evidence source** — nguồn bằng chứng cho việc gán MỘT cột đã đọc. Bốn nguồn, mạnh→yếu:
- `officer-confirmed` — cán bộ đã duyệt, hoặc có map đã lưu cho form này.
- `header-matched` — tiêu đề tại vị trí đó khớp nhãn mong đợi (pin đúng cột).
- `balance-checked` — đẳng thức cân đối của biểu khớp nếu lấy cột này. Đủ cho cột chỉ dùng dạng
  TỔNG; KHÔNG phân biệt hai cột cùng dấu.
- `position-only` — chỉ số cột cố định, không tín hiệu nào khác. Là phỏng đoán.

**Review state** — badge gộp evidence source về hai trạng thái cán bộ hành động:
- `verified` (xanh) — tin được, không cần làm gì.
- `needs_review` (vàng) — cột được một check tiêu thụ nhưng nguồn tốt nhất là `position-only`, hoặc
  dùng riêng lẻ mà chỉ có `balance-checked`. UI render tiếng Việt: "Đã kiểm" / "Cần xác nhận".

**Individually-consumed column** — cột một check đọc TRỰC TIẾP (không qua tổng cân đối), nên cần
`header-matched`/`officer-confirmed`. Ví dụ: `production_out` (C4.3, C5), `repurpose` (C1.x), cột con
export M15a (C1.4), cột ĐM thực tế M16 (C4.3). Đối lập: cột dùng dạng TỔNG (C2 tự tính lại) — chỉ
cần `balance-checked`.

**Form signature** — chữ ký CẤU TRÚC của một bố cục biểu. Hash = danh sách nhãn tiêu đề cột theo
thứ tự + số cột (gập hoa/dấu/khoảng trắng, bỏ chữ số năm) + dòng đánh số khi có; KHÔNG chứa mã DN.
Map đã xác nhận lưu theo `(DN, vân tay)` — tái dùng chéo NĂM trong cùng DN, KHÔNG chéo DN (option 2,
ADR #18 sửa ADR #15).

**File lifecycle** — trạng thái vòng đời một file đã tải, hiện trên UI: `uploaded` (đã lưu, chưa
đọc) → `analyzed` (dry-run parse xong, chưa ghi DB — cổng review ở đây) → `parsed` (đã commit dòng);
`error` nếu hỏng. `analyzed→parsed` tự động khi `verified`, dừng chờ bấm khi `needs_review`. Trục
RIÊNG với review state.

**Review gate** — điểm trong luồng upload hỏi cán bộ xác nhận map cột. Kích MỖI FILE khi có cột
`needs_review` chưa có map lưu. CẢNH BÁO (check vẫn chạy, finding vẫn hiện có cờ), không CHẶN.

**Check→column registry** — dict tĩnh khai mỗi check dùng cột/bảng nào + `consumed_as`
(`individual`|`sum`). Nền cho review gate và cho WS2/WS3.
