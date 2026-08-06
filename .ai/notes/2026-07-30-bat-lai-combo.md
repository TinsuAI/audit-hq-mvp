# Bật lại combo — gói bằng chứng cho quyết định

Bối cảnh: `app/app_settings.py:44-49` đặt `DEFAULT_COMBOS_ENABLED = False`, lý do ghi trong
comment là 2/4 combo neo trên C4.3 đang đổi định nghĩa. P-07 (repo đề án) đã chốt số nhân
định mức = sản lượng sản xuất (không phải xuất khẩu), đo trên dữ liệu pilot cho −13% finding.
Điều kiện thứ hai để bật lại — revalidate combo trên dữ liệu thật — chưa ai làm. Note này đo
điều kiện đó và trả bằng chứng cho owner quyết.

**Phát hiện mở đầu, chặn trước mọi kết luận khác:** `app/checks/c4_norm.py:96-220`
(`check_c4_3`) hiện vẫn dùng `export_qty` (M15a) làm số nhân — CHƯA sửa theo P-07. STATUS.md
2026-07-30 tự ghi nhận: *"c4_norm.check_c4_3 vẫn dùng lượng xuất khẩu, chưa theo P-07"*. Tức
P-07 mới chốt ở tầng đề án, chưa chạm code. Toàn bộ finding C4.3 đang có trong DB — kể cả phần
đo bên dưới — vẫn là basis CŨ. Không có gì trong repo này phản ánh basis mới cả.

## 1. Bốn combo — phụ thuộc C4.3

Đọc từ `app/checks/combos.py:29-71`. Mỗi combo cần TẤT CẢ check trong `triggers` cùng fire
trên cùng `subject_key`, cùng (company, year) — `combos.py:93-101` không so theo `book`.

| Combo | Triggers | Severity | Đụng C4.3? |
|---|---|---|---|
| `COMBO_FORGED_NORM` | C2.3 + C4.3 | CRITICAL | Trực tiếp — một vế là C4.3 |
| `COMBO_ACCOUNTING_INCONSISTENT` | C2.1 + C4.3 | CRITICAL | Trực tiếp — một vế là C4.3 |
| `COMBO_UNDECLARED_SOURCE` | C1.3 + C5.1 | CRITICAL | Không — không check nào trong 2 vế gọi C4.3 hay đọc `norms`. C5.1 dùng cột `production_out_qty` của M15 (`c5_trace.py:25`) nhưng KHÔNG dùng định mức M16/số nhân — không phải cùng phép tính với C4.3, chỉ trùng tên cột. |
| `COMBO_HS_GAMING` | C3.2 + C3.3 | WARNING | Không — C3.2/C3.3 đọc mã HS + đơn vị tính, không liên quan M16/định mức. |

Kết luận phụ thuộc: **2/4 combo (`COMBO_FORGED_NORM`, `COMBO_ACCOUNTING_INCONSISTENT`) đổi
theo P-07 một khi code C4.3 được sửa; 2/4 combo (`COMBO_UNDECLARED_SOURCE`, `COMBO_HS_GAMING`)
độc lập với P-07, xét được ngay không cần chờ.**

## 2. Cơ chế điểm + hiển thị

- `app/checks/scoring.py:31` — `COMBO_BONUS = 20`, cộng CỐ ĐỊNH nếu có ít nhất 1 combo
  không-rejected (`compute_company_year_score:163-179`), không phân biệt combo nào hay bao
  nhiêu combo. `max_raw` (`scoring.py:183`) LUÔN cộng `COMBO_BONUS` dù cờ tắt — comment
  `scoring.py:440` (STATUS) ghi rõ đây là quyết định có chủ ý ("Scoring KHÔNG đổi"), không phải
  bug cần sửa cùng đợt này.
- `app/app_settings.py:159-198` — `get_combos_enabled()`/`set_combos_enabled()`: 1 cờ boolean
  toàn cục (`app_settings.key = "combos_enabled"`), cache 30s process-local. Không có cờ theo
  từng combo — bật là bật cả 4, tắt là tắt cả 4.
- `app/templates/admin_checks.html:26-40` — card "Phát hiện kết hợp (combo)" ở `/admin/checks`,
  toggle qua form POST `/admin/checks/combos-toggle`, badge "BẬT"/"TẮT" đọc thẳng
  `combos_enabled`.
- Runtime: `run_checks` recompute combo MỌI lần chạy, đọc toàn finding-set hiện có; XOÁ
  `COMBO_*` cũ VÔ ĐIỀU KIỆN mỗi lần chạy, chỉ TẠO LẠI nếu `combos_enabled=True` (theo STATUS
  2026-07-24, phần WS2). Đây là chi tiết vận hành quan trọng cho mục 3 bên dưới.

