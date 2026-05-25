# Feature: Trang chi tiết mã NVL/TP — Truy vết & Cross-reference qua các năm

## Scope

Thêm trang detail per mã hàng (NVL hoặc TP) cho một DN, hiển thị toàn bộ thông tin về mã đó qua các năm: cân đối BCQT, giao dịch BCCT, BOM/định mức, và các phát hiện liên quan. Đây là drill-in tự nhiên từ `/companies/{code}/data` (bảng) và từ citation trong findings/AI chat — chỗ hiện tại click code không đi đâu cả.

**Trong scope:**
- URL mới: `/companies/{code}/items/{item_code}` (auto-detect NVL hay TP, hoặc cả hai nếu trùng mã).
- Hiển thị tất cả năm có dữ liệu, default mở năm gần nhất.
- Tab theo năm (top-level), trong mỗi năm là các section: cân đối kho, BCCT, BOM (norms), findings liên quan.
- Biểu đồ trực quan (xem §Visualizations).
- Cross-year traceability summary (top of page, "câu chuyện" của mã qua các năm).

**Ngoài scope (giai đoạn này):**
- Cross-company traceability (cùng mã ở nhiều DN khác nhau).
- Sửa data inline.
- Bulk export riêng cho 1 mã (đã có export tổng `/companies/{code}/export`).
- Smart matching giữa BCCT `item_code` và BCQT `material_code/product_code` khi khác chuỗi (xem Risks).

## Data model recap

- `nvl_balances` (M15): `material_code`, year-level: opening, import, reexport, repurpose, production_out, other_out, closing.
- `sp_balances` (M15a): `product_code`, year-level: opening, intake, repurpose, export, other_out, closing.
- `norms` (M16): `(product_code, material_code, year) → norm_qty` — đây là BOM thực tế.
- `declaration_lines` (BCCT): line-level XNK, có `item_code`, `declaration_date`, `customs_code` (nhập/xuất phân biệt qua loại hình), partner, qty, unit_price.
- `findings`: `subject_key` trỏ về mã hàng cho nhiều check (C1/C2/C4/C5...).

Index hiện có đủ cho query per `(company_id, period_year, code)`. Không cần migration.

## UX / Layout

```
─────────────────────────────────────────────────────────────
Breadcrumbs:  DN › Mã NPL-123 (Nguyên vật liệu)
─────────────────────────────────────────────────────────────
HERO BAND
  ┌──────────────────────────────────────────────────────┐
  │ NPL-123 · "Vải dệt kim 100% cotton"                  │
  │ Đơn vị: KG  ·  Loại: Nguyên vật liệu                 │
  │                                                       │
  │ 2018 ──●──●──●──●──●──●──●── 2025  (sparkline tồn)   │
  │ Tồn cuối 2025: 12,450 KG   ↓ -8% vs 2024             │
  │ Tổng nhập 8 năm: 1.2M KG  ·  Tổng xuất SX: 1.18M KG  │
  │ 3 phát hiện 🔴  ·  Là input của 7 thành phẩm         │
  └──────────────────────────────────────────────────────┘

TAB BAR (năm):  [2025*] [2024] [2023] [2022] [2021] [2020] [2019] [2018]
                                                            └─ "Tất cả"

NỘI DUNG TAB (năm = 2025):

  ┌─ Cân đối kho (M15) ─────────────────────────────────┐
  │  Đầu kỳ  +  Nhập  −  XK ngược  −  Tự CN  −  SX  −  Khác  =  Cuối kỳ │
  │  Waterfall chart minh hoạ:                          │
  │   ▆▆▆▆▆ ▇▇▇▇▇▇▇                                     │
  │       opening ──┐                                   │
  │              +import ─┐                             │
  │                    −production ──┐                  │
  │                              =closing               │
  │  + Reconciliation badge:  ✅ Khớp / ⚠️ Lệch 0.3%     │
  └─────────────────────────────────────────────────────┘

  ┌─ Giao dịch BCCT trong năm ──────────────────────────┐
  │  Sub-tab: [Tờ khai nhập (12)] [Tờ khai xuất (0)]    │
  │  Timeline chart: chấm theo ngày, size = qty         │
  │  Bảng: ngày · số TK · partner · qty · đơn giá · trị │
  │  Tổng: 145,000 KG nhập từ 3 partner (Trung Quốc 80%)│
  └─────────────────────────────────────────────────────┘

  ┌─ Là đầu vào của thành phẩm nào (M16) ───────────────┐
  │  Sankey nhỏ:  NPL-123 ──┬─→ TP-A01 (45%)            │
  │                          ├─→ TP-A02 (30%)           │
  │                          └─→ TP-B05 (25%)           │
  │  Bảng: TP code · tên · định mức · tổng tiêu thụ ước │
  └─────────────────────────────────────────────────────┘

  ┌─ Phát hiện liên quan trong năm ─────────────────────┐
  │  🔴 C2.1 Cân đối lệch — chi tiết                    │
  │  🟡 C4.3 Định mức bất thường — chi tiết             │
  └─────────────────────────────────────────────────────┘

PHẦN "TẤT CẢ" (cross-year):
  • Heatmap year × metric (nhập / xuất / tồn cuối / số TK)
  • Bảng so sánh BCCT-vs-BCQT mỗi năm: ΣBCCT.import vs M15.import_qty
  • Continuity check: closing(Y) vs opening(Y+1) — flag khi lệch
```

Với mã TP (`product_code`): tương tự nhưng "Là đầu vào của" đổi thành "BOM — cấu thành từ NVL nào", Sankey ngược lại.

## Visualizations (jaw-dropping nhưng nhẹ)

Stack hiện tại: Jinja2 server-render + CSS thuần, không có JS framework. Hai lựa chọn:

