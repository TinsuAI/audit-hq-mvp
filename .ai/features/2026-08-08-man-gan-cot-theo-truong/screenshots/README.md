# Ảnh E2E — màn gán cột theo trường khai (#112)

Sinh bằng `ui_smoke.py` cạnh thư mục này, trên **dữ liệu bịa**.

- `01_man_gan_cot_theo_truong_khai.png` — #112 — một dòng mỗi TRƯỜNG KHAI của biểu (8 dòng cho Mẫu 16), kể cả trường máy không đặt được; nhãn khoá dòng / bắt buộc theo biểu
- `02_bo_chon_cot_kem_tieu_de_va_mau_gia_tri.png` — #112 — mỗi lựa chọn là «cột N · tiêu đề · mẫu giá trị», chọn bằng mắt thay vì đếm cột
- `03_xac_nhan_truong_khong_co_trong_file.png` — #112 — trạng thái thứ ba: cán bộ xác nhận trường không có trong file, cảnh báo thiếu trường có đường đóng
- `04_sau_khi_xac_nhan_vang.png` — #112 — sau khi lưu: trường mang trạng thái “Không có trong file”, bền vững ở saved_column_maps.absent_fields
