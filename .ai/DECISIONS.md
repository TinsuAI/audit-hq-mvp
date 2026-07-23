# DECISIONS — Audit-HQ MVP

Ghi lại các quyết định kiến trúc và phạm vi. Mỗi entry: ngày, quyết định, lý do, alternatives đã loại.

## 2026-05-21 — Khởi tạo MVP

### 1. Repo riêng thay vì monorepo với `audit-hq`

**Quyết định:** Tạo `TinsuAI/audit-hq-mvp` riêng, không bỏ chung với `audit-hq`.

**Lý do:** `audit-hq` là repo đề án (docs, không code). Repo MVP có code Python, Docker, deploy — scope khác hẳn. CLAUDE.md `audit-hq` cấm tạo .py.

**Alternatives loại:** monorepo (rejected vì làm đề án phức tạp lên + lẫn build artifact); npm-style workspaces (rejected vì không cần JS).

### 2. SQLite cho cả dev và demo

**Quyết định:** SQLite. Switch sang Postgres khi thí điểm thật.

**Lý do:** Đơn giản nhất — 1 file, không service riêng. Đề án §5.2 cho phép. Demo 5 DN × 4 năm ~ vài chục nghìn dòng — SQLite thừa năng lực.

**Alternatives loại:** Postgres dev (over-engineer cho 10 tuần demo); MySQL (không có lý do).

### 3. Basic-auth cookie thay vì OAuth/SSO

**Quyết định:** 1 cặp user/password share cho HQ, lưu trong env var. Session signed cookie (itsdangerous).

**Lý do:** Demo URL `audit-hq-demo.tinsu.ai`, chỉ HQ vào xem. Không cần multi-tenant.

**Alternatives loại:** OAuth (overkill); HTTP Basic header (UX kém — popup browser); không auth (an toàn dữ liệu kém).

### 4. Approach A — dữ liệu thực anonymize, không sim thuần

**Quyết định:** Tuần 7 anonymize 5 DN từ 6 DN thực Trọng Tín gửi (2026-05-20); tuần 8 inject sai phạm chủ đích để kịch bản demo đẹp.

**Lý do:** Đã có dữ liệu thực 622 file 6 DN, bỏ qua tuần sim từ scratch. Demo trung thực hơn — số liệu thực sự.

**Mapping DN demo:**
- DN_001 (điện tử) ← GROWATT
- DN_002 (cơ khí) ← KIM_LONG hoặc HIEP_QUANG trích đoạn
- DN_003 (dệt may) ← HONG_AN (case study cúc áo C4.4)
- DN_004 (hoá chất) ← DO_THANH
- DN_005 (sạch) ← HONG_PHUC
- HIEP_QUANG dự bị regression test liên kỳ

**Alternatives loại:** Sim thuần (phí 2 tuần); chỉ anonymize không inject (demo có thể nhạt).

### 5. FastAPI + Jinja2 server-side, không SPA

**Quyết định:** Server-side templates với Jinja2. KHÔNG React/Vue/HTMX cho MVP.

**Lý do:** Demo 5 phút, 3-4 trang. SPA chi phí dev + build chain không đáng.

**Alternatives loại:** HTMX (cân nhắc lại tuần 9 nếu cần partial reload); SPA (over-engineer).

### 7. Adapter trả về dataclass, không trả Pydantic / pandas DataFrame trực tiếp (2026-05-21)

**Quyết định:** Mỗi adapter (`parse_m15`, ...) trả về `@dataclass` thuần (vd `M15File(header, rows, source_file)`, `M15Row(...)`). Không expose pandas DataFrame ra ngoài adapter.

**Lý do:**
- Type-safe (LSP/autocomplete trong IDE), dễ test.
- Tách rời Excel parsing layer khỏi business logic — sau này swap pandas sang polars hoặc openpyxl raw không ảnh hưởng caller.
- Pydantic có overhead validation không cần ở tầng adapter (đã trust schema sau khi parse).

### 8. Pipeline ingest idempotent: xoá rồi insert lại (2026-05-21)

**Quyết định:** `ingest()` delete toàn bộ rows của `(company_id, period_year)` trước khi insert. Re-run cùng command sẽ ghi đè.

**Lý do:** Trong dev, sẽ tinker schema + chạy lại liên tục. Tránh dup data. Khi cần audit lịch sử, dùng git/snapshot.

### 10. Severity là string column (không enum DB) (2026-05-21)

