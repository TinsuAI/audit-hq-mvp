# Session 2026-07-24 — WS2 implement (4 slice) + modal UX chọn test

Tiếp branch `feat/ws1-parse-review`. Input: **ADR #18 Revision — WS2** (đã grill trước đó,
`a47b9af`). Yêu cầu mở: "tự động /implement hết đi" → cài trọn WS2; sau đó owner phản hồi UX
chọn test → làm lại thành modal, gọi `/frontend-design` (skill Anthropic).

## What Was Done

### WS2 — 4 slice (ADR #18 Rev WS2)
1. **Nền** (`5c22a5a`): `RUN_CHECKS` payload nhận `only: list[str]`; `run_checks(only=)` chạy tập
   con. Combo **recompute MỌI lần chạy** (lẻ/full) đọc TOÀN finding-set của (DN,năm), gate
   `get_combos_enabled()` (`app_settings`, **default OFF**); delete `COMBO_*` giữ vô điều kiện.
   `run_checks_handler` chuyển `only` xuống pipeline.
2. **Chạy test lẻ** (`ecb16c4`): nút mỗi nhóm check + route `rerun_checks` nhận `check: list[str]`
   → `RUN_CHECKS {only, year}` → `/jobs/{id}`.
3. **Export chọn** (`ecb16c4`): `build_export(only=)` lọc `check_code.in_(only)`; `/export?check=`
   lặp; sheet Tổng quan liệt kê mã đã chọn (không hộp đen). Không chọn = xuất tất cả.
4. **`documents_confirm_review` async** (`ecb16c4`, option A): save-map + re-ingest GIỮ đồng bộ
   (file→`parsed`); re-run scoped **enqueue** `RUN_CHECKS {only: affected}` → `/jobs/{id}` khi
   re-confirm; confirm lần đầu vẫn về `/documents`. Ẩn combo ở `company_detail` khi OFF (gate setting
   sống). Toggle admin combo = card đầu trang `/admin/checks` + POST `/admin/checks/combos-toggle`.

### Modal UX chọn test (owner phản hồi "xấu, checkbox nhỏ, sao 2 cột")
- Bỏ panel `<details>` inline → **2 `<dialog>` native** (`054e9cd`): "Chọn test chạy" (toàn danh
  mục) + "Xuất Excel kiến nghị" (mã có finding). JS thuần: mở/đóng, chọn-tất-cả/bỏ-chọn, click nền.
- **A11y qua Web Interface Guidelines** (`e9055e3`): `overscroll-behavior: contain`, `:focus-visible`
  trên nút tuỳ biến, `touch-action: manipulation`, `aria-labelledby` cho dialog.
- **Thiết kế lại thành hàng 1 cột** (`5ad7f71`, theo `/frontend-design` Anthropic): mỗi test là hàng
  bấm-cả-hàng, checkbox 18px accent navy, mã = badge mono, số phát hiện = pill; hàng chọn tô nền
  navy + viền trái; footer đếm sống + nút tự mô tả ("Chạy 3 test" / "Chạy tất cả").
- **Gom theo họ C1/C2/…** (`ad4fcc0`): `_group_options_by_family()` suy họ từ mã + tra `GROUP_NAMES`
  (§4 đề án); tiêu đề nhóm "C1 · Số lượng nhập / xuất" **sticky** khi cuộn; COMBO_*/X.* gom nhóm cuối.

### Review + fix
- Chạy critic (fork) đối chiếu ADR → bắt **Defect 1**: pre-delete của `run_checks(only=)` chỉ tính
  `only & ALL_CHECKS` → chạy lẻ 1 check mở rộng `X.*` KHÔNG xoá finding cũ → **nhân đôi**. Sửa: tập
  wipe = (built-in ∪ dynamic đã công bố) ∩ `only`, load dynamic_defs TRƯỚC khi delete. Regression
  test thêm ở `test_pipeline_integration.py`.
- Chạy `/frontend-design` + `web-design-guidelines` (WIG) cho modal → 5 điểm a11y nhỏ đã sửa.

## Decisions Made
- **Defect 2 KHÔNG sửa** (`scoring.max_raw` giữ `+COMBO_BONUS` khi combo OFF → trần điểm ~889): ADR
  chốt "Scoring KHÔNG đổi", tính chất có sẵn từ TRƯỚC WS2, đổi sẽ dịch điểm toàn demo. Chỉ ghi nhận.
- **Fallback inline** trong `confirm_review` khi `ur is None` (gần như không xảy ra vì `require_user`)
  — giữ để không bỏ sót re-run; không vi phạm tinh thần "async" vì là nhánh chết.
- **Commit trên chính branch WS1** (`feat/ws1-parse-review`) vì WS2 = "ADR #18 Revision" nối tiếp WS1,
  WS1 chưa merge. Chưa push (chờ owner).
- **Vị trí toggle combo**: card đầu trang `/admin/checks` (ADR để owner xác nhận — chọn mặc định này).

## What Didn't Work (đừng lặp)
- Panel `<details>` + grid 2 cột checkbox nhỏ: owner chê xấu/khó bấm. → hàng 1 cột bấm-cả-hàng.
- Assert combo fire qua `run_checks` full trong test: full run xoá seeded C2.3/C4.3 rồi tính lại từ
  data (chỉ C2.3 fire) → dùng 2 lần chạy lẻ liên tiếp để chứng minh "dựng lại không mất".

## Open Items
- **CHƯA push/merge** WS1+WS2 (branch `feat/ws1-parse-review`). Chờ owner.
- **Harness chưa chạy lại**: combo default OFF → full-run bỏ meta-finding COMBO_* so với mốc 417
  (delta CÓ CHỦ Ý). Test suite 650 pass là cổng xác nhận phiên này.
- **WS3** đã grill xong (ADR #18 Rev WS3, session khác `694fb3b`) — chưa code. Nền `check_runs`
  ĐỘC LẬP WS2 → implement được song song.
- Screenshot modal (rỗng/list/đã-chọn/gom-nhóm) ở scratchpad — KHÔNG commit (đúng convention scratch).

## Verify
- `650 passed`, ruff sạch, KHÔNG migration (`combos_enabled` = 1 row `app_settings`).
- 5 file test WS2 mới + sửa `test_review_rerun.py` (async drain job) + `test_pipeline_integration.py`
  (regression Defect 1).
