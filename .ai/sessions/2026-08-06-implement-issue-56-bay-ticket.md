# Session 2026-08-06 — Cài đặt bảy ticket của issue #56 (cổng độ phủ định mức + BCCT đọc cột theo nhãn)

Nhánh `feat/data-completeness-gate`. Vào phiên: `0e1d88d` (chỉ tài liệu). Ra phiên:
[**PR #64**](https://github.com/TinsuAI/audit-hq-mvp/pull/64) đã mở và push (25 commit,
`Closes #57–#63`), repo đề án đã push + `make publish`, một vấn đề tách ra thành issue #65.
Ngoài bảy ticket còn **hai lỗi tự phát hiện** trong lúc làm và **ba quyết định owner** chốt cuối
phiên.

Chạy song song bằng agent trên worktree riêng: đợt 1 là #57, #58, #59, #63 (không ai chặn ai);
#60 tôi tự làm vì nằm trên đường găng; đợt 2 là #61 và #62.

## Đã làm

| Ticket | Issue | Nội dung |
|---|---|---|
| T1 | #57 | `companies.first_bcqt_year`, cán bộ nhập ở form sửa DN. Migration `f1c4a2b7d3e5`, `op.add_column` thẳng |
| T2 | #58 | `not_evaluable` thành trạng thái chạy thật: `NotEvaluable(reason)` check trả về, ghi vào `check_runs.status` + cột mới `status_reason` (migration `d1e2f3a4b5c6`), loại khỏi điểm rủi ro cả tử số lẫn trần, hiện ở UI |
| T3 | #59 | C4.3 bỏ qua mã NVL không có dòng M15 nào trong sổ — đất của C4.1 |
| T4 | #60 | `app/checks/effective_norms.py` — định mức hiệu lực = bản khai có kỳ lớn nhất ≤ kỳ đang xét, gộp theo sổ |
| T5 | #61 | Check MỚI **C4.9** — liệt kê từng mã thành phẩm có sản xuất mà thiếu định mức hiệu lực |
| T6 | #62 | Cổng nhị phân trên C4.3: thiếu độ phủ định mức HOẶC kỳ biên chưa xác nhận năm đầu nộp BCQT → `NotEvaluable` |
| T7 | #63 | Adapter BCCT đọc cột theo NHÃN qua `norm()`, `BcctFile` mang `ParseProvenance`, từ chối parse khi ba trường bắt buộc không resolve, kiểm đơn ánh cột |
| (thêm) | — | C4.1 nhận lại phần C4.3 nhường — xem "Sửa ngoài ticket" |

Trước khi code C4.9 đã sửa repo đề án trước theo `AGENTS.md`: `audit-hq` @ `c5a5c3c` (thêm C4.9,
ghi luật định mức hiệu lực + nhường C4.1 + cổng độ phủ vào mô tả C4.3, danh mục 49 → 50, Giai đoạn I
33 → 34) và `f7c638f` (mở phạm vi C4.1). ADR ngày 05/08 ở `audit-hq/.ai/DECISIONS.md`.

Test: vào phiên 957 pass, ra phiên **1028 pass + 1 xfail**. `ruff check app tests` sạch.

## Quyết định trong phiên

**Mã catalog cho check M15a → M16 là C4.9** (owner chốt). Catalog 49 không có mã cho chiều này —
C4.2 là chiều ngược (M16 → M15a), C4.1 là M16 → M15. Sửa repo đề án trước, rồi mới thêm
`CatalogEntry` ở đây.

**Kế thừa định mức tính theo CẶP (mã SP, mã NVL), không theo mã SP.** Ticket #60 ghi rõ như vậy.
Hệ quả: mã NVL bị bỏ khỏi định mức của một thành phẩm ở kỳ sau vẫn còn hiệu lực từ bản khai cũ. Đo
hai cách chênh nhau 451/86.111 cặp (0,5%) ở DN 8/2025 và 302/44.480 (0,7%) ở DN 10/2026, 0 ở các
(DN, kỳ) còn lại — nhỏ, nhưng là giả định đã ghi lại chứ không phải ngầm.

