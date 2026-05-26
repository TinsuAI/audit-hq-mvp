# Phương pháp tính điểm rủi ro dữ liệu BCQT

> **Tóm tắt:** Audit-HQ tính một chỉ số rủi ro từ 0 đến 1000 cho mỗi cặp (Doanh nghiệp, Năm tài chính), dựa trên các phát hiện chênh lệch nội bộ giữa các thành phần của Báo cáo Quyết toán (BCQT) — gồm Mẫu 15 (cân đối nguyên vật liệu), Mẫu 15a (cân đối thành phẩm), Mẫu 16 (định mức thực tế) — và đối chiếu với Bộ chứng từ Tờ khai (BCCT). Chỉ số được tính theo công thức **tỷ lệ trên độ phơi nhiễm** (rate-based), không cộng dồn tuyến tính theo số lượng phát hiện, nhằm loại bỏ thiên lệch quy mô.

---

## 1. Mục đích

Audit-HQ phân tích chất lượng dữ liệu hồ sơ hải quan của doanh nghiệp và phát hiện các chênh lệch có thể là dấu hiệu rủi ro nghiệp vụ. Hệ thống thực hiện 16 phép kiểm tra (catalog MVP) trên dữ liệu đầu vào — gồm các mẫu thành phần của Báo cáo Quyết toán (Mẫu 15, Mẫu 15a, Mẫu 16) và Bộ chứng từ Tờ khai — sinh ra danh sách phát hiện (findings) kèm mức độ nghiêm trọng. Điểm rủi ro dữ liệu là cách tổng hợp các phát hiện đó thành một con số duy nhất để cán bộ Hải quan dễ so sánh, sắp xếp ưu tiên kiểm tra.

**Phạm vi:** Đây là chỉ số rủi ro về **chất lượng dữ liệu báo cáo**, không phản ánh mức tuân thủ pháp luật của doanh nghiệp. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan, thực hiện theo Thông tư 81/2019/TT-BTC.

---

## 2. Mức độ nghiêm trọng của phát hiện

Mỗi phát hiện thuộc một trong ba mức:

| Mức | Ký hiệu | Điểm | Ý nghĩa |
|---|---|---|---|
| Nghiêm trọng | 🔴 | 10 | Chênh lệch lớn, có khả năng cao là sai phạm hoặc gian lận. Ví dụ: tồn cuối NVL âm, có tờ khai nhập nhưng không có trên M15. |
| Cảnh báo | 🟡 | 3 | Chênh lệch ở mức cần lưu ý, có thể do sai sót nghiệp vụ hoặc do bản chất số liệu. Ví dụ: lệch số lượng 5–20%, mã HS không nhất quán giữa các tờ khai. |
| Thông tin | 🔵 | 1 | Chênh lệch nhỏ, ghi nhận để theo dõi. Ví dụ: lệch số lượng dưới 5%, đơn vị tính khác họ nhưng cùng quy đổi. |

Các phát hiện do cán bộ Hải quan đánh dấu **Loại trừ** (status `rejected`) sẽ không được tính vào điểm.

---

## 3. Công thức tính điểm — từng phép kiểm tra

Mỗi phép kiểm tra (gọi là **rule**) được tính điểm độc lập theo công thức:

```
points          = Σ điểm_nghiêm_trọng cho mọi phát hiện còn hiệu lực của rule
exposure        = số đối tượng (mã NVL / mã TP / mã định mức) thuộc phạm vi rule
max_points      = 10 × exposure          (giả sử tất cả phát hiện đều ở mức 🔴)
rate            = min(1, points / max_points)
điểm_rule       = rate × 10
```

### Giải thích

- **Mỗi rule đóng góp tối đa 10 điểm** vào tổng điểm doanh nghiệp, bất kể số phát hiện thực tế.
- **Tỷ lệ (rate)** là một số trong khoảng [0, 1], thể hiện mức độ rủi ro tương đối: 1 nghĩa là tất cả đối tượng trong phạm vi đều phát hiện sai ở mức nghiêm trọng nhất; 0 nghĩa là không có phát hiện nào.
- **Mẫu số (exposure)** được tính riêng cho từng rule theo phạm vi nghiệp vụ. Ví dụ:
  - Rule về cân bằng NVL (C2.1): mẫu số là số mã NVL distinct có trong M15 hoặc BCCT.
  - Rule về xuất TP (C1.4): mẫu số là số mã thành phẩm distinct có trong M15a hoặc BCCT phía xuất.
  - Rule về định mức (C4.1, C4.3): mẫu số là số mã NVL có trong M16.