**Quyết định:** `Finding.severity` lưu string (`critical`/`warning`/`info`). Python side dùng `StrEnum` cho type safety.

**Lý do:** SQLite không có ENUM native; portable. Enum string nên `==` vẫn work giữa Python và DB.

### 11. Detect loại hình DN bằng count BCCT, không hỏi user (2026-05-21)

**Quyết định:** `detect_company_type(session, company_id, year)` đếm dòng BCCT theo mã loại hình → chọn nhóm SXXK/DNCX/Gia công có nhiều dòng nhất.

**Lý do:** Auto-detection thuận tiện cho demo. HQ không phải khai báo. Đề án §4.0 đã list mã rõ ràng nên heuristic an toàn.

**Hạn chế:** DN hỗn hợp (vd vừa SXXK vừa DNCX) sẽ bị classify theo loại lớn hơn. Khi xảy ra, sẽ thêm field `Company.company_type` override.

### 12. Finding lưu evidence_refs dạng JSON filter, không dùng FK (2026-05-21)

**Quyết định:** `Finding.evidence_refs` là JSON list, mỗi item dạng `{"table": "nvl_balances", "filter": {"company_id": 1, "period_year": 2024, "material_code": "X"}}`.

**Lý do:**
- Truy nguồn về dòng dữ liệu Tầng 1 (§2.2 đề án) nhưng tránh ràng buộc FK cứng — vì Finding có thể trỏ đến **nhiều** dòng (Σ tờ khai theo mã), không phải 1-1.
- Filter dict tự document được — đọc finding biết ngay "truy nguồn ở đâu" mà không cần load row.
- Khi xoá rows Tầng 1 + reingest, Finding cũ bị xoá trước (idempotent), không có FK orphan.

**Trade-off:** Không kiểm tra integrity tự động. Test: viewer UI sẽ resolve filter → query → hiển thị.

### 9. Mẫu 16 hỗ trợ 2 format song song (2026-05-21)

**Quyết định:** Adapter `parse_m16` tự detect format theo sheet name:
- `BCTT39` / `Bcqt` → mẫu TT39 chuẩn (data từ row 11, col 1-7)
- `Sheet1` → format DINHMUC tự do (data từ row 1, col 1-9)

**Lý do:** DN nộp 2 format khác nhau (HONG_AN có cả 2 file cùng năm). Forward-fill mã SP để xử lý layout parent-child trong cả 2 format.

### 6. Symlink `data/` thay vì duplicate

**Quyết định:** `audit-hq-mvp/data` là symlink tới `audit-hq/data/raw/`. Cả 2 repo gitignore raw.

**Lý do:** Tránh duplicate 500MB. Source of truth duy nhất.

**Trade-off:** Developer mới clone phải tự `ln -s ../audit-hq/data/raw data` — note trong README.

### 13. `period_year` là khoá thời gian chung; BCCT suy từ `declaration_date` (2026-06-04)

**Quyết định:** Mọi bảng Tầng 1 (NvlBalance/M15, SpBalance/M15a, Norm/M16, DeclarationLine/BCCT) đều có cột `period_year`. Tất cả check query bằng `period_year`. Riêng BCCT: `period_year` **suy từ `declaration_date.year` của từng dòng** lúc ingest, không gán cứng tham số `year`.

**Lý do:**
- M15/M15a/M16 là **báo cáo theo kỳ quyết toán**, KHÔNG có ngày từng dòng — chỉ BCCT có `declaration_date`. Phần lớn check là đối chiếu chéo BCCT ↔ M15/M16, cần một chiều thời gian chung cho cả 4 bảng. Đơn vị phát hiện cũng là cặp **(DN, năm)**. → `period_year` là khoá join duy nhất khả dụng.
- "Kỳ quyết toán" là khái niệm hành chính (DN nộp BCQT cho kỳ nào), không nhất thiết = năm dương lịch — nên `period_year` (kỳ) tách biệt `declaration_date` (mốc giao dịch).
- Gán `period_year` từ tham số `year` (như trước) gây bug file gộp nhiều năm (dòng 2023 lọt vào kỳ 2025). Suy từ `declaration_date.year` loại bug này tận gốc; số dòng kỳ khác bị loại được đếm vào `IngestStats.bcct_other_year` (không cắt âm thầm).

