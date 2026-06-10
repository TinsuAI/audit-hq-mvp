# STATUS — Audit-HQ MVP

> **Trạng thái (2026-06-11 — UI/UX + viết lại methodology, CHƯA commit/push/live):**
> Trên nền build `8d6b6c5`. **449 tests pass** (446 + 3 test sửa DN), ruff clean.
> Dev server local chạy :8200. Toàn bộ thay đổi session này **chưa commit**.
> 🆕 (1) Viết lại `docs/scoring-methodology.md`: thuần Việt (bỏ thuật ngữ Anh +
> định danh code), sửa 16→**17 phép** / 180→**190**, §6 nêu rõ ngưỡng 5 mức là
> **cấu hình runtime** (mặc định 50/100/300/600/1000, không hardcode), đổi
> "Điểm thưởng tổ hợp" → **"Điểm rủi ro tổ hợp"** + bảng 4 tổ hợp (lấy từ
> `combos.py`) + ghi chú danh mục tổ hợp mở rộng theo kinh nghiệm cán bộ HQ.
> (2) **Thẻ giải thích điểm** thu-gọn-được ở `/companies` (công thức động theo
> `len(RULE_SCOPE)`, thang 5 hạng dựng từ `get_tiers()` nên tự đúng khi đổi ngưỡng).
> (3) **Bảng DN**: tìm kiếm + lọc theo mức + lọc/nhóm theo **ngành** + sort cột —
> thêm cột `Company.industry` (migration `e1a2c3d4f5b6`, đã nạp ngành 4 DN local).
> (4) **Redesign** trang Thêm DN + Tải lên (ô file thành vùng kéo-thả, panel chẩn
> đoán restyle). (5) **Trang Sửa DN** `/companies/{code}/edit` (mã DN khoá vì là
> tên thư mục file). (6) Local: set **key OpenRouter** vào `ai_settings` + bật AI
> (test_connection OK) — **KHÔNG commit** (DB gitignored).
> ⚠️ **Deploy live cần:** chạy migration `e1a2c3d4f5b6` + set ngành 4 DN qua trang Sửa.

> **Trạng thái (2026-06-11, demo upload data + tách upload/check + validate/AI + fix drift):**
> Branch `main` = origin (sạch), **6 commit đã push + deploy live xanh**, build live
> **`8d6b6c5`**. **446 tests pass**, ruff clean. Đã verify demo flow trên live (16/16).
> 🆕 (1) `scripts/gen_demo_data.py` — anonymize file Excel **GỐC** (giữ format thật)
> → `demo-data/` theo **tên DN** + slot; upload tái hiện đúng demo. (2) **Tách upload
> khỏi chạy kiểm tra** — upload chỉ ingest; chạy check là bước riêng; trang DN có
> state "đã nạp, chưa chạy". (3) `app/pipeline/validate.py` chặn **misparse thầm
> lặng** (heuristic dò cột lệch) + `app/ai/ingest_doctor.py`/`POST /diagnose-ai`
> (AI Gemini live, **tùy chọn**, degrade về heuristic khi tắt). (4) **Fix drift
> điểm:** trang danh sách đọc `max(company_year_scores)` thay vì cache
> `companies.risk_score` (list luôn khớp detail).
> **Live đã dọn + recompute 17-rule (2026-06-11):** 4 DN demo, điểm **120/28/168/46**
> (xoá rác DN_008/DN_009), list=detail nhất quán. Local: 116/28/148/46.
> Bộ data + screenshot (demo + AI + live) ở `C:\temp\toss` (Windows, không vào git).
> ⏳ Vẫn chờ chị trả lời 4 câu hỏi clarify M16 (session 2026-06-01).

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build hiện tại: **`8d6b6c5`** (tách upload/check + validate/AI + fix drift điểm).
  Deploy CI xanh. Đã verify demo flow read-only trên live: 16/16 check pass.
- **Điểm live đã recompute 17-rule + dọn rác (2026-06-11)** — 4 DN demo,
  list=detail nhất quán:
  - DN_003 Hoa Sen (Dệt may): **168** (was 177 cache 16-rule) — Cần rà soát
  - DN_001 Phương Đông (Điện tử): **120** (was 127) — Cần rà soát
  - DN_004 Nam Tiến (Hoá chất): **46** (was 49) — Dữ liệu nhất quán
  - DN_002 Tiên Phong (Cơ khí): **28** (was 30) — Dữ liệu nhất quán
  - Đã xoá rác: DN_008 (rỗng) + DN_009 (copy DN_002). Backup live:
    `audit_hq.sqlite.bak-pre-cleanup-20260611-000123`.
- DB tinsu (06-03→04, vẫn giữ): lọc tờ khai lạc kỳ; backfill `norms.note` "x";
  backfill tờ khai xuất DN_003 + DN_001 (GROWATT) từ data-hub.
- C4.1 findings: **74** (backfill loại 217 mã hàng nội địa).
- Ngưỡng tier (default sau `4977cd4`): **50 / 100 / 300 / 600 / 1000**.
  Admin chỉnh ở `/admin/risk-tiers` — đổi không cần re-run check.

### Stack
- Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite (WAL + busy_timeout=5000).
- AI: OpenAI SDK compat, Gemini 2.5 (primary) + NIM DeepSeek (dự phòng).
- Dev port: **8200** (cố định, match docker-compose + Cloudflare tunnel).
- **449 tests pass**, ruff clean.

