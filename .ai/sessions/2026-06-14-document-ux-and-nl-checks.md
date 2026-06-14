# 2026-06-14 — Document UX + NL check authoring (SQL/Python) + test_connection fix

> Phiên dài: redesign UX tạo DN/quản lý tài liệu (Task 1), **thay hẳn DSL gen-check bằng
> SQL/Python soạn từ NL theo phương pháp BCQT-System** (Task 2), sửa `test_connection`,
> đảo key AI live về local. 4 commit `3319bca→ca387cb` đã merge `main` + push + **deploy
> live xanh** (`build_sha=ca387cb`). 492 test pass, ruff sạch.

## What Was Done

### Task 1 — Tạo DN + quản lý tài liệu (`feat(companies)` 6a28cb2)
- **Mã DN tự sinh `DN_NNN`** (`_next_company_code`), bỏ khỏi form tạo. Form chỉ còn Tên
  (bắt buộc) + MST + Ngành + Địa chỉ. (User: "có tên + MST rồi cần mã làm gì cho phức tạp".)
- **Bảng `DataFile`** (`app/models/data_file.py`) + migration `f2b3c4d5e6a7` — registry mỗi
  file BCQT (slot/năm/tên/size/uploaded_by/parse_status/row_count). Helper
  `app/pipeline/data_files.py`: `sync_data_files` (quét fs ↔ registry, prune file đã xoá),
  `record_parse_result` (ghi trạng thái parse + số dòng sau ingest), `files_by_year_slot`.
- **Trang `/companies/{code}/documents`** viết lại thành **accordion theo năm** (năm mới nhất
  mở sẵn). Mỗi năm có **1 nhãn trạng thái duy nhất** (`_doc_year_status`): "Đã nạp · N dòng" /
  "Có file · chưa nạp" / "Đã nạp trước đó · file gốc không còn lưu" / "Chưa có dữ liệu" — hết
  mâu thuẫn "đã nạp nhưng chưa có file". File hiện dạng **dòng nhẹ** (không còn ô lớn) + nút
  ↓/🗑/Thay/Thêm. Endpoint: upload-cell, delete, download, ingest-year.
- **Chọn năm = dropdown** (`_year_options`, năm gần đây) thay number-spinner; "Thêm năm" =
  dropdown (`?add=YYYY` mở mục năm trống để upload).
- `_save_upload` sửa slot-aware (glob cũ `M15*` xoá nhầm `M15a*`).

### Task 2 — Soạn check từ NL bằng SQL/Python (`feat(checks)` 3319bca)
- **BỎ HẲN DSL 5-kind** (`dynamic_runner.py` đã xoá). Thay bằng **SQL/Python tự do** (user chốt).
- `app/checks/sql_runner.py` — chạy check read-only → `Finding`. An toàn: deny-list SELECT,
  restricted Python builtins, **chạy SELECT trong SAVEPOINT** (`select_in_savepoint`) để lỗi
  không đầu độc session. Tự dựng `evidence_refs` về Tầng 1 từ `subject_table`+`subject_col`
  (giữ truy nguồn, không hộp đen).
- `app/checks/spec_gen.py` viết lại thành **agentic tool-loop** (port BCQT): tool
  get_table_schema / get_distinct_values / try_sql / lookup_glossary / submit_final_answer +
  tool budget + **dry-run thật trên DN tham chiếu** + **oracle retry** (phản hồi lỗi gắn nhãn)
  + **self_review** (confidence/alternative_interpretation/edge_cases) + **plan** + **dynamic
  few-shot** (Jaccard trên nl_prompt check đã lưu). Dùng `model_deep`, không fallback.
- `CheckDefinition` thêm cột (migration `a3c4d5e6f7b8`): scope / subject_table / subject_col /
  sql_snippet / detail_query / code_snippet / nl_prompt / analysis / plan / self_review.
  `kind` giờ là 'sql'|'python'.
- **Scoring**: `compute_company_year_score(... rule_scope=)` + `extended_rule_scope(session)`
  (built-in RULE_SCOPE + scope của check đã publish) → check tự do vào cả mẫu số lẫn `max_raw`.
  Wire `run_checks.py` (dispatch sql/python, try/except mỗi check) + `recompute.py`.
- UX: `/admin/checks/new` (prompt + chips + picker DN/năm + spinner) → POST `/draft` (loop, đồng
  bộ) → `admin_checks_preview.html` (banner "Bạn yêu cầu → Hệ thống hiểu" + self-review + dòng
  nguồn khớp + phát hiện mẫu + code) → Lưu nháp. Detail page hiện nl_prompt/self_review/plan/SQL.

