# Hướng dẫn sử dụng hệ thống Audit-HQ

> **Tóm tắt:** Audit-HQ giúp cán bộ Hải quan sàng lọc rủi ro dữ liệu Báo cáo Quyết toán (BCQT) của doanh nghiệp gia công, sản xuất xuất khẩu và chế xuất. Quy trình chuẩn gồm sáu bước: chọn doanh nghiệp → nạp dữ liệu → chạy kiểm tra → đọc điểm và phát hiện → xử lý phát hiện → xuất kiến nghị. Tài liệu này hướng dẫn từng bước cho **cán bộ nghiệp vụ** và một mục riêng cho **quản trị viên**.

> **Phạm vi:** Điểm và phát hiện của hệ thống là **chỉ số rủi ro về chất lượng dữ liệu báo cáo**, dùng để sắp xếp ưu tiên kiểm tra. Đây **không** phải là đánh giá mức tuân thủ pháp luật của doanh nghiệp — việc phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan theo Thông tư 81/2019/TT-BTC. Mọi quyết định cuối cùng thuộc thẩm quyền cán bộ Hải quan.

[TOC]

---

## 1. Đăng nhập và tài khoản

### Đăng nhập

Truy cập địa chỉ hệ thống, nhập **tên đăng nhập** và **mật khẩu** do quản trị viên cấp. Phiên đăng nhập có hiệu lực trong **8 giờ**; sau đó hệ thống yêu cầu đăng nhập lại.

Để bảo vệ tài khoản, nếu nhập sai mật khẩu **5 lần liên tiếp**, địa chỉ truy cập sẽ bị tạm khoá **5 phút**. Vui lòng chờ rồi thử lại, hoặc liên hệ quản trị viên nếu quên mật khẩu.

### Đổi mật khẩu

Khi đăng nhập lần đầu (hoặc sau khi quản trị viên đặt lại mật khẩu), hệ thống **buộc đổi mật khẩu** trước khi cho phép thao tác. Mật khẩu tối thiểu **8 ký tự**.

Đổi mật khẩu bất kỳ lúc nào: bấm tên của bạn ở góc phải thanh trên cùng → **Đổi mật khẩu**.

### Hai vai trò

| Vai trò | Quyền hạn |
|---|---|
| **Cán bộ** (officer) | Chỉ xem và làm việc với những doanh nghiệp được **phân công**. Không thấy các mục quản trị hệ thống. |
| **Quản trị viên** (admin) | Xem **tất cả** doanh nghiệp và toàn bộ chức năng quản trị (người dùng, cấu hình AI, ngưỡng rủi ro, nhật ký…). Xem Mục 10. |

---

## 2. Tổng quan giao diện

Thanh điều hướng trên cùng (luôn hiển thị) gồm các lối tắt chính:

- **Audit-HQ** (góc trái): về danh sách doanh nghiệp.
- **💬 Trợ lý**: mở trang trợ lý ảo AI (Mục 8).
- **📑 Danh mục**: danh mục các bài kiểm tra (Mục 9).
- **📚 Tài liệu**: thư viện phương pháp luận và văn bản pháp lý.
- **📋 Công việc**: hàng đợi các lượt chạy kiểm tra. Có **chấm đỏ** báo khi có việc vừa chạy xong.
- **⚙️ Quản trị** (chỉ quản trị viên): nhóm chức năng quản trị.
- **👤 Tên bạn**: đổi mật khẩu, đăng xuất.

Ở góc dưới bên phải mọi trang có **biểu tượng trợ lý ảo** — bấm để hỏi nhanh mà không rời trang đang xem.

> Dữ liệu trong bản trình diễn được giả lập từ hồ sơ thực và không phản ánh doanh nghiệp có thật. Một dải nhắc màu vàng ở đầu trang luôn nhắc điều này.

---

## 3. Quy trình nghiệp vụ chuẩn

Sáu bước dưới đây là luồng làm việc cốt lõi. Các mục 4–8 giải thích chi tiết từng bước.

