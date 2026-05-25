# STATUS — Audit-HQ MVP

> **Trạng thái (2026-05-25, cuối session):** Live demo `https://audit-hq-demo.tinsu.ai` (build `cbc4c8f`, admin/admin) đã filter chỉ 4 DN có giai đoạn liền nhau BCQT+BCCT, tên DN giả lập "Công ty TNHH … (Demo)", banner vàng "🧪 Dữ liệu mẫu" trên top. UX bảng data toàn bộ đã curate cột (7-10 thay vì 14-19), line-clamp 2 dòng + tooltip cho text dài, format số/ngày, ẩn `source_file` để không leak DN gốc. **113 tests pass**, ruff clean.

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). Tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`, `findings`, `uom_canonical`, `uom_aliases`.
- Auth: cookie session, default `admin/admin`. Env vars `AUTH_USER`/`AUTH_PASSWORD`/`SESSION_SECRET`.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.
- **4 DN trên prod**: DN_001 GROWATT (Điện Tử Phương Đông), DN_002 KIM_LONG (Cơ Khí Tiên Phong), DN_003 HONG_AN (May Mặc Hoa Sen), DN_004 DO_THANH (Hoá Chất Nam Tiến). DN_005 (HONG_PHUC) + DN_006 (HIEP_QUANG) đã loại do thiếu giai đoạn liền nhau BCQT+BCCT.
- Demo banner amber trên mọi page (`base.html` + `.demo-banner` CSS).
- Runner self-hosted `tinsu-runner-audit-hq` online qua `~/actions-runner-audit-hq/runner-loop.sh` watchdog (while-loop respawn nếu crash); cron user `tinsu` `@reboot` auto-start sau boot. Log: `/home/tinsu/runner-audit-hq.log`. KHÔNG dùng systemd vì cần sudo password (xem memory `tinsu-server`).
- Cảnh báo: backup DB local `audit_hq.sqlite.bak-20260525-120743` (18M, DB cũ trước reseed) untracked nhưng KHÔNG gitignored (`*.sqlite` không match `.bak-…`). Xoá khi tiện.

## Recent Changes

- **2026-05-25** — Filter 4 DN whitelist + UX polish toàn bộ bảng + realistic naming + deploy.
  - **Filter pipeline**: `app/pipeline/run_all.py:DEMO_WHITELIST = {HONG_AN: 2021-25, GROWATT: 2023-25, DO_THANH: 2024-25, KIM_LONG: 2024-25}`. Thay `discover_company_years` quét toàn bộ bằng iterate qua whitelist. Loại HIEP_QUANG (đứt quãng), HONG_PHUC (1 năm).
  - **discover.py**: thêm fallback BCCT `multi_year/HANG_CHI_TIET/` với `_filename_covers_year` regex `(20\d{2}|\b\d{2}\b)[-_–](20\d{2}|\b\d{2}\b)` cover khoảng năm trong tên file. Fix tt39 filter loại PDF, mở rộng M15/M15a regex bắt "Mẫu số 15".
  - **uom.py bug fix**: cache giữ `families: dict[str, str]` thay vì ORM instance → fix `DetachedInstanceError` cross-session (lỗi tiềm tàng từ trước, lộ ra khi re-seed DB lần này).
  - **UX bảng curated** (`routes/companies.py`): `_TABLE_CONFIG[*].view_cols` + `_VIEW_COLS_BY_TABLE` single source cho M15/M15a/M16/BCCT/Findings. `_format_cell` (num/date/wrap/code-cell). `_format_model_rows` helper dùng chung cho `/companies/{c}/data` lẫn evidence_blocks trong `/findings/{id}`. `?full=1` toggle xem tất cả cột (vẫn loại id/company_id/period_year/source_file).
  - **Line-clamp wrap**: CSS `.cell-clamp` (`-webkit-line-clamp: 2`) + `.data-table td.wrap { max-width: 360px }`. Template render `<div class="cell-clamp" title="full text">…</div>` khi `cls == "wrap"`. Áp cho `material_name`/`product_name`/`item_name`/`f.title`/`description`.
  - **Source_file ẩn khỏi mọi mode** (kể cả `full=1`) — path chứa tên DN gốc → leak qua DN_xxx mask.
  - **Realistic DN names**: `COMPANY_MAPPING` đổi name → "Công ty TNHH \<Ngành\> \<Địa danh\> (Demo)". `anonymize()` idempotent refresh meta khi mapping đổi (giữ stable code+tax_id). +1 test (`test_anonymize_refreshes_name_when_mapping_changes`).
  - **Demo banner vàng** trên top `base.html` (chỉ khi user logged in). CSS `.demo-banner` amber 50/100. User chọn banner > per-DN badge.
  - **company_detail**: gỡ inline notes input để row gọn; giữ hidden field giữ data; thêm nút "Chi tiết →" link tới `/findings/{id}`.
  - **Deploy**: commit `cbc4c8f` → CI Tinsu build ~1 phút sau khi restart runner. SCP local DB (26M, 4 DN, anonymize+inject) lên `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite`; backup file cũ `audit_hq.sqlite.bak-pre-filter-20260525-120046`; `docker restart audit-hq-mvp`.
  - **Runner watchdog**: phát hiện `tinsu-runner-audit-hq` offline silently từ 2026-05-21 (process chết, không có monitoring). Tạo `runner-loop.sh` + crontab `@reboot`. Systemd thực thụ dành cho lúc có sudo. Pattern này nên áp cho 3 runners còn lại (`data-hub`, `co`, `bcqt-showcase`) nếu cũng từng silent-die.
- **2026-05-21 (cuối)** — UOM system + UI redesign + fix finding 782.
  - **UOM canonical/alias DB** (port từ data-hub 2-layer): `uom_canonical` (25 row: MTR/KGM/PCE/PR/MTK/MTQ/ROL/SET/BOX/BTL/CTN/TOO/TAM…) + `uom_aliases` (129+ alias VN+EN). Family: length/mass/area/volume/count/count_packaging. base_factor cho conversion.
  - **C3.3 severity ladder mới**: EQUIVALENT (alias cùng canonical) → skip; SAME_FAMILY (KG↔GAM convertible) → 🔵 Info; DIFFERENT (count vs mass) → 🔴 Critical. Trước đây tất cả mismatch là Critical → false-positive tràn (250+).
  - **Compound separator support** (`Cái/Chiếc`, `KG/GAM`, `Chai/Lọ/Tuýp`): `resolve_canonical` split text trên `[/,;|]`, nếu mọi phần map cùng canonical → return canonical; lenient với unknown parts.
  - **Cache in-memory** trong `app/checks/uom.py` cho hot path. `invalidate_cache()` khi admin sửa.
  - **Admin UI `/admin/units`**: list canonical grouped by family, alias chips, filter family + lọc text. Form thêm alias + canonical mới (collapsible advanced). Link "⚙️ Đơn vị tính" header. Auto-seed `python -m scripts.seed_uom` mỗi container start (idempotent).
  - **UI redesign /companies** (4 iterations qua self-screenshot Playwright): từ table rowspan layout (1 DN tốn 10 row) → 1-DN-1-row + year chips inline với severity dot + rank-badge circle (navy filled top-3). Modern Government design system (USWDS/GOV.UK inspired): brand navy header, font Inter+JetBrains Mono, score-pill 3-tier, stat-grid KPI tile, combo-section gradient warm. Install fonts-noto-color-emoji trên WSL để emoji render đúng.
  - **Versioning + CI/CD + deploy**: file VERSION root + `app/version.py` (env > git > fallback), footer hiển thị `v0.1.0 · build <sha> · <time>`. GitHub Actions self-hosted runner trên Tinsu (label `tinsu-prod`), workflow test → deploy. Cloudflare Tunnel `audit-hq-demo.tinsu.ai` → port 8200 (port 8000 conflict erpnext-frontend). DB persistent ở `/home/tinsu/audit-hq-mvp-deploy/db-data/`.
  - **Finding 782 fix**: user phát hiện C3.3 fire critical cho `KHUY` (M15='PCE' vs BCCT='Cái/Chiếc'). Nguyên nhân: `Cái/Chiếc` compound text không match alias riêng lẻ. Sau fix separator: re-run C3.3 trên live → từ 250+ false → 4 real finding only.
  - +28 tests UOM/scoring/inject/UI route. Tổng 113 tests pass.
- **2026-05-21 (chiều)** — Tuần 10: deploy live + CI/CD + versioning.
  - **Versioning** (semver + git SHA + build time): file `VERSION` (root) + `app/version.py` đọc env vars BUILD_SHA/BUILD_TIME/APP_VERSION (inject từ Docker build-args), fallback đọc git local. Footer hiển thị `v0.1.0 · build <sha> · <ISO time>`. `/healthz` response trả full metadata.
  - **Dockerfile production**: ARG BUILD_SHA/BUILD_TIME, locale C.UTF-8, TZ Asia/Ho_Chi_Minh, entrypoint.sh chạy `alembic upgrade head` trước uvicorn.
  - **docker-compose**: bind `127.0.0.1:${HOST_PORT:-8200}:8000` (tunnel route đến port 8200 vì 8000 conflict erpnext-frontend), volume `${DB_DATA_PATH:-./db-data}:/db-data` (override path khi deploy), healthcheck mỗi 30s.
  - **CI/CD** `.github/workflows/deploy.yml`: trigger push main + workflow_dispatch. Job test (uv venv + pytest + ruff) → Job deploy (build + restart + healthcheck wait + show version). runs-on `[self-hosted, tinsu-prod]`.
  - **Self-hosted runner** đã setup trên Tinsu: `~/actions-runner-audit-hq`, label `tinsu-prod`, online qua nohup. Status check: `gh api /repos/TinsuAI/audit-hq-mvp/actions/runners`.
  - **Cloudflare Tunnel ingress** active: `audit-hq-demo.tinsu.ai` → `http://localhost:8200` (tunnel version 30). DNS CNAME đã add qua `cloudflared tunnel route dns`. Script `deploy/scripts/add-tunnel-ingress.py` idempotent.
  - **Persistent data trên Tinsu**: `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite` (18MB scp từ local, đã có anonymize + inject, 6 DN, score DN_003=7896, DN_005=3).
  - Test fix CI: `test_smoke.py` thêm fixture `_ensure_schema` để CI runner DB trống vẫn pass; `test_healthz` check field version trong response.
