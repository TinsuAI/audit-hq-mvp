# Session 2026-05-27/28 — Audit logic + display findings, vòng fix #1

Session bắt đầu khi user nghi ngờ có lỗi trong các bài kiểm tra sau khi thấy
1 finding năm 2024 hiển thị BCCT của cả 2023+2024. User yêu cầu audit toàn
diện effort cao, sau đó "fix hết". 6 commit deploy + DB tinsu cleaned + rerun.

Live: `audit-hq-demo.tinsu.ai` build `01db20d`.

## What Was Done

### Audit toàn diện 6 check rule modules + display layer + dynamic runner

Đọc kỹ `app/checks/c1_quantity.py`, `c2_balance.py`, `c3_classify.py`,
`c4_norm.py`, `c5_trace.py`, `c6_cross_period.py`, `combos.py`,
`dynamic_runner.py`, `scoring.py`, `denominators.py`, `company_type.py`,
`registry.py`. Đọc `_resolve_evidence` + `finding_detail.html`.

Truy DB live (2586 findings) xác thực giả thuyết bug. Bug ông thấy sáng đó
(C6.1 year=2024 evidence 2023+2024) thực ra KHÔNG phải bug — C6.1 là check
liên-kỳ, theo thiết kế phải show cả 2 năm. Display logic `_resolve_evidence`
filter `period_year==value` đúng. Toàn DB chỉ 1/2586 finding cross-year.

Quá trình tìm ra 7 bug khác, fix 6 cái (1 cái defer — Bug #6, dynamic check
fallback scope).

### 6 commit fix (b4d2737 → 01db20d)

#### `b4d2737` fix(adapters): normalize_code reject placeholder values
`app/adapters/_common.py` — thêm `_JUNK_CODES = {"", ".", "-", "n/a", "nan", …}`,
trả `None` cho mọi placeholder. Trước fix: dòng tổng/header tờ khai Excel
có `item_code="."` được pass-through → C3.2 fire "Mã '.' có 406 mã HS khác
chương" (gom toàn bộ HS DN vào 1 finding ảo). 23 finding rác ở DB.

Test mới `tests/test_normalize_code.py` (21 test parametrize).

#### `233da3f` fix(checks): xoá E13 khỏi IMPORT_CODES[DNCX]
`app/checks/company_type.py`. E13 = máy móc thiết bị miễn thuế (DNCX),
KHÔNG nằm trong M15 (M15 chỉ NVL). Trước fix C1.1/C1.2/C1.3/C1.7 coi E13
là NVL nhập → 93/333 (28%) findings C1.2 là máy móc bị flag "thiếu trong
M15" — CRITICAL noise.

Split:
- `IMPORT_CODES` (chỉ NVL) cho check rules + denominator scope.
- `_DETECT_IMPORT_CODES` (gồm E13) cho `detect_company_type` (giữ E13 là
  chỉ báo DNCX rõ ràng).
- Thêm public `MMTB_CODES = {"E13"}` cho check tương lai.

Test mới `test_c1_2_ignores_mmtb_E13_for_dncx`.

#### `b81e442` fix(checks): C1.1/C1.4 emit INFO band như description đã hứa
`app/checks/c1_quantity.py`. Trước fix: code skip `|diff|<5%` (C1.1) và
`<1%` (C1.4) → INFO band không bao giờ fire (0/544 và 0/611 ở DB demo).
Mâu thuẫn với registry description "<5% Thông tin".

Sau fix: `severity_for()` handle band lookup; thay floor 5%/1% bằng floor
0.5%/0.1% chỉ để lọc nhiễu làm tròn. Result: C1.1 ra 16 INFO + 17 WARN +
527 CRIT (đúng dải).

Tests update: rename `test_c1_1_no_fire_when_diff_under_5pct` →
`test_c1_1_fires_info_when_diff_under_5pct` + thêm `_under_floor` tests.

#### `c36a3e1` fix(checks): C1.7 — thống nhất denominator giữa code, registry, catalog
Trước fix có 3 phát biểu khác nhau:
- Code: `denom = opening_qty + import_qty` (gồm tồn đầu)
- `registry.py` description: "/ nhập_trong_kỳ" (chỉ nhập)
- Finding title: "chiếm X% tổng nhập" (gọi opening+import là "tổng nhập")

