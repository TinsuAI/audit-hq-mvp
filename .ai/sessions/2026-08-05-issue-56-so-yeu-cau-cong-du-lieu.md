# 2026-08-05 — Issue #56: sổ yêu cầu + cổng dữ liệu (không đụng code)

Nhánh `feat/data-completeness-gate`, tách từ `main` @ `0b9e3b2`. **Không sửa dòng code nào** —
phiên này là phân tích, gộp yêu cầu và grill thiết kế. Sản phẩm nằm ở
`.ai/features/2026-08-05-issue-56-data-completeness/`.

## What Was Done

**Gộp ba tài liệu nguồn thành một sổ yêu cầu.** Issue #56 chỉ có 2 link artifact + 1 đoạn văn;
nội dung thật nằm trong hai bản ghi âm anh Dũng (19'24" + 55'42"), notes chị Duyên 05/08 (12 mục),
và đề xuất chị Duyên 16/06 (10 mục, đọc từ `.docx` trên `/mnt/p`). Gộp lại còn **29 yêu cầu** —
trùng lặp nhiều: tờ khai huỷ/sửa nêu 3 lần, tiêu hao lý thuyết 3 lần, ĐM kế thừa 4 lần.

**Xếp sổ đó theo bản đồ mức** do owner đề xuất (mức thấp đứng vững thì mức trên mới có nghĩa):
mức 0 tiếp nhận file · mức 1 mỗi biểu tự đứng vững · mức 2 đủ nguyên liệu để tính · mức 3 đối chiếu
chéo nguồn · mức 4 suy diễn từ định mức · nhánh liên kỳ.

**Chạy `/grill-with-docs`, chốt 3 quyết định** (chi tiết + bằng chứng ở `grill-state.md`), thêm 4
mục vào `.ai/GLOSSARY.md`: định mức hiệu lực · ĐM mới · năm đầu nộp BCQT · chưa đánh giá được.

**Đo trên `audit_hq.sqlite` local** — các số nền quan trọng nhất, đều lưu trong `grill-state.md`.

## Decisions Made

**Q1 — kỳ sớm nhất mỗi DN mặc định `not_evaluable`** cho check độ phủ định mức, trừ khi cán bộ xác
nhận đó là năm đầu nộp BCQT. Không phân biệt được "chưa từng khai" với "đã khai trước cửa sổ dữ
liệu". Cần trường mới trên `companies`.

**Q2 — định mức chuyển tiếp ĐƯỢC đưa vào phép nhân C4.3**, dùng bản khai gần nhất ≤ kỳ đang xét.
Bắt buộc ship kèm việc (b) của `fix/c43-multiplier-p07`, nếu không sinh 151 phát hiện Nghiêm trọng
dán nhầm nhãn của C4.1.

**Q3 — cổng nhị phân, không phụ thuộc sản lượng** (owner chốt, bác đề xuất ngưỡng của tôi). Có mã
thành phẩm nào sản xuất trong kỳ mà chưa từng khai định mức ở bất kỳ kỳ nào → nhóm 4
`not_evaluable`. Hệ quả đo được: **còn 1.772/3.296 = 54%** phát hiện C4.3, chỉ DN 8/2025 qua cả hai
cổng.

**`brief.md` giải nghệ, không vá.** Nội dung tách sang `yeu-cau.md` (làm gì) và `grill-state.md`
(chốt gì); `brief.md` giờ chỉ còn ghi chú kỹ thuật thuần — điểm neo code, sáu chỗ dễ vấp, ràng buộc
CLAUDE.md. Vá nó là tái tạo đúng cái trùng lặp đã gây quá tải.

## What Didn't Work

- **Ngưỡng 5% + thước tỷ trọng sản lượng.** Tôi dựng cả một lập luận có số liệu (DN 9 thiếu 23% số
  mã nhưng 89,4% sản lượng) rồi owner bác thẳng: cổng nhị phân. Đề xuất vẫn đúng về mặt mô tả dữ
  liệu, nhưng sai về ý muốn — anh Dũng đòi tuyệt đối.
- **"Fallback định mức chỉ dùng để báo độ phủ, không vào phép nhân"** — quyết định sai trong brief
  đầu tiên, tôi tự lật sau khi có notes chị Duyên. Nếu định mức kế thừa theo luật thì C4.3 **bắt
  buộc** phải dùng bản kế thừa, không thì hụt đúng cái anh Dũng phản đối.
- **So chuỗi đơn vị thô để tìm lệch đvt giữa M16 và M15.** Ra "100% lệch ở DN10" — SAI. `upper()`
  của SQLite không xử lý tiếng Việt, và `PCE` với `Cái/Chiếc` là cùng đơn vị khác nhãn. Quy về họ
  đơn vị thì toàn bộ dữ liệu chỉ còn **8 mã lệch thật**. Bài học: mọi phép so đơn vị phải đi qua
  `app/checks/uom.py`.
- **Điều kiện "thiếu file" cho `not_evaluable`** — bắn 0 lần, cả 8 (DN, kỳ) đều đủ 4 nguồn. Takagi
  cũng có file M16, chỉ là không phủ hết mã. Điều kiện phải là độ phủ.
- **Nói "ba nguồn độc lập cùng xác nhận"** — sai, chỉ hai người: bản 16/06 cũng của chị Duyên.
- **Cách chạy grill.** Mỗi lượt tôi đo thêm rồi trình bảng số mới; đến lượt thứ ~10 owner báo quá
  tải và phải dừng phiên. Grill là để thu hẹp về một quyết định, không phải mở rộng bối cảnh.

## Open Items

**H1 — ngữ nghĩa "qua mức trước mới chạy mức sau"** cho các mức khác ngoài độ phủ định mức: nhiễm
theo MÃ (khuyến nghị) hay chặn cả mức. Theo cách chặn cả mức thì mức 3 đang có 13.368 phát hiện →
mức 4 không bao giờ chạy.

**H2 — tiếp nhận file** (yêu cầu 0.1): hiện *nhận rồi gắn cờ* (`needs_review`); đề xuất 16/06 viết
*"sai mẫu → từ chối tiếp nhận"*. Chưa bàn.

**Mã catalog cho check độ phủ M15a→M16** — chưa có trong catalog 49 (C4.1 là M16→M15, C4.2 là
M16→M15a). Theo CLAUDE.md phải thêm vào `../audit-hq/` trước. Owner chốt.

**Ba yêu cầu chặn bởi dữ liệu nguồn**, không phải việc code: tờ khai huỷ/sửa (BCCT không mang trạng
thái) · XNK tại chỗ đối ứng (không có dữ liệu DN đối ứng, vượt ranh giới quyền ADR #14) · khu vực
giám sát (không có cột trạng thái thông quan).

**Chưa commit gì.** Working tree còn `app/adapters/bcct.py` (+71 dòng, dò cột theo nhãn tiêu đề) —
việc khác, session này không đụng, xem STATUS 2026-08-02.

**Số đáng kiểm:** C5.1 (truy nguồn NVL) chạy 7 lần ra **0 phát hiện** trên mọi pilot. Với một check
truy nguồn thì 0 tuyệt đối là số nên kiểm lại — có thể nó không thật sự chạy được. Đây đúng là loại
số 0 mà `not_evaluable` sinh ra để phân biệt.

## Next

`/to-tickets` trên `yeu-cau.md` ở **session mới** — bản đồ mức chính là đồ thị blocking edges
(mức 2 chặn mức 4), và đó là skill duy nhất trong bộ Matt diễn đạt được quan hệ chặn. Không dùng
`to-spec` (sổ yêu cầu đã là bản tổng hợp) hay `wayfinder` (không còn sương mù, đã biết rõ 29 việc).
