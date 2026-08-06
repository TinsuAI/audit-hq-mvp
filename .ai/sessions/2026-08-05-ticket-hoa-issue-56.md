# 2026-08-05 — Ticket hoá issue #56, và một lỗi mức 0 tìm ra dọc đường

Nối tiếp `.ai/sessions/2026-08-05-issue-56-so-yeu-cau-cong-du-lieu.md` (phiên phân tích, sinh ra
sổ 39 dòng + 3 quyết định). Phiên này biến sổ thành ticket và phát hiện một lỗi đang sống ở mức 0.

## Đã làm

**PR #55 merge.** `main` từ `0b9e3b2` sang `d528b2f`. Trước đó `mergeable: MERGEABLE`,
`mergeStateStatus: CLEAN`, không có CI check nào gắn vào PR, không có review.

**Cắt phạm vi #56.** Sổ có 39 dòng đánh số, không dòng nào đánh dấu thuộc issue nào. Chốt: #56 ship
**cổng độ phủ định mức, không hơn** — dòng 2.1, 2.2, cộng bốn việc hạ tầng chưa có dòng nào trong sổ
(trường `first_bcqt_year`, `not_evaluable` thành trạng thái thật, cổng nhị phân C4.3, việc (b) của
P-07). Sau khi tìm ra lỗi BCCT thì thêm dòng 0.2 → 3 dòng trong phạm vi, 36 ngoài.

**Bảy sub-issue của #56** (#57–#63), nhãn `ready-for-agent`, cạnh chặn khai bằng **issue dependency
thật của GitHub** (`POST /issues/{n}/dependencies/blocked_by`) chứ không chỉ ghi trong mô tả — trên
tracker thấy được ticket nào đang bị chặn. Mỗi ticket mang mốc nghiệm thu bằng số đo từ
`grill-state.md`, không phải mô tả suông.

**T7 #63 — lỗi mức 0.** Xem mục riêng bên dưới.

**Sửa ba con số sai trong sổ** (`yeu-cau.md`):
- "Mức 2: 6/8 dòng chưa có" → **7/8** (chỉ 2.5 là ✅).
- "5 cái đang bắn 0 phát hiện" → **6 check** bắn 0, chạm **4 dòng**. Câu cũ trộn hai cách đếm.
- "29 yêu cầu" không có mẫu số. Viết phép tính vào sổ: 39 dòng − 5 dòng nguồn `—` (năng lực có sẵn,
  không ai yêu cầu) = 34 dòng do ba tài liệu nêu; − 5 dòng X.* ngoài phạm vi kiểm tra = **29**.

**Thêm dòng Đ.1** — điều tra 6 check bắn 0 phát hiện (C2.1–C2.4, C5.1, C6.1, chạy 7 lần ra 0). Nó
phủ bốn dòng đang đánh ✅ (1.1, 1.2, 3.3, L.1); chưa xác minh thì bốn dòng đó chưa chắc ✅. Không có
dòng nào trong sổ trước đó, `/to-tickets` chạy trên sổ cũ sẽ làm việc này rơi mất.

## T7 #63 — adapter BCCT đọc sai cột, không báo lỗi

Trong cây làm việc có sẵn +72 dòng chưa commit ở `app/adapters/bcct.py` (viết 01/08, không test).
Adapter ánh xạ cột theo **vị trí cố định** (`_COL`, `bcct.py:60-77`); file bố cục khác thì mọi
trường rơi vào cột khác, parse vẫn "thành công", **không ngoại lệ nào phát ra**.

Đo trên **cả 38 file BCCT trong `data/`**: 35 khớp `_COL`, **3 lệch**:

| File | Cột | Trường lệch |
|---|---|---|
| HIEP_QUANG 2021 NK | 50 | 16 |
| HIEP_QUANG 2021 XK | 50 | 16 |
| HONG_AN 2025 XK `__dup1` | 55 | 11 |

HIEP_QUANG 2021 NK, dòng dữ liệu đầu, đọc theo vị trí: `quantity` = 100.880 (thực ra cột *Trị giá
NT*, đúng phải là 104.000) · `unit` = `<trị giá>` (cột *Tổng trị giá*, đúng phải là `KILO-GRAMMES`)
· `company_name` = `2020-08-25` (cột *Ngày hợp đồng*).

**Vì sao là mức 0:** 10 check đọc `declaration_lines` — C1.1, C1.2, C1.3, C1.4, C1.6, C1.7, C3.1,
C3.2, C3.3, C5.1 — cộng `denominators.py` (mẫu số điểm rủi ro) và `company_type.py` (dò loại hình).
Mức 3 hiện có 13.368 phát hiện, toàn bộ dựng trên bảng đó.

