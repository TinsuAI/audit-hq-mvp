# STATUS — Audit-HQ MVP

> **Trạng thái (2026-07-25 — NẠP 004 HAI SỔ (ẩn danh) LÊN PROD + 2SỔ đã MERGE+DEPLOY — main=`1eea393`):**
> **PR #23** (2SỔ UI+ingest, branch A+B) + **PR #24** ("Chung"→"Liên sổ") đã merge vào `main`, CI test+deploy XANH.
> Prod `audit-hq-demo.tinsu.ai` chạy **`1eea393`**, migration head **`d0e1f2a3b4c5`** (đã áp cột `data_files.book`).
> **Nạp 004 lên prod (CHỈ THAO TÁC DỮ LIỆU, build_sha KHÔNG đổi):** prod giờ **3 pháp nhân** — PILOT_002 (id7),
> PILOT_006 (id8), **PILOT_004 (id9, HAI SỔ)**. 004 = Sổ EPE 98 mã·34 pđ · Sổ GC 37 mã·0 pđ · Liên sổ 40 pđ
> (tổng 74). Tổng finding prod = **14.998**.
> **Ẩn danh §6.2 (verify 0 rò):** MST `0901051747`→`6944313927`; tên→"Công ty TNHH Chế Xuất & Gia Công Thí Điểm";
> 23 partner thật→`NCC_*`; GIỮ book tags + tên material/product. Quét TOÀN DB + `/showcase` (công khai): **0** hit
> MST/partner/tên thật. `evidence_refs` giữ `company_id=9` (id 9 trống trên prod) nên resolve đúng; bảng con
> DROP id → autoincrement mới, KHÔNG đụng id 002/006.
> **Cơ chế (2 stage, xem `$CLAUDE_JOB_DIR/tmp/prodload/build_004.py` — script throwaway, KHÔNG commit):**
> Stage 1 = snapshot WAL-safe dev DB (`.backup()`, KHÔNG đụng :8200) + snapshot prod → merge 004 ẩn danh vào bản
> copy prod → verify local (0 rò, UI hai sổ render). Stage 2 = online-backup prod (rollback) + giữ raw gốc →
> `docker stop`/thay file/`start` → `alembic upgrade head` (no-op) → verify.
> **Rollback (trên server `db-data/`):** `audit_hq.sqlite.bak-pre-004-load-20260725-152615` (online) +
> `audit_hq.sqlite.raw-pre-004-load-20260725-152615` (raw gốc). Restore = docker stop → cp bak→.sqlite → rm -wal/-shm → start.
> **LƯU Ý:** prod DB-ONLY (không file nguồn) → trang Tài liệu + selector review (branch B) của 004 TRỐNG; branch A
> (strip/lọc/Liên sổ) chạy đủ. `check_runs` prod trống → staleness forward-only. E2E proof 2SỔ: `.ai/features/
> 2026-07-25-2so-ui-ingest/` (nhãn "Liên sổ"). Prod screenshot 004 (đăng nhập) CHƯA chụp (tránh seed user prod).
> **Next:** — (không việc treo). Muốn xem UI hai sổ đăng nhập trên prod: seed admin throwaway (create_user) rồi purge.

