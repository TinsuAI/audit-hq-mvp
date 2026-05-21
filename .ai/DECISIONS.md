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
