# Quyết định + bằng chứng — issue #56

Đọc `yeu-cau.md` để biết LÀM GÌ. File này ghi ĐÃ CHỐT GÌ và bằng chứng đằng sau.

## Đã chốt (3)

**Q1 — Kỳ sớm nhất của mỗi DN mặc định `not_evaluable` cho check độ phủ định mức**, trừ khi cán bộ
xác nhận đó đúng là năm đầu nộp BCQT.
Lý do: không phân biệt được "chưa từng khai" với "đã khai trước cửa sổ dữ liệu mình có".
→ Cần trường "năm đầu nộp BCQT" trên `companies`, cán bộ nhập. Chỗ ở tự nhiên của nó là chức năng
cảnh báo hạn nộp BCQT (yêu cầu X.1).

**Q2 — Định mức chuyển tiếp ĐƯỢC đưa vào phép nhân C4.3.** Dùng bản khai gần nhất ≤ kỳ đang xét,
không phải `period_year == year`.
Bắt buộc ship kèm việc (b) của nhánh `fix/c43-multiplier-p07` — bỏ qua mã không có dòng M15, nhường
C4.1 — nếu không sẽ đẻ ra 151 phát hiện Nghiêm trọng dán nhầm nhãn.

**Q3 — Cổng là NHỊ PHÂN, không phụ thuộc sản lượng.** Có mã thành phẩm nào sản xuất trong kỳ mà
chưa từng khai định mức ở bất kỳ kỳ nào (kể cả các năm trước) → nhóm 4 `not_evaluable`.
KHÔNG có ngưỡng phần trăm. Đề xuất ngưỡng 5% và thước tỷ trọng sản lượng trước đó **đã bị bác**.

## Đang treo (1)

**H1 — ngữ nghĩa "qua mức trước mới chạy mức sau"** cho các mức KHÁC ngoài độ phủ định mức:
- **A** — nhiễm theo MÃ: mã vi phạm mức N thì mã đó `not_evaluable` ở mức N+1, mã sạch vẫn chạy.
- **B** — chặn cả mức: mức N còn phát hiện nào thì mức N+1 không chạy.
- Khuyến nghị **A**. Theo B thì mức 3 đang có 13.368 phát hiện → mức 4 không bao giờ chạy.
- *(Q3 đã chốt riêng cho độ phủ định mức: chặn cả nhóm, vì thành phẩm chưa khai ĐM thì không biết
  nó ăn NVL nào, không khoanh được vùng ảnh hưởng.)*

## Đã gỡ

**H2 — tiếp nhận file.** Câu hỏi cũ: hệ thống nhận rồi gắn cờ (`needs_review`), còn đề xuất 16/06
viết "sai mẫu → từ chối tiếp nhận" — chọn cái nào.

Không phải chọn. Sổ đã phân định sẵn hai điều kiện khác nhau, cả hai đều áp dụng:
- **0.1** — không nhận ra là biểu nào → **từ chối**. Đã có một phần: `select_sheet` ném
  `SheetNotFound` (`app/adapters/sheet_select.py:145`).
- **0.2** — nhận ra được nhưng có cột phải đoán theo vị trí → **nhận, gắn nhãn bằng chứng, cảnh
  báo**. Đó đúng là cơ chế WS1 đang chạy cho M15/M15a/M16.