> **Trạng thái (2026-07-25 — UI + INGEST THEO SỔ: cài trọn 5 ticket 2SỔ (branch A+B), ĐÃ MERGE PR #23/#24 + DEPLOY):**
> Cài hết 5 ticket GitHub #18/#20/#21/#19/#22 (2SỔ-1..5) theo **ADR #19 Revision — UI + upload**, test-first.
> **5 commit mới** (từ `8b88996`): `8937118` docs ADR/glossary · `95f23eb` branch A · `148bd3d` branch B ingest ·
> `250ee5f` branch B selector · (+1 commit review-fixes sắp tạo). **Full suite XANH**, ruff sạch.
> **Branch A (hiển thị+lọc, `95f23eb`):** `app/books.py` = `company_books`/`is_multi_book` (gate ≥2 sổ từ
> nvl∪sp∪norms, KHÔNG suy từ finding) · `book_label` (EPE/GC known-map, null→"Chung (liên sổ)") · `book_summary`
> (strip mã NVL + phát hiện mỗi sổ + Chung, loại COMBO_). `company_detail`: strip header, dòng split per-check
> `Sổ: EPE 8 · Chung 2`, pill book mỗi finding, segmented `?book=` (chung→`Finding.book IS NULL`), empty-state sổ
> sạch. **View-filter thuần:** điểm năm/strip/export/run GIỮ toàn pháp nhân; `checks_run` full-entity (không lật
> khi lọc sổ sạch). `finding_detail`: field "Sổ quyết toán". Một sổ (002/006) → book=NULL → KHÔNG chrome.
> **Branch B (upload+ingest):** migration **`d0e1f2a3b4c5`** cột `data_files.book` (down `c9d0e1f2a3b4`, head giờ
> `d0e1f2a3b4c5`). `ingest._plan_settlement_files`: đọc book per settlement file từ `data_files`, gom theo sổ,
> parse từng file, tag rows; không tag (CLI/script) → book=NULL → 002/006+script KHÔNG đổi; tờ khai ghi MỘT lần.
> **RETIRE `_guard_single_book`** (re-ingest nhiều sổ full-reprocess không mất sổ). Selector chọn sổ ở review WS1
> (`document_review.html` + confirm handler): chỉ slot settlement, datalist `company_books()`+EPE/GC, normalize
> trim/upper, ghi `data_files.book`; đổi sổ trên file đã parsed → re-run TOÀN BỘ năm.
> **Test:** +28 test mới (test_books/book_findings_ui/book_filter/ingest_book/book_selector), bỏ test_ingest_guard.
> E2E 2 sổ qua endpoint thật → branch A hiện strip 2 sổ.
> **Code-review 2 trục (Standards+Spec):** SỬA 1 lỗi thực — empty-state "đã được đánh giá" thiếu guard
> `checks_run` (nhiều sổ nạp nhưng CHƯA chạy → lọc sổ báo nhầm đánh giá-sạch); nay `checks_run` → tách nhánh
> "chưa chạy kiểm tra". Cleanup: hằng `SETTLEMENT_SLOTS`, import `normalize_book` top-level, datalist EPE/GC từ
> `BOOK_LABELS`. **Còn (ghi chú, ngoài scope):** multi-book UPLOAD đầy đủ chưa xong — `record_parse_result` áp
> MỘT provenance/slot → `parse_detail`/`row_count` per-file chưa đúng khi nhiều file cùng slot (balances vẫn
> đúng, chỉ số hiển thị per-file undercount); analyze-per-file là việc "B-plus" lớn hơn.
> **ĐÃ SHIP:** PR #23 (2SỔ, merge `9d90d3d`) + PR #24 ("Liên sổ", merge `1eea393`) merge+deploy XANH; prod áp
> `d0e1f2a3b4c5`; 004 hai sổ ẩn danh đã nạp prod (xem block trên cùng). `uv.lock` untracked.
> Session log: `.ai/sessions/2026-07-25-2so-ui-ingest.md`.

> **Trạng thái (2026-07-25 — 004 HAI LOẠI HÌNH: fix 6 check + cột `book` + collapse + trim DB LOCAL còn 3 pilot — CHƯA commit, PROD chưa đụng):**
> **ADR #19:** 004 (MST `0901051747`) là **1 DNCX có 2 SỔ QUYẾT TOÁN** khác loại hình (sổ tự sở hữu "EPE"
> + gia công "GC"), KHÔNG phải 2 chế độ. Tờ khai 1 list DNCX (E11/E15/E42) **dùng chung, nhân đôi** 2 row.
> Cũ: **C1.2=99, 91 GIẢ** (mã thuộc sổ kia bị báo "thiếu M15"). Từ đúng = "loại hình" (khớp enum
> `CompanyType`) KHÔNG "chế độ".
> **Code (test-first, 680 pass):** cột nullable `book` trên nvl/sp/norms/findings — migration
> `c9d0e1f2a3b4` (down `b8c9d0e1f2a3`). **C1.1/C1.4 gộp `(mã,đơn vị)`** (không cộng MTR+ROLL); **C4.1/C4.3/
> C6.1 `GROUP BY book`**; **C3.3** đơn vị per-`(book,mã)`; 8 check row-wise gắn `book`+evidence filter. Guard
> `_guard_single_book` chặn re-ingest pháp nhân nhiều sổ. **book=NULL = pháp nhân 1 sổ → 002/006 KHÔNG đổi**
> (re-run identical, verified).
> **DB LOCAL đã đổi (KHÔNG phải prod):** collapse 004 (id9 EPE + id10 GC → 1 row `PILOT_004`/`DEMO_004`,
> dedup tờ khai) → **C1.2 99→4, tổng 187→74, risk 30**. Trim còn **3 pilot**: PILOT_002 (48), PILOT_006
> (14876), PILOT_004 (74); xoá DN_001–005/ZZ_DEMO/DN_GATE + FK. Backup: `bak-pre-004-collapse-20260725-020819`
> + `bak-pre-trim-3pilots-20260725-023941` (+`-wal`/`-shm`; restore = cp đè).
> **Sửa DRIFT DB local:** local ở alembic `f5a6b7c8d9e0`, THIẾU `company_periods.data_version` (model bắt
> buộc) + `book` → `run_checks` CHẾT + server :8200 (`--reload` nạp model mới) 500 trên trang settlement/
> findings. Sửa bằng **ALTER trực tiếp** (`alembic upgrade` FAIL vì `check_runs` đã tồn tại). Server OK lại.
> Memory `local-db-schema-drift`.
> **Next:** (1) **commit** 004 work (16 M + feature dir + migration + guard + tests + ADR#19/GLOSSARY;
> `uv.lock` untracked); (2) prod ở `b8c9d0e1f2a3` = down_rev của migration mới → `alembic upgrade head` prod
> áp `c9d0e1f2a3b4` SẠCH (prod không drift); prod hiện chỉ 002/006, muốn có 004 thì collapse trên prod;
> (3) **UI 2 sổ: GRILL XONG (2026-07-25)** — design CHỐT ở **ADR #19 Revision — UI + upload**, CHƯA code.
> Hai nhánh: **A hiển thị+lọc** (split per-check + strip header `mã NVL·phát hiện` + segmented `Tất cả·EPE·
> GC·Chung` + pill row + finding_detail; `book`=null multi-book = "Chung liên sổ", KHÔNG gộp vào sổ khi lọc;
> gate `company_books()` ≥2 book từ nvl/sp/norms) — chạy trên data 004 ĐÃ gắn book, ship một mình. **B
> upload+ingest** (cột `data_files.book` + selector review WS1 + ingest đọc book per-file, full reprocess,
> RETIRE `_guard_single_book`, tờ khai ghi 1 lần). **Build A trước, B sau.** Glossary + ADR đã ghi.
> E2E proof/brief: `.ai/features/2026-07-25-004-two-loai-hinh/`. Session log `.ai/sessions/2026-07-25-004-two-loai-hinh.md`.

