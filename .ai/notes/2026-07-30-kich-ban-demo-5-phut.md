# Kịch bản demo 5 phút — Audit-HQ (audit-hq-demo.tinsu.ai)

Nguồn: đề án `../audit-hq/de-an-audit-hq.md` §6 (kịch bản gốc dùng dữ liệu giả lập DN_001–005,
**đã bị thay thế trên prod** bởi dữ liệu thí điểm ẩn danh thật — xem dưới); `.ai/STATUS.md` các khối
2026-07-24 đến 2026-07-30 (trạng thái thật trên prod); `app/routes/companies.py`, `app/routes/catalog.py`,
`app/routes/docs.py`; `app/static/docs/huong-dan/index.html` (nhãn nút tiếng Việt chính thức).

**Dữ liệu thật trên prod hôm nay (khác kịch bản gốc §6.3 của đề án):** 3 pháp nhân thí điểm ẩn danh —
`PILOT_002`, `PILOT_004` (DNCX 2 sổ quyết toán EPE/GC), `PILOT_006` — tổng 14.989 phát hiện
(STATUS 2026-07-27, khối "CHẠY LẠI CHECK 004 TRÊN PROD"). Kịch bản dưới đây dùng **PILOT_004/2025** làm
pháp nhân chính vì đây là ca minh hoạ truy nguyên + 2 sổ quyết toán, đã được audit và sửa lỗi trục đơn vị,
số liệu đã verify trên chính prod (không phải số đo trên DB local).

---

## 1. Kịch bản theo phút

### 0:00–0:45 — Bảng tổng quan
- **URL:** `/companies`
- **Bấm:** không thao tác, chỉ dừng ở bảng danh sách 3 pháp nhân.
- **Nói:** "Đây là ba doanh nghiệp thí điểm, dữ liệu đã ẩn danh từ hồ sơ Báo cáo Quyết toán thật. Tổng
  cộng gần 15 nghìn phát hiện chênh lệch được hệ thống đối chiếu tự động từ Mẫu 15, 15a, 16 và BCCT."
- **Số chứng minh:** 14.989 phát hiện / 3 pháp nhân (STATUS 2026-07-27). **Không** dừng lại ở cột điểm
  rủi ro 0–1000 — xem mục 4.

### 0:45–1:45 — Hồ sơ doanh nghiệp, 2 sổ quyết toán
- **URL:** `/companies/PILOT_004?year=2025`
- **Bấm:** chọn PILOT_004 từ bảng tổng quan, dừng ở khối "Số phát hiện theo mức độ" và strip 2 sổ
  (EPE/GC).
- **Nói:** "Doanh nghiệp này là chế xuất, giữ hai sổ quyết toán — tự sở hữu và gia công. Hệ thống tách
  phát hiện theo từng sổ, không gộp nhầm hai luồng nghiệp vụ khác nhau."
