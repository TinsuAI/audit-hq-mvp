# Tài liệu đào tạo cán bộ — Audit-HQ

Tài liệu này dành cho cán bộ Hải quan thực hiện kiểm tra sau thông quan tại doanh
nghiệp gia công, sản xuất xuất khẩu (SXXK) hoặc chế xuất (DNCX). Tài liệu giả định
cán bộ đã nắm nghiệp vụ kiểm tra sau thông quan và Báo cáo Quyết toán (BCQT) theo
Thông tư 38/2015/TT-BTC và Thông tư 39/2018/TT-BTC, nhưng chưa từng dùng phần mềm
Audit-HQ, không biết SQL, không biết lập trình.

Nội dung bám sát đúng những gì phần mềm đang làm tại thời điểm viết tài liệu này
(30/07/2026): route thực tế trong `app/routes/`, bài kiểm tra thực tế trong
`app/checks/`, và luồng thao tác đã có ảnh chụp thật trong cẩm nang sử dụng ở
`/tai-lieu/huong-dan-su-dung` (file nguồn `app/static/docs/huong-dan/index.html`).
Tài liệu này **không thay thế** cẩm nang đó — cẩm nang dạy bấm nút ở đâu; tài liệu
này dạy đọc phát hiện nghĩa là gì và tin đến đâu.

Quy ước: tên trường dữ liệu và định danh trong hệ thống giữ nguyên tiếng Anh
(`status`, `check_code`, `book`) vì đó là khoá nội bộ, không phải chữ dịch — mỗi
định danh được giải nghĩa một lần khi xuất hiện lần đầu.

---

## 1. Phần mềm này làm gì và không làm gì

**Audit-HQ làm gì.** Phần mềm nạp bốn loại tài liệu BCQT của một doanh nghiệp
(Mẫu 15, Mẫu 15a, Mẫu 16, và dữ liệu tờ khai — gọi là BCCT trong hệ thống), chạy
một bộ **bài kiểm tra** (check) so sánh số liệu chéo giữa các tài liệu đó, và liệt
kê từng chỗ lệch thành một **phát hiện** (finding). Mỗi phát hiện có mã bài kiểm
tra (`check_code`, ví dụ `C1.1`), mức độ (`severity`: nghiêm trọng / cảnh báo /
thông tin), và một khối **chứng cứ truy nguồn** trỏ thẳng về dòng dữ liệu gốc đã
sinh ra phát hiện đó (bảng nào, lọc theo điều kiện nào). Phần mềm còn tính một
**điểm rủi ro dữ liệu** từ 0 đến 1000 cho mỗi cặp (doanh nghiệp, kỳ báo cáo), dùng
để sắp xếp ưu tiên kiểm tra giữa nhiều doanh nghiệp.

**Một phát hiện là gì.** Một phát hiện là một chỗ lệch số liệu cần đối chiếu, không
phải kết luận về hành vi vi phạm. Bài kiểm tra chỉ so sánh số học giữa các tài liệu
doanh nghiệp tự nộp; nó không biết bối cảnh nghiệp vụ (hợp đồng gia công, lịch thông
quan, cách doanh nghiệp đặt mã vật tư nội bộ...). Nhiều phát hiện có giải thích hợp
lệ — mục 4 liệt kê giải thích thường gặp cho từng bài kiểm tra. Việc phán đoán một
phát hiện là sai sót nghiệp vụ vô hại hay dấu hiệu cần xử lý tiếp thuộc thẩm quyền
cán bộ, không phải phần mềm.

**Mọi phát hiện đều truy nguồn được.** Ở trang chi tiết phát hiện, khối "Chứng cứ
truy nguồn (Tầng 1)" liệt kê đúng những dòng dữ liệu (bảng + điều kiện lọc) đã được
dùng để tính ra phát hiện đó — không có phát hiện nào là "hộp đen". Kể cả khi khối
chứng cứ trả về 0 dòng, đó cũng là thông tin có nghĩa: ví dụ Mẫu 15 khai nhập một
mã nhưng bảng tờ khai lọc theo mã đó trả về 0 dòng — chính sự vắng mặt đó là lý do
phát hiện tồn tại (bài `C1.2`/`C1.3`).

**Điểm rủi ro không phải đánh giá tuân thủ pháp luật.** Đây là nguyên văn cảnh báo
đã có sẵn trên giao diện (`company_detail.html`, khối quy trình sáu bước trong cẩm
nang): điểm và phát hiện là chỉ số rủi ro về **chất lượng dữ liệu báo cáo**, dùng để
sắp xếp ưu tiên. Đây không phải phân loại mức độ tuân thủ theo Thông tư
81/2019/TT-BTC — việc đó thuộc thẩm quyền Tổng cục Hải quan. Mục 5 giải thích thêm
vì sao điểm số hiện tại còn một vấn đề kỹ thuật khiến nó **không đáng tin cậy** để
so sánh tuyệt đối giữa các doanh nghiệp.

**Phần mềm không làm gì (tính đến bản này).**
- Không tự động kết luận vi phạm, không tự sinh văn bản kiến nghị xử phạt.
- Không đối chiếu với sổ sách kế toán (tài khoản 152/155/156), báo cáo tài chính,
  danh mục tài sản cố định, hay dữ liệu phế liệu/phế phẩm — các nhóm kiểm tra 8–12
  trong catalog (`app/catalog_full.py`) đều ở trạng thái `conditional`: cần dữ liệu
  doanh nghiệp cung cấp thêm mà bản này chưa nạp được, hoặc cần Hải quan cung cấp
  danh mục tham chiếu (nhà cung cấp rủi ro, ngưỡng theo ngành) mà bản này chưa có.
- Không so sánh giữa các doanh nghiệp cùng ngành (nhóm 7) — điều kiện kích hoạt là
  có ≥30 doanh nghiệp cùng ngành trong danh mục, hiện chưa đủ.
- Không phân biệt được "0 phát hiện vì dữ liệu sạch" với "0 phát hiện vì thiếu dữ
  liệu để so sánh" ở một số trường hợp biên — xem mục 5.

---

## 2. Chuẩn bị dữ liệu

### 2.1. Bốn loại tài liệu, mỗi kỳ báo cáo một bộ

Mỗi năm/kỳ báo cáo của một doanh nghiệp cần bốn loại tài liệu, nạp qua trang
**Tài liệu** của doanh nghiệp (`/companies/{code}/documents`):

| Loại | Nội dung | Số file mỗi kỳ |
|---|---|---|
| **Mẫu 15** (`m15`) | Cân đối nhập – xuất – tồn nguyên vật liệu (NVL) | 1 file, tải lại sẽ thay thế |
| **Mẫu 15a** (`m15a`) | Cân đối nhập – xuất – tồn thành phẩm (TP) | 1 file, tải lại sẽ thay thế |
| **Mẫu 16** (`m16`) | Định mức thực tế NVL cho từng thành phẩm | 1 file, tải lại sẽ thay thế |
| **BCCT** (`bcct`) | Dữ liệu tờ khai xuất nhập khẩu (Báo cáo hàng chi tiết) | nhiều file, cộng dồn |

