# Glossary — Audit-HQ MVP

Ngôn ngữ chung của dự án. Chỉ định nghĩa thuật ngữ — không phải spec, không chi tiết cài đặt.
Định danh giữ tiếng Anh; prose tiếng Việt.

## Parse review (WS1)

**Evidence source** — nguồn bằng chứng cho việc gán MỘT cột đã đọc. Bốn nguồn, mạnh→yếu:
- `officer-confirmed` — cán bộ đã duyệt, hoặc có map đã lưu cho form này.
- `header-matched` — tiêu đề tại vị trí đó khớp nhãn mong đợi (pin đúng cột).
- `balance-checked` — đẳng thức cân đối của biểu khớp nếu lấy cột này. Đủ cho cột chỉ dùng dạng
  TỔNG; KHÔNG phân biệt hai cột cùng dấu.
- `position-only` — chỉ số cột cố định, không tín hiệu nào khác. Là phỏng đoán.

**Review state** — badge gộp evidence source về hai trạng thái cán bộ hành động:
- `verified` (xanh) — tin được, không cần làm gì.
- `needs_review` (vàng) — cột được một check tiêu thụ nhưng nguồn tốt nhất là `position-only`, hoặc
  dùng riêng lẻ mà chỉ có `balance-checked`. UI render tiếng Việt: "Đã kiểm" / "Cần xác nhận".

**Individually-consumed column** — cột một check đọc TRỰC TIẾP (không qua tổng cân đối), nên cần
`header-matched`/`officer-confirmed`. Ví dụ: `production_out` (C4.3, C5), `repurpose` (C1.x), cột con
export M15a (C1.4), cột ĐM thực tế M16 (C4.3). Đối lập: cột dùng dạng TỔNG (C2 tự tính lại) — chỉ
cần `balance-checked`.