Gỡ ngày 05/08, khi rà lại `app/adapters/bcct.py` cho T7 (#63).

---

# Bằng chứng đo được

Đo trên `audit_hq.sqlite` local, 2026-08-05. Đo lại tốn công — đừng vứt.

## Chuyển tiếp định mức giải thích được bao nhiêu

TP có sản xuất trong kỳ mà thiếu định mức CÙNG KỲ, tách theo có/không có ĐM kỳ trước:

| DN | kỳ | TP có SX | thiếu ĐM cùng kỳ | có ĐM kỳ trước | **chưa từng có** |
|---|---|---|---|---|---|
| 7 | 2025 | 56 | 0 | 0 | 0 |
| 8 | 2024 | 368 | 5 | 0 | 5 |
| 8 | 2025 | 373 | 16 | **16** | **0** |
| 9 | 2025 | 39 | 9 | 0 | 9 |
| 10 | 2023 | 61 | 13 | 0 | 13 |
| 10 | 2024 | 138 | 5 | 0 | 5 |
| 10 | 2025 | 215 | 15 | 0 | 15 |
| 10 | 2026 | 166 | 17 | 0 | 17 |

Chuyển tiếp xoá sạch 16/16 của DN 8, giải thích **0** cho DN 8/2024 và toàn bộ DN 10. Luật tách
đúng hai tình huống khác nhau — không phải luật làm mọi thứ biến mất.

Cột cuối là đầu vào của cổng Q3.

## Tác động của Q2 lên C4.3 (đo trên DN 8/2025 — chỗ duy nhất có ca chuyển tiếp)

16 mã TP, 485 đơn vị sản xuất, chạm 1.334 mã NVL.

- Tổng tiêu hao bổ sung 144.230 trên 2.840.692.506 đang tính = **0,005%** — con số này gây hiểu
  nhầm, vì C4.3 bắn theo TỪNG mã NVL, không theo tổng.
- Theo mã: **321 / 8.144 mã đổi bậc** — 236 lên Nghiêm trọng, 85 lên Cảnh báo, **0 mã đi ngược**.
- Bóc 236 mã Nghiêm trọng: 204 mã rơi vào ca "có tiêu hao lý thuyết mà M15 xuất SX ≤ 0", trong đó
  **151 mã KHÔNG có dòng M15 nào** (đất của C4.1) và **53 mã có dòng M15 nhưng xuất SX = 0**
  (mâu thuẫn thật).

→ 151 là lý do việc (b) không phải tuỳ chọn.

## Tác động của Q1 + Q3 lên C4.3 hiện tại

| DN | kỳ | C4.3 hiện có | Sau khi áp cổng |
|---|---|---|---|
| 7 | 2025 | 27 | chưa đánh giá (kỳ biên) |
| 8 | 2024 | 564 | chưa đánh giá (kỳ biên) |
| 8 | 2025 | **1.772** | **CHẠY** |
| 9 | 2025 | 8 | chưa đánh giá (kỳ biên) |
| 10 | 2023 | 7 | chưa đánh giá (kỳ biên) |
| 10 | 2024 | 243 | chặn — 5 mã chưa từng khai ĐM |
| 10 | 2025 | 107 | chặn — 15 mã |
| 10 | 2026 | 568 | chặn — 17 mã |

**Còn 1.772 / 3.296 = 54%.** Chỉ DN 8/2025 qua được cả hai cổng. Đó đúng là điều anh Dũng đòi:
không đưa ra số tính trên định mức thiếu.

## Số nền khác

- **Cả 8 (DN, kỳ) đều có đủ 4 nguồn** M15, M15a, M16, BCCT → điều kiện "thiếu file" bắn 0 lần.
- **C2.1–C2.4, C5.1, C6.1 chạy 7 lần, ra 0 phát hiện** trên mọi pilot. C5.1 = 0 là số đáng kiểm lại.
- Khối lượng hiện tại: mức 3 (C1.x, C3.x, C5.1) = **13.368** · mức 4 (C4.3) = **3.296** ·
  mức 1 (C2.x) = **0** · C4.1 = 19.
- **Đvt lệch thật giữa M16 và M15: 8 mã** toàn bộ dữ liệu (mét↔cuộn 6, chiếc↔không rõ 1,
  chiếc↔tấm 1). Con số "100% ở DN10" là SAI — do so chuỗi thô, `PCE` và `Cái/Chiếc` là cùng đơn vị.
  **Phải quy về họ đơn vị (`app/checks/uom.py`) trước khi so.**
- **ĐM < 1 với NVL họ chiếc: 5.260 dòng.** DN7 39,7% · DN9 42,0% · DN8 ~1,3% · DN10 1,0% các năm
  nhưng **13,4% ở 2026** (nhảy từ 1,0% năm 2025 — chính là loại biến động qua năm mà yêu cầu 4.2
  đòi cảnh báo).

## Nguồn yêu cầu

- `officer-requirements.md` — anh Dũng, 2 bản ghi âm
- Notes chị Duyên 2026-08-05 — 12 mục
- `BÁO CÁO ĐỀ XUẤT RÀ SOÁT - 16.06 (1).docx` — chị Duyên, 10 mục, có TRƯỚC hai buổi họp

**HAI người, không phải ba nguồn độc lập** — chị Duyên nêu hai lần cách nhau 7 tuần.
Cả hai đều nói cùng một luật: Mẫu 16 kế thừa giữa các năm. Đó là nền của Q2.
