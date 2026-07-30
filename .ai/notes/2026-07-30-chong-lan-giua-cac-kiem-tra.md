# Chồng lấn giữa các kiểm tra MVP — đọc code + đo dữ liệu thật

Phạm vi: 17 kiểm tra MVP built-in (`app/checks/c1_quantity.py`, `c2_balance.py`,
`c3_classify.py`, `c4_norm.py`, `c5_trace.py`, `c6_cross_period.py`). Không xét check động
`X.*` (dynamic, `app/checks/sql_runner.py`), không xét `COMBO_*` (đã là finding phái sinh, xem
mục Đo dữ liệu thật). Đo trên `audit_hq.sqlite` local, mở read-only qua
`sqlite3.connect("file:...?mode=ro", uri=True)`, không ghi gì.

## Kết luận

1. Hai bao hàm đã ghi ở `.ai/STATUS.md` (2026-07-29) đều **XÁC NHẬN đúng** trên cả 3
   (DN, kỳ) có dữ liệu để đo — nhưng **không cùng bản chất**:
   - `C1.3 ⊆ C1.1` gần như **cấu trúc** (structural): mọi mã lọt điều kiện C1.3 (có
     `import_qty > 0` mà không có tờ khai nào khớp) khi đưa qua công thức C1.1 luôn cho
     `diff_pct = -100%`, luôn vượt ngưỡng nổ và luôn map sang `severity=CRITICAL`. Chỉ vỡ nếu
     dữ liệu có `import_qty` âm bù trừ giữa hai sổ cùng mã — chưa quan sát thấy trong dữ liệu.
   - `C1.7 ⊆ C1.6` là **thật sự có điều kiện** (data-dependent): `check_c1_6` loại mã có tờ
     khai A42, `check_c1_7` không loại. Containment chỉ đúng vì trong CẢ 4 kỳ đo được, **không
     một mã nào** vừa có tỷ lệ chuyển MĐSD ≥10% vừa có tờ khai A42 — kể cả ở 006/2025 nơi A42
     phủ 652 mã. Đường vỡ tồn tại trong code nhưng chưa từng bị kích hoạt bởi dữ liệu thật.
2. Tìm thêm hai bao hàm chưa từng được ghi nhận: `C1.2 ⊆ C4.1` và `C3.3 ⊆ C1.1`, nhưng **cả
   hai chỉ đúng tại PILOT_004/2025** (mẫu 4-5 dòng) — sai ở 006/2024 và 006/2025 (giao = 0 dù
   quần thể lớn hơn hàng chục lần). Đây là bằng chứng thực nghiệm trực tiếp cho lý do KHÔNG
   được hardcode bảng bao hàm: một quan hệ đúng-tuyệt-đối ở một kỳ có thể là trùng hợp cỡ mẫu
   nhỏ, không phải quy luật của DN.
3. Phát hiện một lớp lỗi khác, nghiêm trọng hơn bao hàm: **`subject_key` một mình KHÔNG đủ để
   làm khoá nhận diện đối tượng.** `material_code` và `product_code` — hai domain lẽ ra tách
   biệt — trùng chuỗi ở ít nhất 2 mã thật (006/2024, ví dụ `RV145MS00G0B-AMR07`) do bảng `norms`
   (BOM Mẫu 16 nhiều cấp) dùng cùng một mã vừa làm `material_code` đầu vào vừa làm
   `product_code` đầu ra ở công đoạn khác. Gộp theo `subject_key` bỏ qua `subject_type` sẽ báo
   "3 kiểm tra cùng gắn cờ mã X" trong khi thực ra 2 kiểm tra nói về mã X với VAI TRÒ NVL và 1
   kiểm tra nói về mã X với VAI TRÒ thành phẩm — hai câu chuyện khác nhau bị dán chung.
4. 6/17 kiểm tra (`C2.1, C2.2, C2.3, C2.4, C5.1, C6.1`) **chưa từng phát sinh finding nào**
   trong toàn bộ `audit_hq.sqlite` (không riêng 4 kỳ có finding) — đã đối chiếu trực tiếp với
   dữ liệu Tầng 1 (`nvl_balances`, `sp_balances`), không phải do check hỏng: 0 dòng thật thoả
   điều kiện C2.1/C2.3/C5.1/C6.1 ở bất kỳ (DN, kỳ) nào. Mọi câu hỏi bao hàm liên quan đến 6
   kiểm tra này **không đo được** bằng dữ liệu hiện có, chỉ suy được từ đọc code.