Chỉ chấp nhận `.xls` / `.xlsx`, tối đa 100 MB một file
(`app/routes/companies.py:MAX_UPLOAD_BYTES`). Hệ thống đọc byte đầu file để xác
nhận đúng là file Excel thật (chữ ký `PK\x03\x04` cho `.xlsx`, `\xd0\xcf\x11\xe0`
cho `.xls`) — file đổi đuôi (ví dụ đổi `.txt` thành `.xlsx`) bị chặn ngay, không
tin vào phần mở rộng tên file.

Có hai cách tải: **tải nhiều file cùng lúc** (mục B4 cẩm nang, phân tích rồi nạp
luôn nếu không có cột cần xác nhận) hoặc **tải từng ô** trên ma trận năm × loại tài
liệu (nạp bằng nút riêng). Cả hai cách đều **không tự chạy kiểm tra** — chạy kiểm
tra là bước riêng (mục 3.3).

### 2.2. Trường hợp doanh nghiệp giữ hai sổ quyết toán (EPE / GC)

Một pháp nhân có thể vừa hoạt động theo chế độ chế xuất (DNCX) vừa nhận gia công
cho thương nhân nước ngoài trong cùng năm, và phải nộp **hai bộ quyết toán riêng**
(hai bộ Mẫu 15/15a/16) trên cùng một luồng tờ khai. Hệ thống gọi mỗi bộ này là một
**sổ quyết toán** (`book`), với hai giá trị đã biết:

- `EPE` — Sổ EPE (chế xuất)
- `GC` — Sổ GC (gia công)

**Khi nào phải gán nhãn sổ.** Chỉ ba loại tài liệu thuộc diện quyết toán (Mẫu
15/15a/16) mang nhãn sổ; BCCT (tờ khai) không có nhãn sổ vì tờ khai dùng chung cho
cả doanh nghiệp, không tách theo sổ. Nếu doanh nghiệp chỉ có một sổ, để trống —
hệ thống hiểu là doanh nghiệp một sổ (`book = NULL`), không cần làm gì thêm. Nếu
doanh nghiệp có từ hai sổ khác loại hình trở lên, cán bộ phải vào màn hình **Xác
nhận map cột** của từng file Mẫu 15/15a/16 (mở bằng nút ✏️ Sửa cột trên trang tài
liệu, hoặc tự động hiện ra sau khi tải nếu có cột cần xác nhận) và chọn đúng sổ ở
trường "Sổ quyết toán" trước khi bấm xác nhận.

**Việc gán sổ là tất-cả-hoặc-không** (`app/pipeline/ingest.py:IngestPlanError`).
Hệ thống từ chối nạp nếu:
- doanh nghiệp đang có dữ liệu nhiều sổ trong DB nhưng đợt tải lên mới không file
  nào còn nhãn sổ — nạp tiếp sẽ gộp mọi sổ thành một, im lặng;
- một số file quyết toán của kỳ đã gán sổ, số khác chưa — nạp dở dang một sổ dẫn
  đến các bài kiểm tra định mức/tồn kho (`C4.1`, `C4.3`, `C6.1`) đối chiếu nhầm
  giữa sổ thật và một "sổ NULL" không tồn tại;
- một file quyết toán đã đăng ký sổ nhưng không còn trên đĩa, hoặc đọc lại không
  được (sai trang tính).

Trong cả ba trường hợp, thông báo lỗi liệt kê đúng file còn thiếu nhãn — cán bộ
gán nốt rồi nạp lại, dữ liệu của lượt nạp trước đó không bị xoá.

**Phát hiện liên sổ.** Các bài kiểm tra đối chiếu với tờ khai (ví dụ `C1.1`–`C1.4`,
`C1.6`) không quy được về một sổ cụ thể vì tờ khai dùng chung — phát hiện loại này
mang `book = NULL`, hiển thị nhãn "Liên sổ" (`app/books.py:CHUNG_LABEL`). Khi lọc
riêng một sổ mà 0 phát hiện, hệ thống ghi rõ sổ đó **đã được kiểm tra và không có
chênh lệch**, khác với "chưa chạy kiểm tra" hay "thiếu dữ liệu".

### 2.3. Khi nào việc tải lên bị từ chối hoặc dừng lại

Có hai tầng kiểm tra trước khi dữ liệu vào kho: kiểm tra định dạng file (chặn ngay
khi tải), và **chẩn đoán cấu trúc** (`app/pipeline/validate.py:diagnose_upload`,
chạy sau khi lưu file, trước khi nạp).

Bị từ chối ngay khi tải (lỗi 4xx, không lưu file):
- sai đuôi file (không phải `.xls`/`.xlsx`);
- nội dung không đúng định dạng Excel dù đuôi đúng (đổi đuôi giả);
- vượt 100 MB;
- năm ngoài khoảng 2015–2030.

Dừng lại ở bước chẩn đoán (file đã lưu, nhưng chưa nạp vào kho, báo lỗi kèm chi
tiết trên chính trang tải lên):
- **không chọn được đúng trang tính (sheet)** khớp bố cục Mẫu 15/15a chuẩn TT39 —
  hệ thống dò trang tính điểm cao nhất rồi báo cụ thể cột nào lệch vị trí so với
  mẫu chuẩn (ví dụ "cột 'Tồn cuối' ở vị trí 9, chuẩn 7");
- **đọc được file nhưng 0 dòng dữ liệu** — không tìm thấy dòng tiêu đề mong đợi
  (Mã, Tồn đầu/cuối, Nhập, Xuất), khả năng file theo mẫu Thông tư 38 cũ hoặc dữ
  liệu nằm ở trang tính khác;
- với Mẫu 16/BCCT: đọc được nhưng không trích được dòng nào — Mẫu 16 cần đúng
  cấu trúc SP→NVL, BCCT cần trang tính CHI TIẾT hàng hoá (không phải trang tổng
  hợp cấp tờ khai);
- không nhận diện được file nào khớp một trong bốn loại (Mẫu 15/15a/16/BCCT).

Chỉ cảnh báo, không chặn nạp:
- tất cả cột số (tồn/nhập/xuất) đều bằng 0 trên ≥3 dòng — dấu hiệu lệch cột dù đã
  chọn đúng trang tính;
- có ô lỗi Excel (`#REF!`, `#DIV/0!`...) trong vùng dữ liệu — các ô này nạp thành
  0 hoặc chuỗi rác, không phải số liệu thật;
- có liên kết tới workbook ngoài bộ dữ liệu đang tải — giá trị đọc được là bản
  cache của lần mở gần nhất, nếu liên kết gãy thì các ô đó lặng lẽ về 0.