### Migrations (head: `e1a2c3d4f5b6`)
Chuỗi: `da05efe02a74` → `2d66c843ef0e` (findings) → `9fbf36d7f864` (company.risk_score) → `599dbd931e77` (UOM) → `a3c48313dddf` (ai_settings + ai audit) → `b7e91f4d2a13` (users) → `de9eee546b80` (jobs) → `46b3bcaebbe4` (company_year_scores) → `646b92a93768` (check_definitions) → `a4d5ffcb0da7` (app_settings) → `c7f3a1b2d4e5` (norms.note — xuất xứ "x") → `e1a2c3d4f5b6` (**company.industry** — lọc/nhóm ngành ở danh sách).

### Cấu trúc lưu trữ cấu hình runtime
- `ai_settings` — chỉ cho AI assistant (base_url, api_key, model_default/fast/deep, fallback, limits…).
- `app_settings` — generic key/value JSON cho config admin runtime khác. Hiện chỉ có `risk_tier_uppers`.

### Catalog check
- **49 chính thức** (`app/catalog_full.py`) — danh mục §4 đề án, hardcoded, hiển thị ở `/danh-muc-kiem-tra`.
- **17 MVP đã build** (`app/checks/registry.py`) — runable, có rule code Python (C2.4 thêm 06-10).
- **Catalog động** (`check_definitions` table) — đặc tả no-exec, admin tạo qua `/admin/checks`.

### Async job runner
- Bảng `jobs` + worker thread trong FastAPI lifespan.
- `/jobs` list, `/jobs/{id}` detail, badge navbar polling 10s.

### Rate-based scoring
- `company_year_scores` cache (DN, năm) → score 0-1000 + tier + breakdown JSON.
- 5 hạng neutral, ngưỡng đọc runtime qua `app.app_settings.get_tiers()`.
- `company.risk_score` = max qua các năm.

### Thư viện tài liệu `/tai-lieu`
- 4 trang: scoring-methodology + TT 38/2015, TT 39/2018, TT 81/2019.

## Recent Changes (2026-06-11 — UI/UX: methodology + trang chủ + bảng + form + sửa DN)

Chưa commit. Tests 446 → **449** (+3 sửa DN). Yêu cầu: 5 việc UI/nội dung của chị.

**1. Viết lại `docs/scoring-methodology.md` thuần Việt.** Bỏ thuật ngữ Anh chêm
(rate-based, findings, exposure, max_points, combination bonus, breakdown,
evidence_refs, run-checks, jobs, cohort z-score, calibrated…) + định danh code
khỏi văn xuôi; dịch tên WCO/OECD. **Sửa số liệu dẫn xuất:** 16→17 phép, 180→190
(`max_raw = len(RULE_SCOPE)×10+20`). **§6:** ngưỡng 5 mức là **cấu hình runtime**
(admin chỉnh ở /admin/risk-tiers), bảng ví dụ dùng default hiện hành
50/100/300/600/1000 — KHÔNG còn bộ số cũ 0-100/101-300/… (số cũ không khớp UI).
**§4:** "Điểm thưởng tổ hợp" → **"Điểm rủi ro tổ hợp"** (chị góp ý "thưởng" mang
nghĩa tích cực, sai ngữ cảnh) + thêm bảng **4 tổ hợp** (Định mức ảo C2.3+C4.3;
NVL nội địa không khai báo C1.3+C5.1; Số liệu mâu thuẫn C2.1+C4.3; Phân loại sai
C3.2+C3.3) lấy từ `combos.py` + ghi chú danh mục mở rộng theo kinh nghiệm HQ.

**2. Thẻ giải thích điểm ở trang chủ** (`companies_list.html` + `companies.py`).
`<details open>` thu-gọn-được đầu `/companies`: mô tả + công thức (động theo
`len(RULE_SCOPE)` = **17 phép**) + trọng số 🔴10/🟡3/🔵1 + thang 5 hạng màu dựng
từ `get_tiers(db)` (tự đúng khi admin đổi ngưỡng) + link tài liệu. Route truyền
`n_rules` + `tier_ladder`. Gỡ popover "ℹ️" cũ + CSS chết `.scoring-info/.scoring-popover`.

**3. Bảng DN: tìm kiếm + lọc + sort + nhóm ngành.** Client-side (JS inline trong
template): ô tìm (mã/tên/MST), lọc theo mức cảnh báo, lọc theo ngành, toggle
**nhóm theo ngành** (chèn hàng group-header), sort khi bấm tiêu đề (Điểm/Tên/
Ngành/MST). Thêm cột **Ngành** + schema `Company.industry` (migration
`e1a2c3d4f5b6`). Nạp ngành 4 DN local: DN_001 Điện tử, DN_002 Cơ khí, DN_003
Dệt may, DN_004 Hoá chất. **Live chưa có** (chạy migration + set qua trang Sửa).

**4. Redesign Thêm DN + Tải lên.** Bỏ inline-style → class CSS (`.form-card`,
`.form-grid-2`, `.form-actions`, `.form-alert`, `.form-hint`, `.req`). `new_company`
thêm field **Ngành** (input + datalist 8 ngành). `upload_data`: 4 ô file thành
**vùng kéo-thả** (`.upload-slot`, hiện tên file + viền xanh khi có file, JS
dragover/drop), panel chẩn đoán + khối AI restyle (`.diag-panel`).

**5. Trang Sửa DN** `GET/POST /companies/{code}/edit` + `edit_company.html`. Sửa
tên/ngành/MST/địa chỉ; **mã DN khoá** (read-only — là tên thư mục lưu file). Tên
giữ hậu tố `(Demo)`. Nút "✏️ Sửa" + dòng "Ngành" ở header `company_detail.html`.
Test `tests/test_company_edit.py` (3): prefill+khoá mã, update+giữ Demo, 404.