**Vì sao KHÔNG nạp cả file BCCT một lần (giữ vòng lặp per-year):**
- Whitelist năm gắn với **năm có BCQT**. File BCCT có thể chứa năm chưa có BCQT (vd GROWATT 2026) → không có settlement để đối chiếu → nạp vào chỉ tạo finding rác.
- DN có cả file per-year lẫn file gộp (HONG_AN) → nạp hết một lần sẽ **trùng** năm; cơ chế per-year + fallback multi_year hiện tại đảm bảo mỗi năm đúng 1 nguồn.

**Alternatives loại:** dùng thẳng `declaration_date` trong check (rejected — M15/M16 không có ngày, không join được); decouple BCCT ingest toàn DN (rejected — vỡ curation theo BCQT + trùng nguồn).

### 14. Phân quyền theo DN — nội bộ, một ranh giới chung cho UI lẫn AI (2026-06-14)

**Bối cảnh:** chuyển mục tiêu từ demo nội bộ sang **thí điểm thật, dữ liệu BCQT thật**. User chốt mô hình **(a) nội bộ**: chỉ người Trọng Tín/cơ quan dùng, mỗi officer được phân công một số DN; **khách (DN) KHÔNG đăng nhập**. 2 role (admin/officer).

**Quyết định:**
- Bảng nối `user_companies` (nhiều-nhiều). Officer chỉ thấy DN được gán; admin = sentinel "không giới hạn" (`allowed_* → None`). DN ngoài phạm vi trả **404** (không phải 403) để không lộ tồn tại.
- Cưỡng chế **server-side ở mọi lối vào**: `app/scoping.py` (`allowed_company_ids/codes`, `get_company_or_404`, `can_access_company_id`) dùng ở mọi route `/companies/{code}` + `/findings/{id}` và lọc danh sách DN.
- **AI chat dùng CHUNG ranh giới đó** — đây là điểm cốt lõi: nếu chỉ khoá UI mà không khoá tool thì officer hỏi AI "liệt kê hết DN" là lách. `run_tool(..., allowed_codes)` chặn tool theo `company_code` + lọc `list_companies`/`get_finding`; **`query_sql` lọc bằng TEMP VIEW** shadow `v_*` với `WHERE company_code IN (allowed)` (an toàn cả với COUNT/SUM — wrap LIMIT ngoài không đủ; schema-qualified `main.v_*` bị guard chặn).
- Người tạo DN tự-được-gán DN đó (officer tạo xong vẫn thấy).

**Lý do không làm (b) multi-tenant:** user chốt nội bộ; tenant layer là chi phí thừa cho pilot này. Schema giữ sạch để thêm sau nếu cần.

**Phạm vi:** **P1** (cô lập dữ liệu) ✅ + **P2** (siết auth) ✅. P3 (redesign chat: context phân-giải-cao + history dễ duyệt) chưa làm.

**P2 đã làm (2026-06-14, migration `c2d3e4f5a6b7`):**
- **Đổi mật khẩu**: trang tự đổi ở `/change-password` (menu user) — GIỮ. ~~Buộc đổi lần đầu~~ **đã GỠ theo yêu cầu user (2026-06-14, "hơi phiền")**: bỏ gate trong `require_user`, không set cờ khi admin tạo/đặt lại. Plumbing giữ lại (cột `users.must_change_password`, field `SessionUser.must_change`, tham số `set_password(must_change=)`) để bật lại dễ nếu cần. Vẫn **cảnh báo to lúc startup** nếu `AUTH_PASSWORD` mặc định.
- **Rate-limit login** (`app/login_guard.py`): khoá tạm theo IP sau 8 lần sai/5 phút (in-memory, reset khi restart — đủ làm chậm brute-force cho 1 process pilot).
- **Nhật ký truy cập** (`AccessEvent` + `app/audit.py`): ghi egress/hành động (tải file, xuất Excel, xuất truy vấn, chạy kiểm tra). Xem ở `/admin/audit` (admin-only). KHÔNG ghi lượt xem trang (nhiễu).
- **Validate magic-byte upload**: chặn file đổi đuôi (xlsx=`PK`, xls=OLE2) trên cả 2 đường upload, cộng kiểm size + đuôi sẵn có.

**Alternatives loại:** ẩn menu/nav theo role (rejected — không phải bảo mật thật, data vẫn query được); chỉ thêm role không theo DN (rejected — không giải quyết "officer thấy mọi DN"); multi-tenant (hoãn — vượt scope pilot nội bộ).

### 15. Bố cục Mẫu 15/15a/16 lạ — suy map cột từ dòng đánh số của chính file, kiểm chứng bằng đẳng thức của biểu (2026-07-22)

