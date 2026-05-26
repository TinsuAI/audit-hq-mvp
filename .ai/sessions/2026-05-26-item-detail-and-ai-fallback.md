# Session 2026-05-25 → 26 — Item detail page + AI provider fallback chain

Session marathon, kéo dài 2 ngày. Hai mạch chính: (1) tính năng truy vết theo mã NVL/TP với charts; (2) chuyển provider AI từ OpenRouter sang Gemini + fallback NIM DeepSeek.

## What Was Done

### 1. Trang chi tiết mã NVL/TP — truy vết qua các năm

**Discovery** (skill `/discover`): viết feature brief `.ai/features/2026-05-25-item-detail-traceability.md` — quyết định stack, risks, 5 open questions. User confirm "may tự recommend đi" → tự chọn defaults (exact-match BCCT/BCQT, central operation_types map, BOM per-year + cross-year heatmap, AI quick-prompt YES).

**Implementation** (TDD, 6 bước):

1. **Helpers** (`app/items/`):
   - `operations.py`: bảng mã loại hình XNK → `classify_operation(code)` → `"import"|"export"|"other"|"unknown"`, `operation_label(code)`.
   - `aggregations.py`: `detect_item_kind`, `item_years`, `nvl_yearly_summary`, `sp_yearly_summary`, `bcct_lines_for_item`, `bom_edges_for_nvl`, `bom_edges_for_tp`. Reconciliation BCCT vs BCQT exact-match + balance equation check.
   - `charts.py`: pure geometry functions `sparkline_points`, `waterfall_layout`, `sankey_layout` — deterministic, testable.

2. **Route + template**: `GET /companies/{code}/items/{item_code}?year=<n|all>&kind=nvl|tp`. Detect kind, 404 nếu cả BCQT + BCCT đều rỗng, banner cảnh báo nếu chỉ có BCCT (orphan).

3. **SVG charts server-render**: sparkline trong hero, waterfall cân đối kho 6 bước (NVL) / 5 bước (TP).

4. **ApexCharts via CDN** (lazy load, defer): scatter timeline BCCT theo ngày, heatmap year × metric cho tab "Tất cả".

5. **Sankey BOM + findings + AI button**: SVG sankey 2-cấp, AI prompt button preset context (DN, mã, năm) → mở sidebar.

6. **Patch entry points**:
   - `company_data.html`: cls cột mã `code-cell` → `item-link` cho M15/M15a/M16/BCCT, render link `/companies/{}/items/{}`.
   - `finding_detail.html`: subject_key header + evidence table → link.
   - `company_detail.html`: combo card + bảng findings → link.
   - AI sidebar: thêm citation form `[item:CODE]` với link → trang detail. System prompt cập nhật.

**45 test mới** cho phần này, full suite từ 190 → 235 pass.

### 2. UX polish

- **Findings groups collapsed default**: trang DN trước đây mọi nhóm `<details open>` chiếm full trang. Đổi thành collapsed, click để mở. Commit nhỏ riêng.
- **Sankey readability**: với mã có nhiều NVL (14+), sankey ban đầu lộn xộn vì:
  - Tất cả ribbon xuất phát từ cùng 1 điểm cy_center → crisscross.
  - Không sort → mã to lẫn mã nhỏ.
  - Min thickness quá nhỏ → mã nhỏ biến mất.
  
  Fix: sort qty desc + cap 15 nodes + "+N mã khác" cho phần đuôi (gạch đứt, italic) + stack ribbon origin proportionally dọc thanh center (real sankey) + min thickness 1.5px + share % trên label + hover focus (dim other ribbons). 5 test mới khoá.

### 3. CSS cache bust (incident + fix)

User báo "trang nhìn xấu" sau deploy. Diagnose: Cloudflare cache `style.css` với max-age=14400 → serve CSS cũ trong khi HTML mới. 4 fix layered:

1. Local CSS đã có đúng style — đỉa cũ là cache.
2. Thêm `?v={{ app_version_string | urlencode }}` vào CSS/JS URLs trong `base.html`, `_ai_sidebar.html`, `item_detail.html`.
3. Phát hiện `app_version_string` rỗng vì mỗi route module (companies.py, admin.py, admin_ai.py, admin_users.py) tạo Jinja2Templates instance RIÊNG → globals set ở main.py không lan tới. Fix: add `templates.env.globals["app_version_string"]` vào TẤT CẢ instances.
4. Verified: URL giờ thành `style.css?v=v0.1.0%20build%2032c7760` → mỗi deploy URL đổi, Cloudflare miss, fetch fresh.