**Chứng cứ định mức trỏ về kỳ ĐÃ KHAI, không phải kỳ phát hiện.** Định mức kế thừa nằm ở kỳ khác,
nên `evidence_refs` dùng `period_year__in` với các kỳ nguồn; nếu giữ `period_year = year` thì mở
khối chứng cứ ra là bảng rỗng, vi phạm yêu cầu truy nguồn §5.1. Kèm theo: `_describe_evidence_filter`
không còn ẩn `period_year__in` (vẫn ẩn `period_year` vô hướng) — đó chính là thông tin cán bộ cần.

**Cổng chặn cả lần chạy, không chặn theo sổ.** `check_runs` khoá theo (DN, kỳ) nên không lưu được
`not_evaluable` riêng từng sổ. Một sổ vướng thì cả lần chạy `not_evaluable`. Trên pilot chỉ 1/8
(DN, kỳ) có nhiều hơn một sổ (DN 9/2025, EPE + GC) và cả hai sổ đều vướng, nên coarsening này chưa
đổi kết quả nào. Nó thành rủi ro thật khi có pháp nhân nhiều sổ mà một sổ sạch.

## Sửa ngoài ticket (owner duyệt trong phiên)

T3 cho C4.3 nhường mã không có dòng M15 sang C4.1, nhưng C4.1 vẫn lọc `Norm.period_year == year`
nên không thấy mã có định mức kế thừa. Đo bằng chính code đã merge: **196 mã** không check nào báo
— 188 ở DN 8/2025, 8 ở DN 10/2026.

Phạm vi C4.1 thành HỢP của (mã khai đúng kỳ) và (mã có tiêu hao lý thuyết > 0 theo định mức hiệu
lực). Vẫn gắn với sản xuất trong kỳ — thành phẩm không có sản lượng thì không kéo NVL của nó vào,
nếu không C4.1 sẽ nhận mọi mã từng khai và không bao giờ nhả. Sau khi sửa: khoảng hở = 0, C4.1 đi
từ 36 lên 232 phát hiện trên 8 (DN, kỳ) pilot.

## Số đo trên pilot (06/08/2026, DB local, đọc read-only)

Cổng bật/tắt, C4.3 tính bằng code hiện tại:

| DN | kỳ | cổng | thiếu ĐM / TP có SX | C4.3 tắt cổng | bật cổng |
|---|---|---|---|---|---|
| 7 | 2025 | B | 0 / 56 | 13 | 0 |
| 8 | 2024 | A+B | 5 / 368 | 590 | 0 |
| 8 | 2025 | — | 0 / 373 | 1665 | **1665** |
| 9 | 2025 | A+B | 11 / 41 | 5 | 0 |
| 10 | 2023 | A+B | 13 / 61 | 7 | 0 |
| 10 | 2024 | A | 5 / 138 | 24 | 0 |
| 10 | 2025 | A | 15 / 215 | 115 | 0 |
| 10 | 2026 | A | 17 / 166 | 104 | 0 |

A = thiếu độ phủ định mức · B = kỳ biên chưa xác nhận năm đầu nộp BCQT. Cả 8 DN đều có
`first_bcqt_year = NULL`.

**Chỉ DN 8/2025 qua cả hai cổng** — đúng như dự đoán. Giữ 1.665/2.523 = 66%. Con số
1.772/3.296 = 54% ở ticket KHÔNG tái hiện, đúng như đã lường: nó đo TRƯỚC khi T3 và T4 lên, mà hai
cái đó đã dời mọi số đếm theo mã (10/2026 đi từ 568 xuống 104, 10/2024 từ 243 xuống 24).

## Không đạt được — và không thể đạt như ticket viết

**Mốc nghiệm thu của #62 "phát hiện biến mất KHÔNG làm điểm rủi ro giảm" là SAI về mặt số học.**

Loại một luật khỏi cả tử số lẫn trần kéo điểm về trung bình các luật còn lại. Điều kiện chính xác:

    điểm sau ≥ điểm trước  ⟺  rule_score(C4.3) ≤ 10 × raw / max_raw

