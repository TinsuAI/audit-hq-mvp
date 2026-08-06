# Độ bền hàng đợi job — audit 5 kịch bản lỗi

Ngày: 2026-07-30. Phạm vi: `app/jobs/`, `app/main.py` (worker startup), `app/models/job.py`,
các route enqueue (`app/routes/companies.py`, `app/routes/ai.py`), `app/ai/overview.py`,
`app/pipeline/run_checks.py`, `app/database.py`, `app/ai/retention.py`. Chỉ đọc, không sửa code.

## 1. Container restart giữa lúc job đang `running`

Có reconciliation, nhưng **chỉ chạy một lần lúc khởi động** và chỉ bắt job đã kẹt
**quá 1 giờ**:

- `app/jobs/worker.py:64-81` — `recover_zombie_jobs()`, `ZOMBIE_THRESHOLD_SECONDS = 3600`
  (`worker.py:26`). Điều kiện mark FAILED: `status == RUNNING AND started_at < now - 3600s`.
- `app/main.py:97-103` — gọi đúng MỘT LẦN trong `lifespan()`, trước khi 2 worker thread start.
  Không có vòng lặp định kỳ nào gọi lại hàm này sau đó (khác với `run_retention_loop`,
  `app/main.py:79`, chạy mỗi 24h — `recover_zombie_jobs` không có cơ chế tương tự).

Hệ quả cụ thể: container crash lúc job mới chạy được vài phút, rồi restart ngay (kịch bản
deploy/OOM phổ biến nhất) — `started_at` của job đó còn rất mới so với cutoff `now - 1h`
tại thời điểm restart, nên **không** được reconcile ở lần khởi động này. Job ở lại `running`
cho đến khi (a) đủ 1 giờ trôi qua VÀ (b) có thêm một lần restart nữa sau đó mới quét trúng.
Nếu không có restart tiếp theo, job đó ở `running` **vĩnh viễn**.

Cán bộ thấy gì: `app/templates/job_detail.html:5-7` chèn `<meta http-equiv="refresh" content="2">`
khi `job.status in (queued, running)` (điều kiện ở `app/routes/jobs.py:138`). Trang tự tải lại
mỗi 2 giây, mãi mãi, không báo lỗi, không có nút huỷ hay retry thủ công. Với job `run_checks`
cụ thể: vì `run_checks_pipeline` xoá-rồi-ghi-lại Finding trong MỘT transaction, chỉ `commit()`
một lần ở cuối (`app/pipeline/run_checks.py:238`), quá trình crash giữa chừng khiến SQLite tự
rollback transaction chưa commit — dữ liệu Finding cũ (nếu có) vẫn nguyên, không hỏng. Nhưng cán
bộ nhìn "Đang chạy" mãi, tưởng kiểm tra đang chạy hoặc đã chạy, trong khi thực ra không có gì
thay đổi và không ai được báo để bấm chạy lại.

## 2. Hai worker, một file SQLite — nơi tranh chấp ghi

`app/database.py:14-25`: `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000` (5 giây) +
`foreign_keys=ON`, cấu hình ở event `connect` nên áp cho MỌI connection. `SessionLocal`
(`app/database.py:11`) dùng `autoflush=False`. Vậy: **có** busy timeout, không phải "chờ vô hạn
hoặc raise ngay".

Hai worker thread (`app/main.py:104-113`) chia nhau theo `kind`, không overlap tập `kind`
(`AI_JOB_KINDS` ở `app/models/job.py:29-31` tách biệt hẳn với phần còn lại) — tức KHÔNG BAO GIỜ
có 2 job cùng loại `run_checks`/`batch_run` chạy song song do 2 worker (chỉ có đúng 1 thread xử
lý các kind ngoài AI). Nơi tranh chấp thật sự:

- Cả hai worker cùng UPDATE bảng `jobs` để claim (`app/jobs/worker.py:53-58`) — đã atomic, có
  test race (`test_claim_is_race_safe` theo docstring `worker.py:6-7`), không phải điểm rủi ro.