- **Nếu mẫu số bằng 0** (doanh nghiệp không có dữ liệu trong phạm vi của rule), điểm rule bằng 0.

### Vì sao chuẩn hoá theo tỷ lệ?

Cách cộng dồn tuyến tính (ví dụ: mỗi phát hiện 🔴 = 10 điểm, cộng hết) sẽ ưu tiên doanh nghiệp lớn về quy mô dữ liệu một cách bất hợp lý. Một doanh nghiệp có 500 mã NVL với tỷ lệ lỗi 10% sẽ có 50 phát hiện = 500 điểm; trong khi doanh nghiệp 50 mã có cùng tỷ lệ lỗi 10% chỉ có 5 phát hiện = 50 điểm. Hai trường hợp có chất lượng dữ liệu tương đương nhưng điểm cách nhau 10 lần.

Cách tính theo tỷ lệ chuẩn hoá triệt tiêu thiên lệch này: cả hai doanh nghiệp đều có rate = 0.1 → điểm rule = 1.0.

Đây cũng là nguyên tắc Tổ chức Hải quan Thế giới (WCO) và các chương trình Doanh nghiệp Ưu tiên (AEO) của Liên minh Châu Âu, Hoa Kỳ áp dụng: đánh giá tuân thủ dựa trên **tỷ lệ vi phạm trên tổng giao dịch**, không dựa trên số tuyệt đối.

---

## 4. Thưởng tổ hợp (combination bonus)

Một số tổ hợp phát hiện có ý nghĩa lớn hơn tổng các phát hiện riêng lẻ. Ví dụ: cùng một mã NVL vừa có lệch định mức M16 vừa có tồn âm trên M15 cho thấy dấu hiệu định mức bị làm giả.

Khi hệ thống phát hiện ít nhất một tổ hợp, **cộng thêm 20 điểm** vào tổng điểm thô. Tổ hợp được tính một lần duy nhất, không nhân theo số lần phát hiện.

---

## 5. Quy đổi sang thang 0–1000

Tổng điểm thô của một (Doanh nghiệp, Năm):

```
điểm_thô        = Σ điểm_rule + thưởng_tổ_hợp
điểm_thô_tối_đa = 16 × 10 + 20 = 180     (16 rule, mỗi rule tối đa 10 điểm)
điểm_chuẩn_hoá  = round(1000 × điểm_thô / 180)
```

Kết quả là một số nguyên trong khoảng [0, 1000].

---

## 6. Phân loại 5 mức cảnh báo

Để dễ đọc, điểm chuẩn hoá được ánh xạ sang một trong năm nhãn:

| Khoảng điểm | Nhãn | Màu sắc | Ý nghĩa |
|---|---|---|---|
| 0 – 100 | Dữ liệu nhất quán | 🟢 Xanh lá | Không có hoặc rất ít chênh lệch. Hồ sơ tương đối sạch. |
| 101 – 300 | Có chênh lệch nhỏ | 🟢 Xanh-vàng | Chênh lệch ở mức bình thường của nghiệp vụ XNK. Ghi nhận, không cần ưu tiên kiểm tra. |
| 301 – 600 | Cần rà soát | 🟡 Vàng | Có nhiều chênh lệch hoặc một số chênh lệch nghiêm trọng. Đề nghị cán bộ rà soát kỹ. |
| 601 – 850 | Có dấu hiệu bất thường | 🟠 Cam | Tỷ lệ phát hiện cao, nhiều phát hiện ở mức nghiêm trọng. Đề nghị tăng cường kiểm tra. |
| 851 – 1000 | Bất thường nghiêm trọng | 🔴 Đỏ | Hồ sơ có dấu hiệu rất bất thường, đề nghị kiểm tra sau thông quan hoặc thanh tra. |

