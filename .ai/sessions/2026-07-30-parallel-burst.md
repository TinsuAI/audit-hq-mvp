# 2026-07-30 — Đợt chạy song song 17 luồng (hạn 01:00 SGT)

> Bối cảnh: owner yêu cầu tận dụng hết hạn mức tuần trong ~30 phút. Phát 17 luồng độc lập,
> mỗi luồng sửa lỗi chạy trong một git worktree riêng + nhánh riêng. **KHÔNG push, KHÔNG merge,
> KHÔNG đụng `main`.** Các luồng đo/viết tài liệu chỉ đọc DB (`mode=ro`) và mỗi luồng ghi đúng
> một file mới trong `.ai/notes/`.

## Nhánh đã commit (chờ review + merge)

| Nhánh | Nội dung | Trạng thái |
|---|---|---|
| `fix/percentile-keys-guardrail` | Gỡ khai báo chết `PERCENTILE_KEYS["C3.2"]` + test khoá cho mọi cặp `(check_code, key)` | `ef80f32`, `58d9383` — đã mutation-check |
| `feat/findings-export-xlsx` | Thêm 3 cột truy nguồn vào sheet "Phát hiện" của export sẵn có | `852773b` — 6 test mới, đã mutation-check |
| `fix/ai-overview-timeout-and-empty-content` | `request_timeout_s` không chặn được lời gọi + dòng `done` mà `content` rỗng | xem báo cáo luồng |
| `fix/overview-staleness-format` | `checks_needing_overview` bỏ sót dòng lỗi thời định dạng | xem báo cáo luồng |
| `fix/xstar-book-label` | Punch-list 8 — `X.*` luôn `book=NULL` | xem báo cáo luồng |
| `fix/c43-multiplier-p07` | `c4_norm.py` chưa theo P-07 (số nhân = sản lượng) | xem báo cáo luồng |
| `docs/punchlist-7-glossary` | GLOSSARY lệch ADR #19 | xem báo cáo luồng |

## Phát hiện phải xử lý — xếp theo mức nghiêm trọng

### 1. Mất trạng thái cán bộ mỗi lần chạy lại kiểm tra (LỖI ĐANG CHẠY, chưa có vé)

`app/pipeline/run_checks.py:78-104` xoá cứng toàn bộ `Finding` của các mã kiểm tra sắp chạy rồi
insert lại với id mới. **Không check nào truyền `status=`**, nên mọi `status`
(`confirmed`/`rejected`/`noted`) và `notes` cán bộ đã ghi bị đưa về `"new"` trong im lặng.
Đây là bằng chứng trong thực tế rằng cột trên chính dòng `Finding` là chỗ sai để lưu trạng thái.

**Khoá bền qua re-run có tồn tại:** `(company_id, period_year, check_code, subject_key, book)`.
Đã kiểm trên `audit_hq.sqlite`: không trùng ở C1.6/C1.7/C4.3 — 91% của 10.996 dòng `PILOT_006/2025`.
Ngoại lệ 4 dòng ở `PILOT_004` C1.1/C1.3 (một mã hai đơn vị MTR/ROLL), 0,05%.
Thiết kế + 4 vé T1→T4: `.ai/notes/2026-07-30-trang-thai-da-soat-finding.md`.

### 2. Mã số thuế thật và tên pháp nhân thật nằm trong file đã commit

Không có file dữ liệu nào bị commit (kiểm cả lịch sử bằng `git log --diff-filter=A`), nhưng chuỗi
định danh thật thì có:

- `tests/test_adapters.py:25,38,58` và `tests/test_anonymize.py:12-13,39,48,53,58,117,127` —
  MST `5400273360`, `0202177200` là giá trị assert
- `tests/test_anonymize.py:44` — tên pháp nhân đầy đủ dạng thật
- MST `0901051747` của pilot 004: `.ai/DECISIONS.md:545`, `.ai/GLOSSARY.md:94`,
  `.ai/STATUS.md:240,284,603` + 3 session log — trong khi chính STATUS.md ghi MST này **đã** được
  ẩn danh trên prod thành `6944313927`
- Tên mã `HONG_AN`/`GROWATT`/`KIM_LONG`/`DO_THANH`/`HONG_PHUC`/`HIEP_QUANG` ở ~60 vị trí tracked
  (`app/adapters/`, `app/pipeline/`, `app/templates/companies_list.html`, `scripts/`, `tests/`)
  thay vì `PILOT_xxx`

Mức thấp hơn: `deploy/scripts/add-tunnel-ingress.py:20-22` hardcode `/home/tinsu/.cloudflared/cert.pem`
+ UUID tunnel Cloudflare (không phải token sống); `app/routes/ai.py:347,353,1207,1210` log `%s` của
lỗi API — thân lỗi 400 của nhà cung cấp có thể chứa lại nội dung prompt.
`.gitignore` sạch, kiểm bằng `git status --ignored` (47 mục, đủ `-wal`/`-shm`/`.bak-*`).

