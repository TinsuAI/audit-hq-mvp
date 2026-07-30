# Đề xuất ADR #22 — Thang điểm rủi ro 0–1000 (2026-07-30)

**Trạng thái:** Đề xuất, chờ owner chốt. Chưa được cài đặt — tài liệu này KHÔNG đổi code.

**Nguồn phát sinh:** `.ai/STATUS.md` block 2026-07-29 ("4 vòng prototype dashboard"), mục
(1) trong "PHÁT HIỆN ĐÃ KIỂM CHỨNG". Session gốc: `.ai/sessions/2026-07-29-dashboard-ux-prototype.md`.

**Phạm vi:** Chỉ thang điểm 0–1000 hiển thị cho cán bộ (đâu, tính sao, hạng nào). KHÔNG xử lý
hai phát hiện khác cùng session (subject_key duy nhất; C1.6 ⊃ C1.7 không độc lập) — để ADR riêng.

---

## 1. Bối cảnh

`app/checks/scoring.py:compute_company_year_score` (dòng 128–196) gộp điểm 17 bài kiểm tra
built-in (`RULE_SCOPE`, `app/checks/denominators.py:25-40`) thành một số 0–1000:

```
raw     = Σ rule_scores (mỗi rule tối đa MAX_RULE_SCORE=10, scoring.py:34) + combo_bonus (20, :31)
max_raw = len(rule_scope) × 10 + 20                                        (:183, hiện = 17×10+20 = 190)
score   = round(1000 × raw / max_raw)                                      (:185)
```

`max_raw=190` là trần chỉ đạt được nếu **cả 17 bài kiểm tra đồng thời kịch khung** (100% mã bị
gắn nghiêm trọng ở tất cả 17 chiều kiểm tra cùng lúc). Dữ liệu thật ở dưới cho thấy trần này
không bao giờ đến gần: điểm thô cao nhất từng đo được là 24,519/190 = **12,9% trần**, ứng với
1 pháp nhân có 9.963 phát hiện nghiêm trọng nhưng nhãn hiển thị "Có chênh lệch nhỏ".

Điểm này **hiện đang hiển thị** ở 3 màn hình cán bộ (`companies_list.html`, `company_detail.html`,
`company_documents.html`) và **được đưa vào báo cáo AI + chat** — tức là chỉ thị "không được đưa
điểm lên bất kỳ màn nào" trong STATUS.md 2026-07-29 **chưa được thực thi trong code hiện tại**.
Xem mục 6.0 để danh sách các nơi đang lộ.

---

## 2. Hiện trạng đo được

Đo read-only trên `audit_hq.sqlite` (snapshot 2026-07-30, `mode=ro`, không ghi). 3 pháp nhân,
4 dòng `(company, period_year)` trong `company_year_scores` (id 14–17). `check_definitions` chỉ có
1 dòng `X.1` ở trạng thái `draft` (chưa `published`) → `extended_rule_scope()`
(`app/checks/denominators.py:126-142`) hiện **không thêm rule nào** ngoài 17 built-in, nên
`max_raw = 190` cho cả 4 dòng đang xét.

### 2.1 Điểm hiển thị và raw đứng sau nó

Nguồn: cột `score`, `tier`, cột JSON `breakdown` của bảng `company_year_scores` (4/4 dòng).

| Pháp nhân / năm | raw | max_raw | combo_bonus | score (0–1000) | Hạng hiện tại |
|---|---:|---:|---:|---:|---|
| PILOT_002 / 2025 | 1,288 | 190 | 0 | **7** | Dữ liệu nhất quán |
| PILOT_004 / 2025 | 5,745 | 190 | 0 | **30** | Dữ liệu nhất quán |
| PILOT_006 / 2024 | 24,519 | 190 | 20 (COMBO_HS_GAMING ×28) | **129** | Cần rà soát |
| PILOT_006 / 2025 | 10,339 | 190 | 0 | **54** | Có chênh lệch nhỏ |

Công thức khớp đúng 4/4: `round(1000×raw/190)` cho ra đúng score đã lưu (vd 1000×24,519/190 =
129,05 → 129). Số rule có điểm > 0 (tức có ≥1 phát hiện, nguồn: khoá `rule_scores` trong
`breakdown`, đối chiếu bằng `COUNT(DISTINCT check_code)` trên `findings`): 5, 10, 10, 11 — **tối
đa từng đạt là 11/17 rule**, chưa từng chạm 17.

