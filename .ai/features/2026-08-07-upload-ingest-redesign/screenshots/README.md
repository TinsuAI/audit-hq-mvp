# Ảnh E2E — thiết kế lại luồng tải lên → nạp dữ liệu (#80)

Sinh bằng `ui_smoke.py` cạnh thư mục này, trên **dữ liệu bịa**.

- `01_man_du_lieu_mot_dn_moi_ky_la_dong.png` — #86+#87+#90 — một DN, mọi kỳ là dòng; đếm theo kiểm tra; vướng mắc xếp theo cách gỡ; tóm tắt theo loại + danh sách file thật
- `02_danh_sach_dn_danh_dau_ket_qua_cu.png` — #90 — điểm rủi ro vẫn nằm trong bảng xếp hạng, kèm dấu kết quả cũ; KHÔNG giấu số, KHÔNG loại DN khỏi bảng
- `03_man_phat_hien_danh_dau_ket_qua_cu.png` — #90 — màn phát hiện cũng đánh dấu, kèm nút chạy lại thủ công
- `04_trang_loi_tham_so_khong_hop_le.png` — #94 — tham số sai kiểu ra trang tiếng Việt, không phải JSON thô
- `05_trang_loi_khong_tim_thay.png` — #94 — mã DN không tồn tại; trước đây cũng đổ JSON thô
- `06_luoi_cuon_xem_truoc.png` — #83+#91 — lưới cuộn ảo, bỏ hạn mức 100 dòng / 40 cột / 25MB
- `07_hai_cong_tac_cot_va_cong_thuc.png` — #83+#91 — hai công tắc: cột hệ thống đang đọc, và công thức trong ô
- `08_xac_nhan_vi_tri_cot.png` — #84+#95 — màn xác nhận cột: map cán bộ thắng mẫu biểu theo từng trường, đẳng thức kiểm lại sau khi áp
