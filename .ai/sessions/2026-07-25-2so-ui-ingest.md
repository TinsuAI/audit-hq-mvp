# Session — 2026-07-25 — UI + ingest theo sổ quyết toán (5 ticket 2SỔ)

Branch: `feat/004-two-loai-hinh`. Không push, không deploy.

## Mục tiêu
`/implement lần lượt hết các tickets` — cài trọn 5 ticket GitHub 2SỔ-1..2SỔ-5 (#18/#20/#21/#19/#22),
đưa cột `book` (sổ quyết toán, ADR #19) lên giao diện + hợp đồng ingest. Design đã chốt ở **ADR #19
Revision — UI + upload** (grill xong phiên trước). Build A (hiển thị+lọc) trước, B (upload+ingest) sau.

## Đã làm

### Branch A — hiển thị + lọc (commit `95f23eb`, ticket 2SỔ-1/2/3)
- **`app/books.py` (mới):** `company_books(db, company_id, year)` (tập book khác null từ
  `nvl∪sp∪norms`, sort — KHÔNG suy từ finding); `is_multi_book` (gate ≥2 sổ); `book_label`
  (known-map EPE/GC, lạ→`Sổ {code}`, null→`Chung (liên sổ)`); `book_summary` (strip mã NVL +
  phát hiện mỗi sổ + ô Chung, loại COMBO_).
- **`company_detail`:** strip header theo sổ; dòng split per-check `Sổ: EPE 8 · Chung 2` (chỉ
  bucket >0); pill book mỗi dòng finding + combo card; segmented `?book=` (`chung`→`Finding.book
  IS NULL`, mã lạ→bỏ qua). **View-filter thuần** qua `_book_clause()` áp vào counts/rows/combo;
  điểm năm · strip · export · run GIỮ toàn pháp nhân. Sửa `checks_run` sang full-entity
  (`year_score is not None or selected_year in finding_years`) để lọc sổ sạch không lật "chưa chạy".
  Empty-state sổ sạch tách khỏi no-data/not-run.
- **`finding_detail`:** field "Sổ quyết toán". `book_label` là template global.
- CSS: `.book-strip`, `.book-filter`, `.book-pill`, `.book-split`.

### Branch B — upload + ingest (commit `148bd3d` + `250ee5f`, ticket 2SỔ-4/5)
- **Migration `d0e1f2a3b4c5`:** cột nullable `data_files.book` (down `c9d0e1f2a3b4`; head mới
  `d0e1f2a3b4c5`, up/down/up sạch).
- **`ingest._plan_settlement_files`:** đọc book per settlement file từ `data_files`, gom theo sổ,
  parse từng file, tag rows; KHÔNG có tag (CLI/script/một sổ) → dùng file discover, book=NULL →
  002/006 + script không đổi. Tờ khai/BCCT ghi MỘT lần (book=NULL) — cấu trúc, không dedup.
  **RETIRE `_guard_single_book`** + xoá `tests/test_ingest_guard.py`.
- **Selector review WS1:** `document_review.html` thêm ô chọn sổ chỉ ở slot settlement
  (`SETTLEMENT_SLOTS`), datalist = `company_books()` + known EPE/GC; `documents_confirm_review`
  đọc + `normalize_book` (trim/upper), ghi `data_files.book`, re-ingest sẵn có gom balances theo
  sổ; đổi sổ trên file đã parsed → re-run TOÀN BỘ năm (findings gắn lại book). `sync_data_files`
  giữ nguyên cột book (chỉ refresh name/size/slot).

### Test (test-first)
+28 test mới: `test_books` (7), `test_book_findings_ui` (4), `test_book_filter` (8), `test_ingest_book`
(4), `test_book_selector` (5). Bỏ `test_ingest_guard` (2). E2E `test_ingest_book` (2 file M15 EPE/GC +
BCCT → balances đúng book + tờ khai ghi 1 lần) + `test_book_selector` (gắn 2 sổ qua endpoint thật →
branch A hiện strip 2 sổ). Full suite xanh, ruff sạch.

## Code-review 2 trục (Standards + Spec, sub-agent song song)
- **Sửa 1 lỗi thực (Spec):** empty-state clean `đã được đánh giá — 0 phát hiện` thiếu guard `checks_run`
  → nhiều sổ nạp mà CHƯA chạy kiểm tra thì lọc sổ báo nhầm "đánh giá-sạch". Nay template tách nhánh
  `and checks_run` vs `and not checks_run` ("chưa chạy kiểm tra cho sổ này"). +1 regression test.
- **Cleanup:** hằng `SETTLEMENT_SLOTS` (data_file.py) thay literal 3 chỗ; `normalize_book` import
  top-level; datalist EPE/GC render từ `BOOK_LABELS` (một nguồn).

## Chưa làm / hạn chế đã biết
- **Multi-book UPLOAD đầy đủ:** `record_parse_result` áp MỘT provenance/slot → khi nhiều file cùng
  slot (nhiều sổ), `parse_detail`/`row_count` per-file chưa đúng (balances vẫn đúng — chỉ số hiển thị
  per-file undercount). Analyze-per-file là việc "B-plus" lớn hơn, ngoài scope 5 ticket.
- **Chưa push/PR/deploy.** Prod head `c9d0e1f2a3b4` → cần `alembic upgrade head` áp `d0e1f2a3b4c5`.
- Muốn 004 hai sổ trên prod: tạo dữ liệu book (upload+tag qua selector, hoặc collapse như local).
- `uv.lock` untracked (theo quy ước cũ).

## Next
1. Push branch → PR → CI test+lint+deploy self-hosted.
2. `alembic upgrade head` prod (áp `d0e1f2a3b4c5`).
3. Nếu cần demo 004 hai sổ sống trên prod: nạp + gắn book.