Sau fix: chọn formula của code (đúng nghiệp vụ — tỷ lệ chuyển MĐSD so với
nguồn khả dụng), sửa description trong `registry.py` + `catalog_full.py` +
title finding để dùng cùng wording "(tồn_đầu + nhập_trong_kỳ)".

#### `8c3f33c` fix(dynamic_runner): _eval_threshold AND semantics trong cùng band
Trước fix: nhiều op trong 1 band được OR. Spec `{gte: 5, lt: 20, severity:
warning}` sẽ MATCH với value=100 (vì gte:5 đủ true) → range band không
gate được. Chưa cháy ở DB demo vì chưa có dynamic check published.

Sau fix: refactor dùng `op_checks` dict + `all()` — trong 1 band, mọi op
phải đồng thời thoả; first-band-match wins giữ nguyên.

Test mới `test_range_band_and_semantics`.

#### `01db20d` fix(dynamic_runner): dynamic finding có evidence_refs và subject_type đúng
Trước fix:
- `_make_finding` default `evidence_refs=[]` → mọi dynamic finding hiện
  "(Không có tham chiếu chứng cứ)" → vi phạm §2.2 đề án ("mọi phát hiện
  phải truy nguồn về Tầng 1").
- `_make_finding` hardcode `subject_type="material_code"` bất kể `subject_col`
  của spec → link `/companies/{code}/items/{subject_key}` có thể trỏ sai.

Sau fix:
- `subject_type` lấy từ `subject_col` spec (presence_check dùng cột join
  của bên evidence trỏ về).
- Thêm helper `_evidence_ref(table, company_id, year, subject_col,
  subject_key, extra_filter)` build evidence ref point về (company, year,
  subject) trên bảng tương ứng.
- Thêm helper `_spec_filter_to_evidence` chuyển `{col__op: val}` thành
  filter `_resolve_evidence` hiểu (eq + `col__in`); op khác (gt/lt) bỏ.
- 5 runner đều populate `evidence_refs`:
  - `threshold_compare`, `aggregate_threshold`, `ratio_threshold`: 1 ref.
  - `presence_check`: 1 ref bên còn thiếu (theo `mode`).
  - `cross_table_match`: 2 ref (cả 2 bảng cùng subject).

Test mới `test_finding_has_evidence_and_subject_type`.

### Tinsu DB cleanup + rerun (2026-05-27 evening)

SSH `tinsu` (qua `ssh.exe -F` từ Windows config — WSL ssh broken),
`docker exec audit-hq-mvp`:

1. Backup: `~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite.bak-pre-audit-fix-20260527-232133` (26MB).
2. DELETE 6714 junk rows từ `declaration_lines` (item_code IN junk).
3. `run_checks(DN, year)` cho 11 (DN, year) pair → 3416 findings.

**Verify trên tinsu DB sau rerun:**
- Junk subject_key: **0** (was 23+).
- C1.2 E13-only false positive: **0/240** (was ~93/333 = 28%).
- C1.1 by severity: 16 INFO + 17 WARN + 527 CRIT (band INFO giờ fire đúng).
- C1.4: 611 CRIT (data demo M15a vs BCCT lệch tự nhiên 42-129%, không có
  near-match — INFO band 0 không phải bug).

## Decisions Made

### Bug C6.1 evidence năm trước+năm hiện không sửa
User thấy "C6.1 year=2024 evidence 2023+2024" và nghi bug. Audit DB
confirm: chỉ 1/2586 finding cross-year, và đó chính là C6.1 đang hoạt
động đúng thiết kế (check liên-kỳ phải so opening kỳ N với closing kỳ
N-1). UX có thể gây nhầm cho cán bộ đọc lần đầu, nhưng evidence_refs
ĐÚNG về mặt logic. Defer: nếu HQ phản hồi confusing, sẽ thêm note
"so sánh với kỳ N-1" ở finding_detail render. Chưa làm.

### C1.7 chọn formula của code, không phải registry
Registry nói "/ nhập_trong_kỳ" — strict spec. Code dùng `(opening +
import)` — broader, đúng nghiệp vụ hơn ("tỷ lệ chuyển MĐSD trên tổng
nguồn khả dụng"). Chọn formula code, sửa description spec để match.
Reasoning: nếu DN có tồn đầu lớn + ít nhập mới, chia cho nhập trong kỳ
sẽ blow up; chia cho tổng nguồn khả dụng phản ánh thực tế.

### C1.1 floor 0.5%, C1.4 floor 0.1% — tradeoff
Registry nói "<5% INFO" nghĩa là [0, 5%) đều INFO. Implementation đúng
spec sẽ fire INFO cho diff 0%. Để tránh noise rounding (BCCT/M15 thường
khớp 99.99% do làm tròn), thêm floor nhỏ. Không document floor này trong
registry — coi là implementation detail; nếu HQ muốn fire ngay từ 0% sẽ
xoá floor.

### Bug #6 (dynamic check denominator fallback "nvl") — defer
`denominator_for_rule(code)` fallback "nvl" nếu code chưa map trong
`RULE_SCOPE`. Dynamic check trên `declaration_lines` (vd đếm vi phạm
thuế) sẽ dùng NVL denominator, méo điểm. Defer vì:
- Chưa có dynamic check published, chưa cháy.
- Fix sạch cần thêm field `scope` vào `CheckDefinition` + UI nhập scope
  khi tạo check + migration.
- Để spec_gen AI tự chọn scope cũng cần extend system prompt.

Ghi lại trong Next Steps để vòng fix #2 hoặc khi có dynamic check đầu
tiên publish.

### Commit split theo cụm thay vì 1 commit lớn
User yêu cầu split. Backup files, reset HEAD, apply lại từng cụm bằng
Edit tool, run test, commit. 6 commit gọn, mỗi cái revert được độc lập.
Commit message tiếng Việt theo style repo.

## What Didn't Work

### Tạo evidence_ref cho dynamic check cross_table_match: cân nhắc 1 ref hay 2
Ban đầu nghĩ 1 ref đủ. Nhưng `cross_table_match` so 2 bảng, cả 2 đều có
thông tin cần thiết để cán bộ diễn giải tại sao value_a vs value_b lệch.
Đổi sang 2 ref (cả `table_a` và `table_b` cùng subject_key).

### `_eval_threshold` ban đầu nghĩ giữ logic cũ, đổi tên var
Ban đầu định fix bằng cách giữ for loop nhưng dùng `if matched: continue`
khi op fail. Quá nhiều branch. Refactor sang `op_checks` dict +
`all(op_checks[op](value, band[op]) for op in ops_in_band)` — 1 dòng, đúng AND.

### Tinsu SSH lần đầu chạy `ssh tinsu` (WSL) báo broken
Đúng như memory note. Phải dùng `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`.
Đường dẫn config Windows phải dùng forward slash hoặc escape đúng — lần
đầu gõ `C:/Users/$(whoami)` thất bại vì `$whoami` = "vp" trên WSL nhưng
Windows user dir là "vuong".

## Open Items

1. **Bug #6 chưa fix** — dynamic check fallback denominator "nvl". Cần
   thêm `scope` field vào `CheckDefinition` + migration + UI form. Ưu
   tiên thấp tới khi có dynamic check đầu tiên publish.

2. **C6.1 UX** — display 2 năm evidence có thể gây nhầm. Cân nhắc thêm
   note "so sánh với kỳ N-1" ở `finding_detail.html` cho C6.1, hoặc
   group evidence theo năm với header. Defer.

3. **Demo verify tay** — chưa mở 1 finding cụ thể trên live để xác
   thực evidence hiển thị đúng năm/đối tượng sau fix. Tự động test pass
   nhưng smoke test UI chưa làm.

4. **Catalog backlog** từ session trước (`2026-05-27-catalog-tiers-i18n.md`
   §Next Steps) vẫn còn: gap analysis 49 check vs Johnson Phase 3 /
   BCQT-System / data-hub (Bước 2), spec chi tiết per-check (Bước 3).

5. **C2.4 (tồn cuối TP âm)** vẫn W.I.P theo §4.1 — chưa implement. Symmetric
   với C2.3 cho TP. Có thể clone c2_balance.check_c2_3 sang dùng SpBalance.

6. **DN_001 2025 có 1103 findings** sau rerun (so với 709 trước đây) —
   chủ yếu do INFO band giờ fire đúng. Số lớn nhưng score 296 thấp vì
   rate-based: 1103 finding chia cho denominator NVL distinct lớn của
   2025 (DN_001 năm 2025 nhập nhiều mã mới).