1. **Chọn hoặc tạo doanh nghiệp** — vào danh sách doanh nghiệp, mở hồ sơ cần làm việc.
2. **Nạp dữ liệu** — tải lên các tệp BCQT (Mẫu 15, 15a, 16 và Báo cáo hàng chi tiết) theo từng năm.
3. **Chạy kiểm tra** — bấm *Chạy kiểm tra*; hệ thống xử lý nền và đưa vào hàng đợi **Công việc**.
4. **Đọc kết quả** — xem **điểm rủi ro** theo năm và danh sách **phát hiện**.
5. **Xử lý phát hiện** — mở từng phát hiện, đối chiếu chứng cứ truy nguồn, rồi đánh dấu *Xác nhận / Loại trừ / Đã ghi chú*.
6. **Xuất kiến nghị** — kết xuất danh sách phát hiện ra tệp Excel để lập hồ sơ.

---

## 4. Quản lý doanh nghiệp và nạp dữ liệu

### 4.1. Danh sách doanh nghiệp

Trang **Doanh nghiệp** liệt kê các doanh nghiệp bạn được phép xem, **sắp xếp theo điểm rủi ro giảm dần** để ưu tiên doanh nghiệp đáng chú ý lên đầu. Mỗi dòng hiển thị mã, tên, các năm có dữ liệu, điểm rủi ro cao nhất và số lượng phát hiện theo mức độ.

**Tạo doanh nghiệp mới:** bấm **+ Thêm doanh nghiệp**, nhập tên và thông tin cơ bản (mã số thuế, địa chỉ, ngành). Hệ thống tự sinh mã dạng `DN_NNN`. Cán bộ tạo doanh nghiệp sẽ được tự động phân công doanh nghiệp đó.

### 4.2. Hồ sơ doanh nghiệp

Bấm vào một doanh nghiệp để mở hồ sơ. Tại đây có:

- **Thông tin chung**: tên, mã số thuế, địa chỉ, ngành, điểm rủi ro của năm đang chọn.
- **Bộ chọn năm**: chuyển giữa các kỳ báo cáo.
- **Danh sách phát hiện** của năm đang chọn (xem Mục 5).
- Lối vào **Quản lý tài liệu**, **tra cứu dữ liệu** và **xuất kiến nghị**.

Sửa thông tin doanh nghiệp tại nút **Chỉnh sửa** trong hồ sơ.

### 4.3. Nạp dữ liệu (Quản lý tài liệu)

Trong hồ sơ doanh nghiệp, mở **Quản lý tài liệu**. Màn hình là một **ma trận năm × loại tệp**, với bốn loại tệp BCQT:

| Loại | Nội dung |
|---|---|
| **Mẫu 15** | Cân đối nhập – xuất – tồn nguyên vật liệu |
| **Mẫu 15a** | Cân đối nhập – xuất – tồn thành phẩm |
| **Mẫu 16** | Định mức thực tế |
| **BCCT** | Báo cáo hàng chi tiết (dữ liệu tờ khai) |

Mỗi ô cho biết trạng thái: **Chưa nạp**, **Đã nạp** (kèm số dòng), **Cảnh báo** hoặc **Lỗi**.

**Các bước nạp:**

1. Bấm **+ Thêm năm** nếu năm cần làm việc chưa có trong bảng.
2. Tải tệp Excel (`.xls` hoặc `.xlsx`, tối đa **100 MB**) vào đúng ô năm – loại tệp. Hệ thống kiểm tra định dạng thật của tệp (chống đổi đuôi giả).
3. **Chẩn đoán tự động:** nếu cấu trúc tệp bất thường, hệ thống cảnh báo **trước khi nạp** và cho phép bấm **Chẩn đoán bằng AI** — trợ lý sẽ phân tích cấu trúc tệp và gợi ý cách xử lý.
4. Khi tệp hợp lệ, bấm **Nạp dữ liệu**. Dữ liệu được đưa vào kho dữ liệu gốc của hệ thống và sẵn sàng để chạy kiểm tra.

**Thao tác khác trên mỗi tệp:** **Xem nhanh** (xem nội dung Excel thô, chọn từng sheet), **Tải xuống**, **Xoá**, hoặc **Nạp lại** từ tệp đã có sẵn mà không cần tải lên lại.

