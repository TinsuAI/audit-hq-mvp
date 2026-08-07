# Hướng dẫn lập Mẫu số 16/ĐMTT/GSQL — trích NGUỒN GỐC

**Nguồn:** Phụ lục II ban hành kèm **Thông tư 39/2018/TT-BTC** ngày 20/4/2018 (thay Phụ lục V Thông
tư 38/2015/TT-BTC). Bản Công báo, tệp phụ lục biểu mẫu
`https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/03/25kem6.pdf`, **trang 8** — trang "Hướng dẫn
lập" nằm ngay sau trang biểu Mẫu 16 (trang 7).

**Cách lấy:** tệp là bản QUÉT, không có lớp text (`pdftotext` ra 91 ký tự cho tệp cùng bộ). Trích
bằng `pdftoppm -r 400 -png` rồi `tesseract -l vie`. **Có nhiễu OCR** ở dấu câu và vài chữ (`điện`
↔ `điền`, `:` ↔ `;`) — phần chữ nghĩa dưới đây rõ ràng, nhưng khi cần trích nguyên văn cho văn bản
gửi ra ngoài thì phải đối chiếu lại mắt người trên chính trang quét đó.

## Nguyên văn (đã sửa nhiễu OCR ở dấu câu, giữ nguyên chữ)

> **1. Hướng dẫn lập Mẫu số 16/ĐMTT-GSQL:**
>
> **Cột (2):** Mã sản phẩm xuất khẩu tại cột này phải thống nhất với mã sản phẩm đã khai trên tờ
> khai hải quan
>
> **Cột (3):** Tên sản phẩm xuất khẩu tại cột này phải thống nhất với tên sản phẩm xuất khẩu đã khai
> trên tờ khai hải quan
>
> **Cột (4):** Đơn vị tính của sản phẩm xuất khẩu: sử dụng thống nhất với mã đơn vị tính doanh
> nghiệp quản lý tại nhà xưởng sản xuất, với đơn vị tính đã khai báo trên tờ khai hải quan.
>
> **Cột (5):** Mã của nguyên liệu, vật tư (bao gồm cả nhập khẩu, mua trong nước) để sản xuất ra 01
> đơn vị sản phẩm. Trường hợp nguyên liệu, vật tư nhập khẩu để gia công, sản xuất hàng hóa xuất khẩu
> thì phải thống nhất với mã nguyên liệu, vật tư đã khai trên tờ khai hải quan
>
> **Cột (6):** Tên của nguyên liệu, vật tư (bao gồm cả nhập khẩu, mua trong nước) để sản xuất ra 01
> đơn vị sản phẩm.
>
> **Cột (7):** Đơn vị tính của nguyên liệu, vật tư: sử dụng thống nhất với mã đơn vị tính doanh
> nghiệp quản lý tại nhà xưởng sản xuất, với đơn vị tính đã khai báo trên tờ khai hải quan
>
> **Cột (8):** Lượng nguyên liệu, vật tư thực tế sử dụng để sản xuất sản phẩm xuất khẩu bao gồm
> lượng nguyên liệu, vật tư cấu thành sản phẩm và lượng nguyên liệu, vật tư tiêu hao, tạo thành phế
> liệu, phế phẩm.
>
> Định mức thực tế của một đơn vị sản phẩm theo từng nguyên liệu, vật tư = Tổng lượng nguyên liệu,
> vật tư đã dùng để gia công, sản xuất sản phẩm xuất khẩu chia cho tổng số lượng sản phẩm thu được
>
> Trong đó:
> - Tổng lượng nguyên liệu, vật tư đã dùng để gia công, sản xuất sản phẩm xuất khẩu bằng tổng lượng
>   nguyên liệu, vật tư đưa vào để sản xuất sản phẩm **trừ** lượng nguyên liệu vật tư **thu hồi** và
>   lượng nguyên liệu, vật tư **đang dở dang trên dây chuyền** tính tới thời điểm xác định định mức
>   để gia công, sản xuất sản phẩm xuất khẩu
> - Tổng số lượng sản phẩm thu được: là tổng số lượng thu được cho tới thời điểm xác định định mức.
>
> **Cột (9):** Trường hợp nguyên liệu mua trong nước điền "X"; trường hợp nguyên liệu, vật tư nhập
> khẩu để trống; trường hợp vật tư không xây dựng được định mức điền "KXDĐM"
>
> **2. Chỉ tiêu (10), (11):** Trường hợp hệ thống xử lý dữ liệu điện tử hải quan gặp sự cố, không
> tiếp nhận được báo cáo quyết toán thì phải điền đầy đủ thông tin tại ô này.

## Bốn điều đọc ra được, dùng ngay

1. **ĐVT bắt buộc và có chuẩn đối chiếu.** Cột (4) và (7) đều buộc ĐVT "thống nhất với đơn vị tính
   đã khai báo trên tờ khai hải quan". Đây là căn cứ pháp lý cho việc đối chiếu ĐVT giữa Mẫu 16 và
   BCCT — thứ ADR #28 để lại vì chưa có bảng đồng nghĩa đơn vị.
