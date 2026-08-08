# 01 — Bằng chứng (gom từ 4 subagent, mỗi phát hiện có nguồn)

Subagent bị CẤM chấm điểm; chúng chỉ trả số liệu và trích dẫn. Chấm điểm ở `02-scorecard.md`.

## A. Cấu trúc

- **Phần tử tương tác, lúc chạy** (`document_file.html`, sau khi nở vòng lặp): m15 **31** ·
  m15a 29 · m16 23 · **bcct 45**. Tĩnh chỉ 15 (`document_file.html:45,49,53,124,139,193,196,214,230,286,288,290`).
- **Độ sâu lồng tối đa 8**: `form:112 > div.fieldmap-card:169 > table:170 > tbody:183 >
  tr:184 > td:187 > select:196 > option:197`.
- **Bốn cách render CÙNG một trường biểu mẫu `col_{field}`**: select `:196`, ô chữ nhóm
  cột `:193`, ô chữ cũ `:214`, hidden `:218`. Cộng checkbox `absent_` `:230` gỡ gán.
- **Hai bộ chọn trang tính cùng màn, khác ngữ nghĩa**: `document_file.html:124` ghim
  trang cho lượt nạp sau; `cell-grid.js:387-394` chỉ đổi khung nhìn lưới.
- **10 bộ từ vựng nhãn trên MỘT màn**: `match_source_label` (5 giá trị,
  `file_page.py:44-54`) · `layout_label` (3, `:56-60`) · cách nói ghim trang (hai lối
  diễn đạt, `:85` vs `:117`) · khoá dòng/bắt buộc `:177-178` · `state_label` (3,
  `file_page.py:81-85`) · `review_label` (2, `evidence.py:53-56`) · `evidence_label` (5+1,
  `evidence.py:45-51`) · `cg-col-needs/mapped` (`cell-grid.js:186-192`) · `#cg-notes`
  (`:420-439`) · `#cg-status` (`:441-455`).
- **42 class CSS chết** trong `style.css` (không template/JS/Python nào tham chiếu), gồm
  cả cụm 12 selector `.upload-slot*` và `.score-pill.low/.mid/.high`.
- **13 selector khai trùng, giá trị xung khắc**, gồm `.doc-file-badge` `:1254`
  (`0.68rem`) vs `:1971` (`var(--fs-xs)`).
- **Tính năng chết hoàn toàn**: `cell-grid.js:486` bắt `input.review-idx`; **không
  template nào phát class đó**. Chuỗi `wireColumnInputs → setHighlight → showColumn`
  không bao giờ chạy; `.cg-col-hi` `:2461` / `.cg-cell-hi` `:2477` không đường nào tới.
- **Số bước việc chính**: 5 khi cấu trúc đã xác nhận; **8+ khi cổng cột bắn**, mỗi file
  bị gác thêm một lượt. Xác nhận lần đầu KHÔNG kéo theo chạy check
  (`companies.py:1680` `was_parsed` False → `then_run_checks=None`), nên vẫn phải bấm
  "Chạy kiểm tra" riêng.

## B. Thị giác

- **Thang giãn cách** `--space-*` 4→48px (`style.css:57-65`); **15 giá trị inline lệch
  thang** (2/5/6/10/14px) ở `admin_ai.html:274,285,441` · `admin_risk_tiers.html:57,65,71`
  · `admin_user_scope.html:44` · `admin_users.html:80` · `company_detail.html:215,355,373,374,553,564`
  · `item_detail.html:300`. `cell-grid.js:21-24` dựng hệ hình học thứ tư lúc chạy.
- **Thang chữ** `--fs-*` 12→30px (`:71-78`); **73 khai `font-size` không dùng token**,
  trong đó **49 lệch thang / 26 giá trị rời rạc**; 3 giá trị dưới sàn 12px
  (`0.7rem` ×3, `0.6875rem` `:685`, `0.625rem` `:730`) cộng 7 chỗ `11px`.
