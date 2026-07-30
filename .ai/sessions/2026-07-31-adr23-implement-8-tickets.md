# 2026-07-31 — Cài trọn 8 vé ADR #23 (#47–#54), test-first, nhánh chưa merge

**Nhánh:** `feat/adr23-ktstq-period-scope` (từ `main` = `f88cc36`), **9 commit, CHƯA push,
CHƯA merge, CHƯA deploy.**

## Đã làm

Cài hết 8 vé của ADR #23 theo đúng thứ tự phụ thuộc, mỗi vé viết test trước:

| Vé | Nội dung | Commit |
|---|---|---|
| #47 BCCT-1 | `app/checks/scope.py` — `declaration_scope` là selector DUY NHẤT cho vế BCCT của 17 check | `736118b` |
| #48 BCCT-2 | Ingest LƯU TRỌN dòng BCCT; `app/pipeline/coverage.py` đếm 3 cảnh báo lúc render | `8d02be0` |
| #49 BCCT-3 | Sửa kỳ bump `data_version`; cảnh báo chồng lấn; banner khoảng thiếu | `8d02be0` + `ffa4a86` |
| #50 NIENDO-1 | `companies.fiscal_start_month`; chuỗi suy cửa sổ 4 tầng; nhãn kỳ kèm khoảng ngày | `99b92fc` |
| #51 TPL-1 | `app/adapters/templates.py` — tầng builtin + nguồn `builtin-template` | `328a9fe` |
| #52 TPL-2 | Seed 4 họ đo từ census + badge 3 trạng thái | `328a9fe` |
| #53 KTSTQ-1 | `registry.requires` + `check_runs.skip_reason` + loại khỏi trần điểm | `0050e8c` |
| #54 KTSTQ-2 | `companies.audit_decision_date`; màn `/scope`; tag render-time | `21dd9eb` |

**Toàn bộ test XANH, `ruff check app tests scripts` sạch.** ~120 test mới.

## Hai cổng nghiệm thu — cả hai QUA, và cổng 2 cho kết quả KHÁC dự đoán của ADR

Phương pháp delta (xem `[[harness-baseline-methodology]]`): dựng `git worktree` ở `HEAD`
cũ, chạy trên BẢN COPY DB, so khoá `(company, period_year, check_code, subject_key, book)`
+ severity.

- **Cổng 1** (đổi query trên DB hiện trạng, KHÔNG re-ingest): **14.961 finding, delta = 0**
  trên cả 3 pilot. Không dòng nào vào/ra scope.
- **Cổng 2** (fresh re-ingest PILOT_002/2025 + PILOT_006/2024 + PILOT_006/2025, **385.722
  dòng BCCT**): **14.970 finding, delta = 0**.

**ADR đoán sai một điểm — ghi lại để đừng tin lại:** ADR #23 viết "006 *file gộp nhiều kỳ*
sẽ có dòng dated 2024 ở nhãn 2025 vào scope 2024 — chủ ý, soát tay". **Không có dòng nào
như vậy.** Đo trên cả 3 pilot: `bcct_out_of_window = 0`, `bcct_undated = 0`. Lý do: parser
đã chọn sheet theo `year` nên mỗi file chỉ đóng góp dòng đúng kỳ của nó ngay từ đầu.
Defect drop-im-lặng ở `ingest.py:330` là THẬT (đã đọc code, đã sửa) nhưng **không có ca
nào trong bộ pilot hiện tại kích hoạt nó**. Đừng dùng bộ pilot này để chứng minh #48 có
tác dụng — nó chỉ chứng minh #48 không làm hỏng gì.

## Migration — đổi kỹ thuật, áp cho cả repo về sau

4 migration nối tiếp: `d6e7f8a9b0c1` (fiscal_start_month) → `e7f8a9b0c1d2` (skip_reason)
→ `f8a9b0c1d2e3` (audit_decision_date) → `a9b0c1d2e3f4` (template_id + match_source).
up → down → up SẠCH trên DB dựng từ đầu.