nên cổng làm điểm GIẢM đúng khi C4.3 đang chấm cao hơn trung bình các luật còn lại. Trên pilot:
DN 7/2025 6→4 · DN 8/2024 129→**132** · DN 9/2025 28→27 · DN 10/2024 3→2 · DN 10/2025 3→1 ·
DN 10/2026 8→6. DN 10 có 16 luật khác gần như không bắn gì (`raw` = 0,486 trên trần 190), nên C4.3
đang gánh điểm; bỏ nó khỏi cả hai vế của một tỷ số là giảm.

Đây đúng là thứ cả loạt ticket sinh ra để chặn: thừa nhận không đánh giá được lại làm DN sạch hơn.
T2 không sửa được — T2 bảo đảm "not_evaluable == luật vắng mặt khỏi lần chạy", và nó giữ đúng lời.
Cái sai nằm ở chỗ điểm là một TRUNG BÌNH, nên không có cách nào loại một luật mà không dời trung
bình.

Ghi lại bằng `tests/test_checks/test_norm_gate.py::test_gate_does_not_lower_the_risk_score` đánh
`xfail(strict=True)`, reason mang đủ số đo — KHÔNG hạ assertion. Ai "sửa" điểm sau này thì test đó
đỏ ngay.

Cần một quyết định về thang điểm, ngoài phạm vi loạt ticket này → **đã tách thành
[issue #65](https://github.com/TinsuAI/audit-hq-mvp/issues/65)**, ba hướng nêu ở đó, chưa chọn.
Owner chốt trong phiên biện pháp giảm thiểu — giữ công thức, luôn hiện "Đã đánh giá N/M bài" cạnh
điểm, tách nhóm khi xếp hạng (quyết định (1) bên dưới). Đó là che chắn cách đọc sai, **không phải
lời giải**; #65 chặn việc dùng điểm rủi ro để xếp hạng DN cho tới khi chốt.

## Còn mở

- **Thang điểm khi có luật `not_evaluable` → [issue #65](https://github.com/TinsuAI/audit-hq-mvp/issues/65).**
  Tách ra khỏi #56, cần owner chốt. Ba hướng nêu ở đó, chưa chọn. **CHẶN việc dùng điểm rủi ro để
  xếp hạng DN.** Cũng ghi ở `.ai/BACKLOG.md` (trỏ về #65, không chép nội dung để khỏi lệch).
- ~~C4.9 ra 11 ở DN 9/2025 trong khi sổ yêu cầu ghi 9~~ — **đã giải quyết**, xem quyết định (3):
  11 = 9 thiếu hẳn + 2 khai ở sổ EPE. Hai con số hoá ra đếm cùng một thứ theo hai cách; màn hình
  nay nói rõ cái nào là cái nào, không cần ngoại lệ cho ADR #19.
- **Cổng review WS1 chưa bắn cho BCCT.** `review_state` trả `verified` cho mọi trường không có
  trong `CHECK_COLUMNS`, mà registry không có dòng BCCT nào. Cột `position-only` hiện badge nhưng
  file vẫn "Đã kiểm" và luồng nạp tự đi tiếp. Thêm BCCT vào `CHECK_COLUMNS` đổi vòng đời file cho
  mọi DN và mọi test đang nạp BCCT → việc riêng. Vế "đọc đúng cột" của dòng 0.2 đã xong, vế "cảnh
  báo tới cán bộ" chưa thông suốt.
- **HIEP_QUANG và HONG_AN chưa nạp.** Adapter đã sửa nên nạp được rồi; thứ tự bắt buộc (sửa adapter
  trước) đã thoả.
- **Provenance BCCT theo SLOT, không theo FILE.** Một kỳ có thể có nhiều file BCCT;
  `record_parse_result` giữ một `ParseProvenance` mỗi slot, hiện lấy file đầu tiên có cột
  `position-only`.
- **DB dev lệch schema.** `alembic current` fail: DB stamp `a9b0c1d2e3f4`, revision chỉ có trên
  nhánh chưa merge `feat/adr23-ktstq-period-scope`. `tests/test_smoke.py` bind vào DB đó nên suite
  đỏ ở máy dev cho tới khi migrate. Chạy sạch bằng
  `DATABASE_URL="sqlite:////<scratch>/x.sqlite" pytest`. Khi `feat/adr23-ktstq-period-scope` merge
  sẽ có hai alembic head, cần revision merge.
- **Bản vá tạm ở prompt tổng quan AI (ADR #18 `:513`) nay HẾT CHẶN.** Nó viết "KHÔNG khẳng định
  sạch từ mỗi con số 0 … tới khi Tầng C thêm `not_evaluable`". Tầng C đã có — gỡ được bản vá, và
  nên cho prompt đọc `not_evaluable` thay vì né mọi số 0.
- **Việc (a) của P-07 còn mở** — tách cột (6) khỏi (7) ở `extended_layout.py:381`. Chưa ra số sai
  vì DN 004 có khách trả lại = 0, là trùng hợp dữ liệu chứ không phải chốt chặn trong code.
- **Nhánh `fix/c43-multiplier-p07` và `fix/bcct-label-columns` đã cherry-pick vào nhánh này** —
  xoá được sau khi merge PR #64.

## Review hai trục (chạy trước khi kết phiên)

Trục **chuẩn mã nguồn** và trục **đúng đặc tả** chạy song song, độc lập context. Đã sửa theo:

- **C4.3 và C4.1 trong `catalog_full.py` + `registry.py` không mang ngữ nghĩa mới.** Trang
  `/danh-muc-kiem-tra` đọc thẳng `catalog_full`, nên bản mô tả cho cán bộ không hề nói C4.3 có thể
  bị cổng chặn trắng cả kỳ, cũng không nói phạm vi C4.1 đã mở. Đã bổ sung cả hai.
- **`check_runs.status_reason` lưu `str(exc)` của check mở rộng.** Lỗi SQLAlchemy nhúng cả câu lệnh
  lẫn tham số đã bind — tức giá trị dòng dữ liệu thật — và cột này hiện ra UI. Nay chỉ lưu LOẠI lỗi;
  nội dung đầy đủ vẫn ở log hệ thống (dòng log đó có từ trước nhánh này).
- **`⃠` (U+20E0) là dấu tổ hợp**, đứng một mình sẽ hiện thành vòng tròn chấm. Đổi sang `⊘` ở
  `run_checks.py` và `company_detail.html`.
- `"Số hóa đơn"` → `"Số hoá đơn"` cho khớp chính tả phần còn lại của repo.
- Dấu 🚧/✅ ở đề án nói kiểm tra vào ở GIAI ĐOẠN nào, không nói đã có mã nguồn chưa — C4.9 là 🚧 mà
  đã cài xong. Đã ghi rõ vào chú thích bảng trạng thái thay vì đổi con số "16 kiểm tra" (đó là phạm
  vi demo, không phải số đã triển khai).

Ghi nhận, chưa sửa:

- **`products_without_norm` coi định mức `norm_qty = 0` là ĐÃ khai**, còn `consumed_materials` đòi
  `> 0`. Cố ý: khai 0 vẫn là đã khai, độ phủ đạt; giá trị 0 là sai phạm riêng của C4.5 (chưa dựng).
  Gộp lại thì mã khai 0 bị chặn với lý do "thiếu định mức" — nói sai chuyện đang xảy ra. Đo pilot:
  **0 mã** rơi vào ca này, khác biệt chưa đổi kết quả nào. Đã ghi vào docstring.
- **Kỳ biên chỉ chặn C4.3, không chặn C4.9.** #61 đòi đúng các số 5/13/11 ở kỳ biên, mà Q1 lại nói
  ở kỳ biên không phân biệt được "chưa từng khai" với "đã khai trước cửa sổ dữ liệu". Hai ticket
  chọi nhau — **cần owner chốt**. Lý lẽ giữ nguyên hiện trạng: C4.9 phát biểu "chúng tôi không có
  định mức cho mã này", là mệnh đề về dữ liệu đang giữ, không phải cáo buộc; C4.3 mới là chỗ suy
  diễn nên mới cần cổng.
- **Đường mòn tính lại:** một lần chạy C4.3 + C4.9 gọi `effective_norms` / `production_intake` 4+
  lần qua `norm_coverage_gate` → `products_without_norm`. Đúng kết quả, phí công. Chưa tối ưu vì
  chưa đo thấy chậm.
- `key=lambda b: (b is None, b or "")` lặp ở 4 chỗ; `app/books.py` là chỗ ở tự nhiên của nó.

**Harness delta của #63:** delta = 0 theo cấu tạo — không nạp lại file nào, `declaration_lines`
không đổi một dòng, nên mọi phát hiện mức 3 giữ nguyên. Đo delta chỉ có nghĩa sau khi nạp
HIEP_QUANG và HONG_AN.

## Ba quyết định owner chốt cuối phiên (06/08) — đã cài xong

**1. Thang điểm: giữ nguyên công thức, nhưng điểm không bao giờ đứng một mình.**
`score_coverage(breakdown)` → `(số luật đã đánh giá, tổng số luật)`. Trang chi tiết DN hiện
"Đã đánh giá N/M kiểm tra" ngay cạnh điểm; danh sách DN có cột "Độ phủ". Xếp hạng **tách nhóm**:
DN có kỳ nào còn luật chưa đánh giá được thì xuống nhóm sau bất kể điểm — cả ở sort phía server
lẫn sort phía client khi bấm cột điểm. Độ phủ của DN lấy **kỳ xấu nhất**, không phải kỳ của điểm
max. `compute_company_year_score` lưu thêm `rule_count`: `max_raw` chỉ còn phần chấm được nên
không suy ngược ra mẫu số; breakdown cũ (chưa có trường này) vẫn đọc được bằng cách suy từ
`max_raw`, nếu không mọi kỳ cũ hiện độ phủ 0 và trông như chưa chạy kiểm tra.
KHÔNG đổi một dòng logic check nào. Test `xfail` vẫn nguyên — công thức không đổi thì tính chất
đó vẫn sai, và đó là điều cần giữ hiển thị.

**2. Kỳ biên: C4.9 vẫn liệt kê, gắn cờ cảnh báo.** C4.3 dừng hẳn ở kỳ biên, C4.9 thì không —
danh sách từng mã là thứ anh Dũng cần. Mỗi phát hiện mang `boundary_period`, nhãn
"Kỳ biên — có thể đã khai trước cửa sổ dữ liệu", để cán bộ đi hỏi hồ sơ kỳ trước thay vì kết luận
DN chưa khai. `is_boundary_period()` tách ra khỏi `norm_coverage_gate()` để hai check dùng chung
một định nghĩa.

**3. DN 9: định mức ở sổ khác thì nói đúng như vậy.** Hành vi KHÔNG đổi — định mức sổ EPE vẫn
không phủ sản lượng sổ GC (ADR #19), cổng vẫn bắn. Chỉ đổi câu chữ: mã có định mức ở sổ khác báo
"định mức M16 khai ở Sổ EPE (chế xuất)" kèm `evidence_refs` trỏ về dòng `norms` đó, thay vì
"không có định mức hiệu lực". Đo lại trên DN 9/2025: **11 phát hiện = 9 thiếu hẳn + 2 khai ở sổ
EPE** — khớp lại được với con số 9 trong sổ yêu cầu, và cán bộ không mất công đi đòi file đã nộp.

Suite sau ba việc này: **1027 pass + 1 xfail**.

## Ảnh E2E — và lỗi thứ hai nó bắt được

9 ảnh + `ui_smoke.py` + `brief.md` ở `.ai/features/2026-08-05-issue-56-data-completeness/`.
Smoke seed hai pháp nhân BỊA vào DB throwaway rồi **chạy thật `run_checks()`** — ảnh là kết
quả check, không phải `Finding` dựng tay. Không đụng DB live hay cổng 8200.

**Mẫu số `m16` = 0 khi DN không khai lại định mức.** Seed DN có định mức kế thừa (0 dòng
`norms` trong kỳ) ra **điểm 0** dù có phát hiện Nghiêm trọng. `_count_distinct_m16` đếm
`period_year == year`, mà T4 vừa làm C4.3 đánh giá được ở kỳ không có dòng nào → mẫu số 0 →
`compute_rule_score` trả 0 → mọi phát hiện C4.3 của kỳ đó rơi khỏi điểm. **DN ngừng khai lại
định mức thì điểm tự đẹp lên** — cùng một lớp lỗi với khoảng hở C4.1, ở chỗ khác. Sửa: đếm
theo định mức hiệu lực; điểm 0 → 50. Pilot đổi mẫu số ở 4/8 (DN, kỳ), **không kỳ nào rơi về
0** nên chỉ ca seed mới lộ ra — bài học: dữ liệu pilot không phủ hết ca biên, ca seed có giá
trị riêng.

Hai lỗi nhỏ ảnh cũng bắt: phụ đề bảng còn ghi "sắp xếp theo điểm rủi ro giảm dần" sau khi đã
tách nhóm; nhãn cột `boundary_period` dài gấp đôi các cột số.

## Từ ngữ: "Độ phủ" → "Đã đánh giá"

Owner phản hồi chữ "độ phủ" không rõ nghĩa. Đúng — đó là chữ của dân test, cán bộ đọc cột
không biết đang phủ cái gì. Hai màn hình nay nói cùng một câu: **"Đã đánh giá 17/18 bài kiểm
tra"**. Thêm ba lớp giải thích: `title` ở tiêu đề cột, `title` ở từng ô (nói luôn vì sao DN
đó xếp xuống nhóm sau), và một đoạn trong thẻ "Cách tính điểm rủi ro" đã có sẵn.

**Giữ "độ phủ định mức" trong code và tài liệu nghiệp vụ** — đó là tên cái CỔNG (thành phẩm
đã khai định mức chưa), khác hẳn chuyện chấm được bao nhiêu bài. Trộn hai thứ vào một chữ
mới là chỗ gây rối ban đầu.

Repo không có component tooltip, cả codebase dùng `title=` gốc trình duyệt → theo lối đó,
không dựng cơ chế mới.

**Hai test hỏng vì đoạn giải thích mới in "18/18" làm ví dụ** — chúng khẳng định
`"17/18" in r.text` trên TOÀN TRANG. Hỏng là đúng: kiểu khẳng định đó xanh giả, dòng dữ liệu
render rỗng vẫn qua. Sửa cả hai neo vào ô của từng dòng qua `_coverage_cells()`.
Cùng họ với [[test-false-green-ambient-db]].

## Push, PR, publish

- `feat/data-completeness-gate` push, **[PR #64](https://github.com/TinsuAI/audit-hq-mvp/pull/64)**
  mở, `Closes #57–#63`. **KHÔNG** đóng #56 — sổ yêu cầu còn 36 dòng ngoài phạm vi.
- **Ảnh không nhúng được vào mô tả PR.** Repo private, GitHub tải ảnh markdown của PR qua
  proxy camo, camo tải ẩn danh. Đo lại 06/08 trên đúng file: ẩn danh **404**, có token **200**.
  PR để gallery dạng LIÊN KẾT + trỏ `brief.md` (ở đó GitHub render bằng phiên người xem nên
  hiện inline). Muốn thumbnail thật trong PR thì phải kéo thả file vào comment — `gh` không
  có API upload attachment.
- Repo đề án push **6 commit** (5 + 1 phát sinh). Rà trước 2 commit có từ trước phiên
  (`f047b03`, `77f1117`): sạch, 4 file văn bản, không dữ liệu thật.
  **Phát sinh:** `de-an-audit-hq.html` là file SINH RA từ markdown qua `make html` và đã cũ —
  bản đang nằm trong repo (và đang được `make publish` đẩy lên web) vẫn ghi "49 kiểm tra",
  không có C4.9. Render lại → `8fba236`.
- `make publish` xong. Verify trên web thật, không chỉ tin exit code:
  `https://audit-hq.tinsu.ai/` trả 200, C4.9 xuất hiện 4 chỗ, "49 kiểm tra" hết, **md5 bản web
  = md5 file local**.

## Ghi chú kiểm chứng

`op.batch_alter_table(...).add_column()` **không** tái hiện lỗi trên schema này (alembic 1.18.5 /
SQLAlchemy 2.0.51 / SQLite 3.45.1): `recreate="auto"` phát `ALTER TABLE ADD COLUMN` native cho batch
chỉ có add-column, không dựng lại bảng. Cả hai migration vẫn dùng `op.add_column` thẳng theo ticket,
nhưng lý do ghi trong ghi chú cũ rộng hơn thứ đo được. `companies` là đích của FK từ **14** bảng,
không phải 6 như ticket #57 ghi.