- **101 màu literal rời rạc / 250 lần xuất hiện**; **85 literal nằm NGOÀI `:root`**
  (hardcode) so với 459 lần dùng `var(--c-*)`. **19 literal trùng khít một token đã có**
  (~65 lần), vd `#1d3557`×11 = `--c-brand-500`, `#fff`×9 = `--c-surface`.
- **Một dấu `}` thừa mức cao nhất** ở `style.css:1328`.
- **Tương phản thấp nhất**: `.badge-op-unknown` `#6b7280`/`#f3f4f6` = **4.39 FAIL**;
  `--c-text-subtle` trên nền trang = **4.44 FAIL** (dùng ở `.form-hint`, `.cg-status`,
  `.app-footer`, `.breadcrumbs .sep`); `.fm-col-absent` `opacity:.55` → **2.55 FAIL**.
- **Trạng thái**: empty **có markup nhưng KHÔNG có rule CSS nào** (`.empty-state` không
  tồn tại trong mọi file CSS) · loading có · error có · success có (thiếu màu tiêu đề) ·
  focus **một phần** (form dùng `outline:none` + box-shadow tương phản **1.34**, dưới
  ngưỡng 3:1) · **disabled KHÔNG có rule nào** — ô khoá nhìn y hệt ô sửa được
  (`08_form_nam_dau_nop_bcqt.png`).
- **Dark mode: không có** trong app shell. **`prefers-reduced-motion`: 2/4 animation,
  0/19 transition**.
- **Ảnh render**: 4 kiểu chip trong một bảng · "Huỷ" có 3 lối thể hiện khác nhau
  (`08_admin_dinh_dang_hien_thi.png` link gạch chân vs nút viền ở 2 màn khác) · mức độ
  nghiêm trọng mã hoá **ba lần** trên một dòng (nền màu + pill có nhãn + pill trạng thái,
  hai bán kính bo khác nhau cạnh nhau, `09_bang_phat_hien_quy_uoc_anh_my.png`) · 8 nút
  công cụ đều gắn emoji màu trên nền đơn sắc.

## C. Câu chữ & tính trung thực

- **1.155 chuỗi rời rạc**; **22 chuỗi trên 200 ký tự**; dài nhất **564 ký tự**
  (`document_file.html:138`) — một đoạn liền chứa 4 quy tắc khác nhau về sổ quyết toán.
- **Không có thổi phồng, không có dark pattern.** Đã soát 17 từ khoá marketing và toàn bộ
  `checked`, giá/gói/hết hạn, confirmshaming → sạch. Ngược lại còn tự hạ thấp đúng mực:
  điểm rủi ro được nói rõ "không phải đánh giá tuân thủ theo TT 81/2019"
  (`companies_list.html:65`), và `base.html:108` khẳng định quyết định cuối thuộc cán bộ.
- **Thuật ngữ KHÔNG được định nghĩa ngay trên màn đang dùng**: `Khớp đẳng thức`,
  `Chỉ theo vị trí`, `Khớp tiêu đề`, `Đã gán`/`Chưa gán` — không tooltip, không chú thích
  ở `document_file.html:242-244`. Cẩm nang có giải thích nhưng **không màn nào liên kết
  tới** (grep `tai-lieu|huong-dan` trong 4 template chính → 0). `Chuyển MĐSD` không bao
  giờ được viết đủ ở nơi nó hiện.