> **Lưu ý:** Một bài kiểm tra chỉ chạy được khi có đủ loại dữ liệu nó cần. Ví dụ, kiểm tra cân đối nguyên vật liệu cần Mẫu 15 và BCCT của cùng năm. Nên nạp đủ bốn loại tệp cho mỗi năm trước khi chạy kiểm tra.

---

## 5. Chạy kiểm tra và đọc kết quả

### 5.1. Chạy kiểm tra

Trong hồ sơ doanh nghiệp, bấm **Chạy kiểm tra**. Có hai cách:

- **Tất cả các năm có dữ liệu** (mặc định): hệ thống chạy lần lượt mọi kỳ báo cáo.
- **Một năm cụ thể**: chọn năm rồi chạy.

Việc chạy diễn ra **ở chế độ nền**. Hệ thống tạo một **công việc** trong hàng đợi và chuyển bạn tới trang theo dõi tiến độ của công việc đó.

### 5.2. Hàng đợi Công việc

Mở **📋 Công việc** trên thanh điều hướng để xem các lượt chạy. Có thể lọc theo trạng thái: **Đang chờ**, **Đang chạy**, **Hoàn tất**, **Thất bại**. Khi có công việc chạy xong, một **chấm đỏ** xuất hiện trên biểu tượng Công việc cho tới khi bạn mở xem.

Bấm vào một công việc để xem chi tiết tiến độ. Trang tự làm mới khi công việc còn đang chạy; khi xong sẽ hiển thị kết quả (số phát hiện, lỗi nếu có).

### 5.3. Điểm rủi ro

Sau khi chạy xong, mỗi cặp **(doanh nghiệp, năm)** có một **điểm rủi ro từ 0 đến 1000**. Điểm càng cao, mức độ chênh lệch trong dữ liệu càng đáng chú ý. Điểm được **chuẩn hoá theo tỷ lệ** chứ không cộng dồn theo số lượng phát hiện, nhằm tránh thiên lệch do quy mô doanh nghiệp lớn nhỏ khác nhau.

Điểm được phân thành **năm hạng cảnh báo** (từ thấp đến cao). Chi tiết công thức và ý nghĩa từng hạng xem tài liệu **[Phương pháp tính điểm rủi ro](/tai-lieu/scoring-methodology)**.

### 5.4. Danh sách phát hiện

Phát hiện của năm đang chọn hiển thị ngay trong hồ sơ doanh nghiệp, **nhóm theo từng bài kiểm tra**. Các phát hiện **tổ hợp** (kết hợp nhiều dấu hiệu) được hiển thị riêng ở đầu vì thường đáng chú ý hơn.

Mỗi phát hiện có một **mức độ nghiêm trọng**:

| Mức | Ý nghĩa |
|---|---|
| 🔴 **Nghiêm trọng** | Chênh lệch lớn, khả năng cao là sai phạm. |
| 🟡 **Cảnh báo** | Chênh lệch cần lưu ý, có thể do sai sót nghiệp vụ. |
| 🔵 **Thông tin** | Chênh lệch nhỏ, ghi nhận để theo dõi. |

---

## 6. Xử lý phát hiện và truy nguồn

Bấm vào một phát hiện để mở **trang chi tiết**. Tại đây có:

- **Mô tả** phát hiện và **đối tượng** liên quan (mã nguyên vật liệu, mã thành phẩm…).
- **Chứng cứ truy nguồn:** các bảng dữ liệu gốc (Mẫu 15/15a/16, BCCT) đúng những dòng làm phát sinh phát hiện. **Mọi phát hiện đều truy nguồn được về dữ liệu gốc — không có phát hiện "hộp đen".**
- Lối tắt sang **chi tiết mặt hàng** để xem diễn biến qua các năm.

### Đánh dấu trạng thái

Sau khi đối chiếu, bấm **Chỉnh sửa trạng thái** và chọn:

