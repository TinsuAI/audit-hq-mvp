# Phương pháp tính điểm rủi ro dữ liệu BCQT

> **Tóm tắt:** Audit-HQ tính một chỉ số rủi ro từ 0 đến 1000 cho mỗi cặp (Doanh nghiệp, Năm tài chính), dựa trên các phát hiện chênh lệch nội bộ giữa các thành phần của Báo cáo Quyết toán (BCQT) — gồm Mẫu 15 (cân đối nguyên vật liệu), Mẫu 15a (cân đối thành phẩm), Mẫu 16 (định mức thực tế) — và đối chiếu với Bộ chứng từ Tờ khai (BCCT). Chỉ số được **chuẩn hoá theo tỷ lệ**, không cộng dồn theo số lượng phát hiện, nhằm loại bỏ thiên lệch quy mô doanh nghiệp.

---

## 1. Mục đích

Audit-HQ phân tích chất lượng dữ liệu hồ sơ hải quan của doanh nghiệp và phát hiện các chênh lệch có thể là dấu hiệu rủi ro nghiệp vụ. Hệ thống thực hiện các phép kiểm tra trong danh mục triển khai (MVP) trên dữ liệu đầu vào — gồm các mẫu thành phần của Báo cáo Quyết toán (Mẫu 15, Mẫu 15a, Mẫu 16) và Bộ chứng từ Tờ khai — sinh ra danh sách phát hiện kèm mức độ nghiêm trọng. Điểm rủi ro dữ liệu là cách tổng hợp các phát hiện đó thành một con số duy nhất để cán bộ Hải quan dễ so sánh và sắp xếp ưu tiên kiểm tra.

**Phạm vi:** Đây là chỉ số rủi ro về **chất lượng dữ liệu báo cáo**, không phản ánh mức tuân thủ pháp luật của doanh nghiệp. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan, thực hiện theo Thông tư 81/2019/TT-BTC.

---

## 2. Mức độ nghiêm trọng của phát hiện

Mỗi phát hiện thuộc một trong ba mức:

| Mức | Ký hiệu | Điểm | Ý nghĩa |
|---|---|---|---|
| Nghiêm trọng | 🔴 | 10 | Chênh lệch lớn, có khả năng cao là sai phạm hoặc gian lận. Ví dụ: tồn cuối NVL âm; có tờ khai nhập nhưng không có trên Mẫu 15. |
| Cảnh báo | 🟡 | 3 | Chênh lệch ở mức cần lưu ý, có thể do sai sót nghiệp vụ hoặc do bản chất số liệu. Ví dụ: lệch số lượng 5–20%; mã HS không nhất quán giữa các tờ khai. |
| Thông tin | 🔵 | 1 | Chênh lệch nhỏ, ghi nhận để theo dõi. Ví dụ: lệch số lượng dưới 5%; đơn vị tính khác họ nhưng cùng quy đổi. |

Các phát hiện do cán bộ Hải quan đánh dấu **Loại trừ** sẽ không được tính vào điểm.

---

## 3. Công thức tính điểm — từng phép kiểm tra

Mỗi phép kiểm tra được tính điểm độc lập theo công thức:

```
điểm phát hiện  = tổng điểm mức của mọi phát hiện còn hiệu lực của phép kiểm tra
số đối tượng    = số mã thuộc phạm vi kiểm tra (mã NVL / mã TP / mã định mức)
điểm tối đa     = 10 × số đối tượng     (giả định mọi phát hiện đều ở mức Nghiêm trọng)
tỷ lệ           = giá trị nhỏ hơn giữa 1 và (điểm phát hiện ÷ điểm tối đa)
điểm kiểm tra   = tỷ lệ × 10
```

### Giải thích

