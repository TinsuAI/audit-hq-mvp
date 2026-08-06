# Sổ yêu cầu — gộp ba tài liệu

Mỗi yêu cầu MỘT dòng. Yêu cầu được nêu nhiều lần thì vẫn một dòng, cột **Nguồn** ghi đủ.
Xếp theo **mức** — mức thấp phải đứng vững trước thì mức trên mới có nghĩa.

**Nguồn:** `D` = anh Dũng (2 bản ghi âm) · `Y` = chị Duyên, notes 05/08 · `J` = chị Duyên, đề xuất
16/06. Lưu ý: `Y` và `J` cùng một người, cách nhau 7 tuần — không phải hai nguồn độc lập.

**Trạng thái:** ✅ đã có · 🔨 có một phần · ⬜ chưa có · 🚫 chặn bởi dữ liệu

**Soát lại 06/08/2026** sau khi PR #64 (bảy ticket #57–#63) và PR #67 (ADR #23) vào `main`. Số phát
hiện lấy từ `check_runs` trên DB local — 14 (DN, kỳ), lần chạy cuối 06/08 07:38.

---

## Mức 0 — Tiếp nhận file

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| 0.1 | Kiểm định dạng + đúng mẫu + đủ chỉ tiêu. **Sai mẫu → từ chối tiếp nhận**, báo lỗi cụ thể | J10 | 🔨 đã từ chối được 2 ca: BCCT không resolve nổi trường bắt buộc (`bcct.py`), file quyết toán không đọc được / thiếu nhãn sổ (`ingest.py:129-168`). M15/15a/16 sai mẫu vẫn *nhận rồi gắn cờ* |
| 0.2 | Đọc đúng cột — mỗi cột mang nhãn bằng chứng, cột đoán theo vị trí thì cảnh báo | — | ✅ T7 #63 — `BcctFile` mang `ParseProvenance`, `_COL` chỉ dùng khi nhãn xác nhận bố cục chuẩn. 3 file từng đọc sai nay resolve **19/19 trường theo nhãn** |
| 0.3 | Map biểu mẫu 15 / 15a / 16 theo thông tư **121** | D12, Y11 | ⬜ Y11 ghi "later"; 4 họ template seed (#51, #52) đều là TT39 |
| 0.4 | Chuẩn hoá dữ liệu đầu vào — mỗi phần mềm kế toán kết xuất một kiểu | D13 | ⬜ |

## Mức 1 — Mỗi biểu tự đứng vững

*(không so với nguồn nào khác)*

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| 1.1 | Phương trình cân đối M15 và M15a | — | ✅ C2.1, C2.2 — vẫn bắn **0** trên cả 14 (DN, kỳ) |
| 1.2 | Tồn kho âm | — | ✅ C2.3, C2.4 — vẫn bắn **0** trên cả 14 (DN, kỳ) |
| 1.3 | Tồn đầu/cuối phải là **số nguyên** với đvt cái/chiếc. Định mức thì được lẻ | D10, Y4 | ⬜ |
| 1.4 | **ĐM < 1** với NVL đvt cái/chiếc → cảnh báo; ĐM > 1 bỏ qua | J3 | ⬜ đo được: **5.260 dòng** |

## Mức 2 — Có đủ nguyên liệu để tính không

*(đây là các CỔNG — không phải sai phạm của DN, mà là "mình tính được không")*

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| 2.1 | **Bảng thừa/thiếu định mức** — liệt kê mã thành phẩm thiếu ĐM, không chỉ báo tổng | D1, Y1.1 | ✅ T5 #61 — check MỚI **C4.9**, 66 phát hiện / 13 kỳ |
| 2.2 | ĐM **kế thừa** giữa các năm; chỉ khai lại khi thay đổi | D6, D7, Y1.2, J2c | ✅ T4 #60 — `app/checks/effective_norms.py`, gộp theo sổ. **Sửa 06/08:** kế thừa theo **THÀNH PHẨM** (bản khai mới thay trọn bản cũ), không ghép từng cặp TP-NVL — ghép cặp giữ thêm 774 cặp / 126 mã TP chưa từng được khai cùng nhau |
| 2.3 | Chuỗi Mẫu 16 **đứt quãng** giữa các năm → cảnh báo | J2c | ⬜ luật kế thừa (2.2) lấp chỗ đứt mà không báo — chưa ai thấy khoảng hở |
| 2.4 | Có tồn đầu kỳ mà lại có ĐM khai kỳ này → cảnh báo **"ĐM mới"** | Y1.3 | ⬜ |
| 2.5 | NVL trong M16 không có nguồn trong M15 | — | ✅ C4.1 — **244** phát hiện (19 lúc 05/08; phạm vi mở theo #59 + sửa ngoài ticket) |
| 2.6 | **Đvt của cùng một NVL phải khớp** giữa M16 và M15 | J8 | ✅ 06/08 — C3.3 mở phạm vi sang M16 (đề án sửa trước). Trên pilot: 108 → **152** phát hiện, 47 dòng có M16 trong nguồn lệch |
| 2.7 | **Đếm tờ khai** HQ vs DN, chỉ ra thừa/thiếu từng tờ | D3 | ⬜ |
| 2.8 | Số dư đầu kỳ: đối chiếu DN vs HQ, bắt `#N/A` | D2 | ⬜ |

## Mức 3 — Đối chiếu chéo nguồn (BCQT ↔ tờ khai)

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| 3.1 | Lệch nhập trong kỳ giữa NXT và tờ khai nhập, **xếp theo giá trị tiền** | D4, Y5 | ✅ 06/08 — `findings.value_vnd` + `app/checks/valuation.py`; bảng xếp theo tiền trong từng mức. Quy được **766/858** phát hiện C1.1 trên pilot |
| 3.2 | Lệch nhập là **không phải lỗi** — nhập trả lại / chuyển kho / tái nhập là hợp lệ; xuất danh sách để DN giải trình | D4 | ⬜ |
| 3.3 | Phân loại hàng hoá, truy nguồn NVL | — | ✅ C3.x (C3.1 11 · C3.2 1.358 · C3.3 108); C5.1 vẫn bắn **0** — đáng kiểm |
| 3.4 | Tách 2 loại báo cáo của một pháp nhân (02 SXXK vs 04 gia công) | D15 | ✅ ADR #19 |

## Mức 4 — Suy diễn từ định mức

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| 4.1 | Tiêu hao lý thuyết = **ĐM × sản lượng nhập kho** (không phải xuất khẩu), **xếp theo giá trị** | D5, Y3, Y6 | ✅ 06/08 — đủ 3/3: số nhân `intake_qty` · nhường mã không có dòng M15 cho C4.1 (#59) · giá trị tiền quy được **1.557/1.665** phát hiện C4.3 |
| 4.2 | ĐM của cùng SP **lệch nhiều giữa các năm** → cảnh báo | Y7.1, J2b | ⬜ = C4.6 catalog (`status="wip"`, chưa vào registry). T4 đã mở đường: ĐM nhiều kỳ đọc được rồi |
| 4.3 | Định giá BOM bằng đơn giá BCCT để so qua các năm (né chuyện mã đổi) | Y7.2 | ⬜ |
| 4.4 | Cùng SP khai **khác tên** qua các năm; khác tên nhưng cùng đặc tính | J2a | ⬜ không được gọi LLM trong rule |

## Nhánh song song — Liên kỳ

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| L.1 | Tồn cuối kỳ trước = tồn đầu kỳ này, **NVL** | Y2 | ✅ C6.1 — ra **2** phát hiện. Lỗ "kỳ N-1 trống vẫn ra 0" đã bịt 06/08: thiếu M15 kỳ N-1 → *chưa đánh giá được*, đúng **8/14** kỳ pilot rơi vào đó |
| L.2 | Bản tương ứng cho **thành phẩm** (M15a) | Y2 | ⬜ |

## Điều tra — không phải yêu cầu mới

| # | Việc | Nguồn | TT |
|---|---|---|---|
| Đ.1 | **5 check bắn 0 phát hiện** — C2.1, C2.2, C2.3, C2.4, C5.1 trên cả 14 (DN, kỳ) | — | ✅ **0 là thật, không phải check hụt dữ liệu** (đo 06/08 bằng SQL cùng công thức với check, trên 29.760 dòng M15 + 2.726 dòng M15a): lệch phương trình > 0,01 = **0** dòng · tồn cuối âm = **0** dòng · xuất SX > 0 mà nhập = 0 và tồn đầu = 0 = **0** dòng (chỉ 96 dòng có nhập = 0 và tồn đầu = 0, không dòng nào có xuất SX). Cột `closing_qty` không có dòng nào NULL. Lý do: file kết xuất tính cột tồn cuối BẰNG chính phương trình — C2.1/C2.2 chỉ bắt được file sửa tay. C6.1 đã rời danh sách (ra 2 phát hiện) |

## Dữ liệu mới phải nạp thêm

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| N.1 | Biên bản kiểm kê — **3 nhóm**: TP, NVL, dở dang | D8, Y8 | ⬜ nạp được thì hết phải đoán dở dang |
| N.2 | Bảng đối chiếu mã DN ↔ mã HQ (chỉ ~50% trùng) | D9 | ⬜ |
| N.3 | BOM kỹ thuật + sơ đồ quy trình sản xuất | J4 | ⬜ |
| N.4 | Quyết định / biên bản / kết quả tiêu hủy, phế liệu, hao hụt | J5 | ⬜ |
| N.5 | Dở dang đầu kỳ / cuối kỳ — nếu không có N.1 thì phải ghi là **giả định** | D17 | ⬜ |

## Chặn bởi dữ liệu nguồn

| # | Yêu cầu | Nguồn | Vướng |
|---|---|---|---|
| B.1 | Thống kê **tờ khai huỷ và tờ khai sửa** | D14, Y12, J1 | 🚫 BCCT không mang trạng thái này |
| B.2 | XNK tại chỗ đối ứng — DNCX khai E15 thì phải có DN khác xuất sang | Y9 | 🚫 không có dữ liệu DN đối ứng; vượt ranh giới quyền theo DN |
| B.3 | Qua khu vực giám sát mới chứng minh hàng thực đi / thực về | Y10 | 🚫 không có cột trạng thái thông quan |

## Ngoài phạm vi kiểm tra

| # | Yêu cầu | Nguồn | TT |
|---|---|---|---|
| X.1 | Hạn nộp BCQT: tự tính năm tài chính + hạn, cảnh báo quá hạn | J6 | 🔨 niên độ nay là thuộc tính DN (`fiscal_start_month`, #50) + cửa sổ kỳ có ràng buộc (#66). **Hạn 90 ngày chưa tính, chưa cảnh báo quá hạn** |
| X.2 | NVL chịu thuế XK dùng trong BOM hàng gia công | J7 | ⬜ cần dữ liệu thuế suất |
| X.3 | Xuất xứ: gia công đơn giản hay đáng kể, quy tắc xuất xứ | J9 | ⬜ domain lớn |
| X.4 | Drill-up từ số dư về từng phiếu xuất kho | D11 | ⬜ |
| X.5 | Báo cáo ngắn, có điểm nhấn, mọi con số truy vết được | D16 | 🔨 evidence_refs đã có |

---

## Phạm vi issue #56 — chốt 05/08/2026

Issue #56 ship **cổng độ phủ định mức, không hơn**. Lý do: thân issue nêu đúng một việc — "phải
kiểm tra ngay được số lượng định mức đã đủ trong báo cáo hay chưa, vì khi chưa đủ định mức thì mọi
kiểm tra về sau đều không chính xác". Q1/Q2/Q3 ở `grill-state.md` đã chốt đủ để build.

**Trong phạm vi — XONG cả bảy, PR #64 merge 06/08/2026:**

| Việc | Gốc | Kết |
|---|---|---|
| Bảng thừa/thiếu định mức — liệt kê mã TP thiếu ĐM | dòng 2.1 | ✅ T5 #61 — check mới **C4.9** |
| ĐM kế thừa giữa các năm, dùng bản khai gần nhất ≤ kỳ đang xét | dòng 2.2, quyết định Q2 | ✅ T4 #60 — `effective_norms.py` |
| Trường "năm đầu nộp BCQT" trên `companies`, cán bộ nhập | quyết định Q1 | ✅ T1 #57 — `companies.first_bcqt_year` |
| `not_evaluable` thành trạng thái chạy thật: `run_checks()` ghi được, `compute_company_year_score()` loại khỏi cả phần cộng điểm lẫn phần trần, UI hiện được | quyết định Q1+Q3 | ✅ T2 #58 — hệ quả điểm số còn mở ở **#65** |
| Cổng nhị phân trên C4.3: có mã TP sản xuất trong kỳ mà chưa từng khai ĐM ở bất kỳ kỳ nào → C4.3 `not_evaluable` | quyết định Q3 | ✅ T6 #62 — C4.3 chặn ở **10/14** kỳ, chạy ở 4 |
| Việc (b) của `fix/c43-multiplier-p07`: bỏ qua mã không có dòng M15, nhường C4.1 | quyết định Q2 | ✅ T3 #59 — kèm sửa ngoài ticket cho C4.1 nhận phần nhường |
| Đọc cột BCCT theo nhãn + mô hình bằng chứng WS1 cho BCCT | dòng 0.2 | ✅ T7 #63 — 3 file từng đọc sai nay 19/19 trường theo nhãn |

**Còn mở sau khi #56 ship:** #65 — luật `not_evaluable` kéo điểm rủi ro GIẢM (bỏ luật khỏi cả tử số
lẫn trần); #68 — cột chết `check_runs.skip_reason` sau khi #53 gộp vào `not_evaluable` của #58;
#66 — cửa sổ kỳ / niên độ, đã sửa ràng buộc nhưng còn chờ xác nhận với cán bộ.

**Cả sổ**, chia theo cái gì đang chặn — danh sách dưới gồm luôn 3 dòng #56 đã ship. Không phải dòng
nào cũng ship được bằng PR:

- **Đã có** (12): 0.2, 1.1, 1.2, 2.1, 2.2, 2.5, 2.6, 3.1, 3.3, 3.4, 4.1, L.1 — nhưng 5 check phủ
  1.1/1.2/3.3 vẫn bắn 0, xem Đ.1 (đã đo: 0 là thật).
- **Ship được bằng code, xếp hàng sau** (14): 0.1, 0.3, 0.4, 1.3, 1.4, 2.3, 2.4, 2.7, 2.8, 3.2,
  4.2, 4.3, 4.4, L.2. Rẻ nhất là 1.4 và 4.2: phần đo (1.4: 5.310 dòng) và nền ĐM nhiều kỳ (4.2)
  đã xong, chỉ còn viết check.
- **Chặn bởi dữ liệu nguồn** (3): B.1, B.2, B.3. Không PR nào ship được, phải xin nguồn khác.
- **Cần file mới nạp vào** (5): N.1–N.5. Adapter viết được, nhưng vô nghĩa khi chưa có file.
- **Ngoài phạm vi kiểm tra** (5): X.1–X.5. Ông tự đánh dấu, X.3 (quy tắc xuất xứ) là domain riêng.

12 + 14 + 3 + 5 + 5 = 39 dòng đánh số trong sổ. (Sáng 06/08 là 3 + 6 + 17 + 3 + 5 + 5; ba dòng
trong phạm vi #56 rồi 2.6, 3.1, 4.1 lần lượt chuyển sang nhóm "đã có".)

**Một câu còn treo** (chi tiết ở `grill-state.md`):

- **H1** — ngữ nghĩa "qua mức trước mới chạy mức sau" cho các mức khác. Không chặn #56: Q3 đã chốt
  riêng cho độ phủ định mức. Chốt khi nào cần cổng thứ hai.

**H2 đã gỡ.** Câu hỏi cũ là "từ chối tiếp nhận file sai mẫu hay nhận rồi gắn cờ". Sổ đã phân định
sẵn: dòng **0.1** nói *từ chối* khi không nhận ra là biểu nào; dòng **0.2** nói *cảnh báo* khi nhận
ra được nhưng có cột phải đoán theo vị trí. Không phải chọn một trong hai — hai điều kiện khác nhau.

## Đọc bảng này ra được gì

**29 yêu cầu, không phải 40.** Cách ra con số: sổ có **39** dòng đánh số; bỏ **5** dòng nguồn `—`
(năng lực đã có sẵn, không ai yêu cầu: 0.2, 1.1, 1.2, 2.5, 3.3) còn **34** dòng do ba tài liệu nêu;
bỏ tiếp **5** dòng X.* nằm ngoài phạm vi kiểm tra → **29**. Trùng lặp đã gộp: tờ khai huỷ/sửa nêu 3
lần, tiêu hao lý thuyết 3 lần, ĐM kế thừa 4 lần.

**12 cái đã có sẵn** (0.2, 1.1, 1.2, 2.1, 2.2, 2.5, 2.6, 3.1, 3.3, 3.4, 4.1, L.1). Năm check phủ 1.1/1.2/3.3 vẫn
bắn 0 (C2.1–C2.4, C5.1) nhưng Đ.1 đã đo xong: **dữ liệu không có dòng nào vi phạm**, nên ba dòng
đó ✅ có căn cứ. Hệ quả cho việc chọn việc tiếp: check nào đọc lại đúng các cột M15/M15a đó cũng sẽ
ra 0 — muốn có phát hiện phải đi vào cột khác (định mức, đơn vị tính, giá trị tiền).

Dòng 0.2 đã lên ✅ sau T7 (#63): `bcct.py` dò cột theo nhãn, `BcctFile` mang `ParseProvenance`,
`_COL` chỉ được dùng khi đủ neo nhãn đúng vị trí. Ba file từng đọc sai (HIEP_QUANG 2021 NK/XK,
HONG_AN 2025 XK) nay resolve 19/19 trường theo nhãn, 0 rơi về `_COL`.

**Mức 2 còn 4/8 dòng chưa có** (2.3, 2.4, 2.7, 2.8) — 2.1 và 2.2 ship trong loạt #56, 2.6 ship
chiều 06/08. Đây vẫn là chỗ trống lớn nhất, và đúng là chỗ anh Dũng dừng lại không chịu đọc kết quả.

**3 cái chặn bởi dữ liệu** (B.1–B.3) — không phải việc code, phải xin nguồn khác.
