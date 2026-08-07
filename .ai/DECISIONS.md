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

### 17. Mẫu 15a mở rộng (export theo NHÃN) + Mẫu 16 định mức thực tế + badge truy nguồn (2026-07-24)

**Bối cảnh:** hoàn thành phần "CHƯA thực hiện — Mẫu 15a" của ADR #15 cho 004. Đo trên file thật:
`select_sheet` (cột cố định) TRƯỢT cho M15a của 004 EPE/GC (mã ở c2, tách cột con), và
`content_slots` chỉ dò bằng `select_sheet` → 004 **không nạp M15a** → C4.3/C1.4 không chạy.

**Quyết định:**
- **`resolve_m15a` (`extended_layout.py`):** cổng đẳng thức cân đối như M15, NHƯNG số biểu M15a
  không ổn định giữa DN nên **KHÔNG map field theo số biểu**. Cột `export_qty` (thứ duy nhất
  C4.3/C1.4 dùng) xác định theo **NHÃN** cột (`xuất khẩu`/`export`, loại `năm trước`/`chưa đăng
  ký`/`xuất bán`/`nghiên cứu`/`trả lại`/`khác`), và bắt buộc là **số hạng TRỪ trong đẳng thức**
  (cổng đẳng thức riêng), và phải **DUY NHẤT**. Không đủ 3 điều kiện → trả None → không nạp
  (thà thiếu hơn nạp sai — đúng kiểu hỏng ADR #15 chống). Khai triển **nhãn gộp** `(8ab)`=8a+8b
  (KHÔNG gồm 8c) cho sổ GC (`parse_formula_terms` giữ nhóm chữ).
- **Discovery:** `content_slots` thử thêm đường mở rộng cho slot m15a (`_extended_m15a_ok`). Chỉ
  m15a — m15 luôn nhận theo tên file ("NVL"/"NPL"); whitelist buckets đầy theo tên nên không đụng.
- **Mẫu 16:** chọn cột ĐM theo nhãn "thực tế/Actual" khi có CẢ cột "kỹ thuật/Technical"
  (`_detect_actual_norm_col`). DN một cột ĐM → giữ cột mặc định (c7) → 6 DN whitelist bất biến.
- **Bằng chứng CÓ LƯU (không hộp đen):** `ParseProvenance` (layout `standard`/`extended`/`labeled`
  + detail) trên M15File/M15aFile/M16File → `IngestStats.provenance` → `record_parse_result` ghi
  `DataFile.parse_layout`/`parse_detail` (migration **`f5a6b7c8d9e0`**, 2 cột). Badge ở trang Tài
  liệu + note ở trang Dữ liệu gốc: bố cục, đẳng thức khớp N/N, nhãn cột export/ĐM đã chọn.

**Đo (dữ liệu thật):** 004 EPE M15a 43 dòng (43/43, export "Export this year" cột 10), M16 664
dòng (thực tế c8) → C4.3 fire 8, phát hiện 111→98. 004 GC M15a 2 dòng (2/2), M16 216 → C1.4 fire 2
(sau khi sửa kỳ tay, xem dưới). 006 vẫn đường CHUẨN (mã c1, export c7) — không đụng.

**Regression:** harness nạp mới toàn whitelist vào DB rỗng (seed_uom + ingest + run_checks) =
**419 finding, y hệt từng DN trước/sau** (DO_THANH 9 · GROWATT 175 · HONG_AN 126 · KIM_LONG 109).
Trung tính. **LƯU Ý số liệu:** 419 KHÁC "1.331" ghi ở ADR #16/STATUS — 1.331 đo bằng nguồn khác
(nhiều khả năng DB local có finding inject / gồm pilot), KHÔNG phải fresh-ingest whitelist. Cần
chốt MỘT harness chuẩn cho lần sau (xem [[harness-baseline-methodology]]).

**Kèm — sửa kỳ GC (dùng tính năng ADR #16):** header M15/M15a của GC ghi SAI kỳ (2024-04..2025-03)
trong khi M16 + BCCT là FY2025 (2025-04..2026-03). `ingest` lấy header đầu (M15) → cửa sổ rỗng →
`bcct=0` → 0 phát hiện. Đã đặt `company_periods` **manual** GC 2025 = 2025-04-01..2026-03-31 →
bcct=547, C1.4 fire. Đây là đúng ca dùng manual-override của ADR #16 (cán bộ sửa header sai).

**Alternatives loại:** *map M15a theo số biểu* (rejected — không ổn định giữa DN, đã đo); *sửa
`default_bounds` chọn header khớp năm folder* cho ca GC (hoãn — đụng logic C1 đã deploy, rủi ro
6 DN whitelist; manual-override an toàn hơn).

### 18. WS1 — Tin cậy parse theo NHÃN BẰNG CHỨNG mỗi cột + cổng review mỗi file (2026-07-24; WS1 đã cài #4–#7; SỬA + mở rộng WS2 2026-07-24 — xem **Revision — WS2** cuối ADR)

> Kết quả grill WS1 (`.ai/features/2026-07-24-parse-review-per-test-ux/brief.md`). Xương sống +
> mọi nhánh chịu lực đã chốt; còn lại là việc cơ học + nền WS3 (xem cuối).

**Bối cảnh:** luồng parse hiện tin cột theo VỊ TRÍ mà không có tín hiệu tin cậy. Đường `standard`
(`select_sheet` đạt `_MIN_SCORE=5` → áp `_COL` cố định) không kiểm số học; chỉ đường `extended`
kiểm bằng đẳng thức. Ý ban đầu — chạy lại match-rate đẳng thức mức FILE trên mọi path — bị bác:
C2.1/C2.2 (`c2_balance.py`) ĐÃ tự tính lại đúng đẳng thức đó thành finding, nên làm vậy chỉ dời
một check vào parser. Quan trọng hơn, **đẳng thức cân đối KHÔNG đủ để xác thực map cột**:
- Bất biến dưới **hoán vị hai cột cùng dấu**: đổi `production_out`↔`other_out` (đều trừ) → C2 vẫn
  xanh, nhưng C4.3 đọc riêng `production_out` → đọc nhầm cột, IM LẶNG.
- Các cột **ngoài đẳng thức** (cột con "xuất khẩu" M15a cho C1.4; cột ĐM "thực tế" M16 cho C4.3)
  không đẳng thức nào kiểm — đúng lý do ADR #17 phải thêm logic theo NHÃN riêng.
- `BALANCE_EXPECT` (`layout.py:22`) chỉ có từ khoá cho 4/6 cột cân đối m15; `reexport`(6)/
  `repurpose`(7)/`other_out`(9) KHÔNG có từ khoá → hôm nay không label-check được.

**Quyết định:**
- **Mỗi cột đọc mang MỘT nguồn bằng chứng** (định danh tiếng Anh, KHÔNG dịch), mạnh→yếu:
  `officer-confirmed` (cán bộ duyệt / map đã lưu cho form này) > `header-matched` (tiêu đề khớp) ·
  `balance-checked` (đẳng thức cân đối khớp — số vouch) > `position-only` (chỉ vị trí, không kiểm).
- Badge cho cán bộ gộp về **HAI trạng thái**: `verified` (xanh) vs `needs_review` (vàng); nguồn
  hiện ở dòng phụ khi mở. Định danh nội bộ tiếng Anh; UI render tiếng Việt ("Đã kiểm"/"Cần xác nhận")
  theo quy ước ngôn ngữ UI.
- `balance-checked` chỉ ĐỦ cho cột dùng dạng TỔNG (C2 tự tính lại); cột **dùng riêng lẻ** cần
  `header-matched`/`officer-confirmed` (đẳng thức không phân biệt hai cột cùng dấu): `production_out`
  →C4.3/C5, `repurpose`→C1.x, cột con export M15a→C1.4, cột ĐM thực tế M16→C4.3.
- **Trạng thái = `needs_review`** khi cột được một check tiêu thụ có nguồn tốt nhất là `position-only`,
  HOẶC cột dùng riêng lẻ mà nguồn tốt nhất chỉ `balance-checked`; còn lại `verified`. Cột dùng riêng
  lẻ hay dạng tổng do registry D2 (`consumed_as: individual|sum`) khai.
- **Cổng review MỖI FILE** (không mỗi check): kích khi có cột `needs_review` chưa có map lưu. Banner
  nêu cột + các check bị ảnh hưởng.
- **CẢNH BÁO, KHÔNG CHẶN:** check vẫn chạy, finding vẫn hiện, kèm cờ "dựa trên cột chưa xác nhận".
  Chặn chỉ cân nhắc nếu sau này DN tự upload hàng loạt không có cán bộ trung gian.
- **Xác nhận scope theo DN (option 2); lưu map theo `(DN, vân tay form)`.** SỬA ADR #15: xác nhận
  KHÔNG tái dùng chéo DN — DN-A duyệt không cấp `officer-confirmed` cho DN-B (lý do user chốt: một
  DN duyệt sai không được lan sang DN khác). Vân tay form vẫn CẤU TRÚC (không mã DN) nên trong CÙNG
  DN tái dùng chéo NĂM: 004 2024+2025 cùng shape → duyệt 1 lần/DN, không mỗi năm; shape đổi giữa
  năm thì vân tay bắt và hỏi lại. 6 DN whitelist mỗi DN seed `officer-confirmed` cho shape của mình.
- **Vân tay form = hash chuẩn hoá vùng tiêu đề mỗi slot:** danh sách nhãn tiêu đề cột theo thứ tự
  (dòng header đã dò) + số cột, gập hoa/dấu/khoảng trắng + bỏ chữ số năm; kèm dòng đánh số `(1)(2)…`
  khi form có (004 có, 002 không). KHÔNG chứa mã DN. Tính được ở bước profile từ vùng header
  `select_sheet` đã đọc. Rủi ro va chạm (hai bố cục cùng rỗng/thưa ở cột nhập nhằng) triệt tiêu nhờ
  số cột + dòng đánh số ở quy mô MVP.
- **6 DN whitelist seed sẵn `confirmed`** (regression 419 đã kiểm, ADR #17) → đường demo không đổi.
- **Registry test→cột (D2) = dict TĨNH trong code** (`app/checks/registry.py`), KHÔNG bảng DB.
- **Vòng đời file (state machine, HIỆN TRÊN UI):** `uploaded` (đã lưu + đăng ký, chưa đọc) →
  `analyzed` (dry-run parse: chọn sheet + map cột + tính evidence source/review state; **CHƯA ghi
  DB** — cổng review ở đây) → `parsed` (đã commit dòng vào DB); `error` nếu đọc/nạp hỏng (terminal
  tới khi tải lại). Tận dụng `ingest(dry_run=True)` sẵn có (tính stats không commit). `analyzed→parsed`
  **TỰ ĐỘNG khi `verified`**, DỪNG chờ cán bộ bấm khi `needs_review` (đường whitelist chảy suốt,
  không thêm click). Badge tin cậy (`verified`/`needs_review`) là TRỤC RIÊNG — file có thể `parsed`
  + `needs_review` (warn-not-block). Ánh xạ enum cũ (`DataFileStatus`): PENDING→`uploaded`, THÊM
  `analyzed`, OK→`parsed`, WARNING→cờ `needs_review` (không còn là status), ERROR→`error`.
- **Map lưu chứa:** map cột (`slot → field → chỉ số cột`) + evidence source mỗi cột + ai/khi nào
  xác nhận; khoá `(DN, vân tay form)`. Lưu TOÀN map (không chỉ cột lệch) để tái dựng đủ.
- **AI = bước SỬA (ADR #15), chỉ khi heuristic + đẳng thức đều trượt:** đề xuất map, BẮT BUỘC
  re-validate bằng đẳng thức, cán bộ xác nhận. WS1 chỉ lộ đề xuất trong cổng review khi cột
  `needs_review` và chưa có map lưu. KHÔNG gọi LLM trong rule logic (chỉ parse-time).
- **Staleness khi sửa map file đã `parsed`:** re-analyze → re-parse → **re-run CHỈ các check registry
  báo đọc cột đã đổi** (scoped qua D2) — **SỬA WS2: re-run này chạy qua JOB async, không còn đồng
  bộ; xem Revision cuối ADR**. WS1 KHÔNG cần cờ stale. Mô hình stale tổng quát
  (`check_runs` + `data_version`, overview `stale = based_on_run_at < ran_at`) là của **WS3** — chỉ
  cần khi re-run không tức thì + cho AI overview. Hệ quả: WS1 core build được CHỈ với registry; nền
  `check_runs`/`data_version` chỉ bắt buộc khi WS3 (overview) tới.

**Việc (đo từ code hiện có):** đường `standard` đã tính vị trí khớp nhãn trong `SheetCandidate.colmap`
rồi **vứt đi** (`parse_m15` chỉ dùng `.name`). Cần: giữ `colmap`; thêm từ khoá cho cột 6/7/9; ghi
nhãn bằng chứng vào `ParseProvenance.detail`; thêm registry; một màn review.

**Alternatives loại:** *Option A — match-rate đẳng thức mức FILE trên mọi path* (trùng C2.1/C2.2;
mù với hoán vị cùng dấu + cột ngoài đẳng thức); *cổng mỗi check* (bắt cán bộ xác nhận cùng một cột
N lần, không hơn gì việc liệt kê check bị ảnh hưởng trên một banner file).

**Còn lại (KHÔNG chặn thiết kế WS1):** nội dung `consumed_as` của registry là việc CƠ HỌC (đọc từ
code check — bảng trong brief); nền staleness tổng quát (`check_runs`/`data_version`) thuộc WS3;
phân quyền confirm trong CÙNG DN = cán bộ có quyền DN đó (ranh giới ADR #14). Xem
[[parse-confidence-evidence-model]].

---

**Revision — WS2 (chạy test lẻ + export chọn) + đổi mô hình chạy check sang ASYNC (2026-07-24, grill `/grill-with-docs WS2`)**

> Grill WS2 chốt ba nhánh dưới và SỬA quyết định "re-run inline" của WS1 ở trên. Gộp vào ADR #18
> (không tách ADR #19) theo yêu cầu owner. WS2 build được CHỈ với hạ tầng job sẵn có + registry WS1;
> **KHÔNG cần nền `check_runs`/`data_version` của WS3** — combo recompute-mỗi-lần thay cho stale-flag.

*(1) Chạy check — TẤT CẢ qua JOB QUEUE (SỬA staleness inline của WS1):*
- Không còn `run_checks(...)` đồng bộ trong request handler. Mọi lần chạy check enqueue job; worker
  là **1 thread chạy tuần tự** → serialize mọi ghi, triệt tranh chấp single-writer SQLite (đây là lý
  do chính owner chốt async). Trang `/jobs/{id}` đã auto-refresh 2s + link "→ Xem kết quả" về DN.
- `RUN_CHECKS` payload thêm `only: list[str]` (tuỳ chọn): có → chạy tập con; không → full năm.
  `BATCH_RUN` giữ nguyên (full mọi năm). `INGEST_AND_RUN` (enum) vẫn để trống, KHÔNG dùng.
- **Chạy test lẻ:** nút mỗi nhóm check ở `company_detail` → enqueue `RUN_CHECKS {only:[mã]}` theo
  **NĂM đang xem** → redirect `/jobs/{id}`. (All-years-một-check: KHÔNG làm — đã có "Tất cả năm".)
- **Cổng confirm map (SỬA `documents_confirm_review`, option A — tách confirm/run):** `save_column_map`
  + re-ingest + `record_parse_result` GIỮ đồng bộ (file lên `parsed`, map áp NGAY vì áp map = ý nghĩa
  của "confirm"); phần re-run scoped đổi thành enqueue `RUN_CHECKS {only: affected}`. Confirm LẦN ĐẦU
  (file `analyzed`, chưa finding) KHÔNG enqueue → ở lại `/documents` như cũ; re-confirm (file đã
  `parsed` + cột đổi) enqueue job → `/jobs/{id}`.
- *Loại — option B* (chỉ save map đồng bộ, re-ingest + re-run đều vào `INGEST_AND_RUN` job): đẩy cả
  việc áp map ra sau hàng đợi → file kẹt `analyzed` tới khi worker chạy; owner chọn A.

*(2) Combo (D4) — recompute MỖI lần chạy + toggle tắt toàn cục:*
- `run_checks` recompute combo trên MỌI lần chạy (lẻ hay full), đọc **TOÀN finding-set** của (DN, năm),
  không chỉ finding vừa chạy. Sửa lỗi hiện tại: chạy `only=` xoá sạch `COMBO_*` (delete vô điều kiện,
  dòng ~77-83) rồi KHÔNG dựng lại (recompute chỉ khi `only is None`) → combo biến mất tới lần full kế.
  Delete `COMBO_*` giữ vô điều kiện; chỉ RECOMPUTE mới gate theo toggle.
- **Toggle `combos_enabled`** (app_settings, `get_setting("combos_enabled", default=False)`) — **mặc
  định OFF**, một công tắc admin toàn cục (không per-combo). OFF → `run_checks` skip `detect_combos`;
  `company_detail` ẩn mục combo (gate theo setting SỐNG → flip giữa chừng ẩn ngay). **Lazy**: flip áp
  theo mỗi (DN, năm) ở lần chạy kế; demo re-run hết nên không lệch. KHÔNG eager-purge toàn bộ.
- Scoring KHÔNG đổi: `compute_company_year_score` cộng `COMBO_BONUS=20` khi `has_combo`. OFF → không
  `COMBO_*` trong DB (sau lần chạy) → `has_combo=False` → không +20. Tự nhất quán UI↔điểm.
- Lý do OFF mặc định (present-tense "hiện không make sense"): 2/4 combo neo trên **C4.3** đang đổi định
  nghĩa (số nhân = sản lượng, đề án sửa, `c4_norm.py` chưa) → combo dựng trên metric đang biến động;
  bật lại sau khi C4.3 chốt + revalidate. Combo vẫn ở catalog §2.7, chỉ tắt runtime (đảo được).

*(3) Export chọn test — EPHEMERAL, không profile:*
- `build_export(..., only: set[str] | None)`: lọc finding theo `check_code.in_(only)`; sheet chứng cứ
  M15/M15a/M16/BCCT tự thu hẹp theo subject của finding còn lại (đã key sẵn). `/export` nhận param
  `check` LẶP LẠI (`?year=&check=C1.1&check=C4.3`); **KHÔNG chọn = xuất TẤT CẢ** (nút cũ nguyên vẹn).
- UI: checkbox mỗi nhóm check + nút "Xuất các test đã chọn"; thêm "Xuất test này" ở màn drill-down.
- Combo là mã như mọi check (gồm khi chọn mã `COMBO_*`); KHÔNG logic combo riêng. Sheet Tổng quan
  **liệt kê mã đã chọn** → export lọc không nhầm thành export đủ (kỷ luật không-hộp-đen). Audit log mã.
- *Loại:* export profile lưu tên (bảng + CRUD cho nhu cầu chưa ai nêu, demo gần) — YAGNI, thêm sau nếu
  có workflow xuất lặp thật.

Xem [[parse-confidence-evidence-model]] · [[check-execution-async-via-jobs]].

---

**Revision — WS3 (AI tổng quan mỗi test + staleness) (2026-07-24, grill `/grill-with-docs WS3`, advisor fable review)**

> Grill WS3 chốt mô hình theo-dõi-lần-chạy + tổng quan AI. GREENFIELD hoàn toàn: KHÔNG có
> `check_runs`, `data_version`, hay overview lưu trữ nào hôm nay — mọi narrative AI hiện sinh LIVE
> mỗi lượt chat, chỉ `ai_conversations`/`ai_messages` persist. Gộp vào ADR #18 (không tách #19)
> theo owner. Advisor (fable) review chốt Q1–Q7, LẬT Q8 sang forward-only (sửa một sự thật sai).

*(1) Tổng quan AI — grain, trigger, cơ chế chạy:*
- **Grain = một overview mỗi `(company_id, period_year, check_code)`** (D6): tóm tắt tiếng Việt CÓ
  TRUY NGUỒN của riêng check đó cho DN-năm, render ở khối `group-actions` (`company_detail.html:240`).
  KHÔNG phải một narrative gộp mỗi DN-năm — bản gộp đã có LIVE trong chat (`_generate_report`,
  `app/ai/tools.py:674`). Grain per-check là điều kiện để staleness có nghĩa (re-run C4.3 chỉ stale
  overview C4.3).
- **On-demand, KHÔNG eager:** cán bộ bấm "Tạo tổng quan" → sinh + lưu một overview. Eager (auto sau
  mỗi `run_checks`) = hàng trăm gọi LLM mỗi BATCH_RUN, hầu hết không ai đọc. Overview là công cụ ĐỌC,
  không phải một phần kết quả kiểm toán.
- **Sinh ĐỒNG BỘ trong request, KHÔNG qua job worker.** Worker 1 thread (WS2) serialize check; một
  gọi LLM 5s ở đó sẽ CHẶN hàng đợi check. Overview chỉ ghi MỘT dòng `check_overviews` (không đụng
  finding-set) nên gần như không tranh chấp ghi → chạy trong request đúng chỗ.
  **Endpoint khai `def` THUẦN, KHÔNG `async def`:** `async def chat` (`ai.py:181`) gọi OpenAI client
  đồng bộ → CHẶN cả event loop; `def` thuần chạy trong threadpool FastAPI, chỉ tốn 1 thread. Tái dùng
  `check_rate_limit`/`check_daily_budget`, đặt timeout client tường minh, GHI DB SAU khi LLM trả (không
  để transaction ghi bắc qua lời gọi LLM).

*(2) `check_runs` — upsert, cột, status, dọn orphan:*
- **Latest-upsert**, một dòng mỗi `(company_id, period_year, check_code)`, unique bộ ba. KHÔNG
  append-history: consumer duy nhất là staleness (chỉ cần `ran_at` mới nhất); lịch sử LẦN CHẠY đã có
  ở bảng `jobs` (`payload.only`, `started_at`/`finished_at`) + `findings.created_at` (de-facto last-run
  cho check khác 0 nhờ wipe-and-recreate). Tiền lệ: `CompanyYearScore` cũng upsert.
- **Cột:** `company_id`, `period_year`, `check_code`, `ran_at`, `finding_count`, `status`, `data_version`.
- **Upsert PHẢI nằm TRONG `run_checks()`** (vòng lặp `~run_checks.py:97-115`), KHÔNG ở job handler —
  nếu không, entry CLI (`run_checks.py:190`) + fallback inline (`companies.py:1187`) không dời `ran_at`
  → false-stale. Ghi cho MỌI check đã chạy, kể cả 0 finding (đó là lý do D5: không suy từ
  `findings.created_at` — check ra 0 finding thì không có dòng finding).
- **Full run cũng DELETE `check_runs` của mã `X.*` orphan** (soi `run_checks.py:81-88` xoá finding orphan).
- **`status` = `ok`/`error` bây giờ, `not_evaluable` DÀNH SẴN (chưa build).** `error` chỉ với check
  ĐỘNG (`CheckRunError` bắt ở `run_checks.py:107-114`); check built-in raise → rollback CẢ transaction
  trước `s.commit()` → không có dòng `check_runs` nào của lần đó (nhất quán, đừng mong dòng error
  per-check cho built-in). `not_evaluable` (phân biệt "0 vì sạch" vs "0 vì thiếu dữ liệu") là việc
  **Tầng C — chờ họp**, KHÔNG front-run ở WS3; cột sẵn, phái sinh để sau.

*(3) `data_version` — GIỮ (crux), trên `CompanyPeriod`:*
- **Vì sao giữ:** đường re-ingest trần (`documents_ingest_year`, `companies.py:1196`) đổi dữ liệu mà
  KHÔNG chạy check (ingest ≠ run là hai bước cố ý; flow sửa kỳ muốn đặt kỳ giữa hai bước). Sau nó
  finding + overview stale nhưng `ran_at` KHÔNG dời → `based_on_run_at < ran_at` sai → không ai phát
  hiện. Đường confirm-review khi `changed_fields` rỗng/không map check nào cũng là ingest-không-run.
  → chỉ `ran_at` có ĐIỂM MÙ thật.
- **Số nguyên trên `CompanyPeriod`** (đã 1 dòng/DN-năm, `resolve_period_bounds` upsert MỌI lần ingest
  không dry-run → dòng chắc chắn tồn tại). Số nguyên > timestamp: `_now()` Python và
  `func.current_timestamp()` SQL là HAI đồng hồ; so bằng không cần thứ tự.
- **Ba ràng buộc cài đặt (advisor):** (a) bump version TRONG transaction của ingest → version + data
  commit nguyên tử; (b) `run_checks` đọc data_version ở ĐẦU lần chạy và ghi giá trị đó — re-ingest ở
  route-thread có thể commit GIỮA lúc worker chạy check; ghi version lúc-commit sẽ che mất; (c) upsert
  `check_runs` trong `run_checks()` (đã nêu ở 2).
- **Overview stale ⇔ `check_runs.ran_at` dời (check chạy lại) HOẶC `CompanyPeriod.data_version` dời
  (dữ liệu nạp lại từ khi sinh).**
- **Đường chưa phủ:** sửa alias/canonical UOM (`admin.py`) đổi chuẩn hoá check mà không ingest, không
  run → không tín hiệu staleness. Hiếm, chỉ admin — GHI CHÚ, không kỹ-nghệ-hoá.
- *Loại:* auto-run check khi ingest rồi bỏ data_version (chọi flow ingest→đặt-kỳ→run cố ý; re-ingest
  14 DN fan-out 14 run); chỉ `ran_at` (mù đường re-ingest — chính là hộp đen dự án bác).

*(4) Staleness UX + persistence:*
- **Flag-only:** overview stale hiện text XÁM + badge "Tổng quan đã cũ — dựa trên lần chạy trước" +
  mốc `based_on` + nút "Tạo lại"; KHÔNG auto-regenerate lúc load (company_detail là trang chính → sẽ
  gọi LLM mỗi lần xem). Đánh dấu-không-ẩn = kỷ luật không-hộp-đen.
- **Overwrite (upsert một dòng mỗi check), KHÔNG version history** — consumer duy nhất là "overview
  hiện tại + có stale không". Dòng `check_overviews` TỰ mang telemetry (`model`, `tokens_in`,
  `tokens_out`, `cost_usd`, `latency_ms`, gương `AiMessage` `models/ai.py:78-82`) → mỗi overview tự
  truy nguồn được chi phí (đây là gọi LLM tính tiền) mà không cần bảng history hay `ai_conversation`
  giả. Double-click đồng thời = hai gọi LLM last-write-wins (chấp nhận; guard in-flight theo bộ ba là
  tuỳ chọn tỉa).
- **Cột `check_overviews`:** `company_id`, `period_year`, `check_code`, `content`, `generated_at`,
  `based_on_run_at`, `based_on_data_version`, `model`, `tokens_in`, `tokens_out`, `cost_usd`,
  `latency_ms`; unique `(company_id, period_year, check_code)`.

*(5) Kỷ luật prompt (không-hộp-đen áp cho cả narrative):*
- **Nạp prompt: đếm theo severity + top-N `subject_key`, KHÔNG nạp dòng** (code tự ghi 11.003 finding
  cho một DN-năm, `companies.py:1369`). LƯU snapshot tổng hợp đó lên dòng overview.
- **Đọc `ran_at` + `data_version` + tổng hợp finding trong MỘT session/transaction** khi sinh — một
  lần chạy commit giữa chừng sẽ ghép snapshot từ hai trạng thái.
- Prompt được lệnh KHÔNG khẳng định "sạch/không bất thường" từ mỗi con số 0 (honesty tạm ở prompt tới
  khi Tầng C thêm `not_evaluable`). Cân nhắc: status triage finding (confirmed/false-positive) RESET
  về `new` mỗi lần re-run → quyết định có đưa status vào overview không.

*(6) Phạm vi — combo LOẠI, forward-only KHÔNG backfill:*
- **Combo (`COMBO_*`) KHÔNG vào `check_runs` lẫn overview:** recompute mỗi lần chạy (WS2), default OFF,
  UI `group-actions` đã guard `not code.startswith('COMBO_')` — không nút chạy lẻ, không panel per-test.
  `check_runs` chỉ theo mã check thật; overview chỉ cho check thật.
- **Forward-only, KHÔNG backfill** (LẬT so với đề xuất grill ban đầu). **Sự thật sửa:**
  `CompanyYearScore.computed_at` là mốc lần chạy ĐẦU TIÊN, KHÔNG phải mới nhất — upsert
  `run_checks.py:159-173` chỉ đổi `score`/`tier`/`breakdown`, cột `score.py:28-30` có `server_default`
  KHÔNG `onupdate` → không bao giờ dời sau insert đầu. Seed `ran_at` từ nó = đóng dấu mốc cũ hàng tuần
  (sai "lần chạy gần nhất" tệ hơn không có). Thêm nữa seed `finding_count=0` vô consumer: group dựng từ
  findings `GROUP BY` (`companies.py:1371`) → check ra-sạch không render group, không mặt overview.
  → dòng `check_runs` VẮNG = "chưa rõ" (KHÔNG stale); lần chạy thật đầu tiên tạo dòng.
- **KHÔNG "batch re-run để seed":** `run_checks` xoá finding mọi mã nó đụng và KHÔNG có carry-over
  status triage nào → populate-run RESET mọi `status` finding về `new`. Nếu SAU này cần "lần chạy" mỗi
  check cho toàn DN lịch sử ngày-một → seed từ `MAX(findings.created_at)` per (DN, năm, mã) (mốc
  latest thật cho check khác 0), KHÔNG từ `computed_at`, và để check ra-sạch không seed.

*(7) Ranh giới Q1/Q5 (làm rõ, không phát hiện ở template):* overview chỉ mặt trên GROUP đã render
(check ≥1 finding) → lệnh prompt "không khẳng định sạch từ 0" tạm CHƯA có consumer sống (check 0
finding không hiện nút overview). Ổn cho demo; ghi rõ scoping ở đây.

**WS3 build được trên:** `check_runs` + `data_version` (mới) + registry WS1 + hạ tầng LLM
`call_with_fallback` sẵn có. Thứ tự: nền `check_runs`/`data_version` (ghi trong `run_checks` +
bump trong `ingest`) TRƯỚC → overview on-demand chồng lên. Alembic head hiện `b7d2e1f4a3c6` →
migration WS3 `down_revision = "b7d2e1f4a3c6"`.

Xem [[parse-confidence-evidence-model]] · [[check-execution-async-via-jobs]] · [[ws3-overview-staleness-model]].

### 19. 004 hai loại hình — một pháp nhân = tờ khai dùng chung + N sổ quyết toán per loại hình (2026-07-25)

**Bối cảnh:** 004 (MST `0901051747`) là 1 DNCX vừa sản xuất tự sở hữu vừa gia công. DB có 2 company
row (id 9 EPE, id 10 GC). Kiểm dữ liệu 2026-07-25: `declaration_lines` của 2 row **byte-identical**
(229 tờ, 547 dòng), 100% mã DNCX (E11/E15/E42), 0 mã gia công (không E21/E23/E52/E54) → tờ khai là
MỘT list dùng chung nhân đôi. Phân biệt EPE/GC chỉ ở BCQT + định mức (M15 98 vs 37 mã, M15a 43 vs 2,
định mức 60 vs 34). Mã quy về sổ gần 1:1: 107 mã NVL nhập = 66 EPE-only + 25 GC-only + 12 chung + 4
không sổ nào; 41 mã SP xuất = 39 EPE + 2 chung.

**Vấn đề:** cả hai cách hiện có đều SAI, ngược chiều. Bản gộp Tầng-1 (219): M15 sổ này che thiếu sót
sổ kia (C1.2 sập 99→4 GIẢ). Bản 2 row tách (187): mỗi sổ đối chiếu list tờ khai TOÀN pháp nhân nhưng
chỉ M15 sổ mình → báo "thiếu M15" cho mã thuộc sổ kia. Verified: **C1.2 = 99 finding, 91 GIẢ** (GC 70
= 66 mã có trong sổ EPE + 4 thật; EPE 29 = 25 mã có trong sổ GC + 4 thật).

**Quyết định:** mô hình **"1 pháp nhân = 1 sổ tờ khai HQ dùng chung + N sổ quyết toán, mỗi sổ một loại
hình"**. Từ đúng cho trục là **"loại hình"** (enum `CompanyType`), KHÔNG phải "chế độ". Cài đặt:
- Gộp id 9 + id 10 → 1 row `PILOT_004` (MST giữ nguyên); nạp tờ khai MỘT lần (dedup — 2 bản y hệt,
  và `SUM` tờ khai của C1.1/C1.4 cần dedup nếu không nhân đôi).
- Thêm cột nullable `book` trên `nvl_balances`/`sp_balances`/`norms`, gán theo `source_file`
  (`(EPE)`→`EPE`, `(GC)`→`GC`). **Null = pháp nhân một sổ → hành vi cũ, 002/006 KHÔNG đổi.**
- Thêm `book` vào `findings` (truy nguồn per-sổ — kỷ luật không-hộp-đen).
- Check cross-layer đối chiếu tờ khai với UNION các sổ; check nội-sổ `GROUP BY book`.

**Phân loại 17 check đã cài (registry ghi "16"):**
- *Cross-layer set-only* (collapse TỰ sửa, KHÔNG đổi code): **C1.2** (91/99 finding giả biến mất),
  C1.3, C1.6.
- *Cross-layer quantity* (SUM per mã across sổ — sai cho 12 mã NVL + 2 mã SP chung): **C1.1, C1.4**.
- *Nội-sổ* (`GROUP BY book` — dict keyed-by-mã đang ghi đè mất một sổ; C4.3 còn lấy MAX 2 sổ):
  **C4.1, C4.3, C6.1**; **C3.3** (đơn vị, rủi ro thấp — chỉ sai nếu 2 sổ khai đơn vị khác nhau cho mã
  chung).
- *Neutral* (row-wise, KHÔNG đổi; mã chung ra 2 finding/2 sổ là ĐÚNG, chỉ thiếu nhãn book): C1.7,
  C2.1–C2.4, C5.1, C3.1, C3.2.

**Kết quả 004 sau fix:** C1.2 99→4 thật; C1.1/C1.4 hết double-report mã chung; định mức/tồn kho hết
trộn sổ.

**Alternatives loại:**
- Gộp Tầng-1 không tách sổ (219): khớp chéo giả, mất phát hiện thật.
- Giữ 2 row + union lúc check theo `tax_id`: không migration nhưng tờ khai vẫn nhân đôi (check SUM tờ
  khai double), client thấy 2 công ty cho 1 pháp nhân, entity concept ẩn/mong manh.
- Từ "chế độ" cho trục loại hình: loại — lệch enum `CompanyType`, từ đúng là "loại hình" (owner chốt).

**Chưa làm (scope sau):** UI breakdown EPE/GC đầy đủ (pass này chỉ correctness + `book` trên finding);
cơ chế upload gán book cho pháp nhân nhiều sổ tương lai (004 gán theo `source_file` có sẵn). Migration
nối từ head hiện tại (`b8c9d0e1f2a3` theo STATUS — xác nhận lúc cài). Xem [[pilot-004-epe-gc-merge]].

**Rà soát advisor (Fable) 2026-07-25 — sửa cách cài + rủi ro (đã verify DB/code):**
- **Gán book theo `company_id` nguồn (9→EPE, 10→GC), KHÔNG parse `source_file`.** Tên file GC thực tế là `(GC.)` / `(GC)` / `-GC`; match literal `"(GC)"` chỉ trúng 1/3 file → book=NULL → single-book semantics → trộn sổ ÂM THẦM. (Sửa mệnh đề "gán theo source_file" ở phần Cài đặt trên.) Parse filename chỉ liên quan đường upload hoãn lại.
- **Guard re-ingest (rủi ro #1, chưa flag):** `ingest()` xoá SẠCH NvlBalance/SpBalance/Norm/DeclarationLine của `(company_id, year)` rồi nạp từ MỘT thư mục company-code (`discover`). Sau collapse không có thư mục `PILOT_004` → `documents_ingest_year` lỗi, HOẶC nếu ai rename dir → xoá cả 2 sổ nạp lại 1. → thêm 1 dòng guard `raise` khi company nhiều sổ + test. (Nếu owner chốt 004 không re-ingest trước demo, hạ xuống "giới hạn ghi chú" nhưng vẫn thêm guard.)
- **C1.1/C1.4 KHÔNG phải "SUM theo mã" — theo `(mã, ĐƠN VỊ)`.** 6 mã EPE có 2 dòng M15 = cùng mã, HAI đơn vị (MTR + ROLL); vd `NO 153-BLACK` 908.259 MTR + 18.165 ROLL. Cộng across đơn vị là vô nghĩa → khoá gộp union = `(material_code, unit)`, guard `HAVING SUM>0`, nhãn `unit`/tên lấy từ dòng chọn xác định (min id) để output không nhảy. **Hệ quả:** C1.1 per-row hiện tại có thể đã ra finding GIẢ trên mã 2-đơn-vị (so dòng ROLL với tổng tờ khai mù đơn vị). Khớp đơn vị PHÍA TỜ KHAI là vấn đề PRE-EXISTING, đơn-sổ — FLAG, KHÔNG giải trong pass này.
- **`book` vào `findings` — Option X + thêm key `book` vào evidence_refs filter.** Cột không đủ: sau collapse filter `{company_id, year, material_code}` khớp dòng CẢ 2 sổ cho mã chung → panel chứng cứ dưới finding per-sổ hiện dòng sổ kia. `_resolve_evidence` (companies.py:1646-1671) map key generic qua `getattr` → thêm `"book":"EPE"` chạy không sửa resolver. Set `finding.book=row.book` + key `book` ở evidence cho MỌI check emit từ 1 dòng sổ (C4.1/C4.3/C6.1 + C1.3/C1.6 + neutral C2.x/C1.7/C5.1); union findings (C1.1/C1.4/C1.2) để book=NULL.
- **Collapse ngoài Tier-1:** `company_year_scores` (xoá + recompute), `company_periods` (id-10 `is_manual=1` — GIỮ cờ; `data_version`=max+bump), `data_files` (dedupe cặp bcct `DS NK/XK 2025.xls` đăng ký cả 2 sổ). `check_runs`/`check_overviews`/`saved_column_maps`/`user_companies`/`jobs`: 0 dòng cho 9/10.
- **Gate tích hợp mạnh hơn** (thay "chỉ C1.2→4"): assert FULL vector finding/check của 004 + assert 0 dòng `company_id=10` trên 14 bảng FK.
- **S2 sửa:** bỏ assert "identical to current" cho C1.1/C1.4; pin ngữ nghĩa mới `(mã,đơn vị)`-SUM bằng fixture single-book 2 dòng-cùng-mã.
- Non-risk đã verify: không index unique nào vỡ khi 2 dòng/mã dưới 1 company; `detect_company_type` vẫn DNCX sau collapse (multiset mã tờ khai giữ nguyên); C6.1 TRƠ trên 004 thật (chỉ có 2025) → thay đổi group-by-book ở đó là fixture-only.
- **Giả định cần verify sau:** sổ EPE/GC là ledger TÁCH biệt hợp lệ về nghiệp vụ (lấy theo ADR — nếu định mức GC được phép tiêu thụ NVL sổ EPE thì C4.1 per-sổ ra finding gây tranh cãi; KHÔNG phải regression vì bản 2-row cũng đã per-sổ); prod mirror local cho 004.

---

**Revision — UI + upload (hai sổ EPE/GC) (2026-07-25, grill `/grill-with-docs`)**

> Grill chốt cách ĐƯA `book` lên giao diện (hiện `book` chỉ ở tầng dữ liệu — findings/nvl/sp/norms,
> KHÔNG route/template nào render) và cách GÁN `book` lúc upload (thay workaround "2 company → collapse").
> Gộp vào ADR #19 (không tách #20). Hai nhánh độc lập về build: **A (hiển thị + lọc)** chạy trên dữ liệu
> 004 ĐÃ gắn book (từ collapse) → ship được một mình; **B (upload + ingest)** là thay đổi hợp đồng ingest,
> chỉ cần khi tạo dữ liệu book MỚI qua trình duyệt. Build A trước, B sau. Số liệu neo: 004/2025 = EPE 34 ·
> GC 0 · Chung 40 phát hiện; EPE 104 mã NVL · GC 37 mã NVL. Glossary thêm `Pháp nhân nhiều sổ`,
> `Chung (phát hiện liên sổ)` (chốt `book`=null MANG HAI NGHĨA: liên-sổ ở pháp nhân nhiều sổ · vô-nghĩa ở
> pháp nhân một sổ).

*Ba quyết định khó đảo / gây bất ngờ (lý do vào ADR):*
- **`book`=null trong pháp nhân nhiều sổ = "Chung (liên sổ)" — KHÔNG gộp vào một sổ khi lọc.** Check
  cross-layer (C1.1/C1.2/C1.4/C3.2) đối chiếu list tờ khai dùng chung với UNION các sổ nên KHÔNG quy
  được finding về sổ nào → để nguyên là loại thứ ba. Chọn "Sổ EPE" hiện EPE-only; KHÔNG kéo Chung vào
  (gộp = khẳng định sổ mà check chưa quy kết → vi phạm truy nguồn; và nhân đôi across EPE+GC). Người đọc
  tương lai sẽ hỏi "sao lọc EPE không thấy 33 finding C1.1?" — đây là câu trả lời.
- **Ingest đọc `book` per-file từ `data_files`, RETIRE `_guard_single_book`.** `book` là thuộc tính file
  (cột mới `data_files.book`), gán ở bước review WS1; ingest gom file settlement theo book, wipe
  `(company, year)`, ghi lại MỌI sổ trong một lượt (full reprocess). Không có info book (đường CLI/script,
  pilot một sổ) → book=NULL → 002/006 + script KHÔNG đổi. `_guard_single_book` (chặn re-ingest pháp nhân
  nhiều sổ) là stopgap của bản collapse — ingest book-aware ghi nhiều sổ hợp lệ nên bỏ guard, thay bằng
  chính nhãn book per-file. Tờ khai ghi MỘT lần toàn pháp nhân (book=NULL) — sửa lỗi nhân đôi tờ khai 004
  bằng CẤU TRÚC (một pháp nhân upload tờ khai một lần), KHÔNG bằng thuật toán dedup.
- **Gate hiển thị = dữ liệu, KHÔNG phải finding.** `company_books(db, company_id, year)` = tập `book` khác
  null trên `nvl+sp+norms` theo năm; multi-book ⇔ `len ≥ 2`. Đọc từ balances/norms (nơi book thực sự ở),
  KHÔNG từ findings — sổ sạch (GC: 37 mã, 0 finding) vẫn phải hiện. Một helper cấp nguồn cho gate + strip
  header + dòng split + option lọc.

*(A) Hiển thị + lọc — chạy trên dữ liệu đã gắn book:*
- **Scope:** đầy đủ (hiển thị + lọc + split per-check). Chỉ bật cho pháp nhân nhiều sổ; một sổ (002/006)
  KHÔNG có chrome nào.
- **Split per-check:** giữ chip severity làm chính; thêm dòng phụ gọn `Sổ: EPE 8 · Chung 2` dưới tiêu đề
  mỗi nhóm, chỉ bucket khác 0. KHÔNG ma trận book×severity (9 ô/check, hầu hết 0).
- **Strip header:** `Sổ EPE (chế xuất): 104 mã NVL · 34 phát hiện | Sổ GC (gia công): 37 mã NVL · 0 phát
  hiện | Chung (liên sổ): 40 phát hiện`. Con số **mã NVL** làm "0 phát hiện" đọc thành ĐÃ đánh giá-sạch,
  KHÔNG phải chưa chạy. Strip luôn hiện tổng toàn pháp nhân, KHÔNG theo bộ lọc.
- **Lọc:** segmented `Tất cả · Sổ EPE · Sổ GC · Chung` qua param `?book=` (`book=chung`→`Finding.book IS
  NULL`). **View-filter thuần:** phạm vi = danh sách finding (đếm + dòng + nhóm hiện), compose với
  `?check=`, reset trang. Điểm năm · strip header · export · run GIỮ toàn pháp nhân (book là lăng kính,
  KHÔNG phải chủ thể kiểm toán — 004 = một pháp nhân một điểm).
- **Nhãn:** known-map `{EPE:'Sổ EPE (chế xuất)', GC:'Sổ GC (gia công)'}`, lạ→`Sổ {code}`, null→`Chung
  (liên sổ)`. Book code là chuỗi TỰ DO per-pháp-nhân (không enum — chỉ có trong comment adapter, gán lúc
  collapse), nên fallback raw. KHÔNG suy loại hình per-sổ từ dữ liệu (tờ khai dùng chung không có book;
  `detect_company_type` sau collapse trả một loại cho cả pháp nhân).
- **Leaf:** pill book mỗi dòng finding (EPE/GC/Chung, chỉ multi-book) + field `Sổ quyết toán` ở
  finding_detail. Bỏ item_detail (book của mã ngầm định theo đường drill). Combo `COMBO_*` (cross-book) →
  book=NULL → hiện dưới Chung, không special-case.
- **Empty-state khi lọc trúng sổ sạch:** `Sổ GC (gia công) đã được đánh giá — 0 phát hiện trên 37 mã
  NVL.` — tách khỏi state "chưa nạp dữ liệu" / "chưa chạy kiểm tra".

*(B) Upload + ingest — thay đổi hợp đồng ingest, build sau:*
- **Gán book per-file ở review WS1:** cột `book` trên `data_files`; selector ở slot M15/M15a/M16;
  tờ khai/BCCT KHÔNG có selector (toàn pháp nhân). Default `1 sổ (dùng chung)`=NULL; gõ/chọn code từ
  datalist autocomplete `company_books()`; non-null ĐẦU TIÊN → pháp nhân nhiều sổ (KHÔNG cờ riêng);
  normalize code (trim/upper). KHÔNG registry book (YAGNI — demo một pháp nhân nhiều sổ, EPE/GC đã ở
  known-map).
- **Hợp đồng ingest:** đọc book per-file từ `data_files`; gom settlement theo book; wipe `(company,year)`;
  ghi lại mọi sổ (full reprocess, idempotent); tờ khai ghi một lần book=NULL. Đổi tag book một file →
  re-ingest full dựng lại nhất quán (qua đường confirm/re-ingest sẵn có). `discover()` (single m15/company
  folder) → nguồn book chuyển sang `data_files`; đường CLI thiếu data_files → book=NULL (single-book giữ
  nguyên). Bỏ `_guard_single_book`.

*Không làm:* chấm điểm per-sổ · book vào export/run · book ở item_detail · registry book kèm loại hình ·
ingest incremental wipe theo book.

*Bề mặt cài đặt (khi build):* helper `company_books()`/`book_label()` · route+template `company_detail`
(đếm theo book, dòng split, lọc, strip) · finding row + finding_detail · migration thêm `data_files.book` ·
selector review WS1 · viết lại ingest (data_files-driven, gom theo book, full reprocess, bỏ guard).

Xem [[pilot-004-epe-gc-merge]] · glossary `Pháp nhân nhiều sổ` · `Chung (phát hiện liên sổ)`.

---

### 20. Cuộc trò chuyện AI gắn MỘT doanh nghiệp — nhãn LƯU trên dòng, tự nhận diện lúc tạo, sửa được (2026-07-27, grill-with-docs)

**Bối cảnh:** `ai_conversations` không có cột DN. Nhãn DN hiện SUY ở client bằng regex `page_url_seed`
(`chat-core.js:157`) → hỏng hai đường: (a) trang không phải `/companies/...` — cuộc #1 local mở từ
`/findings/36330`, toàn bộ nội dung về một DN, hiện KHÔNG nhãn; (b) id không sống qua re-run —
`36330` đã bị xoá khi chạy lại 004. Lịch sử một mức, cap 30 toàn cục. FAB chỉ resume theo
`sessionStorage` (`sidebar.js:135`) → tab mới = cuộc mới, và cuộc resume có thể thuộc DN khác trang
đang xem, trong khi mỗi lượt gửi ngữ cảnh trang HIỆN TẠI (`chat-core.js:433`).

**Quyết định:**
- **Cột `ai_conversations.company_id`** NULL-able + index `(user, company_id, started_at)`. Nhãn LƯU,
  không suy lúc đọc.
- **Tự nhận diện lúc tạo**, chuỗi ưu tiên dừng ở khớp đầu: DN cán bộ chọn trên UI → `page_context.dn_code`
  → `findings.company_id` của `page_context.finding_id` → NULL. Xác thực lại theo `allowed_company_codes`
  (ADR #14).
- **Gán muộn CHỈ từ mention `@DN` tường minh**, khi cuộc còn NULL và lượt đó có ĐÚNG một DN; ≥2 DN →
  giữ NULL. KHÔNG gán từ tool call (vô hình với cán bộ; câu hỏi so sánh sẽ rơi vào DN model tra trước).
- **Sửa được sau:** `PATCH /api/chat/conversations/{id}` `{company_code|null}`. Chủ cuộc sửa cuộc mình,
  admin sửa mọi cuộc.
- **Nhãn vào system prompt làm CHỦ ĐỀ cuộc** → câu hỏi trống ngữ cảnh ("năm 2025 có gì đáng chú ý?")
  resolve về DN đó. KHÔNG ràng buộc tool theo nhãn: ranh giới quyền ADR #14 vẫn là biên duy nhất, và
  "so sánh với DN khác" là câu hỏi kiểm toán hợp lệ.
- **Hiển thị:** `/chat` nhóm theo DN (section gập, section của DN đang xem mở sẵn, `Chưa gán doanh
  nghiệp` cuối); sidebar giữ danh sách phẳng + chip DN mỗi dòng + bộ lọc (panel ngắn, header/section ăn
  hết chỗ). Cùng một `company_id` → chuyển ở đâu cũng chuyển ở kia.
- **Mở FAB:** tiếp tục cuộc gần nhất CÙNG DN nếu < **24h**, ngược lại mở cuộc mới trong phạm vi đó; báo
  rõ "Đang tiếp tục cuộc trò chuyện gần nhất của …". Mốc 24h vì resume nạp lại 20 message vào MỌI prompt
  (`HISTORY_TURN_LIMIT`, `ai.py:52`) — cuộc hai tuần trước neo câu trả lời vào dữ liệu có thể đã nạp lại.
  `sessionStorage` vẫn override trong cùng tab.
- **Lệch phạm vi** (cuộc thuộc DN A, trang đang xem DN B): HIỆN thông báo + nút "Mở cuộc trò chuyện mới
  cho B". KHÔNG tự tách cuộc (mất cuộc đang dở khi chỉ điều hướng), KHÔNG tự đổi nhãn.
- **Admin:** `Chỉ của tôi` BẬT mặc định, toggle xem mọi user; 30 cuộc/section + "tải thêm" thay cap 30
  toàn cục (`ai.py:383`).
- **DN bị gỡ phân công:** cuộc vẫn ĐỌC được (giữ hành vi hiện tại — `get_conversation_messages` chỉ kiểm
  sở hữu, `ai.py:421`), nhưng KHÔNG gửi thêm được; ô nhập khoá kèm lý do. Chống cảnh "hỏi được, câu nào
  cũng bị tool từ chối, không nói vì sao".
- **Backfill trong migration:** `page_url_seed` khớp `companies.code`/`slug` → gán; `/findings/{id}` mà
  finding còn tồn tại → gán theo `findings.company_id`; còn lại NULL.

**Loại:** suy nhãn lúc đọc (hỏng khi finding bị xoá; phải quét tool payload mỗi lần render) · một cuộc
gắn nhiều DN (không dựng được nhóm) · ràng tool theo nhãn (chặn câu hỏi so sánh hợp lệ) · cấp con theo
NĂM (đa số nhóm chỉ một cuộc) · ẩn cuộc của DN đã gỡ quyền (mất việc của chính cán bộ, không lý do).

**Ngôn ngữ:** KHÔNG dùng "thư mục"/"folder" — header section CHÍNH LÀ doanh nghiệp, nên nhóm không cần
danh từ riêng. "cuộc" không đứng một mình (luôn "cuộc trò chuyện"). Xem glossary mục *Chat gắn doanh
nghiệp*.

**Hệ quả:** nhãn thành load-bearing cho CÂU TRẢ LỜI (vào prompt), nên nhận diện sai đắt hơn nhãn trang
trí — đó là lý do chuỗi nhận diện chỉ nhận tín hiệu tường minh. Chi phí token: một dòng system prompt.

---

### 21. Tổng quan AI v2 — tách BẢNG SỐ LIỆU (tính) khỏi NHẬN ĐỊNH (LLM); sinh ASYNC qua worker phân theo kind; sổ chi phí `ai_usage` (2026-07-27, grill-with-docs; SỬA ADR #18 Revision WS3)

**Bối cảnh:** bản WS3 sinh MỘT đoạn văn xuôi 3–6 câu; mọi con số trong đoạn đó do model phát, và
aggregate nạp prompt (đếm severity + top-15) bị vứt sau lời gọi. Với C1.6 = 7.446 finding (local),
đoạn văn là TOÀN BỘ cái cán bộ thấy về phân bố. Nút chạy ĐỒNG BỘ trong request — ADR #18 chọn có chủ
đích: worker 1 thread, một lời gọi LLM 5s trong hàng đợi sẽ chặn mọi lần chạy check đang chờ. Chi phí
overview ghi ở `check_overviews.cost_usd` nhưng `check_daily_budget` chỉ cộng `AiMessage.cost_usd`
(`limits.py:44`) → **chi tiêu overview KHÔNG vào trần ngày lẫn `/admin/ai`**.

**Quyết định:**
1. **Tách hai nửa.** Số liệu TÍNH bằng Python, lưu `check_overviews.aggregate_json`, template render;
   LLM chỉ viết phần ĐỌC. Lý do theo thứ tự trọng số: số do model phát không đưa vào báo cáo khách được
   (sinh lại có thể đổi số trong khi dữ liệu đứng yên); bảng số liệu vẫn hiện khi LLM lỗi/tắt/chậm;
   nhận định ngắn và rẻ đi vì thôi kể lại con số đã cho.
2. **Aggregate gồm:** tập trung (số mã distinct, tỉ trọng top-5, số mã phủ 80%) · phân vị các trường số
   trong `details` (`n/min/p50/p90/max`; khoá khác nhau theo check: `diff_pct`, `ratio_pct`,
   `m15_repurpose`, `theoretical_consumption`…) · chiều lệch (cao hơn / thấp hơn) · tách theo sổ ·
   so với năm trước (tổng, delta, mã mới xuất hiện). **KHÔNG cộng tuyệt đối chéo đơn vị** — mỗi mã một
   `unit` (Cái/Chiếc, Lon/Can, kg), tổng lệch chéo đơn vị là số vô nghĩa; độ lớn chỉ báo bằng phần trăm
   + đếm, số tuyệt đối để nguyên trong mục điểm nóng theo từng mã.
   *Loại:* tách theo `status` triage (re-run wipe + reset về `new` → bảng đọc thành "chưa ai xử lý" cho
   check vừa triage xong) · so với DN khác cùng năm (vượt ranh giới quyền ADR #14; khác quy mô nên so
   cũng lệch).
3. **Nhận định trả JSON:** `nhan_dinh` (1–2 câu) · `phan_bo` (2–3 câu) · `diem_nong[{subject_key,
   nhan_xet}]` ≤5 (render thành link `/companies/{slug}/items/{key}?year=` — truy nguồn) · `de_xuat` ≤3.
   JSON hỏng → render text thô như hiện tại (xuống cấp, không vỡ trang). Miễn trừ trách nhiệm ("chỉ số
   rủi ro dữ liệu, không phải kết luận vi phạm") là TEXT TĨNH của template, không phải output LLM.
   Check <10 finding: bỏ `phan_bo` (đoạn phân bố cho 11 dòng là độn chữ).
4. **Số trong nhận định phải COPY nguyên chuỗi** đã định dạng sẵn trong prompt; hậu kiểm bằng so khớp
   chuỗi (không parse số — parse vấp làm tròn 61,8→62%, năm 2025, mã check C1.6, subject key có chữ số).
   Lệch → gắn cờ `cần đối chiếu` + badge, KHÔNG publish âm thầm. Đây là bộ dò hallucination rẻ nhất hệ
   thống chạy được, đặt đúng trên artifact ra trước mặt khách.
5. **ASYNC:** `JobKind.AI_OVERVIEW` + `claim_next_job(kinds=…)`; worker hiện có LOẠI kind AI, worker thứ
   hai CHỈ nhận kind AI. Giữ đúng tính chất ADR #18 bảo vệ (hàng đợi check không bao giờ chờ LLM) mà vẫn
   có job row: traceback, `created_by` (ai tiêu token), `/jobs`, zombie recovery.
   **SỬA "sinh đồng bộ trong request" của ADR #18 Revision WS3.**
6. **UI:** POST → 303 về đúng anchor; **bảng số liệu hiện NGAY** (không cần LLM), chỗ nhận định hiện
   "⏳ Đang viết nhận định… (công việc #N)", poller thay text khi xong hoặc hiện lỗi kèm link job.
   KHÔNG redirect sang `/jobs/{id}` như run-checks: overview là một đoạn trong nhóm cán bộ đang đọc, mà
   `/companies/{slug}` không khôi phục vị trí cuộn lẫn `<details>` đang mở. Bấm lại khi đang
   `pending|running` → trả job CŨ (đóng luôn double-click double-spend ADR #18 để ngỏ).
7. **Handler TÍNH LẠI aggregate ngay trước lời gọi LLM** và lưu bản đó — giữ quy tắc ADR #18: snapshot
   đọc trong một transaction với lời gọi. Không có bước này, một lần chạy check chen giữa enqueue và
   sinh sẽ để nhận định mô tả bảng số liệu khác bảng đang hiện.
8. **Bảng số liệu ĐÓNG BĂNG theo snapshot, KHÔNG tính live.** Live nghĩa là parse `details` mỗi lần load
   `company_detail` cho MỌI nhóm có overview (C1.6 = 7.446 dòng) — trên màn hình chính; và panel với
   nhận định phải mô tả cùng một mốc, nếu không cán bộ đọc "8 mã" ở bảng và "12 mã" ở câu dưới, cả hai
   đều đúng ở hai thời điểm khác nhau. Cờ stale (ADR #18) phủ cả hai nửa. KHÔNG auto-regenerate lúc load.
9. **Nút gộp** "Tạo tổng quan cho các test chưa có / đã cũ" (`AI_OVERVIEW_BATCH`), duyệt check có ≥1
   finding, bỏ qua check đã có overview còn mới, **commit từng check**. Hết ngân sách → dừng, job `done`
   kèm `{đã tạo, bỏ qua, dừng: "hết ngân sách ngày"}` — KHÔNG `failed`: 7 overview đã sinh vẫn đúng, và
   `failed` mời cán bộ bấm lại một nút chắc chắn không làm gì. ADR #18 bác sinh EAGER (tự động sau mỗi
   `run_checks`), không bác nút tường minh.
10. **Sổ chi phí `ai_usage`** (append-only: `kind` chat|overview, `ref`, `model`, tokens, `cost_usd`,
    `user`, `created_at`). Trần ngày + `/admin/ai` đọc sổ này. KHÔNG chỉ mở rộng câu query sang
    `check_overviews`: bảng đó upsert MỘT dòng mỗi bộ ba, sinh lại 3 lần trong ngày chỉ còn chi phí lần
    cuối — đếm thiếu đúng lúc chi tiêu cao nhất. Telemetry trên dòng overview giữ nguyên (chi phí của
    CHÍNH overview đó). Seed sổ từ `check_overviews` hiện có (theo `generated_at`) + `ai_messages` trong
    ngày.
    **Sổ là thứ LƯU + CHẶN, KHÔNG phải thứ hiển thị (owner chốt):** khối tổng quan ở `company_detail`
    KHÔNG hiện chi phí / token / tên model — chỉ mốc sinh, cờ stale, cờ `cần đối chiếu`, trạng thái đang
    chạy. `job.result` của `AI_OVERVIEW`/`AI_OVERVIEW_BATCH` KHÔNG chứa `cost_usd`/tokens: `/jobs/{id}`
    in nguyên result ra màn hình cho mọi cán bộ (`job_detail.html:31`), mà vé TQ-2 lại link thẳng tới đó
    khi job hỏng. Nơi DUY NHẤT đọc ra tiền vẫn là `/admin/ai`, sau cờ `show_cost` (hiện truyền `False`,
    `admin_ai.py:117`/`:337`).
11. **Rate limit giờ vẫn là guard của CHAT** (đếm `AiMessage`, `limits.py:19`), KHÔNG áp cho overview —
    một lượt gộp 12 call không được khoá trợ lý của cán bộ một tiếng. Chỗ chặn chi tiêu là trần ngày,
    nay đã thấy đủ mọi lời gọi.
12. **Model: slot `model_fast`** (+ fallback slot `fast`) thay `model_default`. Slot này khai sẵn cho
    "summarize/explain" (`config.py:51`); sau khi tách, việc của model là đọc aggregate gọn và trả 4
    trường ngắn với số copy nguyên văn. Đổi ở `/admin/ai`, không redeploy — đúng mục đích `ai_settings`.
13. **KHÔNG đưa nhận định vào Excel export / báo cáo.** Workbook là artifact rời khỏi hệ thống: không
    mang miễn trừ trách nhiệm và đọc như kết luận của cơ quan. Muốn đưa ra sản phẩm cho khách thì thứ
    còn thiếu là bước cán bộ SỬA + DUYỆT overview, không phải một checkbox. *Lưu ý tên trùng:* sheet
    "Tổng quan" của export (`export.py:233`) là bảng tổng hợp finding — khác vật với "Tổng quan AI".

**Thứ tự build (3 PR):** (1) chat gắn DN [ADR #20] → (2) hạ tầng: `ai_usage` + worker theo kind + async
một check → (3) nội dung: aggregate + bảng số liệu + JSON nhận định + nút gộp. Tách (2) để `/rev` soi
thay đổi HÀNG ĐỢI CHECK (thứ duy nhất ở đây chạm prod run) tách khỏi thay đổi template.

**Hệ quả:** `/jobs` có thêm loại job AI (nhiễu nhẹ, đổi lại minh bạch chi phí). Hai worker thread cùng
poll SQLite — chấp nhận được vì ghi ngắn, WAL bật, và transaction ghi chỉ mở SAU khi LLM trả (kỷ luật
đã có trong `generate_check_overview`).

Xem [[ws3-overview-staleness-model]] · [[so-lieu-phai-co-mau-so-va-nguon-doc-lap]] ·
[[check-execution-async-via-jobs]].

### 22. Phân tích pilot tách khỏi cẩm nang — trang riêng `phan-tich-pilot/`, KHÔNG gộp vào bản giao khách (2026-07-28)

**Quyết định:** dựng một trang tĩnh thứ hai `app/static/docs/phan-tich-pilot/index.html` chứa (A) mô tả
luồng dữ liệu sáu chặng và (B) phân tích ba hồ sơ pilot 002/004/006, trọng tâm là trường hợp 004 hai sổ.
Cẩm nang `huong-dan/` giữ nguyên phạm vi cũ; chỉ thêm **một dòng liên kết** ở mục D5. Hai trang trỏ lẫn
nhau: D5 (tính năng chung) → mục C của trang mới (trường hợp cụ thể) → ngược lại.

**Lý do:** `huong-dan/` là cẩm nang sản phẩm — dữ liệu trình diễn, giao cho mọi khách. Phân tích pilot là
dữ liệu người nộp thuế cụ thể, vòng đời khác (số đổi theo mỗi lần chạy lại check) và người đọc hẹp hơn.
Gộp vào sẽ buộc mỗi lần chạy lại check phải sửa tài liệu giao khách.

**Alternatives loại:**
- *Gộp cả hai vào cẩm nang* — loại: đưa đặc thù một người nộp thuế vào bản giao mọi khách.
- *Tách CSS chung ra `_shared/manual.css` rồi `<link>` từ hai trang* — loại: commit `535b71b` chọn
  **standalone HTML** làm thuộc tính của cẩm nang ("thư mục đó copy sang host tĩnh khác chạy được nguyên
  vẹn", `docs.py:32`). Một tệp CSS chung phá thuộc tính đó. Thay vào đó **sao chép nguyên khối `<style>`**
  và nối thêm một khối bổ sung có đánh dấu (nhãn ba loại phát biểu + lưới đầu vào/đầu ra). Chi phí: khi
  sửa design token phải sửa hai chỗ — chấp nhận được vì token đã ổn định.
- *Chỉ đưa phần luồng dữ liệu vào cẩm nang, giữ riêng phần pilot* — vẫn để ngỏ nếu owner muốn một link duy
  nhất cho onboarding. Không làm sẵn vì phần luồng dữ liệu hiện dẫn chiếu trực tiếp tới số của ba hồ sơ pilot.

**Ba ràng buộc nội dung, ghi lại vì dễ vi phạm về sau:**
1. **Trang nằm dưới `/static`, tức CÔNG KHAI không auth** (`main.py:127` mount `StaticFiles`, không có
   dependency `require_user`). Nên tài liệu KHÔNG có tên doanh nghiệp, tên đối tác, mã số thuế, số tờ khai.
   Mã vật tư / mã sản phẩm thì giữ — đã có sẵn trên `/showcase` công khai. Đã quét lại toàn tệp trước khi
   commit: 0 hit.
2. **Số phải đối chiếu DB prod, không lấy từ `audit_hq.sqlite` local.** Local hiện là bản TRƯỚC lần chạy
   lại multi-unit (004 = 74 phát hiện / điểm 30); prod là **65 / 25**. Đã verify 81 khẳng định số bằng
   script read-only trên `/db-data/audit_hq.sqlite` (`mode=ro`, không checkpoint WAL) — 81/81 khớp.
3. **Giữ nguyên tách bạch ba loại phát biểu** của báo cáo phân tích sơ bộ: `(Sự thật)` đọc từ chứng từ ·
   `(Suy luận)` nhận định · `(Căn cứ pháp lý)` dẫn văn bản. Có class CSS riêng cho ba nhãn này.

**Hai đính chính so với số đang lưu hành, đã áp vào trang:**
- **Thang điểm là 0–1000, không phải 0–190.** 190 (nay 200 khi tập check khác) là `max_raw` — trần điểm
  thô nội bộ = 17 bài × 10 + 20 tổ hợp (`scoring.py:183-186`). Điểm hiển thị luôn quy về 0–1000.
- **Sổ EPE của 004 có 98 mã NVL trong 104 DÒNG**, không phải "104 mã". 6 mã ghi kép hai đơn vị tính
  (MTR/ROLL), mỗi đơn vị một dòng. Đây đúng chỗ ADR #19 `:608` gọi nhầm dòng thành mã — xem punch-list
  mục 7 của `.ai/sessions/2026-07-26-audit-004-hai-so.md`.

**Nguồn nội dung:** `../audit-hq-pilot/notes/14` (002) · `/13` (006) · `/10`, `/02`, `/05`, `/11` (004) ·
`/12` (lỗi sản phẩm), cộng `.ai/sessions/2026-07-26-audit-004-hai-so.md` cho phần đính chính che khuất
phát hiện, và báo cáo phân tích sơ bộ hồ sơ 004 (bản `_v2`, chủ dự án đã biên tập tay) cho văn phong và
phần câu hỏi A/B/C.

**Ảnh minh hoạ:** dùng lại ảnh dữ liệu trình diễn của cẩm nang qua đường dẫn tương đối
`../huong-dan/*.png` — 6 ảnh, tất cả đã kiểm là dữ liệu demo hoặc đã ẩn danh. **Cố ý KHÔNG dùng
`21-hai-so-quyet-toan.png`** dù đó là ảnh đúng chủ đề: ảnh này hiện **mã số thuế thật** của 004 và số
liệu của lần chạy CŨ (74 phát hiện / điểm 30), mâu thuẫn với số đang công bố. Ảnh đó vẫn nằm trong cẩm
nang đã phát hành — **việc cần làm riêng, chưa xử lý ở nhánh này.**

**Kiểm chứng đã chạy:** render Chromium ở 1440px và 420px, hai nền sáng/tối — 24 mục / 6 nhóm trên mục
lục, không tràn ngang (`body.scrollWidth == clientWidth` ở cả hai bề rộng), bảng nằm trong khung, phóng
ảnh và phím Esc hoạt động, ô tìm kiếm lọc đúng, liên kết hai chiều với D5 điều hướng đúng.

Xem [[pilot-004-epe-gc-merge]] · [[gan-nhan-to-khai-theo-so]] · [[public-showcase-and-no-edge-auth]] ·
[[so-lieu-phai-co-mau-so-va-nguon-doc-lap]].

## 2026-07-31 — KTSTQ 5 năm · kỳ quyết toán linh động · template cấu trúc lạ

### 23. BCCT lưu trọn theo nhãn nạp — tư cách thuộc kỳ tính lúc QUERY; niên độ mức DN; template registry 2 tầng; phạm vi KTSTQ là VIEW (2026-07-31, grilling)

**Bối cảnh:** KTSTQ chốt phạm vi = 5 năm kể từ **ngày đăng ký tờ khai** (khoản 3 Điều 77 Luật HQ
54/2014, còn nguyên trong VBHN xác thực 23/3/2026) → không trùng trọn các kỳ quyết toán. Kỳ BCQT
theo pháp luật là **năm tài chính**, hạn nộp 90 ngày sau kết thúc niên độ (Đ.60 TT 38 bản TT 39/2018;
giữ nguyên ở khoản 32 Đ.1 TT 121/2025, hiệu lực 01/02/2026). Căn cứ + trích dẫn đầy đủ:
`.ai/notes/2026-07-31-research-ky-ke-toan-bcqt-ktstq.md`. Phương án gốc + census cấu trúc file:
`.ai/notes/2026-07-31-ktstq-5-nam-template-ky-quyet-toan.md`. Defect nền: `ingest.py:330` BỎ dòng
BCCT ngoài cửa sổ kỳ ngay lúc nạp, đếm `bcct_other_year` chỉ in CLI — web UI không thấy, sửa cửa sổ
sau nạp không phục hồi được.

**T1 — Lưu trọn dòng BCCT, membership theo query (BLOCKING cho T4)**
- `declaration_lines.period_year` = **NHÃN NẠP / provenance**, không còn là tư cách thuộc kỳ.
  Ingest lưu ĐỦ mọi dòng parse được (bỏ nhánh drop). Wipe re-ingest giữ nguyên
  (`delete where label == year` = "lượt nạp này thay chính nó"). ADR #13/#16 không đổi: `period_year`
  vẫn là khoá join của các bảng BCQT.
- **MỘT helper duy nhất** (vd `declaration_scope(company_id, year)`) là selector vế BCCT cho CẢ 17
  check (hiện mỗi check tự filter `period_year == year` rải rác — phải quy về một chỗ): dòng CÓ ngày
  → `declaration_date` trong cửa sổ `company_periods` của `year`, BẤT KỂ nhãn; dòng KHÔNG ngày →
  fallback khớp nhãn (giữ nguyên hành vi `in_period` cũ) + đếm hiện ở banner độ phủ
  ("N dòng không có ngày tờ khai — quy theo kỳ nạp").
- **Trùng chéo nhãn: CẢNH BÁO, KHÔNG dedup, KHÔNG chặn.** Sau khi lưu, đếm dòng có khoá
  (`declaration_no`, `line_no`; `line_no` NULL → (`declaration_no`, `item_code`)) đã tồn tại ở nhãn
  khác cùng DN → banner trang tài liệu. Số lượng có thể lệch giữa hai bản export nên mọi auto-pick là
  đoán — cán bộ sửa file nguồn. (Trùng chéo nhãn chỉ tồn tại SAU T1 — trước đây drop che mất.)
- **Sửa cửa sổ kỳ = đổi kết quả check không qua ingest** → route sửa kỳ bump
  `company_periods.data_version` TRONG cùng transaction (đúng ca `data_version` sinh ra để bắt —
  WS3). Cửa sổ hai năm chồng lấn sau khi sửa → CẢNH BÁO (không chặn): kỳ chuyển tiếp khi đổi niên độ
  là hợp pháp (từ 01/01/2025 theo khoản 4 Đ.2 Luật 56/2024: gộp ≤ 3 kỳ tháng liên tiếp, tối đa 15
  tháng — thay quy tắc "<90 ngày" cũ).
- **Cảnh báo độ phủ mỗi (DN, kỳ):** so cửa sổ với min/max `declaration_date` + đếm theo tháng →
  "thiếu 01/01–31/03/2026 — nạp thêm file dương lịch 2026". Đây là câu trả lời cho "up BCCT dương
  lịch vào DN niên độ lệch": cảnh báo thiếu + nạp file năm kề là lấp được, không dán nhãn lại.
- **HAI cổng nghiệm thu tách bạch** (phương pháp delta, xem [[harness-baseline-methodology]]):
  (1) đổi query trên DB HIỆN TRẠNG (không re-ingest) → delta finding = **0** trên 3 pilot;
  (2) fresh re-ingest → delta CHỈ gồm dòng trước đây bị drop nay vào scope (006 "file gộp nhiều kỳ":
  dòng dated 2024 nằm ở file nhãn 2025 sẽ vào scope 2024 — chủ ý, soát từng dòng).
- Loại: (b) bỏ hẳn `period_year` khỏi `declaration_lines` (undated mất neo, churn evidence_refs/index
  vô ích); (c) bảng phụ chứa dòng ngoài cửa sổ (mọi query phải union 2 bảng, dữ liệu "lẻ" thành hạng
  hai — phá mục đích T4).

**T2 — Niên độ: mức DN default + per-year override**
- Cột `companies.fiscal_start_month` (int, default 1 = dương lịch — mọi DN hiện có giữ nguyên hành
  vi, không backfill). UI cho đúng 4 giá trị {1, 4, 7, 10} (điểm a khoản 1 Đ.12 Luật Kế toán
  88/2015: niên độ khác dương lịch phải 12 tháng tròn từ đầu quý). Kỳ lẻ (năm đầu/cuối, chuyển tiếp
  đổi niên độ) dùng override per-year `company_periods` đã có.
- **Nhãn năm = NĂM BẮT ĐẦU kỳ**: cửa sổ default của năm Y = [01/`fiscal_start_month`/Y → trước đó 1
  ngày của năm sau]. Căn cứ research: pháp luật định danh kỳ CHỈ bằng khoảng ngày ("Từ ngày… đến
  ngày…"), KHÔNG có quy ước tên "năm tài chính 20XX" chính thức → nhãn là khoá nội bộ, chọn năm bắt
  đầu; bù lại **mọi màn hiện nhãn kỳ ≠ dương lịch phải in kèm khoảng ngày** (mở rộng cơ chế
  `load_period_windows` ra mọi màn có nhãn kỳ, gồm cả export).
- Thứ tự suy cửa sổ: `is_manual` > tiêu đề file (đủ 2 ngày) > **default từ `fiscal_start_month`** >
  dương lịch. Tiêu đề file lệch với default niên độ DN → CẢNH BÁO trên màn review (không chặn, không
  tự pick) — nhất quán triết lý cảnh-báo-không-đoán của T1.

**T3 — Template registry 2 tầng + đánh dấu file khớp mẫu**
- Tầng builtin: **sống trong CODE** (module cạnh `BALANCE_EXPECT`), mỗi entry = {id, tên hiển thị,
  slot, tập vân tay `form_signature`, column map, data_start}; đổi qua PR + test fixture thật từng
  template; seed từ census 2026-07-31 (BCCT chi tiết ECUS phủ 10/11 DN · BCCT tổng hợp · Mẫu 15a
  chuẩn 8 DN · biến thể DN03/DN04). **YÊU CẦU TƯƠNG LAI đã chốt:** sau này phải quản lý template
  qua UI (bảng DB seed từ code) — không ở lại code vĩnh viễn; chưa build bây giờ.
- Thứ tự resolve khi parse: map officer-confirmed của DN → template builtin khớp vân tay → dò từ
  khoá → cổng review. Không đường nào parse im lặng; fallback hằng số phải hiện nguồn "mặc định".
- **Khớp template = TỰ QUA cổng review**: nguồn bằng chứng mới `builtin-template`, rank giữa
  `header-matched` và `officer-confirmed`. Lý do: cổng review canh CẤU TRÚC chưa được người xem —
  template là cấu trúc ĐÃ được mình xem lúc curate (code, PR, test); bắt mỗi DN click lại là re-review
  cấu trúc, không thêm được kiểm tra nào cổng thực sự làm. Rủi ro chấp nhận: template curate sai áp
  im lặng diện rộng — chặn bằng test fixture + badge "Khớp mẫu: <tên>" luôn hiển thị + officer
  override ghi map per-DN (rank cao hơn, thắng template).
- Ghi `template_id`/`match_source` vào `data_files` — trang tài liệu + màn review hiện
  "Khớp mẫu: …" / "Map đã xác nhận …" / "Không khớp — cần xác nhận cột".

**T4 — Phạm vi KTSTQ 5 năm là VIEW, không phải khoá dữ liệu**
- `companies.audit_decision_date` (nullable, ngày quyết định thực tế/dự kiến). NULL → mọi màn như
  cũ. Cửa sổ `[D − 5 năm, D]` **tính, không lưu**; lọc trên `declaration_date` (= "Ngày ĐK" — đúng
  mốc neo pháp lý). Đổi ngày = re-render, không đụng dữ liệu, không tương tác staleness. Hình thái
  tương lai đã ghi nhận: bảng `audit_engagements` nhiều đợt/DN — KHÔNG build bây giờ; không được
  couple sâu hơn "đọc một cột date nullable".
- **Màn độ phủ**: chiếu cửa sổ lên các kỳ quyết toán → mỗi kỳ: trọn trong phạm vi · cắt đầu · cắt
  đuôi · chưa có BCQT. Nói CẢ HAI ngôn ngữ (khoảng ngày + danh sách kỳ) — mẫu 01/QĐKT (PL II TT
  121/2025) để "Phạm vi kiểm tra" là dòng trống tự do nên hệ phải dịch được giữa hai cách ghi.
- Kỳ đầu bị cắt: chạy ĐỦ check trên TRỌN kỳ (đẳng thức cân đối chỉ đúng trên trọn kỳ); tag hiển thị
  tính lúc render từ `audit_decision_date`: finding có ngày → trong/ngoài phạm vi; finding cân đối →
  "kỳ quyết toán rộng hơn phạm vi kiểm tra". KHÔNG lưu state cửa sổ trên finding.
- **Đuôi chưa quyết toán — sửa luôn defect "0 finding = sạch giả"**: spec trong `registry.py` khai
  `requires` (tập nguồn: bcct/m15/m15a/m16); `run_checks` kiểm presence per (DN, năm) trước khi
  dispatch; thiếu nguồn → ghi `check_runs.skip_reason` (cột mới, vd `"no_bcqt"`) thay vì chạy join
  rỗng. UI phân biệt rõ "Chưa chạy — chưa có BCQT (chưa đến hạn nộp)" với "chạy rồi, 0 phát hiện".
  Defect này hôm nay đã có với BẤT KỲ năm nào chạy check trước khi up BCQT — không riêng đuôi.
  Phân loại 17 check theo `requires` làm lúc implement, là fact-audit không phải đoán.
- Loại: hardcode danh sách check "thuần BCCT" cho kỳ đuôi (mục rữa khi check đổi, không sửa được
  ca "clean giả" ở năm thiếu dữ liệu khác).

**Trình tự build:** T1 → T4 (T4 phụ thuộc T1); T2, T3 độc lập, song song được. Demo 2026-08-01
không ship gì trong này — dùng đồ có sẵn (flow review cấu trúc lạ per-DN, sửa kỳ tay) + nói phương
án; TRÁNH nạp live BCCT dương lịch vào DN đã set kỳ lệch (drop im lặng trên web còn nguyên tới T1).

Xem [[harness-baseline-methodology]] · [[parse-confidence-evidence-model]] ·
[[checks-khong-doc-lap-khi-dem-gop]] · [[so-lieu-phai-co-mau-so-va-nguon-doc-lap]] ·
[[trich-luat-phai-neu-ban-hop-nhat-va-hieu-luc]].

## 2026-08-06 — Nạp dữ liệu chạy ở hàng đợi · parse một lần · trang tính chọn được

Sự cố mở đầu: cán bộ tải bộ file 006 lên demo, Cloudflare trả **lỗi 524** (origin không trả lời
trong 100 giây). Không phải do deploy: trang lỗi đóng dấu 09:29:24 UTC, lượt deploy trước xong
09:20:49 và lượt sau tới 09:33 mới khởi động lại container, `/healthz` lúc đó vẫn phục vụ build
`e0ca059`.

**Đo trên chính file gây lỗi** (`PILOT_006/2025/.../BaoCaoToKhai 01.01.2025-31.12.2025 F1+F3.xlsx`,
68,0 MB, 243.454 dòng chi tiết):

| bước | thời gian | RSS đỉnh |
|---|---|---|
| `parse_bcct` riêng file này | 97,0 s | 770 MB |
| `diagnose_upload(PILOT_006, 2025)` | 119,9 s | 904 MB |
| `ingest(dry_run=True)` (270.505 dòng BCCT + 10.560 M15 + 501 M15a + 113.561 M16) | 116,1 s | 850 MB |
| `ingest()` commit (đọc lại lần ba + ghi ~395k dòng) | ≥ 116 s | — |

### 1. Mọi đường nạp đi qua job queue (`JobKind.INGEST`) — SỬA ADR #18 Revision WS2 mục (1)

**Quyết định:** `POST /companies/{code}/upload`, `POST /documents/ingest` và
`POST /documents/file/{id}/review` chỉ làm phần rẻ trong request (ghi file, `sync_data_files`, lưu
map cột / sổ / trang tính) rồi enqueue job `ingest` và redirect `/jobs/{id}`. Handler chạy chuỗi
chẩn đoán → xem trước → cổng review → nạp. Payload `gate` (True ở đường tải lên, False ở nạp lại
và xác nhận cột) và `then_run_checks` — **handler tự enqueue** job kiểm tra nối tiếp, nên thứ tự
đúng không phụ thuộc số worker và nạp hỏng thì không chạy kiểm tra trên dữ liệu cũ.

**Lý do:** ADR #18 Revision WS2 chọn option A (re-ingest giữ đồng bộ, chỉ re-run vào hàng đợi) với
lý do "áp map là ý nghĩa của confirm, không được kẹt ở `analyzed`". Số đo trên cho thấy option A
không sống được với dữ liệu thật: một lượt tải lên tốn hơn 6 phút CPU trong khi biên là 100 giây,
và giới hạn đó của Cloudflare chỉ Enterprise mới nới được. Cái giá của option B (file kẹt
`analyzed` vài phút) nay hiện rõ trên trang công việc tự làm mới 2 giây, kèm kết luận
`status = ok | diagnosis_error | needs_review | plan_error`, danh sách chẩn đoán và cột cần xác nhận.

**Alternatives loại:** nới timeout (Cloudflare free/pro không cho); chỉ nạp nền cho file lớn (hai
đường mã cho cùng một việc, ngưỡng nào cũng tuỳ tiện); giữ `INGEST_AND_RUN` (tên nói "nạp và chạy
kiểm tra", còn đường tải lên KHÔNG tự chạy kiểm tra — thêm `INGEST` cho đúng nghĩa, enum cũ vẫn để trống).

### 2. `parse_cache()` — mỗi file mở một lần trong một lượt nạp

**Quyết định:** `app/adapters/parse_cache.py` nhớ kết quả `parse_m15/m15a/m16/bcct` theo
`(hàm, đường dẫn, mtime, size, sheet, năm)` bên trong `with parse_cache():`; `app/adapters/__init__.py`
xuất bản có nhớ. Handler bọc cả ba bước trong một phạm vi.

**Lý do:** ba bước đọc cùng bộ file ba lần. Nhớ theo `(mtime, size)` để file tải lên đè vẫn parse lại.
ContextVar chứ không phải biến module vì worker kiểm tra và worker AI là hai thread. Nhớ cả lỗi:
`SheetNotFound` là kết luận về file, không phải sự cố nhất thời.

**Alternatives loại:** cache toàn cục theo tiến trình (giữ ~900 MB kết quả parse của một kỳ sống
giữa các job); truyền `ParsedSet` qua tham số (đổi chữ ký `diagnose_upload`/`ingest`/
`_plan_settlement_files` và phải tự mang ngữ nghĩa lỗi của từng file).

### 3. Trang tính: ghi lại, hiện ra, chọn lại được

**Quyết định:** `IngestStats.sheets` (khoá `"slot:tên file"`) → `data_files.parse_detail.sheet`;
màn xác nhận cột vẽ lưới của **trang được đọc** thay vì trang đầu workbook, kèm ô chọn trang; cột
mới `data_files.sheet_override` (NULL = để hệ thống tự chọn) được `ingest` áp cho cả xem trước lẫn
nạp thật. Đổi trang = chạy lại kiểm tra cả năm khi file đã `parsed` (như đổi sổ) vì đổi trang là
đổi toàn bộ dòng đọc ra. `parse_bcct`/`parse_m16` khi nhận trang chỉ định thì **dò lại dòng dữ liệu
đầu** (`find_data_start`) thay vì giữ hằng số của mẫu chuẩn.

**Lý do:** `select_sheet` chấm điểm chọn trang mà không ghi lại đã chọn gì, còn màn review lại đọc
trang chỉ số 0. File BCCT của 006 có 6 trang (`Tổng hợp`, `Chi tiết`, `Phí vận chuyển`, `lệ phí HQ`,
`làm co`, `TK tại chỗ`): parser đọc `Chi tiết`, màn review vẽ `Tổng hợp` — cán bộ xác nhận chỉ số
cột trên một bố cục khác hẳn cái đang được nạp. Trang tổng hợp cấp tờ khai cũng có "Số TK" ở cột 1
nên chọn nhầm ra **dòng sai**, không phải 0 dòng.

**Alternatives loại:** lưu trang trong `parse_layout`/provenance theo slot (một kỳ có nhiều file
BCCT, mỗi file một trang — provenance chỉ giữ một bản cho cả slot); chỉ hiện trang mà không cho
sửa (biết sai vẫn không sửa được, phải sửa file nguồn).

## 2026-08-07 — Thiết kế lại luồng tải lên → nạp dữ liệu

### 24. Đủ dữ liệu đo theo kiểm tra chạy được; vướng mắc xếp theo cách gỡ; xem trước trích xuất một lần (2026-08-07, grill-with-docs; spec ở issue #80; SỬA ADR #18 mục nhãn truy nguồn)

**Quyết định:**

(1) **"Đủ dữ liệu" = mọi kiểm tra áp dụng cho DN đều có đủ nguồn Tầng 1 nó khai cần**, không phải "đủ 4 loại tài liệu". Phép đếm đo theo DÒNG đã nạp (kiểm tra đọc dòng), nhưng câu chữ cách gỡ tra `data_files` trước khi chọn động từ — nếu không hệ thống bảo cán bộ tải lên thứ vừa tải (ca lượt nạp dừng ở cổng review ghi 0 dòng trong khi file đã có).

(2) **Vướng mắc xếp theo CÁCH GỠ, ba lớp:** `need-file-this-period` · `need-other-period-or-confirmation` · `nothing-to-load` (là phát hiện về DN, không phải lỗ hổng dữ liệu). Đo trên dữ liệu thật: 10 lần `not_evaluable` chia 1 / 6 / 3 — tức 9/10 vướng mắc KHÔNG gỡ bằng file của chính kỳ đó. Lớp là **trường bắt buộc trên `NotEvaluable`, per-instance**, không suy theo mã kiểm tra (C4.3 sinh cả ba lớp) và không gán tĩnh theo chỗ gọi (nhánh độ phủ ĐM sinh lớp 2 hay 3 tuỳ còn kỳ trước nào chưa nạp). **Có NĂM nguồn sinh, không phải bốn** — `run_checks` tự ghi trạng thái từ cổng thiếu nguồn mà không dựng đối tượng; đường đó phải dựng `NotEvaluable` và bỏ lệnh ghi thẳng, để còn đúng một kiểu và một đường lưu. Thêm cột `check_runs.remedy` (nullable, `op.add_column` thẳng). Ba cổng mà `requires` không diễn đạt được (C3.3 OR, C6.1 kỳ N−1, cổng ĐM xuyên kỳ) đánh giá bằng cách GỌI chính hàm điều kiện kiểm tra gọi, không viết lại song song.

(3) **Vật chứa màn chuẩn bị dữ liệu = MỘT DN, các kỳ là dòng**, trường mức DN ở đầu màn. Tách khỏi màn phát hiện (giữ tab năm, một kỳ một lúc) — hai phạm vi kỳ khác nhau, gộp thì bộ chọn năm chỉ chi phối nửa trang. Phản hồi nạp hiện TẠI CHỖ, không chuyển sang trang công việc.

(4) **Xem trước Excel: trích xuất một lần vào kho đệm SQLite mỗi (file, trang tính)**, mọi cửa sổ sau là truy vấn khoảng dòng. Ba bộ đọc nhận dạng theo BYTE ĐẦU chứ không theo đuôi file. Bỏ cả ba hạn mức 100 dòng / 40 cột / 25MB.

(5) **Giữ khoá map cột `(DN, slot, chữ ký cấu trúc)`**, không mở rộng liên DN. **Map cán bộ thắng mẫu biểu curate ở mức từng trường, lúc đọc file.**

**Lý do:**

(1) Đủ 4 loại vẫn có thể thiếu ba tháng dòng tờ khai; thước đo phải gắn với thứ sản phẩm làm ra là kết luận kiểm tra. Nhưng `available_sources` trả lời "đã nạp dòng chưa" chứ không phải "đã có file chưa" — hai câu hỏi khác nhau, và trộn lẫn thì thông báo sai.

(2) Cùng một câu lý do không nói được cách gỡ. Đo 9/10 không gỡ bằng file kỳ đó nghĩa là một danh sách phẳng khiến cán bộ đi tìm file không tồn tại. Gắn lớp tại chỗ QUYẾT ĐỊNH là cách duy nhất để bảng điều khiển (tính trước khi chạy) và trạng thái đã lưu (sinh lúc chạy) không lệch nhau.

(3) Cách gỡ lớp 2 trỏ tới **kỳ khác** hoặc **trường của DN** — không cấu trúc theo kỳ đơn lẻ nào chứa được hai thứ đó. `first_bcqt_year` rỗng trên cả 7 DN, tức đang chặn kỳ sớm nhất của mọi DN, mà chỗ sửa nó lại nằm ngoài luồng nạp.

(4) Đo: mở file 71,3MB ở chế độ đọc tuần tự chỉ 1,19 s — hạn mức 25MB là hệ quả của việc đọc trọn trang bằng pandas, không phải chi phí mở. Nhưng chế độ đó CHỈ ĐI TỚI: nhảy tới dòng 200.000 mất 3,87 s, nên cuộn một trang 270k dòng theo cửa sổ là ~1.000 lượt đọc với chi phí tăng dần. Trích xuất trả chi phí đúng một lần. Nhận dạng theo byte đầu vì đuôi file NÓI DỐI: đếm 493 file ra 268 xlsx thật · 185 xls thật · **38 file đuôi `.xls` thật ra là XML SpreadsheetML** (190,8MB) · 2 hỏng — khớp ghi chú "40 file không mở được" sẵn có trong mã. 38 file đó đọc bằng thư viện XML chuẩn hết 3,49 s cho file 64,5MB.

(5) Chữ ký cấu trúc KHÔNG phải định danh đầy đủ của bố cục (chính hàm khớp mẫu từ chối ca cùng chữ ký khác dòng bắt đầu; chữ ký gộp hoa thường, bỏ dấu, bỏ chữ số năm). Tin nhau xuyên DN biến một lần xác nhận sai thành cột đọc lệch im lặng trên cả đội — đúng dạng lỗi đã làm mất 28,5 tỷ. Lợi ích gần bằng 0: bố cục dùng chung giữa các DN chính là 4 họ đã curate, vốn đã tự qua cổng.

**Alternatives loại:**

- *Giữ thước đo "đủ 4 loại"* — rejected: nói "Đã nạp" trong khi kiểm tra âm thầm bỏ qua hoặc chạy trên kỳ khuyết.
- *Đếm cả lớp 3 vào bảng điều khiển* — rejected: "chưa từng khai ĐM" là kết luận về DN, đưa vào phép đếm thì con số không bao giờ đầy và cán bộ đi tìm file không có.
- *Tự chạy lại kiểm tra sau mỗi lượt nạp* — rejected: `run_checks` xoá rồi dựng lại `Finding`, đưa `status`/`notes` cán bộ đã đánh về `new`. Hiện chưa lộ (15.356 finding đều `new`) nhưng lộ ngay khi thí điểm bắt đầu.
- *Giấu điểm rủi ro khi kết quả cũ* — rejected: DN rơi khỏi bảng xếp hạng vì có người tải file lên, cùng dạng sai lầm với việc bỏ luật khỏi thang điểm làm DN sạch hơn (issue #65).
- *Xoá file thì xoá luôn dòng của file đó* — rejected: bảng Tầng 1 không có tham chiếu file nguồn, cần đổi lược đồ. Thay bằng: xoá/thay file dời `data_version`, dòng kỳ báo "cần nạp lại".
- *Đọc thẳng workbook mỗi cửa sổ, không kho đệm* — rejected: đọc tuần tự chỉ đi tới, nhảy sâu là O(n) từ dòng 0.
- *Giữ handle mở xuyên request* — rejected: không giải quyết nhảy lùi, và rò handle.
- *Chuyển 38 file XML bằng LibreOffice/ssconvert* — rejected: phụ thuộc ngoài nặng; thư viện XML chuẩn đủ và đo được 3,49 s.
- *Mở rộng khoá map cột ra liên DN* — rejected, xem lý do (5). Đường tin nhau xuyên DN đã có và CÓ KIỂM DUYỆT: nâng thành mẫu biểu curate qua PR kèm fixture.
- *Gộp màn dữ liệu vào màn phát hiện* — rejected: tab năm sẽ chỉ chi phối nửa dưới trang.
- *Bỏ tab năm, màn phát hiện cũng liệt kê mọi kỳ* — rejected: viết lại 704 dòng template phát hiện, ngoài phạm vi luồng nạp.

**SỬA ADR #18:** mục "nhãn truy nguồn hiện ngay trên dòng file để không hộp đen" — nay dòng file CHỈ hiện thứ có hệ quả (cần xác nhận cột · đọc hỏng · có cảnh báo), toàn bộ căn cứ đọc chuyển sang trang riêng của file. Truy nguồn cách một cú bấm chứ không mất. Nền của thay đổi: `match_source` đang RỖNG trên 15/15 file (đọc một khoá đường parse hiện tại không sinh ra) nên ba trong bốn nhãn đó chưa bao giờ hiện; `parse_layout` rỗng 11/15.

**KHÔNG phải sửa ADR #18:** cổng review. Bản nháp spec ban đầu nói cổng dừng ở MỌI lượt nạp và đề xuất nối tham số `has_saved_map` — SAI. `record_parse_result` đã nâng cột có map lưu lên `officer-confirmed` → `verified` nên cổng trả rỗng và lượt nạp đi thẳng. `has_saved_map` là tham số CHẾT, không lời gọi nào trong sản phẩm. Hành vi "dừng lần đầu mỗi (DN × cấu trúc)" đã đúng như mong muốn.

### 25. Map cột cán bộ áp được cho bố cục MỞ RỘNG — map diễn đạt nhóm cột, đẳng thức kiểm lại sau khi áp (2026-08-07, issue #95; SỬA giới hạn của #84 trong ADR #24 mục 5)

**Bối cảnh:** ADR #24 mục (5) cho map cán bộ thắng mẫu biểu curate ở mức từng trường, nhưng #84 cố ý KHÔNG áp cho nhánh bố cục mở rộng: ở đó một trường đọc bằng TỔNG nhiều cột con `(6a)+(6b)`, còn map lưu chỉ giữ được một chỉ số cột. Hệ quả trên file của hai DN pilot: cán bộ sửa chỉ số cột thì không gì được áp, và theo cổng kiểm tra bằng nhau của #84 thì cột đó cũng không được gắn nhãn "cán bộ xác nhận" — file ở lại trạng thái cần xác nhận vĩnh viễn, không có đường ra.

**Quyết định:**

1. **Map lưu diễn đạt `trường → [cột…]`.** Giá trị JSON nhận cả `int` (một cột — mọi map cũ và toàn bộ bố cục chuẩn) lẫn `list[int]` (nhóm cột con). Không migration; một hàm chuẩn hoá duy nhất (`app.adapters.templates.column_groups`) dùng ở mọi chỗ đọc map.
2. **Nhánh mở rộng ghi CẢ nhóm cột vào `parse_detail.column_map`**, không phải cột đầu nhóm như trước. Màn xác nhận dựng ô nhập từ chính giá trị này, nên ghi cột đầu là đưa cho cán bộ một bố cục sai để xác nhận.
3. **Sau khi áp vị trí của cán bộ, đẳng thức cân đối của biểu được KIỂM LẠI trên map đã áp** (ADR #15). Không đạt ngưỡng 98% → ném `OfficerMapBalanceError`: không nạp dòng nào, chẩn đoán nói đúng nguyên nhân và chỉ chỗ sửa. KHÔNG có nhánh quay về map suy được. Đẳng thức viết lại theo TRƯỜNG (Mẫu 15 suy từ công thức trên file qua bảng số biểu→trường; Mẫu 15a theo đúng cách `resolve_m15a` chia vế cộng/vế trừ) để kiểm được sau khi thay vị trí cột.
4. **Trang tính đã ghim vẫn dò lại bố cục mở rộng.** Lúc xác nhận, biểu mẫu ghim luôn trang tính đang đọc, mà nhánh mở rộng cũ chỉ chạy khi `sheet is None` — nên chính lượt nạp ngay sau khi cán bộ xác nhận sẽ đọc file mở rộng bằng cột cố định. Nay: trang đã ghim mà nhãn tiêu đề trên chính trang đó không xác nhận bố cục chuẩn (`standard_layout_colmap`) thì thử bố cục mở rộng.
5. **Lượt nạp đọc hỏng KHÔNG xoá `parse_detail` cũ.** Căn cứ đọc của lượt trước là thứ duy nhất màn xác nhận dựng ô nhập từ đó; xoá đi là đổi một ngõ cụt lấy một ngõ cụt khác.
6. **Một cột chỉ đọc cho một trường.** Biểu mẫu xác nhận từ chối gán cùng một chỉ số cột cho hai trường, và cổng trùng cột của BCCT chạy LẠI sau khi áp map cán bộ (trước đó chỉ soi bản đồ suy từ nhãn, nên map lưu đưa hai trường về một cột vẫn lọt).

**Lý do:** kiểu hỏng cần chặn không phải "không đoán được bố cục" mà là "map trông hợp lý nhưng ra số sai, im lặng" (ADR #15) — repo này đã mất 28,5 tỷ vì một cột đọc sai không báo gì. Bố cục mở rộng không có nhãn tiêu đề để pin cột; thứ duy nhất chứng minh cách đọc là đẳng thức của chính biểu, nên map cán bộ phải qua đúng cổng đó chứ không được miễn.

**Giới hạn còn ghi rõ:** đẳng thức là lưới chặn, KHÔNG phân biệt hai cột cùng dấu — đổi `export_qty` sang một cột trừ khác VÀ đổi cột kia ngược lại thì vế trừ không đổi và đẳng thức vẫn đúng. Đó đúng là mô hình bằng chứng của ADR #18, và cũng là lý do nhãn cuối cùng là "cán bộ xác nhận" chứ không phải "đã chứng minh". Đường bố cục CHUẨN vẫn chỉ đọc một cột mỗi trường: map nhiều cột ở đó không được áp (và biểu mẫu chặn từ đầu), vì đọc cột đầu nhóm là im lặng bỏ phần còn lại.

**Alternatives loại:**

- *Áp cột đầu nhóm cho gọn* — rejected: chính là lỗi #84 mô tả, im lặng bỏ mất các cột con còn lại.
- *Áp map cán bộ rồi bỏ qua đẳng thức* — rejected: mất luôn thứ duy nhất chứng minh cách đọc ở bố cục mở rộng.
- *Đẳng thức vỡ thì quay về map suy được và nạp tiếp* — rejected: cán bộ nhận một lượt nạp "thành công" đọc bằng bố cục họ không chọn.
- *Sửa ở handler xác nhận (đừng ghim trang tính)* — rejected: ghim trang là quyết định đã có lý do riêng (2026-08-06 mục 3); chỗ sai là adapter hiểu "trang đã ghim" thành "đọc bằng cột cố định".

### 26. SỬA ADR #24 mục (4) — trích xuất xem trước chạy ở LUỒNG NỀN, không trong request (2026-08-07, issue #91)

**Quyết định:** Việc trích xuất trang tính vào kho đệm chạy ở **luồng nền**, sau một khoá chống dựng trùng. Request lấy cửa sổ ô chờ tối đa `preview_wait_seconds` (mặc định 12 giây); quá thì trả **202** kèm tiến độ, và lưới tự hỏi lại cho tới khi kho đệm sẵn sàng.

ADR #24 mục (4) viết **"Dựng NGAY TRONG REQUEST đầu tiên… KHÔNG đẩy vào hàng đợi"**. Vế thứ hai giữ nguyên — vẫn không đẩy vào hàng đợi. Vế thứ nhất **sai** và mục này sửa nó.

**Lý do:** số đo lúc cài #83, trên file thật:

| file | trích xuất lần đầu | cửa sổ sau đó |
|---|---|---|
| xlsx 71,3MB | **164,6 giây** | 5 ms |
| XML SpreadsheetML 64,5MB | 5,4 giây | 2 ms |
| xls BIFF 39,3MB | 7,1 giây | 2 ms |

164,6 giây **vượt ngưỡng cắt 100 giây của Cloudflare**. ADR #24 (4) dựng trên giả định trích xuất mất 10–15 giây; giả định đó đúng với mọi file trong kho **trừ một file**, và file đó lại đúng là loại cán bộ cần soát nhất. Giữ nguyên "dựng trong request" nghĩa là file đó không bao giờ xem được — đúng thứ hạn mức 25MB cũ đang gây ra và cả loạt vé này sinh ra để bỏ.

Chi phí 130 trong 164,6 giây là **hai lượt đọc openpyxl** (60 giây lấy giá trị + 67 giây lấy công thức): chế độ đọc tuần tự chỉ lộ một trong hai mỗi lượt nên không gộp được.

**Alternatives loại:**

- *Giữ "dựng trong request"* — rejected: file 71,3MB đứt kết nối, không xem được.
- *Đẩy vào hàng đợi job* — rejected, và ADR #24 (4) đã loại vì đúng lý do: hàng đợi chạy một việc nạp một lúc, nên một việc trích xuất xếp sau lượt nạp dài bắt cán bộ chờ vài phút chỉ để xem file.
- *Chỉ trích xuất giá trị, bỏ công thức* — rejected: công tắc "hiện công thức trong ô" là thứ đáng lẽ đã bắt được 2.076 ô công thức đọc thành 0 làm mất 28,5 tỷ. Bỏ nó để nhanh hơn 67 giây một lần là đổi sai chiều.
- *Hạ ngưỡng chờ xuống 0, luôn trả 202* — rejected: mọi file khác trong kho xong dưới 10 giây, bắt chúng đi qua vòng hỏi lại là thêm độ trễ không đổi lấy gì.

**Ghi chú:** con số 12 giây là cấu hình (`preview_wait_seconds`), không phải hằng số — chọn để mọi file trong kho trừ file 71,3MB vẫn xong trong đúng một request.

### 27. LÀM RÕ ADR #24 mục (1) — mã "biết khi chạy" ở lại MẪU SỐ nhưng không khoá TỬ SỐ (2026-08-07, issue #103)

**Quyết định:** Tách hai con số. `total_count` giữ nguyên nghĩa "mọi kiểm tra áp dụng cho DN". `predictable_count` = `total_count` trừ số mã **biết khi chạy** (kiểm tra động do admin viết, không khai `requires` nên không dự đoán được). Trạng thái **đủ** so `sufficient_count` với `predictable_count`, KHÔNG với `total_count`. Giao diện hiện cả hai: "Đủ nguồn cho N/M kiểm tra" cộng "K kiểm tra biết khi chạy", và M + K = tổng.

**Lý do:** ADR #24 mục (1) viết "đủ dữ liệu = mọi kiểm tra áp dụng đều có đủ nguồn". Đọc sát chữ thì mã không dự đoán được cũng phải vào tử số mới đủ — mà nó **không bao giờ vào được**, vì bản chất là không dự đoán được. Hệ quả: chỉ cần admin công bố MỘT kiểm tra động, mọi kỳ của mọi DN **vĩnh viễn không bao giờ đọc là đủ**, kể cả khi cán bộ đã nạp hết mọi thứ nạp được. Triệu chứng im lặng: không báo lỗi, chỉ là con số không bao giờ đầy.

Đo lúc phát hiện: bảng kiểm tra động có 1 bản nháp, 0 bản đã công bố — nên lỗi **tiềm ẩn**, bật lên ở lần công bố đầu tiên.

Câu chuyện người dùng 51 chỉ đòi mã không dự đoán được **ở lại mẫu số**, để mẫu số không tự co lại làm DN trông sạch hơn (đúng sai lầm ghi ở issue #65). Nó không đòi tử số không bao giờ đóng được. Mục này giữ vế thứ nhất và bỏ ràng buộc thứ hai vốn không ai yêu cầu.

**Alternatives loại:**

- *Rút mã biết khi chạy khỏi mẫu số* — rejected: đúng sai lầm #65, mẫu số co lại làm DN trông sạch hơn thực tế.
- *Coi mã biết khi chạy là đã đủ nguồn* — rejected: nói dối, hệ thống không biết nó đủ hay không.
- *Giữ nguyên, coi là chấp nhận được* — rejected: cán bộ không bao giờ thấy kỳ nào xong là hỏng đúng thứ cả loạt vé này sinh ra để làm.

**Ghi chú:** nếu MỌI kiểm tra đều là biết-khi-chạy thì `predictable_count` = 0 và trạng thái đọc là đủ. Không tới được chừng nào còn kiểm tra dựng sẵn, nên không có test cho ca đó — ghi lại để người sau khỏi tưởng là sót.

## 2026-08-08 — Mô hình bằng chứng phủ đều bốn biểu · màn gán cột hai chiều

### 28. Tập trường KHAI theo biểu là nguồn sự thật; bằng chứng và ô nhập suy TỪ nó (2026-08-08, issue #110; MỞ RỘNG ADR #18, KHÔNG đổi thang nguồn)

**Bối cảnh — một lỗi cấu trúc, không phải ba lỗi rời.** `bcct.py:276` suy bằng chứng TỪ map cột
(`evidence = {f: … for f in col}`) nên phủ đủ do cách viết. `m15` · `m15a` · `m16` đi NGƯỢC:
`evidence` là danh sách viết tay, map cột suy từ nó (`m16.py:192`, `_EVIDENCE_FIELDS`). Dây chuyền
kéo thẳng vào giao diện: `evidence` → `column_map` → `parse_detail` → `base_map`
(`companies.py:1649`) → ô nhập của biểu mẫu xác nhận. **Trường không có bằng chứng thì không có ô
nhập, cán bộ không sửa được.** Đo được ở `.ai/notes/2026-08-07-ra-bang-chung-bon-slot.md`: m16 đọc
8 trường / có bằng chứng 2; m15 11/8; m15a 10/7; bcct đủ 100%.

**Quyết định — chín mục.**

1. **Tập trường khai theo biểu (declared field set)** là nguồn sự thật cho màn gán cột: mỗi biểu
   khai một lần, màn hiện MỘT DÒNG MỖI TRƯỜNG KHAI. Phỏng đoán của máy thành giá trị điền sẵn,
   không còn là cổng quyết định trường nào hiện ra.
2. **"Bắt buộc" là HAI sự thật khác nhau, không gộp:** *bắt buộc theo biểu* — biểu mẫu chính thức
   có cột đó (khai theo biểu); *có check đọc* — suy từ `CHECK_COLUMNS`. Hai cái nói hai hậu quả
   khác nhau nên cảnh báo khác nhau.
3. **Ràng buộc gán có BA trạng thái:** đã gán cột · chưa gán · **xác nhận không có trong file**.
   Trạng thái thứ ba là lời của cán bộ, ghi lại như `officer-confirmed`. Thiếu nó thì cảnh báo
   "thiếu trường bắt buộc" không có đường đóng — đúng hình dạng bế tắc của #95.
4. **Khai đặt ở MỘT module dưới `app/adapters/`**, mỗi biểu một mục: tên trường · nhãn tiếng Việt ·
   một cột hay nhóm cột · bắt buộc theo biểu. `CHECK_COLUMNS` Ở LẠI `registry.py`. Hằng vị trí cột
   của từng adapter (`_COL`, `_M16_TT39_COLS`, `_M16_DINHMUC_COLS`, `_LABEL_ALIASES`) giữ nguyên —
   chúng trả lời "cột nào", không phải "trường nào". **Test khoá:** mọi khoá trong mọi hằng cột
   phải có mặt trong khai của biểu đó. Chiều ngược để lỏng có chủ ý: trường khai mà bố cục không có
   vị trí mặc định thì tới màn gán ở trạng thái *chưa gán* — đúng ca `_M16_DINHMUC_COLS` thiếu
   `note`.
5. **Gửi biểu mẫu = xác nhận MỌI trường đang hiện.** Hành vi hiện tại (`saved_map.py:117` nâng mọi
   trường trong map lưu lên `officer-confirmed`) giữ nguyên, nhưng kèm NGHĨA VỤ: màn phải hiện, mỗi
   trường, cột đang gán VÀ mẫu giá trị của cột đó. Không hiện đủ thì nhãn "cán bộ xác nhận" là nói
   sai.
6. **Màn gán theo TRƯỜNG (field-major)**, ~8–11 dòng, mỗi dòng một bộ chọn cột mang tiêu đề + mẫu
   giá trị. **KHÔNG dựng** phía cột ("cột này không phải trường nào cả"): dưới bố cục field-major,
   cột không trường nào chọn thì không đọc — đó đã là mặc định của mọi cột, không có gì để ghi.
7. **"Xác nhận không có trong file" lưu ở cột MỚI `saved_column_maps.absent_fields`** (JSON list),
   `column_map` giữ nguyên hình dạng. Hai tập BẤT BIẾN không giao nhau, khẳng định ở một chỗ + test.
8. **`not_evaluable` mức TRƯỜNG nối vào CỔNG TIỀN-DISPATCH đã có** (`sources.py`): adapter ghi
   trường xác nhận vắng vào `parse_detail`, cổng gom theo kỳ như `data_files.py:355` đang gom
   `review`, check nào có `CHECK_COLUMNS` gọi tên `(slot, trường)` vắng thì `not_evaluable`, lớp
   cách gỡ `need-file-this-period`. Ánh xạ dùng `checks_reading()` — **cùng một hàm** sinh cảnh báo
   trên màn và sinh hành vi lúc chạy, nên hai cái không thể nói khác nhau.
9. **Tập trường khai = tập trường adapter GHI vào dòng Tầng 1**, đúng bằng tập nó đang đọc (đã đối
   chiếu: mọi khoá hằng cột đều có cột trong model — `row_no`, các `*_name`, các `*_unit`, `note`).
   Quy tắc này bỏ phán đoán ra khỏi bước mà phán đoán đã hỏng ba lần.

**Hai hậu quả của "bắt buộc theo biểu", tách theo trường có phải KHOÁ DÒNG hay không:**

- thiếu trường là **khoá dòng** (`material_code` m15 · `product_code` m15a · `product_code` +
  `material_code` + `norm_qty` m16 · ba trường sẵn có của bcct) → không dựng được dòng nào → **từ
  chối**, đúng hành vi bcct đang có, đúng dòng 0.1 sổ yêu cầu;
- thiếu trường **bắt buộc mà không phải khoá dòng** (`product_unit`, `material_unit` của m16) →
  **nhận, cảnh báo ở màn gán, đánh dấu file thiếu**, KHÔNG nhận vơ là có check đọc. Dòng 0.2.

**Nền số đo của vế ĐVT (đo 08/08 trên 270.385 dòng đã nạp):** `material_unit` có ở 270.384/270.385
dòng (một dòng rỗng, HONG_AN 2021); `product_unit` rỗng 5.077 dòng, **toàn bộ thuộc HIEP_QUANG
2024** = 65,8% file đó. Đối chiếu ĐVT giữa các nguồn: M16↔M15 22.374 mã chung, lệch **5.088
(22,7%)**; M16↔tờ khai 21.568 mã chung, lệch **5.092 (23,6%)**. Nhưng lệch là **khác từ vựng, không
phải khác đơn vị vật lý**: `PCE` vs `Cái/Chiếc` (4.974 mã), `Mét` vs `MTR`, `Kilogam` vs `KGM` /
`KILO-GRAMMES`, `Đôi/Cặp` vs `PR` / `PAIR`, `Bộ` vs `SETS`, `ROLL` vs `Cuộn`. Và lệch theo FILE chứ
không rải rác: PILOT_006 2024/2025 và ZONSEN 2026 khớp ~100%, còn ZONSEN 2024, ZONSEN 2025,
PILOT_002 2025 khớp **0%** — DN ghi mã ECUS ở biểu này, tên tiếng Việt ở biểu kia.

**Vì thế KHÔNG khai `("m16","material_unit")` / `("m16","product_unit")` vào `CHECK_COLUMNS`.**

*Lý do ghi lần đầu ở đây là SAI và đã sửa:* tôi viết "cần bảng đồng nghĩa đơn vị trước". Kiểm lại thì
**kiểm tra thống nhất ĐVT đã tồn tại và đang chạy** — **C3.3** (`app/checks/c3_classify.py`) đối
chiếu ĐVT giữa M15 · M16 · BCCT qua `uom.compare()` trên hai bảng `uom_canonical` (27 dòng) +
`uom_aliases` (154 dòng), và catalog đề án đánh ✅ cho nó. `resolve_canonical` còn tách được đơn vị
ghép theo `[/,;|]` nên `Cái/Chiếc` · `Đôi/Cặp` resolve bình thường.

Nên con số "5.088 / 5.092 mã lệch chuỗi" ở trên **không phải số phát hiện sai** — phần lớn đã bị bảng
alias hấp thụ trước khi thành phát hiện. Số thật: **140 phát hiện C3.3**, trong đó 94 là lệch
canonical thật và 46 có ít nhất một đơn vị KHÔNG resolve được (`Lon/Can` 1.720 dòng · `Phút vuông`
539 · `UNL` 277; tổng 25/73 chuỗi đơn vị trong dữ liệu không resolve được). `compare()` gộp "không
biết" vào `DIFFERENT` → Nghiêm trọng. Đó là **issue #115**, không thuộc #110.

*Lý do ĐÚNG để không khai vào `CHECK_COLUMNS`:* C3.3 đã phụ trách đúng việc đó, và cổng trường vắng
ở mục 8 là một cơ chế KHÁC (thiếu cột ⇒ không chạy được) — khai ĐVT vào đó là làm trùng vai, hai
đường cùng báo một chuyện bằng hai giọng khác nhau.

**Căn cứ biểu mẫu:** Mẫu số 16/ĐMTT/GSQL, Phụ lục ban hành kèm TT 39/2018/TT-BTC (thay Phụ lục V TT
38/2015). Chín cột: (1) Stt · (2) Mã SP · (3) Tên SP · **(4) Đơn vị tính** · (5) Mã NVL · (6) Tên
NVL · (7) **Đơn vị tính** · (8) Lượng NL, VT thực tế để sản xuất một sản phẩm · (9) Ghi chú. Đối
chiếu trên FILE THẬT (`BCDM_TT39 2024.xls`, sheet `BCTT39`): băng tiêu đề hai tầng + dòng đánh số
`(1)…(9)` khớp từng vị trí với `_M16_TT39_COLS`. **ĐVT là 2/9 cột của biểu**, không phải chú thích
tuỳ chọn.

**ĐÃ KIỂM CHỨNG TỪ NGUỒN GỐC (08/08, sau khi ADR này viết lần đầu).** Hai bản quét Công báo được
trích bằng `pdftoppm` + `tesseract -l vie`; nguyên văn ở
`.ai/notes/2026-08-08-huong-dan-lap-mau-16-tt39.md`.

- **Ràng buộc ĐVT là THẬT, ở CẢ HAI thế hệ văn bản.** Hướng dẫn lập Mẫu 16, cột (4) và cột (7):
  ĐVT "sử dụng thống nhất với mã đơn vị tính doanh nghiệp quản lý tại nhà xưởng sản xuất, với đơn vị
  tính đã khai báo trên tờ khai hải quan". TT 39/2018 Phụ lục II (`25kem6.pdf` tr. 8) và TT 121/2025
  (`121-btc.pdf` tr. 238) đều có. Cột (2) mã SP, cột (3) tên SP, cột (5) mã NVL cũng buộc thống nhất
  với tờ khai — tức có căn cứ pháp lý cho cả một lớp đối chiếu M16 ↔ BCCT, chưa dùng tới.
- **Mẫu 16 ĐÃ BỊ SỬA bởi TT 121/2025** (hiệu lực 01/02/2026), mục "đ) Sửa đổi, bổ sung mẫu số
  16/ĐMTT/GSQL". **Tập cột KHÔNG đổi** (9 cột + chỉ tiêu (10), (11)) và công thức định mức thực tế
  ở cột (8) không đổi — nên `_M16_TT39_COLS` vẫn đúng cho kỳ 2026. Đổi ở cột (9) và ở quy tắc mã/tên
  cho sản phẩm tái nhập.

**Alternatives loại:**

- *Chỉ nới `_EVIDENCE_FIELDS` cho đủ trường, giữ chiều suy cũ* — rejected: vẫn bế tắc khi máy không
  đặt được trường nào, chỉ hẹp hơn.
- *"Bắt buộc" suy hết từ `CHECK_COLUMNS`* — rejected trên số đo: `CHECK_COLUMNS` có **0 mục bcct**
  trong khi 10 check đọc `declaration_lines`, nên mô hình này khai "bcct không cần trường nào".
- *Gộp khai trường vào `registry.py`* — rejected: sửa khai của một check sẽ lặng lẽ đổi thứ cán bộ
  nhìn thấy trên màn gán.
- *Mỗi adapter tự khai* — rejected: m16 có hai bố cục cho cùng một tập trường → khai hai lần, trôi
  lệch, đúng cách `product_code` biến mất.
- *Thêm một bậc "cán bộ đã duyệt" giữa `header-matched` và `builtin-template`* — rejected: cán bộ
  đọc "product_code → cột 1" cạnh mẫu giá trị rồi gửi đã xác nhận đúng bằng người gõ lại số 1.
  "Sửa" vs "để nguyên" không phải khác biệt về độ mạnh bằng chứng; mã hoá thành một bậc là đưa vào
  thang ADR #18 một phân biệt không ứng với cái gì thật.
- *Bảng gán theo CỘT (một dòng mỗi cột file)* — rejected: 257 dòng để diễn đạt 8 sự thật.
- *Sentinel `[]` trong `column_map` cho "vắng"* — rejected: `column_groups` (`templates.py:156`) BỎ
  list rỗng có chủ ý ("giá trị hỏng bị bỏ, không đoán"); nới nó là tiêu mất chính cái chốt #95 dựng.
- *Mỗi check tự kiểm trường vắng* — rejected: 17+ chỗ sửa, check viết sau quên kiểm thì hỏng im
  lặng — đúng lớp lỗi vé này sinh ra để diệt.
- *Ép nạp lại toàn bộ file sau khi deploy* — rejected: `run_checks` dựng lại `Finding` → `status` /
  `notes` cán bộ về `new`, đúng lý do đợt trước cố ý không tự chạy lại check sau khi nạp.

**Ba lỗi im lặng bắt được TRONG lúc grill, chưa có ở ghi chú gốc:**

1. **`m16.note` là ca thứ hai của #109.** Đọc ở cột 8, ghi vào `norms.note`, **C4.1 tiêu thụ**
   (`c4_norm.py:76` gọi `is_domestic_origin`, dòng 77 trừ các mã đó khỏi phạm vi check). Không bằng
   chứng, không badge, không ô sửa. → khai `("m16","note", INDIVIDUAL)` cho C4.1.
2. **`_M16_DINHMUC_COLS` KHÔNG có khoá `note`** → mọi dòng của bố cục đó nhận `note=None`,
   `is_domestic_origin` luôn False, và không tín hiệu nào phân biệt với file thật sự không có hàng
   trong nước. Đo lại 08/08 trên 270.385 dòng: **2.445 dòng có ghi chú** — 1.565 dòng giá trị `X`
   (HONG_AN 2021: 715 · HONG_AN 2022: 850) và **880 dòng giá trị SỐ** (PILOT_004 2025); 267.940
   dòng rỗng.
   *(Bản đầu của mục này ghi "269.505 rỗng, chỉ PILOT_004 có giá trị" — SAI, do đọc nhầm bảng đếm
   theo (DN, kỳ). Số đúng ở trên.)*
2b. **`norms.note` của PILOT_004 2025 BẰNG ĐÚNG `norm_qty` ở cả 880/880 dòng.** Bố cục 004 có hai
   cột định mức; `_detect_actual_norm_col` dời `norm_qty` sang cột ĐM thực tế, mà chỉ số 8 — chỗ
   adapter đọc `note` — chính là cột đó. Tức adapter đọc MỘT cột vào HAI trường, và trường `note`
   của DN này không mang ghi chú nào. Không gây loại nhầm (vì `is_domestic_origin` so `== "x"` nên
   trả False), nhưng đúng lớp lỗi đọc sai im lặng — test chống trôi ở lát 1 phải bắt được.
3. **`CHECK_COLUMNS` có 0 mục bcct** → cổng review chưa bao giờ bắn cho bcct (mục còn mở (b) ở
   STATUS), và cổng mức trường ở mục 8 cũng sẽ câm cho bcct tới khi khai bù.

**Ghi chú — nợ đã biết, KHÔNG thuộc #110, và CHƯA đủ căn cứ để cài:** có tài liệu thứ cấp nói cột
(9) Ghi chú mang **năm** trạng thái (`X` trong nước · để trống = nhập khẩu · `KXDĐM` không xác định
được định mức · `TH` thu hồi từ SP tái nhập · `SPTN` sửa chữa/tái chế SP tái nhập), trong khi
`is_domestic_origin` chỉ so `== "x"`.

**Đã đọc bản quét Công báo 08/08 — khẳng định "năm trạng thái" ĐÚNG MỘT NỬA, và nửa sai là nửa quan
trọng: bộ mã hợp lệ PHỤ THUỘC KỲ.**

| | TT 39/2018 (kỳ ≤ 2025) | TT 121/2025 (kỳ từ 01/02/2026) |
|---|---|---|
| cột (9) | `X` · để trống · `KXDĐM` | thêm `TH` · `SPTN` |

Bản tóm tắt của công cụ tìm kiếm nêu năm trạng thái mà không nói đang mô tả bản nào — đúng với TT
121, sai với TT 39. Kho dữ liệu bắc qua cả hai thế hệ (ZONSEN 2026 thuộc TT 121, mọi kỳ còn lại
thuộc TT 39), nên vé cài sau này **không được hằng số hoá bộ mã**.

Dữ liệu hiện tại chưa dùng tới mã nào ngoài `X`: trong 270.385 dòng, `KXDĐM` · `TH` · `SPTN` xuất
hiện **0 lần**, `X` có 1.565 dòng. Nhưng `KXDĐM` là trạng thái DN tự khai "không xây dựng được định
mức" — đúng thứ cổng độ phủ định mức (C4.9 / `norm_gate`) cần biết, và `is_domestic_origin` hiện chỉ
so `== "x"` nên sẽ xử lý nó y hệt "nhập khẩu, có định mức bình thường".

**Triển khai — ba lát, TIẾN LÊN, không backfill:** (1) module khai + đảo chiều suy bằng chứng ở
m15/m15a/m16 + test chống trôi + `("m16","note")` vào `CHECK_COLUMNS` — đóng #109 và lỗ `note`,
không đổi schema; (2) màn gán cột + cột `absent_fields` + migration; (3) cổng `not_evaluable` mức
trường + khai bù bcct vào `CHECK_COLUMNS`. File đã nạp GIỮ `parse_detail` cũ tới khi có người nạp
lại — mã mới chỉ đổi thứ một lượt parse MỚI sinh ra.