- **Mỗi phép kiểm tra đóng góp tối đa 10 điểm** vào tổng điểm doanh nghiệp, bất kể số phát hiện thực tế là bao nhiêu.
- **Tỷ lệ** là một số trong khoảng từ 0 đến 1, thể hiện mức độ rủi ro tương đối: bằng 1 nghĩa là mọi đối tượng trong phạm vi đều có phát hiện ở mức nghiêm trọng nhất; bằng 0 nghĩa là không có phát hiện nào.
- **Số đối tượng (mẫu số)** được tính riêng cho từng phép kiểm tra theo phạm vi nghiệp vụ. Ví dụ:
  - Phép kiểm tra cân đối NVL (C2.1): mẫu số là số mã NVL khác nhau có trong Mẫu 15 hoặc BCCT.
  - Phép kiểm tra xuất thành phẩm (C1.4): mẫu số là số mã thành phẩm khác nhau có trong Mẫu 15a hoặc phía xuất của BCCT.
  - Phép kiểm tra định mức (C4.1, C4.3): mẫu số là số mã NVL có trong Mẫu 16.
- **Nếu mẫu số bằng 0** (doanh nghiệp không có dữ liệu trong phạm vi của phép kiểm tra), điểm của phép kiểm tra đó bằng 0.

### Vì sao chuẩn hoá theo tỷ lệ?

Cách cộng dồn theo số lượng (ví dụ: mỗi phát hiện nghiêm trọng 10 điểm rồi cộng tất cả) sẽ ưu tiên doanh nghiệp có quy mô dữ liệu lớn một cách bất hợp lý. Một doanh nghiệp có 500 mã NVL với tỷ lệ lỗi 10% sẽ có 50 phát hiện, tương đương 500 điểm; trong khi doanh nghiệp 50 mã có cùng tỷ lệ lỗi 10% chỉ có 5 phát hiện, tương đương 50 điểm. Hai trường hợp có chất lượng dữ liệu tương đương nhưng điểm cách nhau 10 lần.

Cách tính theo tỷ lệ triệt tiêu thiên lệch này: cả hai doanh nghiệp đều có tỷ lệ 0,1 và đều được 1,0 điểm cho phép kiểm tra đó.

Đây cũng là nguyên tắc mà Tổ chức Hải quan Thế giới (WCO) và các chương trình Doanh nghiệp ưu tiên (AEO) của Liên minh Châu Âu, Hoa Kỳ áp dụng: đánh giá tuân thủ dựa trên **tỷ lệ vi phạm trên tổng giao dịch**, không dựa trên số tuyệt đối.

---

## 4. Điểm rủi ro tổ hợp

Một số tổ hợp phát hiện cùng xuất hiện trên một mã vật tư có ý nghĩa nghiệp vụ lớn hơn tổng các phát hiện riêng lẻ — chúng là dấu hiệu đặc trưng của một số hành vi rủi ro. Khi hệ thống nhận diện ít nhất một tổ hợp như vậy, **cộng thêm 20 điểm** vào tổng điểm thô. Điểm này chỉ tính một lần, không nhân theo số lần hay số loại tổ hợp.

Các tổ hợp hệ thống hiện nhận diện:

| Tổ hợp | Dấu hiệu kết hợp (trên cùng một mã) | Nghi vấn nghiệp vụ |
|---|---|---|
| Định mức ảo | Tồn cuối âm (C2.3) **+** tiêu hao Mẫu 16 vượt xuất sản xuất Mẫu 15 (C4.3) | Tạo định mức ảo để hợp thức hoá NVL nhập miễn thuế nhưng thực tế đã bán nội địa. |
| NVL nội địa không khai báo | Nhập trên Mẫu 15 không có tờ khai (C1.3) **+** xuất sản xuất không có nguồn nhập/tồn (C5.1) | Dùng NVL mua trong nước không khai báo, đưa vào phạm vi hàng miễn thuế. |
| Số liệu mâu thuẫn | Phương trình cân đối Mẫu 15 không khớp (C2.1) **+** tiêu hao Mẫu 16 vượt Mẫu 15 (C4.3) | Số liệu giữa các mẫu báo cáo không nhất quán; cần làm rõ nguồn sai trước khi xét các phát hiện khác. |
| Phân loại sai có chủ đích | Mã HS không nhất quán (C3.2) **+** đơn vị tính lệch giữa Mẫu 15 và BCCT (C3.3) | Có thể cố tình đổi mã HS hoặc đơn vị tính để né chính sách quản lý hàng hoá. |