- `run_checks_pipeline` (`app/pipeline/run_checks.py:42-238`) mở MỘT transaction ghi kéo dài
  suốt cả lượt chạy: câu `DELETE FROM findings` đầu tiên chạy sớm (dòng 79-104), rồi toàn bộ
  vòng lặp tính từng check + `s.flush()` (dòng 138) + tính combo + risk score, và chỉ
  `s.commit()` ở dòng 238. Với SQLite, transaction ghi giữ writer lock (dưới WAL vẫn là
  single-writer) từ câu DELETE đầu tiên cho tới commit cuối — nghĩa là suốt thời gian tính toán,
  không chỉ lúc ghi.
- Nếu trong lúc đó `ai_worker` xử lý `AI_OVERVIEW`/`AI_OVERVIEW_BATCH` cần commit (ví dụ
  `generate_check_overview` ghi `CheckOverview`/`AiUsage`, `app/ai/overview.py`), connection đó
  phải chờ writer lock rảnh, trong giới hạn `busy_timeout=5000ms`. Nếu lượt `run_checks` (DN
  nhiều năm dữ liệu, hoặc `batch_run` chạy tất cả năm — `app/jobs/handlers.py:57-99`) tính toán
  lâu hơn 5 giây, connection ghi của AI worker vượt timeout và SQLite raise
  `sqlite3.OperationalError: database is locked`.

Trả lời thẳng: có cấu hình busy timeout (5000ms), WAL bật — giảm rủi ro cho các lượt ghi ngắn,
nhưng KHÔNG loại trừ `database is locked` khi một lượt `run_checks`/`batch_run` chạy lâu hơn 5
giây trùng lúc AI worker cần commit.

## 3. Job raise trong handler — ai catch-per-item, ai fail cả job

- **Fail cả job** (không có catch riêng phần): `run_checks_handler`, `run_batch_handler`
  (`app/jobs/handlers.py:33-99`) — raise bất kỳ đâu trong vòng lặp năm/](check) làm hỏng toàn bộ
  job, không có gì được giữ lại từ các năm/](check) đã xong trước đó trong cùng job (vì chỉ có
  MỘT commit cuối, dòng `run_checks.py:238` — raise trước đó thì transaction rollback sạch).
  `run_overview_job` (đơn lẻ, `app/ai/overview.py:313-342`) cũng fail cả job — bắt exception chỉ
  để cập nhật `CheckOverview.status = FAILED` (dòng 339-341) rồi `raise` lại nguyên vẹn.
- **Catch-per-item, tiếp tục**: `run_overview_batch_job` (`app/ai/overview.py:382-445`) — vòng
  `for check_code in targets` bọc `try/except Exception` (dòng 422-431), một check lỗi thì
  `db.rollback()` + ghi vào `failed` list rồi tiếp tục check kế; hết ngân sách ngày thì `break`
  với `stopped_reason` (dòng 419-421) — job vẫn kết thúc `DONE` (qua generic catch-all ở
  `_execute_claimed_job`/`run_job`, không raise ra ngoài), đúng như đề bài mô tả.

**Bắt lỗi tầng ngoài (mọi handler đều đi qua đây khi raise thoát ra)**:
`app/jobs/worker.py:121-133` (`_execute_claimed_job`, dùng trong production) và
`app/jobs/__init__.py:83-95` (`run_job`, dùng trong test/gọi trực tiếp) — CÙNG một logic:
```
job.error = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
```
Không cắt độ dài, không lọc nội dung. `app/templates/job_detail.html:47-50` render thẳng
`{{ job.error }}` trong thẻ `<pre>` cho bất kỳ ai xem được job (chủ job, hoặc admin —
`app/routes/jobs.py:123-124`).

