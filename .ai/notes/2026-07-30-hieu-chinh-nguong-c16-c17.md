# Hiệu chỉnh ngưỡng C1.6 / C1.7 — bằng chứng đo lường

Nghi vấn ghi ở `.ai/STATUS.md` (2026-07-29): C1.6 gắn cờ 55% dân số mã NVL, C1.7 thêm 23%. Ghi chú này đo trực tiếp trên DB thật (read-only) để trả lời: đây là phát hiện thật hay lỗi hiệu chỉnh ngưỡng. Không sửa code — chỉ đo và kết luận.

## 1. Điều kiện kích hoạt đọc từ code

**C1.6** (`app/checks/c1_quantity.py:429-473`, `registry.py:96-104`): fire khi `NvlBalance.repurpose_qty > 0` (sau khử trùng theo `(book, material_code)`, giữ dòng `repurpose_qty` lớn nhất — `_one_row_per_material`) VÀ `material_code` không nằm trong tập `item_code` có `customs_code = 'A42'` khai trong cùng (company, year). Severity cố định `CRITICAL` (`default_severity`, không qua `severity_for`).

**KHÔNG có ngưỡng độ lớn nào ở C1.6.** Bất kỳ `repurpose_qty` lớn hơn 0 mà không khớp A42 đều bị gắn CRITICAL — 1 đơn vị hay 200.000 đơn vị đều fire như nhau.

**C1.7** (`c1_quantity.py:476-519`, `registry.py:105-114,262-267`): `pct = repurpose_qty / (opening_qty + import_qty) * 100`, cùng khử trùng `(book, material_code)` nhưng giữ dòng có mẫu số (`opening+import`) lớn nhất. `severity_for("C1.7", pct)`: `pct < 10%` → không fire · `10% ≤ pct ≤ 25%` → WARNING · `pct > 25%` → CRITICAL.

C1.7 **có** ngưỡng, dạng tỷ lệ tương đối so với tồn đầu + nhập trong kỳ.

## 2. Đo trên DB thật — PILOT_006/2025 (company_id=8, quần thể lớn nhất)

Mẫu số `denom_nvl` (`app/checks/denominators.py`: mã M15 ∪ mã BCCT phía nhập E11/E15, loại hình DNCX xác định qua `detect_company_type`) = **10.572 mã NVL distinct**.

Dòng `NvlBalance` có `repurpose_qty > 0` sau khử trùng `(book, material_code)` = **5.785 dòng** (không có mã trùng sổ ở kỳ này nên số trước/sau khử trùng bằng nhau). Mã có khai A42 (`customs_code='A42'`, distinct `item_code`) = 652.

### C1.6 — quần thể = 5.785 mã (không A42, repurpose>0) = **54,7% denom_nvl** (khớp "55%" trong STATUS.md)

Percentile `repurpose_qty` (n=5.785, đơn vị 95,3% dòng là "Cái/Chiếc"/"PIECES" — đếm nguyên chiếc, không phải khối lượng/thể tích nên không phải artifact quy đổi đơn vị):

| p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|
| 49,0 | 264,0 | 1.005,2 | 2.077,6 | 9.599,8 | 221.709,0 |

Số mã còn bị gắn cờ nếu thêm sàn tuyệt đối vào `repurpose_qty` (mẫu số vẫn 10.572):

| sàn > | số mã | % denom |
|---|---|---|
| 0 (hiện tại) | 5.785 | 54,7% |
| 1 | 5.547 | 52,5% |
| 5 | 4.818 | 45,6% |
| 10 | 4.309 | 40,8% |
| 50 | 2.802 | 26,5% |
| 100 | 2.200 | 20,8% |
| 500 | 963 | 9,1% |
| 1.000 | 581 | 5,5% |

Không sàn tuyệt đối nào đưa số phát hiện của MỘT kiểm tra ở MỘT (DN, kỳ) xuống mức cán bộ xử lý được (cỡ vài chục–vài trăm) mà không cắt bỏ phần lớn quần thể — ở sàn 1.000 chiếc (rất cao so với median 49) vẫn còn 581 mã.

### C1.7 — quần thể trước ngưỡng = 5.785 mã (denom>0 & repurpose>0) = **54,7% denom_nvl** — CÙNG quần thể gốc với C1.6 (khác biệt duy nhất: C1.7 chưa loại mã có A42)