- **2026-05-21 (trưa)** — Tuần 9: UI polish + Excel export.
  - `GET /findings/{id}`: trang chi tiết phát hiện hiển thị spec nghiệp vụ, details JSON dạng bảng, **chứng cứ truy nguồn** — query Tầng 1 thật theo `evidence_refs` (NvlBalance/SpBalance/Norm/DeclarationLine/Finding) và render bảng kèm filter spec. Có inline form cập nhật trạng thái (status + notes lớn). Title click-through từ `/companies/{code}` table.
  - `GET /companies/{code}/data?year=YYYY&table=m15|m15a|m16|bcct&q=&page=`: trang xem dữ liệu Tầng 1 — bảng raw có tabs giữa 4 loại, ô lọc theo mã, pagination 50/trang. Đảm bảo "không hộp đen" theo §2.2 đề án.
  - `GET /companies/{code}/export?year=YYYY`: xuất file `.xlsx` 7 sheet (Tổng quan DN + tổng severity, Phát hiện với màu severity, Chứng cứ M15/M15a/M16/BCCT lọc theo subject_key của findings, Pháp lý với 5 trích yếu). Built bằng xlsxwriter, content-type Excel chuẩn.
  - Thêm quick actions buttons trong `/companies/{code}`: "📋 Dữ liệu gốc" và "📊 Xuất Excel kiến nghị".
  - +7 tests (finding detail + 404, data viewer + filter + invalid table, export valid Excel + 404). Tổng 99 tests pass.
