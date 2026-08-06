# Xử lý check động X.1

## Kết luận trước

Không thể trả lời câu hỏi gốc ("X.1 trùng C1.1 xử lý sao") bằng dữ liệu đọc được, vì
**check X.1 trong `audit_hq.sqlite` local KHÔNG phải bản X.1 mà STATUS.md 2026-07-27
mô tả đang `published` trên prod.** Hai bản khác nội dung hoàn toàn (chi tiết ở mục 2).
Ghi chú này trình bày đầy đủ cơ chế + đối chiếu C1.1 dựa trên dữ liệu thật đọc được, nêu
rõ chỗ không khớp với STATUS.md, và đưa khuyến nghị có điều kiện — cần xác nhận lại nội
dung X.1 trên prod trước khi hành động.

## 1. Cơ chế check động

**Model** (`app/models/check_definition.py`): `CheckDefinition`, bảng `check_definitions`.
Trường chính: `code` (unique, prefix `X.*` — "Extended", phân biệt built-in `C1.*`),
`kind` (`sql` | `python`), `sql_snippet`/`code_snippet`, `subject_table`/`subject_col` (để
tự dựng `evidence_refs`), `scope` (mẫu số rate-based: `nvl`/`tp`/`m16`), `status`
(`draft` → `published` → `disabled`, enum `CheckStatus`), `created_by`, `created_at`,
`updated_at`. `next_check_code()` cấp mã kế tiếp bằng cách lấy `MAX` mã `X.%` **trong
chính CSDL đó** rồi +1 — mã `X.1` không phải định danh toàn cục, mỗi CSDL (dev/local,
staging, prod) tự đánh số độc lập từ 1.

**Routes** (`app/routes/admin_checks.py`): `POST /{id}/publish` → set `status=PUBLISHED`;
`POST /{id}/disable` → `DISABLED`; `POST /{id}/draft` → revert `DRAFT`. Không có route
xoá — chỉ đổi `status`.

**Runner** (`app/checks/sql_runner.py`): `run_check()` chạy `kind='sql'` bằng
`SELECT` (deny-list từ khoá ghi, bắt buộc bind `:company_id` + `:period_year`,
`validate_sql_is_select_only`) hoặc `kind='python'` bằng `exec()` với `__builtins__`
hạn chế (không `__import__`/`open`/`exec`/`eval`) và connection bọc read-only. Mỗi dòng
kết quả → 1 `Finding` (`_rows_to_findings`). Chỉ `status=PUBLISHED` mới được nạp vào
pipeline (`run_checks.py:66`, lọc `CheckDefinition.status == CheckStatus.PUBLISHED`).

**Orphan-cleanup bị `only=` bỏ qua** (`app/pipeline/run_checks.py:86-95` và
`:226-236`): khi chạy **full** (`only=None`), pipeline xoá thêm hai thứ mà chạy scoped
không đụng tới —
- `Finding` có `check_code LIKE 'X.%'` không nằm trong `codes_to_run` hiện tại (check
  động đã gỡ publish nhưng finding cũ còn tồn đọng);
- `CheckRun` cùng điều kiện (dọn lịch sử chạy của check đã gỡ).

Khi gọi `run_checks(..., only={"C1.1", …, "C6.1"})` (17 mã built-in, đúng như prod đã
làm ngày 2026-07-27), nhánh này không chạy — finding `X.*` cũ (nếu có) và `check_runs`
`X.*` cũ đều giữ nguyên, không bị dọn cũng không bị tái tạo.

## 2. X.1 thật trong DB — và chỗ không khớp STATUS.md

Đọc read-only `audit_hq.sqlite` (file cục bộ, mtime 2026-07-28 11:42, sau mốc STATUS.md
2026-07-27 một ngày):

