# Punch-list 6 — test hồi quy cho ngữ nghĩa sổ (EPE/GC) + chặn gán sổ nửa vời

**Ngày:** 2026-07-27
**Nhánh:** `fix/book-tags-all-or-nothing` (3 commit, tách từ `main` tại `33c078f`) — **CHƯA push, CHƯA PR, CHƯA merge**
**Nguồn việc:** mục 6 punch-list trong `.ai/sessions/2026-07-26-audit-004-hai-so.md`
**Kết quả:** 730 test pass (mốc trước 721), ruff sạch

---

## What Was Done

### 1. Chín test mới, hai test cũ được siết

Mọi test đều kiểm bằng **mutation**: sửa hỏng đúng dòng code mà test bảo vệ, xác nhận test đỏ, rồi
hoàn nguyên. Bảng dưới ghi mutant đã dùng — phiên sau muốn kiểm lại thì lặp đúng mutant đó.

| Test | Mutant đã áp | Kết quả |
|---|---|---|
| `test_c1_2_treats_m15_of_every_book_as_declared` | thêm lọc sổ vào query `m15_codes` của C1.2 | bắn giả `GC_ONLY`; **chỉ test này bắt được** |
| `test_c1_1/c1_2/c1_4_finding_is_not_attributed_to_a_book` | thêm `book="EPE"` vào 3 constructor `Finding` | bắt cả ba |
| `test_c1_3_accepts_an_unlabelled_declaration_for_a_book_labelled_row` | thêm `or r.book` vào bộ lọc dòng chưa khai của C1.3 | sinh 2 finding thừa; bắt được |
| `test_c3_1_and_c3_2_are_not_attributed_to_a_book` | KHÔNG mutate — cả hai chỉ đọc `declaration_lines`, bảng không có cột `book` | — |
| `test_plan_refuses_when_a_registered_book_file_has_no_usable_sheet` | đổi nhánh `SheetNotFound` về `continue` im lặng | bắt được; xác nhận test đi đúng nhánh parse, không phải nhánh thiếu file |
| `test_books_are_restored_after_tags_are_pruned_and_registered_again` | KHÔNG mutate — test đường phục hồi, không có dòng đơn lẻ để mutate | — |
| `test_ingest_refuses_when_only_some_settlement_files_carry_a_book` | đỏ thật trước khi sửa code | đỏ → xanh |

**Hai test cũ được siết** (`test_c1_1_sums_rows_of_same_code_and_unit`, `test_c1_4_...`): trước đây hai
dòng đều `book=NULL` nên đổi khoá gộp từ `(mã, đơn vị)` sang `(sổ, mã, đơn vị)` KHÔNG làm test đỏ — đúng
điều audit chỉ ra. Nay gắn `EPE`/`GC` cho hai dòng, mutant đó làm đỏ 4 test.

### 2. Một thay đổi hành vi: gán sổ là tất-cả-hoặc-không

`app/pipeline/ingest.py:130-139` — `_plan_settlement_files` ném `IngestPlanError` kèm danh sách file khi
một số file settlement đã gán sổ còn số khác chưa. Đặt **sau** nhánh return sớm của trường hợp không file
nào có nhãn, nên đường CLI + pháp nhân một sổ (002/006) không đổi.

### 3. Sửa dòng hướng dẫn ở màn review

`app/templates/document_review.html:95` — text cũ ghi "Để trống = 1 sổ (dùng chung)", chỉ đúng khi MỌI file
settlement của kỳ đều để trống. Nay nêu rõ quy tắc tất-cả-hoặc-không.

---

## Decisions Made

### Chặn gán sổ nửa vời thay vì chỉ ghi nhận (mục 9 punch-list) — owner chốt

Ba lựa chọn đã đưa ra: (a) từ chối lượt nạp, (b) chỉ viết test ghi nhận hành vi hiện tại, (c) bỏ qua.
**Owner chọn (a).**