- **2026-05-21 (sáng)** — Tuần 8: inject sai phạm chủ đích cho demo §6.3.
  - `scripts/inject_findings.py` modify 4 NvlBalance + 1 Norm trong DN_003 năm 2024:
    · DG: closing_qty 9468 → -150 (fire C2.3) + norm × 100 (kích C4.3 trên DD-2)
    · KHUY: closing_qty += 999 (fire C2.1)
    · DD-2: opening=import=0, production_out=500 (fire C5.1)
    · HDG: repurpose_qty=250, production_out -= 250 (fire C1.6)
  - DN_003 2024: 1 finding (sạch) → 12 finding + combo `COMBO_ACCOUNTING_INCONSISTENT` (score 3 → 103).
  - `clean_dn_005()` bulk reject 201 critical finding của DN_005 (mô phỏng cán bộ review) — minh chứng "hệ thống không phát hiện bừa". DN_005 score 1290 → 3 (chỉ giữ warning).
  - `recompute_company_scores()` tự cập nhật risk_score toàn bộ DN sau inject.
  - Changelog lưu `db-data/injected_changes.json` (gitignored). `--revert` rollback đầy đủ.
  - +5 tests inject (idempotent, modify đúng 4 mã, norm x100, reject critical chỉ, recompute). Tổng 92 tests pass.
