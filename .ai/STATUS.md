# STATUS — Audit-HQ MVP

> **Trạng thái (2026-06-14 — redesign chat, P3 backlog):**
> Phiên này hoàn tất **redesign Trợ lý AI** (3 phase + phân quyền chat), commit **`444f5ed`**.
> **`main` ĐANG AHEAD origin 1 commit — CHƯA PUSH, CHƯA DEPLOY.** Prod live vẫn `5eef7c5`.
> **533 test pass**, ruff sạch. Migration head **`d3e4f5a6b7c8`** (KHÔNG đổi — chat dùng lại
> bảng `ai_conversations`/`ai_messages` sẵn có, không thêm schema).

## Current State

### Git / deploy
- **Local `main` = `444f5ed`** (chat redesign), **origin/main = `5eef7c5`** → ahead 1, **chưa push**.
  Push `main` sẽ kích CI "Test & Deploy to Tinsu" → build + deploy + `alembic upgrade head`.
  Vì không có migration mới, deploy chat redesign chỉ là code/static/template (an toàn).
- Uncommitted còn lại (CHỦ ĐÍCH để ngoài commit chat): ` M .ai/STATUS.md` (file này),
  `?? .ai/sessions/2026-06-14-company-slug-urls.md` (session log phiên slug trước, chưa commit).

### Trợ lý AI — redesign (MỚI phiên này)
- **Tool-use gọn**: mỗi tool = 1 pill `⚙ tên…`→`✓ tên` (bấm bung preview) thay hộp vàng to.
- **Trang riêng `/chat`** (nav "💬 Trợ lý"): 2 cột (danh sách cuộc trái + chat phải),
  **URL có nghĩa `/chat/{id}`** (pushState + back/forward), FAB ẩn trên trang này.
- **Mention `@DN`/`@finding`**: gõ `@` ra dropdown (🏢 DN + 📎 finding), chèn chip, gửi kèm.
- **Lõi chung** `app/static/chat-core.js` — sidebar (FAB) lẫn trang `/chat` cùng mount lên nó.
- **AI provider**: OpenRouter → `deepseek/deepseek-v4-pro` (primary), fallback Gemini. Key chung.

### Phân quyền chat (đã siết + có test)
- **AI tool theo DN**: `chat_stream` tính `allowed_company_codes(db, user)` → mọi `run_tool`;
  `query_sql` lọc bằng TEMP VIEW. Mention cũng resolve lại scope server-side (`_resolve_mentions`).
- **Cuộc trò chuyện**: **admin ĐỌC ĐƯỢC HẾT** (list của mọi user + badge 👤 chủ; mở messages +
  trang `/chat/{id}` của bất kỳ ai). **Xoá/ghi vẫn OWNER-ONLY** (admin không lỡ tay xoá lịch sử
  người khác — chủ đích "giám sát ≠ quản trị dữ liệu người khác"). Officer chỉ thấy của mình.

### Định danh DN (slug vs code) — giữ nguyên từ phiên trước
- `code` (DN_xxx) = khoá lưu trữ/AI/job/log nội bộ, KHÔNG hiển thị. `slug` = URL + hiển thị.
- Resolver `get_company_or_404(db, slug-or-code, user)`. Chi tiết: session `2026-06-14-company-slug-urls.md`.

### Stack / DB
- Python 3.12, FastAPI, SQLAlchemy+Alembic, SQLite (WAL). Dev port **8200**.
- Migration head **`d3e4f5a6b7c8`**.

## Recent Changes (2026-06-14 — commit `444f5ed`)
Xem chi tiết: session `2026-06-14-chat-redesign.md` + feature proof `.ai/features/2026-06-14-chat-redesign/`.
1. **Phase 1** — tool-use compact pills (`sidebar.js`/`chat-core.js` + CSS).
2. **Phase 2** — tách `chat-core.js` (lõi chung); `sidebar.js` thành mount mỏng; trang `/chat`
   (`chat.html`, `chat-page.js`, `chat-page.css`, route `app/routes/chat_page.py`); URL `/chat/{id}`.
3. **Phase 3** — mention: endpoint `/api/chat/mentions` (scoped), `_resolve_mentions`, inject vào
   `build_page_context` (`app/ai/system_prompt.py`).
4. **Phân quyền chat** — admin read-all conversation (`/api/chat/conversations` + messages + page);
   owner-only delete/write; `/api/ai/meta` thêm `username`; FE badge chủ + ẩn nút xoá cuộc người khác.
5. **Test** — `tests/test_chat_ownership.py` (6), `tests/test_chat_mentions.py` (4).

## Next Steps (ưu tiên)
1. **Push `main`** để deploy chat redesign (nếu user muốn) — watch `gh run watch <id> --exit-status`.
   Không cần thao tác migration tay (head không đổi).
2. **Phân công DN cho officer trên prod** (admin → `/admin/users` → "Phân công DN") — carry, thao tác tay.
3. **Combo +20 điểm tổ hợp — review logic** (carry, user "quyết sau"): flat +20 mọi combo, nhị phân
   (`app/checks/scoring.py:179`). Cân nhắc badge-không-điểm / có-trần / weighted.