**Form signature** — chữ ký CẤU TRÚC của một bố cục biểu. Hash = danh sách nhãn tiêu đề cột theo
thứ tự + số cột (gập hoa/dấu/khoảng trắng, bỏ chữ số năm) + dòng đánh số khi có; KHÔNG chứa mã DN.
Map đã xác nhận lưu theo `(DN, vân tay)` — tái dùng chéo NĂM trong cùng DN, KHÔNG chéo DN (option 2,
ADR #18 sửa ADR #15).

**File lifecycle** — trạng thái vòng đời một file đã tải, hiện trên UI: `uploaded` (đã lưu, chưa
đọc) → `analyzed` (dry-run parse xong, chưa ghi DB — cổng review ở đây) → `parsed` (đã commit dòng);
`error` nếu hỏng. `analyzed→parsed` tự động khi `verified`, dừng chờ bấm khi `needs_review`. Trục
RIÊNG với review state.

**Review gate** — điểm trong luồng upload hỏi cán bộ xác nhận map cột. Kích MỖI FILE khi có cột
`needs_review` chưa có map lưu. CẢNH BÁO (check vẫn chạy, finding vẫn hiện có cờ), không CHẶN.

**Check→column registry** — dict tĩnh khai mỗi check dùng cột/bảng nào + `consumed_as`
(`individual`|`sum`). Nền cho review gate và cho WS2/WS3.

## Chạy test lẻ + export chọn (WS2)

**Per-test run** — chạy MỘT check cho (DN, NĂM đang xem) mà không chạy cả bộ. Cơ chế:
enqueue job `RUN_CHECKS` với `only=[mã]` (payload thêm trường `only`), worker chạy → về `/jobs/{id}`.
Mọi lần chạy check (lẻ, full năm, cả bộ) đều ASYNC qua job — KHÔNG còn `run_checks` đồng bộ trong
request (ADR #18 Revision WS2, SỬA "re-run inline" của WS1). Xem [[check-execution-async-via-jobs]].

**`combos_enabled`** — cờ `app_settings` bật/tắt TOÀN BỘ combo (một công tắc toàn cục, không
per-combo). Mặc định OFF. Gate CẢ recompute (`run_checks` skip `detect_combos`) LẪN render
(`company_detail` ẩn mục combo). Áp lazy: mỗi (DN, năm) nhận hiệu lực ở lần chạy kế. Khác `enabled`
của từng check — đây là bật/tắt lớp meta-finding, không phải một check.

**Combo recompute** — combo tính lại trên MỌI lần `run_checks` (lẻ hay full), đọc TOÀN finding-set
của (DN, năm). `COMBO_*` bị delete vô điều kiện mỗi lần chạy; recompute mới là phần gate theo
`combos_enabled`. (Trước WS2: chạy lẻ xoá combo mà không dựng lại — combo biến mất tới lần full kế.)

**Selective export** — xuất Excel kiến nghị chỉ gồm các check được chọn. `build_export(only=)` lọc
finding theo `check_code.in_(only)`; sheet chứng cứ thu hẹp theo subject còn lại. EPHEMERAL: chọn qua
param `check` lặp lại, KHÔNG lưu "profile". KHÔNG chọn = xuất tất cả (mặc định cũ). Sheet Tổng quan
liệt kê mã đã chọn để không nhầm với export đủ.

## AI tổng quan + staleness (WS3)

**Check run** — mốc lần chạy mới nhất của MỘT check cho (DN, năm). Bảng `check_runs`, latest-upsert
một dòng mỗi `(company_id, period_year, check_code)`: `ran_at`, `finding_count`, `status`,
`data_version`. Ghi TRONG `run_checks()` cho MỌI check đã chạy, kể cả 0 finding — nên KHÔNG suy được
từ `findings.created_at` (check ra 0 thì không có dòng finding). `status = ok|error` (`not_evaluable`
dành sẵn, chưa build — Tầng C). Dòng VẮNG = "chưa rõ", KHÔNG stale. Lịch sử lần chạy KHÔNG ở đây — ở
bảng `jobs`. Xem [[ws3-overview-staleness-model]].

**Data version** — số nguyên trên `CompanyPeriod`, bump MỖI lần `ingest()` (trong transaction ingest
→ nguyên tử với data). Đánh dấu "dữ liệu (DN, năm) đã đổi". Số nguyên chứ không timestamp: đồng hồ
Python (`_now()`) ≠ đồng hồ SQL (`current_timestamp()`), so bằng không cần thứ tự. `run_checks` đọc ở
ĐẦU lần chạy + ghi vào `check_runs`. Cần vì đường re-ingest trần (`documents_ingest_year`) đổi dữ liệu
mà KHÔNG chạy check → `ran_at` không dời → điểm mù nếu chỉ dựa `ran_at`.

**Check overview** — tổng quan AI tiếng Việt CÓ TRUY NGUỒN của một check cho (DN, năm). Bảng
`check_overviews`, overwrite-upsert một dòng mỗi `(company_id, period_year, check_code)`; mang telemetry
riêng (`model`/`tokens_in`/`tokens_out`/`cost_usd`/`latency_ms`) → tự truy nguồn chi phí, không cần
history hay `ai_conversation` giả. Sinh ON-DEMAND (cán bộ bấm) — ADR #21 chuyển sang ASYNC qua job
`AI_OVERVIEW` (worker riêng theo kind), SỬA "đồng bộ trong request" của ADR #18; **chưa cài**. Prompt
nạp ĐẾM severity + top-N `subject_key`, KHÔNG nạp dòng. Chỉ mặt trên GROUP đã render (check ≥1 finding).

**Staleness (overview)** — overview cũ khi trạng thái nền đã tiến. **Stale ⇔ `check_runs.ran_at` dời
(check chạy lại) HOẶC `CompanyPeriod.data_version` dời (dữ liệu nạp lại)** so với `based_on_run_at` /
`based_on_data_version` snapshot trên dòng overview. Xử lý FLAG-ONLY: hiện text xám + badge "đã cũ" +
nút "Tạo lại", KHÔNG auto-regenerate lúc load. Combo (`COMBO_*`) KHÔNG có check-run lẫn overview.

## Pháp nhân · loại hình · sổ quyết toán (004 hai loại hình)

**Pháp nhân (legal entity)** — thực thể pháp lý, định danh bằng MST (`tax_id`). Một pháp nhân có thể
giữ NHIỀU sổ quyết toán khác loại hình. CHƯA có đại diện first-class: mỗi row `companies` hiện là
(pháp nhân × loại hình); `tax_id` free-text, KHÔNG unique — hai row cùng MST là hai company khác
`code`. 004 = 1 pháp nhân MST `0901051747`, hai row id 9 (`PILOT_004_EPE`) / id 10 (`PILOT_004_GC`).

**Loại hình** — kiểu hoạt động hải quan của MỘT sổ quyết toán. Enum `CompanyType`
(`app/checks/company_type.py`): `DNCX` (chế xuất), `GIA_CONG` (gia công — NVL của bên đặt sở hữu),
`SXXK`, `UNKNOWN`. Là thuộc tính PER-SỔ, KHÔNG per-pháp-nhân: một DNCX vừa sản xuất tự sở hữu (sổ
EPE) vừa gia công (sổ GC) → một pháp nhân, hai loại hình. **KHÔNG dùng từ "chế độ"** cho trục này —
không nhất quán với `CompanyType`.

**Hai tầng loại hình (lệch nhau ở 004)** — tầng TỜ KHAI: mã loại hình trên tờ khai (E11/E15/E42 =
DNCX); `detect_company_type` suy MỘT loại hình/row từ đa số mã → DNCX. Tầng QUYẾT TOÁN (BCQT): pháp
nhân tách sổ theo loại hình thực (DNCX-own vs gia công). Mã DNCX ở tờ khai CHE phần gia công → phần
đó chỉ hiện ở BCQT. Vì thế loại hình detect-từ-tờ-khai THÔ hơn sự thật per-sổ.

**Sổ quyết toán (book)** — sổ con trong BCQT của một pháp nhân; mỗi sổ một loại hình + bộ
M15/M15a/định mức riêng, tồn kho độc lập. Cột `book` trên `nvl_balances`/`sp_balances`/`norms` (null
= pháp nhân một sổ, KHÔNG đổi hành vi — 002/006). 004: sổ `EPE` (98 mã NVL) + sổ `GC` (37 mã). Tờ
khai KHÔNG thuộc sổ nào — MỘT list dùng chung cả pháp nhân. Check cross-layer (tờ khai↔quyết toán)
đối chiếu UNION các sổ; check nội-sổ GROUP BY book. Xem [[pilot-004-epe-gc-merge]].

**Pháp nhân nhiều sổ (multi-book company)** — điều kiện nghiệp vụ bật giao diện theo sổ: một pháp
nhân giữ ≥2 sổ quyết toán khác loại hình TRONG một năm. Xác định từ dữ liệu Tầng 1 (tập `book` khác
null trên `nvl_balances`/`sp_balances`/`norms`, phạm vi theo năm) — KHÔNG suy từ finding (sổ sạch có
0 finding vẫn là một sổ, vd GC của 004 = 37 mã NVL, 0 phát hiện 2025). Pháp nhân một sổ (002/006):
toàn bộ `book` null → KHÔNG có chrome theo sổ.

**Liên sổ (phát hiện liên sổ)** — finding KHÔNG quy được về một sổ, do check cross-layer đối chiếu list
tờ khai dùng chung với UNION các sổ (C1.1/C1.2/C1.4/C3.2). **Nhãn UI "Liên sổ"** (param `?book=chung`,
định danh nội bộ giữ "chung"). `book` null trên finding vì thế MANG HAI NGHĨA tuỳ pháp nhân: (a) nhiều
sổ → liên sổ, chưa/không quy về sổ nào; (b) một sổ → trục sổ không liên quan. UI chỉ hiện "Liên sổ" như
một loại thứ ba khi pháp nhân nhiều sổ, TÁCH khỏi "Tất cả" (= hợp EPE ∪ GC ∪ Liên sổ). KHÔNG gộp "Liên
sổ" vào một sổ khi lọc theo sổ — check chưa quy kết sổ nào thì UI không được khẳng định thay (kỷ luật
truy nguồn, không hộp đen). 004/2025: EPE 34 · GC 0 · Liên sổ 40.

## Chat gắn doanh nghiệp (ADR #20 — chưa cài)

**Doanh nghiệp gắn với cuộc trò chuyện** — MỘT doanh nghiệp của một cuộc trò chuyện, lưu ở
`ai_conversations.company_id` (null được). Tự nhận diện lúc TẠO từ tín hiệu tường minh (DN cán bộ chọn
→ DN của trang → DN của finding đang xem), gán muộn chỉ từ mention `@DN` khi lượt đó có đúng một DN;
cán bộ sửa được sau. Là NHÃN LƯU, không suy lúc đọc. Vừa dựng nhóm hiển thị, vừa vào system prompt làm
CHỦ ĐỀ cuộc — KHÔNG thu hẹp quyền truy cập của tool (biên quyền vẫn là `allowed_company_codes`, ADR #14).
KHÔNG gọi là "thư mục": header nhóm chính là DN.

**Chưa gán doanh nghiệp** — cuộc trò chuyện `company_id = NULL`: mở từ trang không thuộc DN nào
(`/chat`, `/jobs`, trang quản trị) và chưa có mention nào quy về một DN. Là một nhóm hiển thị như DN,
xếp cuối. KHÔNG đồng nghĩa "không liên quan DN nào" — chỉ là chưa quy kết.

**Lệch phạm vi (cuộc ↔ trang)** — trạng thái cuộc trò chuyện gắn DN A trong khi cán bộ đang xem trang
DN B; mỗi lượt gửi ngữ cảnh trang HIỆN TẠI nên nội dung sẽ trộn hai DN. Xử lý: HIỆN thông báo + nút mở
cuộc mới cho B; không tự tách cuộc, không tự đổi nhãn.

**Tiếp tục cuộc gần nhất** — hành vi khi mở trợ lý: nối lại cuộc trò chuyện gần nhất CÙNG DN nếu dưới
24 giờ, ngược lại mở cuộc mới trong phạm vi đó. Mốc 24h vì mỗi lượt nạp lại 20 message cuối vào prompt.

## Tổng quan AI v2 (ADR #21 — chưa cài)

**Bảng số liệu tổng quan** — nửa TÍNH ĐƯỢC của một check overview: tập trung (số mã distinct, tỉ trọng
top-5, số mã phủ 80%), phân vị các trường số trong `details`, chiều lệch, tách theo sổ, so với năm
trước. Tính bằng Python, lưu `check_overviews.aggregate_json`, template render. ĐÓNG BĂNG theo snapshot
lúc sinh (không tính lại lúc load). KHÔNG chứa tổng tuyệt đối chéo đơn vị.

**Nhận định** — nửa do LLM viết: `nhan_dinh` · `phan_bo` · `diem_nong` · `de_xuat`, trả JSON, render
theo mục cố định. Chỉ ĐỌC bảng số liệu; mọi con số phải copy nguyên chuỗi đã cho.

**Cần đối chiếu (cờ)** — trạng thái một nhận định có con số không khớp chuỗi nào trong bảng số liệu
(hậu kiểm so khớp chuỗi). Hiện badge, KHÔNG publish âm thầm.

**Điểm nóng** — mục `diem_nong` của nhận định: ≤5 `subject_key` nổi bật kèm nhận xét, render thành link
sang trang chi tiết mã (truy nguồn).

**Sổ chi phí AI (`ai_usage`)** — bảng append-only một dòng mỗi lời gọi LLM tính tiền (`kind` chat |
overview, `ref`, model, tokens, `cost_usd`, user, thời điểm). Là NGUỒN của trần chi phí ngày và thống
kê `/admin/ai`. Cần vì `check_overviews` upsert nên không giữ được lịch sử chi tiêu: sinh lại cùng một
overview 3 lần trong ngày chỉ còn chi phí lần cuối.