### 2.2 Số phát hiện đứng sau raw (mẫu số: đếm `findings` không `rejected`, không `COMBO_*`)

Nguồn: `SELECT severity, COUNT(*) FROM findings WHERE company_id=? AND period_year=? AND
status!='rejected' AND check_code NOT LIKE 'COMBO_%' GROUP BY severity`. Hiện DB có **0 dòng
`status='rejected'`** nên số này trùng với tổng không lọc status.

| Pháp nhân / năm | Nghiêm trọng | Cảnh báo | Thông tin | Tổng (không COMBO) | Denominator (nvl / tp / m16) |
|---|---:|---:|---:|---:|---|
| PILOT_002 / 2025 | 25 | 22 | 1 | 48 | 286 / 77 / 205 |
| PILOT_004 / 2025 | 61 | 7 | 6 | 74 | 127 / 43 / 90 |
| PILOT_006 / 2024 | 3.147 | 394 | 311 | 3.852 | 7.885 / 437 / 5.790 |
| PILOT_006 / 2025 | **9.963** | 904 | 129 | 10.996 | 10.572 / 504 / 8.165 |

`denominator` = số mã NVL/TP/dòng M16 distinct của (DN, năm) — mẫu số dùng để tính rate mỗi rule
(`compute_denominators`, `app/checks/denominators.py`). PILOT_006 có denominator nvl lớn gấp
~37–83 lần PILOT_002/PILOT_004 — bối cảnh cho mục 3, phương án B.

**Điểm nóng của mục 1**: PILOT_006/2025 có 9.963 phát hiện nghiêm trọng (không lọc trạng thái, không
đếm combo) nhưng `score=54` → nhãn "Có chênh lệch nhỏ". Đây chính là ca cụ thể ghi trong STATUS.md.

### 2.3 Rule đóng góp nhiều nhất (nguồn: `rule_scores` trong `breakdown`, đơn vị 0–10/rule)

| Pháp nhân / năm | Rule cao nhất | Điểm rule (/10) | Số rule có điểm >0 |
|---|---|---:|---:|
| PILOT_002 / 2025 | C4.3 | 0,634 | 5 / 17 |
| PILOT_004 / 2025 | C1.1 | 1,858 | 10 / 17 |
| PILOT_006 / 2024 | C1.6 | 2,105 | 10 / 17 |
| PILOT_006 / 2025 | C1.6 | 5,472 | 11 / 17 |

Không rule đơn lẻ nào từng đạt điểm tối đa 10/10 (rate 100%) — rule cao nhất từng đo là C1.6 ở
PILOT_006/2025 = 5,472/10, tức rate 54,72%.

### 2.4 Xác minh hai khẳng định trong bối cảnh giao việc

**(a) `app/routes/companies.py:192-200` đọc `MAX(company_year_scores.score)` thay vì
`company.risk_score` — ĐÚNG, có chủ đích.** Comment tại chỗ (`:192-194`) nêu lý do: cache
`company.risk_score` có thể "drift" khỏi điểm theo năm khi đổi rule hoặc chạy lẻ không recompute.
Đối chiếu số: hiện tại `company.risk_score` (bảng `companies`) = 7 / 129 / 30 cho 3 DN, khớp đúng
`MAX(company_year_scores.score)` tính tươi — **không lệch ở snapshot này**, nhưng cơ chế gây lệch
là có thật (xem (b)).

**(b) "Cache chỉ tăng dần" — SAI, đã kiểm chứng bằng đọc code, không phải giả định.**
`app/pipeline/run_checks.py:187-192` và `app/pipeline/recompute.py:53-59` đều gán
`company.risk_score = max(all_scores)`, nhưng đây là max tại **thời điểm gọi**, trên tập điểm mà
dòng của (DN, năm) vừa được ghi đè trực tiếp (`existing.score = year_score`, `run_checks.py:183`
và `recompute.py:48` — không có bảo vệ "chỉ tăng"). Hai đường khiến điểm 1 năm cụ thể **giảm**:
  1. Cán bộ đánh dấu 1 phát hiện "Loại trừ" (`rejected`) → `companies.py:2429` gọi
     `recompute_company_year` → điểm năm đó tính lại thấp hơn ngay lập tức.
  2. Thêm 1 check vào catalog (`RULE_SCOPE` hoặc publish 1 check X.*) → `max_raw` tăng → lần
     `run_checks` kế tiếp, MỌI DN đã chạy trước đó tụt điểm dù dữ liệu không đổi (số liệu minh hoạ
     ở mục 3, phương án A).