Khi lỗi cấu trúc xảy ra, trang tải lên có nút **Chẩn đoán bằng AI** để hỏi mô hình
ngôn ngữ phân tích thêm — đây là bước mở rộng của chẩn đoán tự động, không phải
đường bắt buộc.

**Cổng xác nhận cột (không phải lỗi, nhưng dừng lại chờ cán bộ).** Ngay cả khi file
đọc được, hệ thống chỉ tự nạp thẳng nếu **mọi cột đều `verified`** — nghĩa là cột đó
khớp đúng tiêu đề tại đúng vị trí, hoặc chỉ dùng làm số hạng trong một đẳng thức cân
đối đã được kiểm chứng. Nếu có cột chỉ suy được theo vị trí cố định (`position-only`,
không có tín hiệu nào khác) và cột đó được một bài kiểm tra đọc trực tiếp, file dừng
ở trạng thái `analyzed` ("Đã phân tích") và cán bộ phải vào màn hình xác nhận map
cột, đối chiếu với nội dung file thật, sửa nếu sai, rồi bấm "Xác nhận & nạp dữ liệu"
mới sang trạng thái `parsed`/`ok` ("Đã nạp"). Đây là cảnh báo mềm — vẫn nạp và chạy
kiểm tra được nếu cán bộ không sửa, nhưng phát hiện sinh ra từ cột đó mang cờ nhắc
là dựa trên cột chưa xác nhận (`app/checks/registry.py:review_state`).

---

## 3. Quy trình một cuộc kiểm tra, theo thứ tự thao tác

### Bước 1 — Chọn hoặc tạo doanh nghiệp

Vào **Danh sách doanh nghiệp** (`/companies`). Cán bộ chỉ thấy doanh nghiệp được
quản trị viên **phân công** cho tài khoản của mình; ngoài phạm vi đó bị ẩn hoàn
toàn, kể cả khi hỏi qua trợ lý AI (`app/scoping.py:allowed_company_ids`). Không
thấy doanh nghiệp cần làm việc — liên hệ quản trị viên phân công thêm, không phải
lỗi hệ thống. Chưa có hồ sơ thì bấm **+ Thêm DN mới**, nhập tên (bắt buộc), ngành,
mã số thuế, địa chỉ; mã doanh nghiệp nội bộ dạng `DN_NNN` do hệ thống tự gán.

### Bước 2 — Nạp dữ liệu

Vào trang **Tài liệu** của doanh nghiệp, chọn năm, tải bốn loại tài liệu (mục 2).
Nếu tải nhiều file cùng lúc và không có cột cần xác nhận, hệ thống tự nạp luôn.
Nếu có cột cần xác nhận, xử lý theo mục 2.3 (cổng xác nhận cột) trước khi dữ liệu
vào kho. Kỳ báo cáo lệch năm dương lịch (ví dụ năm tài chính không trùng 01/01–31/12)
sửa được ở màn hình riêng — sau khi sửa phải nạp lại và chạy lại kiểm tra thì cửa
sổ kỳ mới mới có hiệu lực; năm có kỳ tuỳ chỉnh được đánh dấu **TC** trên tab năm ở
hồ sơ doanh nghiệp.

Kiểm tra trạng thái từng file trước khi sang bước 3: nhãn tiến độ (Đã tải lên → Đã
phân tích → Đã nạp) và nhãn độ tin cậy cột (Đã kiểm / Cần xác nhận) là hai trục độc
lập, đọc cả hai. Trạng thái Cảnh báo/Lỗi kèm thông báo cụ thể — xem mục 2.3.

### Bước 3 — Chạy kiểm tra

Nút **▶️ Chạy kiểm tra <năm>** trên hồ sơ doanh nghiệp chỉ bật khi kỳ đó đã có dữ
liệu trong kho (không chỉ có file, phải đã nạp). Có bốn cách chạy: toàn bộ bài cho
kỳ đang xem, toàn bộ cho mọi kỳ có dữ liệu (**🔄 Tất cả năm**), một tập bài chọn
trước (**☑️ Chọn test chạy**), hoặc đúng một bài (**▶️ Chạy lại <mã bài>** ngay
trong nhóm phát hiện của bài đó).

Mọi lượt chạy đều xử lý ở chế độ nền, không đồng bộ — hệ thống tạo một **công việc**
(job) và chuyển sang trang theo dõi, trang tự làm mới trong lúc còn chạy. Không cần
ngồi chờ, đóng trang không ảnh hưởng lượt chạy; xem lại qua **📋 Công việc** trên
thanh điều hướng, có bộ lọc theo trạng thái (Đang chờ / Đang chạy / Hoàn tất / Thất
bại). Sửa map cột trên một file đã nạp trước đó cũng tự động xếp lịch chạy lại đúng
những bài kiểm tra đọc cột vừa sửa, không phải chạy lại toàn bộ thủ công.

### Bước 4 — Đọc kết quả

Trên hồ sơ doanh nghiệp: **điểm rủi ro dữ liệu** (0–1000) của kỳ đang chọn kèm mức
cảnh báo, số phát hiện tách theo ba mức độ, và danh sách phát hiện **nhóm theo bài
kiểm tra**. Mỗi nhóm hiện 15 dòng đầu, có nút xem toàn bộ (phân trang). Đọc kỹ mục
5 trước khi dùng điểm số để so sánh giữa các doanh nghiệp. Mục 4 giải thích từng
bài kiểm tra.

Mỗi nhóm bài kiểm tra có thể có **Tổng quan AI**: một bảng số liệu do hệ thống tính
(luôn đúng, hiện ngay) và một đoạn nhận định do mô hình ngôn ngữ viết (hiện sau vài
giây, chỉ để tham khảo). Nguyên văn cảnh báo trên giao diện: số liệu dùng để lập hồ
sơ phải lấy từ bảng số liệu và trang chi tiết phát hiện; phần nhận định AI không
phải kết luận vi phạm.

### Bước 5 — Xử lý phát hiện: đối chiếu chứng cứ rồi đánh dấu trạng thái

Bấm **Chi tiết →** trên một phát hiện để mở trang chi tiết. Đọc khối **Chứng cứ
truy nguồn (Tầng 1)** — đúng những dòng dữ liệu gốc đã sinh ra phát hiện, kèm tên
bảng và điều kiện lọc. Đối chiếu với hồ sơ giấy hoặc yêu cầu doanh nghiệp giải trình
theo mục 4 (cột "chứng cứ cần yêu cầu doanh nghiệp"). Sau khi có căn cứ, cập nhật
**trạng thái** (`status`) ngay tại trang chi tiết hoặc trực tiếp trên bảng danh sách:

| `status` | Khi nào dùng |
|---|---|
| `new` — Mới | Chưa xử lý (mặc định khi bài kiểm tra vừa chạy xong) |
| `confirmed` — Xác nhận | Đã xác minh là vấn đề thực sự |
| `rejected` — Loại trừ | Không phải vấn đề — giải thích được, hoặc sai dương |
| `noted` — Đã ghi chú | Ghi nhận để theo dõi, chưa kết luận |

