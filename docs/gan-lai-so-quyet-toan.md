# Gán lại sổ quyết toán cho pháp nhân nhiều sổ đã nạp bằng dòng lệnh

Áp dụng khi một pháp nhân nhiều sổ (`.ai/GLOSSARY.md` — *Sổ quyết toán (book)*,
*Pháp nhân nhiều sổ*) có dòng Tầng 1 mang nhãn sổ nhưng cột `data_files.book` rỗng ở
mọi file quyết toán của kỳ. Đường nạp trên web từ chối kỳ đó, và từ chối đúng: bộ file
không còn nói được file nào thuộc sổ nào, nạp tiếp sẽ dựng lại các sổ thành MỘT sổ gộp
mà không báo gì.

Trạng thái này sinh ra từ những kỳ nạp bằng dòng lệnh trước #88: mỗi sổ nằm ở một thư
mục riêng và được nạp thành một pháp nhân riêng, nhãn sổ chỉ được gắn lúc gộp hai pháp
nhân lại nên không bao giờ tới `data_files`. #88 sửa đường đi cho lần sau (ô chọn sổ
trên dòng kỳ + cổng khoá nút nạp); tài liệu này gỡ trạng thái đang có.

## Nhận biết

Kỳ ở màn dữ liệu báo "Chưa nạp được: còn N file quyết toán chưa gán sổ …", hoặc lượt
nạp trả về `plan_error` với câu "DN đang có sổ … nhưng không file nào còn nhãn sổ".

Đo bằng SQL (mở chỉ đọc):

```sql
-- sổ đang có ở Tầng 1
SELECT 'nvl' t, book, count(*) FROM nvl_balances WHERE company_id=? AND period_year=? GROUP BY book
UNION ALL SELECT 'sp', book, count(*) FROM sp_balances WHERE company_id=? AND period_year=? GROUP BY book
UNION ALL SELECT 'norm', book, count(*) FROM norms     WHERE company_id=? AND period_year=? GROUP BY book;

-- nhãn sổ trên bản ghi file
SELECT slot, book, count(*) FROM data_files WHERE company_id=? AND period_year=? GROUP BY slot, book;
```

Có sổ khác null ở khối trên + `book` rỗng hết ở khối dưới ⇒ đúng ca này.

## Điều kiện trước khi bắt đầu

1. **Ghi lại số dòng theo từng sổ** (khối SQL trên) và số dòng tờ khai:
   `SELECT count(*), count(DISTINCT declaration_no) FROM declaration_lines WHERE company_id=? AND period_year=?;`
   Đây là mốc đối chiếu sau khi nạp lại. Không có mốc thì không chứng minh được sổ nào
   không mất dòng.
2. **File của MỌI sổ phải nằm trong một thư mục kỳ duy nhất**
   `<raw_data_path>/<MÃ DN>/<năm>/{BCQT,DINH_MUC,HANG_CHI_TIET}`. `sync_data_files` và
   `discover` đều tra theo `company.code`; sổ còn nằm ở thư mục mang mã cũ của thời hai
   pháp nhân thì registry rỗng và không có gì để gán. Hai sổ dùng chung một list tờ khai
   nên `HANG_CHI_TIET` chỉ giữ MỘT bản mỗi file — bản của các sổ trùng nhau từng byte.
3. **Schema DB ở head**: `alembic upgrade head`. Thiếu cột mà model đã khai thì mọi câu
   SELECT lên `data_files` hỏng trước khi tới bước gán.

## Các bước

1. **Đồng bộ registry** — mở màn dữ liệu của DN. `sync_data_files` chạy ở mỗi lượt vào
   trang, dựng lại một dòng cho mỗi (file, biểu).
2. **Gán sổ cho từng file quyết toán** — ô chọn sổ trên dòng kỳ (#88), một lượt cho mỗi
   file m15 / m15a / m16. Tờ khai KHÔNG mang sổ: nó là list dùng chung của cả pháp nhân.
   Một workbook đăng ký cho nhiều biểu là nhiều dòng cùng đường dẫn — endpoint gán cho
   cả nhóm, không để sót dòng nào.
3. **Nạp lại** — nút nạp của kỳ. Nút chỉ mở khi mọi file quyết toán đã có sổ.
4. **Xác nhận cột nếu cổng review bật** — lượt nạp có thể dừng ở `needs_review` (biểu bố
   cục mở rộng, DN chưa có map cột đã lưu). Vào màn xác nhận từng file, giữ nguyên vị trí
   cột đề xuất nếu đúng rồi lưu; **ô "Sổ quyết toán" trên màn này phải giữ giá trị đã
   gán** — màn xác nhận ghi đè `data_files.book` bằng chính ô đó, để trống là xoá nhãn
   vừa gán. Lưu xong hệ thống tự xếp lượt nạp tiếp (không qua cổng review nữa).
5. **Chạy lại kiểm tra** cho kỳ đó.

## Đối chiếu

Chạy lại khối SQL ở phần nhận biết và so với mốc đã ghi. Yêu cầu: **số dòng của TỪNG sổ
khớp trước/sau**. Lệch một sổ về 0 hoặc hai sổ cộng vào một là đúng cái hỏng mà cổng từ
chối sinh ra để chặn — dừng lại, không nạp tiếp.

Số dòng tờ khai không đổi: tờ khai không thuộc sổ nào, lượt nạp đọc lại đúng bộ file cũ.

Phát hiện có thể lệch vì phiên bản parser đã đổi giữa hai lượt nạp. Đối chiếu theo
`(check_code, book)` và giải thích từng khoản lệch, đừng chỉ nhìn tổng.

## Những chỗ dễ hỏng

- **Cửa sổ kỳ sửa tay** (`company_periods.period_from/period_to`, `is_manual=1`) quyết
  định tờ khai nào thuộc kỳ. Dựng lại DN ở một DB khác mà quên cửa sổ này thì mọi kiểm
  tra đối chiếu tờ khai↔quyết toán trả về "chưa có BCCT" và số phát hiện tụt hẳn.
- **Gán sổ phải là tất-cả-hoặc-không.** File còn sót rơi vào `book=NULL`, mà NULL ở pháp
  nhân nhiều sổ nghĩa là "liên sổ" — các kiểm tra nội-sổ sẽ đối chiếu định mức và tồn kho
  bên trong một cái sổ không tồn tại.
- **Thứ tự.** Gán sổ TRƯỚC khi bấm nạp. Nạp trước rồi gán là một lượt nạp gộp sổ đã ghi
  xong; phải gán lại và nạp lại lần nữa.

## Đã kiểm chứng

Quy trình chạy trọn trên bản nháp (DB rỗng + bản sao file của PILOT_004 kỳ 2025), qua
đúng các endpoint của web: gán sổ → nạp → xác nhận cột → nạp lại. Kết quả dựng lại đúng
số dòng đang có trong DB dev: sổ EPE 104 / 43 / 664, sổ GC 37 / 2 / 216, tờ khai 547 dòng
/ 229 số. Xoá nhãn sổ đi thì nút nạp khoá và lượt nạp không được xếp; gán lại rồi nạp lại
cho ra đúng bộ số đó. Kiểm tra chạy lại khớp từng `(check_code, book)` với DB dev, điểm
rủi ro 28.