> **Danh mục tổ hợp sẽ tiếp tục được bổ sung.** Bốn tổ hợp trên là bộ khởi đầu, rút ra từ các kịch bản rủi ro phổ biến. Trong quá trình sử dụng, cán bộ Hải quan có thể đề xuất thêm các tổ hợp dấu hiệu mới theo kinh nghiệm thực tế để hệ thống nhận diện — đây là phần được thiết kế để mở rộng dần.

---

## 5. Quy đổi sang thang 0–1000

Tổng điểm thô của một cặp (Doanh nghiệp, Năm) được quy đổi sang thang 0–1000:

```
điểm thô         = tổng điểm kiểm tra của các phép + điểm rủi ro tổ hợp
điểm thô tối đa  = (số phép kiểm tra được tính điểm) × 10 + 20
                 = 17 × 10 + 20 = 190
điểm chuẩn hoá   = làm tròn( 1000 × điểm thô ÷ điểm thô tối đa )
```

Kết quả là một số nguyên trong khoảng từ 0 đến 1000. Hiện hệ thống tính điểm trên **17 phép kiểm tra**; khi bổ sung hoặc bớt phép kiểm tra, điểm thô tối đa được cập nhật tương ứng.

---

## 6. Phân loại 5 mức cảnh báo

Để dễ đọc, điểm chuẩn hoá được ánh xạ sang một trong năm nhãn theo các ngưỡng điểm. **Ngưỡng do quản trị viên cấu hình** tại trang Ngưỡng hạng rủi ro; thay đổi ngưỡng có hiệu lực ngay khi xem, không cần chạy lại kiểm tra. Mặc định, các ngưỡng như sau:

| Khoảng điểm | Nhãn | Màu sắc | Ý nghĩa |
|---|---|---|---|
| 0 – 50 | Dữ liệu nhất quán | 🟢 Xanh lá | Không có hoặc rất ít chênh lệch. Hồ sơ tương đối sạch. |
| 51 – 100 | Có chênh lệch nhỏ | 🟢 Xanh-vàng | Chênh lệch ở mức bình thường của nghiệp vụ xuất nhập khẩu. Ghi nhận, không cần ưu tiên kiểm tra. |
| 101 – 300 | Cần rà soát | 🟡 Vàng | Có nhiều chênh lệch hoặc một số chênh lệch nghiêm trọng. Đề nghị cán bộ rà soát kỹ. |
| 301 – 600 | Có dấu hiệu bất thường | 🟠 Cam | Tỷ lệ phát hiện cao, nhiều phát hiện ở mức nghiêm trọng. Đề nghị tăng cường kiểm tra. |
| 601 – 1000 | Bất thường nghiêm trọng | 🔴 Đỏ | Hồ sơ có dấu hiệu rất bất thường, đề nghị kiểm tra sau thông quan hoặc thanh tra. |

**Lưu ý quan trọng:** 5 nhãn trên là chỉ số nội bộ của Audit-HQ về chất lượng dữ liệu BCQT. **Không phải** 5 Mức tuân thủ theo Thông tư 81/2019/TT-BTC (Doanh nghiệp ưu tiên, Tuân thủ cao, Tuân thủ trung bình, Tuân thủ thấp, Không tuân thủ) — vốn dựa trên hồ sơ vi phạm pháp luật thực tế của doanh nghiệp và do hệ thống của Tổng cục Hải quan tự động đánh giá vào 00 giờ hằng ngày.

---

## 7. Điểm tổng của doanh nghiệp