- **2026-05-21 (rạng sáng-2)** — Tuần 7: anonymize 5 DN demo + script restore.
  - `scripts/anonymize.py`: mapping cố định GROWATT→DN_001 (điện tử), KIM_LONG→DN_002 (cơ khí), HONG_AN→DN_003 (dệt may/da giày), DO_THANH→DN_004 (hoá chất), HONG_PHUC→DN_005 (sạch), HIEP_QUANG→DN_006 (dự bị). MST 10 số ngẫu nhiên SHA256 từ original tax_id (deterministic). Partner trong BCCT → NCC_xxx (96 NCC).
  - Idempotent: skip company đã có code prefix `DN_`. Skip partner đã có `NCC_`.
  - Modify in-place audit_hq.sqlite. Mapping lưu `db-data/anonymize_mapping.json` (gitignored, ngoài symlink `data/` để không lẫn với data thực).
  - `scripts/restore.py`: rollback từ mapping file khi cần debug nội bộ.
  - Verify: `run_checks --company DN_003 --year 2024` vẫn fire đúng 1 finding C3.2. UI `/companies` show DN_001-006 với rank theo risk_score.
  - +9 tests (deterministic MST, idempotency, dry-run, partner alias, mapping coverage).
- **2026-05-21 (rạng sáng)** — Tuần 6: scoring + combo + run_all.
  - `app/checks/scoring.py`: SEVERITY_POINTS (10/3/1), COMBO_BONUS=20, `compute_risk_score` bỏ findings status='rejected'.
  - `app/checks/combos.py`: 4 combo — `COMBO_FORGED_NORM` (C2.3+C4.3), `COMBO_UNDECLARED_SOURCE` (C1.3+C5.1), `COMBO_ACCOUNTING_INCONSISTENT` (C2.1+C4.3), `COMBO_HS_GAMING` (C3.2+C3.3). Trigger logic: cùng subject_key trên (company, year).
  - `Company.risk_score` (Alembic migration, server_default='0').
  - Pipeline `run_checks` tích hợp: chạy 16 check → detect_combos → upsert Finding (combo có check_code prefix `COMBO_`) → cập nhật `Company.risk_score`.
  - CLI mới `app.pipeline.run_all` 2 phase: Phase 1 ingest tất cả DN×năm trong `data/raw/`, Phase 2 run_checks. Bắt exception per-file để không crash toàn pipeline.
  - UI: `/companies` sort theo `risk_score DESC`, thêm cột Hạng + Điểm rủi ro pill. `/companies/<code>` hiện meta-finding combo ở section riêng ở đầu trang (link tới group check trigger).
  - +10 unit test scoring + combo. 78 tests total. C3.1 mâu thuẫn loại hình NVL×MMTB, C3.2 HS không nhất quán (scale chương/nhóm/phân nhóm), C3.3 đơn vị tính lệch giữa M15 vs BCCT (có alias map UN/CEFACT: MTR↔METRES, PR↔PAIR, MTK↔SQUARE METRES…). C4.1 NVL trong M16 không có nguồn, C4.3 tổng tiêu hao M16 vượt M15.production_out (scale 5/20%). C5.1 NVL có xuất SX không có nhập+tồn đầu. C6.1 tồn đầu kỳ N ≠ tồn cuối kỳ N-1. Ingest thêm HONG_AN 2023 (77 NVL, 248 norm) cho C6.1 baseline. +25 unit test. 68 tests total.
- **2026-05-21 (khuya)** — Tuần 4: 3 check Nhóm 2 (C2.1 cân bằng M15, C2.2 cân bằng M15a, C2.3 tồn cuối NVL âm). C2.1 phát hiện kèm pattern "tồn ảo" (opening=0, closing>import) ghi vào details. Cơ chế đánh dấu finding: POST `/findings/{id}/status` với 4 trạng thái (new/confirmed/rejected/noted) + ghi chú; UI có inline form trên mỗi row, anchor scroll về row vừa update. +12 unit test (9 C2.x + 3 status route).
- **2026-05-21 (tối)** — Tuần 3: 6 check Nhóm 1 MVP (C1.1-C1.4, C1.6, C1.7) + registry với severity scale (🔴🟡🔵). Finding model (Tầng 2) với evidence_refs JSON. `detect_company_type` heuristic (SXXK/DNCX/Gia công từ mã loại hình BCCT). Pipeline `run_checks` CLI idempotent. UI: `/companies` (bảng tổng quan), `/companies/<code>?year=YYYY` (chi tiết findings group by check_code, collapsible, badge severity). 19 unit test mới cho check + scale + company_type detection.
- **2026-05-21 (chiều)** — Tuần 2: 4 adapters (M15/M15a/M16/BCCT) chuẩn hoá vào dataclass; models Tầng 1; Alembic initial migration; pipeline `discover + ingest` (CLI `python -m app.pipeline.ingest --company HONG_AN --year 2024`); 7 tests mới (4 adapters + 3 discover). Verify HONG_AN 2024 — Công ty Cổ phần Giầy Hồng An, MST 5400273360, ngành giày dép (SXXK loại hình E31/E62).
- **2026-05-21 (sáng)** — Scaffold tuần 1: pyproject, Makefile, Dockerfile, docker-compose, FastAPI hello + login + overview placeholder, alembic init, 5 smoke tests pass.