Phát hiện đánh dấu `rejected` không tính vào điểm rủi ro nữa, và điểm được **tính
lại ngay** khi lưu — không cần chạy lại kiểm tra.

Từ trang chi tiết phát hiện hoặc bất kỳ đâu mã hàng xuất hiện, bấm vào mã để mở
**trang chi tiết mã hàng**: tồn cuối kỳ, tổng nhập/xuất, biểu đồ cân đối kho cả kỳ,
quan hệ định mức (mã này là NVL đầu vào của thành phẩm nào), và toàn bộ phát hiện
khác của mã đó trong kỳ — dùng khi một mã bị nhiều bài kiểm tra cùng gắn cờ, cần
nhìn tổng thể trước khi kết luận.

### Bước 6 — Xuất kiến nghị

Nút **Xuất Excel kiến nghị** ở hồ sơ doanh nghiệp mở hộp chọn bài kiểm tra cần xuất
(không tick bài nào = xuất tất cả); file gồm danh sách phát hiện kèm chứng cứ của
kỳ đang chọn. Trong từng nhóm phát hiện còn có nút xuất riêng một bài. Mỗi lượt tải
file, xuất báo cáo, chạy kiểm tra đều được ghi vào **nhật ký truy cập**
(`/admin/audit-log`, chỉ quản trị viên xem).

**Khi một thao tác thất bại.** Lỗi nạp dữ liệu (kể cả `IngestPlanError` ở mục 2.2)
không xoá dữ liệu đã nạp trước đó — thông báo lỗi hiện ngay trên trang tài liệu,
cán bộ sửa rồi thử lại. Lỗi chạy kiểm tra hiện trong trang chi tiết công việc kèm
tên bài kiểm tra bị lỗi; các bài khác trong cùng lượt chạy không bị ảnh hưởng.

---

## 4. Đọc phát hiện — 17 bài kiểm tra đã triển khai

Bản này đã triển khai chạy được **17 bài kiểm tra** (`app/checks/registry.py:SPECS`,
xác nhận chéo bởi `app/checks/denominators.py:RULE_SCOPE` cũng liệt kê đúng 17 mã).
Đây là con số hiện tại — nhiều hơn 1 so với "16 kiểm tra MVP" ghi trong quy trình dự
án (`CLAUDE.md`); mục cuối tài liệu này nêu lại điểm lệch đó. Danh mục đầy đủ có 49
bài theo đề án (`app/catalog_full.py`), 17 bài dưới đây đã chạy được, số còn lại ở
trạng thái "Bổ sung thí điểm" (wip, đã viết đề án nhưng chưa code) hoặc "Cần thêm
điều kiện" (conditional, cần dữ liệu hoặc danh mục tham chiếu doanh nghiệp/Hải quan
chưa có) — tra cứu đầy đủ ở trang **📑 Danh mục** (`/danh-muc-kiem-tra`).

Mô tả dưới đây lấy nguyên trạng thái từ trường `problem` (mô tả nghiệp vụ trung
tính) của catalog, không lấy trường `risk` (diễn giải động cơ vi phạm) — theo đúng
nguyên tắc mục 1: một phát hiện là chỗ lệch cần đối chiếu, không phải kết luận.

**Mã loại hình tờ khai dùng lặp lại trong các bài dưới đây** (theo
`app/checks/company_type.py`): DNCX (chế xuất) nhập `E11`/`E15`, xuất `E42`; Gia
công thương nhân nước ngoài nhập `E21`/`E23`, xuất `E52`/`E54`; SXXK nhập
`E31`/`E33`, xuất `E62`. Dùng chung mọi loại hình: `E13` (nhập máy móc thiết bị
miễn thuế), `B13` (tái xuất), `A42` (chuyển mục đích sử dụng, bán/tiêu thụ nội
địa).

### Nhóm 1 — Số lượng nhập / xuất

**C1.1 — Lệch số lượng nhập NVL (M15 vs tờ khai)**
So sánh cột `nhập_trong_kỳ` trên Mẫu 15 với tổng số lượng trên các tờ khai nhập
mang mã đó (theo loại hình nhập của doanh nghiệp). Mức độ theo % chênh lệch tuyệt
đối: dưới 5% → Thông tin, 5–20% → Cảnh báo, trên 20% → Nghiêm trọng
(`app/checks/registry.py:_C1_1`). Chứng cứ cần yêu cầu doanh nghiệp: toàn bộ tờ
khai nhập mang mã đó trong kỳ, đối chiếu số lượng thực nhận trên phiếu nhập kho.
Giải thích vô can thường gặp: đơn vị tính lệch trong cùng họ đơn vị (không phải
sai ×1000, xem `C3.3`); tờ khai thông quan sát ranh giới kỳ báo cáo (khai trước
31/12 nhưng thông quan sang năm sau hoặc ngược lại); làm tròn số lượng khi gộp
nhiều tờ khai cùng mã.

**C1.2 — Có tờ khai nhập nhưng không có trong M15**
Mã có tờ khai nhập trong kỳ nhưng không có dòng nào trên Mẫu 15. Luôn Nghiêm
trọng, đánh dấu mọi trường hợp không có ngưỡng %. Chứng cứ: tờ khai mang mã đó
(khối chứng cứ Mẫu 15 sẽ trả 0 dòng — đó chính là bằng chứng của phát hiện, không
phải lỗi tra cứu). Giải thích vô can thường gặp: mã đã tất toán/thanh khoản từ kỳ
trước nên hợp lý là không xuất hiện lại; mã nhập cho mục đích khác không phải NVL
sản xuất xuất khẩu (cần xác minh loại hình); lệch danh mục mã giữa hệ thống khai
báo và hệ thống kế toán nội bộ doanh nghiệp.

**C1.3 — Có trong M15 nhưng không có tờ khai**
Ngược lại C1.2: `nhập_trong_kỳ` > 0 trên Mẫu 15 nhưng không có tờ khai nhập tương
ứng nào trong kỳ. Luôn Nghiêm trọng. Chứng cứ: dòng Mẫu 15 mang mã đó, đối chiếu
toàn bộ tờ khai nhập trong kỳ (0 dòng khớp). Giải thích vô can thường gặp: mã vật
tư đổi tên/đổi mã giữa hai kỳ mà tồn kho kế thừa mã cũ; sai kỳ báo cáo của tờ khai
liên quan (thông quan ngoài cửa sổ kỳ `period_from`–`period_to` đang xét, xem mục
B8 cẩm nang). Vì bài này không có ngưỡng %, mọi mã không có căn cứ tờ khai đều bị
gắn cờ như nhau dù chênh lệch số lượng nhỏ — xem thêm mục 5 về quan hệ với `C1.1`.

