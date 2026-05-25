# Session 2026-05-25 — Filter 4 DN whitelist + UX bảng + realistic naming + deploy

Continuation of MVP work after 2026-05-21 launch. User asked filter dataset xuống DN có giai đoạn liền nhau BCQT+BCCT, sau đó polish UX bảng data (scroll ngang khó chịu), đổi tên DN cho có hồn, deploy lên Tinsu, setup auto-start runner.

## What Was Done

1. **Data coverage audit** — Lập bảng đầy đủ DN×năm×loại file qua `find` trên `data/raw/`. Xác nhận chỉ 4 DN có ≥2 năm consecutive đều có BCQT+BCCT khi chấp nhận multi_year BCCT file cover khoảng năm. Whitelist chốt: HONG_AN 2021-25 (5y), GROWATT 2023-25 (3y), DO_THANH 2024-25 (2y), KIM_LONG 2024-25 (2y). HIEP_QUANG có BCCT 2021+2024 nhưng 2022/23 thiếu → loại. HONG_PHUC chỉ 2024 đủ → loại.

2. **Filter pipeline** — `app/pipeline/run_all.py` thay `discover_company_years` (quét toàn bộ `data/raw/`) bằng iterate qua `DEMO_WHITELIST: dict[str, range]`. `discover.py` thêm `_filename_covers_year(name, year)` regex `(20\d{2}|\b\d{2}\b)[-_–](20\d{2}|\b\d{2}\b)` cho `BaoCaoHangChiTiet 2023-2025.xls` match cả 2023, 2024, 2025. Fallback BCCT vào `<DN>/multi_year/HANG_CHI_TIET/` nếu per-year thiếu.

3. **Discover bugs fix** —
   - tt39 filter trong `DINH_MUC/` không loại PDF → picked PDF làm M16. Fix: lọc `.xls/.xlsx` trước khi match `startswith("bcdm_tt39")`.
   - M15/M15a regex `_nvl`/`_sp` không match "Mẫu số 15.BCQT-NVL.GSQL.xlsx" (dash trước nvl). Fix: normalize bằng replace `-`/` `/`.` → `_` trước khi check.

4. **UOM cache bug fix** — `_load_cache` giữ ORM instances của `UomCanonical`; lần thứ 2 dùng cache từ session đã đóng → `DetachedInstanceError`. Fix: cache `families: dict[str, str]` (canonical_code → family string) thay vì ORM. Lỗi này tiềm tàng từ trước, lộ ra khi re-seed DB lần này (lần đầu chạy run_all trên DB fresh).

5. **Re-seed prod DB local**:
   ```
   rm audit_hq.sqlite
   alembic upgrade head
   python -m scripts.seed_uom
   python -m app.pipeline.run_all   # ingest + checks cho 12 cặp DN×năm
   python -m scripts.anonymize       # 4 DN demo + 157 NCC
   python -m scripts.inject_findings # 7 changes DN_003 2024 fire combo
   ```
   Kết quả: 4 DN, tổng 2572 findings, 3 combo. DN_003=12653, DN_001=10114, DN_002=2503, DN_004=140.

6. **UX bảng data (Tầng 1)** — User feedback "phải tìm scroll ngang khó chịu". Curate `_TABLE_CONFIG[*].view_cols`: 7-10 cột thực sự cần (STT, Mã, Tên, ĐVT, các cột qty key; không có id/company_id/period_year/source_file). Format số `1,234.56` (tabular-nums, right-align, nowrap), ngày `dd/mm/yyyy`. Helper `_format_cell(value, cls)`. Bỏ `table-overflow` wrapper ở mode default — không còn scroll ngang. Thêm `?full=1` toggle xem tất cả cột (vẫn loại 4 trường nói trên).

7. **Long text wrap** — Recommend hợp lý: line-clamp 2 dòng + `title` tooltip cho text dài (`item_name` BCCT có thể tới 500 ký tự). CSS:
   ```css
   .data-table td.wrap { max-width: 360px; }
   .cell-clamp {
     display: -webkit-box;
     -webkit-line-clamp: 2;
     -webkit-box-orient: vertical;
     overflow: hidden;
   }
   ```
   Template render `<div class="cell-clamp" title="{{ value }}">…</div>` khi `cls == "wrap"`. Áp cho `material_name`/`product_name`/`item_name`/`f.title`/`description`.