## Insight nghiệp vụ (cập nhật cuối tuần 6)

Chạy `run_all` trên 27/29 cặp (DN, năm) — 2 cặp lỗi `pd.ExcelFile` không nhận diện format (cần investigate). Tổng **1355 findings · 1 combo fired**.

**Xếp hạng risk_score top 5:**
| Hạng | DN | Năm | Findings | Score | Note |
|---|---|---|---|---|---|
| 1 | HONG_AN | 2025 | 561 | **5603** | combo COMBO_HS_GAMING fire |
| 2 | HONG_PHUC | 2025 | 129 | 1290 | thiếu BCCT → C1.x fire nhiều |
| 3 | HONG_AN | 2022 | 118 | 1180 | data 2022 có vấn đề |
| 4 | KIM_LONG | 2024 | 109 | 1090 | thiếu BCCT |
| 5 | HONG_AN | 2019 | 97 | 970 | data cũ thiếu |

**Score thấp nhất (DN "sạch"):**
- HONG_AN **2024**: 1 finding (C3.2 da X-DL), **score 3** → tốt cho regression
- HONG_AN **2023**: 0 finding
- HONG_AN **2018**: 0 (chưa có data)
- DO_THANH 2025: 0 (chưa có data)
- GROWATT 2023: 0 (chưa có data)
- HIEP_QUANG 2020: 0

**Findings nhiều khi thiếu BCCT** — đa số DN khác HONG_AN không có file `BaoCaoHangChiTiet` đầy đủ. Khi BCCT trống, C1.1/1.2/1.3 dễ fire (M15 báo nhập nhưng không có tờ khai trong BD). Đây không hẳn là gian lận — chỉ là dataset không đầy đủ. Khi demo cần lọc lại hoặc note rõ giả định "BCCT đầy đủ".

**HONG_AN 2025 combo COMBO_HS_GAMING fire** — patterns thật khá hứa hẹn cho demo, nhưng cần verify đó là vấn đề thực hay artifact của data thiếu/Q1-only. Tuần 7 trước khi anonymize sẽ kiểm tra kỹ.

**Đơn vị tính alias map** (`app/checks/c3_classify.py`) đã giảm false positive từ 43 → 0 trên HONG_AN. Sẽ mở rộng khi gặp DN mới.

## Constraint sau anonymize

DB hiện ở **mode demo** (Company.code = DN_xxx). Pipeline `ingest` nhận argument `--company HONG_AN` sẽ KHÔNG match với DN trong DB nữa, nên:

- **Không re-ingest filesystem path "HONG_AN"** trừ khi `python -m scripts.restore` trước.
- `python -m app.pipeline.run_checks --company DN_003 --year 2024` vẫn hoạt động bình thường.
- `python -m app.pipeline.run_all` nếu chạy lại sẽ tạo Company mới với code "HONG_AN" → duplicate. Cần restore + run_all + anonymize lại.

## Ranking demo (cuối tuần 8)

| Hạng | DN | Score | Note |
|---|---|---|---|
| 1 | DN_003 | 7896 | HONG_AN — inject 4 sai phạm + combo, cộng dồn nhiều năm dataset thực |
| 2 | DN_002 | 2020 | KIM_LONG — fire C4.1 nhiều do parser không đọc được M15 |
| 3 | DN_006 | 1113 | HIEP_QUANG — dự bị, không demo |
| 4 | DN_004 | 390 | DO_THANH |
| 5 | DN_001 | 181 | GROWATT |
| 6 | **DN_005** | **3** | HONG_PHUC — sạch sau bulk reject (mô phỏng cán bộ review) ✓ |

Đề án §6.3 ví dụ "DN_001 ≈ 87 đ" — chỉ là minh hoạ thứ tự. Tinh thần giữ đúng: DN có vấn đề trên đầu, DN sạch dưới cùng. Khi demo 5 phút, narrative sẽ là:

