# Ghi chú kỹ thuật — issue #56

> **File này KHÔNG còn là feature brief.** Bản brief cũ (scope / decisions / kế hoạch 3 slice) đã
> lỗi thời từ khi owner chốt bản đồ mức. Nội dung của nó đã tách ra:
> - **Làm gì** → `yeu-cau.md` (29 yêu cầu, gộp 3 tài liệu, xếp theo mức)
> - **Chốt gì + bằng chứng** → `grill-state.md`
>
> Còn lại ở đây là **sự thật về code** — thứ tốn công tìm và dễ vấp lại. Không có quyết định nào
> trong file này.

## Nhánh chưa merge liên quan trực tiếp

`fix/c43-multiplier-p07`, commit `4bf5333` (cũng nằm trên `integration/2026-07-30`, **không** trên
`main`). Đổi số nhân C4.3 `SpBalance.export_qty` → `intake_qty` tại `c4_norm.py:110`.

P-07 chốt BA việc code, nhánh mới làm việc thứ nhất. Hai việc còn dở:

**(a) Tách cột (6) khỏi (7) ở `app/adapters/extended_layout.py:381`.**
```python
"intake_qty": [c for c in plus_cols if c not in opening],
```
Gom MỌI cột cộng không phải tồn đầu kỳ. Với biểu tách riêng, nhóm cộng gồm cả lượng sản xuất nhập
kho lẫn lượng khách trả lại → số nhân đang là *sản xuất + khách trả lại*. Hôm nay chưa ra số sai vì
004 có khách trả lại = 0 — trùng hợp dữ liệu, không phải chốt chặn trong code.

> **Bẫy đánh số:** đề án gọi khách trả lại là "(7)", nhưng trong bố cục thật cột đó mang token
> `(6b)` nằm trong nhóm cộng `(6ab)`, còn token `(7)` là một khoản TRỪ khác. Lọc theo tên "(7)" là
> loại nhầm cột. Fixture: `tests/test_m15a_extended.py`.

**(b) Mã không có dòng M15 thì nhường C4.1.** Trong `check_c4_3`:
```python
m15 = m15_rows.get(code)
actual = (m15.production_out_qty or 0.0) if m15 else 0.0
if actual <= 0:
    pct = 100.0          # → Nghiêm trọng
```
`m15 is None` → `actual = 0` → gán thẳng 100% → Nghiêm trọng. Nhưng "NVL trong M16 không có dòng
M15" đúng là định nghĩa C4.1. Xem `grill-state.md` cho con số 151.

**Hai fixture KHÔNG khoá được thay đổi** — xanh trên cả `main` lẫn nhánh:
`test_c4_3_no_fire_when_close`, `test_c4_3_repeated_bom_block_counted_once`. Chúng đặt `intake=` và
để `export_qty` mặc định 0, nên nhánh `if sp_qty <= 0: continue` của code cũ cho kết quả rỗng giống
hệt. **Đừng tính chúng là bằng chứng.**

## Điểm neo trong code

| Việc | Chỗ |
|---|---|
| C4.1 (M16 → M15) | `app/checks/c4_norm.py:18` |
| C4.3, chọn số nhân | `app/checks/c4_norm.py:110` |
| C4.3, dựng BOM rồi nhân | `app/checks/c4_norm.py:163-167` — dựng CHỈ từ bảng `norms`, nên TP không có ĐM đóng góp 0 và không sinh phát hiện nào |
| Vòng chạy check, không có preflight | `app/pipeline/run_checks.py:42` |
| Tính điểm | `app/checks/scoring.py:128` |
| Mẫu số + `RULE_SCOPE` | `app/checks/denominators.py:27` |
| Quy đổi họ đơn vị | `app/checks/uom.py` — `resolve_canonical`, `get_family`, `compare` |
| Loại hình DN + cặp cột | `app/checks/company_type.py` — `PAIRING` |
| Trạng thái lần chạy | `app/models/check_run.py:35` — `status` đã khai sẵn `not_evaluable` |

## Sáu chỗ dễ vấp

**1. `not_evaluable` đã có cột, chưa có code.** ADR #18 `:467-471` ghi rõ mục đích: *phân biệt
"0 vì sạch" vs "0 vì thiếu dữ liệu"*, xếp là "Tầng C chờ họp". Issue #56 chính là buổi họp đó.

**2. Điểm rủi ro phải rút check `not_evaluable` khỏi CẢ HAI VẾ.**
`compute_company_year_score` gom finding theo `check_code`; check 0 phát hiện thì vắng mặt khỏi
`by_rule` và đóng góp 0 — không phân biệt được với check sạch. Không rút khỏi trần `max_raw` thì
dữ liệu thiếu đi lại làm điểm ĐẸP LÊN.

**3. Prompt tổng quan AI có bản vá tạm phải gỡ.** ADR #18 `:513` — "KHÔNG khẳng định sạch từ mỗi
con số 0 … tới khi Tầng C thêm `not_evaluable`". Làm xong việc này thì gỡ nó.

**4. `RULE_SCOPE` phải thêm mã check mới**, không thì `test_rule_scope_covers_all_known_checks` đỏ.
Scope của check độ phủ là `tp`.

**5. Đơn vị tiền không cần bảng tỷ giá.** `declaration_lines` có 6 loại tiền (USD 563.696 dòng ·
VND 59.034 · CNY 10.547 · EUR/JPY/SEK không đáng kể) nhưng **`value_total` đã là trị giá quy đổi
VND trên mọi dòng** (tỷ lệ USD ≈ 25.500, JPY ≈ 168 — đều đúng), null đúng 1 dòng trên 633.339.
Đơn giá VND = `Σ value_total / Σ quantity` theo mã — và đó chính là bình quân gia quyền.
Phục vụ cả yêu cầu xếp hạng theo tiền (3.1, 4.1) lẫn định giá BOM (4.3).

**6. Migration:** `companies` và `check_runs` đều là bảng ĐÍCH của khoá ngoại → thêm cột phải dùng
`op.add_column` thẳng, batch mode nổ trên bảng được tham chiếu, và chỉ nổ trên DB có dữ liệu.
Prod còn ở `c5d6e7f8a9b0`, sau local — đối chiếu schema THẬT, đừng tin chuỗi revision.

## Ràng buộc từ CLAUDE.md

- **Không sửa catalog 49 check ở repo này** — sửa `../audit-hq/de-an-audit-hq.md` trước. Check độ
  phủ M15a→M16 (yêu cầu 2.1) **chưa có trong catalog**: C4.1 là NVL M16→M15, C4.2 là SP M16→M15a,
  không mã nào là chiều M15a→M16. Cần owner chốt mã.
- **Không gọi LLM trong rule logic** — ảnh hưởng yêu cầu 4.4 (khớp tên sản phẩm qua các năm). Phải
  đi lối ADR #15/#18: AI đề xuất map, người xác nhận, kết quả cache.
- Đề án C4.3 **đã sửa** rồi (số nhân = sản lượng nhập kho). Mục "chặn bởi đề án" trong `STATUS.md`
  đã stale.
