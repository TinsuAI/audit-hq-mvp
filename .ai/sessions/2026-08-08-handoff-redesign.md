# HANDOFF — phiên sau: REDESIGN màn gán cột

Mở file này trước, rồi mới đọc chỗ khác. Viết cho một phiên **bắt đầu từ con số không**.

---

## Việc của phiên sau, một câu

Thiết kế lại **màn gán cột + lưới xem trước + hệ nhãn/badge dùng chung** của luồng cán bộ,
theo phán quyết REDESIGN của audit `DESIGN-IS-2026-08-08/`.

**Lệnh đầu tiên gõ:** `/grill-with-docs` — lấy `DESIGN-IS-2026-08-08/03-verdict.md` làm đầu
vào. Rồi `/to-spec` → `/to-tickets`. **Ba lệnh này người dùng phải TỰ GÕ**, model không gọi
được (`disable-model-invocation: true`). Đừng tự chế lại quy trình của chúng.

`DESIGN-IS-2026-08-08/04-handoff-prompt.md` có sẵn một prompt tự chứa, nhưng nó viết cho
`/make-plan` (luồng claude-mem). Repo này chạy luồng matt-pocock. Lấy **nội dung** của nó,
đừng lấy **lệnh** của nó.

---

## Bối cảnh tối thiểu

Audit-HQ là công cụ cho **cán bộ Hải quan làm kiểm tra sau thông quan**, không phải kế toán
doanh nghiệp, không phải người dùng phổ thông. Họ sống trong Excel hàng ngày.

Việc chính của họ: đưa hồ sơ quyết toán một DN vào hệ thống sao cho **mọi con số hệ thống
đọc ra đều truy được về đúng ô trong file gốc**, rồi đọc phát hiện mà **không bao giờ nhầm
"chưa đánh giá được" với "đã soát và sạch"**. Toàn bộ giá trị sản phẩm nằm ở câu đó.

Ngăn xếp: FastAPI + Jinja2 + CSS thuần + JS thuần. **Không thêm framework front-end**
(`AGENTS.md`). UI tiếng Việt đủ dấu, giọng hành chính.

---

## Trạng thái ngay lúc bàn giao

- `main` = `388cb06`, đã push, CI xanh, **đã deploy lên `audit-hq-demo.tinsu.ai`**.
- Bộ test **1.747**, `PYTEST_EXIT=0`, xanh cả khi xáo (seed `2302101317`), `ruff` sạch.
- Alembic head `b5c6d7e8f9a0`. **DB dev đã migrate**; prod cũng đã migrate qua entrypoint.
- Issue #109–#116 **đóng hết**. Loạt #110 khép lại.
- Cây làm việc sạch.

---

## Audit: 13/30, REDESIGN

`claude-mem:design-is`, 10 nguyên tắc Dieter Rams, bốn subagent thu bằng chứng và **bị cấm
tự chấm điểm** (chấm điểm là việc của orchestrator, tránh mỗi agent nới tay một ít).

| # | Nguyên tắc | Điểm |
|---|---|---|
| 1 đổi mới · 2 hữu dụng · 7 bền lâu · 9 tài nguyên | | 2 |
| 3 thẩm mỹ · 4 dễ hiểu · 5 kín đáo · 8 kỹ chi tiết · 10 ít mà tốt | | 1 |
| **6 trung thực** | | **0** |

**Vì sao REDESIGN chứ không REFINE:** mô hình tương tác mâu thuẫn mô hình dữ liệu. Màn mời
cán bộ phát biểu **ba** trạng thái mỗi trường (đã gán / chưa gán / xác nhận vắng), nhưng
tầng adapter chỉ biết **một** ("cột nào cho trường nào"). Hai trạng thái kia không có đường
xuống chỗ đọc file. Đó là lỗi tầng kiến trúc giao diện, không sửa được bằng CSS.

**KHÔNG phải lý do:** codebase to, đã bỏ nhiều công. Đó là chi phí chìm.

