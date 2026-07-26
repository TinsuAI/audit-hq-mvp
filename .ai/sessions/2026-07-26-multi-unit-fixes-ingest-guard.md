# 2026-07-26 — Audit 004 hai sổ → sửa lỗi trục đơn vị + chặn mất sổ khi ingest

Phiên bắt đầu bằng một cuộc rà soát READ-ONLY tính đúng đắn của mô hình hai sổ (EPE/GC) cho 004, rồi sửa luôn những gì tìm được. Hai PR đã merge, `main` = `dd763d4`.

**Báo cáo audit đầy đủ ở `.ai/sessions/2026-07-26-audit-004-hai-so.md`** — bảng phạm vi 17 check, định lượng phần tờ khai bị che, punch-list 9 mục, căn cứ pháp lý, đối chiếu 7 khẳng định bàn giao. File này KHÔNG lặp lại nội dung đó.

## What Was Done

**Audit (5 agent chạy song song, read-only).** Kết luận chính: trục `book` thiết kế và cài đặt ĐÚNG, không check nào sai phạm vi. Lỗi thật nằm ở trục **đơn vị tính**. Ba khẳng định của phiên trước bị bác bỏ một phần — xem mục 7 của báo cáo.

**PR #25 `fix/multi-unit-findings`** (merge `dd763d4`, 5 commit):
- `38efa0d` — C1.3/C1.6/C1.7 khử trùng theo `(book, material_code)`; C1.1/C1.4 so trong cùng đơn vị, chỉ áp cho mã nhiều đơn vị; C3.3 dùng TẬP đơn vị thay vì ghi đè dict.
- `fe9c887` — hai lỗi do `/rev` bắt: (1) vế tờ khai đã chuẩn hoá đơn vị còn vế sổ vẫn khoá theo chuỗi thô → `MTR` và `METRES` thành hai lát của cùng một đơn vị, mỗi lát so với cả tổng; (2) `sorted()` ném `TypeError` khi một mã có dòng đơn vị NULL lẫn dòng có đơn vị.
- `1635676` — trích `_one_row_per_material`, guard truy vấn tách-đơn-vị, C3.3 nêu đủ tập đơn vị.

Kết quả trên 004: **74 → 65 phát hiện**. C1.1 33→28, C1.3 15→13, C3.3 4→2. Ba CRITICAL sai (+99900% ×2, −98%) biến mất; hai phát hiện −100% thật vẫn còn, mỗi mã một lần.

**PR #26 `fix/ingest-book-safety`** (merge `bc9e887`, 1 commit `26beda6`): `_plan_settlement_files` ném `IngestPlanError` thay vì suy giảm im lặng — từ chối gộp sổ khi tag `data_files` đã bị prune (đối chiếu `_books_already_stored`, đọc sổ từ `nvl_balances`/`sp_balances`/`norms`), và từ chối chạy tiếp khi file settlement đã đăng ký bị thiếu/không đọc được. Chạy ở `:191`, TRƯỚC lệnh xoá ở `:196`.

**DB local (không nằm trong git).** Sửa drift alembic: đối chiếu từng revision trong 5 bản còn thiếu với schema thật — bốn bản đầu đã có sẵn do sửa tay trước đó, chỉ thiếu đúng `data_files.book`. Thêm cột + stamp `alembic_version` = `d0e1f2a3b4c5` (= head). Backup `audit_hq.sqlite.bak-pre-schema-fix-20260726` (`Connection.backup()`, `integrity_check: ok`, 607.745 dòng / 24 bảng không đổi).

## Decisions Made

