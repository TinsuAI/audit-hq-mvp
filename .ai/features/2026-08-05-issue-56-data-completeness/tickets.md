# Ticket — issue #56, cổng độ phủ định mức

Phạm vi chốt ở `yeu-cau.md` mục "Phạm vi issue #56". Quyết định Q1/Q2/Q3 ở `grill-state.md`.
Số đo dùng làm mốc nghiệm thu cũng ở `grill-state.md` — đo trên `audit_hq.sqlite` local 05/08/2026.

Bảy ticket đã mở trên GitHub, gắn làm sub-issue của #56, cạnh chặn khai bằng issue dependency của
GitHub (`blocked_by`) chứ không chỉ ghi trong văn bản. Ticket nào hết chặn thì làm được, không cần
chờ ticket cùng hàng.

| Ticket | Issue | Chặn bởi |
|---|---|---|
| T1 `companies.first_bcqt_year` | #57 | — |
| T2 `not_evaluable` trạng thái thật | #58 | — |
| T3 C4.3 bỏ qua mã không có dòng M15 | #59 | — |
| T4 Định mức hiệu lực | #60 | #59 |
| T5 Bảng thừa/thiếu định mức | #61 | #60 |
| T6 Cổng nhị phân C4.3 | #62 | #57, #58, #60 |
| T7 Mô hình bằng chứng WS1 cho BCCT | #63 | — |

```
#57 ─────────────────────────┐
#58 ─────────────────────────┤
                             ├──► #62
#59 ──► #60 ─┬───────────────┘
             └──► #61

#63  (rời — không chặn ai, không bị ai chặn)
```

#57, #58, #59, #63 không chặn bởi gì — làm song song được.

T1–T6 là cổng độ phủ định mức (mức 2 + mức 4 của sổ). T7 là mức 0 — đọc đúng cột BCCT. Hai việc
độc lập: mốc nghiệm thu T1–T6 tính từ `norms` / `sp_balances` / `nvl_balances`, T7 đụng
`declaration_lines`.

---

## T1 (#57) — `companies.first_bcqt_year`, cán bộ nhập

**Chặn bởi:** không

Thêm cột `first_bcqt_year: int | None` vào `companies` (migration `op.add_column` thẳng, KHÔNG
`batch_alter_table` — batch mode chết trên bảng là đích của FK, mà `companies` là đích của 6 FK).
Hiện trên form sửa DN (`app/routes/companies.py:429` `edit_company_form`, `:450` `update_company`).

Ngữ nghĩa ở GLOSSARY `:182-185`: năm đầu tiên DN nộp BCQT. KHÔNG suy được từ dữ liệu đã nạp — kỳ
sớm nhất trong hệ thống chỉ là biên của cửa sổ nạp. Để trống là hợp lệ và có nghĩa "chưa biết".

**Nghiệm thu:** test route lưu được giá trị và lưu được `None`; migration chạy trên DB có dữ liệu
mà không lỗi.

---

## T2 (#58) — `not_evaluable` thành trạng thái chạy thật

**Chặn bởi:** không

Cột `check_runs.status` đã dành sẵn giá trị này (`app/models/check_run.py:35`) nhưng chưa chỗ nào
ghi và chưa chỗ nào đọc. Ba việc:

1. `run_checks()` (`app/pipeline/run_checks.py:108-127`) — `run_status` hiện chỉ nhận `'ok'` /
   `'error'`. Cho phép check trả về trạng thái `not_evaluable` kèm lý do.
2. `compute_company_year_score()` (`app/checks/scoring.py`) — check ở trạng thái này KHÔNG tham gia
   điểm rủi ro, **cả phần cộng điểm lẫn phần trần** (GLOSSARY `:189-191`). Nếu chỉ bỏ phần cộng thì
   thiếu dữ liệu lại làm điểm đẹp lên.
3. UI — phân biệt "đã đánh giá, 0 phát hiện" với "chưa đánh giá được", kèm lý do.

**Nghiệm thu:** test chứng minh một check `not_evaluable` không làm đổi `CompanyYearScore.score`
lẫn `tier` so với khi check đó vắng mặt hoàn toàn.

---

## T3 (#59) — C4.3 bỏ qua mã NVL không có dòng M15