Percentile `ratio_pct`:

| p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|
| 3,26% | 100,0% | 100,0% | 100,0% | 100,0% | 100,0% |

Phân bố **hai cực**: median chỉ 3,26% (dưới ngưỡng fire) nhưng từ p75 trở lên toàn bộ đã là 100% — nghĩa là ≥25% quần thể có `repurpose_qty` bằng ĐÚNG toàn bộ `opening_qty + import_qty` của mã đó (chuyển hết vào MĐSD, không còn dư).

Số mã fire tại từng ngưỡng ứng viên:

| ngưỡng > | số mã | % denom |
|---|---|---|
| ≥10% (hiện tại) | 2.436 | 23,0% (khớp "thêm 23%" STATUS.md) |
| 25% | 2.194 | 20,8% |
| 50% | 2.083 | 19,7% |
| 75% | 2.034 | 19,2% |
| 90% | 1.997 | 18,9% |
| 95% | 1.984 | 18,8% |
| 99% | 1.964 | 18,6% |

**Điểm then chốt:** nâng ngưỡng từ 10% lên 99% chỉ giảm số phát hiện từ 2.436 xuống 1.964 (−19%), không giảm theo cấp số như kỳ vọng của một điều chỉnh ngưỡng. Khối phát hiện dồn sát 100% nên đổi vị trí ngưỡng trong khoảng 10–99% gần như không đụng tới nó.

### Đối chiếu để loại trừ giả thuyết "check lúc nào cũng vậy"

| DN/kỳ | denom_nvl | C1.6 (%) | C1.7 fire ≥10% (%) |
|---|---|---|---|
| PILOT_002/2025 | 286 | 0 (0,0%) | 0 (0,0%) |
| PILOT_006/2024 | 7.885 | 1.660 (21,1%) | 618 (7,8%) |
| **PILOT_006/2025** | **10.572** | **5.785 (54,7%)** | **2.436 (23,0%)** |
| PILOT_004/2025 | 127 | 1 (0,8%) | 1 (0,8%) |

Cùng một DN (006), tỷ lệ đổi từ 21,1%/7,8% (2024) sang 54,7%/23,0% (2025) — hơn gấp đôi trong một kỳ. Đây KHÔNG phải hằng số cấu trúc của check (nếu là lỗi thiết kế thì phải tái diễn giống nhau ở mọi kỳ) — biến động theo kỳ ủng hộ giả thuyết đây là hiện tượng nghiệp vụ thật của 006/2025, cần cán bộ xác minh trực tiếp, không phải hiện tượng do ngưỡng.

## 3. Trả lời câu hỏi

**C1.6:** không có cơ sở nghiệp vụ nào để đặt sàn số lượng tuyệt đối — đơn vị là "cái/chiếc" (số nguyên đếm được, không phải khối lượng/thể tích nên không có artifact làm tròn hay quy đổi đơn vị); điều kiện miễn thuế theo NĐ 134/2016 và TT 38/2018 không quy định mức chuyển MĐSD nhỏ được miễn khai A42. Bất kỳ số cắt nào (>1, >50, >1.000…) đưa vào để giảm số phát hiện là **NGƯỠNG TÙY Ý (arbitrary cut)**, không neo được vào quy định hay dung sai kỹ thuật nào — nếu chọn, phải ghi rõ đây là ngưỡng vận hành theo năng lực xử lý của cán bộ, không phải ngưỡng luật định.

**C1.7:** ngưỡng phần trăm hiện có (10%/25%) CÓ cơ sở nghiệp vụ — tỷ lệ so với tồn đầu + nhập là thước đo trọng yếu tương đối hợp lý, không phải số tùy chọn. Nhưng đo thực tế cho thấy đổi vị trí ngưỡng không giải quyết được khối lượng phát hiện, vì phân bố dồn cực ở đuôi phải (≥25% mã đã ở đúng 100%). Số 2.436 mã (23,0% denom) phần lớn là **phát hiện thật** theo nghĩa: chúng phản ánh một hiện tượng rời rạc (chuyển hết một mã vào MĐSD), không phải nhiễu ngưỡng.

