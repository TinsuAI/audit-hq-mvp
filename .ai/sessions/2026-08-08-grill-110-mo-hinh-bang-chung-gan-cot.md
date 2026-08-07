# Phiên 2026-08-07/08 — Grill #110: mô hình bằng chứng + màn gán cột

Không sửa dòng code sản phẩm nào. Sản phẩm của phiên: ADR #28, từ vựng, spec #116, năm vé, và bản
trích nguyên văn hướng dẫn lập Mẫu 16 từ Công báo. `main` @ `05e8e96`, bốn commit đều là tài liệu.

## What Was Done

**Rà bằng chứng bốn slot (việc 1 của #110)** — `.ai/notes/2026-08-07-ra-bang-chung-bon-slot.md`.
Đối chiếu trường adapter ĐỌC/GHI với trường có mặt trong dict `evidence`: m16 8/2 · m15 11/8 ·
m15a 10/7 · bcct đủ 100%. Tìm được **đúng một** ghi chú vòng tránh (`registry.py:471`), đúng chỗ
#109 đã nêu — không còn chỗ nào khác cùng dạng.

**Grill 10 câu** (skill `grilling`), mỗi câu một quyết định của owner. Kết quả ghi thành **ADR #28**
ở `.ai/DECISIONS.md` và năm mục từ vựng mới ở `.ai/GLOSSARY.md`.

**Spec #116** — xuất bản qua `/to-spec` (owner tự gõ). 28 user story, quyết định cài đặt, quyết định
test kèm seam, phạm vi loại trừ. Ba vé lát trỏ tới nó.

**Năm vé, cạnh chặn khai bằng issue dependency thật của GitHub:**
`#111` (module khai + đảo chiều suy bằng chứng — đóng #109 và lỗ `note`) → `#112` (màn gán cột +
cột `absent_fields` + migration) → `#113` (cổng `not_evaluable` mức trường + khai bù bcct);
`#114` (bộ mã cột (9) phụ thuộc kỳ, chặn bởi #111); `#115` (đơn vị tính không resolve được, rời).

**Tra nguyên văn hướng dẫn lập Mẫu 16 từ hai thế hệ văn bản** —
`.ai/notes/2026-08-08-huong-dan-lap-mau-16-tt39.md`.

## Decisions Made

Mười quyết định của owner, đầy đủ lý do và phương án bị loại ở ADR #28. Tóm tắt:

1. **Tập trường khai của biểu** là nguồn sự thật cho màn gán, không phải "trường máy đặt được".
   Phỏng đoán của máy thành giá trị điền sẵn.
2. **"Bắt buộc" là HAI sự thật**: *bắt buộc theo biểu* (khai cùng tập trường) và *có check đọc*
   (suy từ `CHECK_COLUMNS`). Không gộp — hậu quả khác nhau nên cảnh báo khác nhau.
3. **Ba trạng thái gán**: đã gán · chưa gán · **xác nhận không có trong file**. Cái thứ ba là thứ
   cho cảnh báo "thiếu trường bắt buộc" một đường đóng.
4. **Khai đặt ở MỘT module dưới `app/adapters/`**, mỗi biểu một mục. `CHECK_COLUMNS` ở lại
   `registry.py`. Hằng vị trí cột của adapter giữ nguyên. Test chống trôi khoá hai bên.
5. **Gửi biểu mẫu = xác nhận mọi trường đang hiện** → màn BẮT BUỘC hiện cột đang gán + mẫu giá trị
   mỗi dòng. Không thêm bậc mới vào thang ADR #18.
6. **Màn theo TRƯỜNG (field-major)**. Phía cột ("cột này không phải trường nào") **không dựng** —
   dưới field-major đó đã là mặc định của mọi cột.
7. **`absent_fields`** là cột JSON MỚI trên `saved_column_maps`; `column_map` giữ nguyên hình dạng;
   hai tập bất biến không giao nhau.
8. **Cổng trường vắng** mở rộng cổng tiền-dispatch của `sources.py`; ánh xạ dùng `checks_reading()`
   để cảnh báo trên màn và hành vi lúc chạy không thể lệch; remedy `need-file-this-period`.
9. **Tập trường khai = tập adapter ghi vào Tầng 1** (bỏ phán đoán ra khỏi bước đã hỏng ba lần).
   Khoá dòng: `material_code` (m15) · `product_code` (m15a) · `product_code`+`material_code`+
   `norm_qty` (m16) · ba trường sẵn có của bcct.
10. **Ba lát, tiến lên, không backfill.**

**Quyết định thêm sau khi owner nêu ĐVT:** hai cột đơn vị tính của Mẫu 16 là **bắt buộc theo biểu**
(cột (4) và (7) của biểu chính thức) nhưng **không phải khoá dòng** → cảnh báo, không từ chối file.
Tách hậu quả theo "có phải khoá dòng không" thay vì thêm một tầng khái niệm thứ ba.

**Seam để test — ba seam, đều đã có, không thêm seam mới** (chốt với owner trước khi viết spec):
hàm `parse_*(path)` · route HTTP màn gán qua `app_db` · `run_checks()` → `check_runs`. Cộng một test
chống trôi. `tests/test_evidence_source.py` hiện test thấp hơn seam đúng một bậc → chuyển lên.

**Vé để nguyên sau bước quiz** — owner chốt không tách #111 nhỏ hơn, không đổi cạnh chặn, không thêm
vé prefactor (re-home `FIELD_LABEL_VI`) trước #111.

## What Didn't Work

**Bỏ cuộc quá sớm ở việc tra văn bản.** Lần đầu tôi kết luận "không kiểm chứng được từ nguồn gốc" vì
`pdftotext` trả 91 ký tự và vbpl.vn/thuvienphapluat chặn. Sai: PDF Công báo là **bản quét**, và máy
có sẵn `tesseract` gói `vie`. Owner hỏi lại thì mới làm đúng. Cách làm được:
`pdftoppm -r 120` quét thưa để định vị trang → `-r 300..400` + `tesseract -l vie` ở đúng trang.
Phụ lục nằm ở **tệp riêng**, không trong tệp văn bản chính. `g7.cdnchinhphu.vn` (nút tải trên trang
Công báo) bị chặn — lấy link `datafiles.chinhphu.vn` ở `vanban.chinhphu.vn`.

**Tin bản tóm tắt của công cụ tìm kiếm.** Nó nói cột (9) có năm mã mà **không nói đang mô tả bản
nào** — đúng với TT 121/2025, sai với TT 39/2018 (ba mã). Tôi đưa ra như quy định đã xác nhận; owner
hỏi "quy định hay mày suy từ dữ liệu?" mới lộ. Dữ liệu cũng không ủng hộ: `KXDĐM`/`TH`/`SPTN` xuất
hiện **0 lần** trong 270.385 dòng.

**Đọc nhầm bảng đếm.** Tôi ghi "note rỗng 269.505/270.385, chỉ PILOT_004 có giá trị" và đẩy con số
đó vào ADR + bình luận + vé. Đúng là **2.445 dòng có ghi chú** (1.565 `X` của HONG_AN 2021/2022 +
880 số của PILOT_004 2025). Lượt đo lại còn lộ ra `norms.note` của PILOT_004 **bằng đúng `norm_qty`
ở 880/880 dòng** — adapter đọc một cột vào hai trường.

**Kết luận về ĐVT dựa trên giả định chưa kiểm.** Tôi khuyến nghị hoãn kiểm tra thống nhất ĐVT vì
"cần bảng đồng nghĩa trước". Kiểm lại: **C3.3 đã tồn tại, đã chạy, đã có bảng** (`uom_canonical` 27
+ `uom_aliases` 154), và `resolve_canonical` tách được đơn vị ghép nên `Cái/Chiếc` resolve bình
thường. Con số 5.088/5.092 "lệch chuỗi" tôi đưa **không phải số phát hiện sai**. Kết luận (không
khai ĐVT vào `CHECK_COLUMNS`) vẫn đúng nhưng **lý do thì sai**, đã sửa ở ADR và ở #113.

**Thay skill mà không báo.** Ghi chú bàn giao yêu cầu `/grill-with-docs`; nó khai
`disable-model-invocation: true` nên không có trong danh sách của phiên. Tôi lặng lẽ chạy `grilling`
rồi tự viết spec + tự mở vé. Owner hỏi "sao không chạy to-spec với to-tickets?" mới lộ. Hệ quả thật:
**bỏ mất bước "phác thảo seam rồi hỏi lại owner"** của `to-spec` — bước ảnh hưởng nhiều nhất tới cách
cài. Đã chạy bù (owner tự gõ `/to-spec`).

**Job nền chết im lặng.** `nohup ./sweep.sh &` để OCR 371 trang báo "completed exit 0" sau 27 trang.
Chuyển sang chạy foreground theo lô có `timeout` thì xong.

## Open Items

**Vé sẵn sàng:** **#111** và **#115** grab được ngay. #112 ← #111 · #113 ← #112 · #114 ← #111.
Mỗi vé một session mới, đọc #116 rồi ADR #28 trước.

**Chưa có vé, ghi lại để khỏi mất:**

- **Đối chiếu mã và tên hàng M16 ↔ tờ khai.** Hướng dẫn lập Mẫu 16 buộc cột (2) mã SP, (3) tên SP,
  (5) mã NVL "thống nhất với ... đã khai trên tờ khai hải quan", ở cả hai thế hệ văn bản. Có căn cứ
  pháp lý, chưa kiểm tra nào dùng.
- **Khối chữ ký chân biểu bị đọc thành dòng dữ liệu** — 2 dòng mang giá trị đơn vị là cả câu
  "NGƯỜI ĐẠI DIỆN THEO PHÁP LUẬT CỦA TỔ CHỨC, CÁ NHÂN". Cùng nhánh nhận dòng dữ liệu của #110.
- **`'Real Brasil'` và `'Panh'` xuất hiện ở cột đơn vị** (1 phát hiện C3.3 mỗi loại) — nghi đọc lệch
  cột ở đâu đó, chưa truy.
- **Ghi chú pháp lý nên chuyển về thư viện của repo đề án** (`../audit-hq/.ai/legal/`) — INDEX ở đó
  đã xếp TT 39/2018 vào backlog và nêu quy ước lưu. Để tạm ở repo này vì đang chống lưng ADR #28.

**Còn mở từ trước, không đụng tới phiên này:** #65 thang điểm (chặn xếp hạng DN theo điểm) · #108
hai file test vá `app.database` không khôi phục · #93 cần người chạy (DB dev `alembic upgrade head`
+ dựng `data/PILOT_004/2025/`) · 12 kỳ ở DB dev thiếu combo.

**Cảnh báo khi cài #111:** OCR có nhiễu ở dấu câu và vài chữ. Muốn trích nguyên văn cho tài liệu gửi
ra ngoài thì phải đối chiếu lại bằng mắt trên chính trang quét, đừng chép thẳng từ note.