> **Trạng thái (2026-07-24 — LOAD PILOT 002/006 LÊN PROD (thay toàn bộ DN cũ) — main=`fe6efb9`, chỉ thao tác DỮ LIỆU):**
> Nạp pilot 002+006 (ẩn danh) lên prod, XOÁ 14 DN cũ. **DB-ONLY, KHÔNG đổi code** (build_sha vẫn `fe6efb9`).
> Prod DB giờ: **chỉ PILOT_002 (48 finding, điểm 7/2025) + PILOT_006 (14.883 finding, điểm 129/2024)** = 14.931 finding.
> Ẩn danh theo §6.2 (helper `anonymize.py`): tên tổng hợp "(Demo)", MST giả (hash `_deterministic_mst`), địa chỉ/slug
> tổng hợp, **179 partner→`NCC_*`**. Verify live: 0 MST thật, 0 partner thật, `/showcase` (công khai) không lộ tên/MST.
> **GIỮ:** 2 user prod + 27 ai_settings (AI bật + api_key) + app_settings + uom + check_definitions.
> **XOÁ kèm:** jobs, user_companies, ai_conversations/messages, access_events (log về DN đã gỡ, có thể chứa tên thật).
> **Backup prod TRƯỚC swap:** `db-data/audit_hq.sqlite.bak-pre-pilot-load-20260724-230046` (rollback = swap lại + restart).
> Cơ chế: snapshot WAL-safe prod (`src.backup()`) → build target local (empty tables DN cũ + copy 002/006 GIỮ id 7,8
> để evidence_refs còn đúng + anonymize) → scp → `docker stop`/replace file/`start` → `alembic upgrade head` no-op → verify.
> **LƯU Ý cho phiên sau:** (1) **DB-only** → trang Tài liệu/preview/download TRỐNG cho 002/006 (WS1 file-view KHÔNG
> demo được trên prod; muốn có thì phải ẩn danh nội dung file Excel rồi upload). (2) **`check_runs` prod TRỐNG** (không
> import run-history) → overview WS3 SINH được (đọc finding) nhưng staleness forward-only tới khi có người chạy check;
> **CỐ Ý KHÔNG re-run trên prod** (finding import là bản pilot đã verify — re-run rủi ro méo do combo OFF/C4.3 basis…).
> (3) Ẩn danh §6.2 GIỮ số tờ khai/hoá đơn/ngày + tên material/product — muốn scrub thêm là quyết định riêng.
> (4) **disk server 99% (4.2G trống)** — DB 290M vừa đủ; nên dọn backup cũ `bak-pre-c24`/`bak-pre-cleanup` (June, ~26M mỗi cái).
> Login prod: admin password chưa biết (như local) — kiểm authenticated bằng user throwaway nếu cần.

