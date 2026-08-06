# Hiệu năng đường đọc — màn phát hiện + màn chi tiết pháp nhân

> Đo read-only trên `audit_hq.sqlite` thật (337 MB), `sqlite3.connect(..., mode=ro)`, Python
> `.venv/bin/python`, SQLite 3.45.1. Không sửa file sản phẩm, không ghi vào DB thật. Toàn bộ so
> sánh "trước/sau index" chạy trên bảng tổng hợp trong bộ nhớ (`:memory:`), dựng lại đúng cấu
> trúc cột + phân bố dữ liệu quan sát được, để không phải ghi vào DB thật.

## 1. Khối lượng dữ liệu đo

`findings`: 14.998 dòng, 3 pháp nhân (`companies.id` = 7 PILOT_002, 8 PILOT_006, 9 PILOT_004).

| company_id | period_year | số finding |
|---|---|---|
| 8 (PILOT_006) | 2025 | **10.996** |
| 8 (PILOT_006) | 2024 | 3.880 |
| 9 (PILOT_004) | 2025 | 74 |
| 7 (PILOT_002) | 2025 | 48 |

Cặp nặng nhất — **company_id=8, period_year=2025, 10.996 dòng** — dùng làm điểm đo cho toàn bộ
phần dưới. Phân bố theo check trong cặp này: C1.6=5.785, C1.7=2.436, C4.3=1.772, C3.2=776,
C1.1=97, C1.3=43, C3.3=31, C1.4=21, C4.1=14, C1.2=12, C3.1=9 — khớp tỉ lệ 91% ở 3 check ghi
trong đề bài.

## 2. Index hiện có trên `findings` và các bảng liên quan

```
findings:               ix_finding_company_year_code (company_id, period_year, check_code)  -- composite duy nhất
                         ix_findings_check_code (check_code)
                         ix_findings_company_id (company_id)
                         ix_findings_period_year (period_year)
                         ix_findings_severity (severity)
                         ix_findings_status (status)
                         ix_findings_subject_key (subject_key)
check_overviews:         company_id, period_year (đơn cột)
check_runs:               company_id, period_year (đơn cột)
company_year_scores:      company_id, period_year (đơn cột) + unique(company_id, period_year)
company_periods:          company_id, period_year (đơn cột) + unique(company_id, period_year)
nvl_balances:              company_id, period_year, material_code (đơn cột) + composite (company_id, period_year, material_code)
sp_balances:                company_id, period_year, product_code (đơn cột) + composite (company_id, period_year, product_code)
norms:                      company_id, period_year, product_code, material_code (đơn cột) + composite (company_id, period_year, product_code, material_code)
declaration_lines:          company_id, period_year, item_code, declaration_no, declaration_date,
                             customs_code, hs_code (đơn cột) + 2 composite (…, item_code) và (…, customs_code)
```

Không có lệch schema giữa model Python và DB thật — mọi `index=True` khai trong model đều có
mặt trên đĩa (kiểm bằng `sqlite_master`, không phải `PRAGMA index_list` lồng cursor — lần đầu
dùng chung một cursor cho vòng lặp ngoài và trong khiến kết quả sai, chỉ ra 1 index/bảng; đã
sửa bằng cursor riêng và đối chiếu lại).

`findings` **không có index nào phủ `(company_id, period_year, check_code, severity, subject_key)`**
— mọi truy vấn sắp theo `severity, subject_key` sau khi lọc theo `check_code` đều phải sort
riêng (`TEMP B-TREE FOR ORDER BY` / `FOR GROUP BY`).

## 3. Đường đọc `company_detail` — mọi câu query mỗi lần render

`app/routes/companies.py:1636-1897`, hàm `company_detail`, tham chiếu chéo `app/books.py`.