**Bối cảnh:** bộ dữ liệu 3 DN do cán bộ cung cấp có bố cục khác 6 DN đang chạy. 004 chèn thêm cột `Mã kế toán` và tách `Tồn đầu` thành 3 cột con, `Nhập` thành 5 (`6a`–`6d` + Tổng) — đọc bằng vị trí cột cố định thì mọi trường đều sai. Hướng cũ (`notes/12` Tầng D) là viết **layout spec theo từng DN**.

**Quyết định:** KHÔNG viết spec theo DN. Bố cục lấy từ chính file, rồi **chứng minh bằng số học**:

1. Đọc **dòng đánh số** `(1) (2) … (12)` của sheet → map *số biểu → chỉ số cột*.
2. Cột tổng của biểu **tự ghi công thức** dưới dạng text, vd `(11)=(5)+(6)-(7)-(8)-(9)-(10)`. Tính đẳng thức đó trên **mọi dòng**; chỉ nhận map khi khớp gần như toàn bộ.
3. Mẫu 16 không có đẳng thức cân đối. Nơi DN thêm cột sản lượng thì kiểm bằng `lượng NVL dùng theo định mức = định mức × sản lượng` (sản lượng chỉ có ở dòng đầu khối → forward-fill).
4. **AI chỉ là bước SỬA**, chạy khi (1) hoặc (2) hỏng: đưa header + vài dòng + đẳng thức đang sai cho LLM đề xuất map, rồi **bắt buộc chạy lại bước (2)**. Mô hình không có tiếng nói cuối. Cán bộ xác nhận; map đã nhận cache theo vân tay bố cục.

**Số đo (đã chạy trên dữ liệu thật):**

| | đẳng thức khớp |
|---|---|
| 004 EPE Mẫu 15 | 104/104 |
| 006 Mẫu 15 (2024 · 2025) | 7.882/7.882 · 10.560/10.560 |
| 004 EPE Mẫu 15a | 43/43 |
| 006 Mẫu 15a (2024 · 2025) | 436/436 · 501/501 |
| 004 Mẫu 16 — `lượng dùng = định mức × sản lượng` | 664/664 |
| 004 cột con: `(5)=Tồn E13+E11` · `(6)=6a+6b+6c+6d` · `Tổng xuất` | 104/104 mỗi cái |

**Lý do:** kiểu hỏng nguy hiểm ở đây KHÔNG phải "không đoán được bố cục" mà là "**map trông hợp lý nhưng ra số sai, im lặng**". Đã xảy ra thật: whitelist tên sheet chọn đúng `Sheet1` của một workbook Mẫu 15 — nhưng đó là bảng cân đối tồn kho 9 cột — và DN đó nạp 41 dòng rác/năm suốt nhiều kỳ, `material_code` giữ số thứ tự. Vì vậy thứ có **thẩm quyền** phải là đẳng thức, không phải mô hình (cũng không phải bảng từ khoá). Bản thân file đã mang sẵn map — không cần đoán. Bước AI nằm ở **ingest-time**, không nằm trong rule logic (`CLAUDE.md`), và map được *chứng minh + ghi lại* nên không vi phạm truy nguồn.

**Cạm bẫy đã gặp (đừng mất công lại):**
- 004 gõ `-6` thay cho `(6)` ở dòng đánh số → regex bỏ mất số hạng → đẳng thức tụt còn 11/104. Parser **phải chịu được nhãn hỏng**; đây chính là chỗ AI đáng giá.
- 004 sổ GC (Mẫu 15a) dùng **nhãn gộp**: `(10) = (5)+(6ab)-(7)-(8ab)-(9abc)` trong khi cột đánh `(6a)(6b)`, `(8a)(8b)(8c)`, `(9a)(9b)(9c)` → phải khai triển nhóm trước khi tính.
- 002 (bản xuất ECUS) **không có** dòng đánh số — nhưng đúng bố cục chuẩn nên đường cột cố định vẫn đúng. Dòng đánh số chỉ xuất hiện ở bản làm tay.
- Ô gộp: dòng tiêu đề con đọc qua pandas gần như rỗng (giá trị chỉ nằm ở ô neo).

**Hệ quả:** thay được phần lớn Tầng D — không cần spec theo DN. Mở đường cho `Norm.product_qty` + nhánh `Σ(định mức khối × sản lượng khối)` của C4.3, vì cột sản lượng giờ xác định và kiểm chứng được (664/664).

