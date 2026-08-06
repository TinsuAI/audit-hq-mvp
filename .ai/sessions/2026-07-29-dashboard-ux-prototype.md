# 2026-07-29 — Màn tổng quan: prototype UX + các phát hiện đã kiểm chứng

> **Không đụng code sản phẩm.** Toàn bộ phiên là đọc dữ liệu read-only + dựng prototype
> throwaway. `git status` không đổi ngoài `uv.lock` (đã untracked từ trước).
>
> **Kết luận điều hướng: dừng lặp prototype, sang `/grill-with-docs` ở session mới.**

## Bối cảnh

Chị Duyên (chuyên gia nghiệp vụ) phản hồi 5 ý về màn hiện tại: quá tải thông tin · chỉ số mâu
thuẫn (≈10.000 vấn đề / 904 cảnh báo / 52 điểm) · cảnh báo phải hành động được ngay · phần tổng
quan phải nổi trước chi tiết · kiểm tra phải bám thực tế Hải quan.

Đã dựng 4 vòng prototype. Artifact (bản mới nhất, có nút đổi nền sáng/tối):
<https://claude.ai/code/artifact/d21463cf-b0c3-4a76-b66d-8f7c1a4beb38>

## Phát hiện đã KIỂM CHỨNG (giá trị chính của phiên)

Tất cả đo trên `audit_hq.sqlite` local, read-only, chủ yếu `PILOT_006` kỳ 2025.

1. **Màn chị Duyên xem là `PILOT_006`/2025.** Ba số khớp chính xác: 9.963 critical
   ("gần 10.000 vấn đề") · **904** warning · điểm 54 local / 52 prod.

2. **Điểm rủi ro 0–1000 hỏng về cấu trúc.** `compute_company_year_score`
   (`app/checks/scoring.py:183-186`) chia cho `max_raw = 17×10 + 20 = 190` — mức chỉ đạt nếu cả
   17 kiểm tra cùng kịch khung, chưa từng xảy ra. Điểm thực đo cả 3 pháp nhân: **7 · 30 · 54 ·
   129**. Hệ quả: DN có 9.963 phát hiện nghiêm trọng vẫn nhận nhãn "Có chênh lệch nhỏ"
   (ngưỡng hạng 50/100/300/600/1000 đặt cho dải công thức không sinh ra được).
   → memory `risk-score-ceiling-unreachable`. **Cần ADR trước khi đưa bất kỳ điểm nào lên UI.**

3. **Mọi phát hiện có `subject_key` duy nhất** — `subjects == n` ở MỌI kiểm tra. Không có
   "top 5 mã theo số phát hiện"; xếp hạng theo tần suất trong một kiểm tra là bất khả.

4. **3 kiểm tra chiếm 91%** số phát hiện: C1.6 5.785 · C1.7 2.436 · C4.3 1.772 / tổng 10.996.

5. **Độ phủ (mẫu số từ `RULE_SCOPE`):** 6.286/10.572 mã NVL bị gắn cờ (59,5%; 6.146 có mức
   nghiêm trọng) · 1.786/8.165 dòng M16 · 21/504 mã thành phẩm.

6. **Các kiểm tra KHÔNG độc lập.** `C1.7 ⊂ C1.6` (cả 2.436 subject của C1.7 nằm trong C1.6) và
   `C1.3 ⊂ C1.1` (cả 43 nằm trong C1.1). Đúng trên 006/2025, 006/2024, 004/2025.
   → Đếm "N kiểm tra cùng gắn cờ một mã" là **đếm trùng**. Con số 284 mã "bị ≥3 kiểm tra" từng
   đưa ra là sai đơn vị.

7. **Quan hệ bao hàm KHÔNG mang tính cấu trúc — phải tính theo từng (DN, kỳ).**
   `check_c1_6` loại mã có tờ khai A42 (`c1_quantity.py:431-442`); `check_c1_7` KHÔNG loại.
   006/2025 có **697 dòng tờ khai A42**, nên C1.6 hoàn toàn có thể bỏ sót mã mà C1.7 bắt.
   Việc bao hàm xảy ra là **tính chất dữ liệu**: mọi mã có tỷ lệ chuyển MĐSD cao đều không có
   A42 che. Bản thân điều đó là tín hiệu nghiệp vụ, không phải nhiễu mô hình.
   → Gom nhóm phải **tính động**, KHÔNG hardcode.

8. **Gom theo nhóm đề án (nhóm 1 số lượng · nhóm 3 phân loại · nhóm 4 định mức):**
   5.866 đối tượng bị 1 nhóm · 1.149 bị 2 nhóm · **90 bị cả 3 nhóm**. 90 là con số mở được,
   khác 284 (đếm trùng) và 5.785 (không phải hàng đợi).

9. **So kỳ 2024 đang lệch mẫu số.** Tổng 2024 = 3.880 **bao gồm 28 `COMBO_HS_GAMING`**;
   2025 có 0 combo. So rule-với-rule đúng là **3.852 → 10.996**.