## 3. Đo trên DB thật (read-only, `mode=ro`)

Đếm distinct `subject_key` giao nhau giữa 2 vế trigger của mỗi combo, trên finding
`status != 'rejected'` đang có trong DB hôm nay (basis C4.3 CŨ) — đây là cận trên dưới basis
cũ, không phải con số sau P-07.

| Combo | Company/kỳ | |C4.3 hoặc vế A| | |vế B| | Giao (numerator) | Hợp (denominator) |
|---|---|---|---|---|---|
| COMBO_FORGED_NORM (C2.3+C4.3) | PILOT_002/2025 | C2.3=0 | C4.3=27 | **0** | 27 |
| | PILOT_006/2024 | C2.3=0 | C4.3=564 | **0** | 564 |
| | PILOT_006/2025 | C2.3=0 | C4.3=1772 | **0** | 1772 |
| | PILOT_004/2025 | C2.3=0 | C4.3=8 | **0** | 8 |
| COMBO_ACCOUNTING_INCONSISTENT (C2.1+C4.3) | PILOT_002/2025 | C2.1=0 | C4.3=27 | **0** | 27 |
| | PILOT_006/2024 | C2.1=0 | C4.3=564 | **0** | 564 |
| | PILOT_006/2025 | C2.1=0 | C4.3=1772 | **0** | 1772 |
| | PILOT_004/2025 | C2.1=0 | C4.3=8 | **0** | 8 |
| COMBO_UNDECLARED_SOURCE (C1.3+C5.1) | PILOT_002/2025 | C1.3=0 | C5.1=0 | **0** | 0 |
| | PILOT_006/2024 | C1.3=32 | C5.1=0 | **0** | 32 |
| | PILOT_006/2025 | C1.3=43 | C5.1=0 | **0** | 43 |
| | PILOT_004/2025 | C1.3=13 | C5.1=0 | **0** | 13 |
| COMBO_HS_GAMING (C3.2+C3.3) | PILOT_002/2025 | C3.2=14 | C3.3=3 | **0** | 17 |
| | PILOT_006/2024 | C3.2=467 | C3.3=67 | **28** | 506 |
| | PILOT_006/2025 | C3.2=776 | C3.3=31 | **7** | 800 |
| | PILOT_004/2025 | C3.2=1 | C3.3=4 | **0** | 5 |

Ghi chú số liệu: toàn DB hiện có **0 finding C2.1, 0 finding C2.3, 0 finding C5.1** ở mọi
(company, kỳ) — không phải riêng đợt đo này, là toàn bộ 4 công ty pilot đang nạp. `C2.1`/`C2.3`
định nghĩa ở `app/checks/c2_balance.py:32,150`; `C5.1` ở `app/checks/c5_trace.py:15` — cả ba đều
là check built-in, ĐÃ implement (không phải W.I.P.), chỉ đơn giản không fire trên dữ liệu pilot
hiện có. Hệ quả: **3/4 combo (kể cả 2 combo neo C4.3) cho giao = 0 ở MỌI company-kỳ đang có,
bất kể basis C4.3 cũ hay mới** — vì vế còn lại (C2.1/C2.3/C5.1) rỗng tuyệt đối, không phải vì
C4.3 chưa đúng basis.

### Vì sao `COMBO_HS_GAMING` = 28 dòng ở PILOT_006/2024 nhưng 0 dòng ở 2025 (đã tồn tại trong DB)

Đây LÀ dữ liệu đã lưu (`findings.check_code='COMBO_HS_GAMING'`), không phải số đo lại — bảng
group-by xác nhận đúng 28 dòng gắn `(company_id=8, period_year=2024)`, 0 dòng ở
`(8, 2025)`. Nhưng đo lại giao C3.2∩C3.3 trên finding hiện có (bảng trên) cho **7** subject đủ
điều kiện ở 2025 — KHÔNG phải 0. Vậy 0 lưu trong DB không phản ánh đúng dữ liệu hiện tại.