**`batch_alter_table` KHÔNG dùng được để thêm cột vào `companies` / `check_runs`.** Batch
mode dựng lại bảng bằng DROP + CREATE, mà hai bảng này là ĐÍCH của FOREIGN KEY từ bảng
khác → `DROP TABLE companies` bị từ chối trên DB đã có dữ liệu (`IntegrityError: FOREIGN
KEY constraint failed`). Dùng `op.add_column` / `op.drop_column` thẳng: SQLite ≥ 3.35 hỗ
trợ ADD/DROP COLUMN native, không dựng lại bảng, không đụng FK. Máy dev đang SQLite 3.45.1.

**DB local đã migrate** (head giờ `a9b0c1d2e3f4`). Backup WAL-safe TRƯỚC khi migrate:
`audit_hq.sqlite.bak-pre-adr23-20260731` (`Connection.backup()`, `integrity_check: ok`).

## Lỗi THẬT bắt được ngoài test viết cùng lúc

**Trang tài liệu 500 khi một năm có phát hiện nhưng chưa có dòng điểm năm.**
`company_documents.html:63` render nhãn rủi ro khi `yr.checks_run` bật, mà `checks_run =
y in scores or y in finding_years` — năm có finding nhưng chưa có `CompanyYearScore` cho
`yr.score = None`, `tier_css_for(None)` ném `TypeError: '<=' not supported between
instances of 'NoneType' and 'int'` → hỏng CẢ trang, không riêng một dòng. Lỗi CÓ TRƯỚC
nhánh này; bắt được khi chụp ảnh E2E (seed có năm 2021 chỉ có finding). Đã thêm guard +
test hồi quy `test_documents_page_survives_a_year_with_findings_but_no_score_row`.
`company_detail.html` KHÔNG dính (mặc định `ys_score = 0`).

## Hai test cũ phải sửa — vì tiền đề đổi, không phải vì hỏng