**C1.4 — Lệch số lượng xuất thành phẩm (M15a vs tờ khai)**
So sánh `xuất_khẩu` trên Mẫu 15a với tổng số lượng tờ khai xuất mang mã thành
phẩm đó (theo loại hình xuất). Ngưỡng chặt hơn C1.1: dưới 1% → Thông tin, 1–5% →
Cảnh báo, trên 5% → Nghiêm trọng. Chứng cứ: tờ khai xuất mang mã đó, đối chiếu
phiếu xuất kho/vận đơn. Giải thích vô can thường gặp: quy đổi đơn vị đóng gói
thương mại (kiện/thùng) sang đơn vị hải quan chuẩn làm tròn khác nhau; tờ khai
xuất cận kỳ (hàng đã thông quan nhưng ghi nhận kế toán lệch sang kỳ khác).

**C1.6 — Chuyển mục đích sử dụng không có tờ khai A42**
`chuyển_mục_đích_sử_dụng` > 0 trên Mẫu 15 nhưng không có tờ khai `A42` tương ứng
trong kỳ. Luôn Nghiêm trọng. Chứng cứ: dòng Mẫu 15 (cột chuyển mục đích sử dụng)
mang mã đó, đối chiếu toàn bộ tờ khai `A42` trong kỳ (0 dòng khớp). Giải thích vô
can thường gặp: cột Mẫu 15 ghi nhận nhầm hạng mục (nhầm với xuất khác); chuyển mục
đích sử dụng đã khai dưới mã loại hình khác `A42` mà hệ thống không dò tới — cần
đối chiếu thủ công mã loại hình cụ thể doanh nghiệp dùng.

**C1.7 — Tỷ lệ chuyển mục đích sử dụng vượt ngưỡng**
Tỷ lệ `chuyển_mục_đích_sử_dụng / (tồn_đầu_kỳ + nhập_trong_kỳ)`: từ 10% → Cảnh báo,
từ 25% → Nghiêm trọng (dưới 10% không gắn cờ). Chứng cứ: dòng Mẫu 15 mang mã đó.
Giải thích vô can thường gặp: đặc thù ngành có tỷ lệ dư thừa nguyên liệu hợp đồng
cao được phép chuyển đổi mục đích hợp lệ (vẫn cần có `A42` — đối chiếu cùng
`C1.6`); doanh nghiệp tái cơ cấu/thu hẹp sản xuất trong kỳ nên tỷ lệ tăng đột biến
một lần.

### Nhóm 2 — Cân bằng và tồn kho