8. **Đồng nhất cột mọi bảng** — Thêm `_VIEW_COLS_BY_TABLE: dict[tablename, view_cols]` map cho evidence_blocks trong `/findings/{id}` (trước in toàn bộ cột DB như `block.rows[0].keys()`). Cùng spec view_cols cho `/companies/{c}/data` và evidence_blocks. Findings cũng có view_cols riêng (5 cột: Mã check / Mức / Đối tượng / Tiêu đề wrap / Trạng thái). `admin_units.html` Mô tả cũng wrap.

9. **Source_file leak fix** — User phát hiện `source_file` (đường dẫn file gốc, vd `/data/HONG_AN/2024/BCQT/...xlsx`) lộ tên DN gốc qua mask DN_xxx. Thêm `"source_file"` vào exclude set của full mode + curated mode đã không có sẵn.

10. **Realistic DN names** — User: "DN_001 vô hồn lắm". Đổi `COMPANY_MAPPING` từ "Doanh nghiệp DN_xxx" → "Công ty TNHH \<Ngành\> \<Địa danh\> (Demo)". Cụ thể: DN_001 Điện Tử Phương Đông, DN_002 Cơ Khí Tiên Phong, DN_003 May Mặc Hoa Sen, DN_004 Hoá Chất Nam Tiến, DN_005 Cơ Khí Phụ Trợ Bình Minh, DN_006 Dệt May Sao Khuê. `anonymize()` extended: khi `c.code.startswith("DN_")`, reverse-lookup mapping và refresh name/address nếu lệch — giữ stable code+tax_id.

11. **Demo banner** — `<div class="demo-banner">` trong `base.html` (chỉ render khi user logged in). Text: "🧪 Dữ liệu mẫu — tên doanh nghiệp, MST và đối tác đã được giả lập từ hồ sơ thực, phục vụ mục đích trình diễn. Không phản ánh doanh nghiệp có thật." Style amber 50/100, border bottom amber 300. User chọn banner-only thay vì per-DN badge.

12. **Deploy code** — `git commit -m "demo: filter 4 DN whitelist + UX polish + realistic names"` (commit `cbc4c8f`), `git push main`. CI queue 13 phút bất thường (lần trước 1 phút) → check `gh api /repos/.../actions/runners` thấy runner offline. Start lại runner trên Tinsu, CI auto pick + complete ~1 phút.

13. **Deploy DB** — Vì container không mount `data/` (file gốc 497MB), không thể `app.pipeline.run_all` trên server. Workflow: SCP local `audit_hq.sqlite` (26M) lên `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite`; backup file cũ thành `audit_hq.sqlite.bak-pre-filter-20260525-120046` (18M, DB cũ với 6 DN); `docker restart audit-hq-mvp`. Verify: healthz OK, curl /companies thấy 4 DN với tên mới + banner.

14. **Runner watchdog** — User asked systemd unit cho runner. Phát hiện Tinsu KHÔNG có NOPASSWD (sudo cần password) và password không lưu local. User bảo "tự chui vào server" → workaround sudo-free:
    - `~/actions-runner-audit-hq/runner-loop.sh` — while-loop `./run.sh` respawn nếu crash, log `~/runner-audit-hq.log`.
    - Crontab user `tinsu`: `@reboot /home/tinsu/actions-runner-audit-hq/runner-loop.sh &` — auto-start sau boot.
    - User pause hỏi "may dang dinh reboot server?" khi thấy `@reboot` → clarify chỉ là cron directive, không trigger reboot.
    - Kill nohup process cũ bằng PID (pkill -f không match), start runner-loop foreground.

15. **Memory updates** — `tinsu-server.md` (SSH + sudo + runner pattern), `demo-data-policy.md` (4 DN whitelist + naming + banner), `user-prefs.md` (realistic names + confirm destructive). Index updated.

## Decisions Made