### test_connection fix (`fix(ai)` ca387cb)
- `GET /models` của OpenRouter là **PUBLIC** → `test_connection` cũ báo OK GIẢ kể cả key chết.
  Thêm cờ `verify_auth=True` (mặc định, nút "Test kết nối"): gọi **1 completion 1-token** xác
  thực key thật (key chết → ok=False + hint 401). `available_models()` dùng `verify_auth=False`
  (chỉ lấy danh sách model, nhanh, không tốn token).

### Key AI (đảo về local)
- Key OpenRouter local cũ (`sk-or-v1-aca…11fa`) đã **chết** (401 "User not found", KHÁC 402).
  Kéo key từ bản live tinsu (`sk-or-v1-8…b629`) set vào `ai_settings` local (user cho phép) →
  AI chat + soạn check chạy live OK (đã test sinh check thật).

### Tests
- Xoá `test_runner.py` (DSL). Thêm `test_data_files/`, `test_sql_runner.py`; viết lại
  `test_spec_gen.py` (mock loop), `test_admin_checks.py`, `test_pipeline_integration.py`.
  `test_model.py` + `test_registry_merge.py` giữ (chỉ test model/merge, vẫn đúng).
- **Lưu ý:** một số file trong `tests/test_dynamic_checks/` (đặc biệt `test_spec_gen.py`,
  `test_admin_checks.py`) bị hệ thống ghi nhận "modified by user/linter" về **bản DSL cũ** —
  NHƯNG đó là do `git checkout main` lúc merge tạm đảo cây làm việc; bản đã COMMIT
  (3319bca/ca387cb) là bản mới. Working tree hiện = main = bản mới, sạch.

## Decisions Made
- **Thay hẳn DSL bằng SQL/Python** (user chốt qua AskUserQuestion). Rủi ro cao hơn nhưng port
  được toàn bộ phương pháp BCQT làm AI tốt hơn. DB chưa có CheckDefinition nào → không migrate.
- **Mã DN tự sinh** thay vì dùng MST (MST trống/sửa/trùng chi nhánh + phải migrate DN demo).
- **Tài liệu = accordion theo năm** (thay vì bảng matrix / thẻ lớn) → ít ô, hết mâu thuẫn nhãn.
- **SAVEPOINT** cho SELECT người dùng (BCQT dùng RO-handle file; ở đây session in-memory test
  không có file nên dùng begin_nested — đồng nhất + 1 check lỗi không hỏng cả run).
- **Authoring đồng bộ** (spinner), không async drafts (tránh thêm bảng/polling).
- User **không thích bị hỏi menu** cho quyết định rõ ("recommend đi") → đã ghi memory.

## What Didn't Work / Gotchas
- **Session poisoning:** SQL người dùng lỗi qua `session.execute` làm hỏng transaction
  (PendingRollbackError ở dry-run/check sau). Fix = SAVEPOINT.
- **draft-overlay luôn hiện:** `.draft-overlay { display:flex }` đè `[hidden]` (cùng
  specificity, source-order thắng). Fix = `.draft-overlay[hidden]{display:none}`.
- **Mock test reset index:** `make_client` lambda tạo fake mới mỗi attempt → luôn trả payload
  đầu. Fix = 1 instance.
- **`test_connection` báo OK giả** (xem trên).
- **Dev server nền bị thu hồi** giữa các lượt (shutdown sạch, không crash).
- **DB local = mirror prod (DN_001..004) nhưng `data/` symlink trỏ tên thật** → DN demo không
  có file local; test upload bằng DN throwaway.

## Open Items
- **Combo +20 điểm tổ hợp** — review logic (carry từ STATUS cũ, user "quyết sau"): flat +20 mọi
  combo, magnitude tuỳ tiện. Cân nhắc badge-không-điểm / có-trần / trọng số.
- **Dữ liệu test còn trong DB local:** `ZZ_DEMO` (DN throwaway có file 2024+2023) + check nháp
  `X.1` ("Tồn cuối kỳ NVL âm"). User chưa quyết xoá/giữ. (Chỉ local, không lên prod.)
- **Nhánh `feat/document-ux-and-nl-check-authoring`** còn local (đã merge `main`) — xoá nếu cần.
- `test_connection(verify_auth=True)` giờ tốn 1 completion 1-token mỗi lần bấm "Test kết nối"
  (chủ ý, để báo đúng).
- Disk tinsu (carry cũ): ~97%, theo dõi khi deploy lâu dài.