- **Bốn chỗ nhãn hứa khác code làm** (đã tự kiểm lại 2 chỗ nặng nhất):
  1. **Lời khai "Không có trong file" KHÔNG tới adapter.** `grep -rn "absent" app/adapters/`
     → **0**. `resolve_columns` (`templates.py:210`) luôn trộn `base_col`, nên cột đó VẪN
     được nạp vào Tầng 1. Check trả "chưa đánh giá được" trong khi màn dữ liệu gốc hiện
     số của chính cột ấy — hai màn nói ngược nhau.
  2. **Xoá âm thầm**: `absent_fields` tính vô điều kiện (`companies.py:1719`) nhưng ô
     checkbox chỉ render khi `has_choices` (`document_file.html:224`), và
     `save_column_map` ghi đè vô điều kiện (`saved_map.py:101`) → gửi biểu mẫu từ file nạp
     trước #112 **xoá sạch lời khai vắng đã lưu, không một dòng thông báo**.
  3. **"— chưa gán —" bị gán lại âm thầm** và **giao diện quay về "Đã gán"** ở lần tải
     sau (`templates.py:210` + `:266` → `file_page.py:210-238`), không báo gì.
  4. **Nút "Xác nhận & nạp dữ liệu" nạp lại CẢ KỲ**, không phải file đang mở
     (`companies.py:1822`, payload `{company_code, year}`), trên trang có `<h1>` là một
     tên file; và gán nhãn "Cán bộ xác nhận" cho cả những cột cán bộ không hề có ô để sửa.
- **"Đã kiểm" hiện cạnh "Chỉ theo vị trí" trên cùng một dòng**: `registry.py:574-577`
  trả `VERIFIED` khi cột không check nào đọc, kiểm TRƯỚC nhánh `POSITION_ONLY`.
- **Cùng một khái niệm, nhiều tên**: cổng xác nhận cột có **5 lối diễn đạt**; `— chưa gán —`
  dùng cho hai đối tượng khác nhau ở hai màn; `loại hình` mang hai nghĩa (mã loại hình tờ
  khai vs loại sổ quyết toán).

## D. Tải & tiếp cận

- **JS 125.882 B giải nén** (86.316 B truyền), trong đó **103.616 B (83%) là thanh AI
  nằm ngoài màn hình và không dùng ở màn này**. CSS 121.597 B + **font 192.520 B**.
  **`style.css` chỉ dùng 17,1%**.
- **18 request lúc tải**; `/jobs/unread.json` **poll mỗi 10 giây, vĩnh viễn**
  (`base.html:94`). 0 ảnh/0 SVG — mọi biểu tượng là ký tự emoji.
- **TTI 168–367 ms** (localhost, cache ấm). Đường lạnh khác hẳn: lần đầu mở một trang
  tính trả HTTP 202 rồi poll tối đa ~13 phút (`cell-grid.js:29-30`).
- **0 animation lúc nghỉ.** **21 badge hiện cùng lúc** trên một file Mẫu 16 8 trường;
  `Đã gán` và `Đã kiểm` **cùng là `.badge.info`, cùng màu xanh, cạnh nhau ở mọi cột**.
- **`badge danger` KHÔNG có rule** — `khoá dòng` render thành chữ đậm trần, không phải chip.
- **Không có skip-link** (grep toàn bộ → 0); 7 tab đầu ở mọi trang là menu header;
  `<main>` không có `id`.
- **Thứ tự focus**: mỗi `<select>` cột cách checkbox "không có trong file" của CHÍNH nó
  **8–12 chặng** — bảng chuyển vị đặt toàn bộ select trên một hàng, toàn bộ checkbox ở
  hàng sau, nên xác nhận từng trường không phải một đường bàn phím liền mạch.
- **6 điều khiển trong `#ai-panel` `aria-hidden="true"` vẫn nằm trong chuỗi tab** (chặng 35-40).
- **Chỉ chuột**: cuộn ngang bảng gán cột; **toàn bộ tooltip `title`** (kể cả chú thích ô
  lưới và nhãn cột đã map).
- **`thead` của `.fieldmap-table`: 9 `<th>` đều THIẾU `scope="col"`** — bảng đã chuyển vị
  nên một ô cần cả hai trục để có tên, mà chỉ một trục được khai.
- **Lưới xem trước không có tên khả truy cập nào**: `.cg-side`, `.cg-corner`, 128 `.cg-cell`
  đều là `<div>` trần, không role, không `aria-label`, không `aria-rowcount/colcount`.