**CHƯA quyết — cần sửa đề án trước:** dùng sản lượng của Mẫu 16 làm hệ số nhân thay `xuất_khẩu_M15a` là **đổi định nghĩa C4.3** (`de-an-audit-hq.md:228` ghi rõ `Σ(định_mức × xuất_khẩu_M15a)`). Cùng nhóm với B2 (đổi sang lượng nhập kho sản xuất) và với quy ước `import_qty := cột (6b)` của `audit-hq-pilot/notes/09`. Cả ba phải update `../audit-hq/de-an-audit-hq.md` trước khi vào code.

**Alternatives loại:**
- *Layout spec viết tay theo DN* (rejected — không mở rộng được; đã đo 004 EPE và 004 GC khác nhau ngay ở cùng vị trí cột `(8)`, tức một spec/DN vẫn chưa đủ, phải một spec/sổ).
- *AI sinh map rồi dùng thẳng* (rejected — đúng kiểu hỏng "sai mà trông đúng", không kiểm được, vi phạm truy nguồn).
- *Chỉ dò theo từ khoá tên cột* (rejected — đã đo hỏng: `tồn đầu` không khớp `Lượng NL, VT tồn kho đầu kỳ`; `Xuất khẩu` khớp nhầm `Mã sản phẩm xuất khẩu` ở cột 1).

**Đã thực hiện (2026-07-23) — Mẫu 15:** `app/adapters/extended_layout.py`. Suy map từ dòng
đánh số + số biểu→trường CỐ ĐỊNH của Mẫu 15 (ổn định: 006 nén lẫn 004 mở rộng đều
`(11)=(5)+(6)-(7)-(8)-(9)-(10)`), chứng minh bằng đẳng thức trên ≥98% dòng. Chạy trong
`parse_m15` CHỈ khi `select_sheet` (đường cột cố định) trượt → 6 DN whitelist không đổi
(verify 419 finding y hệt). 004 EPE M15 nạp 104 dòng (đẳng thức 0/104 sai), 004 GC 37 dòng
(0/37). Bug đã sửa trong lúc làm: số hạng ĐẦU của công thức `(5)+(6)-...` không có dấu →
regex bỏ mất → 004 GC "lọt" giả vì tồn đầu của nó toàn 0; cổng đẳng thức bắt được.