| Trạng thái | Khi nào dùng |
|---|---|
| **Mới** | Chưa xử lý (mặc định). |
| **Xác nhận** | Đã xác minh là vấn đề thực sự. |
| **Loại trừ** | Không phải vấn đề (giải thích được, hoặc sai dương). |
| **Đã ghi chú** | Ghi nhận để theo dõi, chưa kết luận. |

Có thể kèm **ghi chú** giải thích. Phát hiện bị đánh dấu **Loại trừ** sẽ **không tính vào điểm**, và **điểm rủi ro được tính lại ngay lập tức** — không cần chạy lại kiểm tra.

---

## 7. Xuất kiến nghị, tra cứu dữ liệu và mặt hàng

### Xuất kiến nghị

Trong hồ sơ doanh nghiệp, dùng chức năng **Xuất kiến nghị** để tải tệp Excel chứa danh sách phát hiện kèm chứng cứ của năm đang chọn — phục vụ lập hồ sơ kiểm tra. Mỗi lượt tải xuống/kết xuất đều được ghi vào nhật ký truy cập.

### Tra cứu dữ liệu gốc

Từ hồ sơ doanh nghiệp, mở **tra cứu dữ liệu** để duyệt trực tiếp các bảng dữ liệu gốc (Mẫu 15/15a/16, BCCT) theo năm, có ô tìm kiếm và phân trang.

### Chi tiết mặt hàng

Bấm vào một mã nguyên vật liệu hoặc thành phẩm để xem **trang chi tiết mặt hàng**: tổng nhập – xuất – tồn, diễn biến **tồn cuối qua các năm**, biểu đồ dòng chảy nhập/xuất, quan hệ định mức (cây vật tư) và các tờ khai liên quan. Hữu ích khi cần đào sâu một mặt hàng đáng ngờ.

---

## 8. Trợ lý ảo (AI)

Mở trợ lý ảo qua **💬 Trợ lý** trên thanh trên cùng, hoặc biểu tượng ở góc dưới bên phải mọi trang. Trợ lý hiểu tiếng Việt và làm việc trực tiếp trên dữ liệu của các doanh nghiệp **bạn được phép xem**.

### Trợ lý làm được gì

- **Tra cứu và giải thích phát hiện** — liệt kê, lọc theo năm/mức độ/bài kiểm tra, và giải thích một phát hiện cụ thể.
- **Tra cứu dữ liệu gốc** — tìm trong các bảng Mẫu 15/15a/16, BCCT.
- **Giải thích điểm rủi ro** — vì sao một doanh nghiệp – năm có điểm như vậy.
- **Giải thích bài kiểm tra và bối cảnh pháp lý** — ý nghĩa nghiệp vụ và căn cứ thông tư liên quan.
- **Chạy kiểm tra theo yêu cầu** — đề xuất và khởi chạy kiểm tra cho một doanh nghiệp – năm.
- **Kết xuất Excel** — xuất danh sách phát hiện hoặc kết quả tra cứu ra tệp.

> Tuỳ cấu hình của quản trị viên, một số năng lực nâng cao (chạy kiểm tra theo yêu cầu, truy vấn dữ liệu nâng cao) có thể được bật hoặc tắt.

### Cách dùng

- Gõ câu hỏi bằng tiếng Việt tự nhiên, ví dụ: *"Liệt kê các phát hiện nghiêm trọng của DN_003 năm 2024"* hoặc *"Giải thích điểm rủi ro của doanh nghiệp này"*.
- Dùng **@** để **nhắc tên doanh nghiệp** trong câu hỏi. Cán bộ chỉ nhắc được các doanh nghiệp đã được phân công.
- Các cuộc trò chuyện được lưu lại; mở lại để xem hoặc tiếp tục.

> Trợ lý là công cụ hỗ trợ tra cứu, không thay thế phán đoán nghiệp vụ. Mọi dữ liệu trợ lý đưa ra đều truy nguồn về dữ liệu gốc; hãy đối chiếu trang chi tiết phát hiện trước khi kết luận.

---

## 9. Danh mục kiểm tra và thư viện tài liệu