Đây là chỗ **có** rò rỉ, ở mức thông tin kỹ thuật: traceback đầy đủ gồm đường dẫn file nội bộ,
tên hàm, và với lỗi SQLAlchemy có thể gồm câu SQL kèm giá trị tham số (dữ liệu DN thật nếu lỗi
xảy ra khi ghi Finding). Với `AI_OVERVIEW`, `run_overview_job` re-raise nguyên exception gốc
(`app/ai/overview.py:342`) — nếu đó là `APIStatusError`/`APIError` từ provider LLM (import ở
`app/routes/ai.py:23`), `str(e)` của các exception này thường chứa nguyên văn body lỗi provider
trả về. So sánh: `CheckOverview.error` đã CẮT còn 500 ký tự
(`app/ai/overview.py:340`: `str(e)[:500]`) — nhưng `Job.error` thì KHÔNG, nên cùng một lỗi, bản
hiển thị ở `/jobs/{id}` đầy đủ hơn nhiều so với bản hiển thị cạnh tổng quan AI. Không phải lỗi
vượt ranh giới phân quyền (chỉ chủ job + admin xem được), nhưng verbose quá mức cần thiết cho
một trang UI nghiệp vụ.

## 4. Double submission

**AI overview đơn (`AI_OVERVIEW`)**: có chống double-submit, đã xác minh.
`app/ai/overview.py:254-310` (`start_overview_job`) — nếu `CheckOverview` hiện có
`status == RUNNING` và `job_id` trỏ tới job còn `queued`/`running` (dòng 274-279), trả về
`(job.id, existing=True)`, KHÔNG tạo job mới. Route gọi hàm này:
`app/routes/companies.py:1514-1518` (`generate_overview`).

**RUN_CHECKS / BATCH_RUN**: KHÔNG có chống double-submit. Xác minh ở cả hai nơi enqueue:
- `app/routes/companies.py:1405-1459` (`rerun_checks`, nút "Chạy lại kiểm tra") — gọi
  `enqueue_job(...)` thẳng, không SELECT job đang chờ/đang chạy cho cùng
  `(company_id, period_year, kind)` trước.
- `app/routes/ai.py:904-948` (`chat_run_checks`, nút xác nhận từ đề xuất AI) — tương tự, không
  có kiểm tra tồn tại trước.
- `app/routes/companies.py:1279-1288` (re-ingest sau xác nhận đổi cột) — cũng enqueue thẳng,
  không kiểm tra.

Hai lần bấm liên tiếp (hoặc bấm ở hai route khác nhau cho cùng DN/năm) tạo **2 dòng `Job` riêng
biệt**, cả hai đều `kind` ngoài `AI_JOB_KINDS` nên cùng vào MỘT worker thread duy nhất
(`job_worker` ở `app/main.py:108-109`, không có worker thứ hai xử lý kind này) — `claim_next_job`
lấy theo `order_by(Job.created_at, Job.id)` (`worker.py:44-49`) nên 2 job chạy **tuần tự**, không
song song. Vì `run_checks_pipeline` xoá-rồi-dựng-lại có tính idempotent (cùng dữ liệu nguồn → cùng
kết quả), chạy tuần tự 2 lần chỉ lãng phí thời gian tính toán, không làm hỏng dữ liệu — job thứ
hai ghi đè job thứ nhất bằng kết quả giống hệt.