| # | Việc | Vị trí | Luôn chạy? |
|---|---|---|---|
| 1 | `SELECT DISTINCT period_year FROM findings WHERE company_id=?` | companies.py:1652-1656 | luôn |
| 2 | 4 query `SELECT DISTINCT period_year FROM {nvl_balances,sp_balances,norms,declaration_lines} WHERE company_id=?` | companies.py:1658-1664 | luôn |
| 3 | `load_period_windows` | companies.py:1667 | luôn |
| 4 | `book_summary()` → gọi `company_books()` (3 query DISTINCT book trên norms/nvl/sp) | companies.py:1671, app/books.py:51-69, 105-128 | **luôn, kể cả pháp nhân một sổ** |
| 5 | `company_books()` lần 2 nếu `multi_book` | companies.py:1673 | chỉ khi multi_book |
| 6 | `GROUP BY check_code, severity` đếm tổng | companies.py:1704-1717 | luôn (có năm) |
| 7 | `combo_findings` — không LIMIT | companies.py:1720-1729 | chỉ khi combos_on |
| 8 | `book_splits` — `GROUP BY check_code, book` | companies.py:1738-1746 | chỉ khi multi_book |
| 9 | `_rows(ccode, …)` — **1 query/check_code hiển thị** | companies.py:1763-1789 | luôn, N lần (N = số check có finding) |
| 10 | `year_score` lookup | companies.py:1805-1810 | luôn (có năm) |
| 11 | `get_all_specs` (built-in + published dynamic) | companies.py:1812, checks/registry.py:324-341 | luôn |
| 12 | `load_overviews_with_staleness` (2-3 query gộp, không N+1) | companies.py:1848-1852, ai/overview.py:448-489 | luôn |

**Không có N+1 theo dòng finding.** Template `company_detail.html` chỉ lặp trên `findings` đã
paginate (`_PREVIEW_PER_GROUP=15` hoặc `_PAGE_SIZE=100`), không có quan hệ ORM lazy nào trên
`Finding` (model không khai `relationship()` tới `Company`/`CheckDefinition` — chỉ cột FK thô),
`st = ov.aggregate_json` ở template dòng 323 đọc JSON đã tính sẵn lúc sinh overview, không tính
lại mỗi lần render. Đây là điểm thiết kế đúng, không cần sửa.

**N+1 thật sự nằm ở việc #4 và #9** — không phải theo dòng finding, mà theo lần gọi hàm phụ trợ
chạy vô điều kiện hoặc theo số check_code hiển thị. Mục 4 dưới đây đo cụ thể.