Vậy "chỉ tăng" không phải bất biến của hệ thống — nó chỉ đúng NGẪU NHIÊN khi không ai reject phát
hiện và catalog không đổi. `company.risk_score` là ảnh chụp tại lần recompute gần nhất của TỪNG
năm, có thể cũ (drift) với các năm chưa recompute lại — đúng như comment ở (a) đã cảnh báo.

---

## 3. Các phương án và hệ quả số (tính lại trên đúng 4 dòng ở mục 2.1)

### Phương án A — Chuẩn hoá theo giá trị lớn nhất **đã quan sát** thay vì trần lý thuyết

Công thức: `max_raw_mới = max(raw đã ghi nhận qua mọi (DN, năm))`. Hiện tại `max_raw_mới = 24,519`
(PILOT_006/2024).

| Pháp nhân / năm | raw | score hiện tại | score theo A |
|---|---:|---:|---:|
| PILOT_002 / 2025 | 1,288 | 7 | 53 |
| PILOT_004 / 2025 | 5,745 | 30 | 234 |
| PILOT_006 / 2024 | 24,519 | 129 | 1000 |
| PILOT_006 / 2025 | 10,339 | 54 | 422 |

**Thất bại đã tái hiện bằng số thật:** giả lập PILOT_006/2024 được rà soát và raw giảm còn 8,0
(một tình huống hợp lý — DN đó loại trừ bớt phát hiện sai). Kỷ lục quan sát dời sang PILOT_006/2025
(10,339). Recompute lại toàn bộ theo mẫu số mới:

| Pháp nhân / năm | raw (không đổi) | score cũ (A, mẫu số 24,519) | score mới (A, mẫu số 10,339) |
|---|---:|---:|---:|
| PILOT_002 / 2025 | 1,288 | 53 | **125** |
| PILOT_004 / 2025 | 5,745 | 234 | **556** |
| PILOT_006 / 2024 | 8,0 (giả lập) | — | 774 |
| PILOT_006 / 2025 | 10,339 | 422 | 1000 |

PILOT_002 nhảy từ 53 lên 125 (gần gấp 2,4 lần) **mà không ai đụng tới dữ liệu của PILOT_002**, chỉ
vì một DN khác được sửa. Đây đúng thất bại "mẫu số dời làm điểm hôm qua không so được với hôm nay"
— còn nặng hơn lỗi hiện tại, vì mẫu số giờ phụ thuộc **dữ liệu của DN khác**, không chỉ phụ thuộc
số lượng check trong catalog. Khi thêm 1 DN mới có raw cao hơn kỷ lục cũ, toàn bộ điểm các DN khác
cũng dời lại tương tự. **Loại.**

### Phương án B — Bỏ thang 0–1000, báo cáo trực tiếp số phát hiện theo mức độ

Cơ chế đã có sẵn, không cần code mới cho phần thay thế: `companies.py:203-211` đã tính
`counts[year][severity]`; `company_detail.html:93-104` đã có 3 thẻ Nghiêm trọng/Cảnh báo/Thông tin
độc lập với thẻ điểm; `companies_list.html:126-144` đã có "year-chips" 3 chấm màu theo năm. Bỏ thẻ
điểm + cột điểm là đủ, không cần dựng UI mới.

Số liệu 4 dòng dưới cơ chế này = đúng bảng mục 2.2 (25 / 61 / 3.147 / 9.963 nghiêm trọng).

**Thất bại:** đếm thô mang thiên lệch quy mô — chính lý do rate-based scoring được xây (docstring
`scoring.py:3-6`: "LEGACY (linear sum)... bị volume bias, DN nhiều mã → cao điểm tự động"). PILOT_006
có denominator nvl (10.572) gấp ~37–83 lần PILOT_002/PILOT_004, nên 9.963 so với 25 không có nghĩa
"tệ hơn 400 lần" — không dùng số đếm thô để **xếp hạng chéo DN**.

**Ổn định dưới cả hai thất bại đề bài nêu:** thêm 1 DN mới không đổi số đã hiển thị của DN khác
(đếm theo (DN, năm) độc lập). Thêm/bớt 1 check chỉ thêm/bớt đúng 1 dòng đếm của DN đó, không đổi ý
nghĩa các dòng khác — khác hẳn phương án A và công thức hiện tại.

