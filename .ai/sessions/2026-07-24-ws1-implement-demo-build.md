# Session 2026-07-24 — WS1 implement (5 ticket) + demo build + fix dev server

Triển khai trọn WS1 (parse review) từ tickets #4–#8, build bản demo 3 công ty, sửa 500 do dev server cũ.
Nối tiếp `2026-07-24-grill-ws1.md` (ADR #18). WS2 grill chạy song song session khác (`2026-07-24-grill-ws2.md`).

## What Was Done

- **`/to-tickets`**: cắt WS1 thành 5 tracer-bullet, publish GitHub issue #4–#8 (label `ready-for-agent`),
  blocking chain #4→#5→#6→#7→#8. Tạo label `ready-for-agent` (repo chưa có).
- **WS1 5 ticket** trên branch `feat/ws1-parse-review` (mỗi ticket một agent fresh, verify độc lập, commit riêng):
  - #4 `7df7e22` — evidence source (`officer-confirmed` > `header-matched`·`balance-checked` > `position-only`)
    + `review_state` mỗi cột; registry `CHECK_COLUMNS` (`consumed_as` individual|sum) trong
    `app/checks/registry.py`; ghi `ParseProvenance.evidence` → `parse_detail.columns/review`; badge.
    Header-match qua per-column header-band scan trong `app/adapters/evidence.py`.
  - #5 `0653f1d` — `DataFileStatus` thành trục lifecycle (pending=uploaded / analyzed / ok=parsed / error,
    bỏ WARNING); upload dry-run analyze → auto-advance nếu verified, dừng `analyzed` nếu needs_review
    (banner warn-not-block). `should_stop_for_review(gate, has_saved_map)` là điểm quyết định duy nhất.
  - #6 `fca9bbb` — `form_signature` (hash header chuẩn hoá, KHÔNG mã DN); bảng `saved_column_maps` keyed
    `(company_id, slot, form_signature)`, migration `b7d2e1f4a3c6`; `resolve_officer_confirmed` gọi trong
    `record_parse_result`; seed 6 whitelist officer-confirmed. Per-DN (không chéo DN), chéo năm cùng DN.
  - #7 `573a273` — màn review (`document_review.html`) xem/sửa/xác nhận map → `save_column_map` + re-ingest
    → advance `parsed`. Route ownership-checked.
  - #8 `f00db6f` — sửa map file `parsed` → re-run scoped `run_checks(only=checks_reading(changed))`;
    guard cột-khoá (`checks_reading_slot`) chống treo finding C2 (finding lọc evidence theo mã hàng, không id).
  - Gate cuối: **634 test pass, ruff sạch, harness whitelist 417 bất biến**. Migration up/down/up verify độc lập.
- **Harness regression** (`scratchpad/harness.sh`): fresh-ingest whitelist vào DB throwaway (DATABASE_URL
  override — KHÔNG đụng DB dev) → **417 finding / 2 combo**. Dùng làm delta guard mọi ticket.
- **Demo build** `db-data/audit_hq_demo.sqlite` (gitignored, CHƯA deploy): copy WAL-safe DB local
  (`sqlite3.backup`), giữ 002/006/004, xoá phần còn lại, đổi `name` sang tên demo. 004 gộp option 2:
  reassign Tầng-1 GC→EPE, xoá kỳ GC trùng (unique company_periods), `run_checks(PILOT_004_EPE, 2025)`.
- **Fix 500** trang company: dev server PID 8340 chạy code cũ `84da630` (không `--reload`) vs DB đã tiến
  xa (C1/M15a/WS1 + pilot) → kill PID + relaunch detached `--reload`. TestClient trên code HEAD = 200.
- Memory mới: `pilot-004-epe-gc-merge`.

## Decisions Made

- **Delegate mỗi ticket cho agent general-purpose fresh** (khớp "fresh context per ticket" của ADR #18);
  orchestrator verify độc lập (full suite + harness + diff review) rồi commit. #7/#8 nhịp gọn: agent chạy
  full-suite 1 lần cuối, targeted test lúc dev.
- **#4 KHÔNG sửa `BALANCE_EXPECT`** (dù ticket gợi ý thêm keyword cột 6/7/9): thêm keyword làm
  `find_header_columns` chọn dòng con → tụt `__code__` anchor → `_score`=0 → vỡ chọn sheet whitelist,
  đổi finding. Thay bằng header-band scan độc lập trong `evidence.py` → whitelist vẫn verified.
- **#6 dùng migration thật** (bảng mới); #5/#7/#8 không migration (StrEnum value mới trong String column;
  reuse bảng #6). Test suite dùng `create_all` KHÔNG chạy migration → phải verify alembic up/down/up riêng.
- **004 = 1 pháp nhân** (cùng MST `0901051747`, cùng kỳ FY2025). User chốt gộp **option 2** (219) làm demo
  TẠM nhưng note phải phân tích lại — gộp làm méo findings.
- **MST giữ thật** ở `tax_id` theo lệnh "chỉ đổi tên, dữ liệu khác để nguyên". Flag: file Excel gốc còn tên thật.
- **Demo build trong scratchpad trước → move `db-data/`** (gitignored). KHÔNG deploy (outward-facing, chờ user).
- **Không dùng Workflow tool** (user chưa opt-in ultracode); chuỗi tuần tự nên Agent-per-ticket đủ.

## What Didn't Work

- **Option 2 gộp 004** cho số méo: 187 → **219** với đảo lớn — C1.2 −95 (mã "thiếu M15" một book khớp
  M15 book kia → che thiếu sót thật), C1.1 +80 / C1.4 +41 (18 mã trùng thành 2 dòng + tờ khai chéo book).
  Không đại diện đúng vì trộn 2 chế độ hải quan (chế xuất vs gia công). Giữ tạm, đánh dấu re-analyze.
- **Chạy Python bằng `python`** — không có trên PATH, phải `uv run`. Lần đầu baseline suite no-op (exit 0
  giả từ zsh eval mà thực ra "command not found").
- **Baseline "419"** (ADR #17) ≠ đo thực tế **417** trên branch này. Dùng DELTA 417, không số tuyệt đối
  (xem [[harness-baseline-methodology]]).

## Open Items

- **Push/merge WS1** — chưa push, chưa PR. Issue GH #4–#8 đã cài, chưa đóng.
- **Nợ WS2 (ADR #18 Revision):** #7/#8 gọi `run_checks` ĐỒNG BỘ trong `documents_confirm_review` → chuyển
  sang enqueue `RUN_CHECKS` job (WS2 chốt check chạy async). Là refactor khi làm WS2.
- **WS1 gap:** parser CHƯA đọc vị trí cột từ saved-map (edit-override chỉ đánh officer-confirmed, chưa
  rewire parse); `run_checks(only=)` xoá COMBO tới lần chạy full.
- **Demo:** deploy `db-data/audit_hq_demo.sqlite` lên `audit-hq-demo.tinsu.ai` (+ kiểm `user_companies`/
  login demo); 004 phân tích lại cách trình bày 2 chế độ (label-merge giữ 187 / tách / view riêng).
- **Grill WS3** (session/worktree riêng) song song WS2-impl — tham chiếu brief WS3 + ADR #18 (bản WS2
  revise) + GLOSSARY + `2026-07-24-grill-ws2.md`.