Doanh nghiệp có dữ liệu nhiều năm sẽ có một điểm cho mỗi năm. Trên trang danh sách doanh nghiệp, hệ thống hiển thị **điểm tổng = điểm cao nhất trong các năm** để cán bộ Hải quan nhận biết năm nào cần lưu ý nhất.

Trên trang chi tiết doanh nghiệp, điểm và nhãn được hiển thị theo từng năm để cán bộ theo dõi xu hướng.

---

## 8. Đảm bảo tính minh bạch và truy nguyên

- **Mỗi phát hiện** đều truy nguyên được về dòng dữ liệu gốc ở Tầng 1 (Mẫu 15, Mẫu 15a, Mẫu 16, BCCT). Cán bộ Hải quan có thể bấm từ một phát hiện để xem ngay dòng dữ liệu gốc và tự xác minh.
- **Cách tính điểm của từng phép kiểm tra** được lưu lại chi tiết cùng mỗi điểm năm, có thể tra cứu lại bất cứ lúc nào khi cần kiểm chứng.
- **Mọi thay đổi điểm** đều phát sinh từ việc chạy lại kiểm tra. Hệ thống lưu lịch sử các lần chạy để đối chiếu.

---

## 9. Hạn chế đã biết

1. **Chỉ phản ánh dữ liệu doanh nghiệp khai báo:** Nếu doanh nghiệp không khai báo đầy đủ (ví dụ thiếu Mẫu 16), một số phép kiểm tra không có cơ sở để chạy. Điểm thấp không đồng nghĩa hồ sơ sạch.
2. **Trọng số ba mức (10 / 3 / 1) được hiệu chỉnh theo kinh nghiệm:** Tỷ lệ giữa các mức được chọn theo kinh nghiệm nghiệp vụ và có thể tinh chỉnh khi có thêm dữ liệu phản hồi từ cán bộ Hải quan.
3. **Mẫu số tính theo dữ liệu trong năm:** Doanh nghiệp có ít dữ liệu trong năm (ví dụ năm đầu hoạt động) sẽ có mẫu số nhỏ, khiến điểm biến động mạnh hơn. Hệ thống chưa áp dụng kỹ thuật chuẩn hoá theo nhóm doanh nghiệp tương đồng do số lượng doanh nghiệp trong giai đoạn thí điểm còn ít.
4. **Không dùng để ra quyết định độc lập:** Điểm Audit-HQ là một đầu vào hỗ trợ cán bộ Hải quan, không thay thế việc đánh giá toàn diện hồ sơ.

---

## 10. Cơ sở tham khảo

Phương pháp được xây dựng dựa trên các khung tham chiếu quốc tế và pháp luật trong nước:

- **Cẩm nang Quản lý Rủi ro Hải quan của Tổ chức Hải quan Thế giới (WCO)** — Khuyến nghị dùng chỉ số theo tỷ lệ thay vì số tuyệt đối khi đánh giá rủi ro hải quan.
- **Cẩm nang Xây dựng Chỉ số Tổng hợp của Tổ chức Hợp tác và Phát triển Kinh tế (OECD, 2008)** — Phương pháp xây dựng chỉ số tổng hợp: chuẩn hoá → gán trọng số → tổng hợp.
- **Thông tư 81/2019/TT-BTC** của Bộ Tài chính (Quản lý rủi ro trong hoạt động nghiệp vụ hải quan) — Quy định khung phân loại tuân thủ chính thức của Tổng cục Hải quan. Audit-HQ tham chiếu nhưng không thay thế hệ thống này.
- **Chương trình Doanh nghiệp ưu tiên (AEO)** của Liên minh Châu Âu, Hoa Kỳ và Việt Nam — Sử dụng tiêu chí tỷ lệ vi phạm kết hợp ngưỡng tuyệt đối cho hành vi nghiêm trọng.

---

*Tài liệu được rà soát và cập nhật khi công thức tính điểm thay đổi. Phiên bản hiện tại: 2026-06-11.*
