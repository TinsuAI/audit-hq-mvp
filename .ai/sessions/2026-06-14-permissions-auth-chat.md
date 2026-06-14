# 2026-06-14 — Per-DN permissions + pilot auth hardening + chat redesign

> Phiên dài: chuyển app từ "demo nội bộ" sang **sẵn sàng thí điểm dữ liệu thật**. Ba phase
> (P1 phân quyền DN, P2 siết auth, P3 redesign chat), gói trong **PR #1** (4 commit
> `e53ad70→a43b3fa`), merge rebase → `main` → **deploy live xanh** (`a43b3fa`). 520 test pass,
> ruff sạch. Migration head `c2d3e4f5a6b7`.

## What Was Done

### Khởi đầu: đổi hướng từ user
User muốn **phân quyền người dùng** + redesign chat. Quét code phát hiện 2 điểm quan trọng:
- Chat **đã** per-user (ownership-verified ở `ai.py:169/337/567`) — KHÔNG dùng chung như user
  tưởng; chỉ `/admin/ai` (audit) thấy mọi hội thoại.
- Context awareness + history **đã có** ở mức cơ bản → việc thực là *nâng cấp*, không làm mới.
- DN thì **đúng**: mọi user thấy tất cả (`select(Company).all()` không lọc).

User chốt **mô hình (a) nội bộ** (officer↔DN, khách không đăng nhập), **thí điểm thật**. Chia
3 phase: P1 cô lập dữ liệu (chặn pilot) → P2 siết auth → P3 chat.

### P1 — Phân quyền theo DN (`feat(auth)` acc34ff)
- `user_companies` (M2M) + migration `b1c2d3e4f5a6`. `app/scoping.py`: `allowed_company_ids/codes`
  (None=admin), `get_company_or_404`, `can_access_company_id`. DN ngoài phạm vi → **404 (không
  403)** để không lộ tồn tại.
- Lọc danh sách DN; thay ~15 lookup trong `companies.py` bằng `get_company_or_404` (1 lượt
  `replace_all` vì block giống hệt); scope 2 route `/findings/{id}`; người tạo DN tự được gán.
- **AI scoping (điểm cốt lõi — nối phân quyền + chat):** 12 tool AI vốn đọc *toàn bộ* DN → nếu chỉ
  khoá UI, officer hỏi AI "liệt kê hết DN" là lách. `run_tool(name, args, db, allowed_codes)`:
  `_GUARD_COMPANY_CODE` chặn tool theo `company_code`, `_INJECT_ALLOWED` lọc `list_companies`/
  `get_finding`/`query_sql`. `query_sql` → `install_scoped_views` tạo **TEMP VIEW** shadow `v_*`
  với `WHERE company_code IN (allowed)` (lọc tại nguồn → an toàn cả COUNT/SUM; `main.v_*` bị guard
  chặn). Endpoint export-query + run-checks cũng scoped.
- Trang admin phân công DN (`/admin/users/{id}/scope`, checkbox).
- `tests/test_scoping.py` (helper + tool scoping + TEMP VIEW aggregate + route e2e).

### P2 — Siết auth (`feat(auth)` acc34ff, cùng commit P1)
- `app/login_guard.py`: rate-limit login theo IP (8 sai/5 phút → khoá 5 phút, in-memory).
- `AccessEvent` + `app/audit.py` + `app/routes/admin_audit.py` (`/admin/audit`): nhật ký egress/
  hành động (download/export/export_query/run_checks). Instrument ở companies.py + ai.py.
- Validate magic-byte upload (xlsx=PK, xls=OLE2) trong `_write_upload_stream`.
- `must_change_password` + trang `/change-password` + cảnh báo startup nếu `AUTH_PASSWORD` mặc định.
- `tests/test_p2_hardening.py`.

### P3 — Redesign chat (`feat(ai)` 77f625a)
- **Context phân giải cao:** `getPageContext()` bóc thêm mã hàng (`/items/{code}`), bảng dữ liệu
  + lọc (`/data?table=&q=`), nhãn loại trang; `build_page_context()` render. Gợi ý thích ứng.
- **History:** ô search (nội dung/mã DN), nhóm theo thời gian (Hôm nay/Hôm qua/7 ngày/Cũ hơn),
  chip DN suy từ `page_url_seed`. Toàn bộ frontend (`sidebar.js`/template/css) + `system_prompt.py`.
- `tests/test_system_prompt_context.py`.

### Screenshots + PR
- Tham khảo `data-hub` + `barry-CO-main` → adopt convention `.ai/features/<date>-<slug>/{brief.md,
  screenshots/NN_name.png, ui_smoke.py}` (screenshots **commit**).
- `ui_smoke.py` tự chứa: seed `shot_*` user + audit events + hội thoại (started_at lệch ngày để
  demo nhóm) → Playwright chụp 8 ảnh → dọn sạch. Chạy lại verify reproduce OK.
- **PR #1** merge rebase → main → CI xanh (test 2m10s + deploy 1m40s). Live `a43b3fa` healthz ok.

## Decisions Made
- **Mô hình nội bộ (a), không multi-tenant** (user chốt). Schema sạch để thêm tenant sau. (DECISIONS #14.)
- **404 không 403** cho DN ngoài phạm vi — không lộ tồn tại.
- **TEMP VIEW shadow** cho `query_sql` thay vì wrap LIMIT ngoài — wrap ngoài không chặn aggregate.
- **AI tool dùng CHUNG ranh giới với UI** — nếu không, officer lách qua chat.
- **Buộc đổi mật khẩu: GỠ theo yêu cầu user** ("hơi phiền"). Giữ plumbing + trang tự đổi. Seed admin
  bootstrap KHÔNG buộc đổi (tránh khoá cứng tests/ops) — chỉ cảnh báo startup.
- **1 feature folder cho PR** (không tách 3) — như data-hub B.0 (1 feature nhiều surface, ảnh đánh số).
- **Merge rebase** (giữ history tuyến tính + 4 commit focused) thay vì squash/merge-commit.

## What Didn't Work / Gotchas
- **Suýt vỡ ~10 test cũ:** nếu ép cả admin seed đổi mật khẩu, các route test login `admin/admin` rồi
  navigate sẽ bị 303 về `/change-password`. Fix = chỉ tài khoản admin-UI-tạo bị buộc, seed thì không.
  Sau đó user yêu cầu gỡ hẳn buộc-đổi.
- **zsh assoc array:** `declare -A` lỗi "bad substitution" → dùng cp thẳng.
- **Mật khẩu admin local không biết** → chụp ảnh phải tạo user throwaway `shot_*` qua ui_smoke.
- **`user.py` annotation:** `Mapped[list["Company"]]` quote → ruff UP037; import Company runtime
  (không circular vì company.py không import user) rồi bỏ quote.
- **Files đan xen P1/P2** (companies.py, ai.py, user.py vừa P1 vừa P2) → không tách được 2 commit chạy
  được riêng → gộp P1+P2 thành 1 commit.

## Open Items
- **Phân công DN cho officer trên prod** — chưa làm (admin → /admin/users).
- **Combo +20 điểm** — vẫn treo (user "quyết sau"), `scoring.py:179` flat +20 nhị phân.
- **Bật lại buộc đổi mật khẩu** nếu cần (plumbing còn).
- Nhánh local cũ `feat/ai-assistant`, `feat/document-ux-and-nl-check-authoring` chưa xoá.
- `ZZ_DEMO` (DN throwaway local) chưa quyết xoá/giữ.
- Rate-limit in-memory — nếu sau này multi-worker cần chuyển sang DB/redis.
