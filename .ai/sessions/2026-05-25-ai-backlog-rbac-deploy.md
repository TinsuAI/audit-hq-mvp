# Session 2026-05-25 — AI backlog + RBAC + deploy

## Làm gì

Tiếp tục từ session Day 1-6 (AI assistant đã build xong). Session này hoàn thiện toàn bộ backlog + tech debt + deploy lên prod.

**Commits trong session:**
- `1ffbff3` feat(backlog): multi-user auth + RBAC + AI tech debt (Day 7-8)
- `9dee37c` fix(rbac): officer được phép tạo DN + upload — chỉ /admin/* cần admin
- `088e62d` feat(ai): make tool call cap configurable via DB setting
- `cb0330d` fix(sidebar): ẩn tool history khi load conversation cho officer
- `8fa294c` docs: update STATUS.md
- Merge commit → push → CI deploy thành công

## Những gì đã làm

### Multi-user RBAC (từ BACKLOG.md)
- Bảng `users` + migration `b7e91f4d2a13`. PBKDF2-SHA256 600k iterations (stdlib, no new dep).
- `SessionUser(name, role)` dataclass — `__str__` trả về name để không break `{{ user }}` templates cũ.
- Role baked-in signed cookie tại login (`{u, r}`) — không hit DB mỗi request.
- `require_user` (any logged-in) vs `require_admin` (403 nếu không phải admin).
- Admin UI `/admin/users`: list/create/change-password/delete. Guard: không xoá last admin, không xoá self.
- `seed_default_admin` từ env `AUTH_USER`/`AUTH_PASSWORD` — idempotent, chỉ seed khi bảng trống.

### Officer permissions
- Officer được: xem DN, tạo DN, upload, run-checks, AI chat.
- Officer không được: `/admin/*` (units, AI config, users).
- Sidebar: tool_call + tool_result events ẩn cho officer — check `metaCache.is_admin` cả SSE lẫn history load.

### AI tech debt
- Guardrails: forbidden phrase redaction + missing citation warning (`app/ai/guardrails.py`).
- Retention cron: asyncio task 24h, xoá conversation + orphan messages theo DB settings.
- Admin conversation drill-in: `/admin/ai/conversations/{id}`.
- `tool_call_cap` DB setting (default 10) thay thế hardcoded `MAX_TOOL_LOOP = 5`. Admin đổi qua `/admin/ai` Section 3.

### Bug fix
- `loadConversation` trong sidebar.js render tool result history không check `is_admin` → officer thấy tool events khi mở conversation cũ. Fix: thêm `&& metaCache && metaCache.is_admin` vào condition.

### Deploy
- Merge `feat/ai-assistant` → `main` → push → CI deploy thành công (2m32s).
- Mirror DB local lên prod: `scp.exe` → `/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite`.
- Restart container để pick up DB mới.
- Prod live: `https://audit-hq-demo.tinsu.ai`. Accounts: `admin/admin`, `demo/demouser`.

## Quyết định

- Officer được tạo DN + upload (user xác nhận sau khi ban đầu restrict admin-only). Chỉ `/admin/*` cần admin.
- PBKDF2-SHA256 stdlib thay vì bcrypt/argon2 — MVP 1 instance, tránh thêm dep.
- Role trong cookie (không DB lookup mỗi request) — stale role resolved by re-login.
- `tool_call_cap` DB-backed thay hardcoded — admin có thể tăng live cho query phức tạp.

## Không làm / defer

- QA thực tế với OpenRouter (cần key, ngoài scope code session).
- SSO, 2FA, password reset email.
- Prompt regression test set.

## Trạng thái sau session

190 tests pass. Prod live với đầy đủ tính năng. Không còn TODO code nào blocking.

## Sau handoff

- README rewrite (`fbbef15`) — thêm đầy đủ 4 nhóm tính năng, env vars, bảng biến môi trường.
- Soạn tin nhắn gửi team → `C:\temp\toss\audit-hq-demo-update.txt`.

## Open items

- Theo dõi cost/latency thực tế sau khi cán bộ HQ dùng thử.
- Xoá `audit_hq.sqlite.bak-*` trên local (untracked, 18M).
