# Session 2026-06-14 — Redesign Trợ lý AI (chat)

Nối tiếp backlog P3 "redesign chat" (DECISIONS #14). Commit: **`444f5ed`** (chưa push).

## What Was Done

### Phase 1 — Tool-use compact
- Thay 2 hộp vàng `.ai-msg.tool` mỗi tool (⏳ gọi + ✓ preview 300 ký tự) bằng **dải pill gọn**:
  `⚙ tên_tool …` (running, icon xoay) → `✓ tên_tool` (done, ~20px). Bấm pill 'done' bung/ẩn preview
  trong `<pre>`. Nhiều tool/lượt gom 1 strip. Khớp running→done theo thứ tự backend phát call→result
  (không cần id). Spinner tự dừng nếu stream đứt. Replay lịch sử render pill 'done'.
- File: `app/static/sidebar.js` (→ sau dời vào lõi), `app/static/sidebar.css`.

### Phase 2 — Lõi chung + trang /chat + URL conversation
- **`app/static/chat-core.js`** (mới): `AuditChat.create(cfg)` → instance đóng state trong closure
  (stream SSE, render markdown/citation, tool-pill, download chip, action proposal, loadConversation,
  mention). `AuditChat.util` chứa helper + `renderConversationList` dùng chung.
- **`app/static/sidebar.js`**: viết lại thành mount mỏng (FAB/panel/history overlay/gợi ý) gọi lõi.
- **Trang `/chat`**: `app/templates/chat.html` + `app/static/chat-page.js` + `app/static/chat-page.css`
  + route `app/routes/chat_page.py` (`/chat`, `/chat/{id}`). 2 cột (danh sách trái + chat phải).
  URL `/chat/{id}` qua `history.pushState` + xử lý `popstate`. Nav thêm "💬 Trợ lý" (base.html).
  FAB ẩn trên `/chat` (base.html: include sidebar khi `not hide_chat_fab`).
- `_ai_sidebar.html`: nạp `chat-core.js` trước `sidebar.js`.

### Phase 3 — Mention @DN / @finding
- Endpoint `GET /api/chat/mentions?q=` (`app/routes/ai.py`): trả companies (name/slug/code ilike) +
  findings (title/id), **lọc theo `allowed_company_codes`** (officer chỉ DN mình).
- FE (trong `chat-core.js`): gõ `@` → dropdown `.ai-mention-pop` (🏢 DN + 📎 finding), điều hướng
  ArrowUp/Down/Enter/Tab/Esc (chặn submit khi popup mở bằng `stopImmediatePropagation`), chèn chip,
  theo dõi `pendingMentions`, gửi kèm `mentions` (lọc theo token còn trong câu), clear sau gửi.
- BE: `_resolve_mentions(db, raw, allowed_codes)` xác thực lại scope → `page_context["mentions"]` →
  `build_page_context(..., mentions=)` render "Người dùng vừa nhắc tới: …" (`app/ai/system_prompt.py`).

### Phân quyền chat (theo yêu cầu user giữa phiên)
- Yêu cầu: (1) AI chỉ chạm DN của user; (2) user chỉ xem chat của mình. Audit: (1) đã enforce từ P1
  (`allowed_codes`→`run_tool`, TEMP VIEW); (2) đã enforce ở mọi endpoint conversation. **Thiếu test** → bổ sung.
- Sau đó user chốt **"Admin view được hết"**: đổi `list_conversations` (admin bỏ filter user, thêm field
  `owner`), `get_conversation_messages` + page `/chat/{id}` cho admin bypass ownership; `/api/ai/meta`
  thêm `username`. FE: `renderConversationList` hiện badge 👤 chủ + **ẩn nút xoá** cuộc của người khác.
  **Xoá/ghi vẫn owner-only** (chủ đích).

### Test + proof
- `tests/test_chat_ownership.py` (6): list chỉ của mình (officer); officer không đọc/xoá/mở cuộc người
  khác; admin đọc-được-hết (API+trang+list+owner) nhưng KHÔNG xoá được cuộc người khác.
- `tests/test_chat_mentions.py` (4): endpoint scoped (officer không thấy DN khác kể cả gõ đúng tên);
  admin thấy hết; `_resolve_mentions` chặn DN/finding ngoài phạm vi; admin (allowed=None) không giới hạn.
- Proof commit `.ai/features/2026-06-14-chat-redesign/`: `brief.md` + `ui_smoke.py` (deterministic, KHÔNG
  gọi LLM — seed cuộc có tool message để replay pill) + 5 screenshots.
- Kết quả: **533 test pass**, ruff sạch, `node --check` cả 3 JS.

## Decisions Made
- **1 lõi vanilla dùng chung, 2 mount** thay vì 2 codebase chat. Không build chain. Sidebar còn lại cho
  hỏi nhanh tại-chỗ; trang `/chat` cho phiên sâu + URL chia sẻ + mention rộng rãi.
- **Mention chèn text thường + theo dõi token** (không dùng contenteditable cho MVP); xoá token khỏi câu
  = bỏ mention. Server **resolve lại scope** → mention KHÔNG phải lối lách phân quyền.
- **Admin read-all NHƯNG không delete-all**: ranh giới "giám sát" ≠ "quản trị/xoá dữ liệu người khác".
  Nếu sau muốn admin xoá được → mở thêm (đã hỏi user, user chỉ cần view-all).
- **ui_smoke deterministic**: replay cuộc seed sẵn (có tool message) để chụp pill mà không phụ thuộc LLM
  → ảnh tái lập được, CI/người sau chạy lại cho kết quả y hệt.
- **Không thêm migration**: dùng lại `ai_conversations`/`ai_messages`; chỉ thêm field `owner`/`username`
  ở response JSON, không đụng schema.

## What Didn't Work
- Playwright `wait_for_selector(".ai-mention-pop[hidden]")` để chờ dropdown đóng → timeout (element
  hidden không bao giờ "visible"). Sửa: `state="hidden"`.
- `ls -t .ai/sessions/` qua Bash tool trả nhầm thư mục gốc (alias zsh) → dùng `/bin/ls -1t <abs>/*.md`.
- PIL không có trong `.venv` → không crop ảnh bằng Python; thay bằng `page.locator(...).screenshot()`
  (element-clip) cho ảnh rõ.

## Open Items
- **Chưa push `main`** (ahead origin 1 = `444f5ed`) → prod chưa có chat redesign. Push để deploy.
- `.ai/STATUS.md` (cập nhật phiên này) + `.ai/sessions/2026-06-14-company-slug-urls.md` (phiên trước,
  chưa commit) còn uncommitted — chưa gộp vào commit nào.
- Backlog carry: phân công DN officer trên prod; review combo +20 (`scoring.py:179`); polish admin
  code-text + hậu tố `(Demo)`; bật lại buộc đổi mật khẩu; xoá nhánh local đã merge; quyết `ZZ_DEMO`.
- Chat mở rộng (tuỳ): phân trang list cho admin (cap 30); mention nhiều thực thể; rich-chip input.