Nguyên nhân nằm ở lịch sử chạy, đọc từ `check_runs`: company 8 (PILOT_006) có **check_runs cho
2025** (17 dòng, `ran_at=2026-07-24 18:54:21`, một lần full-run) nhưng **KHÔNG có dòng
check_runs nào cho 2024** (bảng `check_runs` không tracking 2024 — dữ liệu 2024 chưa từng chạy
lại từ khi WS3 thêm tracking này). Cơ chế combo (mục 2) xoá `COMBO_*` VÔ ĐIỀU KIỆN mỗi lần
`run_checks` chạy, chỉ dựng lại nếu `combos_enabled=True`. Full-run 2026-07-24 cho 2025 chạy
SAU khi cờ `combos_enabled` mặc định TẮT đã có hiệu lực → xoá sạch combo cũ của 2025, không
dựng lại → 0. 2024 chưa từng bị chạy lại từ mốc đó nên 28 dòng combo cũ (từ trước khi có cờ)
còn nguyên — và trùng khớp với số đo lại hôm nay (28) vì C3.2/C3.3 của 2024 cũng chưa đổi từ
đó tới giờ. Nói cách khác: **28 vs 0 là dấu vết lịch sử chạy (cache combo cũ/mới), không phải
2024 và 2025 có tỷ lệ HS bất nhất khác nhau về bản chất** — bằng chứng là 2025 vẫn có 7 subject
đủ điều kiện ngay trong dữ liệu hiện tại, chỉ là chưa được dựng lại thành finding.

## 4. Đo này KHÔNG cho biết được gì

Số ở mục 3 là cận trên dưới **basis C4.3 cũ** (export_qty) — vì code hiện tại vẫn chạy basis
đó (mục mở đầu). Số sau P-07 (basis production_out) đòi phải **chạy lại C4.3 trên dữ liệu thật**,
đây là thao tác ghi dữ liệu, chưa ai được uỷ quyền chạy. Vì C2.1/C2.3/C5.1 = 0 tuyệt đối và
không đổi bởi P-07 (không đọc M16/định mức), số C4.3 sau P-07 gần như chắc vẫn cho giao = 0 ở
2 combo neo C4.3 — nhưng đây là suy luận, KHÔNG phải đo, và chỉ đúng chừng nào C2.1/C2.3/C5.1
còn rỗng.

Quy trình chạy lại đã có sẵn trong repo (STATUS.md, đợt 004-recheck 2026-07-27), phải theo
đúng chứ không tự đặt lại:

1. **Backup WAL-safe trước khi đụng gì:** `sqlite3.Connection.backup()` (không phải `cp` — mất
   dữ liệu WAL nếu copy file trần, xem memory `sqlite-wal-copy-gotcha`), copy cả gốc lẫn
   `-wal`/`-shm`, đặt tên `db-data/audit_hq.sqlite.bak-pre-<việc>-<timestamp>`, chạy
   `PRAGMA integrity_check` = `ok` trên bản backup.
2. **Dry-run trên BẢN COPY**, không đụng file gốc: trỏ `DATABASE_URL` sang bản copy, chạy
   `python -m app.pipeline.run_checks --company <code> --year <year> --check C1.1 … --check C6.1`
   (hoặc scoped đúng combo cần, nhưng combo đọc TOÀN finding-set nên phải chạy đủ 17 check nếu
   muốn combo đúng).
3. **Diff finding cũ/mới** trên bản copy (đếm theo check_code, xem CRITICAL nào biến mất/xuất
   hiện — như đợt 004: 74→65, 9 removed/0 added, soát từng dòng trước khi tin).
4. Chỉ sau khi diff khớp kỳ vọng mới chạy lại LIVE trên DB thật, với cùng backup ở bước 1 làm
   điểm rollback (`docker stop` → `cp` bản bak đè → xoá `-wal`/`-shm` → `docker start`).

Việc này CHƯA làm — vì (a) C4.3 code chưa sửa theo P-07 nên chạy lại bây giờ vẫn ra basis cũ,
không giải quyết được gì; (b) đây là thao tác ghi trên prod, cần owner chốt trước, đúng quy
trình dự án ("Rules" CLAUDE.md — không tự ý ghi dữ liệu thật).

## 5. Khuyến nghị

**Giữ combo TẮT, nhưng tách việc: sửa `check_c4_3` theo P-07 trước (code, không đụng DB), rồi
mới lặp lại đo này để xác nhận 2 combo neo C4.3 vẫn cho giao = 0 (nhiều khả năng có, vì
C2.1/C2.3/C5.1 rỗng không phụ thuộc C4.3) — sau đó chạy dry-run mục 4 rồi mới bật.** Lý do:
cờ combo là toàn cục (không tắt được riêng từng combo), mà điều kiện gốc để tắt ("C4.3 chốt")
mới đúng ở tầng đề án — code repo này chưa phản ánh, nên bật ngay bây giờ vẫn phát hành combo
dưới basis mà chính comment trong `app_settings.py` nói là sai. `COMBO_HS_GAMING` tuy độc lập
với C4.3 và có tín hiệu thật (28/7 subject ở PILOT_006), nhưng không tách bật riêng được khỏi
2 combo kia bằng cờ hiện có.