10. **`catalog_full.py` có sẵn hai trường:** `problem` (điều kiện dữ liệu, trung tính) và
    `risk` (quy kết hành vi: "doanh nghiệp lợi dụng kẽ hở miễn thuế", "mượn mã NVL để hợp thức
    hoá hàng mua nội địa không hoá đơn"). Màn DN hiện **không render trường nào** — nhưng khi
    đưa mô tả lên UI cho cán bộ thì phải dùng `problem`, không dùng `risk`.

## Nghi vấn lớn nhất — không phải vấn đề thiết kế

**C1.6 gắn cờ 5.785/10.572 = 55% dân số mã. C1.7 thêm 23%.** Một kiểm tra kích hoạt trên quá
nửa dân số không sinh ra *ngoại lệ*, nó mô tả một *tình trạng hệ thống*. Không bố cục nào làm
cho việc đó "thân thiện" được, vì bên dưới không tồn tại danh sách ngắn nào cả.

Đây chính là ý 5 của chị Duyên nhìn từ phía ngược lại. Là câu hỏi **hiệu chỉnh ngưỡng kiểm
tra**, và theo `CLAUDE.md:38` phải sửa trong `../audit-hq/de-an-audit-hq.md` TRƯỚC.

## Cái gì KHÔNG hiệu quả (và tại sao)

Bốn vòng prototype, mỗi vòng sửa đúng thứ được nêu tên, và vẫn trượt:
v1 xếp hạng theo tỷ lệ → "quá tải" · v2 thêm biểu đồ → "xấu" (chữ/màu) · v3 sửa chữ + bảng màu
→ "vẫn bội thực" · v4 cắt 56% chiều cao, bản đồ khối, bỏ câu quy kết → "không ổn lắm".

**Nguyên nhân quy trình:** nhảy thẳng vào `/prototype` mà bỏ bước 1 `/grill-with-docs`.
Prototype là đường vòng để trả lời MỘT câu hỏi cần code mới trả lời được — không thay thế được
việc chốt màn này để làm gì. Hệ quả: tôi đoán mục tiêu, chủ dự án phản ứng với bản đoán. Đó là
cách đắt nhất để tìm ra mục tiêu.

Prototype vẫn hoàn thành đúng phần việc của nó: mọi mục ở phần "đã kiểm chứng" ở trên là sản
phẩm của nó. **Giữ câu trả lời, bỏ code** — đúng tinh thần `/prototype`.

## Hai lỗi kỹ thuật bắt được khi dựng (thuộc về prototype, đã sửa)

- Bảng màu 3 mức ban đầu (`#c2410c` nghiêm trọng / `#d97706` cảnh báo) có ΔE thị lực thường
  **12,7 — dưới sàn 15**, mà hai màu này nằm sát nhau trong mọi thanh chồng. Đã đổi sang
  `#b91c1c/#d97706/#60a5fa` (nền sáng) và `#d94f6a/#c2860f/#5896d6` (nền tối), qua đủ 6 kiểm
  tra của `scripts/validate_palette.js`. **Đỏ↔xanh lá không dùng được** cho tăng/giảm:
  ΔE deutan 4,2.
- Ô bản đồ khối để `content-box` → padding cộng thêm vào chiều cao %, C1.6 chiếm 57,1% diện
  tích thay vì 52,6%. Diện tích sai tỷ lệ = phá đúng thứ duy nhất treemap phải bảo đảm.

## Quyết định còn MỞ (việc của `/grill-with-docs`)

1. **Màn này để làm gì, cho ai, và người dùng rời màn với quyết định gì?** Chưa ai chốt. Đây là
   gốc của cả 4 vòng trượt.
2. **C1.6/C1.7 ở mức 55%/23% là phát hiện hay lỗi hiệu chỉnh?** Nếu là lỗi hiệu chỉnh → sửa đề
   án trước, và màn tổng quan phải dựng lại trên phân bố khác hẳn.
3. **Đơn vị của "cần mở trước":** nhóm đề án 1/3/4 (đã dùng, 90 mã) hay chia mịn hơn thành 5 họ
   (chuyển MĐSD · nhập lệch · xuất TP · phân loại · định mức)? Chia mịn = **thêm thuật ngữ mới**
   → phải vào đề án trước.
4. **Hiệu chỉnh lại thang điểm 0–1000** — mẫu số theo số kiểm tra ĐÃ CHẠY? phân vị theo dải
   quan sát? bỏ thang số đổi sang nhãn? Cần ADR.
5. **Trạng thái đã-soát/chưa-soát cho finding** — hiện không có. "Mở cái gì trước" ngụ ý có lần
   thứ hai, mà mỗi lần vào lại quay về 10.996 dòng.

## Suggested skills cho session sau

1. **`/grill-with-docs`** — bắt đầu ở đây, tham chiếu file này. Mục tiêu: chốt (1) và (2) ở trên.
   Cần window sạch vì nó chạy liền mạch sang `/to-spec` → `/to-tickets`.
2. Nếu grill kết luận cần đổi ngưỡng/danh mục kiểm tra → sửa `../audit-hq/de-an-audit-hq.md`
   trước, rồi mới quay lại repo này (`CLAUDE.md:38`).
3. `/domain-modeling` nếu vướng ở thuật ngữ nhóm/họ kiểm tra (mục 3).
4. `/implement` sau khi có spec. Việc hiệu chỉnh điểm (mục 4) đi riêng, có ADR riêng.

## Tham chiếu

- Artifact bản v4: <https://claude.ai/code/artifact/d21463cf-b0c3-4a76-b66d-8f7c1a4beb38>
- Code prototype: throwaway trong scratchpad phiên này, **không commit, sẽ mất** — chủ ý.
- Màn đang chạy: `app/templates/company_detail.html` (631 dòng) + `app/routes/companies.py:1862`.
- Chấm điểm: `app/checks/scoring.py` · mẫu số `app/checks/denominators.py:25-40`.
- Mô tả kiểm tra: `app/catalog_full.py` (`problem` / `risk`).
- Memory liên quan: `risk-score-ceiling-unreachable`, `so-lieu-phai-co-mau-so-va-nguon-doc-lap`.