---

## ĐÃ VÁ RỒI — đừng làm lại (`d75f07a`)

Ba lỗi trung thực khiến #6 chấm 0 đã được sửa **sau** khi audit chạy. Điểm #6 nay khoảng
2–3, tổng khoảng **16–17 — vẫn dưới 20, vẫn REDESIGN**, nhưng là nợ có kiểm soát chứ không
phải lỗi đang chảy máu.

1. Lời khai "không có trong file" không tới adapter → cột vẫn nạp vào Tầng 1.
   Vá: `apply_absent_fields` (`app/pipeline/saved_map.py`), gọi trong `ingest.py` sau parse.
2. Gửi biểu mẫu từ file cũ xoá sạch lời khai đã lưu. Vá: `None` = "biểu mẫu không hỏi",
   `[]` = "cán bộ bỏ tick".
3. "— chưa gán —" tự hoàn tác. Vá: ô trống **luôn** nghĩa "giữ nguyên"; thôi đọc một cột
   thì tick "Không có trong file".

**Quyết định thiết kế kèm theo, phiên sau nên giữ:** *chưa gán* không phải một phát biểu của
cán bộ — nó là trạng thái của máy. Cán bộ chỉ có hai phát biểu: "đọc ở cột N" và "không có
trong file". Nếu redesign muốn đổi điều này thì phải mở đường lưu trạng thái thứ ba xuống
tới adapter, đừng chỉ thêm một mục vào bộ chọn.

---

## Năm việc đòn bẩy cao nhất (nguyên văn từ `03-verdict.md`, đã trừ 2 việc vừa vá)

1. **#4 + #5 — gộp 10 bộ từ vựng nhãn xuống còn 3.** Một trục "cột nào", một trục "chắc tới
   đâu", một trục "còn việc gì". `Đã gán` và `Đã kiểm` hiện **cùng một màu xanh, cạnh nhau ở
   mọi cột**. Nguồn: `app/pipeline/file_page.py:44-60,81-85` · `app/adapters/evidence.py:45-56`
   · `app/static/cell-grid.js:186-192,420-455`.
2. **#8 — dựng trạng thái `disabled` và `empty`, sửa vòng focus.** `:disabled` **không có
   một rule nào** trong toàn bộ CSS; `.empty-state` có markup nhưng **không có rule nào**;
   vòng focus của form dùng `outline:none` + box-shadow tương phản **1,34** (ngưỡng 3:1).
   Nguồn: `app/static/style.css:846-850`.
3. **#3 + #10 — ép về hệ token, dọn xác.** 85 màu literal ngoài `:root` (19 cái trùng khít
   một token đã có), 49 khai `font-size` lệch thang / 26 giá trị rời rạc, 42 class CSS chết,
   13 selector khai trùng giá trị xung khắc, một dấu `}` thừa ở `style.css:1328`.
4. **#10 — tính năng làm nổi cột chết hoàn toàn.** `app/static/cell-grid.js:486` bắt
   `input.review-idx`; **không template nào phát class đó**. Cả chuỗi
   `wireColumnInputs → setHighlight → showColumn` không bao giờ chạy. Hoặc nối lại, hoặc xoá.
5. **#4 — định nghĩa thuật ngữ NGAY TẠI CHỖ DÙNG.** `Khớp đẳng thức`, `Chỉ theo vị trí`,
   `Khớp tiêu đề`, `Đã gán`/`Chưa gán` không có tooltip nào trên `document_file.html`. Cẩm
   nang có giải thích nhưng **không màn nào liên kết tới** (grep `tai-lieu|huong-dan` trong
   4 template chính → 0 kết quả).

Nợ khác, không chặn ai: không có skip-link · 6 điều khiển trong `#ai-panel` `aria-hidden`
vẫn nằm trong chuỗi tab · `thead` của `.fieldmap-table` thiếu `scope="col"` · lưới xem trước
không có tên khả truy cập nào · 83% JS tải về là thanh AI không dùng ở màn đó ·
`/jobs/unread.json` poll mỗi 10 giây vĩnh viễn.

