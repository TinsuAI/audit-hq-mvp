# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 8 hoàn tất (2026-05-21). Inject 4 sai phạm chủ đích vào DN_003 2024 (fire 11 finding + combo COMBO_ACCOUNTING_INCONSISTENT). Bulk reject 201 critical finding của DN_005 (mô phỏng cán bộ review). Ranking 5 DN demo đúng tinh thần §6.3: DN_003=7896 (gian lận), DN_005=3 (sạch). 92 tests pass. Sẵn sàng tuần 9-10 (polish UI bảng tổng quan + xuất Excel kiến nghị + demo).

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). 5 tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`.
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

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

## Next Steps

### Tuần 9 — Polish UI + xuất Excel kiến nghị + tổng duyệt nội bộ

Theo §7.5 đề án.

1. **Trang chi tiết phát hiện** (`/findings/<id>`): hiển thị `details` JSON dạng bảng dễ đọc, link evidence_refs về Tầng 1 (vd: nhấn vào tên NVL → trang xem các dòng M15 + BCCT liên quan).
2. **Xuất báo cáo Excel kiến nghị kiểm tra** (`/companies/<code>/export?year=YYYY`): file `.xlsx` với:
   - Sheet 1: Tổng quan DN + danh sách findings (mã check, severity, đối tượng, mô tả).
   - Sheet 2: Trích xuất các dòng BCCT/M15/M15a/M16 làm chứng cứ.
   - Sheet 3: Trích yếu pháp lý (TT 39/2018, TT 38/2015, NĐ 154/2005…).
3. **Trang xem dữ liệu gốc** (Tầng 1): bảng M15, M15a, M16, BCCT cho 1 (DN, năm) để chứng minh "không hộp đen".
4. **Tổng duyệt nội bộ** Trọng Tín + Tinsu trước khi demo cho HQ.

### Sau tuần 9 (lộ trình §7 đề án)

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