**CHƯA thực hiện — Mẫu 15a (và độ chính xác cột Mẫu 16 của 004):**
- **M15a mở rộng không làm đợt này** vì số biểu KHÔNG ổn định: 006 là `(10)=(5)+(6)-(7)-(8)-(9)`,
  004 EPE là `(11)=(5)+(6)+(7)-(8)-(9)-(10)` (11 số, (6)(7) đều cộng), 004 GC dùng nhãn
  gộp `(6ab)(8ab)(9abc)`. Xác định cột `export_qty` phải dựa nhãn phân mảnh ("đăng ký tờ
  khai"/"xuất bán"/"xuất kho để…") — map sai thì C4.3 ra số sai âm thầm, đúng kiểu hỏng
  ADR này chống. → 004 hiện nạp **không có M15a**: C4.3/C1.4 KHÔNG chạy (đúng, thà không có
  hơn sai). Đây là việc tiếp theo, cần map M15a theo nhãn + cổng đẳng thức riêng.
- **Cột định mức Mẫu 16 của 004**: file có `ĐM kỹ thuật` (c7) và `ĐM thực tế` (c8); adapter
  đọc c7. Chưa sửa — Mẫu 16 không có đẳng thức cân đối để gate; và C4.3 đang tắt nên chưa
  fire số sai. Làm cùng đợt M15a.

### 16. C1 — kỳ báo cáo custom-date: BCCT chọn theo cửa sổ `[from,to]`, `period_year` là nhãn kỳ (2026-07-24)

**Bối cảnh:** DN năm tài chính 01/04–31/03 (PILOT_002/004). Ingest cũ (ADR #13) gán
`DeclarationLine.period_year = declaration_date.year` và chỉ giữ dòng `== year` → cắt phần
tờ khai rơi sang năm dương lịch khác. Đo: PILOT_002 (folder kỳ 2025 = FY 01/04/2025–31/03/2026)
mất đúng **3.014/11.115** dòng (các dòng Jan–Mar 2026). 006 dương lịch → mất 0.

**Quyết định (đường RẺ — `notes/12` khuyến nghị; đường ĐẦY ĐỦ thêm from/to vào mọi dòng
4 bảng đã bị `notes/12` "KHÔNG làm" #4 loại):**
- Thêm bảng `company_periods(company_id, period_year, period_from, period_to, is_manual)`,
  unique `(company_id, period_year)` (migration `e4f5a6b7c8d9`).
- BCCT chọn theo **cửa sổ kỳ** `period_from ≤ declaration_date ≤ period_to` (bao biên; dòng
  thiếu ngày → quy về kỳ đang nạp), thay `declaration_date.year == year`.
- **`period_year` = NHÃN kỳ** (`year`, tên thư mục whitelist), tách hẳn khỏi `declaration_date`.
  Đây là phần ADR #13 mới làm nửa vời — nay hoàn tất. `period_year` VẪN là khoá join duy nhất
  (17 check không đổi chữ ký; verify: `app/checks/` không chỗ nào suy năm từ `declaration_date`).
- **Suy cửa sổ** (`app/pipeline/period.py:resolve_period_bounds`), ưu tiên: bản `is_manual`
  cán bộ sửa tay > tiêu đề file (`CompanyHeader.period_from/to`, đủ cả 2 ngày) > **dương lịch**
  `[year-01-01, year-12-31]`. Default dương lịch giữ 6 DN whitelist BẤT BIẾN (harness: finding
  y hệt trước/sau, off_year=0 mọi cặp).
- **Frontend:** trang tài liệu hiện cửa sổ kỳ mỗi năm + form sửa (`POST .../documents/period`,
  lưu `is_manual=True`) + nút "về mặc định" (`is_manual=False`, ingest sau tự suy lại) + banner
  "nạp lại để áp dụng". Re-ingest **tường minh** qua nút Nạp/Chạy sẵn có — không tự động ngầm.

**Chống rò giữ nguyên:** cửa sổ năm tài chính liền kề KHÔNG chồng nhau → mỗi `declaration_date`
rơi tối đa 1 kỳ; dòng năm khác của file gộp vẫn ngoài cửa sổ → vẫn bị loại (đếm vào
`bcct_other_year`, không cắt âm thầm). `company_periods` KHÔNG nằm trong wipe per-(DN,năm) nên
bản sửa tay sống sót re-ingest.

**Giới hạn có chủ đích (chưa làm):**
- **Cửa sổ SỬA TAY có thể chồng nhau giữa 2 năm** → tờ khai trong vùng chồng đếm ở cả 2 kỳ.
  Đường tự động không bao giờ chồng (FY liền kề); chỉ xảy ra khi cán bộ nhập sai. Route validate
  `from ≤ to` nhưng CHƯA kiểm chồng lấn chéo năm. Mitigation (log/cảnh báo khi chồng) hoãn —
  demo dùng đường tự động, an toàn.
- **Re-ingest cần file nguồn:** sửa kỳ chỉ phục hồi dòng khi nạp lại từ file gốc. Prod 10/14 DN
  không có file → sửa kỳ chỉ đổi nhãn. Pilot 002/004 có file local → chạy được.
- `dry_run` (CLI) đếm bằng cửa sổ tự động, bỏ qua override — số xem trước có thể lệch.

**Không đụng catalog/đề án:** đổi *dòng BCCT nào lọt vào kỳ* + schema, KHÔNG đổi mô tả check
nào (khác B2/B4 đổi định nghĩa hệ số nhân). → không cần update `../audit-hq/` trước.

**Đã thực hiện (2026-07-24):** model + migration + `period.py` + ingest (2 điểm lọc) + route +
template + **pass hiển thị nhất quán**. 22 test mới, full suite xanh. Harness: PILOT_002 phục hồi
đúng 3.014 dòng (window tự đọc 2025-04-01..2026-03-31), whitelist 1.331 finding bất biến (mốc
"419" trong STATUS cũ đã lỗi thời — code cũ cũng cho 1.331).

**Hiển thị (review "Năm X" mơ hồ):** nhãn `period_year` in như năm dương lịch ở company_detail/
item_detail gây hiểu nhầm cho DN năm tài chính (tờ khai ngày 2026 dưới nhãn "2025"). Thêm
`load_period_windows()` (chỉ kỳ ≠ dương lịch) → hiện "năm tài chính dd/mm/yyyy–dd/mm/yyyy" ở tab
năm (sup TC), dòng chú dưới tab, phụ đề 2 section item_detail, tooltip cột Năm. DN dương lịch không
đổi. Số liệu vốn ĐÚNG (gom theo `period_year`) — đây chỉ là làm rõ nhãn, không đổi logic.