**DB hiện sạch.** `declaration_lines`: DN 7 = 11.115 dòng · DN 8 = 374.607 · DN 9 = 547 · DN 10 =
247.070; `quantity IS NULL` = 0/2/0/0. Bốn DN đã nạp (3 pilot + ZONSEN) đều đúng bố cục 54 cột.
HIEP_QUANG và HONG_AN **chưa nạp**. `saved_column_maps` rỗng — chưa bản đồ cột nào bị ghim.

**Thứ tự bắt buộc: sửa adapter TRƯỚC, nạp hai DN đó SAU.** Dòng đã nạp không tự đổi khi luật dò cột
đổi — phải nạp lại rồi chạy lại check.

Code tách ra nhánh riêng `fix/bcct-label-columns` @ `06a9db5` (chưa test, chưa push), để không dính
vào commit của #56.

## Quyết định

**H2 gỡ khỏi mục treo.** Câu hỏi cũ: "từ chối tiếp nhận file sai mẫu hay nhận rồi gắn cờ". Không
phải chọn. Sổ đã phân định sẵn hai điều kiện khác nhau, cả hai đều áp dụng — dòng **0.1** *từ chối*
khi không nhận ra là biểu nào (đã có một phần: `select_sheet` ném `SheetNotFound`,
`sheet_select.py:145`); dòng **0.2** *cảnh báo + gắn nhãn bằng chứng* khi nhận ra được nhưng có cột
phải đoán theo vị trí. Còn treo H1 và H3.

**Dòng 0.2 hạ từ ✅ xuống 🔨.** WS1 chỉ phủ M15/M15a/M16: `app/adapters/evidence.py` không có một
dòng nào cho BCCT, `BcctFile` (`bcct.py:45-51`) không mang `ParseProvenance`. Dấu ✅ cũ sai.

**T7 đóng khung là "mở rộng mô hình bằng chứng WS1 sang BCCT"**, không phải feature alias-map rời.
Cơ chế: `norm()` của `layout.py:77-86` thay `strip().lower()`; provenance `header-matched` /
`position-only`; từ chối parse khi ba trường bắt buộc không resolve được theo cả nhãn lẫn vị trí
(tiền lệ `IngestPlanError`, `app/pipeline/ingest.py:69,122,135,161`); kiểm đơn ánh cột.

## Không đúng như tưởng

**Mẫu 1 file/DN bỏ sót một ca.** Lần đo đầu lấy một file mỗi DN → kết luận "11/12 DN khớp `_COL`,
chỉ HIEP_QUANG lệch". Critic chỉ ra mẫu có lỗ; quét lại cả 38 file thì ra **3 file thuộc 2 DN** —
HONG_AN 2025 XK `__dup1` bị bỏ sót. Một DN chứa lẫn nhiều bố cục. **Xác minh phải theo file, không
theo DN.**

**Critic đoán DB đã nhiễm — sai.** Nó suy DN 10 (4 kỳ 2023–2026, không khớp DN pilot nào) có thể
nạp bằng chính bản vá chưa commit, nên đề xuất nâng P1. Query ra DN 10 là **ZONSEN**, cả 4 file
BCCT của nó 54 cột, bản đồ theo nhãn ra **đúng bằng `_COL`** — hai đường cho kết quả giống hệt. Đây
là P2. *(Critic chạy không có shell nên không tự query được — nó nói rõ giới hạn đó.)*

**Bố cục MH 81 cột không có trong `data/`.** File gây ra sự việc gốc 01/08 nằm ở `/mnt/p/Downloads`,
ngoài repo. Không fixture được từ dữ liệu local — phải xin lại file.

**Ghi chú H3 rơi mất khi mở ticket.** Session log phiên trước có ghi "mã catalog cho check độ phủ
M15a→M16 chưa có trong catalog 49", nhưng lúc mở #61 tôi không mang sang. Phát hiện lúc rà STATUS
cuối phiên, đã bổ sung vào issue và `tickets.md`. **Đọc lại session log trước khi mở ticket, không
chỉ đọc file sổ.**

## Còn mở

- **#61 chặn bởi owner** — check chiều M15a → M16 chưa có mã catalog (`C4.2` là chiều ngược,
  `app/catalog_full.py:183-188` và `../audit-hq/de-an-audit-hq.md:227`). `CLAUDE.md` cấm sửa catalog
  ở repo này trước. Owner chốt mã rồi thêm mục vào `../audit-hq/`.
- **H1** — nhiễm theo mã hay chặn cả mức, cho các mức khác ngoài độ phủ định mức.
- **Đ.1** — 6 check bắn 0 phát hiện, chưa ai xác minh.
- **`fix/bcct-label-columns` chưa push, chưa test.**

## Tiếp theo

`/implement` từng ticket ở session mới, clear context giữa mỗi cái. Grab được ngay: **#57, #58,
#59, #63**. #60 chờ #59 · #61 chờ #60 + quyết định catalog · #62 chờ #57 + #58 + #60.

Mỗi ticket cắt nhánh từ `main` (`d528b2f`), không dùng lại `feat/data-completeness-gate`.