Gate `requires` (#53) làm mọi check thiếu nguồn không chạy nữa, nên hai test dựng fixture
KHÔNG nạp nguồn nào bị đổi kết quả:
- `test_check_run_written_for_every_code_incl_zero_finding` — trước assert `status == "ok"`
  cho cả 17 mã trên DN trống. Nay DN trống ⇒ cả 17 đều `skipped`. Giữ nguyên điều test bảo
  vệ (mọi mã vẫn có dòng `check_runs`), thêm test bạn khẳng định `ok` khi ĐÃ nạp nguồn.
- `test_published_check_counted_in_score_max_raw` — hardcode `max_raw == 200` (18 rule).
  Fixture chỉ có M15 nên 11 check bị skip và bị loại khỏi trần → tính động từ
  `missing_sources`.

## Số đo template (#52) — seed phủ họ PHỔ BIẾN, không phủ file NHIỀU DÒNG

Đo trên toàn bộ `data/` bằng ĐÚNG công thức parser (`select_sheet` → `find_data_start` →
`compute_form_signature`), rồi parse thật qua `parse_m15`/`parse_m15a`:

| Họ | File khớp | Dòng |
|---|---|---|
| `m15-tt39-chuan` | 32 | 2.983 |
| `m15-tt39-bien-the` | 24 | 815 |
| `m15a-tt39-chuan` | 25 | 3.252 |
| `m15a-tt39-bien-the` | 19 | 3.770 |
| **không khớp** | 11 m15 + 8 m15a | **21.030** |

**100/119 file khớp (84%) nhưng 19 file không khớp lại chứa 21.030 / 31.850 dòng (66%).**
Seed phủ các cấu trúc hay gặp, KHÔNG phủ các file nặng dòng nhất. Muốn phủ dòng thì phải
curate tiếp các one-off — việc đó cần mở từng file, không suy từ vân tay được.

Bốn họ đều cân đối 100% với cột mặc định của slot (kiểm 3 file mỗi họ) nên seed với
`column_map` RỖNG: xác nhận cấu trúc, không bịa vị trí cột.

**`match_template` đòi cả vân tay LẪN `data_start` trùng.** Vân tay chỉ hash vùng tiêu đề;
census có 1 file cùng vân tay `b7035ba…` nhưng `data_start=8` thay vì 9 — nhận nhầm ở đó
sẽ dời điểm đọc và nuốt mất một dòng, im lặng.

## Lệch so với vé (cố ý, nêu rõ)

1. **#52 seed KHÁC danh sách họ mà vé nêu — không chỉ là "thiếu BCCT".** Vé ghi 4 họ:
   *"BCCT chi tiết ECUS (phủ 10/11 DN) · BCCT tổng hợp · Mẫu 15a chuẩn (8 DN) · biến thể
   15a DN03/DN04"*. Thực tế seed: **m15 chuẩn · m15 biến thể · m15a chuẩn · m15a biến
   thể** — tức là **hai họ BCCT bị thay bằng hai họ m15 vé không hỏi**, và họ "biến thể
   15a" seed được (19 file / 3 DN) là họ đo được ở đường `select_sheet`, chưa đối chiếu
   xem có đúng là DN03/DN04 của census (55 sheet / 2 DN) hay không.
   Lý do không làm BCCT: `bcct.py` không có `ParseProvenance`, không tính
   `form_signature`, và `IngestStats.provenance` không có khoá `"bcct"` — nối vào là thay
   đổi lớn hơn hẳn vế settlement và sẽ land không có cổng nào che (BCCT là 385k dòng của
   hai cổng nghiệm thu). Đã ĐO sẵn vân tay hai họ đó: chi tiết ECUS
   `543b249251256274b19d4e05e8f1c065` (18 file / 8 DN, `data_start=10`), tổng hợp
   `5c8ce1bc440e9fa60ce2d7768edad48b` (4 file / 2 DN, `data_start=10`). **Chưa seed** vì
   seed mà không có chỗ đọc là số chết, và column map của họ "tổng hợp" chưa xác minh.
   Lý do làm thêm hai họ m15: cùng một seam code với m15a, chi phí bằng 0, và cả hai đã
   đo + kiểm cân đối. **Nhưng đó vẫn là việc vé không hỏi — cần chốt lại với owner.**
2. **`skip_reason` dùng khoá `missing:<nguồn>,<nguồn>`**, không phải `"no_bcqt"` như ví dụ
   trong vé — mang đủ thông tin để dựng câu tiếng Việt mà không cần bảng tra riêng.
3. **Cảnh báo "tiêu đề file lệch niên độ" đọc từ trạng thái ĐÃ LƯU**
   (`period_window_conflict`: cửa sổ `company_periods` không `is_manual` vs cửa sổ suy từ
   `fiscal_start_month`), không đọc lại header lúc review. Cửa sổ tự suy CHÍNH LÀ cửa sổ
   header đã ghi, nên cùng một cảnh báo, mà không phải thêm đường ống header vào
   `parse_detail`. Bản `is_manual` không cảnh báo (cán bộ đã chọn có chủ ý).

## E2E

`.ai/features/2026-07-31-adr23-ktstq-period-scope/` — `brief.md` + `ui_smoke.py` + **7
ảnh**. Server throwaway 8331 + DB riêng trong scratchpad, tự seed tự dọn, kill theo PID.
Ảnh là dữ liệu seed minh hoạ: chứng minh render + luật hiển thị, KHÔNG chứng minh chất
lượng parse (vế đó do hai cổng delta lo).

Bẫy khi chụp: `sync_data_files` XOÁ dòng `data_files` không còn file trên đĩa, nên ảnh màn
review phải chụp TRƯỚC khi vào trang tài liệu.

## `/code-review` hai trục — đã sửa gì, còn gì

Chạy sau khi commit, hai sub-agent song song (Standards / Spec). **Sửa ngay trong nhánh:**

1. **Chứng cứ BCCT ở BẢN XUẤT và trang chi tiết mã còn lọc theo NHÃN** trong khi check đã
   đổi sang cửa sổ (`export.py` sheet "Chứng cứ BCCT", `items/aggregations.py
   bcct_lines_for_item`). Vi phạm AGENTS.md *"mọi phát hiện phải có FK về dòng dữ liệu
   Tầng 1"*: chứng cứ xuất ra Excel có thể khác tập dòng đã tính ra phát hiện. Nay cả hai
   dùng `declaration_scope`.
2. **`declaration_scope` làm MẤT dòng khi kỳ láng giềng chưa có dòng `company_periods`.**
   Dòng dated 2024 nạp dưới nhãn 2025 rơi khỏi cửa sổ 2025, mà kỳ 2024 (chưa có dòng kỳ)
   lại chỉ nhận theo nhãn → dòng không thuộc kỳ nào. Đúng dạng mất dòng mà #48 sinh ra để
   chặn. Nay `effective_window` suy cửa sổ từ niên độ DN khi chưa có dòng kỳ. **Chạy lại
   cổng 1: vẫn 14.961 finding, delta = 0.**
3. `available_sources` + `_has_bcqt` dùng `COUNT(*) … LIMIT 1` — `LIMIT` không cắt được
   aggregate nên vẫn quét trọn bảng (BCCT: hàng trăm nghìn dòng mỗi lần chạy check). Nay
   `SELECT id … LIMIT 1`, và `_has_bcqt` gọi thẳng `available_sources` thay vì lặp lại.
4. `scope_coverage` đếm check `status='error'` là "đã chạy" — nay loại ra.
5. `finding_detail.html` in trần `Kỳ {{ period_year }}` — thiếu so với #50 *"MỌI màn hiện
   nhãn kỳ ≠ dương lịch in kèm khoảng ngày"*. Nay có khoảng ngày.
6. Bỏ code chết: `MATCH_LABEL_VI`, `declaration_date_span`,
   `header_conflicts_with_fiscal_year` (bị `period_window_conflict` thay thế). Bỏ một
   query `company_periods` lặp trong `load_period_windows`.

**Còn mở, KHÔNG sửa trong nhánh này:**

- **Map officer per-DN mới thắng template ở NHÃN, chưa thắng ở VỊ TRÍ CỘT.**
  `resolve_officer_confirmed` chỉ nâng nguồn bằng chứng SAU khi parse xong; chỉ số cột
  lúc parse vẫn của template. Hôm nay chưa lệch được vì cả 4 họ seed đều `column_map`
  rỗng — nhưng phải sửa TRƯỚC khi seed họ đầu tiên có map riêng. Đã ghi cảnh báo ngay
  trong docstring `app/adapters/templates.py`.
- **Đường bố cục MỞ RỘNG (`select_extended_m15`) return TRƯỚC khi dò template**, nên với
  file mà `select_sheet` trượt thì suy-từ-khoá thắng template. ADR ghi thứ tự template
  trước dò từ khoá. Ảnh hưởng hẹp (chỉ file mà đường chuẩn đã trượt hẳn).
- **Chưa có index `(company_id, declaration_date)`.** Mọi check giờ lọc BCCT bằng khoảng
  ngày, mà `ix_decl_company_year_code` / `ix_decl_customs` đều dẫn bằng `period_year` nên
  không còn dùng được; chỉ còn index một cột `declaration_date`. Cổng 2 chạy trọn 385.722
  dòng trong thời gian chấp nhận được nên chưa chặn, nhưng là rủi ro hiệu năng thật khi
  số DN tăng.
- **`declaration_scope` bắn một SELECT `company_periods` mỗi lần DỰNG mệnh đề WHERE**
  (6 lần mỗi lượt `c1_quantity`, ~4 lần mỗi dòng năm ở trang tài liệu). Tra một dòng có
  index trên bảng bé nên rẻ, nhưng số lần gọi là thừa — hoist một lần mỗi (DN, kỳ) được.
- **Bảng đối chiếu mà vé đòi đính PR** (#48 bảng soát từng dòng, #53 bảng nguồn-thực-đọc
  từng check) chưa có PR để đính. Bảng nguồn nằm trong test
  `test_requires_matches_the_source_audit`; số cổng nằm ở đây.

## Còn mở

1. Nối template builtin vào `bcct.py` (cần thêm `ParseProvenance` cho BCCT +
   `IngestStats.provenance["bcct"]`) → mới seed được 2 họ BCCT đã đo.
2. Curate tiếp các file m15/m15a one-off — 19 file chưa khớp chiếm 66% số dòng.
3. Chưa push, chưa mở PR, chưa deploy. Prod vẫn `d7844b6`, head migration prod vẫn
   `c5d6e7f8a9b0` → deploy nhánh này cần chạy 4 migration.
4. `C6.1` khai `requires={m15}` theo đúng từ vựng vé (per (DN, kỳ)), nhưng check còn đọc
   M15 của kỳ N-1. Kỳ N-1 trống thì C6.1 vẫn chạy và ra 0 finding — cùng dạng "sạch giả"
   mà #53 sinh ra để diệt, chỉ khác trục. Không sửa ở vé này (ngoài từ vựng `requires`).
