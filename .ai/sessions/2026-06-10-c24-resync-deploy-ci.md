# Session 2026-06-10 — C2.4 + resync local + deploy live (code-only) + fix CI

## What Was Done

### 1. C2.4 — Tồn cuối thành phẩm âm (commit `bc59545`)
- `app/checks/c2_balance.py`: thêm `check_c2_4` (clone C2.3 sang `SpBalance`/`product_code`, `closing_qty < -_TOLERANCE`) + `CHECKS["C2.4"]`.
- `app/checks/registry.py`: `CheckSpec` C2.4 (group 2, CRITICAL).
- `app/checks/denominators.py`: `RULE_SCOPE["C2.4"] = "tp"`.
- `app/catalog_full.py`: C2.4 status `wip` → `mvp`; comment "16 check" → "17".
- Tests: +2 (`test_c2_4_*`); sửa `test_catalog_has_49_entries` (mvp 16→17, wip 14→13) và `test_score_combo_bonus_one_shot` (max_raw 16→17 rule → 111→105). **439 pass**, ruff clean.

### 2. Resync DB local về đúng 4 DN ẩn danh
Phát hiện local lẫn **5 công ty thật** (tên thật hiện trên UI dev) + **4 DN_xxx mồ côi** (có nvl/sp/norms nhưng 0 tờ khai, findings/score cũ). Nguyên nhân: trước đó `run_all` (ingest công ty thật) chạy đè lên DB đã anonymize → 2 lớp chồng nhau.
- Backup: `audit_hq.sqlite.bak-pre-resync-20260610-213107` (38MB).
- Quy trình đúng (giống live): wipe 7 business tables (giữ users/ai_settings/app_settings) → `run_all` (ingest 4 DN + checks) → `anonymize` (4 real→DN_001–004, 197 NCC) → `inject_findings` DN_003 → `run_checks --company DN_003 --year 2024` → `recompute_all_scores`.
- Kết quả: đúng **4 DN demo, 0 tên thật**. Điểm local (code 17-rule): DN_001 116, DN_002 28, DN_003 148, DN_004 46.

### 3. Fix triệt để nguồn GROWATT (Next Step #2 — DONE)
`data/` → symlink `audit-hq/data/raw` (gitignored). `data/GROWATT` chỉ có 1 file BCCT `BaoCaoHangChiTiet 2023-2025.xls` (8945 dòng, **chỉ NK, thiếu xuất + 2025**).
- Copy 2 file HUB từ `data-hub/data/source_inventory/growatt-vn/2026-05-27/BaoCaoHangChiTiet ALL {NK,XK} GRW (20.05.2026).xls` vào `data/GROWATT/multi_year/HANG_CHI_TIET/`, **đặt tên có khoảng năm** `...ALL {NK,XK} GRW 2023-2025.xls` (để `discover._filename_covers_year` nạp được).
- Rename file cũ `...2023-2025 OLD.xls` → `_is_draft` loại (hint "old"), tránh double-count NK.
- Verify parser BCCT: HUB NK 2023=5474/2024=3471 **trùng khít file cũ**; +2025 19369 + HUB XK. Sau ingest (lọc theo `declaration_date.year`): GROWATT **2023=5475, 2024=3505, 2025=19898** — khớp live.
- **Rebuild demo từ nay tự nạp đủ GROWATT, không mất dữ liệu.**

### 4. Deploy C2.4 lên live — CHỈ CODE, GIỮ DATA
- Live **không có Excel raw** (`/app/data` không tồn tại trong container) → KHÔNG ingest/rebuild trên live được. "Rebuild theo quy trình" trên live = transplant DB sạch → chị chọn **chỉ deploy code, giữ data**.
- Commit + push `bc59545`. CI fail (uv, xem mục 5) → deploy tay: `docker compose up -d --build` với `DB_DATA_PATH=/home/tinsu/audit-hq-mvp-deploy/db-data`, build trong Docker (không cần uv host). Backup live: `audit_hq.sqlite.bak-pre-c24-<ts>`.
- Verify: container healthy, `BUILD_SHA=bc59545→cb2f3ad`, C2.4 in `ALL_CHECKS`/`RULE_SCOPE`/`SPECS` (17 runnable), data live **nguyên vẹn** (4 DN, 127/30/177/49, 2 users).

### 5. Fix CI runner kẹt `uv` (commit `cb2f3ad`)
`deploy.yml` step "Setup venv (uv)" fail `uv: command not found`. `uv` vẫn cài (`/snap/bin/uv`, `~/.local/bin/uv`) nhưng PATH shell non-interactive của GitHub Actions (`/usr/bin/bash -e`) không có 2 path đó. Fix: prepend `export PATH="$HOME/.local/bin:/snap/bin:$PATH"` đầu step. Push → **CI xanh hoàn toàn** (test 1m48s + deploy 27s), redeploy live `cb2f3ad`, healthy, data nguyên vẹn.

## Decisions Made
- **C2.4 vào RULE_SCOPE** dù biết nâng mẫu số scoring (16→17 rule) → điểm giảm nhẹ đều. Đúng vì C2.4 là check runnable thật, phải tính vào trần điểm.
- **Resync theo đúng quy trình live** (wipe→ingest→anonymize→inject) thay vì xoá tay 5 công ty thật — để local thành bản canonical tái lập được.
- **Giữ file cũ GROWATT dạng `OLD`** thay vì xoá — recoverable; HUB NK đã là superset nên không mất dữ liệu.
- **Live chỉ deploy code, không transplant data** (chị quyết) — chấp nhận 2 bản lệch điểm, đổi lại không đụng data production.
- **Fix CI qua `deploy.yml`** (version-controlled) thay vì chỉnh PATH trên host runner — bền, reviewable, tự test khi push.

## What Didn't Work
- **Re-ingest sạch không thể byte-match live**: live build kiểu hybrid (ingest cũ + backfill SQL tay từ data-hub), local re-ingest sạch ra số khác (rõ nhất DN_003 Δ−29). Cộng thêm 21 dòng tờ khai **thiếu ngày** trong file HUB bị `ingest` gán `row_year=year` → nhân 3 qua 2023/2024/2025 (~63 dòng dư, 0.2%). Không sửa (pre-existing behavior, tác động không đáng kể, không thuộc scope).
- **CI auto-deploy lần đầu fail** — không phải code, là PATH runner (mục 5).
- **`pkill -f uvicorn` trả exit 144** làm đứt compound command — tách lệnh ra chạy lại OK. `pgrep` đôi khi khớp nhầm chính nó; xác nhận bằng `ps aux | grep [u]vicorn`.

## Open Items
1. **Đồng bộ điểm 2 bản** (pending, defer theo ý chị): rerun checks trên live bằng code 17-rule mới để C2.4 fire + điểm cache khớp local. Sẽ đổi findings/score live (hiện 127/30/177/49 "treo" vì tính bằng code 16-rule cũ).
2. **Vẫn chờ chị trả lời 4 câu hỏi clarify M16** (từ 2026-06-01) — chưa có hồi.
3. Các Next Steps khác trong STATUS.md giữ nguyên (C6.1 UX, edit check spec từ detail page, demo HQ flow, backlog catalog research, văn bản pháp lý mở rộng).

## Trạng thái cuối
- Local: 4 DN ẩn danh, GROWATT đầy đủ, 439 tests pass, dev server chạy `:8200`.
- Live `cb2f3ad`: C2.4 code deployed, data giữ nguyên, CI auto-deploy hoạt động lại.
- Git: `main` đã push tới `cb2f3ad`. Working tree chỉ còn `.ai/STATUS.md` (cập nhật handoff).
