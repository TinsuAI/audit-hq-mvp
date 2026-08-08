# 03 — Phán quyết: **REDESIGN**

**Một câu:** Luồng cán bộ đạt **13/30** và nguyên tắc chịu lực **#6 Trung thực chấm 0** —
lời khai của cán bộ về file bị hệ thống lặng lẽ phủ nhận ở ba đường khác nhau — nên phải
thiết kế lại từ mục đích, không phải chỉnh sửa.

Luật của skill bắn **cả hai** cửa: tổng < 20 **và** một nguyên tắc chịu lực chấm 0.

## Vì sao REDESIGN chứ không REFINE

Không phải vì màn nào xấu. Vì **mô hình tương tác đang mâu thuẫn với mô hình dữ liệu**:
màn gán cột mời cán bộ phát biểu ba trạng thái về từng trường, nhưng tầng adapter chỉ biết
đúng một trạng thái ("cột nào cho trường nào"). Hai trạng thái còn lại — *chưa gán* và
*xác nhận vắng* — không có đường xuống tới chỗ đọc file, nên chúng bị nuốt. Đó là lỗi tầng
kiến trúc giao diện, không sửa được bằng cách đổi CSS.

**Không phải lý do**: codebase to, hay đã bỏ nhiều công. Đó là chi phí chìm, không phải
nguyên tắc thiết kế.

## Giữ lại — phần này TỐT, đừng đụng

- **Mô hình miền ở backend**: ADR #18 (thang bằng chứng theo cột), #23/#24 (cổng nguồn,
  lớp cách gỡ), #25 (nhóm cột), #28 (tập trường khai). Đây là thứ làm sản phẩm có giá trị.
- **Cổng `not_evaluable` hai mức** (`app/checks/sources.py:104-122`) — cơ chế đúng, chỉ
  thiếu vế adapter.
- **Đạo đức câu chữ**: 0 thổi phồng, 0 dark pattern trên 1.155 chuỗi; điểm rủi ro tự hạ
  thấp đúng mực (`companies_list.html:65`); `base.html:108` khẳng định quyết định thuộc
  cán bộ. Giữ nguyên giọng này.
- **Ý tưởng bảng chuyển vị** hiện dòng dữ liệu thật đọc qua cột đang chọn — giữ ý, dựng lại
  cách thể hiện.

## Năm việc đòn bẩy cao nhất

1. **#6 Trung thực — đưa ba trạng thái xuống tới adapter.** `absent_fields` phải tới
   `parse_m15/m15a/m16/bcct` và loại cột đó khỏi map đọc; *chưa gán* phải bền vững thay vì
   bị `resolve_columns` trộn lại cột mặc định. Bằng chứng: `grep -rn "absent" app/adapters/`
   → 0; `app/adapters/templates.py:210`.
2. **#6 Trung thực — bịt đường xoá âm thầm.** Chỉ ghi `absent_fields` khi biểu mẫu thật sự
   có dựng ô đó; nếu không thì giữ nguyên giá trị đã lưu. Bằng chứng:
   `app/routes/companies.py:1719` + `app/templates/document_file.html:224` +
   `app/pipeline/saved_map.py:101`.
3. **#4 Dễ hiểu + #5 Kín đáo — gộp 10 bộ từ vựng nhãn xuống còn 3.** Một trục "cột nào",
   một trục "chắc tới đâu", một trục "còn việc gì phải làm". `Đã gán` và `Đã kiểm` đang
   cùng một màu xanh cạnh nhau ở mọi cột. Bằng chứng: `01-evidence.md` §A mục 10 bộ từ vựng;
   `app/pipeline/file_page.py:81-85` + `app/adapters/evidence.py:45-56`.
4. **#8 Kỹ tới chi tiết — dựng trạng thái disabled và empty, sửa vòng focus.** Hiện
   `:disabled` không có một rule nào, `.empty-state` không có rule nào, và vòng focus của
   form tương phản 1.34 (ngưỡng 3:1). Bằng chứng: `01-evidence.md` §B bảng trạng thái;
   `app/static/style.css:846-850`.
5. **#3 Thẩm mỹ + #10 Ít mà tốt — ép về hệ token và dọn xác.** 85 màu literal ngoài
   `:root`, 49 `font-size` lệch thang, 42 class chết, 13 selector khai trùng xung khắc, một
   tính năng làm nổi cột chết hẳn. Bằng chứng: `01-evidence.md` §B, §A;
   `app/static/cell-grid.js:486`.

## Phạm vi thiết kế lại

**Trong phạm vi:** màn gán cột, lưới xem trước, và hệ nhãn/badge dùng chung trên toàn luồng.
**Ngoài phạm vi:** mô hình kiểm tra, thang điểm rủi ro, catalog check, thanh AI.