> **Trạng thái (2026-07-24 — WS3 MERGE + DEPLOY PROD (PR #17) — main=`fe6efb9`):**
> PR #17 (`feat/ws3-overview-staleness`→`main`) merge commit **`fe6efb9`**; CI run `30100248644` test+deploy XANH;
> prod `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=fe6efb9` khớp (build_time 14:18:49Z). Deploy áp 2 migration
> WS3 lên prod qua `alembic upgrade head`: `a7b8c9d0e1f2` (check_runs + data_version) + `b8c9d0e1f2a3` (check_overviews).
> **Migration head prod giờ `b8c9d0e1f2a3`.** **Lưu ý:** prod KHÔNG có pilot 002/004 hay DN synthetic → UI overview/
> staleness WS3 chưa có finding để thao tác tới khi nạp data lên prod. Chi tiết cài đặt: block ngay dưới + session log
> `.ai/sessions/2026-07-24-ws3-implement-e2e.md`. **Next:** nạp/reload data lên prod nếu muốn demo WS3 sống. `uv.lock` untracked.

> **Trạng thái (2026-07-24 — WS3 CÀI TRỌN + e2e proof + WS1 review-preview — branch `feat/ws3-overview-staleness`, CHƯA push):**
> Cài trọn **ADR #18 Rev WS3** (3 ticket) + 2 việc phát sinh. 3 commit: `89d62c9` WS3 · `1e85056` e2e proof ·
> `51521f9` WS1 review-preview. **670 test pass** (650→670, +20 WS3 TDD), ruff sạch, 2 migration up/down sạch.
> (1) **WS3:** `check_runs` latest-upsert 1 dòng/(DN,năm,mã) ghi TRONG `run_checks()` cho mọi check kể cả 0 finding +
> dọn orphan `X.*`; `data_version` số nguyên trên `CompanyPeriod` bump mỗi `ingest()` trong transaction (helper
> `current_data_version` ở `period.py`, đọc ở đầu run). `check_overviews` overwrite-upsert + telemetry
> (model/tokens/cost/latency), sinh on-demand qua endpoint **`def generate_overview`** (KHÔNG `async`, KHÔNG job
> worker — đọc snapshot → LLM → ghi SAU); UI panel ở group-actions + badge stale + mốc `based_on` + nút Tạo lại;
> flag-only KHÔNG auto-regen. Stale ⇔ `check_runs.ran_at` dời HOẶC `CompanyPeriod.data_version` dời. Migration head
> giờ **`b8c9d0e1f2a3`** (`a7b8c9d0e1f2` foundation → `b8c9d0e1f2a3` overview, down từ `b7d2e1f4a3c6`). Prompt nạp
> THÊM `top_titles` (aggregate, KHÔNG nạp dòng) ngoài `subject_key` — lệch spec CÓ CHỦ Ý (để tóm tắt nói CÁI GÌ sai).
> Review 2 trục (Standards+Spec) → sửa: thêm mốc `based_on` ở panel stale (ADR §4), xoá call chết
> `cache_supports_anthropic`, tách helper `current_data_version` (3 nơi), dọn test dead-code.
> (2) **E2E proof:** server throwaway (DN giả `DN_E2E`, KHÔNG đụng DB thật/:8200) chạy luồng HTTP THẬT
> upload→parse(verified+gate)→run(C2.1×3,C2.3×1,17 check_runs)→overview(LLM thật deepseek/OpenRouter)→re-run/stale;
> 6 screenshot + `ui_smoke.py` ở `.ai/features/2026-07-24-parse-review-per-test-ux/`.
> (3) **WS1 review-preview:** nhúng grid nội dung file vào màn xác nhận cột, tag field mỗi cột (khớp tiêu đề=xanh,
> needs_review=vàng) + live-highlight cột khi sửa chỉ số; refactor `_extract_sheet_preview` dùng chung preview+review.
> **Next:** push branch → PR → merge → deploy (CI test+lint+deploy self-hosted); reload data 002/004 lên prod nếu cần.
> `uv.lock` để untracked. Session log: `.ai/sessions/2026-07-24-ws3-implement-e2e.md`. Memory
> `ws3-overview-staleness-model` đã đánh dấu ĐÃ CÀI.

> **Trạng thái (2026-07-24 — grill WS3 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs WS3` (AI tổng quan mỗi test + staleness). GREENFIELD (không
> `check_runs`/`data_version`/overview lưu trữ nào). Chốt 8 nhánh + gộp **ADR #18 Revision — WS3**
> (không tách #19). Advisor (fable) endorse Q1–Q7, LẬT Q8. Cốt lõi: (1) `check_runs` latest-upsert
> 1 dòng mỗi `(DN,năm,mã)` ghi TRONG `run_checks()` cho mọi check kể cả 0 finding (không suy từ
> `findings.created_at`); (2) `data_version` số nguyên trên `CompanyPeriod` bump mỗi ingest —
> **stale ⇔ `ran_at` dời HOẶC `data_version` dời** (vì `documents_ingest_year` re-ingest mà KHÔNG
> chạy check → điểm mù nếu chỉ `ran_at`); (3) `check_overviews` overwrite-upsert + telemetry riêng,
> sinh ON-DEMAND ĐỒNG BỘ trong request bằng endpoint `def` THUẦN (không `async def` — sync client
> chặn event loop; không qua job worker 1-thread); (4) flag-only stale (nút "Tạo lại", không
> auto-regenerate); (5) combo LOẠI + **forward-only KHÔNG backfill**. **GOTCHA:**
> `CompanyYearScore.computed_at` là mốc FIRST-run KHÔNG phải latest (`server_default` không `onupdate`)
> → không backfill từ nó. Prompt nạp ĐẾM+top-N subject_key không nạp dòng (11.003 finding/DN-năm).
> 3 ràng buộc cài đặt: bump version trong transaction ingest · đọc version ở ĐẦU run · upsert trong
> `run_checks()` không ở job handler. **KHÔNG đụng code.** Docs: ADR #18 Rev WS3 + GLOSSARY (WS3) +
> memory `ws3-overview-staleness-model` — CHƯA commit. `not_evaluable` là Tầng C chờ họp (cột dành sẵn).
> **Next:** `/to-tickets` (nền check_runs+data_version → overview model+endpoint → UI panel/badge),
> mỗi ticket session fresh tham chiếu ADR #18 Rev WS3. WS3 nền check_runs ĐỘC LẬP WS2.
> Session log: `.ai/sessions/2026-07-24-grill-ws3.md`.

> **Trạng thái (2026-07-24 — WS1+WS2 ĐÃ MERGE + DEPLOY PROD (PR #16) — main=`6f052d3`):**
> PR #16 (`feat/ws1-parse-review`→`main`) merge commit **`6f052d3`**; CI test+lint+deploy XANH; prod
> `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=6f052d3` khớp. Áp 2 migration prod: `b7d2e1f4a3c6`
> (saved-map WS1) + `f5a6b7c8d9e0` (badge ADR#17). PR gộp cả ADR#17 (M15a/M16 004) + docs grill WS3.
> Combo mặc định TẮT trên prod (bật ở `/admin/checks`). **Next thực:** implement WS3 (`/to-tickets`
> ADR#18 Rev WS3); reload data 002/004 lên prod nếu cần; chạy lại harness khi chạm parse/check.
>
> **Chi tiết cài WS2 (đã merge ở trên):** Cài trọn WS2 + làm lại UX chọn test. 6 commit code:
> `5c22a5a` nền · `ecb16c4` UI/async · `4b45bf2` STATUS · `054e9cd`+`e9055e3`+`5ad7f71`+`ad4fcc0` modal UX
> (694fb3b ở giữa là grill WS3 của phiên khác). (1) **Nền:** `RUN_CHECKS` payload `only:list[str]`;
> `run_checks(only=)` chạy tập con; combo **recompute MỌI lần chạy** đọc TOÀN finding-set, gate
> `combos_enabled` (app_settings, **default OFF**); delete `COMBO_*` giữ vô điều kiện. (2) **Chạy test
> lẻ:** nút "Chạy lại {mã}" mỗi nhóm → `RUN_CHECKS {only:[mã], năm}` → `/jobs/{id}`. (3) **Export chọn:**
> `build_export(only=)` lọc `check_code.in_()`; `/export?check=` lặp; Tổng quan liệt kê mã chọn.
> (4) **`documents_confirm_review` async** (option A: save-map+re-ingest sync, re-run scoped **enqueue**
> → `/jobs/{id}` khi re-confirm); ẩn combo ở company_detail khi OFF; toggle admin combo ở card đầu trang
> `/admin/checks`. **Modal UX (theo /frontend-design Anthropic):** panel `<details>` xấu → thay bằng 2
> `<dialog>` native ("Chọn test chạy" = toàn danh mục · "Xuất Excel" = mã có finding), hàng bấm-cả-hàng
> checkbox 18px accent navy, **gom theo họ C1/C2/… tiêu đề nhóm §4 sticky** (`_group_options_by_family`),
> footer đếm sống + nút tự mô tả ("Chạy 3 test"/"Chạy tất cả"), a11y qua WIG (focus-visible/overscroll/
> aria-labelledby). **650 test pass, ruff sạch, KHÔNG migration** (`combos_enabled`=1 row `app_settings`).
> Review (critic) bắt **Defect 1 đã sửa:** pre-delete của `run_checks(only=)` phải gồm cả mã dynamic `X.*`
> (không chỉ built-in) → nếu không "Chạy lại X.1" nhân đôi finding (regression test thêm). Defect 2 (max_raw
> giữ +20 combo khi OFF) **không sửa** — ADR chốt "Scoring KHÔNG đổi", có sẵn từ trước WS2.
> **Lưu ý harness:** combo default OFF → full-run bỏ meta-finding COMBO_* so với mốc 417 (delta CÓ CHỦ Ý,
> không phải regression). **Next:** push/merge WS1+WS2; implement WS3 (`/to-tickets` ADR #18 Rev WS3).
> Memory `check-execution-async-via-jobs` đã đánh dấu ĐÃ CÀI. Session log: `.ai/sessions/2026-07-24-ws2-implement-modal-ux.md`.

> **Trạng thái (2026-07-24 — WS1 IMPLEMENT XONG (5 ticket) + demo build + fix dev server):**
> WS1 cài trọn trên branch `feat/ws1-parse-review`: #4 evidence source+review state+registry
> (`7df7e22`) · #5 vòng đời file+cổng review (`0653f1d`) · #6 vân tay form+saved-map store
> (migration `b7d2e1f4a3c6`, `fca9bbb`) · #7 màn review (`573a273`) · #8 re-run scoped (`f00db6f`).
> **634 test pass, ruff sạch, harness giữ 417** (WS1 provenance/UX, KHÔNG đổi finding). Issue GH
> #4–#8 (ready-for-agent) đã cài nhưng **CHƯA push/merge/PR**. `uv.lock` để untracked.
> **2 giới hạn WS1:** (1) parser CHƯA đọc vị trí cột từ saved-map — sửa cột chỉ đánh `officer-confirmed`,
> chưa rewire parse; (2) `run_checks(only=)` xoá COMBO năm đó tới lần chạy full.
> **Nợ do WS2 revise ADR #18:** #7/#8 gọi `run_checks` ĐỒNG BỘ trong `documents_confirm_review` →
> phải chuyển sang job queue (WS2 chốt check chạy async).
> **Demo build** `db-data/audit_hq_demo.sqlite` (gitignored, CHƯA deploy): chỉ 002/004/006, đổi tên;
> 004 = gộp EPE+GC (option 2) = **219 finding** (méo 187→219, PHẢI phân tích lại — memory
> `pilot-004-epe-gc-merge`). MST thật CÒN ở `tax_id`; file Excel gốc còn tên thật.
> **Dev server:** process cũ `84da630` (không `--reload`) 500 trang company vì DB đã tiến xa → đã
> kill PID 8340 + relaunch detached `--reload` trên code hiện tại, mọi trang 200.
> **Next:** grill WS3 (session fresh, worktree/branch riêng) song song WS2-impl; push/merge WS1;
> deploy demo (+ kiểm `user_companies`/login); 004 phân tích lại; async-hoá `run_checks` #7/#8.
> Session log: `.ai/sessions/2026-07-24-ws1-implement-demo-build.md`.

> **Trạng thái (2026-07-24 — grill WS2 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs WS2` (chạy test lẻ + export chọn). WS1 đã cài (branch `feat/ws1-parse-review`,
> #4–#7). Chốt + gộp vào **ADR #18 Revision — WS2** (không tách #19, theo owner):
> (1) **Chạy check TẤT CẢ async qua job queue** — SỬA "re-run inline" của WS1; `RUN_CHECKS` payload
> thêm `only: list[str]`; worker 1-thread serialize ghi → hết tranh chấp SQLite writer. Per-test run =
> nút mỗi nhóm check → `RUN_CHECKS {only:[mã], năm đang xem}` → `/jobs/{id}`. `documents_confirm_review`
> tách confirm/run (option A): save-map + re-ingest GIỮ đồng bộ (file→`parsed`), re-run scoped →
> enqueue job. (2) **Combo:** recompute MỖI lần chạy đọc TOÀN finding-set (sửa lỗi chạy lẻ xoá combo
> không dựng lại) + toggle `combos_enabled` (app_settings, **default OFF**, lazy per-run, ẩn cả render
> lẫn recompute) — OFF vì 2/4 combo neo C4.3 đang đổi định nghĩa. (3) **Export chọn test EPHEMERAL:**
> `build_export(only=)` + param `check` lặp, không chọn = xuất đủ, không "profile". WS2 build được CHỈ
> với hạ tầng job + registry WS1, **KHÔNG cần `check_runs`/`data_version` (WS3)**. **KHÔNG đụng code.**
> Docs: ADR #18 Revision + GLOSSARY (mục WS2) + memory `check-execution-async-via-jobs` — CHƯA commit.
> **Next:** `/to-tickets` cắt slice (đề xuất: nền `only` trong `RUN_CHECKS` handler + `combos_enabled`
> read → per-test run UI → selective export → sửa `confirm_review` sang async), mỗi ticket session fresh
> tham chiếu ADR #18 Revision — WS2.

> **Trạng thái (2026-07-24 khuya — grill WS1 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs` cho **WS1** (parse review + map cột) của brief UI redesign. Chốt toàn bộ
> nhánh chịu lực → **ADR #18** (`.ai/DECISIONS.md`) + **`.ai/GLOSSARY.md`** (mới) + memory
> `parse-confidence-evidence-model`. Cốt lõi: tin cậy = **evidence source mỗi cột** (`officer-confirmed`
> > `header-matched`·`balance-checked` > `position-only`; `balance-checked` chỉ đủ cho cột dạng TỔNG
> vì đẳng thức bất biến dưới hoán vị cột cùng dấu — advisor xác nhận, C2.1/C2.2 đã own đẳng thức).
> Badge **2 trạng thái** `verified`/`needs_review`; cổng review **per-file, warn-not-block**; registry
> `check→cột` dict tĩnh (`consumed_as: individual|sum`); map lưu theo **(DN, vân tay form)** — **per-DN
> confirm (option 2, SỬA ADR #15 cross-DN)**; vòng đời file **`uploaded→analyzed→parsed`** (auto-advance
> khi verified) hiện trên UI; AI = bước sửa (ADR #15); staleness = re-run check bị ảnh hưởng inline,
> stale-flag để WS3. **KHÔNG đụng code.** Working-tree: ADR #18 + GLOSSARY.md **CHƯA commit**.
> **Next:** `/to-tickets` cắt 4 slice → `/implement` ticket 1 (nền: registry + evidence tagging trên
> đường standard — giữ `SheetCandidate.colmap` đang bị `parse_m15` vứt, thêm keyword cột 6/7/9,
> ghi evidence vào `ParseProvenance`), **mỗi ticket một session fresh** tham chiếu ADR #18.
> Session log: `.ai/sessions/2026-07-24-grill-ws1.md`.

> **Trạng thái (2026-07-24 tối — C4.3 đổi số nhân + tầm nhìn UI redesign):**
> Hai việc phiên này. (1) **C4.3 / P-07:** đã sửa đề án §4.1 (số nhân định mức = **sản lượng sản
> xuất**, không phải xuất khẩu) + ADR ở `audit-hq/.ai/DECISIONS.md` — **CHƯA COMMIT**, cross-repo.
> Code `app/checks/c4_norm.py` **chưa sửa** (việc `/implement` kế tiếp): đổi `sp_export`→sản lượng,
> tách (6)/(7) ở `resolve_m15a`, skip mã không-nguồn nhường C4.1, thêm bậc mâu thuẫn vật lý. Đo
> trên dữ liệu thật: 2.371→2.063 finding (−13%). Chi tiết `audit-hq-pilot/notes/13` P-07.
> (2) **UI redesign:** brief 3 workstream (phát hiện+map cột / chạy test lẻ+export chọn / AI overview+stale)
> ở `.ai/features/2026-07-24-parse-review-per-test-ux/brief.md` — input cho `/grill-with-docs`.
> Owner muốn **mở session mới chạy flow Matt**, nghiêng grill WS1 trước.
> (3) **002 (PILOT_002) đã sửa cấu hình kỳ** trên DB localhost: re-ingest với cửa sổ tài chính
> → 279→48 finding, risk 65→7. Backup `audit_hq.sqlite.bak-pre-002-reingest-20260724`.
> Session log: `.ai/sessions/2026-07-24-c43-basis-and-ui-redesign.md`.

> **Trạng thái (2026-07-24 — M15a mở rộng + M16 ĐM thực tế cho 004 + badge truy nguồn — CHƯA COMMIT):**
> Hoàn thành phần "CHƯA thực hiện — Mẫu 15a" của ADR #15 (nay là **ADR #17**). `resolve_m15a`
> (`extended_layout.py`): cổng đẳng thức + `export_qty` theo NHÃN (duy nhất, phải là số hạng trừ)
> + khai triển nhãn gộp `(8ab)`. `content_slots` dò thêm đường mở rộng cho m15a. M16 chọn cột ĐM
> "thực tế" khi có cặp kỹ thuật/thực tế (004). **Badge CÓ LƯU** (`DataFile.parse_layout`/`parse_detail`,
> migration **`f5a6b7c8d9e0`**): trang Tài liệu + trang Dữ liệu gốc hiện bố cục + đẳng thức N/N +
> nhãn cột. Đo thật: 004 EPE M15a 43 (43/43) + M16 664 (c8 thực tế) → **C4.3 fire 8**; 004 GC M15a 2
> + **C1.4 fire 2** (sau khi đặt kỳ GC manual = FY2025 vì header GC ghi sai). 006/whitelist đường
> CHUẨN không đụng. **Harness: 419→419 y hệt** (trung tính; 419 ≠ "1.331" cũ — xem ADR #17 + memory).
> Full suite **583 pass**, ruff clean. **CHƯA commit, CHƯA deploy** (local DB đã đổi + migration đã áp local).
> Screenshot: `.ai/features/2026-07-24-m15a-m16-004/screenshots/`.
>
> **Trạng thái (2026-07-24 — C1 kỳ báo cáo custom-date, full-stack — ĐÃ DEPLOY PROD):**
> Xong C1 `period_from/to` (ADR #16). BCCT chọn theo cửa sổ kỳ `[from,to]` thay `==year`;
> `period_year` = nhãn kỳ (tách khỏi `declaration_date`). Bảng `company_periods` + migration
> `e4f5a6b7c8d9`. Frontend: trang tài liệu sửa được kỳ (form + banner + về mặc định) + nhãn năm
> tài chính ở company_detail/item_detail. 22 test mới, full suite xanh. Harness: PILOT_002 phục
> hồi **đúng 3.014** dòng (window tự đọc 2025-04-01..2026-03-31), whitelist **1.331** finding BẤT
> BIẾN (code cũ cũng 1.331 — mốc "419" cũ đã lỗi thời).
> **ĐÃ MERGE + DEPLOY:** PR #2 → merge commit **`f5d2c0c`** → CI test+lint+deploy xanh →
> prod `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=f5d2c0c` khớp. Migration
> `e4f5a6b7c8d9` đã `alembic upgrade head` trên DB prod. Migration head giờ **`e4f5a6b7c8d9`**.
>
> **Trạng thái (2026-07-23 — Tier A parse layer + B1 + ADR 15 Mẫu 15):**
> Phiên dài, xử lý bộ dữ liệu mới 3 DN (002/004/006) từ `audit-hq-pilot`. Viết lại **tầng
> parse**: chọn sheet theo nội dung, dò dòng dữ liệu, đếm ô hỏng, chọn cột theo bố cục mở
> rộng qua đẳng thức của biểu. Sửa C4.3 nhân trùng khối định mức (B1). Sửa trang finding
> (18,7 MB → 294 KB) + trang tài liệu nhiều slot. **4 lần deploy, đều xanh.**
> **`main` = `origin/main` = prod = `c82ffa9`**, working tree sạch.
> Migration head **`d3e4f5a6b7c8`** (KHÔNG đổi phiên này — không có migration nào phiên này).
> 523 test function, full suite pass.

## Current State

### Git / deploy
- **`main` = `origin/main` = prod = `1eea393`** (merge PR #24 — "Liên sổ"; PR #23 2SỔ ở `9d90d3d`), working tree
  sạch (trừ `uv.lock` untracked). Prod live `audit-hq-demo.tinsu.ai` chạy `1eea393` (verify 2026-07-25: `/healthz`
  200, `build_sha=1eea393` khớp).
- Migration head prod = **`d0e1f2a3b4c5`** (`data_files.book`; qua `c9d0e1f2a3b4` book settlement/findings) — CI đã `alembic upgrade head`.
- Prod data = **3 pháp nhân**: PILOT_002, PILOT_006, PILOT_004 (hai sổ EPE/GC, ẩn danh — nạp 2026-07-25, xem block đầu file).
- Deploy = push `main` → CI "Test & Deploy to Tinsu" (self-hosted `tinsu-prod`): test+lint →
  docker build → restart → `alembic upgrade head` → healthcheck. Watch: `gh run watch <id> --exit-status`.
  **LƯU Ý:** runner self-hosted đôi khi queue 10+ phút trước khi chạy — không phải lỗi.
- 9 commit phiên này (từ `fadc427`): xem session log `2026-07-23-tier-a-parse-layer.md`.

### Prod ≠ local — ĐỌC KỸ trước khi đụng dữ liệu
- **DB prod ở server** (`/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite`, ~291 MB,
  truy cập qua `ssh tinsu` + `docker exec audit-hq-mvp`). **CẬP NHẬT 2026-07-25:** prod giờ có
  **PILOT_002 + PILOT_006 + PILOT_004 (hai sổ, ẩn danh)** = 14.998 finding (xem block đầu file).
  Rollback 004-load: `db-data/audit_hq.sqlite.{bak,raw}-pre-004-load-20260725-152615`.
  Backup DN cũ (2026-07-24): `db-data/audit_hq.sqlite.bak-pre-pilot-load-20260724-230046`.
- **KHÔNG có file nguồn trên prod cho 002/006** (DB-only) → trang Tài liệu/preview/download trống cho 2 DN này.
  (Cũ: raw-data prod dùng `DN_001/DN_103/...` — nay không còn dùng, 14 DN đó đã gỡ.)
- **`run_all` tìm 0 cặp trên prod** (whitelist là HONG_AN/GROWATT/DO_THANH/KIM_LONG — không tồn
  tại ở server). Re-ingest prod bằng `run_all` là no-op.
- **Local `data/` symlink** → `../audit-hq/data/raw`, có tên THẬT (HONG_AN…) + PILOT_002/004/006.
  Ingest theo `code` → tạo company mới, KHÔNG ghi đè `DN_xxx`. Xem [[local-data-symlink-mismatch]].

### Dữ liệu mới 3 DN (002/004/006) — đã nạp vào LOCAL DB
- Local DB giờ có `PILOT_002` (279 finding), `PILOT_006` (14.883), `PILOT_004_EPE` (111),
  `PILOT_004_GC` (99). Chỉ ở local — KHÔNG ở prod.
- Symlink tree đã tạo cố định: `../audit-hq/data/raw/PILOT_{002,004_EPE,004_GC,006}/<năm>/{BCQT,DINH_MUC,HANG_CHI_TIET}`
  (trỏ tới `raw-hq-2026`, gitignored). `discover`/`ingest` đọc trực tiếp được.
- **File nguồn:** `/mnt/p/Downloads/audit-v2.zip` (148 MB) = giải nén sẵn ở `audit-hq/data/raw-hq-2026/`.
- Verify chéo với parser độc lập của pilot: 006 điểm 154/190 y hệt, M15 10.560 dòng, sai lệch
  2/21.878 finding. → tầng parse đúng.

### Tầng parse — trạng thái từng phần
- **Chọn sheet theo nội dung** (`app/adapters/sheet_select.py`): chấm điểm nhãn cột đúng vị
  trí, phá hoà theo kỳ báo cáo (rank), báo `SheetNotFound` nếu không khớp. 4 slot đều dùng.
- **Dò dòng dữ liệu + P-01** (`app/adapters/layout.py`): `_norm` gập đ/Đ (U+0111/U+0110), dò
  header 2 dòng + dòng đánh số `(1)(2)…`.
- **Bố cục mở rộng Mẫu 15** (`app/adapters/extended_layout.py`, ADR #15): suy map cột từ dòng
  đánh số, chứng minh bằng đẳng thức `(11)=(5)+(6)-(7)-(8)-(9)-(10)` ≥98% dòng. Chỉ chạy khi
  `select_sheet` trượt → prod (16 file, 0 trượt) KHÔNG đụng. 004 nạp được M15 (EPE 104, GC 37).
- **A3 ô hỏng** (`_common.py`): đếm ô lỗi Excel + liên kết workbook ngoài, cảnh báo không đổi số.
- **B1 C4.3** (`c4_norm.py`): mỗi cặp BOM tính 1 lần thay vì 1 lần/khối lặp.

## Recent Changes (2026-07-23)
9 commit trên `main`, 4 lần deploy:
1. `a7f685a` P-01 · `e8dbea3` A1+A2 · `8c69f0b` A1 m16/bcct + discover · `3d98e4f` A3 ·
   `d6b1bf1` B1 · `2847724` ADR 15 · `665e315`+`216afd3` sửa 6 lỗi từ `/rev` → merge `65c88cf`.
2. `f09116b` phân trang finding · `41794d7` fix trang tài liệu nhiều slot → merge `5b0de04`.
3. `56c54bd` bố cục mở rộng Mẫu 15 (ADR 15) → merge `c82ffa9`.

## Next Steps (theo ưu tiên)
0. **C1 — `period_from`/`period_to` — ✅ XONG + ĐÃ DEPLOY PROD (2026-07-24, ADR #16, đường RẺ).**
   Bảng `company_periods` + migration `e4f5a6b7c8d9`; BCCT lọc theo cửa sổ `[from,to]`; `period_year`
   = nhãn kỳ; frontend sửa được kỳ + nhãn năm tài chính. Full-stack + 22 test. Merge `f5d2c0c`,
   CI + deploy xanh, prod verify OK. **Còn (tuỳ chọn, chưa làm):** cảnh báo cửa sổ sửa tay chồng
   lấn chéo năm — giới hạn manual-only có chủ đích (ADR #16). Đường tự động an toàn (FY liền kề
   không chồng). Ngoài ra: reload dữ liệu PILOT_002/004 lên prod để hưởng phục hồi dòng (prod
   hiện không có file nguồn 002/004 → cần upload hoặc chạy lại từ file).
1. **M15a mở rộng + cột M16 của 004 — ✅ XONG (2026-07-24, ADR #17, CHƯA COMMIT).** `resolve_m15a`
   (đẳng thức + export theo nhãn + nhãn gộp), discovery dò mở rộng, M16 ĐM thực tế, badge có lưu.
   Đo thật: EPE C4.3=8, GC C1.4=2. Harness whitelist 419→419 trung tính. 583 test pass.
   **Còn (tuỳ chọn):** commit + deploy (prod chưa có file 002/004 → chỉ code lên, data cần upload);
   reload 004 lên prod. C4.3 nhánh sản lượng M16 (hệ số nhân) vẫn CHẶN bởi đề án — xem #2.
2. **Sửa đề án `../audit-hq/de-an-audit-hq.md:228` TRƯỚC** rồi mới làm B2 (đổi hệ số nhân C4.3
   sang lượng nhập kho SX), B4 (báo độ phủ C4.3), và hệ số nhân theo sản lượng Mẫu 16. Cả ba
   mâu thuẫn định nghĩa `Σ(định_mức × xuất_khẩu_M15a)` hiện tại — là "sửa catalog" theo AGENTS.md.
3. **B3 đọc cột Ghi chú** — cần migration (thêm `note` vào NvlBalance/SpBalance).
4. **Tầng C — chờ họp:** `period_from`/`period_to` (002/004 năm tài chính → ingest xoá 27-30%
   dòng tờ khai), `NOT_EVALUABLE` (phân biệt "0 vì sạch" vs "0 vì thiếu dữ liệu"), trình bày
   quy mô lớn (đã làm phân trang, còn xếp hạng theo lượng + ngưỡng severity).

## Blockers
- **B2/B4/hệ số nhân C4.3 chặn bởi đề án** — không được sửa mô tả check trước khi update
  `../audit-hq/`. Câu hỏi quy trình 3 repo, cần user chốt.
- **Banner "dữ liệu mẫu"** đang phủ lên tên DN + MST THẬT ở local DB sau khi nạp pilot (banner
  nói dữ liệu giả — sai). `anonymize.py` chỉ sửa DB, KHÔNG sửa nội dung file Excel (trang tài
  liệu vẫn tải file gốc). Chưa xử lý — chặn việc đưa pilot data lên demo.
- **Tầng C chờ họp** (chưa có lịch).

## Notes for Next AI Session
- **Dev server local đang chạy** ở `http://127.0.0.1:8200` (background). Local admin password
  KHÔNG biết → đăng nhập bằng user throwaway seed qua `create_user` rồi purge (xem
  [[ui-screenshots-convention]]). Screenshot scratch, KHÔNG commit.
- **Harness verify** (scratchpad, session-specific, có thể mất): ingest+run_checks toàn bộ
  whitelist vào DB tạm, dump finding đã sort, diff trước/sau. **Mốc chuẩn hiện tại (2026-07-24):
  1.331 finding trên 12 cặp DN×năm** (đo lại code cũ = code mới sau C1 → C1 trung tính). Con số
  "419" trong ghi chú cũ ĐÃ LỖI THỜI (khác bộ dữ liệu/thời điểm) — đừng dùng làm tiêu chí. Chạy
  lại mỗi khi chạm tầng parse/check.
- **Kỷ luật số liệu:** số của `audit-hq-pilot/notes/` đếm theo luật parser CỦA PILOT, không
  phải sản phẩm — phải phát biểu lại theo luật đếm sản phẩm trước khi dùng làm tiêu chí. Xem
  [[tier-a-thu-tu-a1-truoc-a2]] và [[so-lieu-phai-co-mau-so-va-nguon-doc-lap]].
- **A1 trước A2, KHÔNG song song** — `notes/12` ghi sai, đã đính chính. A2 chạy trước A1 làm
  hỏng nặng thêm (đo được +20 finding CRITICAL giả).
- **Cổng đẳng thức là trọng tài** cho map cột — không tin nhãn/mô hình. Bug bắt được nhờ nó:
  số hạng đầu công thức `(5)+(6)-...` không có dấu, 004 GC "lọt" giả vì tồn đầu toàn 0.
- **ADR mới:** `.ai/DECISIONS.md` #15 (15 ADR tổng). Ghi rõ phần đã làm (M15) vs chưa (M15a/M16).
- `audit-hq-pilot` là repo anh em (git local, không remote), commit `7e8e438` đã đính chính
  `notes/12`. Prompt bàn giao gốc ở `audit-hq-pilot/.ai/STATUS.md`.