`finding_detail` (companies.py:2364-2403) và `export_recommendations` /
`build_export` (companies.py:1938-1960, `app/pipeline/export.py:174-257`) đều dùng
query gộp (`IN (...)`), không N+1 theo dòng — export nạp toàn bộ `findings` của
(company, year) vào bộ nhớ một lần (đúng bản chất xuất Excel, không phải N+1).
`combo_findings` (việc #7) không giới hạn số dòng — hiện tại 0 dòng ở cặp nặng nhất nên
không đo được chi phí thật, nhưng cấu trúc không có trần.

## 4. Đo thời gian + query plan — company_id=8, period_year=2025 (10.996 dòng)

Mỗi query chạy 5 lần liên tiếp (ấm cache OS sau lần đầu); số cold (chạm đĩa lần đầu) ghi riêng.

### 4.1. Ba câu chậm nhất khi render trang mặc định

**#1 — `company_books()` quét `norms` tìm book khác NULL, chạy VÔ ĐIỀU KIỆN mỗi lần render**
(companies.py:1671 → app/books.py:57-68, bảng `norms`):
```sql
SELECT DISTINCT book FROM norms WHERE company_id=8 AND period_year=2025 AND book IS NOT NULL
```
Plan: `SEARCH norms USING INDEX ix_norm_company_year_pair (company_id=? AND period_year=?)` +
`USE TEMP B-TREE FOR DISTINCT`. Quét toàn bộ **113.561 dòng** norms của (company 8, 2025) —
đây là pháp nhân MỘT sổ, kết quả luôn rỗng.
Thời gian: cold lần đầu **4.288 ms**; ấm 5 lần: 160,7 / 120,8 / 125,7 / 98,4 ms (min 98,38 ms).

**#2 — `_data_years` quét `declaration_lines` (companies.py:1658-1664)**:
```sql
SELECT DISTINCT period_year FROM declaration_lines WHERE company_id=8
```
Plan: `SEARCH declaration_lines USING COVERING INDEX ix_decl_customs (company_id=?)`, không có
temp b-tree (dữ liệu đã sắp theo period_year trong index nên dedup được khi stream) nhưng vẫn
phải đi qua **374.607 dòng** của công ty 8. Cold lần đầu **507,5 ms**; ấm 5 lần: 46,8 / 45,6 /
43,5 / 45,9 ms (min 43,5 ms).

**#3 — `_data_years` quét `norms` cho period_year (companies.py:1658-1664)**: cùng dạng, quét
**184.931 dòng** norms của công ty 8 (2 năm gộp). Cold lần đầu **1.982 ms**; ấm 5 lần: 45,2 /
31,9 / 32,6 / 25,5 ms (min 25,5 ms).

Ba câu này cộng lại (ấm) ≈ **167-232 ms**, tức **47-70%** tổng thời gian query đo được cho một
lần render trang mặc định (tổng 22 câu, đo lặp lại 3 lần: 210,6 / 215,7 / 226,7 ms). Cả ba đều
KHÔNG liên quan trực tiếp đến `findings` — chúng đọc bảng Tầng 1 (norms, declaration_lines) để
trả lời hai câu hỏi nhỏ ("pháp nhân này có mấy sổ" và "pháp nhân này có dữ liệu năm nào") mà DB
đã có sẵn câu trả lời rẻ hơn nhiều lần (mục 5.2).

### 4.2. Các câu còn lại (đã tối ưu bằng SQL, không phải điểm nóng)

- `GROUP BY check_code, severity` đếm tổng (companies.py:1704-1717): plan
  `SEARCH … USING INDEX ix_finding_company_year_code (company_id=? AND period_year=?)` +
  `USE TEMP B-TREE FOR GROUP BY`. 5 lần: 23,8 / 21,3 / 22,7 / 29,9 / 19,9 ms (min 19,9 ms).
- `_rows()` cho C1.6 (5.785 dòng), preview 15 dòng đầu (companies.py:1763-1775): plan
  `SEARCH … USING INDEX ix_finding_company_year_code (company_id=? AND period_year=? AND
  check_code=?)` + `USE TEMP B-TREE FOR ORDER BY`. 5 lần: 3,1 / 13,0 / 3,3 / 3,1 / 15,1 ms (min
  3,1 ms).
- `_rows()` cho C1.6, trang sâu (`LIMIT 100 OFFSET 5000`): CÙNG plan, vì SQLite phải sort xong
  toàn bộ 5.785 dòng khớp điều kiện vào temp b-tree trước khi bỏ qua 5.000 dòng đầu. 5 lần: 35,3
  / 38,2 / 19,8 / 33,3 / 21,2 ms (min 19,8 ms) — cao hơn preview vì phải duyệt xa hơn trong temp
  b-tree đã sort, dù kết quả chỉ trả 100 dòng.
- Vòng lặp 11 query `_rows()` — mỗi check_code hiển thị 1 query (companies.py:1784-1789, không
  focus): tổng 11 query cho company 8/2025 = **18,1 ms**. Đây là N+1 theo số check, không theo
  số dòng finding — hiện chưa phải điểm nóng nhưng sẽ tuyến tính theo số check hiển thị.
- `combo_findings` (companies.py:1720-1729): 0 dòng khớp ở cặp này, 5 lần: 4,8 / 2,5 / 7,6 / 2,1
  / 2,0 ms.
- `year_score` lookup (companies.py:1805-1810): index unique, ấm gần 0 ms (0,009-0,037 ms sau
  lần đầu 7,1 ms cold).

## 5. Index thiếu — chính xác câu lệnh, phục vụ query nào, tốn gì lúc ghi

### 5.1. `findings` — composite phủ `severity, subject_key`

```sql
CREATE INDEX ix_finding_company_year_code_sev_subject
    ON findings (company_id, period_year, check_code, severity, subject_key);
```

Phục vụ: mục 4.2 dòng 1 (đếm `GROUP BY check_code, severity`, companies.py:1704-1717) và mọi
lời gọi `_rows()` (companies.py:1763-1775, 1784-1789). Đối chiếu synthetic (bảng dựng lại đúng
phân bố company 8/2025, 10.996 dòng, cùng cột):

- `GROUP BY check_code, severity`: trước — `SEARCH … (company_id=? AND period_year=?)` +
  `TEMP B-TREE FOR GROUP BY`, 10,4-30,9 ms (7 lần). Sau — `SEARCH … USING COVERING INDEX …
  (company_id=? AND period_year=?)`, KHÔNG còn temp b-tree, 2,0-12,0 ms.
- `_rows()` C1.6 preview 15: trước — `TEMP B-TREE FOR ORDER BY`, 1,5-5,2 ms (bảng nhỏ hơn trong
  bộ nhớ nên số tuyệt đối thấp hơn DB thật). Sau — `SEARCH … USING COVERING INDEX …`, KHÔNG còn
  temp b-tree, 0,02-0,07 ms — SQLite đọc index đã sắp sẵn theo `severity, subject_key` và dừng
  ngay khi đủ `LIMIT`, không phải sort hết tập khớp trước.

Lưu ý: trên bảng `findings` thật, `_rows()` chọn `SELECT *` (gồm `title`, `details`,
`evidence_refs`, `notes`…) — các cột này KHÔNG nằm trong index mới nên plan thật sẽ là
`SEARCH … USING INDEX` (không phải `COVERING INDEX`), vẫn cần tra `rowid` cho từng dòng trả về.
Lợi ích chính vẫn giữ nguyên: bỏ được bước sort toàn bộ tập khớp trước khi cắt `LIMIT/OFFSET`.

**Tốn lúc ghi**: `run_checks.py:78-104` xoá rồi chèn lại finding theo `(company_id, period_year,
check_code IN (...))` mỗi lần chạy lại check — với company 8/2025 là ~11.000 dòng mỗi lần.  Đo
synthetic bulk insert/delete 10.996 dòng, so 7 index (hiện tại) với 8 index (thêm composite
trên), 3 lần mỗi cấu hình:
- Insert: 7 index 195-284 ms; 8 index 195-231 ms — chênh lệch nằm trong nhiễu đo, không phải
  bước nhảy rõ rệt.
- Delete: 7 index 107-126 ms; 8 index 138-153 ms — chênh khoảng **+20-30 ms (~15-25%)** cho
  8 index so với 7.

Kết luận: thêm 1 index composite trên `findings` có tốn ghi đo được (~20-30 ms mỗi lần xoá lại
~11.000 dòng) nhưng không phải chi phí lớn so với lợi ích đọc (loại bỏ 2 điểm `TEMP B-TREE`
lặp lại mỗi lần render/click phân trang). Cần migration Alembic — không sửa an toàn ngay được
vì đụng schema `findings`, bảng đang chịu ghi thường xuyên nhất trong hệ thống.

### 5.2. Không phải index — 2 câu quét sai bảng, sửa ở tầng ứng dụng, AN TOÀN NGAY

Đối chiếu 3 pháp nhân thật: tập năm suy từ `SELECT DISTINCT period_year` gộp 4 bảng
(nvl_balances ∪ sp_balances ∪ norms ∪ declaration_lines) **khớp tuyệt đối** với tập năm đọc
thẳng từ `company_periods` (bảng đã có sẵn, 1 dòng/(company, year), tạo lúc ingest —
`app/pipeline/ingest.py` gọi `resolve_period_bounds` đảm bảo dòng này tồn tại mỗi lần ingest bất
kỳ slot nào):

```
company 7: 4-bảng=[2025]        company_periods=[2025]        khớp
company 8: 4-bảng=[2024, 2025]  company_periods=[2024, 2025]  khớp
company 9: 4-bảng=[2025]        company_periods=[2025]        khớp
```

`SELECT DISTINCT period_year FROM company_periods WHERE company_id=?` đo 5 lần: 0,26 / 0,04 /
0,01 / 0,007 / 0,006 ms (min 0,006 ms) — so với 25-507 ms (ấm-lạnh) khi quét `norms` hay
`declaration_lines`. `company_periods` đã có index sẵn trên `company_id` (đơn cột + unique
`(company_id, period_year)`) — **không cần index mới, chỉ cần đổi nguồn truy vấn**.

Với `company_books()`/`book_summary()` (app/books.py:51-69, 105-128), bài toán khác: câu hỏi
không phải "năm nào có dữ liệu" mà "sổ nào có dữ liệu", và cột `book` không có mặt trong bất kỳ
bảng tra cứu rẻ nào sẵn có. Ở đây cần index mới, dạng partial (SQLite hỗ trợ từ 3.8.0, bản đang
chạy 3.45.1):

```sql
CREATE INDEX ix_norms_company_year_book
    ON norms (company_id, period_year, book) WHERE book IS NOT NULL;
CREATE INDEX ix_nvl_balances_company_year_book
    ON nvl_balances (company_id, period_year, book) WHERE book IS NOT NULL;
CREATE INDEX ix_sp_balances_company_year_book
    ON sp_balances (company_id, period_year, book) WHERE book IS NOT NULL;
```

Đối chiếu synthetic (113.561 dòng norms, toàn bộ book NULL — đúng phân bố công ty 8): trước —
`SEARCH … USING INDEX ix_norm_company_year_pair (company_id=? AND period_year=?)` +
`TEMP B-TREE FOR DISTINCT`, 25,8-32,8 ms; sau — `SEARCH … USING COVERING INDEX … (company_id=?
AND period_year=? AND book>?)`, KHÔNG chạm bảng gốc, **0,002-0,03 ms**. Vì index partial chỉ
chứa dòng có `book IS NOT NULL`, với pháp nhân một sổ SQLite chứng minh tập rỗng ngay từ range
scan, không cần đọc dòng nào trong 113.561 dòng.

**Tốn lúc ghi**: đối chiếu toàn DB, chỉ company 9 (PILOT_004 — pháp nhân nhiều sổ, EPE/GC) có
`book` khác NULL: 880 dòng norms, 141 dòng nvl_balances, 45 dòng sp_balances. Index partial trên
chỉ chứa tối đa ~1.066 dòng CỘNG DỒN cho toàn hệ thống — công ty 002/006 (nơi có toàn bộ khối
lượng 10.996 và 3.880 dòng) không ghi dòng nào vào 3 index này, vì các bảng norms/nvl/sp của họ
đều có `book IS NULL`. Ba index này cũng KHÔNG đụng bảng `findings` — không liên quan đường xoá-
tạo-lại của `run_checks.py`. **Tốn ghi gần như bằng không.**

## 6. Danh sách sửa xếp theo lợi ích đo được

| # | File:dòng | Sửa | Hiệu quả đo được | Rủi ro | An toàn ngay? |
|---|---|---|---|---|---|
| 1 | `app/routes/companies.py:1671`, `app/books.py:57-68` | Thêm 3 index partial `WHERE book IS NOT NULL` trên norms/nvl_balances/sp_balances | Bỏ **98-160 ms ấm** (tới 4.288 ms lạnh) mỗi lần render `company_detail` cho pháp nhân một sổ — chiếm 47-70% tổng thời gian query đo được của trang | Thấp — partial index, cú pháp SQLite chuẩn, không đổi kết quả truy vấn | An toàn ngay (thêm index không đổi hành vi ứng dụng); cần migration Alembic |
| 2 | `app/routes/companies.py:1658-1664` | Đổi nguồn `data_years` từ union 4 bảng sang `SELECT DISTINCT period_year FROM company_periods WHERE company_id=?` | Bỏ **~70-92 ms ấm** (tới ~2.500 ms lạnh cộng dồn 2 bảng nặng nhất) — còn **~0,01 ms**; đã đối chiếu khớp tuyệt đối với 3 pháp nhân thật | Thấp-trung bình — phụ thuộc giả định "mọi ingest đều tạo dòng company_periods" (đã xác nhận qua `resolve_period_bounds`, chưa xác nhận với toàn bộ đường ingest lịch sử/khôi phục từ backup cũ) | An toàn ngay về schema (không cần index mới); nên chạy lại đối chiếu 3 pháp nhân sau khi đổi trước khi xoá code cũ |
| 3 | `app/models/finding.py` (migration mới) | Thêm `CREATE INDEX ix_finding_company_year_code_sev_subject ON findings (company_id, period_year, check_code, severity, subject_key)` | Bỏ `TEMP B-TREE FOR GROUP BY` (đếm tổng, **~20-30 ms → ~2-12 ms** theo đối chiếu synthetic) và `TEMP B-TREE FOR ORDER BY` (`_rows()`, đặc biệt trang sâu — 19,8-38,2 ms hiện tại) | Trung bình — tốn ghi đo được **+20-30 ms (~15-25%)** mỗi lần `run_checks` xoá-tạo-lại ~11.000 dòng finding (company 8/2025); không tốn với PILOT_004 (74 dòng) | CẦN migration — đụng bảng ghi nhiều nhất hệ thống |
| 4 | `app/routes/companies.py:1784-1789` | Không sửa — theo dõi | Vòng lặp 1 query/check_code hiện 18,1 ms cho 11 check (company 8/2025), không phải điểm nóng ở khối lượng hiện tại; sau khi sửa #3 chi phí mỗi query gần 0 | — | Không cần hành động bây giờ |
| 5 | `app/routes/companies.py:1720-1729` | Không sửa — theo dõi | `combo_findings` không có `LIMIT`; hiện 0 dòng ở cặp nặng nhất nên không đo được chi phí thật. Cấu trúc không có trần — cần đo lại nếu combo bắt đầu sinh nhiều dòng trên pháp nhân/kỳ khác | Chưa biết — chưa có số đo | Không sửa nếu chưa có số đo cho thấy cần |

**Thứ tự làm**: #1 và #2 trước (an toàn ngay, không migration, gộp lại bỏ được phần lớn — đo
được **167-232 ms ấm / tới ~6.700 ms lạnh** trong tổng ~210-227 ms mỗi lần render trang mặc
định của cặp nặng nhất). #3 sau, kèm migration, cân nhắc với chi phí ghi đã đo (~20-30 ms mỗi
lần chạy lại check trên company 8/2025) so với lợi ích đọc lặp lại mỗi lần xem/click phân trang.
#4, #5 chỉ ghi nhận, không có số đo đủ để xếp hạng chi phí-lợi ích lúc này.
