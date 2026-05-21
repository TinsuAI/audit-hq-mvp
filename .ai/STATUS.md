# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 6 hoàn tất (2026-05-21). Risk scoring (§2.6, 10/3/1 + combo 20đ) + 4 combination signatures (§2.7) + CLI `run_all` orchestrate ingest+check toàn bộ 6 DN × 11 năm. Chạy `run_all` trên dataset thực sinh **1355 findings · 1 combo (COMBO_HS_GAMING trên HONG_AN 2025)**. 78 tests pass, ruff clean. Hoàn tất §7.3 (Tuần 5-6). Sẵn sàng tuần 7-8 (anonymize 5 DN demo + inject sai phạm chủ đích).

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). 5 tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`.
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

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

## Next Steps

### Tuần 7 — Anonymize 5 DN demo

Theo `audit-hq/.ai/sessions/2026-05-21-demo-plan.md` mục 4.7.

1. **Script `scripts/anonymize.py`** với mapping (đã chốt 2026-05-21):
   - GROWATT → **DN_001** (điện tử HS 85 nominal — sẽ verify nội dung)
   - KIM_LONG → **DN_002** (cơ khí HS 84)
   - HONG_AN → **DN_003** (dệt may HS 61 — case study cúc áo C4.4 khi sang Giai đoạn II)
   - DO_THANH → **DN_004** (hoá chất HS 39)
   - HONG_PHUC → **DN_005** (sạch — không inject sai phạm)
2. **Anonymize fields** theo §6.2 đề án:
   - Tên DN → `DN_xxx` (chỉ trong DB; data/raw vẫn nguyên bản)
   - MST → dãy 10 số ngẫu nhiên có seed cố định
   - Partner (NCC) → `NCC_xxx`
   - Giữ: mã HS, mã loại hình, số lượng/giá trị
3. **Script idempotent** — chạy lại không lặp; lưu mapping vào file riêng để restore khi cần debug.
4. **Verify run_checks vẫn fire đúng** sau anonymize (tránh anonymize phá quan hệ FK).

### Sau tuần 7 (lộ trình §7 đề án)

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