### 4. Provider switch: OpenRouter → NIM → Gemini

User muốn tiết kiệm tiền OpenRouter:

- **Lần 1 — NIM**: lấy key từ `bcqt-growatt/.env` (`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`). Config qua admin UI: base_url `https://integrate.api.nvidia.com/v1`, model_default `meta/llama-3.3-70b-instruct`. Test OK.
- User feedback "Llama ngao ngao, kém Gemini Flash" → switch sang DeepSeek V4 Pro/Flash trên NIM.
- **Lần 2 — Gemini Google AI Studio**: user paste key `AIzaSyAZ5lHd3BU6CjFcwX2dA6tSqLPT9T38tUw`. Endpoint OpenAI-compat: `https://generativelanguage.googleapis.com/v1beta/openai/`. Test trả 50 models. Set default `gemini-3.5-flash` → user báo `gemini-3.1-flash-lite` không work (preview model). Switch sang series 2.5 GA stable.
- User lo "free tier 250 req/ngày × 5 tool calls/câu = chỉ ~50 câu/ngày". Đổi default → `gemini-2.5-flash-lite` (1000/ngày) và giảm `tool_call_cap` 10 → 5.

### 5. Hybrid fallback chain Gemini → NIM DeepSeek

User: "implement hybrid fallback đi" (vì chỉ chuyển provider không đủ — Gemini cạn quota giữa demo HQ thì gay).

Design + TDD:
- 6 settings mới: `fallback_enabled`, `fallback_base_url`, `fallback_api_key`, `fallback_model_{default,fast,deep}`.
- `app/ai/client.py`: `make_fallback_client()`, `fallback_model_for(slot)`, `should_fallback(exc)` (429/5xx/404/408/424/timeout/connection → yes; 400/401/403 → no), `call_with_fallback()` wrapper.
- Wire vào `app/routes/ai.py`: cả tool loop (non-stream) lẫn streaming start path đều dùng wrapper.
- Admin UI Section 2b cho cấu hình fallback.

Test live: tạm set `model_default=gemini-bogus-zzz` → primary trả 404 → fallback fire → DeepSeek trả lời. Log `Primary LLM failed (NotFoundError); falling back to deepseek-ai/deepseek-v4-pro` xác nhận.

### 6. Tracking model thực sự trả lời

Phát hiện bug nhỏ: `usage.model` trong response luôn ghi tên primary, kể cả khi fallback fire. Fix:
- `call_with_fallback(return_model=True)` trả tuple `(response, model_used)`.
- `routes/ai.py` lưu `model=used_model` trong `_save_msg` + return `usage.fallback_used: bool`.
- Verified: test 1 primary OK → `model: gemini-2.5-flash, fallback_used: false`. Test 2 force fail → `model: deepseek-ai/deepseek-v4-pro, fallback_used: true`.

### 7. Hide cost UI

User: "tạm thời ẩn phần cost trong admin/ai". Thêm flag `show_cost: bool` (default False) vào context của `admin_ai_page` + `admin_ai_conversation`. Gate 4 chỗ: tile "💰 Chi phí", progress bar budget, cột "Cost" trong bảng conv, dòng cost trong conv drill-in. Đổi `True` để bật lại.

### 8. Team announcement + screenshots

Soạn tin nhắn thông báo cho team (English-Việt mix → user yêu cầu "thuần Việt hơn"). Lưu ra `C:\temp\toss\audit-hq-update-item-detail-2026-05-25.txt`. 5 screenshots Playwright minh hoạ: item detail full, cross-year tab, findings collapsed, M16 với links, admin/ai fallback. Toss ra cùng folder.

## Decisions Made