- **Số chứng minh:** 65 phát hiện (52 nghiêm trọng · 7 cảnh báo · 6 thông tin) — số đã verify trực tiếp
  trên prod sau lượt chạy lại 2026-07-27 (STATUS: "74 → 65 finding: 9 dòng bị xoá, 0 dòng thêm mới… Severity:
  critical 61→52, warning 7, info 6"). **Xem mục 2** — STATUS có một khối đo khác (61·7·6) từ một lượt đo
  read-only trên DB local ngày 2026-07-29/30, chưa đối chiếu với số prod — phải verify lại số hiện trên
  màn hình ngay trước giờ demo, không đọc thuộc lòng số trong kịch bản này.

### 1:45–3:00 — Một phát hiện cụ thể, truy nguồn
- **URL:** `/companies/PILOT_004?year=2025` → bấm vào một dòng phát hiện nhóm **C1.1** (số lượng nhập/xuất
  lệch) → `/findings/{id}`
- **Bấm:** mở chi tiết phát hiện, cuộn tới khối chứng cứ (dẫn dòng BCCT/Mẫu 15 gốc).
- **Nói:** "Mỗi phát hiện đều dẫn ngược về đúng dòng dữ liệu doanh nghiệp đã nộp — không có phát hiện nào
  là hộp đen. Cán bộ đối chiếu trực tiếp con số này với file gốc."
- **Số chứng minh:** con số lệch cụ thể của dòng đang mở (đọc trực tiếp trên màn, không nêu số cố định
  trong kịch bản vì phụ thuộc finding id chọn lúc rehearsal).
- Đây là điểm hành động đầu tiên: cán bộ có thể đánh dấu trạng thái (Xác nhận / Loại trừ / Đã ghi chú —
  nhãn tại `app/routes/companies.py:95-98`) ngay tại đây.

### 3:00–3:50 — Tổng quan AI cho một bài kiểm tra
- **URL:** `/companies/PILOT_004?year=2025`, mở khối tổng quan AI của **một bài kiểm tra đã có tổng quan
  hợp lệ của chính PILOT_004** (10 tổng quan đã sinh cho 004/2025 ngày 2026-07-27, xem mục 2 — chọn cụ thể
  lúc pre-flight, KHÔNG dùng check nào của PILOT_006/2024).
- **Bấm:** không bấm "Tạo lại" — chỉ đọc tổng quan đã có sẵn.
- **Nói:** "Bảng số liệu phía trên do hệ thống tính trực tiếp, hiện ngay khi bấm. Phần nhận định do AI viết
  luôn kèm hậu kiểm số — nếu AI nêu một con số không khớp bảng, dòng đó tự động gắn cờ 'cần xem lại' thay vì
  hiển thị như đã xác nhận."
- **Số chứng minh:** số phát hiện theo mức độ + phân vị trường số trong bảng tính sẵn của đúng check đang
  mở (đọc trên màn).

### 3:50–4:40 — Xuất kiến nghị
- **URL:** `/companies/PILOT_004/export`
- **Bấm:** nút **Xuất Excel kiến nghị**.
- **Nói:** "Đây là sản phẩm cán bộ mang đi: danh sách phát hiện ưu tiên, kèm dòng dữ liệu gốc làm chứng cứ
  và trích yếu văn bản pháp lý liên quan — Thông tư 38/2015, 39/2018."
- **Số chứng minh:** số dòng trong file Excel vừa tải xuống, đọc trực tiếp khi mở file (khớp số hiện trên
  hồ sơ doanh nghiệp lúc 0:45–1:45 — nếu lệch, xem mục 3 "beat 5").

### 4:40–5:00 — Kết
- **Nói:** "Cán bộ rời màn hình này với một danh sách rà soát có ưu tiên, có chứng cứ, có trích dẫn pháp
  lý — quyết định kiểm tra hay không vẫn thuộc thẩm quyền cán bộ." Kết thúc, không mở thêm màn nào.

---

## 2. Pre-flight checklist

| Việc phải xác minh trước giờ demo | Trạng thái theo STATUS.md | Đã xác minh trong lượt soạn kịch bản này? |
|---|---|---|
| Pháp nhân + kỳ dùng demo | `PILOT_004`, năm 2025, 65 phát hiện (52·7·6) | **CHƯA** — chỉ đọc từ STATUS 2026-07-27, không truy vấn DB live (phiên này read-only, không kết nối DB) |
| `check_runs` đã chạy đủ cho PILOT_004/2025 | 17 dòng cho company id 9, `data_version=0` (STATUS 2026-07-27) | Chưa xác minh live |
| Tổng quan AI đã có cho PILOT_004/2025 | 10 tổng quan sinh 2026-07-27, đủ `aggregate_json`+`sections_json` | Chưa xác minh live — **phải chọn cụ thể 1 mã check của 004 và kiểm tra 2 cột JSON đó không rỗng ngay trước demo** |
| Tổng quan không bị gắn cờ `needs_review` | 2 dòng bị gắn cờ đã biết đều thuộc **PILOT_006/2024** (C1.7, C3.2), không phải 004 | Suy luận từ STATUS, **chưa loại trừ khả năng có dòng mới bị gắn cờ sau đó** |
| `/healthz` trả `build_sha` đúng bản đã deploy | Bản deploy xác nhận gần nhất là `d7844b6` (2026-07-27); đợt "17 luồng song song" ngày 2026-07-30 **tường minh không merge, không deploy** nên prod lẽ ra vẫn `d7844b6` | **KHÔNG XÁC MINH ĐƯỢC** trong phiên này (read-only, không gọi mạng tới prod) — bắt buộc `curl https://audit-hq-demo.tinsu.ai/healthz` trước giờ diễn |
| Không có finding nào trên PILOT_004/2025 vừa bị đánh dấu trạng thái rồi có người chạy lại check | Lỗi chưa có vé (STATUS 2026-07-30): chạy lại check xoá-và-insert-lại `Finding`, không truyền `status=` → mọi `confirmed/rejected/noted` bị đưa về `"new"` trong im lặng | Bắt buộc: **không ai được bấm "Chạy kiểm tra" hoặc "Chạy lại" trên PILOT_004/2025 giữa lúc rehearsal và lúc demo** |
| Tài khoản đăng nhập cho demo | Nên dùng tài khoản vai trò **cán bộ** (không phải quản trị viên) đã được phân công đúng 3 pháp nhân thí điểm, để đúng góc nhìn khán giả sẽ thấy khi triển khai thật (mục A4 cẩm nang) | Chưa xác minh tài khoản này tồn tại trên prod — mật khẩu admin local không ai biết (ghi nhớ dự án), tài khoản demo phải chuẩn bị và test riêng |
| Dung lượng ổ đĩa server | 97% đầy, còn 9,0G tính đến 2026-07-27 (STATUS), có thể đã tệ hơn sau các backup của đợt 2026-07-30 | Chưa xác minh hôm nay |
| Đường truyền mạng nơi demo | — | Không thuộc phạm vi STATUS, tự kiểm riêng |

---

## 3. Failure playbook

**Beat 0:00–0:45 (bảng tổng quan):** nếu khán giả hỏi ngay về cột điểm rủi ro trước khi kịp pivot — trả
lời theo mục 5 câu 1, không mở khối "Cách tính điểm rủi ro" để tránh phải giải thích công thức giữa demo.

**Beat 0:45–1:45 (hồ sơ 2 sổ):**
- Nếu bảng số liệu/tổng quan hiện nhãn khoá thô (`DIFF_PCT`, `M15_REPURPOSE`…) thay vì tiếng Việt: bản vá
  nằm ở nhánh `fix/percentile-keys-guardrail`, **chưa merge tính đến hôm nay** (STATUS 2026-07-30) — nên
  bug này **còn sống trên prod**. Nói: "đây là nhãn kỹ thuật nội bộ, số bên dưới vẫn đúng" rồi lướt sang
  đúng dòng phát hiện thay vì dừng ở bảng đó.
- Nếu số phát hiện hiện trên màn khác con số trong kịch bản (65 / 52·7·6): đọc số thật trên màn hình, đừng
  sửa lại lời thoại để khớp con số cũ — nói thẳng "con số này cập nhật theo lần chạy kiểm tra gần nhất".

**Beat 1:45–3:00 (chi tiết phát hiện):**
- Nếu trạng thái phát hiện đã đánh dấu trước đó (để minh hoạ) bị hiện lại là "Mới" thay vì "Xác nhận": đây
  là hệ quả của lỗi reset trạng thái khi có ai chạy lại check — **không sửa lại trên sân khấu**, tiếp tục
  vì trạng thái không ảnh hưởng đến chứng cứ đang trình bày; ghi chú xử lý sau.
- Nếu trang `/findings/{id}` lỗi 500 hoặc trắng: chuẩn bị sẵn một `finding_id` dự phòng đã rehearsal kỹ
  trước, chuyển hướng sang dòng đó ngay trong 10 giây, không debug trên sân khấu.

**Beat 3:00–3:50 (tổng quan AI):**
- Nội dung nhận định trống dù trạng thái ghi "Đã xong": xảy ra thật ngày 2026-07-27 (một lượt gọi chạy 817
  giây, `request_timeout_s` không được áp, `content` rỗng nhưng `status=done`). Mitigation: **không sinh
  tổng quan trực tiếp trên sân khấu** — dùng tổng quan đã sinh sẵn và verify trước; nếu lỡ bấm "Tạo lại" và
  gặp rỗng, chuyển sang một check khác đã verify sẵn, không chờ generate lại giữa demo.
- Dòng tổng quan cũ định dạng khác (thiếu `aggregate_json`/`sections_json`) mà cơ chế phát hiện "đã cũ"
  không bắt được vì check chưa chạy lại từ lúc đó: bảng số liệu sẽ trống dù nhận định vẫn hiện. Mitigation:
  pre-flight đã yêu cầu kiểm tra 2 cột JSON đó trước — nếu rỗng, đổi sang check khác của cùng công ty.
- Số trong nhận định AI không khớp bảng (đã từng xảy ra ở PILOT_006/2024 C1.7/C3.2 — mô hình tự viết ra số
  77,7 và 80,1 không có trong dữ liệu): nếu badge "cần xem lại" hiện, đọc thẳng "dòng này hệ thống tự phát
  hiện số không khớp và đã gắn cờ, chưa đưa cho khách" — biến lỗi thành minh chứng cho cơ chế hậu kiểm, đừng
  chọn check này làm nội dung chính từ đầu.

**Beat 3:50–4:40 (xuất Excel):**
- Số dòng trong file khác số đã nói ở beat trước, do có người chạy lại check ở nơi khác giữa hai beat (đã
  từng đổi 14.998→14.989 do một lượt recheck độc lập, STATUS 2026-07-27): mở file, đọc số thật, không đối
  chiếu ngược với con số đã nói bằng miệng trước đó trên sân khấu.

**Toàn bộ 5 phút — dải cảnh báo vàng rỗng ở đầu mọi trang:** lỗi CSS specificity đã có thật
(`.ai-scope-bar`/`.ai-scope-mismatch` cùng specificity với `[hidden]`, khai sau nên thắng) nhưng **đã được
vá trong bản `d7844b6`** đang chạy trên prod (STATUS 2026-07-27, mục "BỐN LỖI THẬT… (4)"). Rủi ro thấp
nếu build đúng là `d7844b6` — xác minh qua `/healthz` trong pre-flight; nếu tái hiện, refresh trang.

---

## 4. Không được chiếu, không được nói — và lý do

1. **Điểm rủi ro 0–1000 như một con số kết luận mức độ nghiêm trọng.** Mẫu số của công thức
   (`scoring.py:183-186`, `max_raw`=190) giả định cả 17 bài kiểm tra cùng đạt trần điểm cùng lúc — điều
   chưa từng xảy ra trong dữ liệu thật. Hệ quả đo được: **PILOT_006/2025 có 9.963 phát hiện nghiêm trọng
   vẫn nhận điểm 54**, rơi đúng dải "Có chênh lệch nhỏ" (51–100) theo bảng ngưỡng công khai trong cẩm nang
   (`app/static/docs/huong-dan/index.html`, mục D1). Nếu bảng tổng quan hiện cột điểm này (nó hiện theo
   thiết kế), không dùng nó để so sánh mức độ nghiêm trọng giữa các pháp nhân bằng lời — dùng số phát hiện
   theo mức độ.
2. **Bất kỳ cách đếm nào kiểu "N bài kiểm tra cùng gắn cờ một mã hàng".** Các bài kiểm tra không độc lập:
   `C1.7 ⊂ C1.6` và `C1.3 ⊂ C1.1` (kiểm chứng trên dữ liệu PILOT_006/2025, PILOT_006/2024, PILOT_004/2025 —
   STATUS 2026-07-29). Riêng C1.6 đã gắn cờ 55% dân số mã, C1.7 cộng thêm 23% — một phép đếm "3 bài cùng
   gắn cờ" là đếm trùng cùng một sự kiện dữ liệu ba lần.
3. **Trang danh mục công khai `/danh-muc-kiem-tra` với cột "Rủi ro nghiệp vụ".** Cột này
   (`app/templates/catalog_full.html:72,85`, đọc trường `risk`) quy kết hành vi ("thổi phồng định mức để
   điều tiết…") thay vì mô tả trung tính. Cùng bảng dữ liệu có sẵn trường `problem` trung tính
   (`catalog_full.html:83`) — nếu mở trang này trước khán giả, không đưa cột `risk` vào tầm nhìn hoặc đổi
   hướng sang mô tả từ `problem`.
4. **Không chạy lại kiểm tra (nút "Chạy kiểm tra"/"Chạy lại") trên pháp nhân đang demo trong lúc trình
   bày.** Lỗi chưa có vé: `run_checks.py:78-104` xoá và insert lại toàn bộ `Finding`, không check nào
   truyền `status=`, nên mọi trạng thái cán bộ đã đánh dấu (`confirmed`/`rejected`/`noted`) và ghi chú kèm
   theo bị đưa về `"new"` trong im lặng.
5. **Không tự nhận là "16 kiểm tra MVP" nếu bị hỏi đếm số bài kiểm tra.** `CLAUDE.md` ghi 16, nhưng registry
   thực tế có **17** (`app/checks/registry.py:SPECS`, STATUS 2026-07-30) — nếu bị hỏi trực tiếp, trả lời 17.

---

## 5. Câu hỏi khán giả sẽ hỏi

**"Số này lấy ở đâu ra?"**
Mọi con số trên màn tính trực tiếp từ dòng dữ liệu Mẫu 15/15a/16 và BCCT do chính doanh nghiệp nộp — bấm
vào phát hiện để xem đúng dòng nguồn, không có bước suy diễn trung gian. Ngoại lệ cần nói rõ nếu bị hỏi:
điểm rủi ro 0–1000 có vấn đề cấu trúc ở mẫu số (mục 4.1) — nếu được hỏi riêng về điểm này, nói thẳng đang
được hiệu chỉnh lại, chưa nên dùng để so sánh mức độ.

**"Phần mềm có kết luận doanh nghiệp gian lận không?"**
Không. Hệ thống chỉ đối chiếu số liệu giữa các biểu doanh nghiệp tự nộp và báo chênh lệch — chênh lệch có
thể do gian lận, do lỗi ghi sổ, hoặc do đặc thù nghiệp vụ hợp pháp (ví dụ mô hình 2 sổ quyết toán của
DNCX). Phần mềm không phân loại tuân thủ — thẩm quyền đó thuộc Tổng cục Hải quan theo Thông tư
81/2019/TT-BTC (đã ghi rõ trong cẩm nang, mục A3). Mọi quyết định cuối cùng thuộc thẩm quyền cán bộ.

**"Dữ liệu của chúng tôi có bị lộ không?"**
Dữ liệu trên bản demo đã được ẩn danh theo quy trình của đề án (§6.2): mã số thuế, tên doanh nghiệp, tên
nhà cung cấp thay bằng mã. Đã quét toàn bộ DB và trang công khai `/showcase` — 0 kết quả trùng MST hoặc
tên thật (STATUS 2026-07-25, 2026-07-27). Dữ liệu sản xuất thật của doanh nghiệp không được commit vào mã
nguồn và không ghi log ra console (CLAUDE.md, mục Rules).
