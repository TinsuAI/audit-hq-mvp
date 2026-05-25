# 2026-05-25 — Self-service: tạo DN + upload + chạy lại kiểm tra

## What Was Done

Mở 3 luồng tương tác để cán bộ HQ (hoặc demo viewer) thao tác qua UI mà không cần CLI:

1. **Tạo DN mới** (`GET/POST /companies/new` → `POST /companies`)
   - Form 4 trường: `code` (required, regex `^[A-Z][A-Z0-9_-]{1,30}$`), `name`, `tax_id`, `address`.
   - Demo guardrail: tự gắn hậu tố ` (Demo)` vào `name` nếu chưa có. Banner vàng `🧪 Dữ liệu mẫu` vẫn fire (giữ posture demo).
   - Validate uniqueness; lỗi render lại form với status 400 + form state preserved.
   - Redirect 303 → `/companies/{code}/upload` sau khi tạo.

2. **Upload dữ liệu BCQT** (`GET/POST /companies/{code}/upload`)
   - 1 form, 4 slot file (`m15` / `m15a` / `m16` / `bcct`) + `year` (2015-2030). Slot trống được chấp nhận (ingest đã handle `None`).
   - File save vào đúng struct `data/raw/<code>/<year>/{BCQT,DINH_MUC,HANG_CHI_TIET}/<stem>_<year>.<ext>` để `discover()` pick được mà không cần đổi adapter.
   - Stem cố định (`M15_NVL`, `M15a_SP`, `BCDM_TT39`, `BCCT`) — match đủ pattern trong `discover.py`.
   - Helper `_save_upload` stream 1MB chunk, limit 100MB, wipe sibling cũ trong subdir để discover không pick file outdated.
   - Sau khi save: chạy `ingest()` + `run_checks()` đồng bộ. Với 16 check, latency ~0.7s ngay cả khi BCCT 11MB.
   - Catch `FileNotFoundError` → 400; bắt mọi exception khác → 500 với type+message (cố ý lộ stacktrace gọn để debug demo, đổi sau nếu vào prod thật).

3. **Chạy lại kiểm tra** (`POST /companies/{code}/run-checks`, hidden `year` field)
   - Wrap `run_check_pipeline(code, year)` — đã idempotent sẵn (xoá finding cũ + recompute score).
   - Nút render trên `/companies/{code}?year=Y`, ngay btn-group cạnh "Dữ liệu gốc" / "Xuất Excel".

**Templates:**
- Mới: `new_company.html`, `upload_data.html`.
- Sửa: `companies_list.html` (thêm "+ Thêm DN mới" cạnh nút "Cách tính điểm"), `company_detail.html` (thêm "📥 Upload dữ liệu" + "🔄 Chạy lại kiểm tra"; cập nhật empty state khi `selected_year is None` để CTA upload thay vì hint CLI).

**Lint config:** thêm `fastapi.File` vào `extend-immutable-calls` (pyproject) — `Form/Depends/Query/Header` đã có sẵn.

**Verify E2E:** Upload thật 4 file HONG_AN 2024 (`TT39_BaoCaoQuyetToan_NVL 2024.xlsx`, `…_SP 2024.xlsx`, `BCDM_TT39_HA_2024.xls`, `BaoCaoHangChiTiet XNK 2024.xls`, tổng ~11MB) qua endpoint mới → 99 M15 rows / 75 M15a / 476 norm / 246 BCCT / 1 finding `C3.2 X-DL warning` / score=3 — **khớp đúng baseline đã ghi trong STATUS.md từ tuần 6**.

113 test pass, ruff clean. Test DN (`DN_TEST_01`, `DN_TEST_02`) đã cleanup khỏi DB + `data/raw/`.

## Decisions Made

- **Demo posture giữ nguyên** (user chốt qua AskUserQuestion): banner `🧪 Dữ liệu mẫu` vẫn render, name DN mới ép thêm `(Demo)`. Quyết định này dồn việc "tách clean prod" sang sau — khi HQ thực sự deploy ở Chi Cục thì có thể remove banner + ép suffix bằng env var. Không build env-var toggle bây giờ (over-engineering với scope hiện tại).

