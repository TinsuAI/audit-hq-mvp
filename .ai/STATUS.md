# STATUS — Audit-HQ MVP

> **Trạng thái:** Tuần 5 hoàn tất (2026-05-21). **16/16 MVP check** đã cài đặt — đủ scope §7.3 đề án. HONG_AN 2024 với 2023 baseline phát hiện 1 finding thực C3.2 (Da X-DL khai 2 mã HS khác nhóm). 68 tests pass, ruff clean. Sẵn sàng tuần 6 (scoring + combination signatures).

## Current State

- Stack: Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite, pandas + openpyxl/xlrd, Jinja2.
- DB: SQLite (`audit_hq.sqlite`). 5 tables: `companies`, `nvl_balances`, `sp_balances`, `norms`, `declaration_lines`.
- Auth: basic-auth (cookie-signed session). Mặc định `admin/admin` cho dev — thay env vars `AUTH_USER`/`AUTH_PASSWORD` cho demo.
- Dữ liệu: symlink `data/` → `../audit-hq/data/raw/` (gitignored), 622 file thực 6 DN.

## Recent Changes

- **2026-05-21 (đêm)** — Tuần 5: 7 check MVP cuối (Nhóm 3 + 4 MVP + 5 + 6 MVP). C3.1 mâu thuẫn loại hình NVL×MMTB, C3.2 HS không nhất quán (scale chương/nhóm/phân nhóm), C3.3 đơn vị tính lệch giữa M15 vs BCCT (có alias map UN/CEFACT: MTR↔METRES, PR↔PAIR, MTK↔SQUARE METRES…). C4.1 NVL trong M16 không có nguồn, C4.3 tổng tiêu hao M16 vượt M15.production_out (scale 5/20%). C5.1 NVL có xuất SX không có nhập+tồn đầu. C6.1 tồn đầu kỳ N ≠ tồn cuối kỳ N-1. Ingest thêm HONG_AN 2023 (77 NVL, 248 norm) cho C6.1 baseline. +25 unit test. 68 tests total.
- **2026-05-21 (khuya)** — Tuần 4: 3 check Nhóm 2 (C2.1 cân bằng M15, C2.2 cân bằng M15a, C2.3 tồn cuối NVL âm). C2.1 phát hiện kèm pattern "tồn ảo" (opening=0, closing>import) ghi vào details. Cơ chế đánh dấu finding: POST `/findings/{id}/status` với 4 trạng thái (new/confirmed/rejected/noted) + ghi chú; UI có inline form trên mỗi row, anchor scroll về row vừa update. +12 unit test (9 C2.x + 3 status route).
- **2026-05-21 (tối)** — Tuần 3: 6 check Nhóm 1 MVP (C1.1-C1.4, C1.6, C1.7) + registry với severity scale (🔴🟡🔵). Finding model (Tầng 2) với evidence_refs JSON. `detect_company_type` heuristic (SXXK/DNCX/Gia công từ mã loại hình BCCT). Pipeline `run_checks` CLI idempotent. UI: `/companies` (bảng tổng quan), `/companies/<code>?year=YYYY` (chi tiết findings group by check_code, collapsible, badge severity). 19 unit test mới cho check + scale + company_type detection.
- **2026-05-21 (chiều)** — Tuần 2: 4 adapters (M15/M15a/M16/BCCT) chuẩn hoá vào dataclass; models Tầng 1; Alembic initial migration; pipeline `discover + ingest` (CLI `python -m app.pipeline.ingest --company HONG_AN --year 2024`); 7 tests mới (4 adapters + 3 discover). Verify HONG_AN 2024 — Công ty Cổ phần Giầy Hồng An, MST 5400273360, ngành giày dép (SXXK loại hình E31/E62).
- **2026-05-21 (sáng)** — Scaffold tuần 1: pyproject, Makefile, Dockerfile, docker-compose, FastAPI hello + login + overview placeholder, alembic init, 5 smoke tests pass.

## Insight nghiệp vụ (cập nhật cuối tuần 5)

HONG_AN 2024 + 2023 baseline, chạy 16/16 MVP check → **1 finding thực** (C3.2 Cảnh báo):

- Mã `X-DL` (Da lộn) khai trên 2 mã HS: `41079900` (Da đã thuộc) và `41151000` (Da nhân tạo). Cùng chương 41 nhưng khác nhóm 4 số → có thể là tách dòng sai HS, hoặc cùng 1 mã NPL được DN dùng cho 2 loại da → nên đề nghị DN tách mã.

Các check khác đều **clean trên HONG_AN**:
- M15 nhập = Σ BCCT[E31] *chính xác* mọi mã (diff 0.0%)
- Phương trình M15 cân hoàn hảo (diff = 0.0000)
- Tồn đầu 2024 = tồn cuối 2023 *chính xác* trên 77 NVL chung
- 22 NVL mới xuất hiện 2024 đều có opening = 0 (đúng — mã mới đăng ký)
- 0 NVL âm, 0 NVL không có nguồn, 0 M16 không có nguồn
- Định mức M16 × xuất khẩu M15a ≈ xuất SX M15 (diff < 5% mọi mã)

Phát hiện C3.2 trên dữ liệu thực **không** phải false positive — sẽ là material cho demo "rule không phát hiện bừa, mà phát hiện đúng vấn đề tinh tế" (§6.3 đề án). Trừ vấn đề da X-DL, dataset HONG_AN "sạch" — cần inject sai phạm chủ đích ở tuần 8 để demo kịch tính 5 phút.

**Đơn vị tính alias map** (`app/checks/c3_classify.py`) đã giảm false positive từ 43 → 0 trên HONG_AN. Map sẽ mở rộng khi gặp DN mới có biến thể khác (vd LTR/Litres, TNE/Tons…).

## Next Steps

### Tuần 6 — Scoring + combination signatures + dọn dẹp

Mục tiêu §7.3 đề án: kết thúc 16 MVP gọn gàng, sẵn sàng cho tuần 7-8 (anonymize + inject) và 9-10 (UI + demo).

1. **Cộng dồn điểm rủi ro DN (§2.6 đề án):** tính `Company.risk_score` từ tổng findings:
   - Mỗi finding critical = 10 đ, warning = 3 đ, info = 1 đ (config trong registry).
   - Bonus combo (xem dưới).
   - Hiển thị xếp hạng DN ở `/companies` (đã có column).
2. **Combination signatures (§2.7):** vd:
   - `C2.1 + C4.3` cùng DN → cờ đỏ "phương trình lệch + tiêu hao bất thường".
   - `C1.3 + C5.1` → "M15 khai nhập không có tờ khai + có xuất SX không nguồn" → gian lận điển hình.
   - Mỗi combo +20 đ vào risk_score, hiển thị riêng như 1 "meta-finding".
3. **Refactor + dọn dẹp:**
   - Tách common patterns ra `_common` (vd evidence_refs builder).
   - Review naming, ensure docstring nghiệp vụ đầy đủ.
   - Coverage check.
4. **CLI mở rộng:**
   - `python -m app.pipeline.run_all` — chạy ingest + run_checks cho toàn bộ DN trong `data/raw/`.
   - Output: ai có findings, top mã rủi ro.

### Sau tuần 6 (lộ trình §7 đề án)

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