**Kết luận chung:** gốc vấn đề không nằm ở vị trí ngưỡng mà ở CHỨC NĂNG của hai kiểm tra — cả hai đọc trên cùng một quần thể gốc (5.785 mã, 54,7% denom, có `repurpose_qty>0`). C1.6 lọc theo có/không hồ sơ A42 (không lọc theo độ lớn) → mọi mã trong quần thể gốc trừ mã có A42 đều fire. C1.7 lọc theo tỷ lệ nhưng tỷ lệ đó dồn cực nên lọc yếu. Thêm sàn tuyệt đối vào C1.6 CÓ giảm được số đếm (bảng §2) nhưng bằng một ngưỡng không có căn cứ luật — phải ghi nhận đó là lựa chọn vận hành, không phải sửa lỗi.

## 4. Ràng buộc CLAUDE.md và nội dung cần đưa vào repo đề án

`CLAUDE.md` của repo này: "Catalog 49 kiểm tra ở repo đề án `audit-hq` — đừng thay đổi mô tả check ở đây trước khi update đề án." Ghi chú này là gói bằng chứng cho thay đổi đó, không phải bản thân thay đổi — `app/checks/c1_quantity.py` và `app/checks/registry.py` không bị sửa.

Đề án hiện ghi (`../audit-hq/de-an-audit-hq.md:202-203`): C1.6 mô tả điều kiện `> 0`, không nêu ngưỡng độ lớn; C1.7 ghi ngưỡng ">10% Cảnh báo · >25% Nghiêm trọng" — khớp đúng những gì code hiện có, không lệch tài liệu. Dòng 77 đã ghi "Cơ quan Hải quan có toàn quyền điều chỉnh ngưỡng theo thực tế nghiệp vụ" — đề án coi ngưỡng là tham số cấu hình do cán bộ chỉnh, không phải hằng số luật định.

Đề án cần bổ sung, trước khi sửa code repo này:

1. Quyết định C1.6 có cần sàn số lượng tuyệt đối hay không. Nếu có: ghi rõ đây là ngưỡng vận hành (operational threshold), không phải ngưỡng luật định, kèm giá trị cụ thể và cơ sở chọn giá trị đó (ví dụ khảo sát thêm với cán bộ nghiệp vụ hoặc đo trên nhiều DN khác trước khi chốt số — dữ liệu 4 (DN, kỳ) hiện có không đủ để chốt một số chung).
2. Phân vai rõ C1.6 và C1.7 thay vì coi là dư thừa lẫn nhau: C1.6 = danh sách mã thiếu hồ sơ A42 (compliance/hồ sơ), C1.7 = mức độ trọng yếu tài chính của việc chuyển MĐSD (rate). Hai vai trò khác nhau nên không tự động gộp hay loại trừ nhau trên màn hình.
3. Vì phân bố C1.7 dồn cực gần 100%, đề án nên thêm một dải severity cao hơn 25% (ví dụ >75% hoặc >90%) để phân biệt "vượt trọng yếu" khỏi "chuyển gần như toàn bộ mã" — hai dải hiện tại (WARNING/CRITICAL) không đủ phân giải ở đuôi phân bố mà bảng §2 cho thấy.
4. Yêu cầu xác minh nghiệp vụ trực tiếp với DN 006 về kỳ 2025: tỷ lệ C1.6/C1.7 tăng hơn gấp đôi so với 2024 (21,1%→54,7% / 7,8%→23,0%) trên cùng một DN — cần biết đây có phải một sự kiện thật trong 2025 (ví dụ đợt thanh lý/chuyển đổi lớn) hay là lỗi nạp/khớp dữ liệu của kỳ đó trước khi dùng số này làm căn cứ hiệu chỉnh ngưỡng chung cho toàn bộ 49 kiểm tra.

## Nguồn số liệu

Đo bằng `sqlite3` read-only (`file:audit_hq.sqlite?mode=ro`) trên `/home/vp/workspace/client/audit-hq-mvp/audit_hq.sqlite`, script tạm không lưu trong repo (`/tmp/.../scratchpad/measure_c16c17.py`), logic khử trùng và mẫu số tái hiện đúng theo `app/checks/c1_quantity.py::_one_row_per_material` và `app/checks/denominators.py::_count_distinct_nvl`. Không ghi, không sửa DB.