- **Exact-match BCCT ↔ BCQT** (not fuzzy) + banner cảnh báo orphan. Fuzzy nguy hiểm hơn missing data — sẽ fix sau khi biết phạm vi mismatch thực tế qua data quality report.
- **Operation type map centralized** trong `app/items/operations.py` thay vì heuristic prefix. Dict 20+ loại hình theo TT 38/39, sửa năm vài lần.
- **Search box "nhập mã → đi thẳng" → SKIP v1**. Drill-in từ bảng + citation đủ.
- **BOM per-year là default**, heatmap cross-year cho tab "Tất cả" để spot biến động định mức.
- **AI prompt button**: low cost feature, high demo value. Click → mở sidebar với prompt preset.
- **SVG cho sparkline/waterfall/sankey** (server-render, in giấy đẹp), **ApexCharts CDN cho timeline + heatmap** (interactive). Hybrid này tránh thêm JS framework.
- **Sankey design choice**: ribbon origin stack theo qty (real sankey) thay vì all-at-center (chaotic). 15-node cap với "+N khác" để tránh overflow.
- **Provider chain Gemini primary + NIM fallback**: Gemini chất lượng VN cao nhất nhưng quota free chặt. NIM DeepSeek không có daily cap, đủ tốt fallback. 429/5xx/404/timeout → retry; 400/401/403 → no (config issue, đổi provider vô ích).
- **Mid-stream không retry**: stream đã yield chunks thì giữ; chỉ retry khi error xảy ra TRƯỚC khi stream bắt đầu.

## What Didn't Work

- **`gemini-3.1-flash-lite`** trên Gemini OpenAI-compat endpoint: list ra trong /models nhưng request thật trả 404. Là preview model, chưa GA cho free tier. Switch sang `gemini-2.5-flash-lite` GA stable.
- **`z-ai/glm4.7`** trên NIM: user có env var nhưng model không trong catalog NIM trả về. Có thể callable nếu NIM proxy nhưng chưa verified. Bypass dùng `meta/llama-3.3-70b-instruct` xác định trong catalog. (Sau đó switch luôn sang DeepSeek vì Llama 3.3 70B chất lượng VN yếu.)
- **First push fail CI**: ruff lint bắt 8 lỗi E501 + E401 + I001 trong code mới. Phải fix + push lại. Lesson: chạy `make lint` local trước khi push.
- **Cache bust v1 không work**: thêm `?v={{ app_version }}` vào CSS link nhưng `app_version` empty vì globals chỉ register ở `main.py`'s templates instance. Phải propagate vào TẤT CẢ route modules' Jinja2Templates instances.
- **Jinja namespace `__setattr__`**: lần đầu viết waterfall macro trong Jinja với `{% set ns.__setattr__('val', ...) %}` — báo lỗi `'Namespace' object has no attribute '__setattr__'`. Workaround: tính geometry trong Python (`app/items/charts.py`), template chỉ render coords. Sạch hơn.
- **Jinja tuple unpacking trong list comprehension**: `[(b.material_code, b.norm_qty, ...) for b in bom_rows]` không parse được. Pre-compute trong route, pass list of tuples đến macro.

## Open Items

- [ ] Demo HQ thực tế: kịch bản 5-10 câu hỏi tiếng Việt + watch quota Gemini.
- [ ] Xin nâng NIM rate limit 40 → 200 RPM (sau khi scale).
- [ ] Trang `/admin/data-quality` liệt kê mã BCCT orphan (không khớp BCQT) → quyết alias mapping sau.
- [ ] Verify behavior của Gemini Flash với tool calling phức tạp (3+ tool calls/turn). Nếu Flash quá rụt rè, tăng `tool_call_cap` lại.
- [ ] Xoá file `audit_hq.sqlite.bak-20260525-120743` (18MB untracked, dọn dẹp).
- [ ] Refactor: shared Jinja2Templates instance (hiện 4 modules duplicate setup) — không blocking, chỉ là tech debt nhỏ.

## Commits (10 in this session)

```
8702a74 feat(items): item detail page with traceability + cross-ref charts
803e51b fix(lint): satisfy ruff (E501 line length, E401/I001 imports)
60eb3b3 fix(static): version-bust CSS/JS URLs to defeat CDN cache
32c7760 fix(templates): propagate version globals to all route template envs
90a1993 fix(sankey): readability with many nodes
fddd4dd feat(admin/ai): temporarily hide cost UI behind show_cost flag
6911e0c feat(ai): provider fallback chain (Gemini → NIM DeepSeek)
c9605cf fix(ai): track actual model used when fallback fires
```

(Plus prod config changes via admin UI: provider switch + fallback enable.)

## Test count progression

- Start session: 190 pass
- After item detail (steps 1-6): 235 pass
- After sankey readability: 240 pass
- After cost UI hide: 240 pass (no test change)
- After fallback chain: 254 pass
- After tracking actual model: 257 pass