Lý do kỹ thuật: `book=NULL` ở pháp nhân nhiều sổ **đã mang nghĩa xác định** — "liên sổ", phát hiện không
quy được về sổ nào (ADR #19 Revision). Dòng của file chưa gán không được đánh dấu là "chưa biết"; chúng
rơi thẳng vào nhóm liên sổ. `C4.1`/`C4.3`/`C6.1` gom theo sổ bằng `defaultdict` nên `None` thành nhóm thứ
ba và bị đối chiếu như một sổ thật: định mức EPE chỉ thấy vật tư EPE, nhóm NULL có vật tư mà không định
mức nào; C6.1 khoá `(sổ, mã)` nên dòng EPE năm sau không khớp dòng NULL năm nay và bắn hàng loạt.

Cùng chính sách "thà hỏng ồn còn hơn suy giảm im lặng" đã chốt ở PR #26.

### Quy tắc chỉ áp cho slot settlement, KHÔNG áp cho BCCT

`SETTLEMENT_SLOTS = ("m15", "m15a", "m16")` (`app/models/data_file.py:47`). Query của
`_plan_settlement_files` lọc theo tập này nên file BCCT vô hình với quy tắc, dù DN nộp 1 hay 2 file.
Đúng thiết kế: `declaration_lines` **không có cột `book`**, tờ khai ghi một lần cho cả pháp nhân.

**Hệ quả cần nhớ:** chia BCCT thành hai file theo sổ cũng KHÔNG gán sổ được — `is_settlement` False nên
selector không render (`document_review.html:92`) và handler confirm không đọc trường `book`
(`companies.py:1197`). Hai file vẫn nạp đủ nhưng bị trộn thành một luồng
(`bcct_all = [r for b in bcct_files for r in b.rows]`, `ingest.py:198`).

### Guard phải có đường thoát, nên viết test cho đường phục hồi

`test_books_are_restored_after_tags_are_pruned_and_registered_again` bao đúng chuỗi: nạp 2 sổ → prune sạch
`data_files` → nạp lại (dừng, đã có test cũ) → đăng ký lại + gán sổ → nạp lại → hai sổ về nguyên trạng, 0
dòng `book=NULL`, tờ khai vẫn 2 dòng. Không có test này thì guard của PR #26 có thể là ngõ cụt mà không ai
biết.

### Test viết cho code đã ship thì phải chứng minh bằng mutation

Phần lớn punch-list 6 là test cho hành vi ĐÃ ship, nên viết xong là xanh ngay. Test chưa bao giờ đỏ không
chứng minh gì. Cách làm: với mỗi test, sửa hỏng đúng dòng nó bảo vệ rồi chạy lại. Bảng mutant ở trên là
bằng chứng, không phải mô tả.

---

## What Didn't Work

- **Không test được nhánh `SheetNotFound` qua `ingest()` đầu-cuối.** `discover` chọn ứng viên m15 theo tên
  file (`"nvl"`/`"npl"` trong tên, `discover.py:131`), nên file rác tên `NVL_GC.xlsx` có thể được `_pick_best`
  chọn và `parse_m15` ở `ingest.py:172` nổ `SheetNotFound` TRƯỚC khi kế hoạch chạy — test sẽ bắt nhầm
  exception. Chuyển sang test thẳng ở `_plan_settlement_files`, đúng chỗ quyết định từ chối. Thứ tự
  "plan trước, xoá sau" đã có test cũ (`test_reingest_refuses_when_a_registered_book_file_is_missing`) bao.
- **Mutant đầu tiên cho C1.2 phải chọn cẩn thận.** Lọc `book.is_not("GC")` mới tái hiện đúng lớp finding
  giả; các mutant yếu hơn (vd đổi thứ tự sort) không chứng minh được điều gì.
- Ruff E501 ở `test_c1_quantity.py` sau khi thêm test — đổi tên fixture `TRULY_MISSING` → `MISSING_BOTH`
  cho gọn dòng.

---

## Open Items

1. **Nhánh `fix/book-tags-all-or-nothing` đang treo** — 3 commit, chưa push/PR/merge/deploy. `main` vẫn ở
   `33c078f`, prod vẫn `dd763d4`. `CLAUDE.md:44` đặt `/rev` là cổng trước merge; thay đổi này có sửa hành vi
   ingest nên áp dụng.
2. **Punch-list 8 chưa đụng** — check động `X.*` luôn emit `book=NULL` (`sql_runner.py:217-227`), nên luôn
   hiện nhãn "Liên sổ" kể cả khi kết quả chỉ từ một sổ.
3. **Punch-list 7 chưa đụng** — GLOSSARY mục "Pháp nhân" (`.ai/GLOSSARY.md:91-94`) còn tả mô hình hai row đã
   bỏ; ADR #19 `:573-574` xếp nhầm C3.1/C3.2; ADR `:608` ghi "104 mã" trong khi DB có 98 mã phân biệt trên
   104 dòng.
4. **Nhãn sổ nên sống ở đâu cho bền — chưa trả lời (cần ADR).** Guard chặn được hậu quả nhưng tag vẫn mất khi
   `sync_data_files` prune. Ứng viên: ngừng prune dòng có tag · khôi phục map file→sổ từ
   `nvl_balances.source_file` · chuyển sang `company_periods`.
5. **Prod vẫn hiện 3 CRITICAL sai của 004** — deploy chỉ đổi code, finding cũ nằm trong DB tới khi chạy lại
   check. Chạy lại riêng 004/2025 khả thi (check đọc bảng DB, chỉ ingest mới cần file nguồn) và ra 65. Chính
   sách hiện tại CỐ Ý không re-run trên prod → **cần owner quyết**.
6. **Gán sổ cho tờ khai** — muốn làm thì phải thêm cột `book` vào `declaration_lines` và chuyển
   C1.1/C1.2/C1.3/C1.4 từ đối chiếu union sang theo sổ. Đo được ở audit: đang che 6 phát hiện C1.3 của EPE và
   1 của GC. Chưa có quyết định.