**A. SVG server-rendered (recommend cho sparkline + waterfall + sankey nhỏ)**
- Hand-render trong Jinja macro hoặc Python helper → trả SVG inline.
- Zero JS, không tăng bundle, in được, copy được, SEO-friendly cho cán bộ xem.
- Đủ đẹp cho sparkline, bar, waterfall, sankey-2-level.

**B. ApexCharts qua CDN (cho timeline BCCT + heatmap)**
- ~150KB gzip, chỉ load ở trang detail này.
- Pro: tooltip mượt, zoom, animation lúc load — "lác mắt" effect.
- Con: phụ thuộc CDN, hơi nặng. Có thể self-host file.

Đề xuất: **A cho hero sparkline + waterfall cân đối + sankey BOM** (server-render, fast paint), **B cho timeline BCCT theo ngày + heatmap year×metric** (tương tác).

Palette gắn với CSS hiện có (`.text-mono`, severity colors `--c-critical/warning/info`) — không introduce theme mới. Numbers format `vi-VN` locale (đã có ở `_format_model_rows`).

## Decisions

- **URL:** `/companies/{code}/items/{item_code}` — single URL, server detect kind. Query `?kind=nvl|tp` để disambiguate khi trùng mã (rare). Default year = year mới nhất có dữ liệu, override qua `?year=`.
- **Tab UX:** tabs là server-rendered links (`?year=2024`), không phải client tab. Đơn giản, deep-linkable, in được. ARIA-tabs role nhưng degrade thành nav nếu no JS.
- **Cross-year section:** lazy — chỉ render khi user click "Tất cả", tránh load nặng default.
- **Sankey/waterfall:** dùng SVG macro Python helper trong `app/visualizations.py` mới — không thêm dependency.
- **Charts tương tác:** ApexCharts CDN, load defer, fallback gracefully nếu offline (hiện bảng số).
- **Liên kết ngược:** patch `company_data.html` để cột mã thành link `→ /items/...`. Patch citation builder trong AI tools để link đến trang mới khi citation kèm `code`.
- **Findings filtering:** dùng `Finding.subject_key` (đã có). Cần verify check nào set subject_key = material/product code (C1/C2/C4 chắc chắn có).

## Risks

- **Code drift BCCT ↔ BCQT.** `declaration_lines.item_code` có thể không khớp 1-1 với `nvl_balances.material_code` (DN tự code khác giữa hai báo cáo). Trang detail dựa vào exact-match → có thể "thiếu giao dịch" mà không báo. **Mitigation:** hiện banner "BCCT tìm theo exact-match item_code = 'NPL-123', nếu DN dùng mã khác trong BCCT giao dịch sẽ không xuất hiện ở đây." Để vòng sau làm fuzzy/alias mapping (giống UOM alias).
- **NVL vs TP cùng code.** Cùng chuỗi có thể là material_code ở DN này và product_code ở DN khác, hoặc cả hai trong cùng DN. Cần hiển thị cả hai panel với toggle khi xảy ra.
- **Sankey/waterfall với dữ liệu lệch.** Khi `opening + import − out ≠ closing`, waterfall vẫn phải vẽ đúng dữ liệu thật + badge lệch (đừng "tự sửa" để chart đẹp — sẽ che bug audit).
- **Performance.** HONG_AN có 8 năm + nhiều mã. Per-page truy vấn: 4 bảng × 1 năm = nhanh; cross-year "Tất cả" có thể nặng. Đảm bảo lazy + dùng aggregate query thay vì pull rows.
- **BCCT phân biệt nhập/xuất.** Hiện model không có cờ trực tiếp; phải suy từ `customs_code` (loại hình E31/E62/A41…). Cần map loại hình → nhập/xuất ở một chỗ tập trung. Hỏi: có sẵn helper chưa?
- **In ra giấy / xuất PDF.** Cán bộ HQ in báo cáo điều tra. SVG inline in đẹp; ApexCharts canvas in xấu. Cân nhắc layout có version "in" gọn (no interactive).

## Open Questions

1. **Code matching BCCT↔BCQT** — có spec/quy ước nào hiện hành chưa, hay cứ exact-match và banner cảnh báo? (Tôi đề xuất exact-match v1 + log số mã "không tìm thấy ở BCQT" để biết phạm vi vấn đề.)
2. **Loại hình XNK → nhập/xuất** — đã có mapping ở đâu trong code chưa? Nếu chưa, dùng heuristic prefix (`E*` = nhập sản xuất, `B*` = xuất sản xuất) hay yêu cầu admin maintain?
3. **Trang detail có nên là entry-point từ search box** ("nhập mã NPL-123" → đi thẳng), hay chỉ drill-in từ bảng/findings? Search box thêm value nhưng đòi UX rộng hơn.
4. **TP với BOM thay đổi qua năm** — hiển thị BOM mỗi năm riêng (đúng nhất, "định mức thực tế" có thể đổi) hay overlay so sánh năm-qua-năm để spot biến động? Tôi nghiêng về **cả hai**: tab năm hiện BOM năm đó, mục "Tất cả" có heatmap norm_qty theo năm × NVL.
5. **AI assistant tích hợp** — trang detail có nên ghim 1 prompt-suggestion "Giải thích bất thường của mã này"? Click → mở AI sidebar với context preset. (Nhỏ nhưng tạo wow.)

## Suggested next step

1. Confirm 5 open questions (đặc biệt #1, #2 — chặn chính xác data shape).
2. Implement theo TDD: viết test cho aggregation helper trước (sum BCCT theo year, build sankey edges từ Norm), rồi route + template. Skill `/tdd`.
3. Frontend làm lát mỏng: hero band + 1 tab năm + 1 chart SVG trước → review UX → mở rộng phần còn lại.