- **📑 Danh mục:** liệt kê toàn bộ danh mục bài kiểm tra, kèm mô tả, mức độ và trạng thái triển khai. Trang này chỉ để **tra cứu**.
- **📚 Tài liệu:** thư viện gồm **phương pháp tính điểm** và các **văn bản pháp lý** nền tảng (Thông tư 38/2015, 39/2018, 81/2019). Nên đọc **[Phương pháp tính điểm rủi ro](/tai-lieu/scoring-methodology)** để hiểu cách hệ thống chấm điểm.

---

## 10. Dành cho quản trị viên

Các mục dưới đây nằm trong nhóm **⚙️ Quản trị** và chỉ quản trị viên thấy.

### Người dùng và phân công doanh nghiệp

**Quản trị → Người dùng.** Tạo tài khoản mới (đặt vai trò *cán bộ* hoặc *quản trị viên*), đặt lại mật khẩu, hoặc xoá tài khoản (không thể tự xoá chính mình). Với mỗi cán bộ, vào **Phân công doanh nghiệp** để chọn những doanh nghiệp họ được phép xem — đây là cơ chế phân quyền cốt lõi.

### Ngưỡng hạng rủi ro

**Quản trị → Ngưỡng hạng rủi ro.** Điều chỉnh ngưỡng phân chia **năm hạng** cảnh báo. Khi lưu thay đổi, điểm của các doanh nghiệp bị ảnh hưởng được **tính lại**.

### Đơn vị tính

**Quản trị → Đơn vị tính.** Quản lý bảng đơn vị tính chuẩn và các **tên gọi quy đổi** (ví dụ "cái", "chiếc", "pcs" cùng quy về một đơn vị). Việc này giúp các bài kiểm tra so sánh số lượng chính xác khi dữ liệu dùng đơn vị khác nhau.

### Cấu hình AI

**Quản trị → Cấu hình AI.** Cấu hình kết nối tới nhà cung cấp mô hình ngôn ngữ (địa chỉ, khoá API), chọn mô hình, đặt tham số, giới hạn **số lượt/phút** và **ngân sách theo ngày**, bật/tắt các nhóm năng lực của trợ lý, và theo dõi **chi phí, lượng token** sử dụng. Có nút **Kiểm tra kết nối**.

### Nhật ký truy cập

**Quản trị → Nhật ký truy cập.** Tra cứu các thao tác nhạy cảm: tải xuống tệp, xuất kiến nghị, chạy kiểm tra — kèm thời điểm, người thực hiện và doanh nghiệp liên quan. Lọc theo doanh nghiệp hoặc loại thao tác.

### Kiểm tra mở rộng (nâng cao)

**Quản trị → Kiểm tra mở rộng.** Cho phép soạn bài kiểm tra mới từ mô tả bằng lời, có chạy thử trên một doanh nghiệp tham chiếu trước khi áp dụng. Đây là chức năng nâng cao, nên dùng thận trọng và kiểm thử kỹ.

---

## 11. Câu hỏi thường gặp

**Tôi không thấy doanh nghiệp cần làm việc.**
Có thể bạn chưa được phân công. Liên hệ quản trị viên để được gán doanh nghiệp đó.

**Chạy kiểm tra xong nhưng không có phát hiện.**
Có thể dữ liệu sạch, hoặc chưa nạp đủ loại tệp cho năm đó. Kiểm tra lại **Quản lý tài liệu** để chắc chắn đã nạp đủ Mẫu 15/15a/16 và BCCT.

**Điểm rủi ro nghĩa là doanh nghiệp vi phạm?**
Không. Đây là chỉ số **chất lượng dữ liệu báo cáo** để ưu tiên kiểm tra, không phải kết luận tuân thủ pháp luật. Xem phần phạm vi ở đầu tài liệu.

**Tôi đánh dấu một phát hiện là Loại trừ, điểm có đổi không?**
Có. Phát hiện *Loại trừ* không tính vào điểm, và điểm được **tính lại ngay**.

**Tải tệp lên báo lỗi cấu trúc.**
Dùng nút **Chẩn đoán bằng AI** ngay tại bước nạp để biết tệp sai ở đâu, hoặc dùng **Xem nhanh** để đối chiếu cấu trúc tệp Excel.