**Lưu ý quan trọng:** 5 nhãn trên là chỉ số nội bộ của Audit-HQ về chất lượng dữ liệu BCQT. **Không phải** 5 Mức tuân thủ theo Thông tư 81/2019/TT-BTC (Doanh nghiệp ưu tiên, Tuân thủ cao, Tuân thủ trung bình, Tuân thủ thấp, Không tuân thủ), vốn dựa trên hồ sơ vi phạm pháp luật thực tế của doanh nghiệp và do hệ thống Tổng cục Hải quan tự động đánh giá vào 00 giờ hàng ngày.

---

## 7. Điểm tổng của doanh nghiệp

Doanh nghiệp có dữ liệu nhiều năm sẽ có một điểm cho mỗi năm. Trên trang danh sách doanh nghiệp, hệ thống hiển thị **điểm tổng = điểm cao nhất trong các năm** để cán bộ Hải quan nhận biết năm nào cần lưu ý nhất.

Trên trang chi tiết doanh nghiệp, điểm và nhãn được hiển thị theo từng năm để cán bộ có thể so sánh xu hướng.

---

## 8. Đảm bảo tính minh bạch và truy nguyên

- **Mỗi phát hiện** có thể truy nguyên về dòng dữ liệu Tầng 1 (M15, M15a, M16, BCCT) qua trường `evidence_refs`. Cán bộ Hải quan có thể bấm từ phát hiện → xem dòng dữ liệu gốc để xác minh.
- **Mỗi điểm rule** được lưu chi tiết trong trường `breakdown` của bảng `company_year_scores`. Khi cần kiểm tra cách tính, có thể xem trực tiếp.
- **Mọi thay đổi điểm** đều phát sinh từ việc chạy lại kiểm tra (run-checks). Lịch sử chạy lưu trong bảng `jobs`.

---

## 9. Hạn chế đã biết

1. **Chỉ phản ánh dữ liệu doanh nghiệp khai báo:** Nếu doanh nghiệp không khai báo đầy đủ (ví dụ thiếu M16), một số rule không có cơ sở chạy. Điểm thấp không đồng nghĩa hồ sơ sạch.
2. **Trọng số mức nghiêm trọng (10/3/1) là calibrated:** Các tỷ lệ giữa các mức được chọn theo kinh nghiệm nghiệp vụ; có thể tinh chỉnh sau khi có thêm dữ liệu phản hồi từ cán bộ Hải quan.
3. **Mẫu số tính theo dữ liệu trong năm:** Doanh nghiệp có ít dữ liệu trong năm (ví dụ năm đầu hoạt động) sẽ có mẫu số nhỏ → biến động điểm cao hơn. Hệ thống chưa áp dụng kỹ thuật cohort z-score do số lượng doanh nghiệp trong giai đoạn thí điểm còn ít.
4. **Không dùng cho ra quyết định độc lập:** Điểm Audit-HQ là một đầu vào hỗ trợ cán bộ Hải quan, không thay thế việc đánh giá toàn diện hồ sơ.

---

## 10. Cơ sở tham khảo

Phương pháp được xây dựng dựa trên các khung tham chiếu quốc tế và pháp luật trong nước:

- **WCO Customs Risk Management Compendium** — Khuyến nghị sử dụng chỉ số tỷ lệ (rate-based metrics) thay vì số tuyệt đối trong đánh giá rủi ro hải quan.
- **OECD Handbook on Constructing Composite Indicators (2008)** — Phương pháp xây dựng chỉ số tổng hợp: chuẩn hoá → gán trọng số → tổng hợp.
- **Thông tư 81/2019/TT-BTC** của Bộ Tài chính (Quản lý rủi ro trong hoạt động nghiệp vụ hải quan) — Quy định khung phân loại tuân thủ chính thức của Tổng cục Hải quan. Audit-HQ tham chiếu nhưng không thay thế hệ thống này.
- **Authorized Economic Operator (AEO)** — Chương trình DN ưu tiên của Liên minh Châu Âu, Hoa Kỳ và Việt Nam, sử dụng tiêu chí tỷ lệ vi phạm + ngưỡng tuyệt đối cho hành vi nghiêm trọng.

---

*Tài liệu này được rà soát và cập nhật khi công thức scoring thay đổi. Phiên bản hiện tại: 2026-05-26.*