**Ngoại lệ thật sự nguy hiểm**: `app/routes/companies.py:1296-1300` — nhánh fallback khi
`ur is None` (user hiện tại không map được vào bảng `users`, theo comment dòng 1298 "Fallback
hiếm... chạy inline để không bỏ sót") gọi `run_checks_pipeline` **đồng bộ, ngay trong
request thread của FastAPI**, HOÀN TOÀN NGOÀI hàng đợi job. Nhánh này có thể chạy thật sự song
song với worker thread đang xử lý một `RUN_CHECKS`/`BATCH_RUN` đã enqueue trước đó cho CÙNG
`(company_id, period_year)` — đây mới là kịch bản 2 lượt ghi cùng target thật sự đồng thời mà đề
bài nêu. Vì mỗi lượt là một transaction SQLite riêng, SQLite tự serialize hai transaction (không
xen kẽ dòng), nhưng **lượt commit sau cùng thắng, ghi đè hoàn toàn kết quả của lượt commit trước**
— và HTTP response của request đã chạy fallback trả về "Đã xác nhận... và nạp dữ liệu" thành công
(`companies.py:1302-1304`) dù kết quả của chính request đó có thể đã bị lượt kia ghi đè ngay sau,
không có cảnh báo nào cho cán bộ biết việc này đã xảy ra. Nếu lượt kia chạy lâu hơn 5 giây, một
trong hai transaction có thể raise `database is locked` (mục 2).

## 5. Tăng trưởng không giới hạn

Không có retention nào cho bảng `jobs`. Đã đọc toàn bộ `app/ai/retention.py` — vòng lặp
`run_retention_loop` (`app/main.py:79`) chỉ xoá `AiConversation`/`AiMessage` cũ theo
`history_retention_days`/`audit_retention_days` (`retention.py:33-59`), không đụng tới bảng
`jobs`. `Job.result` (JSON) và `Job.error` (Text, không giới hạn độ dài — mục 3) tích luỹ vĩnh
viễn, không có job xoá/archive nào trong toàn bộ `app/`.

Số dòng hiện tại (DB local, đọc chỉ-đọc `sqlite3.connect("file:.../audit_hq.sqlite?mode=ro", uri=True)`):

```
total jobs: 3
by status: [('done', 3)]
by kind: [('batch_run', 1), ('run_checks', 2)]
date range: 2026-07-23 11:46:38 → 2026-07-24 18:59:25
error bytes: 0 · result bytes: 1042 · payload bytes: 115
```

Quy mô hiện tại quá nhỏ để thấy vấn đề, nhưng đây là DB dev cá nhân — không đại diện quy mô
thí điểm 6 DN chạy nhiều năm × nhiều lần "Chạy lại kiểm tra" × AI overview theo từng check. Cấu
trúc bảng (`app/models/job.py:41-69`) không có cột nào hỗ trợ archive/soft-delete, chỉ có 2 index
theo `status`/`created_by` — không có gì ngăn bảng phình theo thời gian thí điểm.

## Xếp hạng theo mức cán bộ cảm nhận + fix

**1. Job kẹt `running` vĩnh viễn sau crash, im lặng không báo lỗi (mục 1)** — cao nhất vì âm
thầm nhất: cán bộ thấy "Đang chạy" mãi, không có tín hiệu để biết cần bấm chạy lại, trong khi dữ
liệu thực chất không đổi.
   - Fix: chạy `recover_zombie_jobs()` (`app/jobs/worker.py:64-81`) định kỳ, không chỉ lúc
     startup (`app/main.py:97-103`) — thêm một vòng lặp giống `run_retention_loop`
     (`app/ai/retention.py:19-27`) gọi lại hàm này mỗi vài phút, và cân nhắc hạ
     `ZOMBIE_THRESHOLD_SECONDS` (`worker.py:26`, hiện 3600s) xuống mức khớp thời lượng chạy tối
     đa thực tế của `batch_run` (ví dụ 10-15 phút cộng biên an toàn) thay vì 1 giờ.
   - Migration: KHÔNG cần — dùng lại đúng cột `started_at`/`status` đã có.

**2. `run_checks`/`batch_run` enqueue không chống double-submit, có một nhánh chạy ngoài hàng đợi
(mục 4)** — nhánh `companies.py:1298-1300` là điểm duy nhất có thể ghi đè âm thầm kết quả của
một lượt khác mà không báo cho cán bộ, kể cả khi HTTP response báo "thành công".
   - Fix (double-submit qua route thường): thêm kiểm tra job `queued`/`running` cùng
     `(kind, company_id, period_year)` trước khi `enqueue_job`, theo đúng mẫu đã có ở
     `start_overview_job` (`app/ai/overview.py:274-279`) — áp cho `rerun_checks`
     (`app/routes/companies.py:1433-1459`) và `chat_run_checks` (`app/routes/ai.py:934-945`).
   - Fix (nhánh inline `companies.py:1296-1300`): bỏ nhánh chạy đồng bộ, thay bằng enqueue qua
     hàng đợi với `created_by` hệ thống/mặc định khi không map được user — giữ tính chất "không
     bỏ sót" mà không phá vỡ tuần tự hoá của worker.
   - Migration: KHÔNG cần — chỉ thêm một câu SELECT trước enqueue, dùng index sẵn có
     (`ix_jobs_status_created_at`) hoặc thêm index mới `(company_id, period_year, kind, status)`
     nếu cần tối ưu — index này CẦN migration nhưng không bắt buộc để fix đúng, chỉ để nhanh khi
     bảng lớn.

**3. Tranh chấp SQLite giữa lượt `run_checks` dài và AI worker (mục 2)** — có thể xảy ra, hệ quả
là job AI fail với lỗi khó hiểu ("database is locked") thay vì bị chặn hoàn toàn.
   - Fix: nâng `busy_timeout` (`app/database.py:23`, hiện 5000ms) lên mức an toàn hơn (ví dụ
     15000-20000ms) cho tới khi có số liệu thời lượng `run_checks` thực tế; đồng thời bắt riêng
     `sqlite3.OperationalError`/`OperationalError: database is locked` ở
     `_execute_claimed_job` (`app/jobs/worker.py:121-133`) để set `job.error` với thông điệp rõ
     ràng ("Hệ thống đang bận ghi dữ liệu, thử lại sau") thay vì traceback thô, và có thể tự động
     retry job đó một lần.
   - Migration: KHÔNG cần — chỉ đổi hằng số + thêm nhánh except.

**4. `Job.error` không cắt độ dài, không lọc nội dung (mục 3)** — rủi ro thấp hơn vì chỉ chủ job
+ admin xem được, nhưng verbose không cần thiết và có thể chứa dữ liệu DN thật trong SQL lỗi.
   - Fix: áp cùng quy tắc đã dùng cho `CheckOverview.error` — cắt còn vài trăm ký tự khi ghi vào
     `job.error` (`app/jobs/worker.py:130`, `app/jobs/__init__.py:92`), bỏ
     `traceback.format_exc()` khỏi phần lưu DB/hiển thị UI (traceback đầy đủ đã có sẵn trong log
     server qua `log.exception(...)` ngay dòng trước, không mất thông tin để debug).
   - Migration: KHÔNG cần — cột `Text` đã đủ rộng, chỉ đổi logic ghi.

**5. Không có retention cho bảng `jobs` (mục 5)** — thấp nhất vì hiện tại (3 dòng) chưa gây hại,
nhưng là khoảng trống cấu trúc sẽ lộ ra khi thí điểm chạy đủ lâu.
   - Fix: thêm hàm dọn `jobs` cũ (`DONE`/`FAILED` quá N ngày) theo đúng mẫu
     `_cleanup_once` (`app/ai/retention.py:30-59`), gọi từ cùng `run_retention_loop`
     (`app/main.py:79`); thêm 1 key cấu hình mới (ví dụ `job_retention_days`) vào bảng
     `app_settings` (`app/models/app_setting.py:17-29`, key-value tự do).
   - Migration: KHÔNG cần cho phần xoá job (dùng cột `status`/`created_at` sẵn có); KHÔNG cần
     cho key cấu hình mới (bảng `app_settings` là key-value, không cố định schema theo cột).

## File liên quan

- `app/jobs/worker.py` — claim, zombie recovery, vòng lặp worker
- `app/jobs/__init__.py` — `enqueue_job`, `run_job` (đường test/gọi trực tiếp)
- `app/jobs/handlers.py` — `run_checks_handler`, `run_batch_handler`
- `app/main.py` — đăng ký handler, khởi động 2 worker, gọi zombie recovery 1 lần
- `app/models/job.py` — schema `Job`, `JobKind`, `AI_JOB_KINDS`
- `app/models/app_setting.py` — bảng key-value cấu hình runtime (chỗ thêm retention setting)
- `app/database.py` — pragma SQLite (WAL, busy_timeout, autoflush)
- `app/routes/jobs.py`, `app/templates/job_detail.html` — hiển thị job cho cán bộ
- `app/routes/companies.py` — `rerun_checks`, `generate_overview`, nhánh inline fallback
- `app/routes/ai.py` — `chat_run_checks`
- `app/ai/overview.py` — `start_overview_job` (mẫu chống double-submit), `run_overview_job`,
  `run_overview_batch_job`
- `app/pipeline/run_checks.py` — transaction xoá-rồi-dựng-lại Finding
- `app/ai/retention.py` — mẫu cleanup định kỳ (chưa bao phủ `jobs`)