---

## GIỮ NGUYÊN — không nằm trong phạm vi redesign

- **Mô hình miền backend**: ADR #18, #23, #24, #25, #28 (`.ai/DECISIONS.md`). Đây là thứ làm
  sản phẩm có giá trị.
- **Cổng `not_evaluable` hai mức** (`app/checks/sources.py:104-122`) — cơ chế đúng.
- **Đạo đức câu chữ**: 1.155 chuỗi, **0 thổi phồng, 0 dark pattern**. Điểm rủi ro tự hạ thấp
  đúng mực (`companies_list.html:65`); `base.html:108` khẳng định quyết định cuối thuộc cán
  bộ. **Giữ nguyên giọng này.**
- **Ý tưởng bảng chuyển vị** hiện dòng dữ liệu thật đọc qua cột đang chọn. Giữ Ý, dựng lại
  CÁCH THỂ HIỆN.
- Ngoài phạm vi hẳn: mô hình kiểm tra, thang điểm rủi ro, catalog check, thanh AI.

---

## Bẫy đã trả giá — đừng dẫm lại

- **Push vào `main` KÉO THEO DEPLOY LÊN PROD**, không chỉ chạy test. Workflow
  `Test & Deploy to Tinsu`, runner self-hosted `tinsu-prod`, `entrypoint.sh` tự chạy
  `alembic upgrade head`. Có sao lưu DB prod trước, nhưng **đừng push khi chưa định deploy**.
- **zsh: glob trần không khớp thì HUỶ CẢ LỆNH và vẫn thoát 0.** `rm -f foo.sqlite*` làm
  pytest phía sau không bao giờ chạy mà không có dấu hiệu gì. Viết đủ tên file kèm
  `-wal`/`-shm`; bắt mã thoát bằng `> log 2>&1; echo $?`, đừng suy từ `tail` đã lọc.
- **Máy này KHÔNG có `sqlite3` CLI.** Sao lưu DB bằng `Connection.backup` của Python —
  `cp` một file `.sqlite` lẻ bỏ rơi phần WAL chưa checkpoint.
- **Ảnh chụp cả trang (`full_page=True`) vẽ phần tử `sticky` ở vị trí đang dính** rồi để lại
  một mảng trắng chỗ nó vốn nằm. Ảnh ra không giống thứ cán bộ thấy, và chính nó làm tôi
  chẩn đoán sai một lỗi bố cục. Chụp **theo khung nhìn**.
- **`/implement`, `/to-spec`, `/to-tickets`, `/grill-with-docs`, `/handoff` chặn model gọi.**
  `/tdd`, `/code-review`, `/rev`, `/fix`, `/v_handoff` thì gọi được.
- Test đi qua route/hàng đợi **phải dùng fixture `app_db`**, không tự dựng engine
  (`AGENTS.md`). Chạy test với `DATABASE_URL` trỏ file scratch, không dùng DB dev.

---

## Ảnh và bằng chứng có sẵn

- `DESIGN-IS-2026-08-08/01-evidence.md` — bằng chứng gom từ 4 subagent, mọi số có `file:line`.
- `.ai/features/2026-08-08-man-gan-cot-theo-truong/screenshots/` — 4 ảnh bảng chuyển vị hiện
  tại, kèm `ui_smoke.py` chạy lại được (server throwaway, cổng tự do, không đụng DB dev,
  không đụng cổng 8200).
- 45 ảnh của 6 feature gần đây ở `.ai/features/2026-08-*/screenshots/`.

## Đọc thêm khi cần

`.ai/sessions/2026-08-08-implement-111-115-bon-ve.md` — nhật ký đầy đủ của đợt cài #111–#115,
audit, và các bản vá trung thực. `.ai/DECISIONS.md` ADR #28 — mô hình tập trường khai.
