# BACKLOG — Audit-HQ MVP

> Tính năng / cải thiện chờ schedule. Không thay STATUS.md (state hiện tại) hay
> sessions/ (history). Mục nào đi vào sprint → chuyển sang STATUS / session log.

## Rà soát toàn bộ ngôn ngữ tiếng Việt trên giao diện — ĐÃ LÀM, CHỜ MERGE

> Chốt 2026-07-27 (owner). Khởi từ badge tổng quan AI ghi "Cần đối chiếu số liệu" —
> nghe không ổn vì **lặp đúng câu của dòng miễn trừ trách nhiệm ngay dưới nó**
> (`company_detail.html:413`), nên badge không nói thêm được gì.
>
> **TRẠNG THÁI 2026-07-27:** đã làm trên nhánh `fix/badge-wording` (đã rebase lên `main`
> `a3525e0`; badge sửa sẵn giờ là `2dd6a48`). 4 commit tiếp theo phủ cả 6 mục dưới.
> **CHƯA MERGE, CHƯA DEPLOY** — vẫn giữ nguyên quyết định gộp một lần deploy.
>
> **Chốt từ vựng đợt này (owner chọn):** GIỮ `file`, `Excel`, `AI`, tên sản phẩm
> (OpenRouter/Claude/…), mã đơn vị (`MTR`/`KGM`/`PCE`), mã kiểm tra, và định danh trong
> ngữ cảnh quản trị/dòng lệnh (`nvl_balances`, `python -m app.pipeline.ingest`).
> ĐỔI: `link`→đường dẫn · `test`→kiểm tra · `map`→bố cục cột · `tick`→đánh dấu ·
> `scope`→nhóm điểm · `preview`→xem trước · `read-only`→chỉ đọc · `model`→mô hình ·
> `raw`→thô · `0-index`→đếm từ 0 · `Token in/out`→Token vào/ra.
>
> **Còn mở sau đợt này:** `PERCENTILE_KEYS["C3.2"]` trỏ `divergence`, nhưng
> `c3_classify.py:157` ghi giá trị CHUỖI (`chapter`/`heading`/`subheading`) nên
> `_numeric` trả None và ô phân vị của C3.2 **chưa bao giờ render** — mục cấu hình chết,
> cần quyết định bỏ hay đổi sang giá trị số (đụng ngữ nghĩa check, không gộp vào đợt chữ).

**Nguyên tắc:** mọi chữ CÁN BỘ ĐỌC phải là tiếng Việt có nghĩa. Tên cột DB / khoá JSON
nội bộ **giữ tiếng Anh** (`status`, `check_code`, `needs_review`) — đó là định danh, không
dịch; nhưng **không được để lọt ra màn hình** dưới dạng thô.

### Đã biết — theo mức độ lộ liễu (cả 6 mục ĐÃ XỬ LÝ, xem ghi chú cuối mỗi mục)

1. **`job.result` in nguyên JSON cho mọi cán bộ** (`job_detail.html:31`,
   `{{ job.result | tojson(indent=2) }}`). Nặng nhất vì giờ **lẫn hai thứ tiếng trong
   cùng một khối**: handler cũ dùng khoá tiếng Anh (`combos_fired`, `years_processed`,
   `findings_per_check`, `risk_score`), handler `AI_OVERVIEW_BATCH` mới dùng khoá tiếng
   Việt (`da_tao`, `bo_qua`, `bo_qua_con_moi`, `bo_qua_chua_toi_luot`, `dung_vi`,
   `checks_loi`). **Hướng sửa đề xuất:** trả khoá về tiếng Anh cho nhất quán với phần
   còn lại, rồi render qua bảng nhãn tiếng Việt ở trang công việc thay vì dump JSON.
   → **XONG** (`734cf2d`): khoá `AI_OVERVIEW_BATCH` về tiếng Anh (`created`/`skipped`/
   `failed`/`stopped_reason`…), `app/jobs/result_labels.py` giữ bảng nhãn + `describe_result`,
   `job_detail.html` render bảng nhãn thay `tojson`. `job.kind` cũng có nhãn (`jobs_list` +
   `job_detail`). Test khoá tập khoá: chạy thật 3 handler rồi đối chiếu với bảng nhãn.
