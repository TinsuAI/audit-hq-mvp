# Thiết kế lại màn gán cột · lưới xem trước · hệ nhãn ba trục

**Vé:** #117 (loạt) — #118, #119, #120, #121, #122, #123, #124, #125, #126, #127, #128, #130
**Vé này:** #129 — bằng chứng cho NGƯỜI xem, và lượt kiểm bằng mắt bốn thứ không seam nào
ngoài trình duyệt phủ được.
**Ngày:** 2026-08-09 · **Đo trên:** Chromium 1440×1000, `device_scale_factor=2`

---

## Việc loạt vé này làm

Audit thiết kế `DESIGN-IS-2026-08-08/` chấm luồng cán bộ **13/30** theo 10 nguyên tắc
Dieter Rams và phán quyết **REDESIGN**. Lý do không phải "codebase xấu" mà là một mâu
thuẫn tầng kiến trúc: màn mời cán bộ phát biểu **ba** trạng thái mỗi trường (đã gán /
chưa gán / xác nhận vắng) trong khi tầng adapter chỉ biết **một** ("cột nào cho trường
nào"). Hai trạng thái kia không có đường xuống chỗ đọc file.

Mười hai vé con, mỗi vé cắt thẳng từ `main`, review hai trục trước khi merge.

---

## Bốn tồn dư kiểm bằng mắt

Bộ test của repo không thấy được bốn thứ dưới đây: lưới dựng bằng JavaScript từ payload
`/cells`, nên `TestClient` chỉ đọc được cái vỏ máy chủ trả về. `ui_smoke.py` cạnh file này
chạy thật và khẳng định **30 phép đo**; phần dưới ghi cả những gì ĐỌC ĐƯỢC BẰNG MẮT trên
ảnh, kể cả thứ phép đo không hỏi tới.

### 1. Làm nổi cột có thật sự sáng lên và cuộn tới không (#122)

**Đo được:** chọn “Tồn cuối kỳ” (cột 10) ở bảng gán cột → `.cg-col-hi` = 1,
`.cg-cell-hi` = 15, `scrollLeft` **0px → 484px**. Rời ô thì `.cg-col-hi` về 0.

**Nhìn thấy** (`02_lam_noi_cot_sang_va_cuon.png`): ô tiêu đề cột K đổi sang nền cam đậm,
cả cột dữ liệu bên dưới nhuộm vàng nhạt, và lưới đã cuộn ngang — cột A–D không còn trong
khung, cột K nằm sát mép phải. Chữ “Tồn cuối kỳ” ở dòng tiêu đề (dòng 9 của trang tính)
cũng đổi màu theo. Đây là tính năng audit ghi là **chết hoàn toàn**
(`cell-grid.js:486` bắt `input.review-idx`, không template nào phát class đó).

### 2. Quan hệ bộ chọn trang tính đã gộp, lúc chạy thật (#124)

**Đo được:** đúng MỘT bộ chọn với hai trang (`Phụ lục`, `BCQT_NVL`);
`select[name="sheet"]` = 0 phần tử; bấm đổi trang **không tải lại trang** (biến đánh dấu
đặt trước cú bấm còn nguyên); địa chỉ thành `?sheet=0`; `aria-current` dời sang nút đang
chọn; vùng cài đặt **tự mở** vì trang đang xem khác trang hệ thống đọc.

**Nhìn thấy** (`03_bo_chon_trang_tinh_da_gop.png`): hàng nút “Trang tính đang xem:” với
“Phụ lục” đang tô đậm, lưới hiện đúng nội dung trang phụ (2 dòng × 1 cột), và vùng “Cài
đặt đọc file” bên dưới đã mở sẵn với nút “Ghim trang “Phụ lục” & nạp lại”. Nút ghim mang
đúng tên trang ĐANG XEM, không phải tên trang đang ghim.

### 3. Số dòng / số cột do JS đóng vào (#123)

**Đo được:** máy chủ dựng `aria-rowcount="-1"` / `aria-colcount="-1"` (CHƯA BIẾT theo
đúng nghĩa ARIA quy định — máy chủ không mở file); sau khi cửa sổ đầu về, lưới ghi đè
thành **69 dòng × 11 cột**, khớp bộ dữ liệu (9 dòng tiêu đề + 60 dòng hàng). `role` là
`table`, không phải `grid`. Lưới có `aria-label`.

**Nhìn thấy** (`01_luoi_khai_hinh_dang.png`): dòng trạng thái dưới lưới in
“69 dòng × 11 cột · Bảng tính Excel dạng gói ZIP (OOXML) · lấy từ kho đệm xem trước” —
cùng con số với thuộc tính ARIA, tức hai đường nói cùng một điều.

### 4. Tương phản SAU KHI trình duyệt hợp thành

Phép đo trong `tests/test_static_assets.py` so một CẶP GIÁ TRỊ ghim trong stylesheet; nó
không tính `opacity`, thứ tự xếp lớp, nền thừa hưởng, màu nửa trong suốt. Ở đây đo trên
màu đã hợp thành: đi ngược cây cha gom nền, nhân `opacity` tích luỹ, rồi mới tính tỷ số.

| Chỗ đo | Tỷ số | Sàn |
|---|---:|---:|
| Nhãn trường ở bảng gán cột (`.fm-fname`) | 17,85 | 4,5 |
| Chữ trong ô lưới (`.cg-cell`) | 17,85 | 4,5 |
| Câu căn cứ ở dòng trường (`.fm-evi`) | 7,58 | 4,5 |
| Dòng đã khai vắng (`.fm-row-absent .fm-evi`) | 7,24 | 4,5 |
| Câu nghĩa ở màn dữ liệu (`.evidence-key dd`) | 6,21 | 4,5 |
| Gợi ý trong vùng cài đặt (`.fp-set .form-hint`) | 5,16 | 4,5 |
| Dòng trạng thái dưới lưới (`.fp-status`) | 4,82 | 4,5 |

Dòng đã khai vắng là chỗ #121 thay `opacity: .55` — audit đo được **2,55** ở đó.

---

## Đo thêm ngoài bốn tồn dư

**Bàn phím (#126).** Chặng tab đầu tiên của trang là skip-link (`document.activeElement`
mang class `skip-link` sau đúng một phím Tab); bấm Enter thì focus vào
`#noi-dung-chinh`. Thanh trợ lý đóng: khai `inert`, và **0/11** điều khiển bên trong nhận
được focus khi gọi `.focus()` từng cái. Mở thanh → `inert` mất; đóng bằng Escape →
`inert` quay lại **và focus về `#ai-fab`**, không rơi về `<body>`. Trang file không tải
thanh trợ lý (`#ai-panel` = 0 phần tử).

**Nghĩa nguồn bằng chứng ở màn dữ liệu (#130).** 3 dòng nghĩa hiện thành chữ, không nằm
trong tooltip; tương phản 6,21.

**Không lỗi JavaScript** trên mọi màn đã đi qua.

---

## Ghi lại thứ ảnh cho thấy mà phép đo KHÔNG hỏi tới

- `05_man_du_lieu_nghia_thanh_chu.png`: bảng dữ liệu in “0 dòng · Không có dữ liệu”. Đó
  là ĐÚNG với bộ dữ liệu này — lượt nạp dừng ở cổng xác nhận cột (`gate=True`) nên chưa
  ghi dòng Tầng 1 nào. Ảnh chứng minh khối nghĩa, không chứng minh bảng dữ liệu.
- `04_skip_link_hien_khi_nhan_focus.png`: skip-link khi nhận focus **che một đoạn chữ của
  dải “Dữ liệu mẫu”** ở góc trên bên trái. Nó là lớp phủ, chỉ hiện lúc có focus, và biến
  mất khi tab tiếp — nhưng đây là hành vi có thật, ghi lại để không ai chẩn đoán nhầm.
- `02_lam_noi_cot_sang_va_cuon.png`: cột A–D cuộn ra khỏi khung khi lưới nhảy tới cột 10.
  Cột `#` (số dòng) dính lại bên trái, đúng thiết kế.

---

## Cách chạy lại

```bash
.venv/bin/python .ai/features/2026-08-09-thiet-ke-lai-man-gan-cot/ui_smoke.py
```

DB throwaway ở `/tmp`, cổng tự do, dữ liệu bịa. **Không đụng DB dev, không đụng cổng
8200.** Ảnh ghi đè vào `screenshots/` cạnh file này.

Bản chạy ghi lại ở đây: **30/30 phép đo ĐẠT**, 5 ảnh.

---

## Chạy lại audit thiết kế — LÀM THÔNG TIN, không phải cổng

Vé #129 đòi chạy lại audit và ghi điểm **để đọc**, không phải để đạt/không đạt. Lý do đã
ghi trong ADR #29: điểm do model chấm, và một cổng theo điểm là lời mời chỉnh sản phẩm
cho vừa thước đo.

**Cách chạy lại, và giới hạn của nó.** Giữ đúng hình dạng của lượt audit gốc: một
subagent đi ĐO và **bị cấm chấm điểm**, chấm điểm làm ở đây. Nhưng lượt gốc dùng bốn
subagent trên sáu bề mặt kèm 45 ảnh, còn lượt này đo lại **đúng những mục lượt gốc đã
trích dẫn**. Vì vậy phần đáng tin là BẢNG SỐ bên dưới; phần điểm là một model chấm lại
thứ một model khác từng chấm — không phải hai phép đo so với nhau.

### Số đo, gốc → nay

| Mục | Audit 2026-08-08 | Hôm nay | Nguồn |
|---|---:|---:|---|
| Màu literal ngoài `:root` (giá trị rời rạc) | 85 | **0** | `style.css` |
| — trong đó trùng khít một token đã có | 19 | 0 | |
| `font-size` không dùng token | 73 | **4** (đều là `em` của biểu tượng) | |
| — khai dưới sàn 12px | 3 + 7 chỗ `11px` | **0** | |
| Lớp CSS chết¹ | 42 | **0** | tombstone `test_static_assets.py` |
| Selector khai trùng, giá trị xung khắc | 13 | **2** (đều là ghi đè có chủ ý, đã khai) | |
| Dấu `}` thừa mức cao nhất | 1 (`:1328`) | **0** | |
| Bộ từ vựng nhãn trên màn gán cột² | 10 | **6** | `file_page.py`, `cell-grid.js` |
| Bộ chọn trang tính trên trang file | 2 (khác nghĩa) | **1** | `document_file.html:79` |
| Tính năng làm nổi cột | chết hoàn toàn | **sống**, đo trong trình duyệt | `cell-grid.js:631` |
| `:disabled` có rule | 0 | **2** | |
| `.empty-state` có rule | 0 | **1** | |
| Tương phản vòng focus | 1,34 | **12,36** | |
| `thead` `scope="col"` ở bảng gán cột | 0/9 | **4/4** | `document_file.html:280` |
| Lưới xem trước có tên khả truy cập | không | **có** | |
| Skip-link | không | **có, ở mọi trang** | `base.html` |
| Điều khiển của thanh trợ lý đóng nhận focus | 6 | **0** (`inert`) | đo trong trình duyệt |
| JS tải về ở trang file | 125.882 B (83% là thanh trợ lý) | **34.611 B, 0% là thanh trợ lý** | |
| Giãn cách inline lệch thang³ | 15 | **15** (ngoài phạm vi, cố ý) | |
| `prefers-color-scheme` | 0 rule | **0 rule** (chưa có hệ màu tối) | |
| Poll `/jobs/unread.json` | 10 giây | **10 giây** (ngoài phạm vi, cố ý) | |
| Bộ test | 1.747 | **1.967** (+1 xfail) | |

**¹ "0 lớp chết" đúng THEO PHƯƠNG PHÁP nào.** Dò theo chỗ class THẬT SỰ được gán
(`class=` sau khi bóc khối Jinja · `classList` · `{ class: … }` của `util.el` ·
`className` · tham số class truyền vào hàm dựng DOM · giá trị `cls` trong dữ liệu Python).
Một lượt dò tên trên toàn văn bản vẫn trả về khoảng 40 tên "không thấy ở đâu" — tất cả đều
là **tên ghép lúc chạy** (`badge-op-{{ … }}`, `job-status-{{ … }}`, `tier_css_for()`), tức
sống. Lượt gốc cũng loại nhóm này ra; con số 0 chỉ có nghĩa dưới cùng phương pháp đó.

**² Sáu bộ từ vựng nhãn, liệt kê ra** (lượt gốc liệt kê đủ 10, nên lượt này cũng phải):
`STATE_LABEL_VI` 3 giá trị (`file_page.py:82`) · "Cần xác nhận" (`:178`) · ba cách nói về
trang đã ghim, cả ba đều render: `sheet_note` (`:310`), `sheet_line` (`:414`),
`sheet_summary` (`:426`) · `cg-col-labelled`/`cg-col-mapped` (`cell-grid.js:209`) ·
`#cg-notes` (`:515`) · `#cg-status` (`:573`). Bốn bộ đã mất: `match_source_label` và
`layout_label` (nay chết, ghim ở `test_evidence_prose.py:218,220`), `review_label` và
`evidence_label` (gộp thành CÂU ở `evidence_sentence`, không còn là một bộ nhãn).

**³ "Màn quản trị" là cách gọi của lượt gốc, và nó không chính xác.** Đo lại: đúng 15 giá
trị lệch thang, đúng danh sách `file:line` lượt gốc đưa — nhưng 7 trong 15 nằm ở màn của
CÁN BỘ (`company_detail.html` 6, `item_detail.html` 1), không phải màn quản trị. Cả 15 vẫn
nằm ngoài phạm vi #128 (vé chỉ đụng `style.css`), chỉ là nhãn dán sai chỗ. Bốn giá trị
`.25rem`/`.5rem` ở `admin_checks_detail.html` KHÔNG tính: chúng đúng thang, chỉ viết thiếu
số 0 ở đầu.

Ba lỗi trung thực làm nguyên tắc #6 chấm 0 (lời khai vắng không tới adapter · gửi biểu
mẫu xoá lời khai đã lưu · "— chưa gán —" tự hoàn tác) đã vá ở `d75f07a` **trước** loạt
vé này, và lượt đo hôm nay xác nhận cả ba vẫn đúng, mỗi cái có test khoá.

### Điểm — của tôi, không phải của lượt audit gốc

Luật giữ nguyên: chấm **ca xấu nhất**, phân vân thì lấy điểm **thấp hơn**, không trọng số.

| # | Nguyên tắc | Gốc | Nay | Vì sao dời (hoặc không) |
|---|---|---:|---:|---|
| 1 | Đổi mới | 2 | 2 | Vẫn là làm mới một khuôn mẫu đã có. Điều kiện "ships it with restraint" khá hơn (10→6 bộ từ vựng, nhãn hiện theo ngoại lệ) nhưng không đủ để lên 3 |
| 2 | Hữu dụng | 2 | 2 | Hai lý do gốc nêu đã hết (tính năng chết, xác nhận đầu không nói gì), nhưng ca xấu nhất vẫn còn: cổng cột bắn thì mỗi file thêm một lượt |
| 3 | Thẩm mỹ | 1 | 2 | Hệ token đã kín. Chưa lên 3: 15 giãn cách inline ở màn quản trị, và bảng phát hiện vẫn mã hoá mức nghiêm trọng ba lần trên một dòng |
| 4 | Dễ hiểu | 1 | 2 | Bốn thuật ngữ nay có nghĩa tại chỗ ở CẢ hai màn. Chưa lên 3: màn ngoài phạm vi loạt vé (bảng phát hiện, chi tiết mặt hàng) vẫn có nhãn trần |
| 5 | Kín đáo | 1 | 2 | Nhãn hiện theo ngoại lệ; `evidence` thành câu, thôi là một chip. Chưa lên 3: đếm nhãn ca xấu nhất chưa đo lại trên mọi màn |
| 6 | **Trung thực** | **0** | **3** | Ba lỗi gốc vẫn vá; loạt vé cộng thêm: nút chính nêu đúng phạm vi, "kiểm tra chưa chạy" nói ra, dòng nghĩa chỉ hiện khi thứ nó tả có trên màn |
| 7 | Bền lâu | 2 | 2 | Chốt hãm và bia mộ giữ được hệ, nhưng đó là hạ tầng bảo trì, không phải bằng chứng thiết kế sống lâu |
| 8 | Kỹ chi tiết | 1 | 3 | Bốn thứ gốc nêu đều đã có: `:disabled`, `.empty-state`, vòng focus 12,36, không còn `}` thừa. Thêm `scope="col"`, tên lưới, skip-link |
| 9 | Tài nguyên | 2 | 3 | Trang file: 125.882 B → 34.611 B JS |
| 10 | Ít mà tốt | 1 | 3 | Cả ba bằng chứng gốc (42 lớp chết, 13 selector xung khắc, một tính năng chết) đã hết |
| | **Tổng** | **13/30** | **24/30** | |

**Đọc con số này thế nào.** 13 → 24 là **hai model chấm hai lần**, không phải hai phép đo.
Phần chắc chắn là bảng số ở trên: mỗi dòng có nguồn và đo lại được. Ngưỡng REDESIGN của
lượt gốc là dưới 20; nếu lấy 24 làm bằng chứng "hết REDESIGN" thì đó đúng là kiểu dùng
điểm mà ADR #29 cấm. Việc đúng là đọc từng dòng số và tự kết luận.

Ba mục **cố ý không dời**: 15 giãn cách inline ở màn quản trị · poll `/jobs/unread.json`
mỗi 10 giây · chưa có hệ màu tối. Cả ba đều nằm ngoài phạm vi loạt vé, ghi ở đây để lượt
audit sau không đọc chúng thành hồi quy.