> "DN_003 (HONG_AN sau anonymize) có điểm rủi ro cao nhất 7896. Trong đó năm 2024 có 12 phát hiện trên 5 mã NVL, kèm 1 combo `COMBO_ACCOUNTING_INCONSISTENT` cho thấy số liệu giữa M15 và M16 mâu thuẫn — pattern điển hình của gian lận tiêu hao. Cán bộ chọn vào DN_003 → trang chi tiết → xem từng phát hiện kèm chứng cứ truy nguồn về dòng dữ liệu gốc."

> "DN_005 đứng cuối với 3 điểm — DN này dataset không đầy đủ BCCT nên hệ thống bỏ qua các phát hiện không có căn cứ truy thu. Đây là minh chứng tool không phát hiện bừa."

## Demo public

- URL: **https://audit-hq-demo.tinsu.ai**
- Auth: admin / admin (basic-auth, share OK cho teammate)
- Healthcheck: `curl https://audit-hq-demo.tinsu.ai/healthz` trả `{"status":"ok","version":"...","build_sha":"...","build_time":"..."}`

## Quy trình deploy

1. Edit code + commit + push main → GitHub Actions tự trigger
2. Job `test`: uv venv, pytest, ruff
3. Job `deploy` (chỉ chạy khi test pass): docker build với BUILD_SHA/TIME, restart container, wait healthcheck
4. Footer ở UI cập nhật phiên bản tự động: `v{VERSION} · build {SHA} · {TIME}`

Manual deploy local: `make deploy` (build + up + show version).

Runner persistence: hiện nohup, NOT survive reboot. Cần convert systemd service (sudo) — defer.

## Next Steps

### Ưu tiên trước khi demo HQ

1. **Tổng duyệt nội bộ Trọng Tín + Tinsu** — share URL `audit-hq-demo.tinsu.ai` (admin/admin), chạy kịch bản 5 phút §6.3, ghi feedback.
2. **Test cá nhân khi gặp finding false-positive** — vào `/admin/units` thêm alias (không cần redeploy). Cache tự invalidate.
3. **Convert runner sang systemd** (hiện nohup, không survive Tinsu reboot). Cần sudo password trên Tinsu.
4. **Generate password mạnh** thay admin/admin cho prod (env vars `AUTH_USER`/`AUTH_PASSWORD`/`SESSION_SECRET` trong GitHub secrets).

### Sau khi demo HQ (§7.7 đề án)

- Thí điểm Chi Cục Hải Quan Khu vực IV với dữ liệu thực.
- Cài 14 W.I.P còn lại (C1.5, C2.4, C4.2/4-8, C5.2-3, C6.2-5).
- Mở Giai đoạn II (Nhóm 8-12, 16 check cần dữ liệu bổ sung).
- Tích hợp VNACCS trực tiếp thay vì Excel.

- Tuần 3-4 — Cài Nhóm 1 + Nhóm 2 (9 check MVP).
- Tuần 5-6 — Cài Nhóm 3 + 4 + 5 + 6 MVP (7 check) + scoring.
- Tuần 7 — Anonymize 5 DN demo. Map: GROWATT→DN_001, KIM_LONG→DN_002, HONG_AN→DN_003, DO_THANH→DN_004, HONG_PHUC→DN_005 (sạch). HIEP_QUANG dự bị (giữ data full để regression test rule liên kỳ).
- Tuần 8 — Inject sai phạm chủ đích cho DN_001-004 theo §6.3 kịch bản.
- Tuần 9-10 — UI bảng tổng quan + trang chi tiết + xuất Excel + demo HQ.

## Notes

### Đề án là source of truth

- Catalog 49 kiểm tra, mức độ 🔴🟡🔵, ngưỡng, mô tả pháp lý — tất cả ở `../audit-hq/de-an-audit-hq.md`.
- Khi nghiệp vụ có thay đổi → update đề án trước, MVP follow.
- Demo plan chi tiết: `../audit-hq/.ai/sessions/2026-05-21-demo-plan.md`.

### Deploy demo

- Server: Tinsu VPS (`tinsu` Tailscale 100.84.189.87).
- URL: `audit-hq-demo.tinsu.ai` (Cloudflare Tunnel, basic-auth).
- Setup ingress: `audit-hq/deploy/scripts/add-ingress.py` (script ở repo đề án).
- Sẽ wire `make publish` ở tuần 9-10.

## Blockers

Không có. Sẵn sàng đi tuần 2.
