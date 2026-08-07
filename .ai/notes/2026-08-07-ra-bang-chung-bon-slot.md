# Rà bằng chứng bốn slot — kết quả đo (việc 1 của #110)

Đo bằng đọc code ngày 2026-08-07. Không chạy trên dữ liệu, chỉ đối chiếu trường adapter ĐỌC/GHI
với trường có mặt trong dict `evidence`.

## Bảng chênh lệch

| slot | đường | trường adapter đọc & ghi | có bằng chứng | chênh lệch |
|---|---|---|---|---|
| m15 | chuẩn (`_COL`) | 11 | 8 (`_EVIDENCE_FIELDS`) | `row_no` · `material_name` · `unit` |
| m15 | mở rộng | mã + tên + đvt + 7 số | 8 | `material_name` · `unit` |
| m15a | chuẩn (`_COL`) | 10 | 7 (`_EVIDENCE_FIELDS`) | `row_no` · `product_name` · `unit` |
| m15a | mở rộng | mã + tên + đvt + 6 số | 7 | `product_name` · `unit` |
| m16 | TT39 (`_M16_TT39_COLS`) | 8 | **2** | `product_code` · `product_name` · `product_unit` · `material_name` · `material_unit` · `note` |
| m16 | DINHMUC (`_M16_DINHMUC_COLS`) | 6 | **2** | `product_code` · `product_name` · `material_name` · `material_unit` |
| bcct | theo nhãn | N cột dò được | **N — đủ 100%** | không |

## Cơ chế: chiều suy ngược nhau giữa bcct và ba slot còn lại

Đây là phát hiện cấu trúc, không phải ba lỗi rời rạc.

**bcct** (`bcct.py:276`) suy bằng chứng TỪ map cột:

```python
evidence = {f: (HEADER_MATCHED if f in by_label else POSITION_ONLY) for f in col}
```

Cột nào dò ra thì cột đó có bằng chứng. Phủ đủ **do cách viết**, không do ai nhớ liệt kê.

**m15 · m15a · m16** đi ngược: `evidence` là danh sách viết tay, rồi map cột suy TỪ nó.
`m16.py:192`:

```python
column_map = {f: cols[f] for f in evidence if f in cols}
```

m15/m15a cùng dạng qua hằng `_EVIDENCE_FIELDS` (`m15.py:226`, `m15a.py:221`).

## Vì sao chiều đó kéo theo mục 2 của #110

Dây chuyền là cứng, không phải trùng hợp:

`evidence` → `column_map` → `parse_detail["column_map"]` → `companies.py:1649` `base_map` →
vòng lặp `for field, default_cols in base_groups.items()` dựng ô nhập của biểu mẫu xác nhận.

Nên **trường không có bằng chứng thì không vào map, không có ô nhập, cán bộ không sửa được**.
Việc 2 của #110 ("cán bộ phải gán được trường ↔ cột") không phải yêu cầu giao diện rời — nó là
hệ quả trực tiếp của chiều suy này.

## Cổng review chỉ bắn cho trường có check đọc

`registry.py:522` `review_state`: `if not is_consumed(slot, field): return VERIFIED`.

Trong 15 trường chênh lệch ở bảng trên, **đúng một trường** được `CHECK_COLUMNS` khai:
`("m16", "product_code", INDIVIDUAL)` của C4.9. Các trường còn lại (`row_no`, các `*_name`,
các `*_unit`, `note`) **không check nào đọc** → có gắn bằng chứng cũng không làm cổng bắn thêm.

Tức lấp trọn chênh lệch KHÔNG làm mọi file đổi sang "Cần xác nhận". Chỉ m16 `product_code` đổi
trạng thái cổng — đúng vé #109.

## "Trường bắt buộc mỗi biểu" — có một phần, ở đúng một slot

Ghi chú gốc viết khái niệm này "hiện không tồn tại". Chính xác hơn: **bcct có**
(`bcct.py:139` `_REQUIRED_FIELDS = ("declaration_no", "item_code", "quantity")`,
kiểm ở `:266`), ba slot còn lại không có.

Và bcct dùng nó làm **lỗi phân tích cứng** (thiếu → không dựng được dòng nào), không phải
cảnh báo ở màn gán cột như việc 3 của #110 mô tả. Nên câu hỏi thiết kế không phải "dựng khái
niệm từ số không" mà là: đặt nó ở đâu cho cả bốn slot, và **chặn hay cảnh báo**.

## Ghi chú vòng tránh — tìm thấy đúng một

`grep` cả `app/`: chỉ `registry.py:471` (đúng chỗ #109 đã nêu). Không có ghi chú vòng tránh
nào khác cùng dạng.
