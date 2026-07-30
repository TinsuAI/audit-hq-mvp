# Kế hoạch gộp nhanh — đợt chạy song song 2026-07-30

Đọc trước khi gộp bất kỳ nhánh nào trong đợt 17 luồng tối nay. Không nhánh nào đã push hay
merge; tất cả nằm trong worktree riêng dưới `.claude/worktrees/`. Tài liệu này chỉ dựa trên
`git log`, `git diff`, `git status`, `git merge-tree` — không chạy test, không gộp thật.

## 0. Tình trạng tìm thấy

Trong 17 tên nhánh kỳ vọng, 7 nhánh đã **commit đầy đủ** dưới đúng tên:

- `fix/ai-overview-timeout-and-empty-content` — `12c7fb9`
- `fix/overview-staleness-format` — `c14334d`
- `fix/xstar-book-label` — `2f8bbfa`
- `fix/percentile-keys-guardrail` — `ef80f32`, `58d9383`
- `fix/c43-multiplier-p07` — `4bf5333`
- `feat/findings-export-xlsx` — `852773b`
- `docs/punchlist-7-glossary` — `9eca1d5`

2 nhánh **tồn tại nhưng rỗng** (con trỏ trùng `main` = `f88cc36`, không có commit riêng):

- `test/traceability-invariant` — worktree sạch, chưa có gì, kể cả uncommitted.
- `feat/finding-reviews-t1` — worktree **có sửa nhưng CHƯA COMMIT**: `app/models/finding_review.py`
  (mới), `app/models/__init__.py` (sửa), `migrations/versions/cdbe8615226a_finding_reviews_table.py`
  (mới, revision mới — xem mục 3).

8 nhánh **không tìm thấy dưới đúng tên**: `fix/ai-tools-stale-risk-score`,
`fix/catalog-public-risk-column`, `chore/scrub-real-identifiers-from-tests`,
`fix/ai-error-logging-no-raw-body`, `docs/fix-stale-claims`, `perf/company-periods-year-source`,
`perf/book-partial-indexes`, `fix/wording-pass-remainder`. Tuy nhiên rà `git status` trên toàn bộ
worktree (kể cả nhánh tên generic `worktree-agent-*` chưa đổi tên) lộ ra **uncommitted work khớp
nội dung** với 5 trong 8 tên trên:

| Worktree (tên nhánh generic) | File uncommitted | Khớp với tên kỳ vọng |
|---|---|---|
| `agent-a601e9a6763f8c678` | `app/ai/client.py`, `app/ai/overview.py`, `app/routes/ai.py`, `tests/test_ai_error_logging.py` (mới) | `fix/ai-error-logging-no-raw-body` |
| `agent-aa1df55d62a8020a7` | `app/models/bcqt.py`, `migrations/versions/d4e5f6a7b8c9_book_partial_indexes.py` (mới) | `perf/book-partial-indexes` |
| `agent-ab8e92fa2797a6c73` | `tests/test_company_years_source.py` (mới) | `perf/company-periods-year-source` |
| `agent-afddfe1f3991594b8` | `app/static/style.css`, `app/templates/catalog_full.html`, `tests/test_jobs/test_catalog_route.py` | `fix/catalog-public-risk-column` |
| `agent-aa044ef5341472342` | `app/routes/admin_ai.py`, `app/templates/admin_ai.html` | không chắc — có thể `fix/wording-pass-remainder`, chưa xác nhận |

3 nhánh còn lại (`fix/ai-tools-stale-risk-score`, `chore/scrub-real-identifiers-from-tests`,
`docs/fix-stale-claims`) không tìm thấy cả dưới tên đúng lẫn nội dung khớp trong các worktree còn
sạch (`agent-a1b763e946a19233b`, `agent-a1cd9076024dbfd41`, `agent-a30cb7b98973760e1`) — các
worktree này không có gì, kể cả uncommitted. Coi như **chưa bắt đầu hoặc đã bị bỏ**.

Kết luận mục 0: chỉ 7 nhánh đủ điều kiện xét gộp ngay (đã commit). `feat/finding-reviews-t1` và
2 worktree uncommitted có migration (`aa1df55d62a8020a7`) cần được **commit trước** rồi mới xét —
xem mục 3.

## 1. Từng nhánh — commit, file, mô tả

