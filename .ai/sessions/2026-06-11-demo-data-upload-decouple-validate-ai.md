# Session 2026-06-11 — Demo upload data + tách upload/check + validate/AI

Chuẩn bị demo cho HQ. 4 yêu cầu: (1) gen lại bộ data DN để upload chạy 1 flow
hoàn chỉnh; (2) tách upload data khỏi chạy kiểm tra; (3) backlog: xử lý elegant
khi HQ upload data lạ, có AI; (4) gợi ý UI/UX.

## Đã làm

### #1 — Bộ data demo để upload (`scripts/gen_demo_data.py`, commit `86a7d48`)
- **Hướng (chị chỉ định):** KHÔNG export từ DB ("vô tri, sai cấu trúc"). Anonymize
  file Excel **GỐC** mà `discover()` chọn, chỉ thay PII, giữ nguyên format thật.
- Đọc tên DN/MST/địa chỉ/NCC alias từ `db-data/anonymize_mapping.json` → output
  khớp 100% DB demo. 4 DN × mọi năm (~12 bộ, 42 file) → `demo-data/<tên DN>/
  <năm>/{BCQT,HANG_CHI_TIET}/`.
- Cấu trúc (sau chị góp ý): **ĐM (Mẫu 16) nằm trong folder BCQT** (cùng M15/15a);
  folder theo **tên DN đã anonymize** (không dùng mã DN_xxx).
- Anonymize: `.xlsx` sửa cell tại chỗ (openpyxl, giữ style); `.xls` đọc lưới →
  ghi `.xlsx` giữ vị trí cột; BCCT gộp nhiều file + lọc theo năm tờ khai (như
  ingest), thay cột 47/48/49 (MST/tên/NCC). Leak scan accent-insensitive + word
  boundary → đảm bảo 0 rò rỉ.
- DN_003/2024 nhúng lại 7 sai phạm inject §6.3 (giá trị cuối từ
  `injected_changes.json` — toàn M15; **phát hiện** block norm DG ×100 trong
  `inject_findings.py` thực tế chưa từng chạy vì DB không có norm `DG`).
- **Verify round-trip:** ingest demo-data vào scratch DB + run checks →
  116/28/148/46 **khớp tuyệt đối** DB gốc (DN_003 494 vs 492 finding — nhiễu float
  .xls→.xlsx, điểm 148 không đổi).
- Copy `C:\temp\toss` cho chị dùng tay (Windows, không vào git).

### #2 — Tách upload khỏi chạy kiểm tra (commit `2ee586e`)
- `upload_data` route: bỏ `run_check_pipeline`, **chỉ `run_ingest`**. Báo lỗi rõ.
- `company_detail`: năm lấy từ hợp 4 bảng Tầng 1 (không chỉ findings) → data hiện
  khi chưa chạy check. Thêm `has_data`/`checks_run`/`just_ingested`.
- `company_detail.html`: banner "Đã nạp dữ liệu… chưa chạy kiểm tra" + nút "Chạy
  kiểm tra năm N"; ô điểm "— / Chưa chạy kiểm tra" (không giả 0).
- `upload_data.html`: copy đổi sang "Tải lên & nạp dữ liệu".

### #3 — Validate upload + AI chẩn đoán (commit `2ee586e`)
- Rủi ro thật = **misparse thầm lặng** (adapter hardcode cột/sheet TT39/ECUS).
- Lớp 0 `app/pipeline/validate.py`: `diagnose_upload()` chạy trước ingest. Bắt
  file hỏng / 0 dòng / số toàn 0; **heuristic dò header + map cột thực vs chuẩn**
  → giải thích cụ thể từng cột lệch (tiếng Việt). Lỗi nặng → panel 422, KHÔNG nạp.
- Lớp AI `app/ai/ingest_doctor.py` + `POST /companies/{code}/diagnose-ai`: nút
  "🤖 Nhờ AI chẩn đoán" (chỉ hiện khi AI bật). Gửi trích đoạn sheet + schema cho
  LLM (slot `fast` + fallback chain, guard rate/budget). Xử mẫu lạ heuristic bó
  tay. Tắt AI thì heuristic vẫn đầy đủ.
- `tests/test_validate.py`: 5 test. 439 → **444 pass**, ruff clean.

### #4 — UI/UX: chỉ gợi ý (badge trạng thái, progress inline, drag-drop, nút nạp
mẫu 1 chạm). Chưa implement — xem Next Steps D.

### Screenshot (Playwright, không commit)
7 ảnh ở `C:\temp\toss\screenshots\`. Chạy app thật trên **scratch DB + raw tạm**
(không đụng DB/data thật): tạo DN, upload bộ file anonymize, chạy check (job
async → điểm 112 + combo), upload file lỗi → panel chẩn đoán. Demo AI: kéo config
AI **live từ tinsu** (Gemini 2.5 Flash-Lite + NIM fallback) vào scratch, gọi thật,
chụp; case 2 file header tiếng Anh → AI map ngữ nghĩa Anh→Việt.

## Quyết định
- Anonymize file gốc (không DB export) — chị chỉ định, đúng vì giữ variation thật HQ gặp.
- Port inject DN_003/2024 vào file để giữ kịch bản combo demo (chị chọn).
- Phạm vi 4 DN × mọi năm (chị chọn).
- ĐM trong BCQT + folder theo tên DN (chị chỉ định).
- AI là **escalation tùy chọn**, không nằm trong rule logic; heuristic-first (tuân
  thủ CLAUDE.md "không gọi LLM trong rule logic").
- **2 commit** (không 3): #2 và #3 dùng chung `companies.py`/`upload_data.html`,
  tách sẽ tạo commit trung gian gãy import. #1 tách riêng.

## Không chạy / bug đã sửa
- **DB export bị bác** (vô tri) → chuyển anonymize file gốc.
- **Ô công thức Excel:** openpyxl giữ công thức nhưng mất cache → pandas đọc lại =
  0 (DO_THANH closing) → C2.1 false. Fix: bake `data_only=True` cache. Chỉ lộ khi
  verify round-trip (DN_001/003 closing là giá trị tĩnh nên khớp; chỉ DO_THANH formula).
- **`M15aRow` không có `import_qty`** (dùng `intake_qty`) → validate 500 khi upload
  Mẫu 15a. Fix field-agnostic `_inflow()`. **Chỉ lộ nhờ chụp screenshot** (S2 ra
  Internal Server Error) → bài học: screenshot bắt được bug mà unit test không phủ.
- **Leak scan false positive:** token "hong an" khớp "phòng ăn"/"chống ăn mòn" trong
  item name DN khác → thêm word-boundary `\b`.
- **`pkill -f "uvicorn.*8222"` tự kill shell** (cmdline chứa chính pattern) → kill
  theo PID từ pidfile thay vì pattern.

## Open items
- **Chưa push** 2 commit (chờ chị OK). Push → auto-deploy code lên live (data không đổi).
- AI auto-remap (tự map cột rồi ingest, có UI duyệt mapping) — feature lớn, defer.
- UI/UX #4 chưa làm.
- Tồn từ trước: 4 câu hỏi clarify M16 (session 2026-06-01) vẫn chờ chị.

## File chạm
- Mới: `scripts/gen_demo_data.py`, `app/pipeline/validate.py`,
  `app/ai/ingest_doctor.py`, `tests/test_validate.py`.
- Sửa: `app/routes/companies.py`, `app/templates/company_detail.html`,
  `app/templates/upload_data.html`, `.gitignore`.
- Không commit: `demo-data/` (gitignored), screenshot + bộ data ở `C:\temp\toss`.