- **1 form 4 slot, auto-ingest-+-run** (user chọn 2 lần option Recommended): thay vì 4 form rời hoặc ZIP upload, hoặc tách bước ingest/run. Lý do: demo flow ngắn, latency 0.7s đủ để user không cần spinner async.

- **Tên file lưu cố định theo stem chứ không preserve original filename**: trade-off giữa traceability (giữ tên gốc) vs predictable discover (filename match pattern). Chọn predictable vì file gốc DN gửi tên rất tự do (`TT39_BaoCaoQuyetToan NVL 2024 - HA fn.xlsx` v.v.) — discover().is_draft() heuristic dễ false-positive.

- **Wipe sibling**: `_save_upload` xoá file cùng prefix cũ trong subdir trước khi ghi mới. Tránh trường hợp upload `M15_NVL_2024.xlsx` mà subdir vẫn còn `M15_NVL_2024.xls` cũ → discover ambiguous.

- **Sync pipeline (không background task)**: 0.7s là OK cho 16 check trên dataset thật lớn nhất hiện có. Nếu sau này thêm 30+ check Giai đoạn II hoặc data DN khổng lồ → đổi sang BackgroundTasks/Celery sau, không phải bây giờ.

- **Không thêm test mới**: 3 route mới đều là wrapper mỏng quanh `ingest()` và `run_checks()` đã có test. Verify end-to-end qua httpx khi smoke test thay vì viết route test riêng — repo đề án không có tradition test cho mọi route (login chưa có test, finding_detail có).

- **Lint whitelist `fastapi.File`**: cùng pattern với `Form/Depends/Query/Header` đã có. Đây là FastAPI idiom, B008 false-positive.

## What Didn't Work / Gotchas

- **Port 8000 conflict** với `BCQT-System` đang chạy local — phải start dev server ở port 8200 (cùng port với prod tunnel). Pattern này lặp lại trên máy này — nên dùng `lsof -i :PORT` trước khi assume port free.

- **Route order quan trọng**: `/companies/new` phải đăng ký TRƯỚC `/companies/{code}` trong `companies.py`, không thì FastAPI match `code="new"` và rơi vào `company_detail()`. Đã chèn block routes mới ở giữa file (line ~140, ngay trước `company_detail`).

- **Lần đầu chạy ruff fail 6 lỗi B008** — `File()` không có trong whitelist. Update pyproject 1 lần, không tách thành nhiều fix.

- **Empty UploadFile từ FastAPI**: khi user submit form mà bỏ trống 1 slot, FastAPI gửi `UploadFile` với `filename=""` chứ không phải `None`. Check `not upload or not upload.filename` để skip.

## Open Items

- **Run-checks không có data**: nếu user bấm 🔄 trên năm chưa upload data, pipeline chạy với DB trống → 0 finding, score=0. Không crash nhưng UX hơi confusing. Có thể thêm guard "phải có ít nhất N row M15 mới enable nút" sau.

- **File size limit 100MB**: BCCT đa kỳ (gộp 3-5 năm) có thể vượt. Đổi `MAX_UPLOAD_BYTES` ở `app/routes/companies.py:67` nếu gặp.

- **Không có delete-DN route**: tạo DN xong không có cách xoá qua UI. Phải xoá tay qua DB + filesystem. Có thể thêm `POST /companies/{code}/delete` (with confirm modal) nếu cần. Trong demo flow hiện tại, user chỉ tạo + xem nên chưa cần.

- **Realistic-name policy cho DN mới qua UI**: hiện ép suffix `(Demo)`. Nếu user gõ chính xác tên DN thật mà không gắn `(Demo)`, hệ thống vẫn render với `(Demo)` — có thể leak intent tên thật. Validation thô hơn (block các từ "Công ty TNHH …" thật) sẽ over-engineer. Để nguyên, cảnh báo bằng help text trên form.

- **Sửa metadata DN sau khi tạo**: chưa có route. Nếu typo tên/MST thì phải đụng DB. Add edit-company route nếu thấy cần khi test với teammate.

- **Deploy lên prod?**: chưa wire CI deploy cho commit này. Nếu push main, runner self-hosted (đã online) sẽ tự build + restart. Vẫn nên test sạch sẽ trên local trước.