### 3. Thang điểm 0–1000 — khuyến nghị bỏ khỏi mọi màn

`.ai/notes/2026-07-30-adr-thang-diem-rui-ro.md`. Thay bằng đếm theo mức nghiêm trọng (đã có sẵn
trong code, đang chạy song song với điểm):

| Pháp nhân/kỳ | Điểm hiện tại → nhãn | Thay bằng |
|---|---|---|
| PILOT_002/2025 | 7 → "Dữ liệu nhất quán" | 25 critical / 22 warning / 1 info |
| PILOT_004/2025 | 30 → "Dữ liệu nhất quán" | 61 / 7 / 6 |
| PILOT_006/2024 | 129 → "Cần rà soát" | 3.147 / 394 / 311 |
| PILOT_006/2025 | 54 → "Có chênh lệch nhỏ" | 9.963 / 904 / 129 |

Phương án "chuẩn hoá theo giá trị lớn nhất quan sát được" đã bị loại bằng số thật: sửa dữ liệu
006/2024 (raw 24,519 → 8,0) làm điểm hiển thị của 002 nhảy 53 → 125 dù dữ liệu 002 không đổi.
Mẫu số phụ thuộc dữ liệu của pháp nhân khác — tệ hơn hiện tại.

### 4. PR #45 — merge được như hiện trạng

4 nhãn trích dẫn khớp byte-for-byte với template trên `main`; ảnh dùng `DEMO_002/004/006` + banner
"Dữ liệu mẫu", API key đã che; không có `.sqlite`/Excel trong diff. `app/static/docs/huong-dan/` là
vị trí đúng cho ảnh SẢN PHẨM (`scripts/guide_screenshots.py:1-6` nói rõ, khác `.ai/features/`).

Việc theo sau (có trước PR này): trong chính `index.html` còn `map` chưa đổi thành "bố cục cột"
(420, 454-455, 464, 475-476 — đúng mục B7 mà PR vừa chụp lại ảnh) và `tick` chưa đổi thành
"đánh dấu" (504-505, 718, 720, 788, 847, 852), trong khi `main` đã đổi xong ở
`document_review.html:146`, `company_documents.html:150`, `company_data.html:41`.
Ngoài ra `app/templates/admin_ai.html:104-106` trên `main` vẫn ghi "Model mặc định/nhanh/sâu".

### 5. `PERCENTILE_KEYS` — 11/12 khoá lành, 1 khoá chết

Chỉ C3.2 chết cấu trúc (`c3_classify.py:157` ghi chuỗi). C6.1 `diff` phủ một phần: nhánh
"không có kỳ trước, opening>0" (`c6_cross_period.py:58-78`) không ghi khoá `diff`, nhưng
`_numeric_fields` bỏ qua đúng — không phải lỗi. Muốn C3.2 hiện ô phân vị thì `c3_classify` phải
phát ra tín hiệu số mới → sửa `../audit-hq/` trước.

### 6. Export đã có sẵn — chỉ thiếu cột truy nguồn

`GET /companies/{code}/export` (`app/routes/companies.py:1938` → `app/pipeline/export.py`) đã đầy đủ:
quyền qua `get_company_or_404`, lọc theo `check` khớp màn danh sách, `Content-Disposition`. Thiếu
`book`, `period_year`, `evidence_refs` — tức thiếu đúng cái FK về Tầng 1 mà `CLAUDE.md` yêu cầu.
Đã bổ sung. `?book=` cố ý KHÔNG áp cho export (export giữ toàn pháp nhân) — quyết định có sẵn, không đụng.
`build_export` nạp toàn bộ `Finding` vào bộ nhớ rồi dựng workbook trong `BytesIO`, không stream —
hành vi có sẵn, **chưa đo ở 11.000 dòng**.

## Chưa xác minh

- Chưa luồng nào chạy trọn `pytest tests`; các luồng chạy tập con do hạn thời gian.
- Hiệu năng export ở 11.000 dòng chưa đo (script có sẵn ở scratchpad, chưa chạy).
- Chưa nhánh nào được push hay merge. Chưa deploy gì.

## Việc tiếp

1. Chạy full suite + `ruff check app tests scripts` trên từng nhánh trước khi merge.
2. Quyết định xử lý mục 2 (MST/tên thật trong repo) — đụng cả lịch sử git nếu muốn xoá sạch.
3. Mở vé cho mục 1 (mất `status`/`notes` khi re-run) — đây là lỗi mất dữ liệu người dùng.
4. Chốt ADR thang điểm trước khi đưa điểm lên bất kỳ màn nào.