```
id=1  code=X.1  kind=sql  status=draft
title: "Tồn cuối kỳ NVL âm"
scope: nvl · subject_table: nvl_balances · subject_col: material_code
sql_snippet:
  SELECT 'critical' AS severity, material_code AS subject_key,
         'Tồn cuối kỳ âm: '||material_code AS title,
         'closing='||closing_qty AS detail
  FROM nvl_balances
  WHERE company_id=:company_id AND period_year=:period_year AND closing_qty < -0.01
created_by=1 · created_at=2026-06-13 15:16:48 · updated_at=2026-06-13 15:16:48 (chưa từng sửa)
```

Toàn bảng `check_definitions` chỉ có đúng 1 dòng — không có bản X.1 nào khác. Toàn bảng
`findings` không có dòng nào `check_code LIKE 'X.%'` cho bất kỳ (company, period) nào
trong 3 pháp nhân pilot (PILOT_002 id=7, PILOT_006 id=8, PILOT_004 id=9). Bảng
`check_runs` cũng 0 dòng `X.%`.

**Đối chiếu với STATUS.md 2026-07-27** ("X.1 đang `published` trên prod, bản
`cross_table_match` trùng nghiệp vụ với C1.1"):

| | X.1 trong local DB (đọc được) | X.1 theo STATUS.md (mô tả prod) |
|---|---|---|
| status | `draft` | `published` |
| Bảng dùng | chỉ `nvl_balances` (1 bảng) | mô tả là `cross_table_match` — ngụ ý đối chiếu 2 bảng, giống C1.1 |
| Logic | `closing_qty < -0.01` (tồn cuối âm) | trùng nghiệp vụ C1.1 (đối chiếu M15 nhập vs BCCT) |
| Finding hiện có | 0 | STATUS.md dòng 169 cũng ghi "X.* vẫn 0 finding" — khớp ở điểm này |

Nội dung SQL không khớp mô tả "trùng nghiệp vụ C1.1": lọc tồn kho âm trên một bảng
không phải là phép so khớp nhập-M15-với-BCCT trên hai bảng. Vì `next_check_code()` cấp
mã theo `MAX` cục bộ trong từng CSDL, mã `X.1` ở local và mã `X.1` trên prod **không bảo
đảm cùng một nội dung** — rất có thể đây là hai check khác nhau được tạo độc lập ở hai
môi trường, cùng nhận số thứ tự 1 vì mỗi nơi đều là check động đầu tiên được tạo tại đó.
Không loại trừ khả năng khác (ví dụ file local không phải bản mirror mới nhất của prod),
nhưng bằng chứng trong tay (nội dung SQL, `status=draft`, `updated_at=created_at`) không
khớp bản "cross_table_match" mà STATUS.md mô tả.

**Hệ quả:** phần so sánh C1.1 vs "X.1 trùng nghiệp vụ" ở mục 3 dựa trên **mô tả bằng lời
trong STATUS.md** (vì SQL thật của bản đó không đọc được từ CSDL local), không dựa trên
SQL text đã kiểm chứng. Cần đọc `check_definitions` trên CSDL prod thật để lấy `sql_snippet`
chính xác trước khi quyết định publish/unpublish/xoá.

## 3. So sánh C1.1 (built-in) với X.1 (theo mô tả STATUS.md)

`check_c1_1` (`app/checks/c1_quantity.py:163-239`):

- **Hai vế so sánh:** vế trái = `nvl_balances.import_qty` (Mẫu 15, cột nhập trong kỳ),
  gộp theo `(material_code, đơn vị đã chuẩn hoá)`, cộng dồn qua mọi `book`. Vế phải =
  tổng `declaration_lines.quantity` lọc `customs_code IN import_codes_for(company_type)`
  (BCCT — bộ mã nhập tuỳ loại hình DN), cùng gộp theo `(item_code, đơn vị)` khi mã có
  nhiều đơn vị.
- **Ngưỡng dung sai:** `_pct_diff` — bỏ qua nếu `|diff_pct| < 0.5` (floor làm tròn); mức
  severity (`warning`/`critical`) tra theo `severity_for("C1.1", abs(diff_pct))`, có cấu
  hình ngưỡng riêng (không hard-code trong hàm này).
- **subject_key:** `material_code`. `subject_type`: `"material_code"`. **`book`: KHÔNG
  set** (không truyền `book=` vào `Finding()`) — vế đối chiếu là luồng tờ khai toàn pháp
  nhân, không tách theo sổ (đúng chủ đích, không phải thiếu sót — cùng cách C1.2/C1.4/
  C3.1/C3.2 xử lý, theo STATUS.md dòng 199).
- **evidence_refs:** trỏ về cả `nvl_balances` (filter `material_code`) lẫn
  `declaration_lines` (filter `item_code` + `customs_code__in`).

X.1 theo mô tả STATUS.md ("cross_table_match trùng nghiệp vụ với C1.1"): nếu đúng như
mô tả, hai vế so sánh về bản chất là cùng cặp bảng (`nvl_balances` M15 vs
`declaration_lines` BCCT) cho cùng loại phát hiện (lệch nhập-khai). Điểm khác biệt cụ thể
về ngưỡng dung sai, cách gộp đơn vị, tập `customs_code` dùng lọc — **không xác định
được** vì không đọc được `sql_snippet` thật của bản đó (mục 2). Điểm duy nhất đã xác nhận
qua `sql_runner.py`: mọi check động (bất kể nội dung) đi qua `_rows_to_findings` — hàm
này **không có tham số `book`**, nên **mọi finding của mọi check X.\* luôn `book=NULL`**,
bất kể logic SQL bên trong ra sao (`sql_runner.py:204-228`, đúng punch-list 8 STATUS.md).
Đây không phải điểm khác biệt so với C1.1 (C1.1 cũng luôn để `book` trống) — punch-list 8
gắn nhãn X.1 là hiểu chưa chính xác nếu so với hành vi C1.1: cả hai đều `book=NULL`.

Vì không có `sql_snippet` thật của X.1-trên-prod, không thể "chứng minh bằng cách so
`subject_key` set trong DB" như yêu cầu — dữ liệu findings X.\* hiện là tập rỗng ở local
DB (mục 2), không có gì để so khớp.

## 4. Khuyến nghị

**Không thể chốt một phương án dứt khoát ở bước này** vì thiếu nội dung SQL thật của X.1
trên prod (mục 2 nêu rõ vì sao). Khuyến nghị theo điều kiện:

- Nếu đọc `sql_snippet` prod xác nhận đúng như mô tả (đối chiếu M15 vs BCCT trùng cặp
  bảng + tập `customs_code` với C1.1, chỉ khác cách viết SQL) → **unpublish** (chuyển
  `draft`), không xoá. Lý do: giữ lại làm ví dụ nội bộ cho tính năng check-động (không
  mất giá trị bán hàng — sản phẩm có thể trưng ví dụ khác không trùng nghiệp vụ built-in,
  như bản "tồn cuối kỳ âm" đang nằm sẵn ở local DB dạng `draft`) trong khi loại bỏ nguyên
  nhân buộc chạy scoped. Xoá hẳn thì mất luôn phần "vết soạn từ NL" (`nl_prompt`,
  `analysis`, `plan`, `self_review`) — có giá trị làm case study cho tính năng AI-soạn-
  check, nên giữ ở trạng thái `draft` thay vì xoá.
- Nếu sql_snippet KHÔNG trùng nghiệp vụ C1.1 (giống tình huống phát hiện ở local — một
  check hoàn toàn khác) → **giữ nguyên `published`**, sửa lại workaround: bỏ chạy scoped,
  chuyển sang chạy full bình thường cho cả 3 pháp nhân, chấp nhận X.1 chỉ sinh finding
  cho DN nào dữ liệu thật khớp điều kiện (đây là hành vi đúng của một check thật, không
  phải lệch nhất quán cần né).

Việc đầu tiên, không phụ thuộc điều kiện trên: **đọc `sql_snippet` thật trên CSDL prod**
trước khi làm bất cứ gì khác — mọi phân tích trong ghi chú này về "X.1 trùng C1.1" đang
dựa trên diễn giải bằng lời trong STATUS.md, chưa dựa trên SQL đã kiểm chứng.

## 5. Hệ quả từng phương án lên demo

Giả định X.1-trên-prod đúng như STATUS.md mô tả (trùng nghiệp vụ C1.1, hiện 0 finding vì
chưa từng chạy full kể từ khi publish):

- **Unpublish (chuyển draft):** Không cần re-run — check X.\* không nằm trong
  `dynamic_defs` (lọc `status==PUBLISHED`, `run_checks.py:66`) nên lần chạy full kế tiếp
  tự động bỏ qua X.1 VÀ tự dọn orphan (`Finding`/`CheckRun` `X.%` không nằm trong
  `codes_to_run`, nhánh `only is None` — mục 1). Nếu vẫn muốn dọn ngay không đợi lần
  chạy full tiếp theo (ví dụ database hiện có leftover finding X.1 nào đó chưa biết),
  cần một lần `run_checks(company, year, only=None)` cho từng DN. Trên màn hình: 004,
  002, 006 không đổi gì về finding hiện có (X.\* đang 0 finding ở cả 3 theo STATUS.md);
  thay đổi duy nhất là màn "Check động" (`/admin/checks`) không còn hiện X.1 ở tab đã
  publish. Từ đây có thể **chạy full bình thường** cho cả 3 DN mà không lo lệch — nguyên
  nhân buộc chạy scoped đã mất.
- **Xoá hẳn:** cùng hệ quả màn hình như unpublish, nhưng mất `nl_prompt`/`analysis`/
  `plan`/`self_review` — không khôi phục được. Không có route xoá sẵn trong
  `admin_checks.py` — phải thao tác DB trực tiếp (ngoài quy trình chuẩn của tính năng).
- **Giữ published, chạy full bình thường:** 004 sẽ xuất hiện finding X.1 mới (số lượng
  bằng đúng những gì C1.1 đã báo — nếu X.1 quả thực trùng nghiệp vụ, findings của nó là
  bản sao gần như 1-1 của C1.1 hiện có cho 004); 002/006 nhiều khả năng vẫn 0 finding X.1
  nếu dữ liệu hai DN đó không có lệch nhập-khai đáng kể — nhưng đây là **giả định**, phải
  kiểm bằng dry-run thật, không suy diễn. Cần re-run.
- **Reconcile (viết lại X.1 để không trùng C1.1):** cần re-run sau khi sửa `sql_snippet`
  qua UI publish lại; hệ quả trên 004/002/006 phụ thuộc nội dung mới, không đoán trước
  được.

**Nếu cần re-run** (áp dụng cho phương án "giữ published + chạy full" hoặc "reconcile"),
quy trình an toàn repo đã dùng thật ngày 2026-07-27 (STATUS.md dòng 176-180), không bịa
mới:

1. Backup WAL-safe bằng `sqlite3.Connection.backup()` (không `cp` file đơn lẻ — mất dữ
   liệu WAL, xem memory `sqlite-wal-copy-gotcha`) → file `*.bak-pre-x1-<timestamp>`,
   chạy `PRAGMA integrity_check` trên bản backup để xác nhận.
2. Dry-run trên **bản copy** của CSDL, trỏ `DATABASE_URL` vào file copy đó — không chạy
   thẳng lên CSDL đang phục vụ demo.
3. Diff finding cũ/mới (đếm theo check_code, theo company) — xác nhận đúng như dự đoán
   trước khi làm tiếp bước live (mẫu đối chiếu 74→65, 9 removed/0 added của lần 004
   recheck).
4. Chạy live, xoá bản copy dry-run (gồm cả `-wal`/`-shm`), backup ở bước 1 vẫn giữ lại để
   rollback nếu cần (`docker stop` → `cp` backup đè file chính → xoá `-wal`/`-shm` →
   `docker start`).

## 6. Việc cần làm trước khi chốt

Đọc `check_definitions` bảng thật trên CSDL prod (không phải file local đã đọc ở đây) để
lấy đúng `sql_snippet` của X.1 hiện `published`, rồi mới áp mục 4 vào đúng nhánh điều
kiện.
