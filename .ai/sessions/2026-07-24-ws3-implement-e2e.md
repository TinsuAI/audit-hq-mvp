# Session 2026-07-24 — WS3 implement + e2e proof + WS1 review-preview

`/implement chạy hết cái WS3` → cài trọn ADR #18 Rev WS3, rồi 2 việc phát sinh theo yêu cầu
owner: (a) test e2e + chụp ảnh WS1→WS3; (b) nhúng preview file vào màn xác nhận cột.
Branch `feat/ws3-overview-staleness` (từ `main`=`7a8d4b6`). 3 commit, **CHƯA push/PR/deploy**.

## What Was Done

**WS3 (commit `89d62c9`) — ADR #18 Rev WS3, 3 ticket:**
- *Foundation:* `CheckRun` (`app/models/check_run.py`) + cột `data_version` trên `CompanyPeriod`
  (migration `a7b8c9d0e1f2`, down từ `b7d2e1f4a3c6`). `run_checks()` đọc `data_version` ở đầu run
  (helper `current_data_version` ở `app/pipeline/period.py`), upsert 1 dòng `check_runs` mỗi
  `(company, năm, mã)` cho MỌI check kể cả 0 finding, dọn orphan `X.*` khi full run. `ingest()` bump
  `data_version` trong transaction (skip `dry_run`).
- *Overview:* `CheckOverview` (migration `b8c9d0e1f2a3`) + `app/ai/overview.py`
  (`build_overview_aggregate` đếm+top-N, `overview_is_stale`, `generate_check_overview`,
  `load_overviews_with_staleness`). Route `POST /companies/{code}/overview` = **`def` thuần** (threadpool,
  không job worker), guard rate-limit/budget, đọc snapshot → gọi LLM → ghi SAU. Audit action
  `ACTION_AI_OVERVIEW`.
- *UI:* panel overview ở `group-actions` (`company_detail.html`) + badge "Tổng quan đã cũ" + mốc
  `based_on` + nút "Tạo lại"/"Tạo tổng quan"; flash banner; `company_detail` route nạp overviews +
  tính stale.
- *TDD:* `tests/test_ws3_foundation.py` (9) + `tests/test_ws3_overview.py` (11). 670 test pass (650→670),
  ruff sạch, 2 migration up/down sạch.
- *Review 2 trục* (Standards + Spec, subagent song song) → áp: thêm mốc `based_on` ở panel stale
  (ADR §4, Spec bắt), xoá call chết `cache_supports_anthropic`, tách helper `current_data_version`
  (Standards: lặp 3 nơi), dọn test dead-code. GIỮ `top_titles` (Spec gọi scope-creep nhưng vẫn
  aggregate, để tóm tắt nói được CÁI GÌ sai — lệch spec có chủ ý).

**E2E proof (commit `1e85056`):**
- Server throwaway `:8323` (`DATABASE_URL`/`RAW_DATA_PATH` env → DB + raw riêng, setsid + kill theo PID)
  trên DN giả `DN_E2E` (tên/MST giả → an toàn commit). Luồng HTTP THẬT: upload M15 chuẩn (2025→verified)
  + M15 đổi tên cột 9 (2024→needs_review gate) → run checks (C2.1×3, C2.3×1, 17 check_runs) →
  sinh overview (LLM thật deepseek/OpenRouter, $0.0013) → re-run C2.3 → stale.
- 6 screenshot + `ui_smoke.py` ở `.ai/features/2026-07-24-parse-review-per-test-ux/screenshots/`.

**WS1 review-preview (commit `51521f9`):**
- Nhúng grid nội dung file (15 dòng đầu) vào màn `document_review.html`, tag mỗi cột grid theo field
  đã map (khớp tiêu đề = xanh, needs_review = vàng ⚠️) + JS live-highlight cột khi focus/sửa chỉ số.
- Refactor `_extract_sheet_preview()` ở `companies.py` — dùng chung route preview + review.

**Artifact:** gallery 6 ảnh publish private (claude.ai/code/artifact) để owner xem.

## Decisions Made

- **Endpoint overview = `def` thuần, KHÔNG `async`, KHÔNG job worker** (ADR): sync client chặn event loop
  nếu `async`; job worker 1-thread bị chặn nếu qua queue. Đọc snapshot + gọi LLM + ghi trong request.
- **Stale = `ran_at` dời HOẶC `data_version` dời**: chỉ `ran_at` mù đường re-ingest trần
  (`documents_ingest_year`). Đã verify 3/3 caller ingest non-dry-run bump version.
- **`based_on_data_version` = CompanyPeriod hiện tại lúc sinh** (semantics "since generation"), so với
  version hiện tại lúc xem. `based_on_run_at` = `check_runs.ran_at` của check đó.
- **Prompt nạp `top_titles` (ngoài `subject_key`)**: bounded top-N, vẫn "KHÔNG nạp dòng"; đánh đổi lệch
  spec để overview mô tả được nội dung sai, phục vụ "không hộp-đen". Ghi rõ ở memory để owner revert nếu muốn.
- **E2E + ảnh trên DN GIẢ** (không PILOT thật): local DB có tên/MST THẬT (blocker banner) → chụp DN thật
  = lộ dữ liệu khách. Synthetic vẫn chạy đúng mọi code path → an toàn commit.
- **Preview NHÚNG (không link riêng)**: bảng chỉ-số-không thì cán bộ không biết cột 8 là gì; grid + tag +
  live-highlight nối chỉ số ↔ nội dung file thật.

## What Didn't Work

- **Mở tất cả `<details>` khi chụp trang Tài liệu** → bung luôn dropdown nav (đè góc phải). Sửa: target
  `details.doc-year` thôi.
- **Chạy lại full `ui_smoke.py` trên DB cũ để re-shoot** → nút "Tạo tổng quan" biến mất vì C2.1 đã có
  overview (chỉ hiện khi `code not in overviews`). Re-shoot lẻ hoặc chạy trên DB fresh.
- (Loại từ design, không thử lại — xem ADR #18 Rev WS3): backfill `check_runs` từ `computed_at`
  (mốc first-run); append-history; auto-run khi ingest; eager overview; `not_evaluable` (Tầng C chờ họp).

## Open Items

- **Push branch → PR → merge → deploy** (chưa làm). CI self-hosted `tinsu-prod`: test+lint+deploy +
  `alembic upgrade head` (sẽ áp `a7b8c9d0e1f2` + `b8c9d0e1f2a3` lên prod). Prod đang `main`=`6f052d3`.
- **`uv.lock`** vẫn untracked (để nguyên như các session trước).
- **`top_titles`**: owner có thể muốn revert về đúng spec (chỉ `subject_key`) — chờ quyết.
- **Grid preview** hiện 15 dòng đầu; DN synthetic có 8 dòng trắng đầu nên nhìn hơi trống — dữ liệu thật
  có block tiêu đề/tên DN ở đó nên OK. Cân nhắc bắt đầu gần dòng header nếu muốn gọn hơn.
- **Đường chưa phủ (ghi chú)**: sửa alias UOM (`admin.py`) đổi chuẩn hoá mà không ingest/run → không tín
  hiệu stale (hiếm, chỉ admin).
