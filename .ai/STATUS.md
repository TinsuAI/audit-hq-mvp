# STATUS — Audit-HQ MVP

> **Trạng thái (2026-06-14 — phân quyền theo DN + siết auth + redesign chat):**
> `main` = origin (sạch, đã push), **deploy live xanh** `build_sha=a43b3fa`. Phiên này merge
> **PR #1** (rebase, 4 commit `e53ad70→a43b3fa`) → main → CI "Test & Deploy to Tinsu" xanh.
> **520 test pass**, ruff sạch. Migration head **`c2d3e4f5a6b7`** (2 migration mới phiên này).
>
> App giờ **sẵn sàng thí điểm dữ liệu thật**: (1) **phân quyền theo DN** — officer chỉ thấy DN
> được phân công, cưỡng chế server-side ở mọi route UI lẫn tool AI; (2) **siết auth** —
> rate-limit login, nhật ký truy cập, validate magic-byte upload; (3) **redesign chat** —
> context phân giải cao + history search/nhóm/chip DN.

## Current State

### Production (`audit-hq-demo.tinsu.ai`)
- Build **`a43b3fa`**, healthz ok. Entrypoint container **tự chạy `alembic upgrade head`** lúc
  start → 2 migration mới đã áp trên prod (`user_companies`, `access_events` + cột
  `must_change_password`). KHÔNG cần thao tác migration tay khi deploy.
- **AI provider:** OpenRouter → `deepseek/deepseek-v4-pro` (primary, key `sk-or-v1-8…b629`),
  fallback Gemini. Key chung prod + local.
- **Phải làm thủ công sau deploy:** admin vào `/admin/users` → "Phân công DN" cho từng officer.
  Officer chưa được gán sẽ thấy **trống** (default an toàn chủ đích). Admin hiện tại thấy tất cả.

### Stack / DB
- Python 3.12, FastAPI, SQLAlchemy+Alembic, SQLite (WAL). Dev port **8200**.
- Migration head **`c2d3e4f5a6b7`**. Phiên này thêm: `b1c2d3e4f5a6` (user_companies),
  `c2d3e4f5a6b7` (must_change_password + access_events).

## Recent Changes (2026-06-14, PR #1 — 4 commit)
1. **`e53ad70` docs(ai):** handoff phiên trước (document UX + NL checks) — chỉ docs.
2. **`acc34ff` feat(auth) — P1+P2:**
   - **P1 phân quyền DN:** `app/scoping.py` (`allowed_company_ids/codes`, `get_company_or_404`,
     `can_access_company_id`), bảng `user_companies`. Lọc danh sách DN + mọi route
     `/companies/{code}` và `/findings/{id}` (404 — không 403). **AI dùng chung ranh giới:**
     `run_tool(..., allowed_codes)` chặn tool theo company_code + lọc `list_companies`/`get_finding`;
     **`query_sql` lọc bằng TEMP VIEW** shadow `v_*` (an toàn cả aggregate). Trang admin phân công
     DN. Người tạo DN tự được gán.
   - **P2 siết auth:** `app/login_guard.py` (rate-limit IP), `AccessEvent`+`app/audit.py`+
     `/admin/audit` (nhật ký egress/hành động), validate magic-byte upload, cảnh báo startup nếu
     `AUTH_PASSWORD` mặc định, trang `/change-password`.
3. **`77f625a` feat(ai) — P3 chat:** `getPageContext()`+`build_page_context()` phân giải cao
   (mã hàng / bảng dữ liệu+lọc / nhãn trang); history search + nhóm thời gian + chip DN.
4. **`a43b3fa` docs(features):** `.ai/features/2026-06-14-permissions-auth-and-chat/` (brief.md +
   8 screenshots + `ui_smoke.py`) — **adopt convention feature-folder của data-hub/barry-CO-main**.

## Next Steps (ưu tiên)
1. **Phân công DN cho officer trên prod** (admin → `/admin/users` → "Phân công DN"). Chưa làm thì
   officer (nếu tạo) thấy trống.
2. **Combo +20 điểm tổ hợp — review logic** (carry, user "quyết sau"): flat +20 mọi combo, nhị
   phân (xem `app/checks/scoring.py:179`). Cân nhắc badge-không-điểm / có-trần / weighted.
