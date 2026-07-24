# STATUS — Audit-HQ MVP

> **Trạng thái (2026-07-24 — WS1 IMPLEMENT XONG (5 ticket) + demo build + fix dev server):**
> WS1 cài trọn trên branch `feat/ws1-parse-review`: #4 evidence source+review state+registry
> (`7df7e22`) · #5 vòng đời file+cổng review (`0653f1d`) · #6 vân tay form+saved-map store
> (migration `b7d2e1f4a3c6`, `fca9bbb`) · #7 màn review (`573a273`) · #8 re-run scoped (`f00db6f`).
> **634 test pass, ruff sạch, harness giữ 417** (WS1 provenance/UX, KHÔNG đổi finding). Issue GH
> #4–#8 (ready-for-agent) đã cài nhưng **CHƯA push/merge/PR**. `uv.lock` để untracked.
> **2 giới hạn WS1:** (1) parser CHƯA đọc vị trí cột từ saved-map — sửa cột chỉ đánh `officer-confirmed`,
> chưa rewire parse; (2) `run_checks(only=)` xoá COMBO năm đó tới lần chạy full.
> **Nợ do WS2 revise ADR #18:** #7/#8 gọi `run_checks` ĐỒNG BỘ trong `documents_confirm_review` →
> phải chuyển sang job queue (WS2 chốt check chạy async).
> **Demo build** `db-data/audit_hq_demo.sqlite` (gitignored, CHƯA deploy): chỉ 002/004/006, đổi tên;
> 004 = gộp EPE+GC (option 2) = **219 finding** (méo 187→219, PHẢI phân tích lại — memory
> `pilot-004-epe-gc-merge`). MST thật CÒN ở `tax_id`; file Excel gốc còn tên thật.
> **Dev server:** process cũ `84da630` (không `--reload`) 500 trang company vì DB đã tiến xa → đã
> kill PID 8340 + relaunch detached `--reload` trên code hiện tại, mọi trang 200.
> **Next:** grill WS3 (session fresh, worktree/branch riêng) song song WS2-impl; push/merge WS1;
> deploy demo (+ kiểm `user_companies`/login); 004 phân tích lại; async-hoá `run_checks` #7/#8.
> Session log: `.ai/sessions/2026-07-24-ws1-implement-demo-build.md`.