| Nhánh | Commit | File thay đổi | Mô tả |
|---|---|---|---|
| `fix/ai-overview-timeout-and-empty-content` | `12c7fb9` | `app/ai/client.py`, `app/ai/overview.py`, `tests/test_ai_fallback.py`, `tests/test_ws3_overview.py` | Thêm `deadline_s` (từ `request_timeout_s`) vào `call_with_fallback`; nội dung LLM trả rỗng nhưng không lỗi giờ ném `RuntimeError` thay vì ghi overview `status=done` trống. |
| `fix/overview-staleness-format` | `c14334d` | `app/ai/overview.py`, `app/models/check_overview.py`, `tests/test_overview_batch.py`, `tests/test_ws3_overview.py` | `overview_is_stale` coi dòng thiếu `aggregate_json` (định dạng trước ADR #21) là cũ ngay cả khi `ran_at`/`data_version` chưa dời — sửa bug production PILOT_006/C1.1 2026-07-27. |
| `fix/xstar-book-label` | `2f8bbfa` | `.ai/STATUS.md`, `app/checks/sql_runner.py`, `tests/test_dynamic_checks/test_sql_runner.py` | `sql_runner._rows_to_findings` đọc cột kết quả tuỳ chọn `book` từ SELECT, gán `finding.book` giống check tích hợp; check X.* SQL/Python trước đây luôn emit `book=NULL`. |
| `fix/percentile-keys-guardrail` | `ef80f32`, `58d9383` | `.ai/BACKLOG.md`, `app/ai/overview_stats.py`, `tests/test_overview_stats.py` | Bỏ entry chết `PERCENTILE_KEYS["C3.2"]`, thêm test guardrail; đóng mục BACKLOG tương ứng. |
| `fix/c43-multiplier-p07` | `4bf5333` | `.ai/GLOSSARY.md`, `app/adapters/extended_layout.py`, `app/catalog_full.py`, `app/checks/c4_norm.py`, `app/checks/registry.py`, `tests/test_checks/test_c4_norm.py` | C4.3 đổi số nhân định mức sang sản lượng sản xuất (M15a intake) thay vì lượng xuất khẩu, theo quyết định P-07. |
| `feat/findings-export-xlsx` | `852773b` | `app/pipeline/export.py`, `tests/test_export_findings_traceability.py` | Thêm cột sổ (book), kỳ, và tham chiếu bằng chứng vào file xuất findings. |
| `docs/punchlist-7-glossary` | `9eca1d5` | `.ai/DECISIONS.md`, `.ai/GLOSSARY.md` | Sửa lệch GLOSSARY/ADR #19 (punch-list 7): mô hình 1 pháp nhân/1 row thay 2 row EPE/GC, đính chính nhóm C3.1/C3.2 không có nguồn `book` để gán, `AI_OVERVIEW` job đã cài. |
| `test/traceability-invariant` | — (rỗng) | — | Chưa có commit, chưa có uncommitted work. |
| `feat/finding-reviews-t1` | — (rỗng, chưa commit) | `app/models/finding_review.py`, `app/models/__init__.py`, `migrations/versions/cdbe8615226a_finding_reviews_table.py` | Bảng `finding_reviews` độc lập với `Finding.id` (không ổn định qua re-run), neo khoá tự nhiên `(company_id, period_year, check_code, subject_key, book)` để giữ trạng thái "đã soát" qua lần chạy lại. |

## 2. Ma trận xung đột

File đụng nhau giữa các cặp nhánh đã commit:

| Cặp nhánh | File chung | Có xung đột dòng thật không |
|---|---|---|
| `fix/ai-overview-timeout-and-empty-content` × `fix/overview-staleness-format` | `app/ai/overview.py` | KHÔNG — A sửa trong `generate_check_overview` (dòng ~181-208, thêm `timeout_s`/raise khi content rỗng); B sửa trong `overview_is_stale` (dòng ~122-140, thêm nhánh `aggregate_json is None`). Vùng dòng tách biệt. |
| `fix/ai-overview-timeout-and-empty-content` × `fix/overview-staleness-format` | `tests/test_ws3_overview.py` | KHÔNG — A thêm test mới ở cuối file (test timeout/empty-content), B sửa helper `_ov()` + thêm 2 test staleness. Không cùng vùng dòng. |
| `fix/c43-multiplier-p07` × `docs/punchlist-7-glossary` | `.ai/GLOSSARY.md` | KHÔNG — E sửa mục "Individually-consumed column" (dòng ~19-24); G sửa 4 đoạn khác (dòng ~43, ~78, ~89, ~116+, mục "Pháp nhân"/"Liên sổ"). Không chồng dòng. |

Đã xác nhận cả hai cặp bằng `git merge-tree --write-tree <A> <B>` (chiến lược `ort`, git 2.43) —
cả hai trả về một tree hash duy nhất, exit 0, không có báo cáo conflict. Định dạng `merge-tree`
3 tham số kiểu cũ (`base A B`) gắn nhãn "changed in both" cho các file này vì nó chỉ báo "cả hai
bên đổi file", KHÔNG có nghĩa là xung đột dòng — đừng đọc nhầm nhãn đó thành CONFLICT.

Điểm nóng riêng — `.ai/STATUS.md`: `fix/xstar-book-label` (`2f8bbfa`) sửa mục "Punch-list 7 + 8"
ở dòng ~552-560. `main` hiện có sửa **uncommitted** ở đầu file (chèn 2 khối trạng thái mới, dòng
1-70) — không chồng dòng với sửa của nhánh. Tuy nhiên `git merge`/`git checkout` sẽ từ chối nếu
`.ai/STATUS.md` có thay đổi chưa commit tại thời điểm merge (dù không chồng dòng), báo lỗi "local
changes would be overwritten". **Phải commit hoặc stash `.ai/STATUS.md` trên `main` trước khi gộp
`fix/xstar-book-label`.**

`.ai/DECISIONS.md`: chỉ `docs/punchlist-7-glossary` đụng trong số các nhánh đã commit — không có
cặp để xét. `app/checks/registry.py` và `app/catalog_full.py`: chỉ `fix/c43-multiplier-p07` đụng
— không có cặp để xét trong các nhánh đã commit.

Không cặp nhánh nào khác trong 7 nhánh đã commit đụng chung file.

## 3. Alembic heads

Head hiện tại trên `main`: `c5d6e7f8a9b0` (`overview_sections`). Không nhánh nào trong 7 nhánh
đã commit thêm migration. Nhưng rà `git status` lộ ra **2 migration mới, cả hai UNCOMMITTED**,
cùng chain từ `c5d6e7f8a9b0`:

| Revision | File | `down_revision` | Vị trí |
|---|---|---|---|
| `cdbe8615226a` | `migrations/versions/cdbe8615226a_finding_reviews_table.py` | `c5d6e7f8a9b0` | worktree nhánh `feat/finding-reviews-t1`, chưa commit |
| `d4e5f6a7b8c9` | `migrations/versions/d4e5f6a7b8c9_book_partial_indexes.py` | `c5d6e7f8a9b0` | worktree `agent-aa1df55d62a8020a7` (nghi là `perf/book-partial-indexes`), chưa commit |

Nếu cả hai được commit rồi merge như hiện trạng, `main` sẽ có **2 alembic head** cùng lúc
(`cdbe8615226a` và `d4e5f6a7b8c9`), vì cả hai cùng khai `down_revision = c5d6e7f8a9b0`.

**Cách xử lý:** đây là 2 migration độc lập về mặt dữ liệu (bảng mới `finding_reviews` không đụng
schema mà partial index nhắm tới) — **rechain đơn giản là đủ, KHÔNG cần revision `alembic merge`**.

1. Commit và gộp `feat/finding-reviews-t1` trước (giữ nguyên `down_revision = c5d6e7f8a9b0`).
2. Trước khi gộp `perf/book-partial-indexes`, sửa `down_revision` trong
   `d4e5f6a7b8c9_book_partial_indexes.py` từ `'c5d6e7f8a9b0'` thành `'cdbe8615226a'`, chạy lại
   `alembic upgrade head` trên DB test để xác nhận chain áp được, rồi mới commit/gộp.

Thứ tự giữa hai cái này không quan trọng về nghiệp vụ — chọn `finding_reviews_table` đi trước vì
nó phục vụ `test/traceability-invariant` (T1), vốn có vẻ là hạng mục được ưu tiên trong đợt này
(tên nhánh `-t1` + ghi chú trong `.ai/STATUS.md` uncommitted về khoá bền qua re-run).

## 4. Thứ tự gộp

Áp dụng cho 7 nhánh đã commit; 2 nhánh còn migration uncommitted xử lý theo mục 3 sau khi đã có
commit thật.

1. **`fix/percentile-keys-guardrail`** — chỉ đụng `.ai/BACKLOG.md` + `app/ai/overview_stats.py`,
   không giao với nhánh nào khác. Gộp trước để dọn nền, rủi ro bằng không.
2. **`docs/punchlist-7-glossary`** — chỉ sửa tài liệu (`GLOSSARY.md`, `DECISIONS.md`), không đụng
   code. Gộp sớm để các nhánh sau (nhất là `fix/c43-multiplier-p07`, cũng sửa `GLOSSARY.md`) rebase
   trên bản tài liệu mới nhất, tránh merge muộn phải rà lại xung đột tài liệu.
3. **`fix/c43-multiplier-p07`** — sau (2) vì cùng đụng `GLOSSARY.md` (không xung đột dòng theo mục
   2, nhưng gộp theo thứ tự tài liệu → logic là kỷ luật tốt hơn). Đây là nhánh sửa nghiệp vụ nặng
   nhất (C4.3), nên gộp sớm, cô lập, và **chạy full test riêng nhánh này** trước khi đi tiếp.
4. **`feat/findings-export-xlsx`** — độc lập hoàn toàn (`app/pipeline/export.py`), không giao file
   với ai. Gộp bất kỳ lúc nào; đặt ở đây để giữ mạch "độc lập trước, giao nhau sau".
5. **`fix/ai-overview-timeout-and-empty-content`** — gộp trước `fix/overview-staleness-format` vì
   theo `git log`, `12c7fb9` (giờ tạo commit) đứng trước `c14334d`; không bắt buộc về xung đột (mục
   2 đã xác nhận sạch) nhưng gộp theo thứ tự thời gian giảm nguy cơ trộn lẫn hai đợt sửa cùng file
   `tests/test_ws3_overview.py` khi debug nếu có lỗi phát sinh.
6. **`fix/overview-staleness-format`** — ngay sau (5). Sau khi gộp cả hai, **bắt buộc chạy lại**
   `pytest tests/test_ws3_overview.py tests/test_overview_batch.py` trên `main` đã gộp — merge tự
   động sạch không đảm bảo hai bộ test không xung đột logic (vd. `_ov()` helper của B thêm tham số
   mặc định, A thêm test dùng helper cũ — cần xác nhận bằng chạy thật, không suy diễn từ diff).
7. **`fix/xstar-book-label`** — gộp cuối cùng trong nhóm 7 vì đụng `.ai/STATUS.md`, nơi `main` có
   uncommitted changes. **Trước bước này: commit hoặc stash `.ai/STATUS.md` trên `main`.** Sau khi
   xử lý STATUS.md, rebase `fix/xstar-book-label` lên `main` đã gộp (1)-(6) và chạy lại test
   `tests/test_dynamic_checks/test_sql_runner.py`.
8. **`feat/finding-reviews-t1`** — commit phần uncommitted trước (mục 3), rebase lên `main` đã
   gộp (1)-(7), chạy `alembic upgrade head` + test liên quan, rồi gộp.
9. **`perf/book-partial-indexes`** (worktree `agent-aa1df55d62a8020a7`) — commit phần uncommitted,
   sửa `down_revision` theo mục 3, rebase lên `main` đã có (8), chạy `alembic upgrade head` xác
   nhận 1 head duy nhất, rồi gộp.

Các nhánh còn lại (`test/traceability-invariant` rỗng; `perf/company-periods-year-source`,
`fix/catalog-public-risk-column`, `fix/ai-error-logging-no-raw-body`, và nhánh nghi
`fix/wording-pass-remainder` — tất cả đang ở dạng uncommitted trong worktree tên generic) phải
được **commit dưới đúng tên nhánh trước**, sau đó lặp lại bước rà xung đột + test ở mục 2 và 5
cho từng nhánh; tài liệu này không đủ dữ liệu để xếp thứ tự cho chúng vì nội dung commit thật
chưa tồn tại để `git merge-tree` kiểm tra.

## 5. Cổng kiểm — chưa nhánh nào chạy full suite

Toàn bộ 17 luồng chạy dưới áp lực thời gian tối nay và mỗi luồng chỉ chạy **một phần** test liên
quan trực tiếp đến thay đổi của mình — **không nhánh nào đã chạy trọn `pytest tests`**. Trước khi
gộp bất kỳ nhánh nào ở mục 4, chạy đúng trình tự sau cho từng nhánh, trong worktree riêng của
nhánh đó (không chạy trên `main` đang có uncommitted changes):

```bash
# Trong worktree của nhánh cần kiểm — DATABASE_URL RỖNG là bắt buộc:
# app/ai/config.py bind SessionLocal lúc import; nếu để trống, biến môi trường sẽ
# trỏ vào DB dev sẵn có trên máy → test "xanh giả" vì đọc nhầm dữ liệu ambient.
DATABASE_URL= .venv/bin/pytest tests -q

# Lint toàn bộ, không giới hạn phạm vi nhánh:
.venv/bin/ruff check app tests scripts
```

Cả hai lệnh phải chạy sạch (exit 0) trước khi nhánh đó được coi là sẵn sàng gộp theo thứ tự mục 4.
Với `feat/finding-reviews-t1` và `perf/book-partial-indexes`, thêm bước xác nhận alembic trước
`pytest`:

```bash
.venv/bin/alembic upgrade head   # phải chạy không lỗi, kết thúc ở đúng 1 head
.venv/bin/alembic heads          # phải in ra đúng 1 dòng
```

Sau khi gộp mỗi nhánh vào `main` cục bộ (theo thứ tự mục 4), chạy lại toàn bộ `pytest tests -q`
với `DATABASE_URL` rỗng trên `main` đã gộp — không chỉ test của riêng nhánh vừa gộp — trước khi
chuyển sang nhánh kế tiếp trong danh sách.