2. **Cột (9) có BA trạng thái, không phải năm.** `X` mua trong nước · để trống = nhập khẩu ·
   `KXDĐM` không xây dựng được định mức. **`TH` và `SPTN` KHÔNG có trong bản TT 39/2018.** Bản tóm
   tắt của công cụ tìm kiếm nêu năm trạng thái là SAI với văn bản này — có thể nó mô tả bản TT
   121/2025, chưa kiểm chứng được.
3. **`KXDĐM` là trạng thái nghiệp vụ đang bị bỏ qua.** `is_domestic_origin` (`app/adapters/m16.py`)
   chỉ so `== "x"`, nên mã khai `KXDĐM` — tức DN tự khai KHÔNG xây dựng được định mức — bị xử lý y
   hệt "nhập khẩu, có định mức bình thường". Đo trên kho hiện tại: `KXDĐM` xuất hiện **0 lần**
   trong 270.385 dòng, nên chưa gây sai ở dữ liệu đã nạp; nhưng đây đúng là thứ cổng độ phủ định
   mức (C4.9 / `norm_gate`) cần biết.
4. **Cột (8) mang định nghĩa pháp lý của "định mức thực tế"**, và nó TRỪ lượng thu hồi + lượng dở
   dang. Ghi lại vì mọi kiểm tra Nhóm 4 dựng trên con số này.

## Bản HIỆN HÀNH: TT 121/2025/TT-BTC ĐÃ SỬA Mẫu 16

**Nguồn:** `https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/01/121-btc.pdf`, **trang 237–238** —
mục *"đ) Sửa đổi, bổ sung mẫu số 16/ĐMTT/GSQL như sau"*. Cũng là bản quét, cùng cách trích
(`pdftoppm` + `tesseract -l vie`). Hiệu lực **01/02/2026**.

Tập cột **không đổi** (vẫn 9 cột + chỉ tiêu (10), (11)), công thức định mức thực tế ở cột (8)
**không đổi**. Ba chỗ đổi:

**1. Cột (9) từ BA trạng thái lên NĂM:**

> Cột (9): Trường hợp nguyên liệu mua trong nước điền "X"; trường hợp nguyên liệu, vật tư nhập khẩu
> để trống; trường hợp vật tư không xây dựng được định mức điền "KXDĐM"; **trường hợp nguyên liệu,
> vật tư thu hồi từ sản phẩm tái nhập điền "TH"; trường hợp sửa chữa, tái chế từ sản phẩm tái nhập
> thì điền "SPTN"**.

**2. Cột (5) và (6) thêm quy tắc cho sản phẩm tái nhập** — sửa chữa/tái chế từ SP tái nhập thì điền
mã/tên sản phẩm tái nhập đã khai trên tờ khai hải quan tái nhập.

**3. Cột (4) đổi một chữ**, cùng nghĩa: TT 39 viết "…tại nhà xưởng sản xuất**,** với đơn vị tính đã
khai báo trên tờ khai hải quan"; TT 121 viết "…tại nhà xưởng sản xuất **và** đơn vị tính đã khai
báo trên tờ khai hải quan". Ràng buộc ĐVT ↔ tờ khai giữ nguyên ở CẢ HAI bản.

## Kết luận theo hai thế hệ văn bản

| | TT 39/2018 (kỳ ≤ 2025) | TT 121/2025 (kỳ từ 01/02/2026) |
|---|---|---|
| ĐVT cột (4) và (7) buộc thống nhất với tờ khai | có | có |
| Mã cột (2) · tên cột (3) · mã NVL cột (5) buộc thống nhất với tờ khai | có | có, thêm nhánh SP tái nhập |
| Cột (9) | `X` · trống · `KXDĐM` | thêm `TH` · `SPTN` |
| Tập cột | 9 | 9 |

**Hệ quả cho hệ thống:** kho dữ liệu bắc qua CẢ HAI thế hệ (ZONSEN 2026 thuộc TT 121; mọi kỳ còn
lại thuộc TT 39). Nên bộ mã hợp lệ của cột (9) **phụ thuộc kỳ**, không phải hằng số. Bản tóm tắt
của công cụ tìm kiếm nêu năm trạng thái là đúng với TT 121 và SAI với TT 39 — nó không nói mình
đang mô tả bản nào.

**Nơi ở lâu dài của ghi chú này** nên là thư viện pháp lý của repo đề án
(`../audit-hq/.ai/legal/`) — INDEX ở đó đã xếp TT 39/2018 vào backlog "cần ingest dần" và nêu quy
ước "khi có câu hỏi pháp lý phát sinh trong session, fetch + lưu vào đây cho session sau". Để ở repo
này trước vì nó đang chống lưng ADR #28.
