# BACKLOG — Audit-HQ MVP

> Tính năng / cải thiện chờ schedule. Không thay STATUS.md (state hiện tại) hay
> sessions/ (history). Mục nào đi vào sprint → chuyển sang STATUS / session log.

## Multi-user + role-based access

### Tài khoản riêng cho cán bộ HQ
- **Hiện tại**: chỉ 1 cookie session global `admin/admin` (env `AUTH_USER`/`AUTH_PASSWORD`).
- **Cần**: nhiều tài khoản, mỗi cán bộ HQ 1 tài khoản, không dùng chung admin.
- **Scope**: bảng `users(id, username, password_hash, role, created_at, last_login_at)`. Migration mới. Login form lookup theo username, verify hash (argon2 hoặc bcrypt). Admin có UI tạo/xoá user.
- **Roles cần thiết**: `admin` (Trọng Tín/Tinsu), `officer` (cán bộ HQ). Sau này có thể thêm `auditor` (chỉ xem, không sửa).
- **Migrate `AUTH_USER` env**: lần đầu seed 1 user admin từ env (tương tự `seed_ai_defaults`).
- **Out of scope V1**: SSO, 2FA, audit log đăng nhập, password reset email.

### Role-based view (RBAC)
- **`officer` KHÔNG được phép thấy**:
  - `/admin/units` (cấu hình UOM)
  - `/admin/ai` (cấu hình AI)
  - Bất kỳ trang `/admin/*` nào trong tương lai
  - Header link "⚙️ Đơn vị tính", "🤖 AI"
- **`officer` được phép**:
  - `/companies`, `/companies/{code}`, `/findings/{id}`, `/companies/{code}/data`, `/companies/{code}/export`
  - Sidebar AI assistant + chat — nhưng có giới hạn (xem dưới)
- **Officer KHÔNG được phép tạo DN / upload data**: hiện UI cho phép. Nên restrict cho admin. (Khả thi: officer chỉ làm việc trên data admin đã chuẩn bị sẵn.)
- **Implementation**: decorator `@require_role("admin")` cho các route admin. Sidebar template kiểm tra `user.role` trước khi render link.

### Tool-use UI chỉ cho admin
- **Lý do**: cán bộ HQ thấy "đang gọi tool search_findings..." trong chat → confusing, lộ implementation detail. Họ chỉ cần thấy câu trả lời.
- **Hiện tại**: sidebar.js hiện tool_call + tool_result event như message vàng amber.
- **Cần**: trong `sidebar.js`, check `meta.is_admin` (từ `/api/ai/meta`) — nếu false thì silent skip render tool_call + tool_result events. Audit log backend vẫn lưu đầy đủ.
- **API**: `/api/ai/meta` thêm field `is_admin: bool` dựa trên user role.

### Tương quan với feature đang có
- **AI conversation history**: hiện list theo `user` field. Multi-user → cần lọc theo `user_id` đúng — đã đúng rồi (truy vấn `WHERE user = current_user`), nhưng verify thêm khi có nhiều tài khoản.
- **Audit log `/admin/ai` section 5**: hiện hiện ALL conversation của mọi user. Đây là intended behavior cho admin. Officer KHÔNG được vào page này.
- **Page context inject vào system prompt**: không tiết lộ user role cho LLM (an toàn).

### Trình tự đề xuất khi sprint
1. Migration `users` + hash password + login lookup (1 ngày).
2. Decorator `require_role` + restrict admin routes (0.5 ngày).
3. Sidebar tool_use hide for non-admin (0.5 ngày).
4. Admin UI tạo/xoá user (1 ngày).
5. Test cuối: tạo 2 user (admin/cán bộ X), verify không cross access (0.5 ngày).

Tổng: ~3.5 ngày làm việc. Có thể chèn sau Day 7-8 hiện tại (QA + deploy AI) hoặc gộp luôn nếu cán bộ HQ chuẩn bị thử demo.