5. Tính lại "N kiểm tra gắn cờ mã này" theo thuật toán tính động (mục Phương án) cho thấy con
   số hiện tại phóng đại mức độ tương ứng chứng: ở PILOT_006/2025, "3.215 mã bị ≥2 kiểm tra"
   co lại còn **947 mã có ≥2 tín hiệu ĐỘC LẬP** sau khi trừ các kiểm tra bị hấp thụ — giảm hơn
   3 lần.

## Bảng chồng lấn tĩnh từ code

Mọi check chỉ mang MỘT `subject_type`, cố định trong code:

| `subject_type` | Checks | File |
|---|---|---|
| `material_code` | C1.1, C1.2, C1.3, C1.6, C1.7, C2.1, C2.3, C3.3, C4.1, C4.3, C5.1, C6.1 (12) | c1_quantity.py, c2_balance.py, c3_classify.py, c4_norm.py, c5_trace.py, c6_cross_period.py |
| `product_code` | C1.4, C2.2, C2.4 (3) | c1_quantity.py:409, c2_balance.py:128/199 |
| `item_code` | C3.1, C3.2 (2) | c3_classify.py:67/149 |

Theo `subject_type` lưu trên `Finding` (`app/models/finding.py:25`), 66 cặp cross-domain
(material↔product, material↔item, product↔item) **không thể chồng lấn về mặt định danh
đã lưu** — nhưng mục "Đo dữ liệu thật" cho thấy `subject_key` (chuỗi thô) vẫn trùng giữa
`material_code` và `item_code` RẤT RỘNG (cố ý, xem combos.py) và giữa `material_code` và
`product_code` HIẾM nhưng CÓ THẬT (không cố ý). Bảng dưới chỉ xét trong-domain.

### Trong `material_code` (12 check, 66 cặp) — điều kiện nổ rút từ code

| Check | Điều kiện nổ (rút gọn) | File:dòng |
|---|---|---|
| C1.1 | `Σimport_qty(mã, đơn vị) > 0` và `\|diff_pct(BCCT, import)\| ≥ 0.5%` (severity luôn có, không None) | c1_quantity.py:163-239, registry.py:249-253 |
| C1.2 | mã có tờ khai NVL nhưng KHÔNG có dòng M15 nào (mọi sổ) | c1_quantity.py:242-296 |
| C1.3 | dòng M15 có `import_qty > 0` và mã KHÔNG có tờ khai nào (toàn DN) | c1_quantity.py:299-350 |
| C1.6 | dòng M15 có `repurpose_qty > 0` và mã KHÔNG có tờ khai A42 (toàn DN, không theo sổ) | c1_quantity.py:429-473 |
| C1.7 | dòng M15 có `repurpose_qty > 0`, `(opening+import) > 0`, tỷ lệ ≥10% | c1_quantity.py:476-519, registry.py:262-267 |
| C2.1 | `closing ≠ opening+import−reexport−repurpose−production_out−other_out` (±0.01) | c2_balance.py:32-96 |
| C2.3 | `closing_qty < -0.01` | c2_balance.py:150-179 |
| C3.3 | đơn vị M15 (theo sổ) không cùng family với MỌI đơn vị BCCT của mã | c3_classify.py:174-290 |
| C4.1 | mã có trong Norm (M16, theo sổ, không nội địa) và (không có dòng M15 trong sổ đó, HOẶC `import=0` và `opening=0` trong sổ đó) | c4_norm.py:18-93 |
| C4.3 | `Σ(norm×export_qty theo TP) > production_out_qty` quá 5% (theo sổ) | c4_norm.py:96-214, registry.py:270-274 |
| C5.1 | dòng M15 có `production_out_qty>0`, `import_qty==0`, `opening_qty==0` (đúng bằng, không dung sai) | c5_trace.py:15-58 |
| C6.1 | `opening(kỳ N) ≠ closing(kỳ N-1)` cùng (sổ, mã), hoặc mã mới có `opening>0` mà kỳ N-1 không có dòng | c6_cross_period.py:18-107 |

Suy luận logic (không cần đo, đúng với mọi dữ liệu hợp lệ):