3. (Tuỳ) **Bật lại buộc đổi mật khẩu** nếu cần — plumbing còn nguyên (cột + field + tham số
   `set_password(must_change=)`), chỉ cần restore gate trong `require_user` + set `must_change=True`
   ở `users_create`/`users_change_password`. User đã yêu cầu TẮT phiên này ("hơi phiền").
4. (Tuỳ) Xoá nhánh local cũ đã merge: `feat/ai-assistant`, `feat/document-ux-and-nl-check-authoring`.
5. (Tuỳ) Dữ liệu test local còn `ZZ_DEMO` (DN throwaway) — user chưa quyết xoá/giữ.

## Blockers
- Không có blocker. Lưu ý đĩa tinsu ~97% (theo dõi khi deploy lâu dài).

## Notes for Next AI Session

### Phân quyền (P1) — cách hoạt động
- `admin` = `allowed_* → None` (không giới hạn). `officer` = tập DN trong `user_companies`.
- MỌI lối vào lọc theo tập đó. Thêm route theo DN mới → BẮT BUỘC dùng `get_company_or_404(db, code, user)`.
- **AI tool scoping** ở `app/ai/tools.py run_tool`: `_GUARD_COMPANY_CODE` (chặn) +
  `_INJECT_ALLOWED` (lọc). `query_sql` → `app/ai/sql_tool.py install_scoped_views` (TEMP VIEW).
  Thêm tool mới đụng DN → nhớ thêm vào 1 trong 2 set.

### Auth (P2)
- Rate-limit **in-memory/1 process** (`app/login_guard.py`) — reset khi restart container.
- Nhật ký: gọi `log_access(db, username=, action=, company_code=, detail=)` ở điểm egress/hành động.
- `must_change_password`: feature buộc-đổi **đã tắt** (gate gỡ khỏi `require_user`), trang tự đổi vẫn còn.

### Chat (P3)
- Context: `app/static/sidebar.js getPageContext()` (frontend bóc URL) → `app/ai/system_prompt.py
  build_page_context()` (render). Thêm trang mới muốn AI ý thức → thêm pattern ở cả 2 chỗ.
- Frontend JS KHÔNG có test harness → verify bằng `node --check` + ảnh chụp.

### Chụp ảnh UI (convention mới)
- **Mật khẩu admin local KHÔNG biết** (DB = mirror prod, seed không chạy vì bảng users không trống).
  → Chụp ảnh bằng `ui_smoke.py` trong feature folder: seed user throwaway `shot_*` + hội thoại →
  Playwright chụp → dọn sạch. Chạy: `PYTHONPATH=. .venv/bin/python .ai/features/<slug>/ui_smoke.py`
  (dev server :8200 phải chạy + AI enabled để hiện FAB chat).
- Playwright ở `.venv` (1.60) + chromium cached. Screenshots **commit** dưới `.ai/features/<slug>/screenshots/`.

### Môi trường / gotcha (carry)
- Dev server nền hay bị thu hồi → bật lại:
  `nohup .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`
- **DB local = mirror prod (DN_001..004) nhưng `data/` symlink trỏ tên thật** → DN demo không có
  file local; test upload bằng DN throwaway. DN_001..004 CÓ findings/score (chạy được chat/scoring).
- Shell mặc định **zsh** — cú pháp bash assoc array (`declare -A`) lỗi "bad substitution".
- WSL ssh: `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`.

### Deploy flow
- Push `main` → CI "Test & Deploy to Tinsu" (self-hosted runner): test+lint → docker build → restart
  → entrypoint chạy `alembic upgrade head` + seed UOM → healthcheck. Watch: `gh run watch <id> --exit-status`.

### Văn phong điểm / disclaimer (giữ nguyên)
- "bài kiểm tra" (KHÔNG "phép"), "kịch khung", "quy mô dữ liệu". Điểm rate-based, mỗi bài tối đa 10
  theo tỷ lệ, không cộng dồn. Finding "Loại trừ" không tính + recompute ngay.
- Disclaimer: "chỉ số rủi ro dữ liệu BCQT… KHÔNG phải đánh giá tuân thủ theo TT 81/2019/TT-BTC".
