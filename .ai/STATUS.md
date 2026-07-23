# STATUS — Audit-HQ MVP

> **Trạng thái (2026-07-24 — C1 kỳ báo cáo custom-date, full-stack):**
> Xong C1 `period_from/to` (ADR #16). BCCT chọn theo cửa sổ kỳ `[from,to]` thay `==year`;
> `period_year` = nhãn kỳ (tách khỏi `declaration_date`). Bảng `company_periods` + migration
> `e4f5a6b7c8d9`. Frontend: trang tài liệu sửa được kỳ (form + banner + về mặc định). 20 test
> mới, full suite **573 xanh**. Harness: PILOT_002 phục hồi **đúng 3.014** dòng (window tự đọc
> 2025-04-01..2026-03-31), whitelist **1.331** finding BẤT BIẾN (code cũ cũng 1.331 — mốc "419"
> cũ đã lỗi thời). **CHƯA commit** (working tree có thay đổi). Migration head giờ **`e4f5a6b7c8d9`**.
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
- **`main` = `origin/main` = prod = `c82ffa9`**, working tree sạch. Prod live
  `audit-hq-demo.tinsu.ai` chạy `c82ffa9` (đã verify `/healthz` 200, build_sha khớp).
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
0. **C1 — `period_from`/`period_to` — ✅ XONG (2026-07-24, ADR #16, đường RẺ).** Bảng
   `company_periods` + migration `e4f5a6b7c8d9`; BCCT lọc theo cửa sổ `[from,to]`; `period_year`
   = nhãn kỳ; frontend sửa được kỳ. Full-stack + 20 test + full suite 573 xanh. **Còn:** commit;
   (tuỳ chọn) cảnh báo cửa sổ sửa tay chồng lấn chéo năm — hiện là giới hạn manual-only có chủ
   đích (xem ADR #16). Đường tự động an toàn (FY liền kề không chồng).
1. **M15a mở rộng + cột M16 của 004** — việc tiếp ADR 15. Số biểu M15a KHÔNG ổn định giữa DN
   (006 trừ (7), 004 EPE cộng, 004 GC nhãn gộp), nên map `export_qty` phải theo NHÃN + cổng
   đẳng thức riêng. Mở khoá C4.3/C1.4 cho 004. Cột định mức M16 của 004 đang đọc c7 (ĐM kỹ
   thuật) thay c8 (ĐM thực tế) — sửa cùng đợt.
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