2. **Ô phân vị hiện tên trường thô** — `company_detail.html:339` in `{{ nf.key }}`, ra màn
   hình thành `M15_REPURPOSE`, `DIFF_PCT`, `RATIO_PCT`, `CLOSING_QTY`,
   `THEORETICAL_CONSUMPTION`, `DIVERGENCE`. Cần bảng nhãn tiếng Việt cho 11 khoá khai ở
   `app/ai/overview_stats.py:PERCENTILE_KEYS` (vd `m15_repurpose` → "Lượng chuyển mục
   đích", `diff_pct` → "Chênh lệch (%)").
   → **XONG** (`92b77ab`): `PERCENTILE_LABEL_VI` ở `overview_stats.py`, đưa vào template
   globals; template `.get(nf.key, nf.key)`. Cũng đổi `n=12` → `12 phát hiện`.
   Thực tế chỉ 7 khoá RIÊNG BIỆT (12 mục khai), không phải 11.
3. **`evidence_label`** (`document_review.html:120`) — kiểm lại đủ nhãn tiếng Việt cho mọi
   giá trị `evidence`, không rơi về chuỗi gốc.
   → **XONG** (`05f6472`): đủ nhãn sẵn; thêm 2 test khoá lại — mọi nguồn trong `_RANK` có
   trong `SOURCE_LABEL_VI`, mọi field trong `_EVIDENCE_ORDER` có trong `FIELD_LABEL_VI`,
   và `_evidence_columns` không rơi fallback với mọi (cột, nguồn).
4. **Từ tiếng Anh còn dùng trong câu tiếng Việt:** `combo` (`admin_checks.html:26`
   "Phát hiện kết hợp (combo)"), `file` (`upload_data.html` nhiều chỗ: "Kéo thả hoặc bấm
   chọn file", "100MB/file", "chẩn đoán cấu trúc file"), `link`
   (`edit_company.html:32` "không gãy link"). Quyết định giữ hay dịch từng từ — `file`
   và `Excel` có thể là từ mượn đã quen, `link` thì nên đổi "đường dẫn".
   → **XONG** (`e6b3f1c`): theo bảng chốt ở đầu mục. `combo` GIỮ (mã `COMBO_*` hiện trên
   danh sách phát hiện nên cần neo từ), nhưng câu văn quanh nó dùng "phát hiện kết hợp".
5. **`AI`** dùng khắp nơi ("Trợ lý AI", "Cấu hình AI", "Tổng quan AI"). Nhiều khả năng
   GIỮ — nhưng cần chốt một lần cho nhất quán thay vì mỗi chỗ một kiểu.
   → **XONG**: GIỮ `AI`. Thống nhất "Trợ lý AI" (bỏ "AI Assistant"), "mô hình" thay
   "model", "gọi mô hình AI" thay "gọi LLM".
6. **Định dạng ngày kiểu ISO lọt ra UI** — `job_detail.html:24` dùng
   `strftime("%Y-%m-%d %H:%M:%S")` trong khi phần còn lại dùng `%d/%m/%Y %H:%M`.
   → **XONG** (`734cf2d`): `job_detail` (3 chỗ) + `jobs_list` (2) + `admin_checks_detail`
   (2). Quét lại `app/templates/*.html`: không còn `%Y-%m-%d` nào.

### Cách làm

Quét `app/templates/*.html` + chuỗi trong `app/routes/*.py` (thông báo lỗi, `msg=`,
`error=`) + `app/static/*.js` (chuỗi hiện cho người dùng). Đối chiếu với
[[vietnamese-ui-text-style]]: thuần Việt, chú ý sắc thái, **cấu hình runtime ≠ bug**.
Mỗi chuỗi tự hỏi: cán bộ đọc có hiểu ngay không, và nó có nói thêm gì so với chữ ngay
cạnh không.

---

## Multi-user + role-based access

### Tài khoản riêng cho cán bộ HQ
- **Hiện tại**: chỉ 1 cookie session global `admin/admin` (env `AUTH_USER`/`AUTH_PASSWORD`).
- **Cần**: nhiều tài khoản, mỗi cán bộ HQ 1 tài khoản, không dùng chung admin.
- **Scope**: bảng `users(id, username, password_hash, role, created_at, last_login_at)`. Migration mới. Login form lookup theo username, verify hash (argon2 hoặc bcrypt). Admin có UI tạo/xoá user.
- **Roles cần thiết**: `admin` (Trọng Tín/Tinsu), `officer` (cán bộ HQ). Sau này có thể thêm `auditor` (chỉ xem, không sửa).
- **Migrate `AUTH_USER` env**: lần đầu seed 1 user admin từ env (tương tự `seed_ai_defaults`).
- **Out of scope V1**: SSO, 2FA, audit log đăng nhập, password reset email.

### Role-based view (RBAC)
- **`officer` KHÔNG được phép thấy**:
  - `/admin/units` (cấu hình UOM)
  - `/admin/ai` (cấu hình AI)
  - Bất kỳ trang `/admin/*` nào trong tương lai
  - Header link "⚙️ Đơn vị tính", "🤖 AI"
- **`officer` được phép**:
  - `/companies`, `/companies/{code}`, `/findings/{id}`, `/companies/{code}/data`, `/companies/{code}/export`
  - Sidebar AI assistant + chat — nhưng có giới hạn (xem dưới)
- **Officer được phép tạo DN + upload data + run-checks**: theo quyết định 2026-05-25 (user xác nhận). Chỉ `/admin/*` mới cần admin.
- **Implementation**: decorator `@require_role("admin")` cho các route admin. Sidebar template kiểm tra `user.role` trước khi render link.

### Tool-use UI chỉ cho admin
- **Lý do**: cán bộ HQ thấy "đang gọi tool search_findings..." trong chat → confusing, lộ implementation detail. Họ chỉ cần thấy câu trả lời.
- **Hiện tại**: sidebar.js hiện tool_call + tool_result event như message vàng amber.
- **Cần**: trong `sidebar.js`, check `meta.is_admin` (từ `/api/ai/meta`) — nếu false thì silent skip render tool_call + tool_result events. Audit log backend vẫn lưu đầy đủ.
- **API**: `/api/ai/meta` thêm field `is_admin: bool` dựa trên user role.

### Tương quan với feature đang có
- **AI conversation history**: hiện list theo `user` field. Multi-user → cần lọc theo `user_id` đúng — đã đúng rồi (truy vấn `WHERE user = current_user`), nhưng verify thêm khi có nhiều tài khoản.
- **Audit log `/admin/ai` section 5**: hiện hiện ALL conversation của mọi user. Đây là intended behavior cho admin. Officer KHÔNG được vào page này.
- **Page context inject vào system prompt**: không tiết lộ user role cho LLM (an toàn).

### Trình tự đề xuất khi sprint
1. Migration `users` + hash password + login lookup (1 ngày).
2. Decorator `require_role` + restrict admin routes (0.5 ngày).
3. Sidebar tool_use hide for non-admin (0.5 ngày).
4. Admin UI tạo/xoá user (1 ngày).
5. Test cuối: tạo 2 user (admin/cán bộ X), verify không cross access (0.5 ngày).

Tổng: ~3.5 ngày làm việc. Có thể chèn sau Day 7-8 hiện tại (QA + deploy AI) hoặc gộp luôn nếu cán bộ HQ chuẩn bị thử demo.