> **Trạng thái (2026-07-24 — grill WS2 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs WS2` (chạy test lẻ + export chọn). WS1 đã cài (branch `feat/ws1-parse-review`,
> #4–#7). Chốt + gộp vào **ADR #18 Revision — WS2** (không tách #19, theo owner):
> (1) **Chạy check TẤT CẢ async qua job queue** — SỬA "re-run inline" của WS1; `RUN_CHECKS` payload
> thêm `only: list[str]`; worker 1-thread serialize ghi → hết tranh chấp SQLite writer. Per-test run =
> nút mỗi nhóm check → `RUN_CHECKS {only:[mã], năm đang xem}` → `/jobs/{id}`. `documents_confirm_review`
> tách confirm/run (option A): save-map + re-ingest GIỮ đồng bộ (file→`parsed`), re-run scoped →
> enqueue job. (2) **Combo:** recompute MỖI lần chạy đọc TOÀN finding-set (sửa lỗi chạy lẻ xoá combo
> không dựng lại) + toggle `combos_enabled` (app_settings, **default OFF**, lazy per-run, ẩn cả render
> lẫn recompute) — OFF vì 2/4 combo neo C4.3 đang đổi định nghĩa. (3) **Export chọn test EPHEMERAL:**
> `build_export(only=)` + param `check` lặp, không chọn = xuất đủ, không "profile". WS2 build được CHỈ
> với hạ tầng job + registry WS1, **KHÔNG cần `check_runs`/`data_version` (WS3)**. **KHÔNG đụng code.**
> Docs: ADR #18 Revision + GLOSSARY (mục WS2) + memory `check-execution-async-via-jobs` — CHƯA commit.
> **Next:** `/to-tickets` cắt slice (đề xuất: nền `only` trong `RUN_CHECKS` handler + `combos_enabled`
> read → per-test run UI → selective export → sửa `confirm_review` sang async), mỗi ticket session fresh
> tham chiếu ADR #18 Revision — WS2.

> **Trạng thái (2026-07-24 khuya — grill WS1 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs` cho **WS1** (parse review + map cột) của brief UI redesign. Chốt toàn bộ
> nhánh chịu lực → **ADR #18** (`.ai/DECISIONS.md`) + **`.ai/GLOSSARY.md`** (mới) + memory
> `parse-confidence-evidence-model`. Cốt lõi: tin cậy = **evidence source mỗi cột** (`officer-confirmed`
> > `header-matched`·`balance-checked` > `position-only`; `balance-checked` chỉ đủ cho cột dạng TỔNG
> vì đẳng thức bất biến dưới hoán vị cột cùng dấu — advisor xác nhận, C2.1/C2.2 đã own đẳng thức).
> Badge **2 trạng thái** `verified`/`needs_review`; cổng review **per-file, warn-not-block**; registry
> `check→cột` dict tĩnh (`consumed_as: individual|sum`); map lưu theo **(DN, vân tay form)** — **per-DN
> confirm (option 2, SỬA ADR #15 cross-DN)**; vòng đời file **`uploaded→analyzed→parsed`** (auto-advance
> khi verified) hiện trên UI; AI = bước sửa (ADR #15); staleness = re-run check bị ảnh hưởng inline,
> stale-flag để WS3. **KHÔNG đụng code.** Working-tree: ADR #18 + GLOSSARY.md **CHƯA commit**.
> **Next:** `/to-tickets` cắt 4 slice → `/implement` ticket 1 (nền: registry + evidence tagging trên
> đường standard — giữ `SheetCandidate.colmap` đang bị `parse_m15` vứt, thêm keyword cột 6/7/9,
> ghi evidence vào `ParseProvenance`), **mỗi ticket một session fresh** tham chiếu ADR #18.
> Session log: `.ai/sessions/2026-07-24-grill-ws1.md`.

> **Trạng thái (2026-07-24 tối — C4.3 đổi số nhân + tầm nhìn UI redesign):**
> Hai việc phiên này. (1) **C4.3 / P-07:** đã sửa đề án §4.1 (số nhân định mức = **sản lượng sản
> xuất**, không phải xuất khẩu) + ADR ở `audit-hq/.ai/DECISIONS.md` — **CHƯA COMMIT**, cross-repo.
> Code `app/checks/c4_norm.py` **chưa sửa** (việc `/implement` kế tiếp): đổi `sp_export`→sản lượng,
> tách (6)/(7) ở `resolve_m15a`, skip mã không-nguồn nhường C4.1, thêm bậc mâu thuẫn vật lý. Đo
> trên dữ liệu thật: 2.371→2.063 finding (−13%). Chi tiết `audit-hq-pilot/notes/13` P-07.
> (2) **UI redesign:** brief 3 workstream (phát hiện+map cột / chạy test lẻ+export chọn / AI overview+stale)
> ở `.ai/features/2026-07-24-parse-review-per-test-ux/brief.md` — input cho `/grill-with-docs`.
> Owner muốn **mở session mới chạy flow Matt**, nghiêng grill WS1 trước.
> (3) **002 (PILOT_002) đã sửa cấu hình kỳ** trên DB localhost: re-ingest với cửa sổ tài chính
> → 279→48 finding, risk 65→7. Backup `audit_hq.sqlite.bak-pre-002-reingest-20260724`.
> Session log: `.ai/sessions/2026-07-24-c43-basis-and-ui-redesign.md`.

> **Trạng thái (2026-07-24 — M15a mở rộng + M16 ĐM thực tế cho 004 + badge truy nguồn — CHƯA COMMIT):**
> Hoàn thành phần "CHƯA thực hiện — Mẫu 15a" của ADR #15 (nay là **ADR #17**). `resolve_m15a`
> (`extended_layout.py`): cổng đẳng thức + `export_qty` theo NHÃN (duy nhất, phải là số hạng trừ)
> + khai triển nhãn gộp `(8ab)`. `content_slots` dò thêm đường mở rộng cho m15a. M16 chọn cột ĐM
> "thực tế" khi có cặp kỹ thuật/thực tế (004). **Badge CÓ LƯU** (`DataFile.parse_layout`/`parse_detail`,
> migration **`f5a6b7c8d9e0`**): trang Tài liệu + trang Dữ liệu gốc hiện bố cục + đẳng thức N/N +
> nhãn cột. Đo thật: 004 EPE M15a 43 (43/43) + M16 664 (c8 thực tế) → **C4.3 fire 8**; 004 GC M15a 2
> + **C1.4 fire 2** (sau khi đặt kỳ GC manual = FY2025 vì header GC ghi sai). 006/whitelist đường
> CHUẨN không đụng. **Harness: 419→419 y hệt** (trung tính; 419 ≠ "1.331" cũ — xem ADR #17 + memory).
> Full suite **583 pass**, ruff clean. **CHƯA commit, CHƯA deploy** (local DB đã đổi + migration đã áp local).
> Screenshot: `.ai/features/2026-07-24-m15a-m16-004/screenshots/`.
>
> **Trạng thái (2026-07-24 — C1 kỳ báo cáo custom-date, full-stack — ĐÃ DEPLOY PROD):**
> Xong C1 `period_from/to` (ADR #16). BCCT chọn theo cửa sổ kỳ `[from,to]` thay `==year`;
> `period_year` = nhãn kỳ (tách khỏi `declaration_date`). Bảng `company_periods` + migration
> `e4f5a6b7c8d9`. Frontend: trang tài liệu sửa được kỳ (form + banner + về mặc định) + nhãn năm
> tài chính ở company_detail/item_detail. 22 test mới, full suite xanh. Harness: PILOT_002 phục
> hồi **đúng 3.014** dòng (window tự đọc 2025-04-01..2026-03-31), whitelist **1.331** finding BẤT
> BIẾN (code cũ cũng 1.331 — mốc "419" cũ đã lỗi thời).
> **ĐÃ MERGE + DEPLOY:** PR #2 → merge commit **`f5d2c0c`** → CI test+lint+deploy xanh →
> prod `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=f5d2c0c` khớp. Migration
> `e4f5a6b7c8d9` đã `alembic upgrade head` trên DB prod. Migration head giờ **`e4f5a6b7c8d9`**.
>
> **Trạng thái (2026-07-23 — Tier A parse layer + B1 + ADR 15 Mẫu 15):**
> Phiên dài, xử lý bộ dữ liệu mới 3 DN (002/004/006) từ `audit-hq-pilot`. Viết lại **tầng
> parse**: chọn sheet theo nội dung, dò dòng dữ liệu, đếm ô hỏng, chọn cột theo bố cục mở
> rộng qua đẳng thức của biểu. Sửa C4.3 nhân trùng khối định mức (B1). Sửa trang finding
> (18,7 MB → 294 KB) + trang tài liệu nhiều slot. **4 lần deploy, đều xanh.**
> **`main` = `origin/main` = prod = `c82ffa9`**, working tree sạch.
> Migration head **`d3e4f5a6b7c8`** (KHÔNG đổi phiên này — không có migration nào phiên này).
> 523 test function, full suite pass.

## Current State

### Git / deploy
- **`main` = `origin/main` = prod = `f5d2c0c`** (merge PR #2 — C1), working tree sạch. Prod live
  `audit-hq-demo.tinsu.ai` chạy `f5d2c0c` (đã verify 2026-07-24: `/healthz` 200, `build_sha=f5d2c0c` khớp).
- Migration head prod = **`e4f5a6b7c8d9`** (company_periods) — CI đã `alembic upgrade head`.
- Deploy = push `main` → CI "Test & Deploy to Tinsu" (self-hosted `tinsu-prod`): test+lint →
  docker build → restart → `alembic upgrade head` → healthcheck. Watch: `gh run watch <id> --exit-status`.
  **LƯU Ý:** runner self-hosted đôi khi queue 10+ phút trước khi chạy — không phải lỗi.
- 9 commit phiên này (từ `fadc427`): xem session log `2026-07-23-tier-a-parse-layer.md`.

### Prod ≠ local — ĐỌC KỸ trước khi đụng dữ liệu
- **DB prod ở server** (`/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite`, 101 MB, 14 DN,
  1.727 finding), truy cập qua `ssh tinsu` + `docker exec audit-hq-mvp`. KHÁC local
  (`audit_hq.sqlite`, giờ ~300 MB sau khi nạp pilot).
- **raw-data prod dùng tên anonymize** `DN_001/DN_103/DN_104/DN_105/DN_106`, mỗi DN chỉ 2024+2025.
  `DN_103`=HONG_AN, `DN_104/105/106`=ba bản sao GROWATT. 10/14 DN prod KHÔNG có file nguồn.
- **`run_all` tìm 0 cặp trên prod** (whitelist là HONG_AN/GROWATT/DO_THANH/KIM_LONG — không tồn
  tại ở server). Re-ingest prod bằng `run_all` là no-op.
- **Local `data/` symlink** → `../audit-hq/data/raw`, có tên THẬT (HONG_AN…) + PILOT_002/004/006.
  Ingest theo `code` → tạo company mới, KHÔNG ghi đè `DN_xxx`. Xem [[local-data-symlink-mismatch]].

### Dữ liệu mới 3 DN (002/004/006) — đã nạp vào LOCAL DB
- Local DB giờ có `PILOT_002` (279 finding), `PILOT_006` (14.883), `PILOT_004_EPE` (111),
  `PILOT_004_GC` (99). Chỉ ở local — KHÔNG ở prod.
- Symlink tree đã tạo cố định: `../audit-hq/data/raw/PILOT_{002,004_EPE,004_GC,006}/<năm>/{BCQT,DINH_MUC,HANG_CHI_TIET}`
  (trỏ tới `raw-hq-2026`, gitignored). `discover`/`ingest` đọc trực tiếp được.
- **File nguồn:** `/mnt/p/Downloads/audit-v2.zip` (148 MB) = giải nén sẵn ở `audit-hq/data/raw-hq-2026/`.
- Verify chéo với parser độc lập của pilot: 006 điểm 154/190 y hệt, M15 10.560 dòng, sai lệch
  2/21.878 finding. → tầng parse đúng.

### Tầng parse — trạng thái từng phần
- **Chọn sheet theo nội dung** (`app/adapters/sheet_select.py`): chấm điểm nhãn cột đúng vị
  trí, phá hoà theo kỳ báo cáo (rank), báo `SheetNotFound` nếu không khớp. 4 slot đều dùng.
- **Dò dòng dữ liệu + P-01** (`app/adapters/layout.py`): `_norm` gập đ/Đ (U+0111/U+0110), dò
  header 2 dòng + dòng đánh số `(1)(2)…`.
- **Bố cục mở rộng Mẫu 15** (`app/adapters/extended_layout.py`, ADR #15): suy map cột từ dòng
  đánh số, chứng minh bằng đẳng thức `(11)=(5)+(6)-(7)-(8)-(9)-(10)` ≥98% dòng. Chỉ chạy khi
  `select_sheet` trượt → prod (16 file, 0 trượt) KHÔNG đụng. 004 nạp được M15 (EPE 104, GC 37).
- **A3 ô hỏng** (`_common.py`): đếm ô lỗi Excel + liên kết workbook ngoài, cảnh báo không đổi số.
- **B1 C4.3** (`c4_norm.py`): mỗi cặp BOM tính 1 lần thay vì 1 lần/khối lặp.

## Recent Changes (2026-07-23)
9 commit trên `main`, 4 lần deploy:
1. `a7f685a` P-01 · `e8dbea3` A1+A2 · `8c69f0b` A1 m16/bcct + discover · `3d98e4f` A3 ·
   `d6b1bf1` B1 · `2847724` ADR 15 · `665e315`+`216afd3` sửa 6 lỗi từ `/rev` → merge `65c88cf`.
2. `f09116b` phân trang finding · `41794d7` fix trang tài liệu nhiều slot → merge `5b0de04`.
3. `56c54bd` bố cục mở rộng Mẫu 15 (ADR 15) → merge `c82ffa9`.

## Next Steps (theo ưu tiên)
0. **C1 — `period_from`/`period_to` — ✅ XONG + ĐÃ DEPLOY PROD (2026-07-24, ADR #16, đường RẺ).**
   Bảng `company_periods` + migration `e4f5a6b7c8d9`; BCCT lọc theo cửa sổ `[from,to]`; `period_year`
   = nhãn kỳ; frontend sửa được kỳ + nhãn năm tài chính. Full-stack + 22 test. Merge `f5d2c0c`,
   CI + deploy xanh, prod verify OK. **Còn (tuỳ chọn, chưa làm):** cảnh báo cửa sổ sửa tay chồng
   lấn chéo năm — giới hạn manual-only có chủ đích (ADR #16). Đường tự động an toàn (FY liền kề
   không chồng). Ngoài ra: reload dữ liệu PILOT_002/004 lên prod để hưởng phục hồi dòng (prod
   hiện không có file nguồn 002/004 → cần upload hoặc chạy lại từ file).
1. **M15a mở rộng + cột M16 của 004 — ✅ XONG (2026-07-24, ADR #17, CHƯA COMMIT).** `resolve_m15a`
   (đẳng thức + export theo nhãn + nhãn gộp), discovery dò mở rộng, M16 ĐM thực tế, badge có lưu.
   Đo thật: EPE C4.3=8, GC C1.4=2. Harness whitelist 419→419 trung tính. 583 test pass.
   **Còn (tuỳ chọn):** commit + deploy (prod chưa có file 002/004 → chỉ code lên, data cần upload);
   reload 004 lên prod. C4.3 nhánh sản lượng M16 (hệ số nhân) vẫn CHẶN bởi đề án — xem #2.
2. **Sửa đề án `../audit-hq/de-an-audit-hq.md:228` TRƯỚC** rồi mới làm B2 (đổi hệ số nhân C4.3
   sang lượng nhập kho SX), B4 (báo độ phủ C4.3), và hệ số nhân theo sản lượng Mẫu 16. Cả ba
   mâu thuẫn định nghĩa `Σ(định_mức × xuất_khẩu_M15a)` hiện tại — là "sửa catalog" theo AGENTS.md.
3. **B3 đọc cột Ghi chú** — cần migration (thêm `note` vào NvlBalance/SpBalance).
4. **Tầng C — chờ họp:** `period_from`/`period_to` (002/004 năm tài chính → ingest xoá 27-30%
   dòng tờ khai), `NOT_EVALUABLE` (phân biệt "0 vì sạch" vs "0 vì thiếu dữ liệu"), trình bày
   quy mô lớn (đã làm phân trang, còn xếp hạng theo lượng + ngưỡng severity).

## Blockers
- **B2/B4/hệ số nhân C4.3 chặn bởi đề án** — không được sửa mô tả check trước khi update
  `../audit-hq/`. Câu hỏi quy trình 3 repo, cần user chốt.
- **Banner "dữ liệu mẫu"** đang phủ lên tên DN + MST THẬT ở local DB sau khi nạp pilot (banner
  nói dữ liệu giả — sai). `anonymize.py` chỉ sửa DB, KHÔNG sửa nội dung file Excel (trang tài
  liệu vẫn tải file gốc). Chưa xử lý — chặn việc đưa pilot data lên demo.
- **Tầng C chờ họp** (chưa có lịch).

## Notes for Next AI Session
- **Dev server local đang chạy** ở `http://127.0.0.1:8200` (background). Local admin password
  KHÔNG biết → đăng nhập bằng user throwaway seed qua `create_user` rồi purge (xem
  [[ui-screenshots-convention]]). Screenshot scratch, KHÔNG commit.
- **Harness verify** (scratchpad, session-specific, có thể mất): ingest+run_checks toàn bộ
  whitelist vào DB tạm, dump finding đã sort, diff trước/sau. **Mốc chuẩn hiện tại (2026-07-24):
  1.331 finding trên 12 cặp DN×năm** (đo lại code cũ = code mới sau C1 → C1 trung tính). Con số
  "419" trong ghi chú cũ ĐÃ LỖI THỜI (khác bộ dữ liệu/thời điểm) — đừng dùng làm tiêu chí. Chạy
  lại mỗi khi chạm tầng parse/check.
- **Kỷ luật số liệu:** số của `audit-hq-pilot/notes/` đếm theo luật parser CỦA PILOT, không
  phải sản phẩm — phải phát biểu lại theo luật đếm sản phẩm trước khi dùng làm tiêu chí. Xem
  [[tier-a-thu-tu-a1-truoc-a2]] và [[so-lieu-phai-co-mau-so-va-nguon-doc-lap]].
- **A1 trước A2, KHÔNG song song** — `notes/12` ghi sai, đã đính chính. A2 chạy trước A1 làm
  hỏng nặng thêm (đo được +20 finding CRITICAL giả).
- **Cổng đẳng thức là trọng tài** cho map cột — không tin nhãn/mô hình. Bug bắt được nhờ nó:
  số hạng đầu công thức `(5)+(6)-...` không có dấu, 004 GC "lọt" giả vì tồn đầu toàn 0.
- **ADR mới:** `.ai/DECISIONS.md` #15 (15 ADR tổng). Ghi rõ phần đã làm (M15) vs chưa (M15a/M16).
- `audit-hq-pilot` là repo anh em (git local, không remote), commit `7e8e438` đã đính chính
  `notes/12`. Prompt bàn giao gốc ở `audit-hq-pilot/.ai/STATUS.md`.