**Không mất phần đã đúng:** tỷ lệ theo rule (`compute_rule_score`, đã chống thiên lệch quy mô đúng
cách bằng denominator riêng từng DN) vẫn giữ nguyên trong `breakdown`, chỉ ngừng gộp thành 1 số.

**Cái giá:** mất 1 khoá để SẮP XẾP trang danh sách DN theo "độ nghiêm trọng". Cần khoá thay thế
(mục 6, câu hỏi mở #1).

### Phương án C — Giữ công thức, hiệu chỉnh lại 5 ngưỡng hạng

`/admin/risk-tiers` đã có UI runtime chỉnh 5 ngưỡng (`app_settings.py:22`
`DEFAULT_RISK_TIER_UPPERS=(50,100,300,600,1000)`; ràng buộc: 5 số tăng dần, dương, số cuối=1000 —
`app_settings.py:107-117`) — hiệu chỉnh không cần deploy code.

Thử ngưỡng `(10, 25, 40, 80, 1000)`:

| Pháp nhân / năm | score | Hạng mặc định (50/100/300/600/1000) | Hạng theo ngưỡng mới (10/25/40/80/1000) |
|---|---:|---|---|
| PILOT_002 / 2025 | 7 | Dữ liệu nhất quán | Dữ liệu nhất quán |
| PILOT_004 / 2025 | 30 | Dữ liệu nhất quán | Cần rà soát |
| PILOT_006 / 2025 | 54 | Có chênh lệch nhỏ | Có dấu hiệu bất thường |
| PILOT_006 / 2024 | 129 | Cần rà soát | Bất thường nghiêm trọng |

Nhãn đúng hơn hẳn cho 3/4 dòng. Nhưng:

1. **Nội suy qua đúng 4 điểm dữ liệu** — không có căn cứ thống kê, chỉ khớp vừa vặn với 4 dòng
   đang có. Đề án dự kiến mở rộng ra 6 DN thật (`CLAUDE.md`); thêm 2 DN sẽ đổi phân bố, ngưỡng lại
   phải chỉnh tiếp — về bản chất là phiên bản khác của thất bại "mẫu số dời" ở phương án A, chỉ là
   mẫu số ở đây là ngưỡng NHÃN thay vì công thức TÍNH.
2. **Không sửa nguyên nhân gốc**: `max_raw=190` vẫn là trần không đạt được. Raw cao nhất từng đo
   (24,519) chỉ bằng 12,9% trần; dải điểm 150–1000 (85% thang) gần như không thể chạm tới với công
   thức hiện tại. Nhãn đúng nhưng con số đi kèm ("54/1000") vẫn đọc như "5,4%" — vẫn gây hiểu lầm
   "gần như sạch" bất kể màu nhãn nói khác, vì UI hiện tại in số VÀ nhãn cạnh nhau
   (`company_detail.html:86-87`: `{{ ys_score }}<span class="stat-unit">/1000</span>` + `tier-label`).
3. **Không tự dời theo khi catalog đổi**: minh hoạ bằng số thật — thêm 1 check vào `RULE_SCOPE`
   (17→18 rule, `max_raw` 190→200), giữ nguyên raw, recompute: PILOT_006/2024 129→123,
   PILOT_006/2025 54→52, PILOT_004 30→29, PILOT_002 7→6 — **mọi DN tụt điểm dù không ai đụng dữ
   liệu**, và ngưỡng cắt tuyệt đối (vd 80) không tự dời theo, phải rà thủ công lại mỗi lần đổi số
   check trong catalog — chi phí bảo trì lặp lại vô thời hạn.

Rẻ để thử (không cần deploy), nhưng là băng cứu triệu chứng (nhãn sai) chứ không phải nguyên nhân
(trần không đạt được + con số hiển thị cạnh nhãn vẫn gây hiểu lầm).

---

## 4. Khuyến nghị

**Chọn Phương án B: bỏ điểm gộp 0–1000 khỏi mọi màn hình/báo cáo/chat cán bộ; thay bằng số phát
hiện theo mức độ (Nghiêm trọng/Cảnh báo/Thông tin) đã có sẵn theo (DN, năm), có ghi rõ đây là số
đếm thô, không so sánh chéo giữa các DN khác quy mô.**

Lý do, theo đúng hai phép thử đề bài nêu (thêm DN mới, thêm/bớt check):

1. **B là phương án duy nhất trong 3 phương án ổn định dưới cả hai phép thử**, bằng chứng số thật
   ở mục 3: A thất bại nặng khi mẫu số dời theo dữ liệu DN khác (PILOT_002 nhảy 53→125 do sửa DN
   khác); C thất bại khi catalog đổi (mọi DN tụt điểm đồng loạt dù dữ liệu không đổi) và cần rà lại
   ngưỡng thủ công vô thời hạn khi thêm DN thật thứ 4–6.
2. **Chi phí cài đặt thấp nhất**: cả hai khối hiển thị thay thế (severity_totals, year-chips) đã
   tồn tại và đang chạy song song với thẻ điểm — chỉ cần gỡ khối điểm, không cần dựng UI mới.
3. **B loại bỏ đúng rủi ro pháp lý đang treo**: `scoring.py` tự ghi rõ (dòng 11-12) "5 hạng là chỉ
   số rủi ro dữ liệu, KHÔNG PHẢI đánh giá tuân thủ pháp luật theo TT 81/2019" — nhưng khi số 54/1000
   đứng cạnh nhãn "Có chênh lệch nhỏ" trong khi có 9.963 phát hiện nghiêm trọng, cán bộ đọc số
   trước, đọc nhãn sau, và số đang nói ngược với thực tế dữ liệu. C giữ nguyên đúng cặp (số, nhãn)
   gây hiểu lầm này, chỉ sửa nhãn.
4. **Không mất phần công thức đã đúng**: `compute_rule_score` (rate mỗi rule, đã chống thiên lệch
   quy mô bằng denominator riêng từng DN) không sai và không cần sửa — chỉ ngừng gộp 17 rule thành
   1 số theo trần không đạt được.

**Đánh đổi phải chấp nhận:** trang danh sách DN mất khoá sắp xếp "độ nghiêm trọng" bằng 1 số duy
nhất; cần khoá thay thế (câu hỏi mở #1, mục 6).

---

## 5. Việc phải làm nếu chốt Phương án B

### 5.0 Khẩn cấp — dừng đúng phần đang vi phạm chỉ thị "không đưa điểm lên màn nào" (STATUS.md
2026-07-29), độc lập với việc B có được chốt lâu dài hay không

Điểm/hạng **đang hiển thị thật** ở các vị trí sau — cần ẩn trước, bất kể phương án cuối cùng:

- `app/templates/companies_list.html:91` (cột "Điểm rủi ro dữ liệu (0-1000)"), `:103-105`
  (`tier_css`/`tier_label`), `:107,114-115` (score-pill/tier-pill).
- `app/templates/company_detail.html:11-13` (`ys_score`/`ys_tier`/`ys_css`), `:80-92` (thẻ
  "Rủi ro dữ liệu ... /1000"), `:107` đến `</details>` (khối giải thích công thức).
- `app/templates/company_documents.html:63` (badge "Rủi ro {{ yr.score }}/1000").
- `app/ai/sql_tool.py:99-105` — view SQL `v_company_scores` cho `query_sql` của AI chat có cột
  `overall_risk_score`, `score`, `tier` — cán bộ có thể tự query ra số này qua chat dù UI đã ẩn.
- `app/ai/system_prompt.py:88` — mục 2 của "Template báo cáo rủi ro" yêu cầu AI viết "Điểm rủi ro
  — điểm + hạng năm đó" vào MỌI báo cáo AI sinh ra cho cán bộ.
- `app/ai/tools.py:394` (`company_risk_score` trong tool trả finding), `:548` (`ORDER BY
  Company.risk_score.desc()` — dùng điểm để xếp hạng trong tool chat), `:567`, `:717-790`
  (`_explain_score` — tool trả nguyên `breakdown` gồm score/tier cho LLM diễn giải cho cán bộ).
- `app/pipeline/export.py:85` — dòng `("Điểm rủi ro DN", company.risk_score)` trong file Excel
  xuất cho khách/cán bộ.

### 5.1 Nếu B được chốt lâu dài — dọn theo hướng B

- `app/routes/companies.py:217` — bỏ `summary.sort(key=lambda s: (-s["score"], s["company"].code))`,
  thay bằng khoá đã chốt ở câu hỏi mở #1.
- `app/templates/companies_list.html:113` (rank badge gắn với thứ hạng theo score) — đổi ý nghĩa
  "Hạng" theo khoá sort mới hoặc bỏ cột.
- `app/templates/companies_list.html:211,255` (JS sort theo `'score'`) — đổi theo khoá mới.
- `app/templates/companies_list.html:158-165` (link "Xem cách tính điểm" → `/tai-lieu/scoring-methodology`)
  — nội dung trang đó mô tả đúng công thức đang bỏ, cần viết lại hoặc gỡ link.
- `app/ai/system_prompt.py:88` — sửa hướng dẫn báo cáo AI: thay mục 2 bằng "Phát hiện theo mức độ
  (nghiêm trọng/cảnh báo/thông tin theo (DN, năm)), nêu rõ là số đếm thô, không so sánh chéo DN
  khác quy mô".

### 5.2 KHÔNG bắt buộc đổi ngay — giữ backend nguyên trạng

- `app/checks/scoring.py` — giữ nguyên toàn bộ, kể cả `compute_company_year_score`/`tier_for`.
  Vẫn đúng vai trò tính `breakdown` làm dữ liệu chẩn đoán nội bộ (đội kỹ thuật audit công thức).
- `app/models/score.py` (`CompanyYearScore.score`/`tier`), `app/models/company.py:20`
  (`risk_score`) — giữ cột, giữ ghi nhận mỗi lần `run_checks`/`recompute_company_year`. Không cần
  migration.
- `app/routes/admin_risk_tiers.py`, `app_settings.py` (5 ngưỡng) — trang mất tác dụng thực tế khi
  không còn hiển thị hạng ở đâu cho cán bộ. Đề xuất tắt route (hoặc ẩn khỏi menu admin) thay vì
  xoá code, chờ câu hỏi mở #2.
- `app/jobs/handlers.py:53,76,86,91,97`, `app/jobs/result_labels.py:31` — payload job giữ
  `risk_score` (dữ liệu nội bộ, không phải màn cán bộ đọc trực tiếp) — nhưng STATUS.md 2026-07-27
  đã ghi nhận "trang công việc vẫn in JSON thô": nếu đúng, payload này lộ ra màn đó qua đường khác —
  cần xác minh riêng, không giả định đã an toàn chỉ vì không phải màn hình chính.

---

## 6. Câu hỏi còn mở cho owner

1. **Khoá sắp xếp mặc định cho trang danh sách DN** thay `-score`: mã DN (alphabet, trung tính,
   đang là khoá phụ hiện tại) hay một khoá khác (vd số phát hiện nghiêm trọng năm gần nhất, dù biết
   thiên lệch quy mô và phải ghi rõ giới hạn đó ngay trên UI)? Đây là quyết định UX, không phải kỹ
   thuật, cần owner chốt.
2. **`/admin/risk-tiers`** — tắt hẳn, hay giữ cho một mục đích nội bộ khác (vd ngưỡng cảnh báo kỹ
   thuật, không hiển thị cán bộ)?
3. **`_explain_score`** (`ai/tools.py:753-790`) và trang `/tai-lieu/scoring-methodology` — giữ làm
   công cụ nội bộ cho đội kỹ thuật audit lại công thức, hay gỡ hẳn cùng đợt với B?
4. **Nhu cầu xếp hạng nhiều DN cùng lúc** có thật không? MVP hiện có 3/6 DN thật (theo lộ trình
   `CLAUDE.md`) — đủ nhỏ để cán bộ tự đọc từng dòng Nghiêm trọng/Cảnh báo/Thông tin mà không cần
   máy xếp hạng hộ, hay cần một ADR riêng để thiết kế lại phần tổng hợp đa-rule thành 1 tín hiệu
   xếp hạng đúng cách (vd dựa trên rule cao nhất thay vì tổng 17 rule, mục 2.3 cho thấy rule cao
   nhất từng đo là C1.6=5,472/10 — một tín hiệu đơn giản hơn, nhưng đó là thiết kế mới, ngoài phạm
   vi ADR này)?
5. **Xác nhận phạm vi**: ADR này chỉ xử lý HIỂN THỊ điểm 0–1000. Hai phát hiện khác cùng session
   2026-07-29 (mọi finding có `subject_key` duy nhất; C1.6 ⊃ C1.7 không độc lập cấu trúc) cố tình
   để ngoài — đúng không, hay owner muốn gộp chung một đợt quyết định?