**6. Key OpenRouter (local).** Set `ai_settings.api_key` + `enabled=true` qua
`set_setting`, `test_connection` OK (229ms). DB gitignored → **không commit, chưa
lên live**. Default `base_url` vốn đã là OpenRouter + model Claude.

## Recent Changes (2026-06-11 — demo upload data + tách upload/check + validate/AI)

Commits (main, **chưa push**): `86a7d48`, `2ee586e`. Tests 439 → **444**.

**1. Bộ data demo để UPLOAD** — `scripts/gen_demo_data.py` (commit `86a7d48`).
Yêu cầu: HQ cần upload BCQT (M15/15a/16) + BCCT thật để chạy 1 flow hoàn chỉnh.
KHÔNG export từ DB (vô tri, sai cấu trúc) — thay vào đó **anonymize file Excel
GỐC** mà `discover()` chọn, chỉ thay PII (tên DN/MST/địa chỉ/NCC từ
`db-data/anonymize_mapping.json`), giữ nguyên layout/cột/sheet/công thức.
- 4 DN × mọi năm có data (~12 bộ, 42 file). Output `demo-data/<tên DN>/<năm>/
  {BCQT,HANG_CHI_TIET}/` — ĐM (Mẫu 16) gộp trong BCQT; folder theo **tên DN**
  (không dùng mã DN_xxx). gitignored.
- DN_003/2024 nhúng lại 7 sai phạm inject §6.3 (từ `injected_changes.json` —
  toàn M15; block norm DG ×100 thực tế chưa từng chạy vì DB không có norm DG).
- **Bug fix khi verify:** ô closing của DO_THANH là **công thức Excel**; openpyxl
  giữ công thức nhưng mất cache → pandas đọc lại = 0 → C2.1 false. Fix: bake
  `data_only=True` cache cho mọi ô công thức. Sau fix round-trip khớp tuyệt đối.
- Verify: ingest demo-data vào scratch DB + run checks → **116/28/148/46** khớp
  DB gốc (DN_003 +2 finding nhiễu .xls→.xlsx, điểm không đổi). Leak scan sạch.
- Bản copy ở `C:\temp\toss` cho chị dùng tay.

**2. Tách upload khỏi chạy kiểm tra** (commit `2ee586e`).
Trước: upload → tự `ingest + run_checks`. Giờ: `upload_data` **chỉ ingest**;
chạy check là bước riêng (`POST /run-checks` đã có).
- `company_detail` lấy năm từ **dữ liệu Tầng 1** (NvlBalance/SpBalance/Norm/
  DeclarationLine) chứ không chỉ từ findings → data hiện ngay khi chưa chạy check.
- Context mới: `has_data`, `checks_run`, `just_ingested`. Banner "Đã nạp dữ liệu…
  chưa chạy kiểm tra" + nút "Chạy kiểm tra năm N"; ô điểm hiện "— / Chưa chạy".
- Bỏ import `run_check_pipeline` (không còn dùng).