- **Multi_year BCCT counts as coverage** — Strict per-year = 0 DN qualify (app rỗng). Lỏng (BCCT file cover năm trong tên) → 4 DN qualify. User chọn lỏng.
- **Code DN_xxx stable, đổi name** — Không đổi code (vỡ URL/badge), chỉ đổi name display. Tax_id deterministic giữ idempotent.
- **Banner banner > per-DN badge** — User chọn. Banner đầu trang đủ rõ mà không nhiễu UI.
- **Sudo-free runner watchdog > systemd** — Không có sudo. Cron @reboot + while-loop resolve cùng vấn đề (auto-respawn + auto-start sau boot). Khi nào tiện sudo thì swap qua `sudo ./svc.sh install tinsu`.
- **Bỏ inline notes input company_detail** — Form ngang quá rộng → tràn. Hidden field giữ data; notes vẫn edit được trên `/findings/{id}` detail.
- **SCP DB thay vì re-seed trên server** — Container chỉ mount db-data, không có data/. Re-seed cần upload 497MB raw files lên server, không cần thiết.

## What Didn't Work

- **Strict per-year BCCT filter** — Loại tất cả 6 DN. App rỗng → phải nới.
- **HONG_AN 2021 BCCT=0 rows** — 3 file `.xls` cũ pandas không parse được (likely HTML-as-xls). Out of scope task. M15/M15a/M16 vẫn OK → 207 findings.
- **DO_THANH 2025 ingest all 0** — file BCQT duy nhất "BCQT DO THANH_3 quy dau nam 2025 - CHECK.xlsx" bị `_DRAFT_HINTS` filter loại do " - check". Out of scope.
- **pkill runner pattern không khớp** — `pkill -f "actions-runner-audit-hq/run.sh"` không match. Fallback: kill by PID.
- **Anonymize idempotency lần đầu fail** — Print loop `info['original_tax_id']` raise KeyError khi refresh-only entry không có key đó. Fix: branch print theo `info.get("refresh")`.
- **Test failures sau đổi name** — 2 test hardcode "Doanh nghiệp DN_003". Update: assert `== COMPANY_MAPPING["HONG_AN"]["name"]`; thêm test mới `test_anonymize_refreshes_name_when_mapping_changes` cover refresh path.

## Open Items

- **Systemd cho runner** — Khi tiện sudo, swap watchdog hiện tại bằng `cd ~/actions-runner-audit-hq && sudo ./svc.sh install tinsu && sudo ./svc.sh start`. Cleaner + có proper journal qua `journalctl -u actions.runner.TinsuAI-audit-hq-mvp.tinsu-runner-audit-hq.service`.
- **3 runners còn lại trên Tinsu** (`data-hub`, `co`, `bcqt-showcase`) — đều chạy nohup, không có watchdog. Nên áp pattern `runner-loop.sh` + cron @reboot tương tự nếu họ cũng từng offline silently.
- **DO_THANH 2025 chỉ thấy 2024 trong UI** — File BCQT 2025 draft-marked. Nếu HQ hỏi "DN này có 2025 không?", phải giải thích. Có thể nới `_DRAFT_HINTS` chấp nhận " - check" cho 2025 nếu muốn demo đầy đủ.
- **HONG_AN 2021 BCCT** — Adapter pandas không parse `.xls` cũ HTML-disguised. Nếu cần ingest, dùng `xlrd` legacy hoặc detect HTML-as-xls và fallback.
- **Backup files local** — `audit_hq.sqlite.bak-20260525-120743` (18M) untracked. `*.sqlite` gitignore không match `.bak-…`. Có thể xoá hoặc thêm pattern `*.sqlite.bak-*` vào `.gitignore`.
- **Banner kích thước trên mobile** — Chưa test responsive. Banner text dài có thể wrap thành nhiều dòng trên màn hình hẹp. Acceptable nhưng có thể optimize sau.

## References

- Build deployed: `cbc4c8f` (https://audit-hq-demo.tinsu.ai/healthz)
- Backup prod DB: Tinsu `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite.bak-pre-filter-20260525-120046` (18M, 6 DN cũ)
- Memory: `demo-data-policy.md`, `tinsu-server.md`, `user-prefs.md`
- Runner log Tinsu: `/home/tinsu/runner-audit-hq.log`
- Watchdog script: Tinsu `~/actions-runner-audit-hq/runner-loop.sh`