**Chặn bởi:** không · **Chặn:** #60

Việc (b) của P-07. Nhánh `fix/c43-multiplier-p07` (1 commit, chưa có PR) mới làm việc (a) —
đổi số nhân từ `SpBalance.export_qty` sang `intake_qty`.

Mã NVL có tiêu hao lý thuyết mà **không có dòng M15 nào** thì đó là đất của C4.1 ("NVL trong M16
không có nguồn trong M15"), không phải chênh lệch định mức. C4.3 phải bỏ qua, không được coi là
xuất SX = 0 rồi bắn Nghiêm trọng.

**Nghiệm thu (đứng một mình):** fixture có mã NVL xuất hiện trong M16 mà không có dòng M15 nào →
C4.3 không sinh phát hiện cho mã đó; mã có dòng M15 với xuất SX = 0 thì vẫn sinh.

**Nghiệm thu (sau khi T4 lên):** trên DN 8/2025, trong 236 mã lẽ ra bị đẩy lên Nghiêm trọng phải có
**151 mã không xuất hiện ở C4.3** và **53 mã ở lại** (có dòng M15 nhưng xuất SX = 0 — mâu thuẫn thật).

**Bắt buộc lên trước T4.** Q2 không có T3 thì đẻ ra 151 phát hiện Nghiêm trọng dán nhầm nhãn.

---

## T4 (#60) — Định mức hiệu lực: bản khai gần nhất ≤ kỳ

**Chặn bởi:** #59 · **Chặn:** #61, #62

Mẫu 16 kế thừa giữa các năm — DN chỉ khai lại khi định mức thay đổi (dòng 2.2, cả anh Dũng lẫn chị
Duyên đều nêu). C4.3 hiện lọc `Norm.period_year == year` (`app/checks/c4_norm.py:104-109`), nên mã
nào không khai lại thì mất định mức.

Viết helper trả về định mức hiệu lực cho `(DN, sổ, kỳ, mã SP, mã NVL)` = bản khai có
`period_year` lớn nhất mà `≤ year`. Gộp theo **sổ** — mỗi sổ quyết toán là ledger riêng (ADR #19).
C4.3 dùng helper thay cho truy vấn hiện tại.

**Nghiệm thu:** DN 8/2025 là chỗ duy nhất trong pilot có ca chuyển tiếp — 16 mã TP, 485 đơn vị sản
xuất, chạm 1.334 mã NVL. Sau T3+T4 phải thấy **321/8.144 mã đổi bậc** (236 lên Nghiêm trọng, 85 lên
Cảnh báo, **0 mã đi ngược**), trừ đi 151 mã T3 đã loại.

Luật này giải thích **0** cho DN 8/2024 và toàn bộ DN 10 — nó tách hai tình huống khác nhau, không
phải luật làm mọi thứ biến mất.

---

## T5 (#61) — Bảng thừa/thiếu định mức

**Chặn bởi:** #60 · **và một quyết định của owner**

**Chưa có mã catalog.** Đây là check MỚI chiều M15a → M16 (có sản xuất mà thiếu định mức). Catalog
49 không có mã cho chiều này: `C4.2` là chiều ngược lại (`app/catalog_full.py:183-188`,
`../audit-hq/de-an-audit-hq.md:227`), `C4.1` là M16 → M15. `CLAUDE.md` cấm sửa catalog ở repo này
trước khi sửa repo đề án. Owner chốt mã rồi thêm mục vào `../audit-hq/de-an-audit-hq.md` trước.

Dòng 2.1, anh Dũng gọi là cốt lõi: **liệt kê mã thành phẩm thiếu định mức, không chỉ báo tổng**.

Check mới: mã TP có sản lượng sản xuất trong kỳ (`SpBalance.intake_qty > 0`) mà không có định mức
hiệu lực (theo helper T4) → một phát hiện mỗi mã, `evidence_refs` trỏ về dòng `sp_balances`.

**Nghiệm thu:** số mã thiếu ĐM hiệu lực phải khớp cột cuối bảng `grill-state.md` —
DN 8/2024: 5 · DN 9/2025: 9 · DN 10/2023: 13 · DN 10/2024: 5 · DN 10/2025: 15 · DN 10/2026: 17 ·
DN 7/2025: 0 · **DN 8/2025: 0** (16 mã thiếu ĐM cùng kỳ đều có ĐM kỳ trước — đây là test chứng minh
T4 đã ăn vào).

---

## T6 (#62) — Cổng nhị phân trên C4.3

**Chặn bởi:** #57, #58, #60

Q3: có mã TP nào sản xuất trong kỳ mà **chưa từng khai định mức ở bất kỳ kỳ nào** (kể cả các năm
trước) → C4.3 trả `not_evaluable` cho cả (DN, kỳ, sổ). Cổng là **nhị phân**, không ngưỡng phần
trăm, không cân theo tỷ trọng sản lượng — đề xuất ngưỡng 5% đã bị bác.

Chặn cả nhóm chứ không nhiễm theo mã: thành phẩm chưa khai ĐM thì không biết nó ăn NVL nào, không
khoanh được vùng ảnh hưởng.

Q1: kỳ sớm nhất của mỗi DN mặc định `not_evaluable`, trừ khi `companies.first_bcqt_year` (T1) xác
nhận đó đúng là năm đầu nộp BCQT. Không phân biệt được "chưa từng khai" với "đã khai trước cửa sổ
dữ liệu mình có".

**Nghiệm thu:** trên pilot, C4.3 chỉ chạy ở **DN 8/2025**, còn **1.772/3.296 = 54%** phát hiện.
DN 7/2025, 8/2024, 9/2025, 10/2023 là kỳ biên → chưa đánh giá. DN 10/2024, 10/2025, 10/2026 bị cổng
chặn (5, 15, 17 mã chưa từng khai). Kèm test chứng minh 1.524 phát hiện biến mất KHÔNG làm điểm rủi
ro của DN 10 giảm — đó là điều T2 phải bảo đảm.

---

## T7 (#63) — Mô hình bằng chứng WS1 cho BCCT

**Chặn bởi:** không · **Chặn:** không

Dòng 0.2 của sổ. Adapter BCCT ánh xạ cột theo vị trí cố định (`_COL`, `app/adapters/bcct.py:60-77`);
file có bố cục khác thì mọi trường rơi vào cột khác, parse vẫn "thành công", không ngoại lệ nào
phát ra. Đo trên 38 file BCCT trong `data/`: **35 khớp `_COL`, 3 lệch** — HIEP_QUANG 2021 NK/XK
(50 cột, 16 trường) và HONG_AN 2025 XK `__dup1` (55 cột, 11 trường).

Code đã có một phần ở nhánh `fix/bcct-label-columns` commit `06a9db5` — chưa test, chưa push.

Việc: dùng `norm()` (`app/adapters/layout.py:77-86`) thay `strip().lower()`; `BcctFile` mang
`ParseProvenance` với nhãn `header-matched` / `position-only`; từ chối parse khi ba trường bắt buộc
không resolve được theo cả nhãn lẫn vị trí (tiền lệ `IngestPlanError`); kiểm đơn ánh cột.

**Nghiệm thu:** ba fixture — HIEP_QUANG 50 cột, HONG_AN 55 cột, và một file chuẩn 54 cột khẳng định
map theo nhãn **bằng đúng `_COL`** ở cả 19 trường (chống hồi quy trên 8 DN đã verify).

**Thứ tự bắt buộc:** sửa adapter TRƯỚC, nạp HIEP_QUANG và HONG_AN SAU. Dòng đã nạp không tự đổi khi
luật dò cột đổi. DB hiện sạch — hai DN đó chưa nạp, `saved_column_maps` rỗng.

---

## Không nằm trong loạt này

- **H1** — nhiễm theo mã hay chặn cả mức, cho các mức khác ngoài độ phủ định mức. Q3 đã chốt riêng
  cho cổng này. Chốt H1 khi nào cần cổng thứ hai.
- **Đ.1** — 6 check bắn 0 phát hiện. Việc điều tra riêng, không chặn loạt này.

*(H2 — từ chối tiếp nhận file sai mẫu — đã gỡ, xem `grill-state.md`. Dòng 0.1 và 0.2 nói hai điều
kiện khác nhau, cả hai đều áp dụng.)*