- **C1.1/C1.4 khi một mã có nhiều đơn vị** (user chốt): mã một đơn vị giữ nguyên hành vi cũ; mã nhiều đơn vị chỉ so lát khớp đơn vị tờ khai; không lát nào khớp thì báo MỘT lần bằng lát lớn nhất. Chọn phương án này vì khử trùng đơn thuần KHÔNG sửa được ba CRITICAL sai (mỗi mã chỉ có một finding, không có gì để gộp).
- **KHÔNG gộp `check_c1_1` với `check_c1_4`** dù nhìn giống nhau: khác bảng, cột lượng, subject_type, mã check, floor (0,5% vs 0,1%), tiêu đề, hàm evidence — helper chung cần 7 tham số, khó đọc hơn hai hàm riêng. Chỉ trích phần trùng thật sự (C1.3/C1.6/C1.7).
- **Guard ingest đọc nguồn ĐỘC LẬP.** `_books_already_stored` đọc sổ từ bảng settlement chứ không từ `data_files` — vì chính `data_files` là thứ bị prune. Guard tin vào cùng bảng đã hỏng thì vô dụng.
- **Cột nhãn EPE/GC trong file NK thô = BẰNG CHỨNG AUDIT, không phải tính năng ingest.** Đối chiếu 33 file BCCT của 10 DN: đây là file duy nhất có cột thừa thật và là file duy nhất bị cắt khối mào đầu chuẩn của Hải quan → do người gõ tay, khách sau sẽ không có.
- **Tách PR.** Guard ingest ban đầu nằm chung nhánh với các fix check; đã tách sang nhánh riêng vì nó đụng đường wipe-and-reload và đáng được review riêng. `ee6057a` có kèm 4 dòng sửa báo cáo mà file đó không tồn tại trên `main` → chỉ bê hai file code sang nhánh mới, phần sửa báo cáo để lại ở PR #25.

## What Didn't Work

- **Khớp đơn vị kiểu ngây thơ** (chẻ tổng tờ khai theo đơn vị cho MỌI mã) sẽ âm thầm làm đổi kết quả C1.1/C1.4 của 002 và 006: sau chuẩn hoá, 002 có 4 mặt hàng nhiều đơn vị, 006 có 61 (2024) + 96 (2025), chưa kể mặt hàng có đơn vị không phân giải được. Phải giới hạn chỉ áp khi phía M15 có >1 đơn vị.
- **Khử trùng theo `material_code` KHÔNG sửa được C1.1** — với `6067385-08B/09B` và `NO 153-BLACK` mỗi mã chỉ có một finding.
- **Lập luận "test vừa chốt hành vi nên đừng refactor" (advisor) bị bác** — test chính là thứ khiến refactor an toàn. Refactor đã làm và kiểm chứng bằng delta trước/sau trên DB thật.
- **Không kiểm chứng được guard trên company 9 lúc đầu:** truy vấn `DataFile` chết trước vì `no such column: data_files.book` (chính là punch-list mục 3). Phải sửa drift xong mới chứng minh được.

## Open Items

- **Nhãn sổ vẫn chưa bền.** Guard chặn được hậu quả nhưng tag vẫn mất khi prune; sau đó phải sync + gán lại book cho từng file mới nạp được. Ứng viên: ngừng prune dòng có tag · khôi phục map file→sổ từ `nvl_balances.source_file` · chuyển map sang `company_periods`. **Cần ADR.**
- **Punch-list còn mở: 6, 7, 8, 9** (xem mục 5 báo cáo). Mục 6 đáng chú ý — bản vá union 99→4 mà ADR #19 sinh ra để giải quyết vẫn CHƯA có test.
- **ADR #19 cần ghi giới hạn kèm điều kiện:** che khuất tờ khai chỉ xảy ra "khi một pháp nhân hai sổ khai cả hai sổ dưới mã của cùng một loại hình", KHÔNG phải phổ quát.
- **Prod vẫn hiện ba CRITICAL sai.** Finding nằm trong DB tới khi chạy lại check; chạy lại riêng 004 là khả thi (check đọc bảng DB, chỉ ingest mới cần file nguồn) và ra 65. Chính sách hiện tại là CỐ Ý không re-run → cần user quyết.
- **CX.1 (check rò rỉ liên sổ):** mục catalog MỚI, phải vào `../audit-hq/de-an-audit-hq.md` trước theo `CLAUDE.md:38`. Thu hẹp về quy tắc dựa trên `customs_code` (không cần gán nhãn từng dòng).
- `uv.lock` vẫn untracked (có từ trước phiên này).
