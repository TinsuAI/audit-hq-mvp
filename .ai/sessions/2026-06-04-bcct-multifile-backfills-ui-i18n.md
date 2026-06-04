# Session 2026-06-04 — BCCT đa-file, backfill DN_001/DN_003 từ data-hub, UI i18n

> Nối tiếp ngay sau session Gemini (2026-06-03 ingest year-filter). Bắt đầu bằng
> việc đọc lại log Gemini để nắm context, rồi dọn dẹp + xử lý loạt vấn đề dữ liệu/UI.

## What Was Done

### 1. Dọn dẹp sau session Gemini (`9cb6bbb`)
- Khôi phục `.ai/STATUS.md` đầy đủ (working tree của Gemini cắt mất ~263 dòng Notes
  deploy/workflow) + chồng cập nhật 06-03.
- `ingest.py` về bản generator gọn (bỏ bản verbose logging trung gian lọt vào HEAD
  qua `dff8bd5`), khớp build `ad68837` đang chạy live.
- Viết lại session doc 06-03 từ plan giữa chừng thành handoff hoàn chỉnh.
- Xoá file rác `audit_hq.sqlite.empty-20260527-102310`.

### 2. Backfill `norms.note` "x" trên live (`c0ff982`)
- Kiểm live: `norms.note` 0/20.781 (toàn NULL) → fix C4.1 "x" (06-01) chưa hiệu lực
  vì live chỉ khôi phục `declaration_lines`, không re-ingest `norms`.
- Backfill: parse M16 thật, map qua `anonymize_mapping.json` (material_code giữ
  nguyên qua anonymize), UPDATE 3517 dòng note. Rerun C4.1 **291→74**, recompute.

### 3. Fix BCCT đa-file NK/XK (`a2b3f92`) + backfill DN_003 (`1549389`)
- **Bug:** `discover` chọn 1 file BCCT/năm theo mtime. DN tách tờ khai nhập (NK) và
  xuất (XK) → chỉ nạp 1. HONG_AN 2021 còn chọn nhầm file rỗng → kỳ 2021 trống.
- **Fix:** `DiscoveredFiles.bcct` thành list; `_pick_all` giữ mọi file non-draft;
  ingest parse + gộp, giữ `source_file` từng dòng. +2 test discover.
- **Backfill live DN_003** (parse NK+XK thật, ẩn danh partner): 2021 0→289,
  2022 69→236, 2025 1512→1893. Insight: thiếu tờ khai xuất E62 gây C1.4 FP hàng loạt
  → DN_003 2025 387→14 finding, 2022 417→250. Score DN_003 232→177.

### 4. DN_001 (GROWATT) — tìm dữ liệu thiếu trong data-hub + backfill (`2b656d6`)
- GROWATT thiếu hẳn tờ khai xuất trong `data/` (file chỉ có mã nhập E11/E13/E15).
- Tìm thấy đầy đủ trong project **data-hub**:
  `data/source_inventory/growatt-vn/2026-05-27/BaoCaoHangChiTiet ALL {NK,XK} GRW`.
  Verify item_code khớp M15 379/379, M15a 56/63.
- Backfill live: 2023 +1 E42, 2024 +34 E42 (C1.4 21→0), 2025 0→19.898 (nhập 19.369
  + xuất 529). Rerun + recompute. DN_001 vẫn 127 (max không đổi, data đúng hơn).

### 5. Refactor ingest: derive `period_year` từ `declaration_date` (`e7b1739`)
- BCCT `period_year` nay suy từ `r.declaration_date.year` từng dòng, không gán cứng
  tham số. Dòng thiếu ngày → fallback kỳ đang nạp. Đếm dòng kỳ khác bị loại vào
  `IngestStats.bcct_other_year`, in ra (không cắt âm thầm). Ghi `DECISIONS.md #13`.
- **Chỉ ảnh hưởng rebuild tương lai** — live không re-ingest, runtime tương đương.

### 6. Xoá 3 DN rác trên live (`e58847c`)
- `DN_`, `TEST`, `TEST_1` (score 0, không có dòng dữ liệu nào gắn). Live còn đúng 4 DN.

### 7. Audit UI tiếng Anh + dịch (`6df3f6e`)
- Quét 25 template + routes (4 agent song song + grep lưới). Gần như sạch. Sửa:
  - `admin_ai.py`: 3 message validation Extra headers → tiếng Việt.
  - `_charts.html`: aria-label Sparkline/waterfall → "Biểu đồ xu hướng"/"...cân đối kho".
  - `admin_units.html`: dịch hết từ vựng UOM (Canonical→Đơn vị chuẩn, Family→Nhóm,
    Alias→Bí danh, Code→Mã, Base factor→Hệ số quy đổi); giữ form `name=` keys.
- Verify live render (6 trang qua login admin/admin): 0 tiếng Anh visible sót.

## Decisions Made
- **Giữ scoping BCCT theo năm, KHÔNG nạp cả file một lần.** Lý do: whitelist năm gắn
  với năm có BCQT (file BCCT GROWATT có 2026 nhưng không có M15/M16 → finding rác);
  file per-year + multi_year gây trùng nếu nạp hết. Thay vào đó derive period_year
  từ date (xem `DECISIONS.md #13`).
- **Backfill live thay vì re-ingest:** live không có Excel raw (policy). Pattern:
  parse nguồn → ẩn danh `partner` qua mapping (mint alias mới nếu cần) → DELETE+INSERT
  → rerun full (`only=None`) → recompute. anonymize giữ material/product_code nên map
  theo (DN→real, year, code) chuẩn xác.
- **admin_units dịch hết** (theo yêu cầu user) kể cả từ khoá miền Canonical/Family/Alias.

## What Didn't Work / Bẫy đã gặp
- **`run_checks(only={"C4.1"})` xoá luôn COMBO findings** mà không tái tạo → điểm tụt
  ảo (DN_001 127→55). Phải rerun FULL (`only=None`) rồi recompute. Đã ghi STATUS.
- Chạy `python /tmp/x.py` trong container fail `import app` (sys.path[0]=/tmp) →
  phải `docker exec -e PYTHONPATH=/app -w /app`.
- Bash loop trong sandbox này làm hỏng PATH (`curl/tr/head: command not found`) → chạy
  từng lệnh riêng, không dùng `for` loop khi gọi tool ngoài.

## Open Items
- ⏳ **Chờ chị trả lời 4 câu hỏi clarify M16** (session 2026-06-01) → xử điểm 2/3 góp ý.
- **Nguồn `data/GROWATT` vẫn thiếu file xuất** (chỉ backfill live). Rebuild demo sẽ mất
  lại → fix triệt để: copy 2 file ALL NK/XK GRW của data-hub vào
  `audit-hq/data/raw/GROWATT/multi_year/HANG_CHI_TIET/`. User đã nói "thôi không cần".
- Verify UI tay phần junk `.`/E13 trên live (chưa làm — phần evidence lệch kỳ + i18n
  đã verify).
- Backup live còn giữ: `...bak-pre-note-backfill`, `...bak-pre-decl-backfill`,
  `...bak-pre-grw-backfill`, `...bak-pre-junk-cleanup` (trong `~/audit-hq-mvp-deploy/db-data/`).