**C2.1 — Mất cân bằng phương trình M15 (NVL)**
Kiểm tra đẳng thức: `tồn_cuối = tồn_đầu + nhập − tái_xuất − chuyển_MĐSD − xuất_SX
− xuất_khác` (sai số cho phép ±0,01), bao gồm trường hợp tồn ảo (tồn đầu = 0 nhưng
tồn cuối > nhập). Luôn Nghiêm trọng. Chứng cứ: dòng Mẫu 15 mang mã đó với đủ các
cột trong phương trình. Giải thích vô can thường gặp: sai số làm tròn cộng dồn qua
nhiều cột; doanh nghiệp bỏ sót một cột khi lập báo cáo (ví dụ quên cộng "xuất
khác"). Đây là kiểm tra số học nội tại của chính báo cáo — không phụ thuộc diễn
giải nghiệp vụ, một khi đẳng thức không khớp thì báo cáo không tự nhất quán.

**C2.2 — Mất cân bằng phương trình M15a (TP)**
Tương tự C2.1 cho thành phẩm: `tồn_cuối = tồn_đầu + nhập_kho − chuyển_MĐSD −
xuất_khẩu − xuất_khác`. Luôn Nghiêm trọng. Chứng cứ và giải thích vô can tương tự
C2.1, áp cho Mẫu 15a.

**C2.3 — Tồn cuối NVL âm**
`tồn_cuối_kỳ` < 0 trên bất kỳ mã NVL nào (Mẫu 15). Luôn Nghiêm trọng. Chứng cứ:
dòng Mẫu 15 mang mã đó. Giải thích vô can thường gặp: đợt nhập về cuối kỳ chưa kịp
ghi nhận trước khi số liệu xuất đã trừ (lệch thời điểm ghi sổ, không phải lệch số
lượng thật); lỗi dấu khi nhập liệu. Tồn âm về bản chất nghĩa là báo cáo ghi nhận
xuất nhiều hơn những gì báo cáo ghi nhận đã có — cần xác minh nguồn gốc phần chênh.

**C2.4 — Tồn cuối TP âm**
Tương tự C2.3, áp cho thành phẩm trên Mẫu 15a. Luôn Nghiêm trọng.

### Nhóm 3 — Phân loại hàng hoá

**C3.1 — Cùng mã vật tư khai nhiều loại hình mâu thuẫn**
Một mã xuất hiện cả trên tờ khai NVL (`E11`/`E15`/`E31`/`E33`/`E21`/`E23`) và tờ
khai máy móc thiết bị miễn thuế `E13` trong cùng kỳ. Cặp mâu thuẫn xét: `E11+E13`,
`E31+E13`, `E21+E13`. Cảnh báo. Chứng cứ: các tờ khai mang mã đó ở cả hai loại
hình. Giải thích vô can thường gặp: mã vật tư nội bộ doanh nghiệp dùng trùng cho
cả nguyên liệu và phụ tùng máy móc — lỗi đặt mã trong hệ thống kế toán nội bộ,
không phải khai sai hải quan; cần đối chiếu tên hàng thực tế trên hai tờ khai.

**C3.2 — Mã HS không nhất quán trong kỳ**
Cùng một mã vật tư có từ 2 mã HS khác nhau trên các tờ khai trong kỳ. Mức độ theo
độ sâu khác biệt: khác phân nhóm 6 số → Thông tin, khác nhóm 4 số → Cảnh báo, khác
chương 2 số → Nghiêm trọng. Chứng cứ: các tờ khai mang mã đó kèm mã HS khai trên
từng tờ. Giải thích vô can thường gặp: nhà cung cấp/đối tác nước ngoài khai HS
khác nhau giữa các đợt giao hàng cho cùng lô nguyên liệu; đã có công văn điều
chỉnh mã HS được cơ quan Hải quan chấp nhận; mã vật tư nội bộ gộp nhiều quy cách
kỹ thuật khác nhau dưới một mã, nên đúng là ứng với nhiều mã HS thật.

**C3.3 — Đơn vị tính không nhất quán**
Cùng mã NVL dùng từ 2 đơn vị tính khác nhau giữa Mẫu 15 và tờ khai. Mức độ tính
qua bảng đơn vị chuẩn/quy đổi (`/admin/units`): hai đơn vị cùng họ có thể quy đổi
(KG↔GAM, M↔CM) → Thông tin; khác họ hoặc không rõ quy đổi → Nghiêm trọng vì có thể
là sai đơn vị ×1000 (`app/checks/c3_classify.py:check_c3_3`). Chứng cứ: dòng Mẫu
15 và tờ khai mang mã đó, đối chiếu đơn vị ghi trên từng nguồn. Giải thích vô can
thường gặp cho mức Thông tin: đơn vị đóng gói thương mại khác đơn vị hải quan
chuẩn nhưng quy đổi đúng. Mức Nghiêm trọng cần đối chiếu ngay — sai đơn vị ×1000
làm sai lệch toàn bộ số liệu nhập/xuất/tồn của mã đó một cách hệ thống.

### Nhóm 4 — Định mức M16

**C4.1 — NVL trong M16 không có nguồn**
Mã NVL có dòng định mức trên Mẫu 16 nhưng không có dòng nào trên Mẫu 15, hoặc có
dòng Mẫu 15 nhưng cả `nhập_trong_kỳ` và `tồn_đầu_kỳ` đều bằng 0. Luôn Nghiêm
trọng. Chứng cứ: dòng Mẫu 16 (định mức) mang mã đó, đối chiếu dòng Mẫu 15 nếu có.
Giải thích vô can thường gặp: định mức là thông số kỹ thuật ổn định, khai một lần
cho sản phẩm, có thể vẫn còn trong Mẫu 16 dù nguồn nhập của mã đó đã hết từ các kỳ
trước không còn xuất hiện gần đây; định mức chuẩn bị sẵn cho thành phẩm mới chưa
phát sinh sản xuất thực tế trong kỳ.

**C4.3 — Tổng tiêu hao M16 vượt xuất sản xuất M15**
So sánh tiêu hao lý thuyết Σ(`định_mức` × `xuất_khẩu` trên Mẫu 15a) tính theo từng
mã NVL, với tiêu hao thực tế là `xuất_sản_xuất` trên Mẫu 15 cùng mã. Vượt trên 5%
→ Cảnh báo, trên 20% → Nghiêm trọng. Lưu ý về công thức đang dùng: số nhân là số
lượng **xuất khẩu** trên Mẫu 15a (`app/checks/c4_norm.py:check_c4_3`), không phải
sản lượng sản xuất trong kỳ — mục 5 nêu đây là điểm còn để mở, có thể ảnh hưởng số
% chênh lệch tính ra. Chứng cứ: dòng Mẫu 16 (định mức) mang mã NVL đó, dòng Mẫu 15a
(số lượng xuất khẩu thành phẩm dùng mã NVL đó), dòng Mẫu 15 (xuất sản xuất mã NVL
đó). Giải thích vô can thường gặp: tiêu hao thực tế tốt hơn định mức đã đăng ký
(cải tiến quy trình chưa cập nhật lại Mẫu 16) — hợp lệ nếu định mức đăng ký được
hiểu là mức trần cho phép; nguyên vật liệu đang nằm ở bán thành phẩm dở dang, chưa
cấu thành đủ thành phẩm xuất khẩu trong kỳ (đối chiếu thêm sổ bán thành phẩm nếu
doanh nghiệp có, nhóm kiểm tra 9 chưa triển khai trong bản này).

### Nhóm 5 — Truy nguồn nguyên vật liệu nhập khẩu

**C5.1 — NVL có xuất sản xuất trong M15 nhưng không có nhập khẩu**
Mẫu 15 có `xuất_sản_xuất` > 0 nhưng cả `nhập_trong_kỳ` và `tồn_đầu_kỳ` đều bằng 0.
Luôn Nghiêm trọng. Chứng cứ: dòng Mẫu 15 mang mã đó. Giải thích vô can thường gặp:
nhầm kỳ ghi nhận nhập — hàng đã nhập ở kỳ trước, tồn đầu kỳ này lẽ ra phải dương
nhưng khai sai bằng 0 (đối chiếu với tồn cuối kỳ trước qua `C6.1`); lỗi nhập liệu
cột nhập/tồn đầu.

### Nhóm 6 — Kiểm tra liên kỳ

**C6.1 — Tồn đầu kỳ N khác tồn cuối kỳ N-1 (NVL)**
So từng mã NVL: tồn đầu kỳ hiện tại trên Mẫu 15 phải khớp tồn cuối kỳ liền trước
(sai số ±0,01). Cần có dữ liệu ≥2 kỳ liên tiếp mới chạy được. Luôn Nghiêm trọng.
Chứng cứ: dòng Mẫu 15 mang mã đó ở cả kỳ N và kỳ N−1. Giải thích vô can thường
gặp: doanh nghiệp điều chỉnh số liệu tồn kho giữa hai kỳ theo biên bản kiểm kê
thực tế (yêu cầu xuất trình biên bản); đổi mã vật tư giữa hai kỳ mà không có bảng
map mã cũ–mã mới, khiến hệ thống hiểu nhầm thành hai mã độc lập.

### Phát hiện kết hợp (combo)

Khi quản trị viên bật tính năng này (`/admin/checks`, công tắc "Phát hiện kết
hợp"), một số tổ hợp bài kiểm tra cùng gắn cờ trên **cùng một mã hàng** được gộp
thành một phát hiện riêng, mã bắt đầu bằng `COMBO_`, hiển thị ở đầu trang. Bốn tổ
hợp hiện có (`app/checks/combos.py`): `C2.3+C4.3`, `C1.3+C5.1`, `C2.1+C4.3`,
`C3.2+C3.3`. Ý nghĩa của combo không vượt quá tổng ý nghĩa của các bài thành phần —
đây là cách gộp hiển thị để cán bộ thấy ngay khi nhiều dấu hiệu trùng trên một mã,
không phải một phép kiểm tra độc lập mới. Đọc kỹ từng bài thành phần trước khi
đánh giá combo.

---

## 5. Giới hạn đã biết

**Chỉ 17/49 bài kiểm tra chạy được.** 32 bài còn lại trong đề án ở trạng thái
"Bổ sung thí điểm" (đã thiết kế, chưa viết code — chủ yếu các nhóm 4, 5, 6 mở
rộng) hoặc "Cần thêm điều kiện" (nhóm 7–12: cần dữ liệu doanh nghiệp cung cấp
thêm như sổ kho phế liệu, danh mục tài sản cố định, bảng cân đối phát sinh kế
toán; hoặc cần danh mục tham chiếu Hải quan như danh sách nhà cung cấp rủi ro,
hoặc cần ≥30 doanh nghiệp cùng ngành trong danh mục để so sánh chéo). Không có
phát hiện ở các nhóm này không có nghĩa doanh nghiệp sạch ở khía cạnh đó — có
nghĩa hệ thống chưa kiểm tra khía cạnh đó.

**Điểm rủi ro 0–1000 hiện không đáng tin cậy để so sánh giữa các doanh nghiệp.**
Công thức (`app/checks/scoring.py:compute_company_year_score`): mỗi bài kiểm tra
đóng góp tối đa 10 điểm theo tỷ lệ phát hiện/mẫu số (số mã NVL, số mã TP, hoặc số
dòng định mức tuỳ bài), cộng thêm tối đa 20 điểm nếu có combo, rồi quy đổi về
thang 0–1000 bằng cách chia cho một **trần lý thuyết** `max_raw = 17 × 10 + 20 =
190` — trần này giả định cả 17 bài cùng đạt điểm tối đa (mọi mã hàng đều có phát
hiện Nghiêm trọng ở cả 17 bài) cộng cả combo cùng lúc, một tình huống thực tế gần
như không xảy ra. Hệ quả là điểm thực tế bị nén rất thấp so với thang hiển thị.

Ví dụ minh hoạ tính đúng theo công thức trên (số liệu giả định để minh hoạ, không
phải một doanh nghiệp thật): một doanh nghiệp mà **100% mã NVL đều có tồn cuối âm**
(`C2.3`, mọi mã đều Nghiêm trọng, các bài khác sạch) — bài `C2.3` đạt tối đa
10/10 điểm, `raw = 10`, điểm quy đổi `= round(1000 × 10 / 190) = 53`. Theo bảng
mức mặc định (`app/checks/scoring.py:TIERS`, quản trị viên chỉnh được ở
`/admin/risk-tiers`), 53 điểm rơi vào mức **"Có chênh lệch nhỏ"** (khoảng 51–100)
— mức thứ hai từ dưới lên trên 5 mức, dù toàn bộ danh mục NVL của doanh nghiệp đó
đang vi phạm phương trình cân đối kho. Kết luận thực dụng: **đọc bảng chi tiết
phát hiện theo từng bài kiểm tra, không dùng riêng điểm tổng để kết luận mức độ
nghiêm trọng.** Điểm số hữu ích để xếp thứ tự ưu tiên tương đối giữa nhiều doanh
nghiệp trong cùng một đợt rà soát, không dùng để nói "doanh nghiệp X điểm thấp
nên sạch".

**Một số bài kiểm tra không độc lập — cùng một mã hàng dễ bị đếm ở nhiều bài.**
Theo chính định nghĩa các bài: mọi mã bị `C1.3` gắn cờ (nhập trên Mẫu 15 nhưng 0
tờ khai khớp) đương nhiên cũng khiến `C1.1` tính ra chênh lệch 100% (so với mẫu
số 0 tờ khai) nên gần như chắc chắn cũng bị `C1.1` gắn cờ ở mức Nghiêm trọng.
Tương tự, một mã có tỷ lệ chuyển mục đích sử dụng đủ cao để `C1.7` gắn cờ thường
cũng thiếu tờ khai `A42` nên đồng thời bị `C1.6` gắn cờ. Khi đọc câu "N bài kiểm
tra cùng gắn cờ trên mã này" ở trang chi tiết mã hàng, không cộng dồn N bài đó
thành N bằng chứng độc lập — kiểm tra xem có phải cùng một nguyên nhân gốc đang
được nhiều bài phản ánh lại hay không.

**Một số bài kiểm tra gắn cờ tỷ lệ rất lớn mã hàng của cùng một doanh nghiệp.**
Khi phần lớn mã hàng của một doanh nghiệp cùng bị một bài gắn cờ (ví dụ hầu hết
mã NVL đều có tồn cuối âm, hoặc hầu hết đơn vị tính không khớp giữa Mẫu 15 và tờ
khai), nên đọc đó là **một điều kiện mang tính hệ thống của cách doanh nghiệp lập
báo cáo** (sai quy trình lập Mẫu 15, hoặc sai đơn vị tính chuẩn hoá toàn bộ danh
mục), không phải N trường hợp ngoại lệ riêng lẻ cần xử lý từng mã một. Cách xử lý
phù hợp là làm rõ nguyên nhân gốc với doanh nghiệp (ví dụ đổi đơn vị tính chuẩn ở
`/admin/units` nếu là lỗi quy đổi hệ thống) rồi chạy lại kiểm tra, thay vì lập hồ
sơ riêng cho từng mã.

**C4.3 dùng số lượng xuất khẩu, chưa dùng sản lượng sản xuất, làm số nhân.** Ghi
trong mục 4: công thức hiện tại nhân định mức với số lượng **xuất khẩu** trên Mẫu
15a. Đây là điểm còn mở trong quy trình dự án (`.ai/STATUS.md`, mục Next Steps —
chờ cập nhật đề án gốc trước khi đổi code), có thể ảnh hưởng đến % chênh lệch tính
ra cho các doanh nghiệp có chênh lệch lớn giữa sản lượng sản xuất và sản lượng
thực xuất trong kỳ (hàng tồn kho thành phẩm chưa xuất).

**Không phân biệt được "0 phát hiện vì sạch" với "0 phát hiện vì thiếu dữ liệu để
so sánh" ở một số trường hợp biên.** Ví dụ một bài kiểm tra cần ≥2 kỳ dữ liệu
(`C6.1`) mà doanh nghiệp mới chỉ có 1 kỳ sẽ cho 0 phát hiện giống hệt trường hợp
đã có 2 kỳ và khớp hoàn toàn — phân biệt trạng thái "chưa đủ điều kiện đánh giá"
là hạng mục đang chờ xử lý (`.ai/STATUS.md`, mục "Tầng C — chờ họp").

**Kiểm tra mở rộng (`X.*`) không thuộc danh mục 49 bài chính thức.** Quản trị viên
có thể tự soạn thêm bài kiểm tra qua `/admin/checks`, mã bắt đầu bằng `X.` để phân
biệt. Khi công bố (`status = published`), bài này chạy tự động cùng các bài chính
thức và cũng được tính vào điểm rủi ro — nhưng logic và ngưỡng của nó không nằm
trong đề án Audit-HQ, không được rà soát theo cùng quy trình 6 bài nhóm 1–6 ở
trên. Kiểm tra mã bài có tiền tố `X.` hay `C.` trước khi tra cứu ý nghĩa ở mục 4.

**Trang danh mục kiểm tra công khai (`/danh-muc-kiem-tra`) hiện hiển thị cả cột
"Rủi ro nghiệp vụ" (`risk`)**, diễn giải động cơ vi phạm cho từng bài — khác với
cách trình bày trung tính (`problem`) dùng trong tài liệu này theo đúng yêu cầu
đào tạo. Khi đọc trang đó, tách riêng cột mô tả vấn đề (trung tính) khỏi cột diễn
giải rủi ro (đã có kết luận sẵn về động cơ) để không nhầm một khả năng suy đoán
thành sự thật đã xác lập.

---

## 6. Câu hỏi thường gặp và bảng thuật ngữ

### Câu hỏi thường gặp

**Một phát hiện xuất hiện trên hệ thống có phải là bằng chứng vi phạm không?**
Không. Đó là một chỗ lệch số liệu giữa các tài liệu doanh nghiệp tự nộp, cần đối
chiếu. Mục 4 liệt kê giải thích vô can thường gặp cho từng bài — kiểm tra trước
khi coi là dấu hiệu cần xử lý tiếp.

**Vì sao tôi không thấy một doanh nghiệp cần làm việc trong danh sách?**
Tài khoản cán bộ chỉ thấy doanh nghiệp được quản trị viên phân công. Liên hệ quản
trị viên để được phân công thêm.

**Vì sao nút "Chạy kiểm tra" bị mờ?**
Kỳ đó chưa có dữ liệu **trong kho** — có thể đã tải file lên nhưng chưa bấm nạp,
hoặc file dừng ở cổng xác nhận cột (mục 2.3) chưa được xác nhận.

**Tôi sửa map cột của một file đã nạp rồi, vì sao phát hiện cũ chưa đổi ngay?**
Việc chạy lại kiểm tra sau khi sửa cột được xếp vào hàng đợi công việc, chạy nền —
xem tiến độ ở **📋 Công việc**. Chỉ những bài đọc đúng cột vừa sửa được chạy lại
(trừ khi cột vừa sửa là cột mã hàng, hoặc vừa đổi sổ quyết toán, khi đó toàn bộ
kỳ được chạy lại).

**Doanh nghiệp giải trình được một phát hiện, tôi phải làm gì trên hệ thống?**
Mở trang chi tiết phát hiện, nhập ghi chú giải thích căn cứ, đặt trạng thái
`rejected` (Loại trừ) nếu xác định không phải vấn đề, hoặc `noted` (Đã ghi chú)
nếu ghi nhận để theo dõi tiếp. `rejected` sẽ loại phát hiện đó khỏi điểm rủi ro,
điểm tính lại ngay không cần chạy lại kiểm tra.

**File Excel đúng mẫu nhưng hệ thống vẫn báo lỗi cấu trúc, phải làm sao?**
Xem chi tiết lỗi trên trang tải lên (mục 2.3) — hệ thống nêu cụ thể cột nào lệch
vị trí so với chuẩn. Có thể bấm **Chẩn đoán bằng AI** để phân tích thêm, hoặc mở
**xem nhanh nội dung file** để tự đối chiếu trang tính và dòng tiêu đề thật với
mẫu chuẩn Thông tư 39.

**Trợ lý AI trả lời có dùng để lập hồ sơ được không?**
Không trực tiếp. Trợ lý là công cụ tra cứu, luôn cho biết đã dùng công cụ nào để
lấy số — nhưng số liệu dùng để lập hồ sơ phải lấy từ bảng số liệu và trang chi
tiết phát hiện, đối chiếu độc lập trước khi dùng.

### Bảng thuật ngữ

| Thuật ngữ / định danh | Nghĩa |
|---|---|
| BCQT | Báo cáo Quyết toán — hồ sơ nhập/xuất/tồn NVL và thành phẩm doanh nghiệp nộp định kỳ theo TT38/TT39 |
| Mẫu 15 / `m15` | Bảng cân đối nhập – xuất – tồn nguyên vật liệu |
| Mẫu 15a / `m15a` | Bảng cân đối nhập – xuất – tồn thành phẩm |
| Mẫu 16 / `m16` | Bảng định mức thực tế NVL cho từng thành phẩm |
| BCCT | Dữ liệu tờ khai xuất nhập khẩu (Báo cáo hàng chi tiết), trong hệ thống lưu ở bảng `declaration_lines` |
| `check_code` | Mã bài kiểm tra, ví dụ `C1.1`; tiền tố `C` = danh mục chính thức, `X` = kiểm tra mở rộng do quản trị viên tự soạn |
| Phát hiện (finding) | Một chỗ lệch cụ thể do một bài kiểm tra sinh ra, gắn với một mã hàng và một kỳ |
| `severity` | Mức độ phát hiện: `critical` (Nghiêm trọng, 10 điểm) · `warning` (Cảnh báo, 3 điểm) · `info` (Thông tin, 1 điểm) |
| `status` (của phát hiện) | Trạng thái xử lý: `new` (Mới) · `confirmed` (Xác nhận) · `rejected` (Loại trừ) · `noted` (Đã ghi chú) |
| Sổ quyết toán / `book` | Nhãn phân biệt hai bộ Mẫu 15/15a/16 khi một pháp nhân giữ nhiều chế độ (`EPE` chế xuất, `GC` gia công); `NULL` = doanh nghiệp một sổ |
| Liên sổ | Nhãn hiển thị cho phát hiện có `book = NULL` ở doanh nghiệp nhiều sổ — thường là phát hiện đối chiếu với tờ khai (tờ khai dùng chung cho mọi sổ) |
| Chứng cứ truy nguồn / `evidence_refs` | Danh sách (bảng, điều kiện lọc) trỏ về đúng dòng dữ liệu Tầng 1 đã sinh ra phát hiện |
| Tầng 1 | Lớp dữ liệu gốc đã nạp từ Excel (các bảng `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`) — nơi mọi phát hiện truy nguồn về |
| Điểm rủi ro dữ liệu | Điểm 0–1000 cho một cặp (doanh nghiệp, kỳ), xem giới hạn ở mục 5 |
| `tier` | Một trong 5 mức cảnh báo ứng với khoảng điểm, ngưỡng chỉnh được ở `/admin/risk-tiers` |
| Mẫu số (denominator) | Số mã NVL, số mã TP, hoặc số dòng định mức dùng làm cơ sở tính tỷ lệ phát hiện cho một bài kiểm tra |
| Combo (phát hiện kết hợp) | Phát hiện gộp khi nhiều bài kiểm tra cùng gắn cờ trên một mã hàng, mã bắt đầu `COMBO_` |
| `DataFile` — nhãn tiến độ | Đã tải lên (`pending`) → Đã phân tích (`analyzed`) → Đã nạp (`ok`), hoặc Cảnh báo/Lỗi |
| Nhãn độ tin cậy cột | Đã kiểm (`verified`) / Cần xác nhận (`needs_review`) — trục độc lập với nhãn tiến độ |
| Công việc (job) | Một lượt xử lý chạy nền (nạp dữ liệu, chạy kiểm tra, sinh tổng quan AI), theo dõi ở `/jobs` |
| `problem` (catalog) | Mô tả nghiệp vụ trung tính của một bài kiểm tra — dùng trong tài liệu đào tạo này |
| `risk` (catalog) | Diễn giải động cơ vi phạm gắn với một bài kiểm tra — hiển thị công khai ở `/danh-muc-kiem-tra`, không dùng làm căn cứ kết luận |

---

*Nguồn tham chiếu chính khi biên soạn: `app/routes/companies.py`, `app/routes/docs.py`,
`app/checks/registry.py`, `app/checks/denominators.py`, `app/checks/scoring.py`,
`app/checks/c4_norm.py`, `app/checks/combos.py`, `app/checks/company_type.py`,
`app/catalog_full.py`, `app/books.py`, `app/pipeline/validate.py`,
`app/pipeline/ingest.py`, `.ai/STATUS.md`, `.ai/BACKLOG.md`, và cẩm nang sử dụng
`app/static/docs/huong-dan/index.html`.*
