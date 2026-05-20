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

### 6. Symlink `data/` thay vì duplicate

**Quyết định:** `audit-hq-mvp/data` là symlink tới `audit-hq/data/raw/`. Cả 2 repo gitignore raw.

**Lý do:** Tránh duplicate 500MB. Source of truth duy nhất.

**Trade-off:** Developer mới clone phải tự `ln -s ../audit-hq/data/raw data` — note trong README.
