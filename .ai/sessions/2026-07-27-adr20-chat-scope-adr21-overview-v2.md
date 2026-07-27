# 2026-07-27 — ADR #20 chat gắn doanh nghiệp + ADR #21 tổng quan AI v2 (9 vé, merge + deploy)

Cài trọn 9 vé `ready-for-agent` còn mở: **CHAT-1..4** (#28–#31) và **TQ-1..5** (#32–#36).
Test-first, `/rev` mỗi nhóm, 3 PR theo đúng thứ tự build ADR chốt + 2 PR sửa lỗi.
Kết: `main` = prod = **`d7844b6`**, migration head **`c5d6e7f8a9b0`**, **850 test pass**
(mốc vào phiên 732), ruff sạch.

## What Was Done

### PR #37 — CHAT-1..4 (merge `6a38230`)
- Migration `e1f2a3b4c5d6`: `ai_conversations.company_id` nullable + index
  `(user, company_id, started_at)` + FK `ON DELETE SET NULL`. Backfill 3 nhánh
  (khớp slug/code · finding còn sống · để trống).
- `app/ai/conversation_scope.py`: nhận diện DN lúc TẠO theo chuỗi ưu tiên, gán muộn từ
  đúng một mention `@DN`.
- `/chat` nhóm theo DN: `GET /api/chat/conversation-groups`, `list_conversations` thêm
  `company_id`/`q`/`offset`/`limit`/`mine`, `PATCH /api/chat/conversations/{id}` đổi DN.
- `GET /api/chat/resume?company_code=` — quy tắc 24h ở server.
- Chủ đề cuộc vào system prompt (`build_conversation_topic`); mất quyền DN → 403 kèm lý do
  + `can_send`/`lock_reason` cho UI khoá ô nhập.
- Đếm tin nhắn + preview gom còn **2 câu SQL** thay vì 2 câu mỗi dòng (N+1 cũ).

### PR #41 — TQ-1 + TQ-2 (merge `ed69a0f`)
> Vốn là PR #38; GitHub **tự đóng** khi nhánh base bị xoá lúc merge #37. Phải tạo lại.

- Migration `f2a3b4c5d6e7`: bảng `ai_usage` append-only, seed từ overview đã có +
  tin nhắn chat tính tiền trong ngày. `check_daily_budget` + `/admin/ai` đọc sổ này.
- Migration `a3b4c5d6e7f8`: `check_overviews` thêm `status`/`job_id`/`error`.
- `JobKind.AI_OVERVIEW` + `AI_JOB_KINDS`; `claim_next_job`/`run_worker_iteration`/`JobWorker`
  nhận `kinds`/`exclude_kinds`. Worker kiểm tra loại trừ kind AI, worker thứ hai chỉ nhận kind AI.
- `start_overview_job` trả job cũ khi còn `queued`/`running`. `overview-poll.js` thay text tại chỗ.

### PR #39 — TQ-3 + TQ-4 + TQ-5 (merge `141b600`)
- Migration `b4c5d6e7f8a9` (`aggregate_json`) + `c5d6e7f8a9b0`
  (`sections_json`/`needs_review`/`unsupported_numbers`).
- `app/ai/overview_stats.py`: tập trung, phân vị + chiều lệch, tách theo sổ, so kỳ trước.
- `app/ai/overview_content.py`: prompt cấp số đã định dạng, parse JSON bốn mục, hậu kiểm
  token số, `finalize_sections` bỏ `phan_bo` khi <10 phát hiện và loại mã model bịa.
- `AI_OVERVIEW_BATCH` commit từng kiểm tra, hết ngân sách → `done` kèm lý do.

### PR #40 + #42 — hai fix (merge `d7844b6`)
Xem "What Didn't Work" mục 1 và 3.

### E2E
`.ai/features/2026-07-27-chat-scope-overview-v2/` — `brief.md` + `ui_smoke.py` + 8 ảnh.
Server throwaway cổng 8327 + DB riêng, tự dọn seed, **kill theo PID**.

## Decisions Made

- **Ba PR xếp chồng theo đúng thứ tự ADR #21 chốt** (chat → hạ tầng → nội dung), để `/rev`
  soi thay đổi **hàng đợi kiểm tra** — thứ duy nhất chạm prod run — tách khỏi thay đổi template.
- **Tín hiệu nhận diện DN trỏ tới DN không tồn tại thì đi tiếp; trỏ tới DN có tồn tại nhưng
  ngoài quyền thì DỪNG hẳn.** Rơi tiếp xuống nhánh phát hiện sẽ dán cho cuộc một DN khác hẳn
  DN mà ngữ cảnh vừa nêu. ADR chỉ nói "dừng ở khớp đầu" — đây là diễn giải, đã ghi thành test.
- **`/api/chat/resume` đo theo tin nhắn CUỐI, không phải lúc mở cuộc.** ADR viết "cuộc gần
  nhất"; lý do ADR nêu (resume nạp lại 20 message) nghiêng về `started_at`, nhưng "gần nhất"
  theo nghĩa cán bộ vừa dùng thì tự nhiên hơn. Sắp theo hoạt động cuối **trong SQL** để không
  có cap ngầm.
- **Khoá phân vị khai TƯỜNG MINH theo mã kiểm tra** (`PERCENTILE_KEYS`), không quét mọi khoá
  số trong `details`: phần lớn khoá là lượng thô theo đơn vị từng mã, thống kê thứ tự trên đó
  trộn đơn vị và không đọc được.
- **Hậu kiểm số chấp nhận số nằm trong NHÃN của bảng** ("5 mã lớn nhất", "phủ 80%"), không chỉ
  phần giá trị. Model được bảo copy từ bảng, mà bảng chính là khối nó nhìn thấy — chỉ nhận
  phần giá trị sẽ gắn cờ nhầm những câu đúng. (Phát hiện khi test `test_rounded_number...`
  báo `['5', '62']` thay vì `['62']`.)
- **Badge cờ số không khớp đổi chữ** (chưa lên prod): "Cần đối chiếu số liệu" lặp đúng câu
  miễn trừ trách nhiệm ngay dưới nó nên không nói thêm gì → "Có số không khớp bảng".
- **Owner chốt gộp bản sửa badge vào đợt rà soát ngôn ngữ**, không deploy riêng (mỗi lần
  deploy = một lần `docker restart` + thêm image layer, đĩa đang 96%).
- **Note rà soát vẫn đẩy lên `main` ngay** dù code chờ: phiên sau đọc `BACKLOG.md` của `main`
  trước tiên, note nằm trên nhánh chưa merge coi như không tồn tại.

## What Didn't Work

1. **Test xanh giả vì DB dev — làm `main` đỏ một nhịp.**
   `test_send_refused_with_reason` khẳng định 403 nhưng CI trả 503. `app/ai/config.py:21` bind
   `SessionLocal` **lúc import**, nên `get_setting` không kèm `db` đọc **DB MẶC ĐỊNH**, không
   phải DB in-memory của test. Máy dev có `audit_hq.sqlite` đã bật AI → xanh; CI DB rỗng →
   `enabled=False` → 503. **Xanh vì lý do nó không hề khẳng định.**
   Sửa: monkeypatch `app.routes.ai.get_setting` (đúng chỗ handler bind), không ghi dòng cấu hình.
   Từ đó **mỗi lần merge đều chạy lại suite với `DATABASE_URL` trỏ file rỗng**. Đã lưu memory
   `test-false-green-ambient-db`.
   *Deploy KHÔNG chạy vì CI dừng ở bước test — prod không bị đụng.*

2. **`/rev` bắt 2 lỗi thực trong code tôi vừa viết.**
   - Hộp thoại đổi DN gỡ handler `close` rồi chỉ gắn lại một lần → sau lượt lưu hỏng (officer
     chọn DN ngoài quyền → 404) hộp thoại mở lại nhưng bấm Lưu **không gọi API**, thay đổi mất
     im lặng. Sửa: gắn lại handler mỗi lần mở (`{ once: true }` + hàm `arm()`).
   - `test_overview_route_generates_and_redirects` stub `generate_check_overview` — hàm mà
     route KHÔNG còn gọi sau TQ-2 → test xanh mà không kiểm gì.

3. **Ảnh E2E bắt lỗi CSS đã live trên prod.**
   `.ai-scope-bar` / `.ai-scope-mismatch` khai `display:flex`, cùng specificity với `[hidden]`
   và khai báo SAU nên thắng → hộp vàng **RỖNG hiện trên mọi trang**. Đúng loại lỗi codebase
   đã ghi chú sẵn cho `.ai-history-panel`. Sửa ở `d7844b6`.

4. **Thao tác git hỏng hai lần, mất thời gian:**
   - `git add -A` nuốt `uv.lock` (dự án cố ý để untracked) vào commit CHAT-2 → phải dựng lại
     4 commit bằng `git checkout <c> -- .` từng cái.
   - `git cherry-pick -q` — **`-q` không phải cờ hợp lệ của cherry-pick** → chuỗi lệnh `set -e`
     chạy nửa vời, nhánh về trạng thái dở. Phải khôi phục từ nhánh backup.

5. **Merge PR cha kèm `--delete-branch` làm GitHub tự ĐÓNG PR con** trỏ vào nhánh đó — không
   retarget, và **không reopen được** ("Cannot change the base branch of a closed pull
   request"). PR #38 mất theo cách này, phải tạo lại thành #41.

## Open Items

- **Rà soát toàn bộ ngôn ngữ tiếng Việt trên UI** — work-list 6 mục ở `.ai/BACKLOG.md` mục đầu
  file. Nhánh **`fix/badge-wording` (`ebff51c`) CHƯA MERGE**, chỉ 1 dòng, chờ gộp vào đợt này.
  Owner chốt sang **session mới**, đi đường `/grill-with-docs` → `/implement` (3/6 mục là quyết
  định chứ không phải việc tay chân). Xong phải **chụp lại ảnh 07**.
- **Giao diện mới chưa hiện gì trên prod:** `ai_conversations` = 0 dòng (toàn bộ UI ADR #20
  rỗng); `check_overviews` chỉ 2 dòng bản WS3 cũ, `aggregate_json`/`sections_json` NULL nên
  bảng số liệu + nhận định bốn mục **không hiện**. Muốn demo phải bấm "Tạo tổng quan còn thiếu"
  = **36 lời gọi LLM thật**.
- **Đĩa server 96%, còn 11G** — `docker system df`: 68 GB image reclaimable; `db-data` 1,5G /
  6 backup. Chưa dọn vì xoá không quay lại được, cần owner chốt.
- Punch-list 7 (lệch GLOSSARY/ADR #19) và 8 (`X.*` luôn `book=NULL`) **vẫn mở từ phiên trước**.
- ADR "nhãn sổ sống ở đâu cho bền" vẫn chưa viết.
- Chưa đụng: `build_overview_aggregate` (bản WS3) giờ không còn ai gọi trong đường sinh — để
  lại vì test cũ dùng; nên xoá hoặc gộp khi có dịp.
