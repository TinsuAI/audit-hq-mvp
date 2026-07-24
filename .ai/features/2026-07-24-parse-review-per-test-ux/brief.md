# Feature brief — Parse review + per-test workflow + AI overview

> **Trạng thái:** design brief, CHƯA grill. Đây là input cho `/grill-with-docs`.
> Ngày: 2026-07-24. Nguồn: phiên phân tích C4.3/parse + tầm nhìn UI của owner.

## Vấn đề

Luồng upload → ingest → chạy check hiện tại **kín và cứng**:
1. Cán bộ không thấy thuật toán đã hiểu file/sheet/cột thế nào; form lệch chuẩn có thể bị **đọc nhầm cột âm thầm** (chỉ đường extended có chốt số học ≥98%, đường positional thì không).
2. Check chạy **all-or-nothing**; không chạy lẻ, không chọn test khi export.
3. Không có tổng quan AI theo từng test, không biết tổng quan đã cũ so với lần chạy lại chưa.

## Ba workstream

### WS1 — Upload → phát hiện + đề xuất map cột (to nhất, mờ nhất)

**Đã có (tái dùng):**
- `app/adapters/sheet_select.py:133` `select_sheet` → `profile_sheets` chấm điểm sheet theo **nội dung tiêu đề** (Tier A / A1), ngưỡng `_MIN_SCORE`.
- `app/adapters/extended_layout.py:338` `resolve_m15a` đọc **công thức cân đối form tự khai** ((11)=(5)+(6)+(7)−(8)−(9)−(10)), phân loại cột theo dấu, validate ≥98% dòng (`_MATCH_RATE=0.98`), export theo nhãn.
- `ParseProvenance` (m15a.py) đã ghi `layout` (extended/condensed) + `match_rate`. Chưa lộ UI, chưa cho sửa.

**Mới:**
- Lộ kết quả phát hiện + **mức tin cậy** ra UI (extended validate = tự tin; positional fallback = "chưa kiểm"; AI đề xuất = "xác nhận giúp").
- Form lạ/thấp tin → **đề xuất map + cho cán bộ sửa** → **lưu bản sửa** để lần sau tái dùng.
- AI vào **khi heuristic + công thức trượt** (cache cứng, người xác nhận; parse-time nên không vi phạm "không gọi LLM trong rule logic").

**Quyết định chịu lực:**
- **D1 — đơn vị lưu bản map:** theo DN hay theo *chữ ký form* (hash cấu trúc tiêu đề)? Cùng DN có form khác nhau (004 mở rộng vs chuẩn) → nên khoá `(slot, chữ_ký_form)` để tái dùng chéo DN.
- **D2 — registry test→cột:** "ưu tiên ý nghĩa quan trọng với test" cần bảng ánh xạ mỗi check dùng cột/bảng nào (C4.3 cần sản lượng+xuất SX; C4.1 cần nhập+tồn đầu...). Thiếu cột test cần → cảnh báo "test không chạy được". **Registry này cũng là nền cho WS2/WS3.**
- **D3 — cổng review:** hiện positional được tin **âm thầm**. WS1 biến nó thành **gate xác nhận** khi tin cậy thấp.

### WS2 — Chạy từng test lẻ + export chọn test (gọn nhất)

**Đã có:** `app/pipeline/run_checks.py` `run_checks(company, year, only={mã})` đã chạy lẻ, xoá+tính lại đúng test đó. Chỉ thiếu route + nút UI mỗi test + export lọc theo mã chọn (select box).

**Quyết định chịu lực:**
- **D4 — combo stale:** `run_checks` chỉ tính lại `COMBO_*` khi chạy **full** ("Combo chỉ chạy khi không filter --check"). Chạy lẻ → combo không cập nhật → phải tính lại combo sau mỗi lần chạy lẻ HOẶC đánh dấu combo stale (nối WS3).

### WS3 — AI tổng quan mỗi test + staleness

**Data model mới:**
- **D5 — mốc chạy mỗi test:** bảng `check_runs(company, year, mã, ran_at, số_finding, data_version)`. **Không suy từ `findings.created_at`** — test ra 0 finding thì không có dòng → không biết đã chạy. `run_checks` ghi một dòng mỗi lần.
- **D6 — lưu overview:** `check_overviews(..., content, generated_at, based_on_run_at)`. **Stale = `based_on_run_at` < `check_runs.ran_at`**.
- Đã có `ai_conversations`/`ai_messages` để tái dùng hạ tầng LLM.

## Sợi chỉ chung — nền phải làm trước

Cả ba cần **theo dõi lần chạy + phiên bản dữ liệu**: WS3 cần mốc chạy; WS2 cần nó để biết combo stale; WS1 re-parse thì **làm stale toàn bộ downstream**. Nên `based_on` neo cả **data_version** (ingest lúc nào), không chỉ mốc chạy test.

## Thứ tự đề xuất

1. **Nền:** `check_runs` (mốc + số finding + data_version) + registry `test→cột`. Nhỏ, mở khoá WS2+WS3.
2. **WS2** — chồng lên `only=` sẵn có; xử combo-stale.
3. **WS3** — chồng lên `check_runs`.
4. **WS1** — to/mờ nhất, grill + prototype riêng (có thể `/wayfinder`). Chính là hình thức hoá việc mổ cột M15a làm tay ở phiên 2026-07-24.

Owner nghiêng: **grill WS1 trước** (quyết định nhiều nhất + định hình registry test→cột mà WS2 dùng).

## Câu hỏi mở cho grill

- WS1: AI luôn gợi ý hay chỉ khi trượt? Bản map lưu theo DN hay chữ ký form? Ai được sửa map (phân quyền)?
- WS2: export chọn test là ephemeral hay lưu "export profile"?
- WS3: overview stale khi data re-ingest có tự regenerate hay chỉ báo? Overview lưu bản lịch sử hay ghi đè?
- Chung: registry test→cột đặt ở đâu (khai trong mỗi check, hay bảng riêng)?

## Pointers

- Cơ chế quyết định cột (đã mổ 2026-07-24): brief này WS1 + `sheet_select.py` + `extended_layout.py`.
- Quyết định C4.3 số nhân = sản lượng: `audit-hq/.ai/DECISIONS.md` (2026-07-24) + `audit-hq-pilot/notes/13` P-07.
- Session log: `.ai/sessions/2026-07-24-c43-basis-and-ui-redesign.md`.