4. (Tuỳ) Polish carry: admin còn hiện text `code` (`admin_user_scope.html`, `admin_checks_new.html`);
   tên hiển thị còn hậu tố `(Demo)`; bật lại buộc đổi mật khẩu; xoá nhánh local đã merge; quyết `ZZ_DEMO`.
5. (Tuỳ) Mở rộng chat: phân trang list cho admin (đang cap 30); mention nhiều thực thể; rich-chip input.

## Blockers
- Không có. Lưu ý đĩa tinsu ~97% (theo dõi khi deploy lâu dài).

## Notes for Next AI Session

### Chat redesign — điểm cắm (MỚI)
- **Lõi chung** `app/static/chat-core.js`: `AuditChat.create({messagesEl,inputEl,submitEl,isAdmin,
  onConversationChange,pageContextFn})` → instance (stream, render, tool-pill, mention, loadConversation).
  `AuditChat.util` = el/getPageContext/getSuggestions/renderMarkdown/parseCitations/apiList/
  apiMessages/apiDelete/apiMeta/renderConversationList. **Sửa hành vi chat → sửa ở đây, KHÔNG ở 2 mount.**
- **Mount**: `sidebar.js` (FAB/panel/history overlay) + `chat-page.js` (trang, pushState, list luôn hiện).
  Thêm mặt mới → tạo mount mỏng gọi `AuditChat.create`, đừng nhân đôi engine.
- **Backend chat** ở `app/routes/ai.py` (prefix `/api`): `/chat/stream` (SSE), `/chat/conversations`
  (+`/{id}/messages`, DELETE), `/chat/mentions`, `/chat/run-checks`, `/chat/export-query`, `/ai/meta`.
  Trang HTML ở `app/routes/chat_page.py` (`/chat`, `/chat/{id}` — enforce ownership, admin bypass).
- **Mention an toàn**: client gửi `mentions:[{type,code/id}]`; `_resolve_mentions(db, raw, allowed_codes)`
  tra DB + chặn scope lại (KHÔNG tin client) rồi nhét `page_context["mentions"]` → system prompt.
- **base.html**: sidebar chỉ include khi `not hide_chat_fab`; trang `/chat` set `hide_chat_fab=True`.

### Phân quyền (P1, carry)
- `admin` = `allowed_* → None`. `officer` = tập DN trong `user_companies`. Mọi lối vào lọc theo đó.
- AI tool scoping `app/ai/tools.py run_tool`: `_GUARD_COMPANY_CODE` + `_INJECT_ALLOWED` + `args.pop(
  "allowed_codes")`; `query_sql` → `app/ai/sql_tool.py install_scoped_views`. Tool mới đụng DN → thêm vào.

### Render trang thật / chụp ảnh UI (carry + cập nhật)
- **Mật khẩu admin local KHÔNG biết** (DB mirror prod). Render/chụp cần auth: seed user tạm `shot_*`
  (role admin) qua `app.auth_users.create_user`, login `TestClient`/Playwright (field `user`+`password`,
  POST `/login`), thao tác, rồi xoá.
- **Proof commit**: `.ai/features/<slug>/ui_smoke.py` (Playwright 1.60 ở `.venv`, chromium cached),
  ảnh dưới `screenshots/`. Phiên này: `.ai/features/2026-06-14-chat-redesign/ui_smoke.py` —
  **deterministic, KHÔNG gọi LLM** (seed cuộc có sẵn tool message để replay pill; mention dùng endpoint DB).
  Chạy: `PYTHONPATH=. .venv/bin/python .ai/features/2026-06-14-chat-redesign/ui_smoke.py` (dev :8200 + AI bật).
- Scratch screenshot → thư mục gitignored `.tmp-*` (đừng commit).

### Môi trường / gotcha (carry)
- Dev server :8200 hay đã chạy sẵn (`make dev`/`--reload`). `curl :8200/healthz` 200 = đang sống.
  Nền: `nohup .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8200 > /tmp/audit-hq-dev.log 2>&1 &`.
- **Frontend JS verify**: `node --check app/static/<file>.js` (dòng `compdef…` là noise zsh, bỏ qua) + ảnh.
- DB local = mirror prod (DN_001..005) nhưng `data/` symlink trỏ tên thật → DN demo không có file local;
  test upload bằng DN throwaway (ZZ_DEMO). DN_001..004 CÓ findings/score.
- Lint scope = `app tests scripts` (Makefile); `migrations/` KHÔNG lint.
- Backup DB trước migrate bằng `sqlite3 .backup` (WAL-safe), KHÔNG `cp` file đơn lẻ.
- Shell mặc định **zsh**. WSL ssh: `ssh.exe -F 'C:\Users\vuong\.ssh\config' tinsu`.

### Deploy flow (carry)
- Push `main` → CI "Test & Deploy to Tinsu" (self-hosted): test+lint → docker build → restart →
  entrypoint `alembic upgrade head` + seed UOM → healthcheck. Watch: `gh run watch <id> --exit-status`.

### Văn phong điểm / disclaimer (giữ nguyên)
- "bài kiểm tra", "kịch khung", "quy mô dữ liệu". Điểm rate-based, mỗi bài tối đa 10, không cộng dồn.
- Disclaimer: "chỉ số rủi ro dữ liệu BCQT… KHÔNG phải đánh giá tuân thủ theo TT 81/2019/TT-BTC".
