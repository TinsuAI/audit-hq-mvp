# Session 2026-06-11 — UI/UX + viết lại methodology

Yêu cầu của chị: 5 việc UI/nội dung.
1. Trang methodology viết thuần Việt hơn (đang chêm nhiều tiếng Anh).
2. Giải thích cách tính điểm ngay trang chủ — phương án tiện dụng & đẹp.
3. Bảng công ty thêm filter / group by / search.
4. Redesign UX/UI trang Thêm DN mới + Tải lên dữ liệu.
5. Bổ sung key OpenRouter cho AI.

Sau khi hỏi clarify, chị chốt: trang chủ dùng **thẻ thu gọn được**; bảng làm
**cả 4 tính năng** (kể cả nhóm theo ngành); làm **tuần tự 1→4** rồi giữa chừng
chuyển sang **"làm hết đi"**. Bổ sung cuối: **thêm trang Sửa DN**.

## Đã làm

### 0. Key OpenRouter (item 5)
- `set_setting('api_key', <key>)` + `set_setting('enabled', True)` vào `ai_settings`
  (DB local, gitignored). `test_connection()` OK 229ms, OpenRouter trả model list.
- Default `base_url` vốn đã là `https://openrouter.ai/api/v1` + model `anthropic/claude-*`.
- **KHÔNG commit** (DB không vào git), **chưa set trên live**.

### 1. Viết lại `docs/scoring-methodology.md` (item 1)
- **Thuần Việt:** bỏ thuật ngữ Anh (rate-based, findings, exposure, max_points,
  points, rule, combination bonus, breakdown, evidence_refs, run-checks, jobs,
  cohort z-score, calibrated, composite/compendium) + định danh code khỏi văn
  xuôi; dịch tên tài liệu WCO/OECD. Giữ glossary đã chốt (BCQT, M15/15a/16, BCCT,
  NVL, TP, HS, MST, mã check C2.1…).
- **Sửa số liệu dẫn xuất từ code:** 16→17 phép, 180→190
  (`max_raw = len(RULE_SCOPE)×10 + 20`, xác minh `len(RULE_SCOPE)=17`).
- **§6 ngưỡng 5 mức:** chị chỉ ra đây là **cấu hình runtime** (không phải bug).
  Viết lại: nêu rõ admin chỉnh ở trang Ngưỡng hạng rủi ro, bảng ví dụ dùng
  **default hiện hành 50/100/300/600/1000** (khớp UI demo: DN_003=168 → "Cần rà
  soát"). Bộ số cũ trong doc (0-100/101-300/…) đã bỏ vì không khớp code.
- **§4:** "Điểm thưởng tổ hợp" → **"Điểm rủi ro tổ hợp"** (chị: "thưởng" mang
  nghĩa tích cực, sai ngữ cảnh rủi ro). Thêm **bảng 4 tổ hợp** lấy từ `combos.py`
  + ghi chú "danh mục mở rộng theo kinh nghiệm cán bộ HQ".
- Bump version date → 2026-06-11. Test `test_docs_route.py` 8/8 (heading giữ nguyên).

### 2. Thẻ giải thích điểm ở trang chủ (item 2)
- `companies_list.html`: `<details class="scoring-explainer" open>` — mô tả 1 dòng,
  công thức (`{{ n_rules }}` phép), trọng số 🔴10/🟡3/🔵1, thang 5 hạng màu, link doc.
- `companies.py::list_companies`: truyền `n_rules = len(RULE_SCOPE)` và
  `tier_ladder` dựng từ `get_tiers(db)` (ngưỡng runtime → tự đúng khi admin đổi).
- Gỡ popover "ℹ️ Cách tính điểm" cũ + CSS chết `.scoring-info/.scoring-popover`.
- CSS mới: `.scoring-explainer`, `.se-*`, `.se-ladder/.se-tier`.

### 3. Bảng DN: tìm / lọc / sort / nhóm ngành (item 3)
- Schema: `Company.industry: Mapped[str|None]` (String 100, index). Migration
  `e1a2c3d4f5b6` (down_revision `c7f3a1b2d4e5`), đã `alembic upgrade head` local.
  Nạp ngành 4 DN: DN_001 Điện tử, DN_002 Cơ khí, DN_003 Dệt may, DN_004 Hoá chất.
- `companies_list.html`: toolbar (search/tier-filter/industry-filter/group-toggle/
  count) + cột Ngành + data-attr trên `<tr>` + **JS inline** (filter + sort +
  group-by chèn `tr.dn-group-header`). `get_tiers` cho options dựng từ DOM.
- CSS: `.table-toolbar`, `.toolbar-*`, `th.sortable`, `.dn-group-header`,
  `.industry-tag`, `.is-hidden`, `.table-empty-hint`.

### 4. Redesign Thêm DN + Tải lên (item 4)
- `new_company.html`: class CSS thay inline, lưới 2 cột, alert/hint chuẩn, thêm
  field **Ngành** (input + `<datalist>` 8 ngành). Route `create_company` +
  `industry` Form param + lưu vào Company.
- `upload_data.html`: 4 ô file → **vùng kéo-thả** (`.upload-slot`, hiện tên file,
  viền xanh khi có file; JS dragover/drop set `input.files`). Panel chẩn đoán +
  khối AI restyle (`.diag-panel`, `.diag-item`, `.diag-ai`).
- CSS form/upload/diag thêm cuối `style.css`.

### 5. Trang Sửa DN (bổ sung)
- `GET/POST /companies/{code}/edit` + `edit_company.html`. Sửa tên/ngành/MST/
  địa chỉ. **Mã DN khoá** (disabled) — vì là tên thư mục `raw_data_path/{code}`,
  đổi sẽ mồ côi file đã upload. Tên giữ hậu tố `(Demo)` như lúc tạo.
- `company_detail.html`: nút "✏️ Sửa" ở header + dòng "Ngành".
- `tests/test_company_edit.py` (3 test): prefill+khoá mã, update+giữ Demo, 404.

## Quyết định
- **Mã DN không cho sửa** (tên thư mục file). Nếu sau này cần đổi mã → phải move
  thư mục `data/raw/{code}` + cập nhật DB, chưa làm.
- **Tier ladder + công thức đọc động** (`get_tiers`, `len(RULE_SCOPE)`) thay vì
  hardcode → không drift khi đổi ngưỡng / thêm rule.
- **Ngành lưu free-text + datalist gợi ý** (không enum cứng) cho linh hoạt demo.
- Methodology bảng ngưỡng ví dụ = default code (50/100/300/600/1000), KHÔNG phải
  bộ số cũ — vì bộ cũ không khớp tier đang hiển thị trên UI.

## Không / chưa làm
- **Chưa commit, chưa push, chưa deploy live.** Đang là working changes trên `main`.
- **Live:** cần chạy migration `e1a2c3d4f5b6` + set ngành 4 DN qua trang Sửa
  (live không re-ingest từ Excel được).
- Gợi ý còn lại (Next Step D): badge trạng thái DN trên bảng danh sách, progress
  inline khi chạy check, **tự đoán slot theo tên file** khi kéo-thả (hiện phải kéo
  đúng ô), nút "nạp 1 DN mẫu" một chạm.

## Kết quả
- **449 tests pass** (446 + 3), ruff clean. Dev server :8200 đã verify 3 trang
  render 200 (companies / new / upload / edit), thang hạng + n_rules đúng.