**3. Validate upload + AI chẩn đoán** (commit `2ee586e`).
Rủi ro thật = **misparse thầm lặng** (adapter hardcode cột/sheet, file HQ khác
mẫu → đọc nhầm, không báo). Giải pháp 2 lớp:
- Lớp 0 `app/pipeline/validate.py`: `diagnose_upload()` chạy TRƯỚC ingest. Bắt:
  file hỏng, 0 dòng (sai mẫu/sheet), số toàn 0 (lệch cột). **Heuristic dò dòng
  tiêu đề + map cột thực vs chuẩn** → câu giải thích cụ thể ("cột Tồn cuối ở vị
  trí 12, chuẩn 10"). Lỗi nặng → render panel chẩn đoán (HTTP 422), **KHÔNG nạp**.
- Lớp AI `app/ai/ingest_doctor.py` + `POST /companies/{code}/diagnose-ai`: nút
  "🤖 Nhờ AI chẩn đoán" (chỉ hiện khi AI bật). Gửi trích đoạn sheet thật + schema
  mong đợi cho LLM (slot `fast` + fallback chain, guard rate/budget). Xử mẫu lạ
  heuristic bó tay (vd header tiếng Anh → AI map ngữ nghĩa Anh→Việt). **Không
  phụ thuộc AI** — tắt thì heuristic vẫn đầy đủ. Tuân thủ "không LLM trong rule logic".
- **Bug fix khi screenshot:** `_check_balance` truy cập `r.import_qty` cho mọi
  balance row, nhưng `M15aRow` dùng `intake_qty` → 500 khi upload Mẫu 15a. Fix
  field-agnostic `_inflow()` + regression test. (Nhờ chụp ảnh mới lộ.)
- `tests/test_validate.py`: 5 test (good m15/m15a, lệch cột, thư mục trống, file hỏng).

**4. Screenshot Playwright** (không commit) — 7 ảnh ở `C:\temp\toss\screenshots\`:
upload-chỉ-nạp, đã-nạp-chưa-chạy, sau-khi-chạy (điểm 112 + combo), chẩn-đoán-lỗi,
nút-AI, AI-Gemini-thật, AI-case-file-tiếng-Anh. Chạy trên scratch DB + raw tạm
(không đụng DB/data thật). Demo AI dùng config live kéo từ tinsu (key xoá sau,
không commit, không in raw).

## Recent Changes (2026-06-10 — C2.4 + resync local + deploy live + fix CI)

**1. C2.4 (tồn cuối TP âm)** — commit `bc59545`. Đối xứng C2.3 cho thành phẩm
(`SpBalance`/`product_code`). Thêm: `check_c2_4` + `CHECKS["C2.4"]`, `CheckSpec`
C2.4 (CRITICAL), `RULE_SCOPE["C2.4"]="tp"`, catalog status `wip`→`mvp`. 16→17
runnable. ⚠️ Thêm vào `RULE_SCOPE` nâng mẫu số scoring (16→17 rule) → **điểm mọi
DN giảm nhẹ** khi recompute bằng code mới. Test: +2 C2.4, sửa 3 assertion bị ảnh
hưởng (catalog counts, scoring max_raw). 439 pass.

**2. Resync DB local về đúng 4 DN ẩn danh** — phát hiện local lẫn 5 công ty thật
(tên thật hiện trên UI dev) + 4 DN_xxx mồ côi (mất tờ khai, score cũ). Làm sạch
theo **đúng quy trình live**: wipe business tables → `run_all` (ingest 4 DN +
checks) → `anonymize` → `inject_findings` DN_003 → rerun DN_003 2024 → recompute.
Kết quả: đúng 4 DN demo, 0 tên thật, 197 NCC ẩn danh. Backup pre-resync:
`audit_hq.sqlite.bak-pre-resync-20260610-213107`.

**3. Fix triệt để nguồn GROWATT (Next Step #2 — DONE)** — `data/GROWATT` thiếu
file xuất + 2025. Copy 2 file HUB từ data-hub
(`.../source_inventory/growatt-vn/2026-05-27/BaoCaoHangChiTiet ALL {NK,XK} GRW`)
vào `data/raw/GROWATT/multi_year/HANG_CHI_TIET/` đặt tên **có khoảng năm**
(`...ALL NK GRW 2023-2025.xls`) để `discover._filename_covers_year` nạp; file cũ
rename `...2023-2025 OLD.xls` (draft-excluded, tránh double-count). `data/raw`
gitignored → file thật không lên git. **Rebuild demo từ nay tự nạp đủ GROWATT.**
Verify khớp live: 2023=5475, 2024=3505, 2025=19898 tờ khai (+21 dòng/năm thiếu
ngày tờ khai → ingest gán `row_year=year` nên nhân 3, ~0.2%, không đổi điểm).

**4. Deploy C2.4 lên live (chỉ code, giữ data)** — chị **không ingest được trên
live** (không có Excel raw) → không "rebuild theo quy trình" được; chọn **chỉ
deploy code, giữ nguyên data**. CI lần đầu fail (`uv: command not found`), deploy
tay qua được (`docker compose up -d --build`, build trong Docker). Live: 4 DN,
điểm 127/30/177/49 nguyên vẹn, C2.4 runnable. **2 bản KHÔNG giống nhau về điểm**
(local 17-rule vs live cache 16-rule). Muốn đồng bộ điểm: rerun checks trên live
bằng code mới (sẽ đổi findings/score) — defer theo ý chị.

**5. Fix CI runner kẹt `uv`** — commit `cb2f3ad`. `uv` vẫn cài (`/snap/bin`,
`~/.local/bin`) nhưng PATH shell non-interactive của GitHub Actions không có →
prepend `export PATH="$HOME/.local/bin:/snap/bin:$PATH"` trong step "Setup venv".
CI xanh trở lại, auto-deploy hoạt động. Backup live pre-deploy:
`audit_hq.sqlite.bak-pre-c24-<ts>` trên tinsu.

## Recent Changes (2026-06-04 — fix BCCT đa-file NK/XK + backfill tờ khai DN_003)

Commit `a2b3f92`: `discover`/`ingest` nạp **gộp nhiều file BCCT** mỗi năm.
- **Bug:** discover chọn 1 file BCCT/năm theo mtime. DN tách tờ khai nhập (NK) và
  xuất (XK) thành 2 file → chỉ nạp 1. HONG_AN 2021 còn chọn nhầm file rỗng
  `BaoCaoHang XK 2021.xls` (0 dòng) → kỳ 2021 trống tờ khai.
- **Fix:** `DiscoveredFiles.bcct` thành list; `_pick_all` giữ mọi file non-draft;
  ingest parse + gộp, giữ `source_file` đúng từng dòng. HONG_AN: 2021 0→289,
  2022 69→236, 2025 1512→1893 dòng.
- **Backfill live** (DN_003, vì live không re-ingest từ Excel): parse NK+XK thật,
  ẩn danh `partner` qua mapping (mint 4 alias mới), DELETE+INSERT
  `declaration_lines` 3 năm, rerun full + recompute.
- **Insight:** thiếu tờ khai xuất (E62) khiến C1.4 báo false-positive hàng loạt
  "xuất M15a không có tờ khai". Bổ sung đủ → DN_003 2025 387→14 finding,
  2022 417→250. Score DN_003 232→177 (chính xác hơn).

## Recent Changes (2026-06-03 — fix bug ingest/evidence lệch kỳ, session Gemini)

Commit `ad68837` (push main): lọc tờ khai BCCT theo năm.
- **Bug:** File BCCT gộp nhiều năm (2023–2025). `ingest` gán cứng mọi dòng vào
  `period_year` đang nạp → finding kỳ 2025 hiện evidence tờ khai 2023, sai tổng
  lượng đối chiếu Mẫu 15 (C1.1/C1.4), trang Data lẫn năm.
- **Fix:** `app/pipeline/ingest.py` chỉ nạp dòng
  `r.declaration_date is None or r.declaration_date.year == year`. Mỗi năm
  ingest riêng nên tờ khai 2023 vẫn vào kỳ 2023 — KHÔNG mất dữ liệu (vd HONG_AN
  file 2267 dòng → 2023:180, 2024:246, 2025:1512).
- **Live:** khôi phục `declaration_lines` từ backup 27/05 + lọc ~20.671 dòng
  lạc kỳ + rerun checks. DN_001 296→127, DN_002 125→62.
- Chi tiết: `.ai/sessions/2026-06-03-ingest-year-filter-fix.md`.
- ⚠️ Live chỉ khôi phục `declaration_lines` (không re-ingest từ Excel). Bảng
  `norms` có thể CHƯA có cột `note` "x" → cần kiểm tra fix C4.1 (06-01) đã
  hiệu lực trên live chưa.

## Recent Changes (2026-06-01 — góp ý nghiệp vụ + Mẫu 16 xuất xứ "x")

Commit `9d5bd06` (push main): C4.1 loại NVL xuất xứ trong nước.
- Mẫu 16 TT39 cột "Ghi chú" (col 8) = "x" → xuất xứ VN, không có tờ khai nhập.
- Adapter `m16.py` đọc note → `Norm.note` (migration `c7f3a1b2d4e5`).
- C4.1 bỏ qua mã "x" khi soi "không có nguồn nhập". C4.3 giữ nguyên (vẫn áp
  dụng cho hàng nội địa vì vẫn tiêu hao).
- Impact DB dev (8 cặp DN/năm có "x"): **bỏ ~296 C4.1 false-positive (~80%)**.

Phân tích 5 điểm góp ý: điểm 1 đã làm; điểm 4 (mapping) + 5 (KXDĐM) đã verify
không có vấn đề trong data hiện tại; điểm 2/3 chờ chị trả lời 4 câu hỏi clarify.
Chi tiết: `.ai/sessions/2026-06-01-m16-domestic-origin-c41.md`.

## Recent Changes (2026-05-27 audit + fix vòng 1, từ commit `22aaa7b` → `01db20d`)

6 commit, tất cả đã push + deploy + rerun DB tinsu:
- `b4d2737` fix(adapters): `normalize_code` reject placeholder values
- `233da3f` fix(checks): xoá E13 khỏi `IMPORT_CODES[DNCX]`
- `b81e442` fix(checks): C1.1/C1.4 emit INFO band như description đã hứa
- `c36a3e1` fix(checks): C1.7 thống nhất denominator giữa code, registry, catalog
- `8c3f33c` fix(dynamic_runner): `_eval_threshold` AND semantics trong cùng band
- `01db20d` fix(dynamic_runner): dynamic finding có `evidence_refs` và `subject_type` đúng

Tổng impact đo trên DB demo sau rerun:
- Junk subject_key (`.`, `-`, …) **0** (was 23+).
- C1.2 E13-only false positive **0/240** (was ~93/333 = 28%).
- C1.1 distribution: 16 INFO + 17 WARN + 527 CRIT (INFO band giờ fire đúng).
- Toàn bộ dynamic check finding tương lai sẽ có evidence + subject_type chuẩn.

Chi tiết: `.ai/sessions/2026-05-27-checks-audit-round-1.md`.

## Next Steps

A. ✅ **DONE** — 6 commit đã push + deploy live xanh (build `8d6b6c5`), verify demo
   flow trên live 16/16. main = origin sạch.
B. **Rebuild demo-data trước mỗi demo / sau khi đổi data:** `python -m
   scripts.gen_demo_data` (tự verify leak). Copy sang `C:\temp\toss` nếu cần.
C. **(Feature lớn, defer) AI auto-remap:** hiện AI chỉ *chẩn đoán* (giải thích).
   Bước tiếp: AI tự đề xuất mapping cột → cán bộ **duyệt** → ingest theo mapping.
   Cần thêm UI duyệt mapping trước khi ghi DB. Chưa làm.
D. **UI/UX — phần lớn ĐÃ LÀM 2026-06-11** (xem Recent Changes UI/UX): redesign
   Thêm DN + Tải lên (kéo-thả file), thẻ giải thích điểm trang chủ, bảng DN
   tìm/lọc/sort/nhóm ngành, trang Sửa DN. **Còn lại (gợi ý):** badge trạng thái
   DN ngay trên bảng danh sách, progress inline khi chạy check, **tự đoán slot
   theo tên file** khi kéo-thả (hiện kéo vào đúng ô), nút "nạp 1 DN mẫu" một chạm.
E. **[ĐÃ ĐIỀU TRA 2026-06-11] DN_002 (30) vs DN_009 (28) — KHÔNG phải khác data.**
   DN_009 = bản copy DN_002 (cùng MST `0401886016`, chắc tạo từ upload data DN_002).
   Xác minh trên live: data + findings + **`company_year_scores` giống hệt** — cả
   hai đều **28/năm** (max_raw=190, raw=5.314). Chênh chỉ ở field denormalized
   `companies.risk_score`: DN_002=**30** (kẹt giá trị rate-based **16-rule cũ**),
   DN_009=28 (nhất quán). Per-year của DN_002 **đã là 28** — risk_score 30 là
   **stale**, không khớp chính year-scores của nó. Dry-run `recompute_all_scores`
   trên live: DN_002 TỔNG 30→28 (year-scores KHÔNG đổi). 16-rule cho 5.314/180≈30,
   17-rule 5.314/190≈28.
   - **Bug thật cần để ý:** `companies.risk_score` (dùng ở trang DANH SÁCH/ranking)
     là cache `max(company_year_scores)` — drift được khỏi CYS (dùng ở trang CHI
     TIẾT) khi: đổi rule không recompute toàn bộ, hoặc `run_checks` lấy max trên
     CYS năm-khác còn stale. DN_002 hiện list=30 nhưng detail=28 (lệch nội bộ).
   - **✅ ĐÃ XỬ LÝ trên live 2026-06-11** (chị OK "làm luôn"): backup
     `audit_hq.sqlite.bak-pre-cleanup-20260611-000123` → xoá DN_008 (rỗng) +
     DN_009 (trùng DN_002) → `recompute_all_scores`. Live giờ 4 DN, điểm
     **120/28/168/46**, list=detail nhất quán. **CHƯA push** STATUS này; code live
     không đổi (chỉ data score).
   - **✅ Fix code (2026-06-11):** trang danh sách giờ đọc + sort theo
     `max(company_year_scores)` thay vì field cache `companies.risk_score` →
     list không còn drift khỏi detail kể cả khi cache stale (route `list_companies`
     + `companies_list.html`; test `tests/test_companies_list.py`).
   - Còn lại (vận hành): sau mỗi lần đổi rule vẫn nên `recompute_all_scores` toàn
     bộ để cache `risk_score` + CYS năm-khác đồng bộ.

0. **Chờ chị trả lời 4 câu hỏi clarify** (góp ý 2026-06-01) rồi xử lý điểm 2/3:
   (1) phạm vi loại "x" — chỉ check nhập hay mọi check định mức; (2) nguồn định
   mức ngành cho demo (C7.1); (3) cách quy số thuế truy thu cho "trọng yếu";
   (4) quy ước ghi chú vật tư tiêu hao (KXDĐM). Điểm 2/3 → đưa vào đề án sau khi
   có câu trả lời. Xem session 2026-06-01.
0b. ✅ DONE — backfill `norms.note` "x" trên live + rerun C4.1 (291→74) +
   recompute scores. Fix C4.1 hàng nội địa (06-01) nay đã hiệu lực trên live.
1. **Verify UI tay trên live** — phần evidence lệch kỳ ĐÃ verify 06-03 (DN_001
   kỳ 2024 sạch tờ khai 2023). Còn lại: xác nhận đã sạch junk `.`/E13 (chưa làm).
   DN rác (`DN_`, `TEST`, `TEST_1`) đã xoá 06-04 → live chỉ còn 4 DN demo.
2. **✅ DN_001 (GROWATT) đã backfill tờ khai xuất + 2025 từ data-hub (06-04).**
   `data/GROWATT` (symlink) thiếu file xuất; tìm thấy trong project **data-hub**:
   `data/source_inventory/growatt-vn/2026-05-27/BaoCaoHangChiTiet ALL {NK,XK} GRW`.
   Backfill live: 2023 +1 E42, 2024 +34 E42 (C1.4 21→0 FP), 2025 0→19.898
   (nhập 19.369 + xuất 529). Item_code khớp M15 379/379, M15a 56/63.
   ✅ **DONE 06-10** — đã copy 2 file HUB ALL NK/XK vào `data/raw/GROWATT/
   multi_year/HANG_CHI_TIET/` (tên có khoảng năm) + rename file cũ `...OLD.xls`.
   Rebuild demo từ nay tự nạp đủ. Xem Recent Changes 06-10 mục 3.
3. **Bug #6 (defer)** — dynamic check denominator fallback `"nvl"` trong
   `denominators.RULE_SCOPE`. Khi có dynamic check đầu tiên publish trên
   `declaration_lines`, sẽ méo điểm. Fix sạch cần thêm `scope` field vào
   `CheckDefinition` model + migration + UI form. Ưu tiên thấp.
3. **C6.1 UX** — display 2 năm evidence có thể gây nhầm dù logic đúng.
   Cân nhắc thêm note "so sánh với kỳ N-1" ở `finding_detail.html` cho
   C6.1, hoặc group evidence theo năm với header.
4. **✅ C2.4 (tồn cuối TP âm) DONE 06-10** — `c2_balance.check_c2_4` clone từ C2.3
   sang `SpBalance`. Đã deploy code lên live. **Pending:** rerun checks trên live
   để C2.4 fire + đồng bộ điểm 2 bản (sẽ đổi findings/score live — defer theo ý chị).
5. **Edit check spec từ detail page** — hiện read-only, cần thêm edit form
   (pending từ session trước trước nữa).
6. **Demo HQ flow** — login → vào DN_003 → xem ranking + findings →
   `/danh-muc-kiem-tra` → `/admin/risk-tiers` đổi ngưỡng → quay lại DN
   thấy tier update ngay.
7. **Backlog catalog research** — Bước 2 (gap analysis vs Johnson Phase 3
   / BCQT-System / data-hub) + Bước 3 (spec chi tiết per-check). Pending
   từ session catalog-tiers-i18n.
8. **Văn bản pháp lý mở rộng** — NĐ 08/2015, TT 72/2015, TT 06/2024
   (defer, ưu tiên thấp).

## Blockers

Không có.

## Notes for Next AI Session

### Audit fix vòng 1 — đã làm gì
- Đọc 6 module check (c1..c6) + dynamic_runner + scoring + denominators +
  company_type + registry + `_resolve_evidence` + `finding_detail.html`.
- Tìm 7 bug, fix 6, defer 1. Bug C6.1 cross-year evidence user nghi không
  phải bug — C6.1 là check liên kỳ, theo thiết kế phải show 2 năm.
- `IMPORT_CODES[DNCX]` giờ chỉ `{E11, E15}` — KHÔNG có E13. E13 ở
  `MMTB_CODES` public, dùng cho C3.1 và check MMTB tương lai. Detect
  company type dùng `_DETECT_IMPORT_CODES` (gồm E13) — KHÔNG dùng cho
  rule check.
- `_make_finding` trong dynamic_runner giờ require `subject_type`
  argument. Mọi runner pass `subject_col_name` của spec (hoặc cột join).
- C1.1 / C1.4 / C1.7 ngưỡng + title đã đồng bộ giữa code, registry, catalog.
  Nếu sửa 1 chỗ → cập nhật cả 3.

### Glossary tiếng Việt (đã áp dụng nhất quán — giữ đồng bộ khi viết text mới)
- Draft/Published/Disabled → Nháp/Đã công bố/Đã tắt
- spec/DSL → đặc tả · kind → loại · tier → hạng · score → điểm
- pipeline → dây chuyền xử lý · fallback → dự phòng · timeout → thời gian chờ
- admin (vai trò) → quản trị viên · upload → tải lên · preview → xem trước
- API Key → Mã API · refresh → nạp lại · debug → gỡ lỗi
- (UOM) canonical → đơn vị chuẩn · family → nhóm · alias → bí danh ·
  base factor → hệ số quy đổi · code → mã (áp dụng `admin_units.html`)
- Giữ: BCQT, M15/M15a/M16, BCCT, TKXNK, NVL, TP, HS, MST, A42, E11-E62, AI, JSON, API, HTTP

### Đổi ngưỡng tier
- Mặc định: 50/100/300/600/1000 (hardcoded trong `app.app_settings.DEFAULT_RISK_TIER_UPPERS`).
- Admin sửa runtime ở `/admin/risk-tiers`. Bảng `app_settings` row `risk_tier_uppers`.
- Đổi ngưỡng KHÔNG re-run check — tier compute lúc view qua `tier_for(score)`.

### Local DB
- **Sau resync 06-10: đúng 4 DN ẩn danh** (DN_001–004), 0 tên thật. Điểm
  116/28/148/46 (code 17-rule). 770 findings + inject DN_003. GROWATT đầy đủ.
- Backup pre-resync: `audit_hq.sqlite.bak-pre-resync-20260610-213107` (38MB, state
  cũ lẫn 5 công ty thật + 4 DN_xxx mồ côi — KHÔNG dùng lại trừ khi cần debug).
- Backup cũ hơn: `audit_hq.sqlite.bak-pre-audit-fix-20260527-201520`.
- **Lesson: trước khi `rm audit_hq.sqlite*`, backup trước:** `cp audit_hq.sqlite audit_hq.sqlite.bak-$(date +%Y%m%d-%H%M%S)`.
- **Lesson 06-10:** đừng `run_all` (ingest công ty thật) ĐÈ lên DB đã anonymize —
  tạo state lẫn lộn real + DN_xxx mồ côi. Quy trình đúng: wipe → ingest → anonymize.

### Tinsu DB
- Backup pre-fix (audit vòng 1):
  `~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite.bak-pre-audit-fix-20260527-232133`.
- Cleanup + rerun chạy qua `docker exec audit-hq-mvp python -c "..."`.
- **Live KHÔNG có Excel raw** (policy bảo mật/dung lượng) → không re-ingest từ
  file được. Khi cần sửa dữ liệu Tầng 1 trên live: khôi phục bảng từ backup rồi
  lọc bằng SQL/script trong container, KHÔNG chạy `run_all`/`ingest`. (Đây là
  cách session 06-03 dọn `declaration_lines` lệch kỳ.)
- **Chạy script file trong container:** cwd=/app nhưng `python /tmp/x.py` đặt
  sys.path[0]=/tmp → `import app` fail. Phải `docker exec -e PYTHONPATH=/app
  -w /app ... python /tmp/x.py` (hoặc dùng `python -c`).

### ⚠️ GOTCHA: `run_checks(only={...})` xóa luôn COMBO findings
- `run_checks(code, year, only={"C4.1"})` wipe cả COMBO_* nhưng KHÔNG tái tạo
  (combo chỉ chạy khi `only is None`). Hậu quả: chạy 1 check lẻ → mất hết combo
  → điểm tụt sai (06-03 DN_001 127→55 ảo). **Luôn rerun full `run_checks(code,
  year)` (only=None) rồi recompute_all_scores** khi muốn điểm đúng.

### Backfill norms.note "x" lên live (06-03) — cách đã dùng
- anonymize.py **giữ nguyên material_code/product_code** (chỉ ẩn company/NCC) →
  map note qua `db-data/anonymize_mapping.json` (DN_xxx→real) + (year, pc, mc).
- Parse M16 thật bằng `discover`+`parse_m16` (adapter mới đọc note) → JSON
  {dn,year,pc,mc,note} chỉ dòng có note → docker cp vào container → UPDATE theo
  (company_id, period_year, product_code, material_code). 11 cặp khớp 100% số dòng.
- Tương lai rebuild demo: flow `ingest (adapter mới điền note) → anonymize (giữ
  note)` sẽ tự mang note sang, không cần backfill tay nữa.

### Workflow rerun checks trên tinsu (không full re-ingest)
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu

# Backup
cp ~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite \
   ~/audit-hq-mvp-deploy/db-data/audit_hq.sqlite.bak-$(date +%Y%m%d-%H%M%S)

# Inline cleanup + rerun
docker exec audit-hq-mvp python -c "
from app.pipeline.run_checks import run_checks
pairs = [('DN_001',2023),('DN_001',2024),('DN_001',2025),
         ('DN_002',2024),('DN_002',2025),
         ('DN_003',2021),('DN_003',2022),('DN_003',2023),('DN_003',2024),('DN_003',2025),
         ('DN_004',2024)]
for code, year in pairs:
    s = run_checks(code, year)
    print(f'{code} {year}: {s.total} findings score={s.risk_score}')
"
```

### Workflow re-ingest fresh local
```bash
# Stop dev server trước (file lock SQLite WAL).
kill $(pgrep -f "uvicorn.*8200")

# 1. Wipe business data, giữ users/ai_settings/app_settings.
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('audit_hq.sqlite')
for t in ['findings','company_year_scores','nvl_balances','sp_balances','norms','declaration_lines','companies']:
    c.execute(f'DELETE FROM {t}')
c.commit()
"

# 2. Ingest + run checks 4 DN whitelist (HONG_AN/GROWATT/KIM_LONG/DO_THANH).
.venv/bin/python -m app.pipeline.run_all

# 3. Anonymize TRƯỚC inject (inject expects DN_003).
.venv/bin/python -m scripts.anonymize

# 4. Inject demo findings vào DN_003 (HONG_AN 2024).
.venv/bin/python -m scripts.inject_findings

# 5. Re-run checks DN_003 2024 + recompute scores.
.venv/bin/python -m app.pipeline.run_checks --company DN_003 --year 2024
.venv/bin/python -m scripts.recompute_all_scores

# 6. Restart dev.
nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8200 > /tmp/uvicorn-8200.log 2>&1 &
```

### Deploy manual (vẫn dùng được nếu CI fail)
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
cd /home/tinsu/actions-runner-audit-hq/_work/audit-hq-mvp/audit-hq-mvp
git pull origin main
DB_DATA_PATH=/home/tinsu/audit-hq-mvp-deploy/db-data \
BUILD_SHA=$(git rev-parse --short HEAD) \
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
AUTH_USER=admin AUTH_PASSWORD=admin \
docker compose up -d --build
```

**CRITICAL**: `DB_DATA_PATH` bắt buộc. Quên → volume rỗng → 0 DN.
**CRITICAL**: Sửa migration file → phải `--build` mới có hiệu lực.

### Runner work dir EACCES (fix một lần, có thể tái phát)
Nếu CI `actions/checkout@v5` fail `permission denied unlink db-data/audit_hq.sqlite-shm`:
```bash
ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu
docker run --rm \
  -v ~/actions-runner-audit-hq/_work/audit-hq-mvp/audit-hq-mvp/db-data:/x \
  alpine sh -c "rm -rf /x/*"
```

### Tests
- 439 pass. Conftest có autouse session fixture `create_all` trên default engine — không cần test_smoke chạy trước.
- C2.4 (06-10): `test_c2_4_no_fire_when_zero_or_positive` + `test_c2_4_fires_when_closing_negative`.
  Sửa kèm: `test_catalog_has_49_entries` (mvp 16→17, wip 14→13) + `test_score_combo_bonus_one_shot` (max_raw 16→17 rule → 111→105).
- Test mới sau audit fix vòng 1:
  - `tests/test_normalize_code.py` (21 parametrize)
  - `test_c1_2_ignores_mmtb_E13_for_dncx`
  - `test_c1_1_fires_info_when_diff_under_5pct` + `_under_floor`
  - `test_c1_4_fires_info_when_diff_under_1pct` + `_under_floor`
  - `test_range_band_and_semantics` (dynamic runner)
  - `test_finding_has_evidence_and_subject_type` (dynamic runner)

### Recompute scores trên prod
```bash
docker compose exec -T app python -m scripts.recompute_all_scores
```

### BATCH_RUN cho nhiều DN
```python
# docker compose exec -T app python -c "..."
from app.database import SessionLocal
from app.jobs import enqueue_job
from app.models import Company, User
from app.models.job import JobKind
from sqlalchemy import select

with SessionLocal() as s:
    admin = s.scalar(select(User).where(User.username=='admin'))
    for code in ['DN_001','DN_002','DN_003','DN_004']:
        c = s.scalar(select(Company).where(Company.code==code))
        enqueue_job(s, kind=JobKind.BATCH_RUN, payload={'company_code': code},
                    created_by=admin.id, company_id=c.id, period_year=None)
```

### Hạ tầng cố định
- Cloudflare tunnel `tinsu-online-server` remotely-managed, không sửa file local.
- WSL ssh broken → dùng `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`.
- Mỗi route module có Jinja2Templates instance riêng (chưa refactor).
- `make lint` chạy `ruff check app tests scripts`, KHÔNG check migrations.
- Test pattern: `_setup_db()/_teardown()` với StaticPool in-memory SQLite; admin cookie via `make_session_cookie()`.

### Disclaimer pháp lý — wording đã chốt
> "Đây là chỉ số rủi ro dữ liệu BCQT do Audit-HQ tính từ phát hiện chênh lệch giữa các báo cáo. KHÔNG phải đánh giá tuân thủ pháp luật theo Thông tư 81/2019/TT-BTC. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan."