- **C1.2 ∩ C1.3 = ∅ luôn** — C1.2 đòi mã KHÔNG có dòng M15 nào; C1.3 đòi mã CÓ dòng M15 với
  `import_qty>0`. Hai điều kiện loại trừ nhau ngay trên mặt chữ.
- **C1.3 ∩ C4.1 = ∅ luôn** (cùng sổ) — nhánh `zero_source` của C4.1 đòi `import=0` trong sổ đó;
  C1.3 đòi `import>0` trong sổ đó. Nhánh `no_m15` của C4.1 đòi không có dòng M15 trong sổ; C1.3
  đòi có dòng. Cả hai nhánh loại trừ C1.3.
- **C1.3 ⊆ C1.1** (gần cấu trúc, xem mục Kết luận #1).
- **C1.7 ⊆ C1.6** (có điều kiện qua A42, xem mục Kết luận #1).
- **C5.1 ⊆ C4.1(nhánh zero_source)** — CHỈ đúng nếu mã C5.1 vừa lọt đồng thời cũng có mặt trong
  Norm (M16) của đúng sổ đó và không phải nội địa. C5.1 không kiểm tra Norm; C4.1 không kiểm
  tra `production_out`. Không đo được (C5.1 không có finding nào để thử).
- Các cặp còn lại (C2.1×C2.3, C2.1×C3.3, C2.1×C4.3, C2.3×C3.3, C2.3×C4.3, C3.3×C4.3,
  C3.3×C6.1, C4.3×C6.1, …) — không tìm được điều kiện nào của check này SUY RA điều kiện của
  check kia bằng cách đọc code. Đây là các cặp **độc lập theo cấu trúc**; nếu chồng lấn thì chỉ
  là tương quan dữ liệu, không phải hệ quả logic. Đo được ở mục sau cho các cặp có finding.

### Trong `product_code` (3 check, 3 cặp)

C1.4 (lệch xuất TP), C2.2 (cân bằng M15a), C2.4 (tồn cuối TP âm) — cùng cấu trúc với nhóm
material (C2.4 đối C2.2 giống hệt C2.3 đối C2.1 về mặt logic: không suy được chiều nào). Không
đo được: C2.2 và C2.4 không có finding nào trong dữ liệu hiện có.

### Trong `item_code` (2 check, 1 cặp)

C3.1 (mã vừa khai NVL vừa khai MMTB E13) và C3.2 (mã có ≥2 HS code) đọc hai TRƯỜNG khác nhau
của `declaration_lines` (`customs_code` với `hs_code`) — không có suy luận logic nào nối hai
điều kiện. Đo độc lập tuyệt đối ở mọi kỳ có dữ liệu (xem bảng đo).

## Bảng đo trên dữ liệu thật

4 (DN, kỳ) có finding trong `audit_hq.sqlite`: PILOT_002/2025, PILOT_006/2024, PILOT_006/2025,
PILOT_004/2025. Không có kỳ nào khác. `company_id`: PILOT_002=7, PILOT_004=9, PILOT_006=8.

Tổng finding mỗi kỳ (đã tách `COMBO_*`, khớp đúng số đã ghi ở STATUS.md 2026-07-29):

| DN/kỳ | Tổng finding (17 check thật) | COMBO_* | Tổng đã ghi trên STATUS |
|---|---|---|---|
| PILOT_002/2025 | 48 | 0 | 48 |
| PILOT_006/2024 | 3.852 | 28 (`COMBO_HS_GAMING`) | 3.880 |
| PILOT_006/2025 | 10.996 | 0 | 10.996 |
| PILOT_004/2025 | 74 | 0 | 74 |

11/17 check có finding ở ít nhất một kỳ: C1.1, C1.2, C1.3, C1.4, C1.6, C1.7, C3.1, C3.2, C3.3,
C4.1, C4.3. 6/17 (C2.1, C2.2, C2.3, C2.4, C5.1, C6.1) **không finding nào ở bất kỳ kỳ nào**,
đã xác nhận trực tiếp trên `nvl_balances`/`sp_balances` (không phải check chưa chạy — `select
count(*) from findings where check_code=...` trả 0 trên TOÀN bảng `findings`, và truy vấn lại
điều kiện thô — vd `production_out_qty>0 and import_qty=0 and opening_qty=0` cho C5.1, hay công
thức cân bằng cho C2.1 — cũng trả 0 dòng ở cả 4 kỳ. C6.1 kiểm chứng riêng: `opening(2025) ==
closing(2024)` đúng tuyệt đối trên cả 7.882 mã NVL 2024 của PILOT_006, không lệch mã nào).

### Ma trận chồng lấn theo (subject_type, subject_key) — khoá đúng

Chỉ liệt các cặp có giao khác 0. `A ⊆ B` là bao hàm TUYỆT ĐỐI đo được (không phải ước lượng).

**PILOT_002/2025** (5 check có finding: C1.1=2, C3.1=2, C3.2=14, C3.3=3, C4.3=27) — **0 cặp có
giao khác 0**. Mọi mã ở đây chỉ bị đúng 1 check gắn cờ.

**PILOT_006/2024** (10 check có finding, 2.820 mã (subject_type,subject_key) riêng biệt):

| Cặp | \|A\| | \|B\| | \|A∩B\| | Quan hệ |
|---|---|---|---|---|
| C1.3 vs C1.1 | 32 | 419 | 32 | **C1.3 ⊆ C1.1** |
| C1.7 vs C1.6 | 618 | 1.660 | 618 | **C1.7 ⊆ C1.6** |
| C1.1 vs C1.6 | 419 | 1.660 | 247 | không bao hàm |
| C1.1 vs C1.7 | 419 | 618 | 20 | không bao hàm |
| C1.1 vs C4.3 | 419 | 564 | 35 | không bao hàm |
| C1.3 vs C1.6 | 32 | 1.660 | 14 | không bao hàm |
| C1.3 vs C1.7 | 32 | 618 | 11 | không bao hàm |
| C1.3 vs C4.3 | 32 | 564 | 1 | không bao hàm |
| C1.4 vs C4.1 | 5 | 17 | 2 | không bao hàm (mã trùng string, khác `subject_type` gốc — xem cảnh báo bên dưới) |
| C1.4 vs C4.3 | 5 | 564 | 1 | không bao hàm (như trên) |
| C1.6 vs C4.3 | 1.660 | 564 | 101 | không bao hàm |
| C1.7 vs C4.3 | 618 | 564 | 22 | không bao hàm |
| C4.1 vs C4.3 | 17 | 564 | 9 | không bao hàm |
| C1.1 vs C3.3 | 419 | 67 | 1 | không bao hàm |
| C1.6 vs C3.3 | 1.660 | 67 | 5 | không bao hàm |
| C3.3 vs C4.3 | 67 | 564 | 2 | không bao hàm |

`COMBO_HS_GAMING` (28 dòng) tách riêng: ⊆ C3.2 (467) và ⊆ C3.3 (67) — đúng theo THIẾT KẾ của
`detect_combos` (chỉ tạo combo khi cả hai trigger đã nổ trên cùng `subject_key`), không phải
một quan hệ mới cần điều tra.

**PILOT_006/2025** (11 check có finding, 7.547 mã riêng biệt):

| Cặp | \|A\| | \|B\| | \|A∩B\| | Quan hệ |
|---|---|---|---|---|
| C1.3 vs C1.1 | 43 | 97 | 43 | **C1.3 ⊆ C1.1** |
| C1.7 vs C1.6 | 2.436 | 5.785 | 2.436 | **C1.7 ⊆ C1.6** |
| C1.1 vs C1.6 | 97 | 5.785 | 76 | không bao hàm |
| C1.1 vs C1.7 | 97 | 2.436 | 56 | không bao hàm |
| C1.1 vs C4.3 | 97 | 1.772 | 22 | không bao hàm |
| C1.3 vs C1.6 | 43 | 5.785 | 42 | không bao hàm |
| C1.3 vs C1.7 | 43 | 2.436 | 40 | không bao hàm |
| C1.3 vs C4.3 | 43 | 1.772 | 3 | không bao hàm |
| C1.6 vs C4.3 | 5.785 | 1.772 | 873 | không bao hàm |
| C1.7 vs C4.3 | 2.436 | 1.772 | 118 | không bao hàm |
| C3.2 vs C4.3 | 776 | 1.772 | 192 | không bao hàm |
| C1.6 vs C3.1 | 5.785 | 9 | 3 | không bao hàm |
| C1.7 vs C3.1 | 2.436 | 9 | 2 | không bao hàm |
| C1.6 vs C3.2 | 5.785 | 776 | 324 | không bao hàm |
| C1.7 vs C3.2 | 2.436 | 776 | 27 | không bao hàm |
| C3.2 vs C3.3 | 776 | 31 | 7 | không bao hàm |
| C1.6 vs C3.3 | 5.785 | 31 | 13 | không bao hàm |
| C3.3 vs C4.3 | 31 | 1.772 | 9 | không bao hàm |
| C1.2 vs C3.1 | 12 | 9 | 3 | không bao hàm (trùng string qua `item_code`↔`material_code`) |
| C3.1 vs C4.3 | 9 | 1.772 | 1 | không bao hàm |

`C3.3 ∩ C1.1 = 0` ở kỳ này (khác PILOT_004/2025 — xem mục "phát hiện mới" dưới).

**PILOT_004/2025** (10 check có finding, 40 mã riêng biệt — mẫu rất nhỏ):

| Cặp | \|A\| | \|B\| | \|A∩B\| | Quan hệ |
|---|---|---|---|---|
| C1.3 vs C1.1 | 13 | 31 | 13 | **C1.3 ⊆ C1.1** |
| C1.6 vs C1.7 | 1 | 1 | 1 | **C1.6 = C1.7** (tập bằng nhau, cùng 1 mã) |
| C1.2 vs C4.1 | 4 | 5 | 4 | **C1.2 ⊆ C4.1** — CHỈ ĐÚNG Ở KỲ NÀY (xem dưới) |
| C3.3 vs C1.1 | 4 | 31 | 4 | **C3.3 ⊆ C1.1** — CHỈ ĐÚNG Ở KỲ NÀY (xem dưới) |
| C1.1 vs C4.3 | 31 | 8 | 4 | không bao hàm |
| C1.2 vs C4.3 | 4 | 8 | 3 | không bao hàm |
| C1.3 vs C4.3 | 13 | 8 | 2 | không bao hàm |
| C3.3 vs C4.3 | 4 | 8 | 2 | không bao hàm |
| C4.1 vs C4.3 | 5 | 8 | 4 | không bao hàm |

### Phát hiện mới — hai bao hàm chỉ đúng ở PILOT_004/2025, sai ở 006

`C1.2 ⊆ C4.1` tại 004/2025: 4 mã (`MC50`, `PALLET-06`, `PP-BAND`, `TAPE50`) có tờ khai nhập
nhưng không nằm trong M15, và cả 4 cũng nằm trong Norm (M16) nên bị C4.1 gắn cờ song song. Tại
006/2024: C1.2=3, C4.1=17, giao=0. Tại 006/2025: C1.2=12, C4.1=14, giao=0. Bao hàm **không giữ**
ở quần thể lớn hơn.

`C3.3 ⊆ C1.1` tại 004/2025: 4 mã (`6067385-08B`, `6067385-09B`, `INKSTSGA1-BK`,
`INKSTSGA1-BL`) lệch đơn vị tính (C3.3) và cũng lệch số lượng (C1.1). Tại 006/2024: C3.3=67,
giao với C1.1 chỉ 1/67. Tại 006/2025: C3.3=31, giao với C1.1 = 0/31. Bao hàm **không giữ** ở
quần thể lớn hơn.

Cả hai chỉ xuất hiện ở kỳ có 40 mã bị gắn cờ (thấp hơn 006 hai bậc độ lớn) — trùng hợp cỡ mẫu,
không phải quy luật DN. Đây là ví dụ THỰC TẾ cho lý do phải tính động theo (DN, kỳ), không được
lưu một bảng bao hàm cố định dùng chung cho mọi DN.

### Cảnh báo `subject_key` trùng khác `subject_type`

Đếm số giá trị `subject_key` xuất hiện ở >1 `subject_type` trong cùng (DN, kỳ):

| DN/kỳ | (`item_code`,`material_code`) | (`material_code`,`product_code`) | Tổng mã trùng / tổng mã riêng biệt |
|---|---|---|---|
| PILOT_002/2025 | 1 | 0 | 1 / 47 |
| PILOT_006/2024 | 124 | **2** | 126 / 2.694 |
| PILOT_006/2025 | 442 | 0 | 442 / 7.105 |
| PILOT_004/2025 | 0 | 0 | 0 / 40 |

Trùng `item_code`↔`material_code` là **cố ý theo thiết kế**: `COMBO_HS_GAMING` (`combos.py:60-70`)
tự ghép C3.2 (`item_code`) với C3.3 (`material_code`) qua đúng `subject_key`, coi "mã trên tờ
khai" và "mã vật tư nội bộ" là MỘT danh tính nghiệp vụ. Đối chiếu dữ liệu gốc xác nhận: ở
006/2024, 6.312/7.882 mã NVL trong `nvl_balances` cũng xuất hiện trong `declaration_lines.item_code`
— khớp đúng ý nghĩa "DN khai đúng mã nội bộ trên tờ khai".

Trùng `material_code`↔`product_code` là **KHÔNG cố ý và LÀ THẬT**: ở 006/2024, `nvl_balances.
material_code ∩ sp_balances.product_code = 0` (0 mã, hai domain sạch ở tầng dữ liệu gốc) —
nhưng `norms.material_code ∩ sp_balances.product_code = 9` mã (vd `RV145MS00G0B-AMR07`,
`R0W0U150BU-0000003`…). Nguồn gốc: Mẫu 16 (BOM) nhiều cấp — một bán thành phẩm vừa là NVL đầu
vào ở công đoạn sau vừa là sản phẩm đầu ra ở công đoạn trước, cùng một mã. Hệ quả đo được: 2 mã
(`RV145MS00G0B-00002`, `RV145MS00G0B-AMR07`) xuất hiện đồng thời trong finding C1.4
(`subject_type=product_code`) VÀ finding C4.1/C4.3 (`subject_type=material_code`) tại 006/2024
— gộp theo `subject_key` một mình sẽ báo "mã X bị 3 kiểm tra" trong khi thực ra là 1 kiểm tra
nói về mã X ở VAI TRÒ đầu ra và 2 kiểm tra nói về mã X ở VAI TRÒ đầu vào.

### Xác minh `book` không phải rủi ro thêm (hiện tại)

Kiểm tra trực tiếp: trong cả 4 (DN, kỳ), không một cặp (check_code, subject_key) nào có finding
trải trên >1 `book`. `book` không cần vào khoá nhận diện hôm nay — xem câu hỏi mở #5.

## Phương án tính động + vị trí đặt

Không lưu bảng bao hàm tĩnh. Tính lại từ finding-set thật của đúng (company_id, period_year)
mỗi lần cần, theo 3 bước, đặt trong module mới **`app/checks/overlap.py`** (cùng tầng với
`combos.py`, `denominators.py`, `scoring.py` — các module hậu xử lý trên finding-set, không tạo
Finding mới của riêng bước 1-2):

```python
# app/checks/overlap.py
SubjectId = tuple[str | None, str]  # (subject_type, subject_key) — KHÔNG dùng subject_key một mình

def check_subject_sets(
    rows: Sequence[tuple[str, str | None, str]],  # (check_code, subject_type, subject_key)
) -> dict[str, set[SubjectId]]:
    """check_code -> tập SubjectId nó gắn cờ, trong PHẠM VI (company, year) của `rows`."""

def containment_map(check_sets: dict[str, set[SubjectId]]) -> dict[str, set[str]]:
    """check_code -> tập check_code khác mà nó LÀ TẬP CON, tính trên đúng finding-set đưa vào.
    Tập bằng nhau (vd C1.6=C1.7 khi cả hai chỉ có 1 mã chung): giữ mã nhỏ hơn theo alphabet làm
    canonical, mã còn lại coi là bị chứa — tránh loại cả hai chiều."""

def independent_signal_counts(
    rows: Sequence[tuple[str, str | None, str]],
) -> dict[SubjectId, tuple[int, int, list[str]]]:
    """SubjectId -> (số check thô, số tín hiệu độc lập sau khi trừ check bị hấp thụ, danh sách
    check bị hấp thụ). Gọi check_subject_sets + containment_map nội bộ."""
```

Quy tắc hấp thụ tại `independent_signal_counts`: với một `SubjectId` bị tập check `{c1..cn}`
gắn cờ, loại `ci` khỏi đếm nếu tồn tại `cj` khác (`cj` cũng nằm trong `{c1..cn}`) sao cho
`ci ∈ containment_map[cj]`-nghịch (tức `ci` là tập con của `cj` trên TOÀN quần thể (DN, kỳ),
không chỉ tại `SubjectId` này). Số còn lại sau khi loại = số tín hiệu độc lập.

Nơi gọi: `app/routes/companies.py::company_detail` (route hiện có ở dòng 1636), ngay sau khối
đếm SQL hiện tại (dòng 1697-1731). Truy vấn MỘT lần, CHỈ 3 cột:

```python
rows = db.execute(
    select(Finding.check_code, Finding.subject_type, Finding.subject_key)
    .where(
        Finding.company_id == company.id,
        Finding.period_year == selected_year,
        ~Finding.check_code.startswith("COMBO_"),
        Finding.subject_key.is_not(None),
    )
).all()
signal_counts = independent_signal_counts(rows)
```

Tính trên TOÀN pháp nhân, không lọc theo `?book=` — cùng quy ước đã có ở `book_splits` (dòng
1735, chú thích "Tính trên TOÀN pháp nhân (không theo lọc)"). Không `SELECT` `title`/`details`/
`evidence_refs` (JSON nặng) — đúng lý do route hiện tại đang tránh nạp cả object `Finding` khi
DN có 11.003 finding cho một kỳ (dòng 1695-1697, "render hết ra một trang là 18,7 MB HTML").

## Chi phí + vô hiệu hoá cache

Đo trực tiếp bằng `.venv/bin/python`, một lần chạy, trên kỳ nặng nhất (PILOT_006/2025, 10.996
dòng finding, 7.547 `SubjectId` riêng biệt, 11 check có finding):

| Bước | Thời gian |
|---|---|
| Truy vấn SQL 3 cột | 41 ms |
| Gom nhóm theo check (Python dict) | 34 ms |
| Dò bao hàm từng cặp (C(11,2)=55 cặp trong số check thật sự có finding) | 1 ms |
| Vòng hấp thụ (7.547 subject) | 20 ms |
| **Tổng** | **~120 ms** |

PILOT_006/2024 (3.852 dòng): ~71 ms. PILOT_004/2025 và PILOT_002/2025 (≤74 dòng): dưới 10 ms.

Kết luận chi phí: **không cần bảng cache mới, không cần cột mới.** 120ms ở khối lượng lớn nhất
hiện có là chấp nhận được cho một lần tính mỗi request `company_detail`, cùng bậc với các
truy vấn SQL khác route này đã chạy. Vì tính lại trực tiếp từ `findings` mỗi lần, **không tồn
tại vấn đề vô hiệu hoá cache** — không có gì để làm "cũ": `run_checks()` (`app/pipeline/
run_checks.py:78-104`) xoá-rồi-chèn lại đúng các `check_code` vừa chạy trong MỘT transaction,
và xoá vô điều kiện mọi `COMBO_*` mỗi lần chạy (dòng 98-104) — request tiếp theo tự động đọc
finding-set mới, không có khái niệm "lần chạy trước" cần dọn.

Ngưỡng cân nhắc chuyển sang tính-một-lần-rồi-lưu: nếu một (DN, kỳ) vượt khoảng **10× khối lượng
hiện tại (~100.000 finding)**, chi phí ước tính vượt 1 giây mỗi request — khi đó nên chuyển việc
gọi `independent_signal_counts` vào TRONG `run_checks()`, ngay sau đoạn tính combo (`run_checks.
py:138-149`, nơi ĐÃ nạp `all_year_findings` vào bộ nhớ vô điều kiện cho mục đích tính điểm) và
lưu kết quả gắn với đúng `data_version`/`ran_at` đã ghi vào `check_runs` (`app/models/
check_run.py`) — không cần kênh vô hiệu hoá mới, đi theo đúng kênh combo/score đang dùng
(recompute toàn bộ mỗi lần `run_checks()` chạy, không có đường sửa `findings` nào khác trong
codebase theo quy ước hiện tại).

## Câu chữ đề xuất cho giao diện

Không dùng "N kiểm tra cùng gắn cờ mã này" khi N là số thô (`raw_count`). Thay bằng số đã trừ
hấp thụ (`reduced_count`), với từ "độc lập" bắt buộc đi kèm để không lặp lại cách đọc sai:

- Tiêu đề: **"{reduced_count} tín hiệu độc lập gắn cờ mã {subject_key}"** thay vì "{raw_count}
  kiểm tra cùng gắn cờ".
- Khi `reduced_count < raw_count`, thêm một dòng phụ liệt kê phần bị hấp thụ, dựng động từ
  `containment_map` (không viết câu giải thích cố định cho từng cặp mã check — chỉ nêu sự kiện
  bao hàm của ĐÚNG kỳ đang xem):
  **"({dropped_check} là tập con của {containing_check} tại kỳ này — không tính thêm)"**.
  Ví dụ cụ thể đo được: "C1.1, C1.3, C1.6, C1.7 cùng có finding tại mã 12432-YDK0110-02A0 → 3
  tín hiệu độc lập (C1.1, C1.6, C4.3); C1.3 là tập con của C1.1, C1.7 là tập con của C1.6 tại
  PILOT_006/2025".
- KHÔNG ẩn dòng finding chi tiết của check bị hấp thụ khỏi danh sách — chỉ đổi số ở tiêu đề.
  Lý do: C1.7 (mang mức % tỷ lệ) và C1.6 (luôn CRITICAL, không mang %) không truyền đạt cùng
  một thông tin dù bao hàm đúng ở cấp quần thể; xem câu hỏi mở #1.

## Câu hỏi còn mở

1. Ẩn hẳn dòng finding bị hấp thụ khỏi danh sách chi tiết, hay chỉ đổi số đếm ở tiêu đề còn
   dòng chi tiết giữ nguyên? Khuyến nghị giữ nguyên dòng chi tiết (khác severity/ý nghĩa giữa
   C1.6 và C1.7) — cần nghiệp vụ xác nhận, không phải quyết định kỹ thuật.
2. Điều kiện A42 của `C1.7 ⊆ C1.6` chưa từng thực sự chặn một mã nào trong dữ liệu đo được (0
   near-miss ở mọi kỳ, kể cả kỳ có 652 mã A42). Cơ chế "tính động" xử lý đúng trường hợp KHÁC
   biệt chưa được kiểm chứng bằng dữ liệu thật — cần một (DN, kỳ) có A42 phủ trúng các mã tỷ lệ
   chuyển MĐSD cao để xác nhận `containment_map` trả về ĐÚNG "C1.7 KHÔNG ⊆ C1.6" ở kỳ đó.
3. `C5.1 ⊆ C4.1` (nhánh zero_source) chỉ suy được từ đọc code — C5.1 chưa từng có finding trên
   dữ liệu hiện có nên không đo được. Cần dữ liệu DN khác mới xác nhận hoặc bác bỏ.
4. Hai bao hàm chỉ đúng ở PILOT_004/2025 (mẫu n=4-5) đặt câu hỏi: thuật toán tính-động có nên
   thêm một ngưỡng cỡ mẫu tối thiểu (vd chỉ công nhận bao hàm khi `|A| ≥ 10`) để tránh một
   trùng hợp nhỏ làm biến mất hẳn một tín hiệu ở một DN nhỏ, hay cứ để đúng-là-đúng theo đúng
   dữ liệu của kỳ đó (cách tài liệu này đang làm)? Đây là quyết định sản phẩm, không phải kỹ
   thuật.
5. `book` chưa vào khoá nhận diện — an toàn trên dữ liệu đo được nhưng KHÔNG được kiểm chứng
   cho `COMBO_UNDECLARED_SOURCE` (C1.3+C5.1, `combos.py:41-49`, khoá theo `subject_key` một
   mình, không xét `book`) vì C5.1 chưa từng fire. Nếu tương lai một DN nhiều sổ (như
   PILOT_004) có C5.1 nổ, cần kiểm lại xem cùng một `material_code` ở hai sổ khác nhau có bị
   combo này ghép sai thành một sự kiện hay không.
6. `item_code` và `material_code` được `combos.py` coi là MỘT danh tính nghiệp vụ (cố ý), nhưng
   `Finding.subject_type` lưu chúng thành hai giá trị khác nhau — có nên chính thức hoá bằng
   cách đổi `subject_type` của C3.1/C3.2 thành `material_code` khi mã đó xác nhận trùng một mã
   NVL/TP nội bộ, để không phải duy trì song song hai khái niệm ("subject_type lưu trên dòng"
   và "domain thực tế theo nghiệp vụ")?
