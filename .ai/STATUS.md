# STATUS — Audit-HQ MVP

> **Trạng thái (2026-08-05 — ISSUE #56: SỔ YÊU CẦU → 7 TICKET #57–#63. PR #55 ĐÃ MERGE.
> Nhánh `feat/data-completeness-gate`):**
> **Bảy sub-issue của #56 đã mở**, gắn nhãn `ready-for-agent`, cạnh chặn khai bằng issue dependency
> thật của GitHub — T1 #57 (`companies.first_bcqt_year`) · T2 #58 (`not_evaluable` thành trạng thái
> chạy thật) · T3 #59 (C4.3 bỏ mã không có dòng M15) · T4 #60 (định mức hiệu lực, chặn bởi #59) ·
> T5 #61 (bảng thừa/thiếu ĐM, chặn bởi #60 **và bởi một quyết định của owner**, xem dưới) ·
> T6 #62 (cổng nhị phân, chặn bởi #57+#58+#60) · T7 #63 (mô hình bằng chứng WS1 cho BCCT, rời).
> **Grab được ngay: #57, #58, #59, #63.** Mỗi ticket mang mốc nghiệm thu bằng số đo, không phải mô
> tả suông. Chi tiết ở `.ai/features/2026-08-05-issue-56-data-completeness/tickets.md`.
>
> **#61 CHẶN BỞI OWNER:** check mới là chiều **M15a → M16** (có sản xuất mà thiếu định mức) — catalog
> 49 không có mã cho chiều này (`C4.2` là chiều ngược, `C4.1` là M16 → M15). Theo `CLAUDE.md` phải
> thêm mã vào `../audit-hq/de-an-audit-hq.md` TRƯỚC. Không tự đặt mã.
>
> **T7 #63 — lỗi mức 0 đang sống:** adapter BCCT ánh xạ cột theo vị trí cố định; file bố cục khác
> đọc sai mọi trường mà **không báo lỗi**. Đo trên **38 file BCCT trong `data/`: 35 khớp, 3 lệch** —
> HIEP_QUANG 2021 NK/XK (50 cột, 16 trường) và HONG_AN 2025 XK `__dup1` (55 cột, 11 trường). Ví dụ
> HIEP_QUANG: `quantity` lấy nhầm sang cột *Trị giá NT*, `company_name` sang *Ngày hợp đồng*.
> **10 check đọc `declaration_lines`** (C1.1–C1.7, C3.1–C3.3, C5.1) cộng `denominators.py` và
> `company_type.py` → mức 3 (13.368 phát hiện) dựng trên bảng đó. DB hiện **sạch** (3 pilot +
> ZONSEN đều đúng bố cục, `quantity IS NULL` = 0/2/0/0); HIEP_QUANG và HONG_AN **chưa nạp**.
> **Thứ tự bắt buộc: sửa adapter TRƯỚC, nạp hai DN đó SAU** — dòng đã nạp không tự đổi khi luật dò
> cột đổi. Code một phần ở nhánh `fix/bcct-label-columns` @ `06a9db5` (chưa test, chưa push).
>
> Phiên trước không sửa dòng code nào. **Toàn bộ sản phẩm ở
> `.ai/features/2026-08-05-issue-56-data-completeness/`** — đọc theo thứ tự: `yeu-cau.md` (làm gì) →
> `grill-state.md` (chốt gì + bằng chứng đo được) → `brief.md` (ghi chú kỹ thuật, chỉ đọc khi code)
> → `officer-requirements.md` (nguyên văn yêu cầu anh Dũng).
> **Gộp 3 tài liệu nguồn thành 29 yêu cầu** (bản ghi âm anh Dũng · notes chị Duyên 05/08 · đề xuất
> chị Duyên 16/06) — trùng lặp nhiều: tờ khai huỷ/sửa nêu 3 lần, tiêu hao lý thuyết 3 lần, ĐM kế
> thừa 4 lần. Xếp theo **bản đồ mức** owner đề xuất (mức 0 tiếp nhận file → 1 biểu tự đứng vững →
> 2 đủ nguyên liệu để tính → 3 đối chiếu chéo nguồn → 4 suy diễn từ ĐM; nhánh liên kỳ riêng).
> **BA QUYẾT ĐỊNH:** (1) kỳ sớm nhất mỗi DN mặc định `not_evaluable` cho check độ phủ ĐM, trừ khi
> cán bộ xác nhận là **năm đầu nộp BCQT** → cần trường mới trên `companies`; (2) **định mức chuyển
> tiếp ĐƯỢC đưa vào phép nhân C4.3** (bản khai gần nhất ≤ kỳ), bắt buộc ship kèm việc (b) của
> `fix/c43-multiplier-p07` nếu không sinh **151 phát hiện Nghiêm trọng dán nhầm nhãn** C4.1;
> (3) **cổng NHỊ PHÂN, không theo sản lượng** — có mã TP sản xuất mà chưa từng khai ĐM ở bất kỳ kỳ
> nào thì nhóm 4 `not_evaluable`. Hệ quả đo được: **C4.3 còn 1.772/3.296 = 54%**, chỉ DN 8/2025 qua
> cả hai cổng. Thêm 4 mục vào `GLOSSARY.md`.
> **Tầng C KHÔNG CÒN CHỜ HỌP** — `not_evaluable` để dành từ ADR #18 `:467-471` chính là việc này,
> issue #56 là buổi họp nó chờ.
> **Mục "chặn bởi đề án" ở dưới ĐÃ STALE:** `../audit-hq/de-an-audit-hq.md` đã sửa C4.3 (số nhân =
> sản lượng nhập kho), nên code hiện **chọi catalog**, không còn chờ owner chốt quy trình 3 repo.
> **Còn treo:** (H1) ngữ nghĩa qua-mức cho các mức khác — nhiễm theo mã (khuyến nghị) hay chặn cả
> mức; (H3) mã catalog cho check độ phủ M15a→M16 — nay là cạnh chặn của #61.
> **H2 ĐÃ GỠ** (tiếp nhận file): không phải chọn giữa từ-chối và nhận-rồi-gắn-cờ. Sổ phân định sẵn
> hai điều kiện khác nhau — dòng **0.1** *từ chối* khi không nhận ra là biểu nào (đã có một phần:
> `select_sheet` ném `SheetNotFound`); dòng **0.2** *cảnh báo + gắn nhãn bằng chứng* khi nhận ra
> được nhưng phải đoán cột theo vị trí. Kèm theo: dòng 0.2 trước đánh ✅ WS1 là **SAI** — WS1 chỉ
> phủ M15/M15a/M16, `evidence.py` không có dòng nào cho BCCT. Đã hạ xuống 🔨 → T7 #63.
> **Phạm vi #56 đã cắt:** 3/39 dòng trong phạm vi (2.1, 2.2, 0.2), 36 ngoài — chia theo cái đang
> chặn: 6 đã có · 17 ship được xếp sau · 3 chặn bởi dữ liệu nguồn · 5 cần file mới · 5 ngoài phạm vi
> kiểm tra. Xem mục "Phạm vi issue #56" trong `yeu-cau.md`.
> **Next: `/implement` từng ticket ở SESSION MỚI, clear context giữa mỗi cái.**
> Session log: `.ai/sessions/2026-08-05-issue-56-so-yeu-cau-cong-du-lieu.md` (phân tích) và
> `.ai/sessions/2026-08-05-ticket-hoa-issue-56.md` (ticket hoá + T7).

> **Trạng thái (2026-08-02 — BA PHẢN HỒI SAU DEMO ĐÃ CÀI XONG. NHÁNH
> `feat/finding-columns-raw-data` — ĐÃ MERGE QUA PR #55 ngày 05/08, `main` nay ở
> `d528b2f`):** 956 test xanh, ruff sạch. Ba việc:
> (1) **Link vào dữ liệu gốc đã lọc sẵn** — từ mỗi dòng phát hiện, mỗi khối chứng cứ,
> mỗi khối trên trang chi tiết mã. Bảng đích lấy theo `evidence_refs` **chứ không đoán
> theo `subject_type`** (C1.2 subject là mã NVL nhưng bằng chứng ở tờ khai). Màn dữ
> liệu gốc thêm lọc số tờ khai / loại hình (nhận cả tập) / khoảng ngày / sổ, giữ bộ
> lọc khi đổi tab, thêm cột `Nguồn file` in TÊN FILE (không in đường dẫn máy chủ).
> (2) **Bảng phát hiện bỏ hẳn cột "Mô tả"**, số tách ra cột theo từng check qua
> `app/checks/detail_labels.py`. Check động (admin viết SQL) không khai bộ cột nên
> vẫn giữ cột mô tả. (3) **`app/formatting.py`** — một chỗ quyết định dấu phân cách;
> setting `number_format` (`vi` mặc định `1.234,56` · `en` `1,234.56`) ở
> `/admin/hien-thi`; `%` luôn có dấu, tiền luôn có mã tiền tệ.
> **`finding.title` KHÔNG đổi cách sinh** — tiêu đề đã lưu trong DB, đổi thì phải chạy
> lại toàn bộ kiểm tra, mà `title` còn là đầu vào của tìm kiếm, công cụ AI và
> `ai/overview.py` (gom theo title). Việc bỏ cột mô tả nằm ở tầng render.
> **BA LỖI THẬT bắt được:** (a) **tiêu đề cột C1.1 nói sai về con số nằm dưới nó** —
> `m15_column` mang tên cột DB, và với DN thuê gia công ở nước ngoài cột đối chiếu là
> `xuất kho để sản xuất` chứ không phải `nhập trong kỳ` → đổi tiêu đề thành "Số M15
> đối chiếu" + thêm cột nêu tên cột thật; (b) **`recompute_company_year` nuốt mất
> trạng thái cán bộ vừa ghi** (`tier_for` → `get_tiers()` tự mở `SessionLocal()`,
> session lồng `close()` phát ROLLBACK; dính khi hai session dùng chung một
> connection — **sản phẩm chạy pool thường nên không dính**, nhưng test đỏ sẵn trên
> `main` từ trước, nay đã sửa + có test hồi quy); (c) **bảng C2.1 tràn ngang, nút thao
> tác bị đẩy khỏi màn hình** khi trải trọn phương trình cân đối thành 10 cột → rút còn
> 4 cột, đầu vào vẫn đủ ở trang chi tiết.
> **E2E:** `.ai/features/2026-08-02-finding-columns-raw-data/` (brief + `ui_smoke.py`
> + 9 ảnh), server throwaway 8332, tự dọn, kill theo PID. Ảnh là seed minh hoạ →
> chứng minh RENDER, KHÔNG chứng minh adapter đọc đúng cột từ Excel thật.
> **Next:** (1) ~~mở PR + review~~ đã merge 05/08; **deploy vẫn chưa chạy** — không có
> migration; (2) nhánh này **sẽ conflict với `feat/adr23-ktstq-period-scope`** ở
> `companies.py` + 2 template, owner đã biết khi chọn tách từ `main`; (3) bản xuất Excel
> kiến nghị chưa dùng lớp `fmt_*` và chưa tách số ra cột — cùng vấn đề, khác mặt trận;
> (4) `app/adapters/bcct.py` nay ở nhánh `fix/bcct-label-columns` @ `06a9db5` → T7 #63.
> Session log: `.ai/sessions/2026-08-02-demo-feedback-cot-so-nhan-du-lieu-goc.md`.

> **Trạng thái (2026-07-27 — SINH TỔNG QUAN AI CHO CẢ 3 PHÁP NHÂN TRÊN PROD — CHỈ THAO TÁC DỮ LIỆU, build_sha vẫn `d7844b6`):**
> Owner chốt chạy. Xếp 4 job `AI_OVERVIEW_BATCH` (#2–#5) qua đúng đường của nút "Tạo tổng quan còn thiếu"
> (enqueue trong container, worker AI của app tự xử — KHÔNG mở tiến trình ghi thứ hai vào SQLite).
> **35 tổng quan sinh mới, 0 lỗi:** 002/2025 = 5 · 004/2025 = 10 · 006/2024 = 10 · 006/2025 = 10.
> Rồi 2 job `AI_OVERVIEW` lẻ (#6, #7) vá hai ca hỏng bên dưới. **`check_overviews` 2 → 36 dòng, cả 36 đều đủ
> `aggregate_json` + `sections_json`.** **Finding KHÔNG đổi (14.989)** — thao tác này chỉ thêm dòng tổng quan.
> **Chi phí $0,0137 / 37 lời gọi** (`model_fast` = `deepseek/deepseek-v4-flash`, trần ngày $100, trước đó tiêu $0).
> Độ trễ 5–22 giây mỗi lời gọi, một ca 71 giây, một ca 817 giây (xem lỗi 1).
> **Backup TRƯỚC khi ghi:** `db-data/audit_hq.sqlite.bak-pre-ai-overview-20260727` (`Connection.backup()` WAL-safe,
> `integrity_check: ok`, chụp ở head `c5d6e7f8a9b0`). Rollback = `docker stop` → cp bak đè `audit_hq.sqlite`
> → `rm -f *-wal *-shm` → `docker start`. `/healthz` 200 `build_sha=d7844b6`, `/showcase` 200.
>
> **HAI LỖI THẬT bắt được nhờ đợt chạy này (CHƯA SỬA, chưa có ticket):**
> (1) **`request_timeout_s` KHÔNG được áp trên đường sinh tổng quan.** Cấu hình 120 giây, nhưng lời gọi
> `PILOT_004/2025 C3.3` chạy **817 giây** rồi trả `content` RỖNG trong khi `status` vẫn ghi `done`, tiêu
> 749+378 token. Dòng `done` mà rỗng thì giao diện render ô trống, không ai biết là hỏng. Sinh lại (job #6)
> ra 755 ký tự bình thường → không tái hiện được, nhưng trần thời gian chờ vẫn không có tác dụng.
> (2) **Luật cũ-mới bỏ sót dòng LỖI THỜI ĐỊNH DẠNG.** `checks_needing_overview` chỉ xét `ran_at` /
> `data_version`, nên dòng WS3 cũ của `PILOT_006/2025 C1.1` (sinh 2026-07-24 bằng `deepseek-v4-pro`, không có
> `aggregate_json`/`sections_json`) bị tính là "còn mới" vì 006 chưa chạy lại kiểm tra → batch bỏ qua, phải
> xếp hàng tay (job #7). Dòng WS3 cũ của 004 thì bị ghi đè đúng, vì 004 đã chạy lại check hôm nay nên hoá cũ.
> Còn dòng WS3 nào ở pháp nhân chưa re-run thì bẫy này lặp lại.
>
> **HAI TỔNG QUAN BỊ GẮN CỜ `needs_review`** — hậu kiểm số của ADR #21 chạy ĐÚNG, không phải lỗi hệ thống:
> `PILOT_006/2024 C1.7` nhắc số **77,7** và `PILOT_006/2024 C3.2` nhắc số **80,1**, cả hai KHÔNG có trong bảng
> số liệu → mô hình tự viết ra. **Cần người đọc lại hai nhận định đó trước khi đưa cho khách.**
>
> **LƯU Ý giao diện:** nhãn ô phân vị trên prod vẫn hiện khoá thô (`DIFF_PCT`, `M15_REPURPOSE`…) và trang
> công việc vẫn in JSON thô, vì bản vá nằm ở **PR #43 chưa merge** (nhánh `fix/badge-wording`, 9 commit,
> 873 test pass). Job #2–#5 cũng trả khoá kết quả tiếng Việt cũ (`da_tao`, `dung_vi`) vì prod chạy `d7844b6`.
> **Đĩa server 97%, còn 9,0G** — `db-data` giờ có **7 backup**.
> **Next:** (1) merge + deploy PR #43 thì giao diện tổng quan mới hiện đúng nhãn; (2) quyết định xử lý 2 lỗi
> trên (trần thời gian chờ · luật cũ-mới theo định dạng); (3) đọc lại 2 nhận định bị gắn cờ.

> **Trạng thái (2026-07-27 — CÀI TRỌN 9 VÉ ADR #20 + #21, MERGE + DEPLOY XONG — main=prod=`d7844b6`):**
> Cài hết **CHAT-1..4** (#28–#31, ADR #20 chat gắn doanh nghiệp) + **TQ-1..5** (#32–#36, ADR #21 tổng
> quan AI v2), test-first, `/rev` mỗi nhóm, 3 PR theo đúng thứ tự build ADR chốt + 2 PR sửa lỗi.
> **850 test pass** (mốc trước 732 → +118), ruff sạch, **5 migration** up→down→up sạch trên DB dựng từ đầu.
> **PR:** #37 CHAT-1..4 (`6a38230`) · #41 TQ-1+TQ-2 (`ed69a0f`, thay #38 bị GitHub tự đóng khi nhánh base
> bị xoá) · #39 TQ-3..5 (`141b600`) · #40 + #42 hai fix (`d7844b6`). Issue #28–#36 đã đóng.
> **Migration head prod giờ `c5d6e7f8a9b0`** (qua `e1f2a3b4c5d6` → `f2a3b4c5d6e7` → `a3b4c5d6e7f8` →
> `b4c5d6e7f8a9`). Prod verify: `/healthz` 200 `build_sha=d7844b6`, **14.989 finding / 3 pháp nhân KHÔNG đổi**,
> `/showcase` 200. **Backup TRƯỚC migration:** `db-data/audit_hq.sqlite.bak-pre-adr2021-20260727`
> (`Connection.backup()` WAL-safe, `integrity_check: ok`, chụp ở head `d0e1f2a3b4c5`).
> Rollback = `docker stop` → cp bak đè `audit_hq.sqlite` → `rm -f *-wal *-shm` → `docker start`.
>
> **ADR #20 (chat):** cột `ai_conversations.company_id` — nhãn **LƯU** trên dòng, thôi suy bằng regex
> `page_url_seed` lúc đọc (hỏng với seed `/findings/{id}` và với finding id không sống qua re-run).
> Nhận diện lúc TẠO dừng ở khớp đầu: DN chọn trên UI → DN của trang → DN của phát hiện → không gắn;
> tín hiệu trỏ tới DN **không tồn tại** thì đi tiếp, trỏ tới DN **có tồn tại nhưng ngoài quyền** thì DỪNG
> hẳn. Gán muộn chỉ từ ĐÚNG một mention `@DN`. `/chat` nhóm theo DN (30 cuộc/section + tải thêm, bỏ cap 30
> toàn cục), `PATCH /api/chat/conversations/{id}` đổi DN chặn ở API. **ĐỔI HÀNH VI:** danh sách của quản trị
> mặc định chỉ hiện cuộc của chính mình (`mine=1`); `mine=0` KHÔNG phải cửa hậu cho officer.
> `GET /api/chat/resume?company_code=` giữ quy tắc 24h ở SERVER, sắp theo **hoạt động cuối** trong SQL.
> DN của cuộc vào system prompt làm CHỦ ĐỀ, **không** thu hẹp quyền tool. Mất quyền DN → transcript đọc
> được, `/api/chat` + `/api/chat/stream` trả **403 kèm lý do**, ô nhập khoá.
>
> **ADR #21 (tổng quan):** bảng `ai_usage` append-only đứng sau trần ngày — trước đó trần cộng
> `ai_messages.cost_usd` nên **chi phí sinh tổng quan chưa bao giờ được đếm**, và không mở rộng query sang
> `check_overviews` được vì bảng đó upsert một dòng mỗi bộ ba. `JobKind.AI_OVERVIEW` + `AI_JOB_KINDS`:
> worker kiểm tra **loại trừ** kind AI, worker thứ hai **chỉ** nhận kind AI → **SỬA** quyết định "sinh đồng
> bộ trong request" của ADR #18 Rev WS3 mà vẫn giữ tính chất nó bảo vệ. Bấm lại khi job còn chờ → trả job
> cũ. `job.result` KHÔNG chứa tiền/token (`/jobs/{id}` in nguyên result cho mọi cán bộ).
> Bảng số liệu tính bằng Python lưu `aggregate_json`, **hiện ngay khi bấm**; nhận định LLM trả JSON bốn mục
> (`sections_json`), số phải copy nguyên văn, hậu kiểm so **token số** (không parse — vấp làm tròn 61,8→62%,
> năm, mã C1.6, mã hàng có chữ số) → lệch thì gắn cờ `needs_review` + badge. Slot model **`model_fast`**.
> `AI_OVERVIEW_BATCH` commit từng kiểm tra, hết ngân sách → job `done` kèm lý do, KHÔNG `failed`.
>
> **BỐN LỖI THẬT bắt được ngoài test viết cùng lúc:**
> (1) `/rev` — hộp thoại đổi DN mất handler sau lượt lưu hỏng, bấm Lưu lần hai đóng hộp thoại mà **không gọi
> API**, thay đổi mất im lặng (đường tới lỗi có thật: officer chọn DN ngoài quyền → 404).
> (2) `/rev` — `test_overview_route_generates_and_redirects` stub `generate_check_overview`, hàm mà route
> KHÔNG còn gọi sau TQ-2 → xanh mà không kiểm gì; viết lại để khẳng định job.
> (3) **CI** — `test_send_refused_with_reason` xanh trên máy dev (DB thật đã bật AI) nhưng 503 trên CI:
> `app/ai/config.py:21` bind `SessionLocal` **lúc import**, nên `get_setting` không kèm `db` đọc **DB MẶC
> ĐỊNH**, không phải DB của test. Đây là lý do main đỏ một nhịp — **deploy không chạy, prod không bị đụng**.
> Từ đó mỗi lần merge đều chạy lại suite với `DATABASE_URL` trỏ **file rỗng** để tái hiện điều kiện CI.
> (4) **Ảnh E2E** — `.ai-scope-bar`/`.ai-scope-mismatch` khai `display:flex`, cùng specificity với `[hidden]`
> và khai báo SAU nên thắng → hộp vàng **RỖNG hiện trên mọi trang**; đã live ở `141b600`, sửa ở `d7844b6`.
> Đúng loại lỗi codebase đã ghi chú sẵn cho `.ai-history-panel`.
>
> **E2E proof:** `.ai/features/2026-07-27-chat-scope-overview-v2/` (brief + `ui_smoke.py` + 8 ảnh) — server
> throwaway 8327 + DB riêng, tự dọn seed, **kill theo PID** (không `pkill uvicorn`). Ảnh 06 chứng minh đúng
> tính chất ADR #21: bảng số liệu hiện đủ trong khi nhận định còn "⏳ Đang viết…".
> **Giới hạn bộ ảnh:** dữ liệu seed minh hoạ, nhận định là JSON dựng sẵn (KHÔNG gọi LLM thật) → chứng minh
> render + hậu kiểm, không chứng minh chất lượng model.
> **Next:** (1) rà soát ngôn ngữ tiếng Việt trên UI — **ĐÃ LÀM**, nhánh `fix/badge-wording` giờ ở PR #43
> (9 commit, 873 test pass), CHƯA MERGE; work-list + kết quả ở `.ai/BACKLOG.md` mục đầu file; (2) punch-list 7
> (lệch GLOSSARY/ADR #19) và 8 (`X.*` luôn `book=NULL`) **vẫn mở**; (3) ADR "nhãn sổ sống ở đâu cho bền" vẫn
> chưa viết; (4) ~~chưa có DN nào trên prod có tổng quan AI mới~~ → **ĐÃ SINH ĐỦ 2026-07-27, xem khối trên
> cùng** (36 dòng `check_overviews`, cả 3 pháp nhân); (5) `ai_conversations` = 0 dòng nên toàn bộ giao diện
> ADR #20 **vẫn đang rỗng trên prod**; (6) **đĩa server 97%, còn 9,0G** — `docker system df` báo 68 GB
> image reclaimable, `db-data` giờ 7 backup; chưa dọn vì xoá không quay lại được.

> **Trạng thái (2026-07-27 — CHẠY LẠI CHECK 004 TRÊN PROD: 74 → 65, hết 3 CRITICAL sai — CHỈ THAO TÁC DỮ LIỆU, build_sha vẫn `03d5031`):**
> Owner chốt chạy lại. Chạy **scoped 17 check built-in** cho `PILOT_004`/2025 trong container prod
> (`python -m app.pipeline.run_checks --company PILOT_004 --year 2025 --check C1.1 … --check C6.1`).
> **74 → 65 finding: 9 dòng bị xoá, 0 dòng thêm mới.** 3 CRITICAL sai đã biến mất (+99900% ở
> `6067385-08B`/`6067385-09B`, −98% ở `NO 153-BLACK`); 6 dòng còn lại là bản trùng đơn vị thứ hai
> (C1.1 ×2, C1.3 ×2, C3.3 ×2). Theo check: **C1.1 33→28 · C1.3 15→13 · C3.3 4→2**, mười check kia không đổi.
> Severity: critical 61→52, warning 7, info 6 (không đổi). Tổng finding prod **14.998 → 14.989**.
> **002/006 KHÔNG đụng** (48 và 14.876 y nguyên, `COMBO_HS_GAMING` 28 dòng của 006 còn đủ); `X.*` vẫn 0 finding.
> **Điểm năm 004: 30 → 25**, tier giữ "Dữ liệu nhất quán". `companies.risk_score` vẫn **30** — `run_checks:188`
> đọc `CompanyYearScore` trên session `autoflush=False` (`database.py:12`) nên cache chỉ tăng, không giảm.
> **KHÔNG hiện sai trên UI**: `companies.py:190` cố ý đọc `max(company_year_scores)`, không đọc cache.
> **`check_runs`: company 9 từ 0 → 17 dòng** (`data_version=0`) → staleness WS3 của 004 tính từ mốc này.
> **Nhãn sổ nguyên vẹn:** nvl EPE 104/GC 37 · sp 43/2 · norms 664/216; finding `book` = NULL 35 / EPE 30
> (GC 0, như trước). Mọi finding còn `evidence_refs` (0 dòng rỗng). `/healthz` 200, `/showcase` 200.
> **Cách làm (an toàn 2 lớp):** backup WAL-safe bằng `sqlite3.Connection.backup()` →
> `db-data/audit_hq.sqlite.bak-pre-004-recheck-20260727-012604` (`integrity_check: ok`), rồi **dry-run trên
> BẢN COPY** với `DATABASE_URL` trỏ file copy, diff finding cũ/mới (74 vs 65, 9 removed / 0 added) → khớp mới
> chạy live. Bản copy đã xoá (cả `-wal`/`-shm`). **Rollback:** `docker stop audit-hq-mvp` → `cp` bản bak đè
> `audit_hq.sqlite` → `rm -f *-wal *-shm` → `docker start`.
> **CỐ Ý chạy scoped, không full:** `X.1` đang `published` trên prod (bản `cross_table_match` trùng nghiệp vụ
> với C1.1). Chạy full sẽ sinh finding `X.1` **chỉ cho 004** trong khi 002/006 không có → lệch giữa các DN trên
> demo. Truyền `only=` cũng bỏ luôn nhánh xoá orphan `X.*` nên không đụng gì khác.
> **Disk server 96% (12G trống).** Backup cũ tháng 6 (`bak-pre-c24`, `bak-pre-cleanup`, ~26MB mỗi cái) vẫn còn — chưa xoá.
> **Next:** (1) punch-list 7 (lệch GLOSSARY/ADR #19: mục "Pháp nhân" còn mô tả mô hình 2 row; C3.1 chưa được
> xếp lại; "104 mã" là số DÒNG, đúng là 98 mã) và 8 (`X.*` luôn `book=NULL`, `sql_runner.py:217-227`) vẫn mở;
> (2) ADR "nhãn sổ sống ở đâu cho bền" — gồm cả đường quay từ nhiều sổ về một sổ (hiện bị từ chối);
> (3) issue GitHub #4–#15 (WS1/WS2/WS3) đã ship nhưng vẫn OPEN — nên đóng.

> **Trạng thái (2026-07-27 — PUNCH-LIST 6: TEST HỒI QUY NGỮ NGHĨA SỔ + CHẶN GÁN SỔ NỬA VỜI — ĐÃ MERGE PR #27 + DEPLOY, main=prod=`03d5031`):**
> Chạy `/tdd` cho mục 6 punch-list của audit 004 (thiếu test hồi quy), rồi `/rev` → sửa 2 lỗi → PR #27 merge
> `03d5031`. **732 test pass** (mốc trước 721 → 730 sau /tdd → 732 sau /rev), ruff sạch (`app tests scripts`).
> **5 commit** (tách từ `main` tại `33c078f`): `61706af` test tầng check · `e219154` fix ingest + test ingest ·
> `0c0a181` text màn review · `c8ef81a` route trả 303 thay 500 · `5fc2711` sửa lại text màn review.
> **ĐÃ DEPLOY:** CI run `30214242113` XANH, prod `/healthz` 200 `build_sha=03d5031` (build_time
> 2026-07-26T18:16:40Z theo đồng hồ server). **KHÔNG có migration** → head prod vẫn `d0e1f2a3b4c5`.
> **9 test mới, 2 test cũ được siết.** Mọi test kiểm bằng MUTATION (sửa hỏng đúng dòng nó bảo vệ, xác nhận
> đỏ, hoàn nguyên) — bảng mutant đầy đủ ở session log. Nội dung: C1.2 trừ tập mã M15 của MỌI sổ (bản vá union
> 99→4); C1.1/C1.2/C1.4/C3.1/C3.2 để `book` trống vì vế đối chiếu là luồng tờ khai toàn pháp nhân; C1.3 chấp
> nhận tờ khai KHÔNG nhãn cho dòng M15 CÓ nhãn; ingest dừng khi file đã đăng ký không đọc được sheet; nhãn sổ
> mất do prune → đăng ký lại + gán lại → hai sổ về nguyên trạng. **Hai test cũ
> `test_c1_1/c1_4_sums_rows_of_same_code_and_unit` trước đây vô hiệu** (hai dòng đều `book=NULL` nên mutant
> đổi khoá gộp sang `(sổ,mã,đơn vị)` vẫn pass) — nay gắn EPE/GC, mutant đó làm đỏ 4 test.
> **MỘT THAY ĐỔI HÀNH VI (owner chốt):** `_plan_settlement_files` (`ingest.py:130-139`) ném `IngestPlanError`
> khi một số file settlement đã gán sổ còn số khác chưa — **gán sổ là tất-cả-hoặc-không**. Lý do: `book=NULL`
> ở pháp nhân nhiều sổ ĐÃ mang nghĩa "liên sổ", nên dòng của file chưa gán rơi vào nhóm liên sổ và
> C4.1/C4.3/C6.1 gom `None` thành SỔ THỨ BA rồi đối chiếu định mức/tồn kho bên trong sổ không tồn tại đó.
> Đặt SAU nhánh return sớm "không file nào có nhãn" → đường CLI + 002/006 KHÔNG đổi (2 test cũ vẫn xanh).
> **`/rev` bắt 2 lỗi thực, đã sửa trong PR:**
> (1) **`IngestPlanError` tới cán bộ dưới dạng HTTP 500 (JSON thô)** ở CẢ BA route gọi `run_ingest`
> (`upload_data`, `documents_confirm_review`, `documents_ingest_year`) — mà selector sổ là **per-file**, nên
> gán sổ cho file ĐẦU của kỳ hai file LUÔN đi qua đúng trạng thái bị từ chối: 500 nằm trên đường chính dựng
> pháp nhân hai sổ. Nay bắt `IngestPlanError` riêng → **303 về trang tài liệu + banner `?error=`**
> (`company_documents.html:29` render sẵn). Sổ vừa gán đã commit trước đó nên cán bộ gán tiếp file sau; từ
> chối xảy ra TRƯỚC lệnh xoá nên dòng của lượt nạp trước còn nguyên (kiểm bằng repro chạy endpoint thật).
> (2) **Text hướng dẫn `document_review.html:95` hứa sai:** "để trống mọi file = 1 sổ" chỉ đúng với kỳ **CHƯA
> từng nạp theo sổ** — kỳ đã có dòng EPE/GC thì bỏ hết nhãn bị `_books_already_stored` từ chối (guard PR #26),
> **không có đường quay về một sổ qua UI**, chỉ gán lại nhãn từng file. Text đã nói đúng giới hạn đó.
> (3) Minor: `test_two_books_tagged_via_browser_show_in_branch_a` không assert status 2 POST confirm → 500 ở
> lượt đầu lọt CI; nay assert 303. **+2 test route** cho luồng bị từ chối (confirm-review + nạp lại).
> **ĐỪNG tin lại:** chia BCCT thành 2 file theo sổ **KHÔNG** gán sổ được — `slot="bcct"` ngoài
> `SETTLEMENT_SLOTS` nên selector không render và handler confirm không đọc `book`; sâu hơn là
> `declaration_lines` không có cột `book`. Hai file vẫn nạp đủ nhưng bị trộn thành một luồng (`ingest.py:198`).
> **Next:** (1) punch-list 7 (lệch GLOSSARY/ADR #19) và 8 (`X.*` luôn `book=NULL`, `sql_runner.py:217-227`)
> vẫn mở; (2) nhãn sổ nên sống ở đâu cho bền — cần ADR, và ADR này giờ phải trả lời cả "đổi từ nhiều sổ về
> một sổ" (hiện bị từ chối, chỉ sửa được bằng gán lại nhãn); (3) prod vẫn hiện 3 CRITICAL sai của 004 tới khi
> chạy lại check — **cần owner quyết**.
> Session log: `.ai/sessions/2026-07-27-punchlist-6-book-tests.md`.

> **Trạng thái (2026-07-26 — AUDIT 004 HAI SỔ → SỬA LỖI TRỤC ĐƠN VỊ + CHẶN MẤT SỔ KHI INGEST — main=`dd763d4`):**
> Rà soát read-only tính đúng đắn mô hình hai sổ rồi sửa luôn. **Kết luận: trục `book` ĐÚNG, không check nào sai
> phạm vi; lỗi thật ở trục ĐƠN VỊ TÍNH.** Hai PR đã merge, **721 test pass trên `main` sau merge**.
> **PR #25** (`fix/multi-unit-findings`, merge `dd763d4`): C1.3/C1.6/C1.7 khử trùng theo `(book, material_code)`;
> C1.1/C1.4 so trong cùng đơn vị (CHỈ áp cho mã nhiều đơn vị — mã một đơn vị giữ nguyên nên 002/006 KHÔNG đổi);
> C3.3 dùng TẬP đơn vị thay ghi đè dict (hết phụ thuộc thứ tự dòng). Rồi 2 fix từ `/rev`: vế tờ khai đã chuẩn hoá
> đơn vị mà vế sổ còn khoá chuỗi thô (`MTR` vs `METRES` thành 2 lát), và `TypeError` khi một mã có dòng đơn vị NULL
> lẫn dòng có đơn vị — **check built-in KHÔNG được bọc try/except ở `run_checks.py:113`** nên lỗi này giết cả 17
> check + scoring của (DN,năm), không riêng C1.1. **004: 74 → 65 phát hiện** (C1.1 33→28, C1.3 15→13, C3.3 4→2);
> 3 CRITICAL sai (+99900% ×2, −98%) biến mất, 2 phát hiện −100% THẬT vẫn còn.
> **PR #26** (`fix/ingest-book-safety`, merge `bc9e887`): `_plan_settlement_files` ném `IngestPlanError` thay vì suy
> giảm im lặng — (a) từ chối gộp sổ khi tag `data_files` bị prune, đối chiếu `_books_already_stored()` đọc sổ từ
> `nvl_balances`/`sp_balances`/`norms` (nguồn ĐỘC LẬP với `data_files`); (b) từ chối chạy khi file settlement đã
> đăng ký bị thiếu/không đọc được. Chạy ở `ingest.py:191` **TRƯỚC** lệnh xoá `:196` → lượt nạp hỏng KHÔNG đụng dữ
> liệu cũ. Kiểm chứng read-only trên DB thật: company 9 kỳ 2025 → `['EPE','GC']`, guard ném đúng.
> **ĐÃ DEPLOY:** merge kích hoạt CI push/main, 2 run XANH, prod chạy **`dd763d4`** (`/healthz` 200, verify
> 2026-07-26T15:53Z). Hai PR này không có migration → head prod vẫn `d0e1f2a3b4c5`.
> **LƯU Ý:** deploy chỉ đổi CODE. Finding 004 trên prod VẪN là 74 bản cũ (gồm 3 CRITICAL sai) cho tới khi chạy
> lại check — xem Next (4).
> **DB LOCAL (không nằm trong git): ĐÃ SỬA DRIFT.** Đối chiếu từng revision trong 5 bản thiếu với schema thật —
> bốn bản đầu đã có sẵn (sửa tay trước đó), CHỈ thiếu `data_files.book`. Thêm cột + stamp `alembic_version` =
> **`d0e1f2a3b4c5` = head**. Backup `audit_hq.sqlite.bak-pre-schema-fix-20260726` (`Connection.backup()`,
> `integrity_check: ok`, 607.745 dòng / 24 bảng không đổi). Local giờ HẾT drift.
> **Punch-list (mục 5 báo cáo): đóng 1, 2, 3. CÒN MỞ 6, 7, 8, 9.**
> **Next:** (1) **nhãn sổ chưa bền** — guard chặn hậu quả nhưng tag vẫn mất khi prune, sau đó phải sync + gán lại
> book mới nạp được; ứng viên: ngừng prune dòng có tag · khôi phục map file→sổ từ `nvl_balances.source_file` ·
> chuyển sang `company_periods` → **cần ADR**; (2) punch-list 7 (GLOSSARY "Pháp nhân" còn tả mô hình 2 row đã bỏ;
> ADR #19 xếp nhầm C3.1/C3.2; "104 mã" vs 98) + ghi vào ADR #19 rằng che khuất tờ khai chỉ xảy ra **khi pháp nhân
> hai sổ khai cả hai sổ dưới mã CÙNG một loại hình**, không phổ quát; (3) punch-list 6 test-first — bản vá union
> 99→4 mà ADR #19 sinh ra để giải quyết vẫn CHƯA có test; (4) **prod vẫn hiện 3 CRITICAL sai** — finding nằm trong
> DB tới khi chạy lại check, chạy lại riêng 004 khả thi (check đọc bảng DB, chỉ ingest cần file nguồn) và ra 65,
> chính sách hiện tại CỐ Ý không re-run → **cần user quyết**; (5) CX.1 check rò rỉ liên sổ = mục catalog MỚI, phải
> vào `../audit-hq/de-an-audit-hq.md` trước (`CLAUDE.md:38`).
> **ĐỪNG tin lại:** gán nhãn tờ khai theo sổ **KHÔNG** phải bất khả thi với khách sau — `customs_code` cho sẵn khi
> mỗi sổ khai đúng loại hình của nó (tập mã rời nhau ở `app/checks/company_type.py:31-41`). **004 là ngoại lệ** vì
> khai cả hai sổ dưới mã chế xuất. Nên union ở check cross-layer là **mặc định đúng, không phải bắt buộc vĩnh
> viễn**; `detect_company_type` (một loại hình cho một DN, `:57-77`) mới là chỗ chặn nếu muốn hỗ trợ DN hai sổ khai
> đúng. Cột nhãn EPE/GC trong file NK thô là **do người gõ tay** (đối chiếu 33 file BCCT của 10 DN) → dùng làm bằng
> chứng audit, **KHÔNG** cho adapter đọc.
> Báo cáo audit: `.ai/sessions/2026-07-26-audit-004-hai-so.md`. Session log: `.ai/sessions/2026-07-26-multi-unit-fixes-ingest-guard.md`.

> **Trạng thái (2026-07-25 — NẠP 004 HAI SỔ (ẩn danh) LÊN PROD + 2SỔ đã MERGE+DEPLOY — main=`1eea393`):**
> **PR #23** (2SỔ UI+ingest, branch A+B) + **PR #24** ("Chung"→"Liên sổ") đã merge vào `main`, CI test+deploy XANH.
> Prod `audit-hq-demo.tinsu.ai` chạy **`1eea393`**, migration head **`d0e1f2a3b4c5`** (đã áp cột `data_files.book`).
> **Nạp 004 lên prod (CHỈ THAO TÁC DỮ LIỆU, build_sha KHÔNG đổi):** prod giờ **3 pháp nhân** — PILOT_002 (id7),
> PILOT_006 (id8), **PILOT_004 (id9, HAI SỔ)**. 004 = Sổ EPE 98 mã·34 pđ · Sổ GC 37 mã·0 pđ · Liên sổ 40 pđ
> (tổng 74). Tổng finding prod = **14.998**.
> **Ẩn danh §6.2 (verify 0 rò):** MST `0901051747`→`6944313927`; tên→"Công ty TNHH Chế Xuất & Gia Công Thí Điểm";
> 23 partner thật→`NCC_*`; GIỮ book tags + tên material/product. Quét TOÀN DB + `/showcase` (công khai): **0** hit
> MST/partner/tên thật. `evidence_refs` giữ `company_id=9` (id 9 trống trên prod) nên resolve đúng; bảng con
> DROP id → autoincrement mới, KHÔNG đụng id 002/006.
> **Cơ chế (2 stage, xem `$CLAUDE_JOB_DIR/tmp/prodload/build_004.py` — script throwaway, KHÔNG commit):**
> Stage 1 = snapshot WAL-safe dev DB (`.backup()`, KHÔNG đụng :8200) + snapshot prod → merge 004 ẩn danh vào bản
> copy prod → verify local (0 rò, UI hai sổ render). Stage 2 = online-backup prod (rollback) + giữ raw gốc →
> `docker stop`/thay file/`start` → `alembic upgrade head` (no-op) → verify.
> **Rollback (trên server `db-data/`):** `audit_hq.sqlite.bak-pre-004-load-20260725-152615` (online) +
> `audit_hq.sqlite.raw-pre-004-load-20260725-152615` (raw gốc). Restore = docker stop → cp bak→.sqlite → rm -wal/-shm → start.
> **LƯU Ý:** prod DB-ONLY (không file nguồn) → trang Tài liệu + selector review (branch B) của 004 TRỐNG; branch A
> (strip/lọc/Liên sổ) chạy đủ. `check_runs` prod trống → staleness forward-only. E2E proof 2SỔ: `.ai/features/
> 2026-07-25-2so-ui-ingest/` (nhãn "Liên sổ"). Prod screenshot 004 (đăng nhập) CHƯA chụp (tránh seed user prod).
> **Next:** — (không việc treo). Muốn xem UI hai sổ đăng nhập trên prod: seed admin throwaway (create_user) rồi purge.

> **Trạng thái (2026-07-25 — UI + INGEST THEO SỔ: cài trọn 5 ticket 2SỔ (branch A+B), ĐÃ MERGE PR #23/#24 + DEPLOY):**
> Cài hết 5 ticket GitHub #18/#20/#21/#19/#22 (2SỔ-1..5) theo **ADR #19 Revision — UI + upload**, test-first.
> **5 commit mới** (từ `8b88996`): `8937118` docs ADR/glossary · `95f23eb` branch A · `148bd3d` branch B ingest ·
> `250ee5f` branch B selector · (+1 commit review-fixes sắp tạo). **Full suite XANH**, ruff sạch.
> **Branch A (hiển thị+lọc, `95f23eb`):** `app/books.py` = `company_books`/`is_multi_book` (gate ≥2 sổ từ
> nvl∪sp∪norms, KHÔNG suy từ finding) · `book_label` (EPE/GC known-map, null→"Chung (liên sổ)") · `book_summary`
> (strip mã NVL + phát hiện mỗi sổ + Chung, loại COMBO_). `company_detail`: strip header, dòng split per-check
> `Sổ: EPE 8 · Chung 2`, pill book mỗi finding, segmented `?book=` (chung→`Finding.book IS NULL`), empty-state sổ
> sạch. **View-filter thuần:** điểm năm/strip/export/run GIỮ toàn pháp nhân; `checks_run` full-entity (không lật
> khi lọc sổ sạch). `finding_detail`: field "Sổ quyết toán". Một sổ (002/006) → book=NULL → KHÔNG chrome.
> **Branch B (upload+ingest):** migration **`d0e1f2a3b4c5`** cột `data_files.book` (down `c9d0e1f2a3b4`, head giờ
> `d0e1f2a3b4c5`). `ingest._plan_settlement_files`: đọc book per settlement file từ `data_files`, gom theo sổ,
> parse từng file, tag rows; không tag (CLI/script) → book=NULL → 002/006+script KHÔNG đổi; tờ khai ghi MỘT lần.
> **RETIRE `_guard_single_book`** (re-ingest nhiều sổ full-reprocess không mất sổ). Selector chọn sổ ở review WS1
> (`document_review.html` + confirm handler): chỉ slot settlement, datalist `company_books()`+EPE/GC, normalize
> trim/upper, ghi `data_files.book`; đổi sổ trên file đã parsed → re-run TOÀN BỘ năm.
> **Test:** +28 test mới (test_books/book_findings_ui/book_filter/ingest_book/book_selector), bỏ test_ingest_guard.
> E2E 2 sổ qua endpoint thật → branch A hiện strip 2 sổ.
> **Code-review 2 trục (Standards+Spec):** SỬA 1 lỗi thực — empty-state "đã được đánh giá" thiếu guard
> `checks_run` (nhiều sổ nạp nhưng CHƯA chạy → lọc sổ báo nhầm đánh giá-sạch); nay `checks_run` → tách nhánh
> "chưa chạy kiểm tra". Cleanup: hằng `SETTLEMENT_SLOTS`, import `normalize_book` top-level, datalist EPE/GC từ
> `BOOK_LABELS`. **Còn (ghi chú, ngoài scope):** multi-book UPLOAD đầy đủ chưa xong — `record_parse_result` áp
> MỘT provenance/slot → `parse_detail`/`row_count` per-file chưa đúng khi nhiều file cùng slot (balances vẫn
> đúng, chỉ số hiển thị per-file undercount); analyze-per-file là việc "B-plus" lớn hơn.
> **ĐÃ SHIP:** PR #23 (2SỔ, merge `9d90d3d`) + PR #24 ("Liên sổ", merge `1eea393`) merge+deploy XANH; prod áp
> `d0e1f2a3b4c5`; 004 hai sổ ẩn danh đã nạp prod (xem block trên cùng). `uv.lock` untracked.
> Session log: `.ai/sessions/2026-07-25-2so-ui-ingest.md`.

> **Trạng thái (2026-07-25 — 004 HAI LOẠI HÌNH: fix 6 check + cột `book` + collapse + trim DB LOCAL còn 3 pilot — CHƯA commit, PROD chưa đụng):**
> **ADR #19:** 004 (MST `0901051747`) là **1 DNCX có 2 SỔ QUYẾT TOÁN** khác loại hình (sổ tự sở hữu "EPE"
> + gia công "GC"), KHÔNG phải 2 chế độ. Tờ khai 1 list DNCX (E11/E15/E42) **dùng chung, nhân đôi** 2 row.
> Cũ: **C1.2=99, 91 GIẢ** (mã thuộc sổ kia bị báo "thiếu M15"). Từ đúng = "loại hình" (khớp enum
> `CompanyType`) KHÔNG "chế độ".
> **Code (test-first, 680 pass):** cột nullable `book` trên nvl/sp/norms/findings — migration
> `c9d0e1f2a3b4` (down `b8c9d0e1f2a3`). **C1.1/C1.4 gộp `(mã,đơn vị)`** (không cộng MTR+ROLL); **C4.1/C4.3/
> C6.1 `GROUP BY book`**; **C3.3** đơn vị per-`(book,mã)`; 8 check row-wise gắn `book`+evidence filter. Guard
> `_guard_single_book` chặn re-ingest pháp nhân nhiều sổ. **book=NULL = pháp nhân 1 sổ → 002/006 KHÔNG đổi**
> (re-run identical, verified).
> **DB LOCAL đã đổi (KHÔNG phải prod):** collapse 004 (id9 EPE + id10 GC → 1 row `PILOT_004`/`DEMO_004`,
> dedup tờ khai) → **C1.2 99→4, tổng 187→74, risk 30**. Trim còn **3 pilot**: PILOT_002 (48), PILOT_006
> (14876), PILOT_004 (74); xoá DN_001–005/ZZ_DEMO/DN_GATE + FK. Backup: `bak-pre-004-collapse-20260725-020819`
> + `bak-pre-trim-3pilots-20260725-023941` (+`-wal`/`-shm`; restore = cp đè).
> **Sửa DRIFT DB local:** local ở alembic `f5a6b7c8d9e0`, THIẾU `company_periods.data_version` (model bắt
> buộc) + `book` → `run_checks` CHẾT + server :8200 (`--reload` nạp model mới) 500 trên trang settlement/
> findings. Sửa bằng **ALTER trực tiếp** (`alembic upgrade` FAIL vì `check_runs` đã tồn tại). Server OK lại.
> Memory `local-db-schema-drift`.
> **Next:** (1) **commit** 004 work (16 M + feature dir + migration + guard + tests + ADR#19/GLOSSARY;
> `uv.lock` untracked); (2) prod ở `b8c9d0e1f2a3` = down_rev của migration mới → `alembic upgrade head` prod
> áp `c9d0e1f2a3b4` SẠCH (prod không drift); prod hiện chỉ 002/006, muốn có 004 thì collapse trên prod;
> (3) **UI 2 sổ: GRILL XONG (2026-07-25)** — design CHỐT ở **ADR #19 Revision — UI + upload**, CHƯA code.
> Hai nhánh: **A hiển thị+lọc** (split per-check + strip header `mã NVL·phát hiện` + segmented `Tất cả·EPE·
> GC·Chung` + pill row + finding_detail; `book`=null multi-book = "Chung liên sổ", KHÔNG gộp vào sổ khi lọc;
> gate `company_books()` ≥2 book từ nvl/sp/norms) — chạy trên data 004 ĐÃ gắn book, ship một mình. **B
> upload+ingest** (cột `data_files.book` + selector review WS1 + ingest đọc book per-file, full reprocess,
> RETIRE `_guard_single_book`, tờ khai ghi 1 lần). **Build A trước, B sau.** Glossary + ADR đã ghi.
> E2E proof/brief: `.ai/features/2026-07-25-004-two-loai-hinh/`. Session log `.ai/sessions/2026-07-25-004-two-loai-hinh.md`.

> **Trạng thái (2026-07-24 — LOAD PILOT 002/006 LÊN PROD (thay toàn bộ DN cũ) — main=`fe6efb9`, chỉ thao tác DỮ LIỆU):**
> Nạp pilot 002+006 (ẩn danh) lên prod, XOÁ 14 DN cũ. **DB-ONLY, KHÔNG đổi code** (build_sha vẫn `fe6efb9`).
> Prod DB giờ: **chỉ PILOT_002 (48 finding, điểm 7/2025) + PILOT_006 (14.883 finding, điểm 129/2024)** = 14.931 finding.
> Ẩn danh theo §6.2 (helper `anonymize.py`): tên tổng hợp "(Demo)", MST giả (hash `_deterministic_mst`), địa chỉ/slug
> tổng hợp, **179 partner→`NCC_*`**. Verify live: 0 MST thật, 0 partner thật, `/showcase` (công khai) không lộ tên/MST.
> **GIỮ:** 2 user prod + 27 ai_settings (AI bật + api_key) + app_settings + uom + check_definitions.
> **XOÁ kèm:** jobs, user_companies, ai_conversations/messages, access_events (log về DN đã gỡ, có thể chứa tên thật).
> **Backup prod TRƯỚC swap:** `db-data/audit_hq.sqlite.bak-pre-pilot-load-20260724-230046` (rollback = swap lại + restart).
> Cơ chế: snapshot WAL-safe prod (`src.backup()`) → build target local (empty tables DN cũ + copy 002/006 GIỮ id 7,8
> để evidence_refs còn đúng + anonymize) → scp → `docker stop`/replace file/`start` → `alembic upgrade head` no-op → verify.
> **LƯU Ý cho phiên sau:** (1) **DB-only** → trang Tài liệu/preview/download TRỐNG cho 002/006 (WS1 file-view KHÔNG
> demo được trên prod; muốn có thì phải ẩn danh nội dung file Excel rồi upload). (2) **`check_runs` prod TRỐNG** (không
> import run-history) → overview WS3 SINH được (đọc finding) nhưng staleness forward-only tới khi có người chạy check;
> **CỐ Ý KHÔNG re-run trên prod** (finding import là bản pilot đã verify — re-run rủi ro méo do combo OFF/C4.3 basis…).
> (3) Ẩn danh §6.2 GIỮ số tờ khai/hoá đơn/ngày + tên material/product — muốn scrub thêm là quyết định riêng.
> (4) **disk server 99% (4.2G trống)** — DB 290M vừa đủ; nên dọn backup cũ `bak-pre-c24`/`bak-pre-cleanup` (June, ~26M mỗi cái).
> Login prod: admin password chưa biết (như local) — kiểm authenticated bằng user throwaway nếu cần.

> **Trạng thái (2026-07-24 — WS3 MERGE + DEPLOY PROD (PR #17) — main=`fe6efb9`):**
> PR #17 (`feat/ws3-overview-staleness`→`main`) merge commit **`fe6efb9`**; CI run `30100248644` test+deploy XANH;
> prod `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=fe6efb9` khớp (build_time 14:18:49Z). Deploy áp 2 migration
> WS3 lên prod qua `alembic upgrade head`: `a7b8c9d0e1f2` (check_runs + data_version) + `b8c9d0e1f2a3` (check_overviews).
> **Migration head prod giờ `b8c9d0e1f2a3`.** **Lưu ý:** prod KHÔNG có pilot 002/004 hay DN synthetic → UI overview/
> staleness WS3 chưa có finding để thao tác tới khi nạp data lên prod. Chi tiết cài đặt: block ngay dưới + session log
> `.ai/sessions/2026-07-24-ws3-implement-e2e.md`. **Next:** nạp/reload data lên prod nếu muốn demo WS3 sống. `uv.lock` untracked.

> **Trạng thái (2026-07-24 — WS3 CÀI TRỌN + e2e proof + WS1 review-preview — branch `feat/ws3-overview-staleness`, CHƯA push):**
> Cài trọn **ADR #18 Rev WS3** (3 ticket) + 2 việc phát sinh. 3 commit: `89d62c9` WS3 · `1e85056` e2e proof ·
> `51521f9` WS1 review-preview. **670 test pass** (650→670, +20 WS3 TDD), ruff sạch, 2 migration up/down sạch.
> (1) **WS3:** `check_runs` latest-upsert 1 dòng/(DN,năm,mã) ghi TRONG `run_checks()` cho mọi check kể cả 0 finding +
> dọn orphan `X.*`; `data_version` số nguyên trên `CompanyPeriod` bump mỗi `ingest()` trong transaction (helper
> `current_data_version` ở `period.py`, đọc ở đầu run). `check_overviews` overwrite-upsert + telemetry
> (model/tokens/cost/latency), sinh on-demand qua endpoint **`def generate_overview`** (KHÔNG `async`, KHÔNG job
> worker — đọc snapshot → LLM → ghi SAU); UI panel ở group-actions + badge stale + mốc `based_on` + nút Tạo lại;
> flag-only KHÔNG auto-regen. Stale ⇔ `check_runs.ran_at` dời HOẶC `CompanyPeriod.data_version` dời. Migration head
> giờ **`b8c9d0e1f2a3`** (`a7b8c9d0e1f2` foundation → `b8c9d0e1f2a3` overview, down từ `b7d2e1f4a3c6`). Prompt nạp
> THÊM `top_titles` (aggregate, KHÔNG nạp dòng) ngoài `subject_key` — lệch spec CÓ CHỦ Ý (để tóm tắt nói CÁI GÌ sai).
> Review 2 trục (Standards+Spec) → sửa: thêm mốc `based_on` ở panel stale (ADR §4), xoá call chết
> `cache_supports_anthropic`, tách helper `current_data_version` (3 nơi), dọn test dead-code.
> (2) **E2E proof:** server throwaway (DN giả `DN_E2E`, KHÔNG đụng DB thật/:8200) chạy luồng HTTP THẬT
> upload→parse(verified+gate)→run(C2.1×3,C2.3×1,17 check_runs)→overview(LLM thật deepseek/OpenRouter)→re-run/stale;
> 6 screenshot + `ui_smoke.py` ở `.ai/features/2026-07-24-parse-review-per-test-ux/`.
> (3) **WS1 review-preview:** nhúng grid nội dung file vào màn xác nhận cột, tag field mỗi cột (khớp tiêu đề=xanh,
> needs_review=vàng) + live-highlight cột khi sửa chỉ số; refactor `_extract_sheet_preview` dùng chung preview+review.
> **Next:** push branch → PR → merge → deploy (CI test+lint+deploy self-hosted); reload data 002/004 lên prod nếu cần.
> `uv.lock` để untracked. Session log: `.ai/sessions/2026-07-24-ws3-implement-e2e.md`. Memory
> `ws3-overview-staleness-model` đã đánh dấu ĐÃ CÀI.

> **Trạng thái (2026-07-24 — grill WS3 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs WS3` (AI tổng quan mỗi test + staleness). GREENFIELD (không
> `check_runs`/`data_version`/overview lưu trữ nào). Chốt 8 nhánh + gộp **ADR #18 Revision — WS3**
> (không tách #19). Advisor (fable) endorse Q1–Q7, LẬT Q8. Cốt lõi: (1) `check_runs` latest-upsert
> 1 dòng mỗi `(DN,năm,mã)` ghi TRONG `run_checks()` cho mọi check kể cả 0 finding (không suy từ
> `findings.created_at`); (2) `data_version` số nguyên trên `CompanyPeriod` bump mỗi ingest —
> **stale ⇔ `ran_at` dời HOẶC `data_version` dời** (vì `documents_ingest_year` re-ingest mà KHÔNG
> chạy check → điểm mù nếu chỉ `ran_at`); (3) `check_overviews` overwrite-upsert + telemetry riêng,
> sinh ON-DEMAND ĐỒNG BỘ trong request bằng endpoint `def` THUẦN (không `async def` — sync client
> chặn event loop; không qua job worker 1-thread); (4) flag-only stale (nút "Tạo lại", không
> auto-regenerate); (5) combo LOẠI + **forward-only KHÔNG backfill**. **GOTCHA:**
> `CompanyYearScore.computed_at` là mốc FIRST-run KHÔNG phải latest (`server_default` không `onupdate`)
> → không backfill từ nó. Prompt nạp ĐẾM+top-N subject_key không nạp dòng (11.003 finding/DN-năm).
> 3 ràng buộc cài đặt: bump version trong transaction ingest · đọc version ở ĐẦU run · upsert trong
> `run_checks()` không ở job handler. **KHÔNG đụng code.** Docs: ADR #18 Rev WS3 + GLOSSARY (WS3) +
> memory `ws3-overview-staleness-model` — CHƯA commit. `not_evaluable` là Tầng C chờ họp (cột dành sẵn).
> **Next:** `/to-tickets` (nền check_runs+data_version → overview model+endpoint → UI panel/badge),
> mỗi ticket session fresh tham chiếu ADR #18 Rev WS3. WS3 nền check_runs ĐỘC LẬP WS2.
> Session log: `.ai/sessions/2026-07-24-grill-ws3.md`.

> **Trạng thái (2026-07-24 — WS1+WS2 ĐÃ MERGE + DEPLOY PROD (PR #16) — main=`6f052d3`):**
> PR #16 (`feat/ws1-parse-review`→`main`) merge commit **`6f052d3`**; CI test+lint+deploy XANH; prod
> `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=6f052d3` khớp. Áp 2 migration prod: `b7d2e1f4a3c6`
> (saved-map WS1) + `f5a6b7c8d9e0` (badge ADR#17). PR gộp cả ADR#17 (M15a/M16 004) + docs grill WS3.
> Combo mặc định TẮT trên prod (bật ở `/admin/checks`). **Next thực:** implement WS3 (`/to-tickets`
> ADR#18 Rev WS3); reload data 002/004 lên prod nếu cần; chạy lại harness khi chạm parse/check.
>
> **Chi tiết cài WS2 (đã merge ở trên):** Cài trọn WS2 + làm lại UX chọn test. 6 commit code:
> `5c22a5a` nền · `ecb16c4` UI/async · `4b45bf2` STATUS · `054e9cd`+`e9055e3`+`5ad7f71`+`ad4fcc0` modal UX
> (694fb3b ở giữa là grill WS3 của phiên khác). (1) **Nền:** `RUN_CHECKS` payload `only:list[str]`;
> `run_checks(only=)` chạy tập con; combo **recompute MỌI lần chạy** đọc TOÀN finding-set, gate
> `combos_enabled` (app_settings, **default OFF**); delete `COMBO_*` giữ vô điều kiện. (2) **Chạy test
> lẻ:** nút "Chạy lại {mã}" mỗi nhóm → `RUN_CHECKS {only:[mã], năm}` → `/jobs/{id}`. (3) **Export chọn:**
> `build_export(only=)` lọc `check_code.in_()`; `/export?check=` lặp; Tổng quan liệt kê mã chọn.
> (4) **`documents_confirm_review` async** (option A: save-map+re-ingest sync, re-run scoped **enqueue**
> → `/jobs/{id}` khi re-confirm); ẩn combo ở company_detail khi OFF; toggle admin combo ở card đầu trang
> `/admin/checks`. **Modal UX (theo /frontend-design Anthropic):** panel `<details>` xấu → thay bằng 2
> `<dialog>` native ("Chọn test chạy" = toàn danh mục · "Xuất Excel" = mã có finding), hàng bấm-cả-hàng
> checkbox 18px accent navy, **gom theo họ C1/C2/… tiêu đề nhóm §4 sticky** (`_group_options_by_family`),
> footer đếm sống + nút tự mô tả ("Chạy 3 test"/"Chạy tất cả"), a11y qua WIG (focus-visible/overscroll/
> aria-labelledby). **650 test pass, ruff sạch, KHÔNG migration** (`combos_enabled`=1 row `app_settings`).
> Review (critic) bắt **Defect 1 đã sửa:** pre-delete của `run_checks(only=)` phải gồm cả mã dynamic `X.*`
> (không chỉ built-in) → nếu không "Chạy lại X.1" nhân đôi finding (regression test thêm). Defect 2 (max_raw
> giữ +20 combo khi OFF) **không sửa** — ADR chốt "Scoring KHÔNG đổi", có sẵn từ trước WS2.
> **Lưu ý harness:** combo default OFF → full-run bỏ meta-finding COMBO_* so với mốc 417 (delta CÓ CHỦ Ý,
> không phải regression). **Next:** push/merge WS1+WS2; implement WS3 (`/to-tickets` ADR #18 Rev WS3).
> Memory `check-execution-async-via-jobs` đã đánh dấu ĐÃ CÀI. Session log: `.ai/sessions/2026-07-24-ws2-implement-modal-ux.md`.

> **Trạng thái (2026-07-24 — WS1 IMPLEMENT XONG (5 ticket) + demo build + fix dev server):**
> WS1 cài trọn trên branch `feat/ws1-parse-review`: #4 evidence source+review state+registry
> (`7df7e22`) · #5 vòng đời file+cổng review (`0653f1d`) · #6 vân tay form+saved-map store
> (migration `b7d2e1f4a3c6`, `fca9bbb`) · #7 màn review (`573a273`) · #8 re-run scoped (`f00db6f`).
> **634 test pass, ruff sạch, harness giữ 417** (WS1 provenance/UX, KHÔNG đổi finding). Issue GH
> #4–#8 (ready-for-agent) đã cài nhưng **CHƯA push/merge/PR**. `uv.lock` để untracked.
> **2 giới hạn WS1:** (1) parser CHƯA đọc vị trí cột từ saved-map — sửa cột chỉ đánh `officer-confirmed`,
> chưa rewire parse; (2) `run_checks(only=)` xoá COMBO năm đó tới lần chạy full.
> **Nợ do WS2 revise ADR #18:** #7/#8 gọi `run_checks` ĐỒNG BỘ trong `documents_confirm_review` →
> phải chuyển sang job queue (WS2 chốt check chạy async).
> **Demo build** `db-data/audit_hq_demo.sqlite` (gitignored, CHƯA deploy): chỉ 002/004/006, đổi tên;
> 004 = gộp EPE+GC (option 2) = **219 finding** (méo 187→219, PHẢI phân tích lại — memory
> `pilot-004-epe-gc-merge`). MST thật CÒN ở `tax_id`; file Excel gốc còn tên thật.
> **Dev server:** process cũ `84da630` (không `--reload`) 500 trang company vì DB đã tiến xa → đã
> kill PID 8340 + relaunch detached `--reload` trên code hiện tại, mọi trang 200.
> **Next:** grill WS3 (session fresh, worktree/branch riêng) song song WS2-impl; push/merge WS1;
> deploy demo (+ kiểm `user_companies`/login); 004 phân tích lại; async-hoá `run_checks` #7/#8.
> Session log: `.ai/sessions/2026-07-24-ws1-implement-demo-build.md`.

> **Trạng thái (2026-07-24 — grill WS2 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs WS2` (chạy test lẻ + export chọn). WS1 đã cài (branch `feat/ws1-parse-review`,
> #4–#7). Chốt + gộp vào **ADR #18 Revision — WS2** (không tách #19, theo owner):
> (1) **Chạy check TẤT CẢ async qua job queue** — SỬA "re-run inline" của WS1; `RUN_CHECKS` payload
> thêm `only: list[str]`; worker 1-thread serialize ghi → hết tranh chấp SQLite writer. Per-test run =
> nút mỗi nhóm check → `RUN_CHECKS {only:[mã], năm đang xem}` → `/jobs/{id}`. `documents_confirm_review`
> tách confirm/run (option A): save-map + re-ingest GIỮ đồng bộ (file→`parsed`), re-run scoped →
> enqueue job. (2) **Combo:** recompute MỖI lần chạy đọc TOÀN finding-set (sửa lỗi chạy lẻ xoá combo
> không dựng lại) + toggle `combos_enabled` (app_settings, **default OFF**, lazy per-run, ẩn cả render
> lẫn recompute) — OFF vì 2/4 combo neo C4.3 đang đổi định nghĩa. (3) **Export chọn test EPHEMERAL:**
> `build_export(only=)` + param `check` lặp, không chọn = xuất đủ, không "profile". WS2 build được CHỈ
> với hạ tầng job + registry WS1, **KHÔNG cần `check_runs`/`data_version` (WS3)**. **KHÔNG đụng code.**
> Docs: ADR #18 Revision + GLOSSARY (mục WS2) + memory `check-execution-async-via-jobs` — CHƯA commit.
> **Next:** `/to-tickets` cắt slice (đề xuất: nền `only` trong `RUN_CHECKS` handler + `combos_enabled`
> read → per-test run UI → selective export → sửa `confirm_review` sang async), mỗi ticket session fresh
> tham chiếu ADR #18 Revision — WS2.

> **Trạng thái (2026-07-24 khuya — grill WS1 xong, design CHỐT, CHƯA code):**
> Chạy `/grill-with-docs` cho **WS1** (parse review + map cột) của brief UI redesign. Chốt toàn bộ
> nhánh chịu lực → **ADR #18** (`.ai/DECISIONS.md`) + **`.ai/GLOSSARY.md`** (mới) + memory
> `parse-confidence-evidence-model`. Cốt lõi: tin cậy = **evidence source mỗi cột** (`officer-confirmed`
> > `header-matched`·`balance-checked` > `position-only`; `balance-checked` chỉ đủ cho cột dạng TỔNG
> vì đẳng thức bất biến dưới hoán vị cột cùng dấu — advisor xác nhận, C2.1/C2.2 đã own đẳng thức).
> Badge **2 trạng thái** `verified`/`needs_review`; cổng review **per-file, warn-not-block**; registry
> `check→cột` dict tĩnh (`consumed_as: individual|sum`); map lưu theo **(DN, vân tay form)** — **per-DN
> confirm (option 2, SỬA ADR #15 cross-DN)**; vòng đời file **`uploaded→analyzed→parsed`** (auto-advance
> khi verified) hiện trên UI; AI = bước sửa (ADR #15); staleness = re-run check bị ảnh hưởng inline,
> stale-flag để WS3. **KHÔNG đụng code.** Working-tree: ADR #18 + GLOSSARY.md **CHƯA commit**.
> **Next:** `/to-tickets` cắt 4 slice → `/implement` ticket 1 (nền: registry + evidence tagging trên
> đường standard — giữ `SheetCandidate.colmap` đang bị `parse_m15` vứt, thêm keyword cột 6/7/9,
> ghi evidence vào `ParseProvenance`), **mỗi ticket một session fresh** tham chiếu ADR #18.
> Session log: `.ai/sessions/2026-07-24-grill-ws1.md`.

> **Trạng thái (2026-07-24 tối — C4.3 đổi số nhân + tầm nhìn UI redesign):**
> Hai việc phiên này. (1) **C4.3 / P-07:** đã sửa đề án §4.1 (số nhân định mức = **sản lượng sản
> xuất**, không phải xuất khẩu) + ADR ở `audit-hq/.ai/DECISIONS.md` — **CHƯA COMMIT**, cross-repo.
> Code `app/checks/c4_norm.py` **chưa sửa** (việc `/implement` kế tiếp): đổi `sp_export`→sản lượng,
> tách (6)/(7) ở `resolve_m15a`, skip mã không-nguồn nhường C4.1, thêm bậc mâu thuẫn vật lý. Đo
> trên dữ liệu thật: 2.371→2.063 finding (−13%). Chi tiết `audit-hq-pilot/notes/13` P-07.
> (2) **UI redesign:** brief 3 workstream (phát hiện+map cột / chạy test lẻ+export chọn / AI overview+stale)
> ở `.ai/features/2026-07-24-parse-review-per-test-ux/brief.md` — input cho `/grill-with-docs`.
> Owner muốn **mở session mới chạy flow Matt**, nghiêng grill WS1 trước.
> (3) **002 (PILOT_002) đã sửa cấu hình kỳ** trên DB localhost: re-ingest với cửa sổ tài chính
> → 279→48 finding, risk 65→7. Backup `audit_hq.sqlite.bak-pre-002-reingest-20260724`.
> Session log: `.ai/sessions/2026-07-24-c43-basis-and-ui-redesign.md`.

> **Trạng thái (2026-07-24 — M15a mở rộng + M16 ĐM thực tế cho 004 + badge truy nguồn — CHƯA COMMIT):**
> Hoàn thành phần "CHƯA thực hiện — Mẫu 15a" của ADR #15 (nay là **ADR #17**). `resolve_m15a`
> (`extended_layout.py`): cổng đẳng thức + `export_qty` theo NHÃN (duy nhất, phải là số hạng trừ)
> + khai triển nhãn gộp `(8ab)`. `content_slots` dò thêm đường mở rộng cho m15a. M16 chọn cột ĐM
> "thực tế" khi có cặp kỹ thuật/thực tế (004). **Badge CÓ LƯU** (`DataFile.parse_layout`/`parse_detail`,
> migration **`f5a6b7c8d9e0`**): trang Tài liệu + trang Dữ liệu gốc hiện bố cục + đẳng thức N/N +
> nhãn cột. Đo thật: 004 EPE M15a 43 (43/43) + M16 664 (c8 thực tế) → **C4.3 fire 8**; 004 GC M15a 2
> + **C1.4 fire 2** (sau khi đặt kỳ GC manual = FY2025 vì header GC ghi sai). 006/whitelist đường
> CHUẨN không đụng. **Harness: 419→419 y hệt** (trung tính; 419 ≠ "1.331" cũ — xem ADR #17 + memory).
> Full suite **583 pass**, ruff clean. **CHƯA commit, CHƯA deploy** (local DB đã đổi + migration đã áp local).
> Screenshot: `.ai/features/2026-07-24-m15a-m16-004/screenshots/`.
>
> **Trạng thái (2026-07-24 — C1 kỳ báo cáo custom-date, full-stack — ĐÃ DEPLOY PROD):**
> Xong C1 `period_from/to` (ADR #16). BCCT chọn theo cửa sổ kỳ `[from,to]` thay `==year`;
> `period_year` = nhãn kỳ (tách khỏi `declaration_date`). Bảng `company_periods` + migration
> `e4f5a6b7c8d9`. Frontend: trang tài liệu sửa được kỳ (form + banner + về mặc định) + nhãn năm
> tài chính ở company_detail/item_detail. 22 test mới, full suite xanh. Harness: PILOT_002 phục
> hồi **đúng 3.014** dòng (window tự đọc 2025-04-01..2026-03-31), whitelist **1.331** finding BẤT
> BIẾN (code cũ cũng 1.331 — mốc "419" cũ đã lỗi thời).
> **ĐÃ MERGE + DEPLOY:** PR #2 → merge commit **`f5d2c0c`** → CI test+lint+deploy xanh →
> prod `audit-hq-demo.tinsu.ai` `/healthz` 200, `build_sha=f5d2c0c` khớp. Migration
> `e4f5a6b7c8d9` đã `alembic upgrade head` trên DB prod. Migration head giờ **`e4f5a6b7c8d9`**.
>
> **Trạng thái (2026-07-23 — Tier A parse layer + B1 + ADR 15 Mẫu 15):**
> Phiên dài, xử lý bộ dữ liệu mới 3 DN (002/004/006) từ `audit-hq-pilot`. Viết lại **tầng
> parse**: chọn sheet theo nội dung, dò dòng dữ liệu, đếm ô hỏng, chọn cột theo bố cục mở
> rộng qua đẳng thức của biểu. Sửa C4.3 nhân trùng khối định mức (B1). Sửa trang finding
> (18,7 MB → 294 KB) + trang tài liệu nhiều slot. **4 lần deploy, đều xanh.**
> **`main` = `origin/main` = prod = `c82ffa9`**, working tree sạch.
> Migration head **`d3e4f5a6b7c8`** (KHÔNG đổi phiên này — không có migration nào phiên này).
> 523 test function, full suite pass.

## Current State

### Git / deploy
- **`main` = `origin/main` = prod = `d7844b6`** (merge PR #42), working tree sạch (trừ `uv.lock` untracked).
  Prod `audit-hq-demo.tinsu.ai` `/healthz` 200 `build_sha=d7844b6`. **850 test pass**, ruff sạch.
- Mốc phiên này: `6a38230` (PR #37 CHAT-1..4) → `ed69a0f` (PR #41 TQ-1+2) → `141b600` (PR #39 TQ-3..5)
  → `d7844b6` (PR #42 fix CSS + E2E proof). Trước phiên: `03d5031` (PR #27).
- **DB local ở alembic head `c5d6e7f8a9b0`**. Backup cũ `bak-pre-schema-fix-20260726`.
- Migration head prod = **`c5d6e7f8a9b0`** — 5 migration phiên này: `e1f2a3b4c5d6` (`ai_conversations.company_id`)
  → `f2a3b4c5d6e7` (bảng `ai_usage`) → `a3b4c5d6e7f8` (`check_overviews.status/job_id/error`)
  → `b4c5d6e7f8a9` (`aggregate_json`) → `c5d6e7f8a9b0` (`sections_json`/`needs_review`/`unsupported_numbers`).
  Backup trước khi áp: `db-data/audit_hq.sqlite.bak-pre-adr2021-20260727`.
- **LƯU Ý CI:** `gh pr checks` KHÔNG bao giờ có gì — workflow chỉ chạy `on: push branches:[main]`, tức CI
  chạy SAU khi merge. Test PHẢI chạy đủ ở local trước khi merge, và chạy với `DATABASE_URL` trỏ **file rỗng**
  (xem lỗi (3) ở block đầu file — DB dev có sẵn cấu hình làm test xanh giả).
- **LƯU Ý PR xếp chồng:** merge PR base kèm `--delete-branch` khiến GitHub **tự ĐÓNG** PR con trỏ vào nhánh
  đó (không retarget, và không reopen được). Đổi base sang `main` TRƯỚC khi merge PR cha, hoặc merge không
  xoá nhánh. PR #38 mất theo cách này, phải tạo lại thành #41.
- Prod data = **3 pháp nhân**: PILOT_002, PILOT_006, PILOT_004 (hai sổ EPE/GC, ẩn danh — nạp 2026-07-25, xem block đầu file).
- Deploy = push `main` → CI "Test & Deploy to Tinsu" (self-hosted `tinsu-prod`): test+lint →
  docker build → restart → `alembic upgrade head` → healthcheck. Watch: `gh run watch <id> --exit-status`.
  **LƯU Ý:** runner self-hosted đôi khi queue 10+ phút trước khi chạy — không phải lỗi.
- 9 commit phiên này (từ `fadc427`): xem session log `2026-07-23-tier-a-parse-layer.md`.

### Prod ≠ local — ĐỌC KỸ trước khi đụng dữ liệu
- **DB prod ở server** (`/home/tinsu/audit-hq-mvp-deploy/db-data/audit_hq.sqlite`, ~291 MB,
  truy cập qua `ssh tinsu` + `docker exec audit-hq-mvp`). **CẬP NHẬT 2026-07-25:** prod giờ có
  **PILOT_002 + PILOT_006 + PILOT_004 (hai sổ, ẩn danh)** = **14.989** finding sau khi chạy lại check 004
  ngày 2026-07-27 (trước đó 14.998 — xem block đầu file).
  Rollback 004-load: `db-data/audit_hq.sqlite.{bak,raw}-pre-004-load-20260725-152615`.
  Backup DN cũ (2026-07-24): `db-data/audit_hq.sqlite.bak-pre-pilot-load-20260724-230046`.
- **KHÔNG có file nguồn trên prod cho 002/006** (DB-only) → trang Tài liệu/preview/download trống cho 2 DN này.
  (Cũ: raw-data prod dùng `DN_001/DN_103/...` — nay không còn dùng, 14 DN đó đã gỡ.)
- **`run_all` tìm 0 cặp trên prod** (whitelist là HONG_AN/GROWATT/DO_THANH/KIM_LONG — không tồn
  tại ở server). Re-ingest prod bằng `run_all` là no-op.
- **Local `data/` symlink** → `../audit-hq/data/raw`, có tên THẬT (HONG_AN…) + PILOT_002/004/006.
  Ingest theo `code` → tạo company mới, KHÔNG ghi đè `DN_xxx`. Xem [[local-data-symlink-mismatch]].

### Dữ liệu mới 3 DN (002/004/006) — đã nạp vào LOCAL DB
- Local DB giờ có `PILOT_002` (279 finding), `PILOT_006` (14.883), `PILOT_004_EPE` (111),
  `PILOT_004_GC` (99). Chỉ ở local — KHÔNG ở prod.
- Symlink tree đã tạo cố định: `../audit-hq/data/raw/PILOT_{002,004_EPE,004_GC,006}/<năm>/{BCQT,DINH_MUC,HANG_CHI_TIET}`
  (trỏ tới `raw-hq-2026`, gitignored). `discover`/`ingest` đọc trực tiếp được.
- **File nguồn:** `/mnt/p/Downloads/audit-v2.zip` (148 MB) = giải nén sẵn ở `audit-hq/data/raw-hq-2026/`.
- Verify chéo với parser độc lập của pilot: 006 điểm 154/190 y hệt, M15 10.560 dòng, sai lệch
  2/21.878 finding. → tầng parse đúng.

### Tầng parse — trạng thái từng phần
- **Chọn sheet theo nội dung** (`app/adapters/sheet_select.py`): chấm điểm nhãn cột đúng vị
  trí, phá hoà theo kỳ báo cáo (rank), báo `SheetNotFound` nếu không khớp. 4 slot đều dùng.
- **Dò dòng dữ liệu + P-01** (`app/adapters/layout.py`): `_norm` gập đ/Đ (U+0111/U+0110), dò
  header 2 dòng + dòng đánh số `(1)(2)…`.
- **Bố cục mở rộng Mẫu 15** (`app/adapters/extended_layout.py`, ADR #15): suy map cột từ dòng
  đánh số, chứng minh bằng đẳng thức `(11)=(5)+(6)-(7)-(8)-(9)-(10)` ≥98% dòng. Chỉ chạy khi
  `select_sheet` trượt → prod (16 file, 0 trượt) KHÔNG đụng. 004 nạp được M15 (EPE 104, GC 37).
- **A3 ô hỏng** (`_common.py`): đếm ô lỗi Excel + liên kết workbook ngoài, cảnh báo không đổi số.
- **B1 C4.3** (`c4_norm.py`): mỗi cặp BOM tính 1 lần thay vì 1 lần/khối lặp.

## Recent Changes (2026-07-27)
9 vé ADR #20 + #21, 5 PR, 3 lần deploy prod (`6a38230` → `ed69a0f` → `141b600` → `d7844b6`):
1. **PR #37** CHAT-1..4 — cuộc trò chuyện gắn DN (migration `e1f2a3b4c5d6`).
2. **PR #40** fix test xanh giả vì DB dev (làm `main` đỏ một nhịp, deploy KHÔNG chạy).
3. **PR #41** TQ-1+TQ-2 — sổ `ai_usage` + worker chia theo loại job
   (migration `f2a3b4c5d6e7`, `a3b4c5d6e7f8`). *Vốn là #38, GitHub tự đóng khi nhánh base bị xoá.*
4. **PR #39** TQ-3..5 — bảng số liệu, nhận định JSON bốn mục, nút gộp cả năm
   (migration `b4c5d6e7f8a9`, `c5d6e7f8a9b0`).
5. **PR #42** fix CSS khối phạm vi hiện rỗng + 8 ảnh E2E.

Chi tiết: `.ai/sessions/2026-07-27-adr20-chat-scope-adr21-overview-v2.md`.
Mốc trước (2026-07-23, 9 commit tầng parse): `.ai/sessions/2026-07-23-tier-a-parse-layer.md`.

## Next Steps (theo ưu tiên)
1. **Rà soát toàn bộ ngôn ngữ tiếng Việt trên UI** — owner chốt 2026-07-27. Work-list 6 mục ở
   `.ai/BACKLOG.md` **mục đầu file**. Có sẵn nhánh **`fix/badge-wording` (`ebff51c`) CHƯA MERGE**
   (1 dòng, sửa badge tổng quan) — **rebase lên `main` rồi làm tiếp trên nó**, đừng sửa lại từ đầu.
   Owner chốt làm ở **session mới**, đường `/grill-with-docs` → `/implement` (3/6 mục là quyết định
   chứ không phải việc tay chân: `job.result` khoá Anh/Việt, các từ `combo`/`file`/`link`, chữ `AI`).
   Xong phải **chụp lại ảnh 07** ở `.ai/features/2026-07-27-chat-scope-overview-v2/screenshots/`.
2. **Punch-list 7 + 8 (mở từ 2026-07-26):** (7) lệch tài liệu — GLOSSARY mục "Pháp nhân" còn tả mô
   hình 2 row đã bỏ, ADR #19 xếp nhầm C3.1/C3.2, "104 mã" thật ra là 104 DÒNG / 98 mã;
   (8) check động `X.*` luôn emit `book=NULL` (`sql_runner.py:217-227`).
3. **ADR "nhãn sổ sống ở đâu cho bền"** — chưa viết. Phải trả lời cả đường quay từ nhiều sổ về một
   sổ (hiện bị từ chối, chỉ sửa được bằng gán lại nhãn từng file).
4. **Dọn đĩa server** (96%, còn 11G) — `docker system df` báo 68 GB image reclaimable, `db-data`
   1,5G / 6 backup. Cần owner chốt vì xoá không quay lại được.
5. **Sửa đề án `../audit-hq/de-an-audit-hq.md:228` TRƯỚC** rồi mới làm B2 (đổi hệ số nhân C4.3
   sang lượng nhập kho SX), B4 (báo độ phủ C4.3), và hệ số nhân theo sản lượng Mẫu 16. Cả ba
   mâu thuẫn định nghĩa `Σ(định_mức × xuất_khẩu_M15a)` hiện tại — là "sửa catalog" theo AGENTS.md.
6. **B3 đọc cột Ghi chú** — cần migration (thêm `note` vào NvlBalance/SpBalance).
7. **Tầng C — chờ họp:** `NOT_EVALUABLE` (phân biệt "0 vì sạch" vs "0 vì thiếu dữ liệu"), trình bày
   quy mô lớn (đã làm phân trang, còn xếp hạng theo lượng + ngưỡng severity).

## Blockers
- **B2/B4/hệ số nhân C4.3 chặn bởi đề án** — không được sửa mô tả check trước khi update
  `../audit-hq/`. Câu hỏi quy trình 3 repo, cần user chốt.
- **~~Banner "dữ liệu mẫu" chặn đưa pilot lên demo~~ — KHÔNG CÒN CHẶN.** Prod đã nạp 002/006
  (2026-07-24) rồi 004 (2026-07-25) qua đường ẩn danh §6.2, verify 0 rò. **Còn lại là vấn đề
  LOCAL:** kiểm 2026-07-27 thấy DB local tên đã ẩn (`DEMO_002/004/006`) nhưng **`tax_id` vẫn là
  MST THẬT** (`0901051747`…), trong khi banner nói "dữ liệu mẫu". Chỉ ảnh hưởng máy dev, không
  ảnh hưởng prod. `anonymize.py` vẫn chỉ sửa DB, KHÔNG sửa nội dung file Excel.
- **Tầng C chờ họp** (chưa có lịch).

## Notes for Next AI Session
- **Dev server local KHÔNG còn chạy** (kiểm 2026-07-27: `:8200` không phản hồi — ghi chú cũ nói
  "đang chạy" đã sai). Cần thì tự dựng. Local admin password KHÔNG biết → đăng nhập bằng user
  throwaway seed qua `create_user` rồi purge (xem [[ui-screenshots-convention]]).
- **Dựng server throwaway để chụp ảnh** — mẫu chạy được ở
  `.ai/features/2026-07-27-chat-scope-overview-v2/brief.md`: `setsid` + DB riêng + cổng riêng
  (8327), **kill theo PID**, TUYỆT ĐỐI không `pkill -f uvicorn` (giết luôn :8200 của user nếu
  user đang chạy — xem [[dev-server-do-not-pkill]]).
- **Chạy test PHẢI kèm `DATABASE_URL` trỏ file rỗng trước khi merge.** CI chỉ chạy
  `on: push branches:[main]` nên **PR không có check nào** — CI chạy SAU khi merge. Suite chạy
  mặc định đọc `audit_hq.sqlite` thật của máy dev và có thể xanh giả (xem
  [[test-false-green-ambient-db]] — đã làm `main` đỏ một nhịp phiên này):
  ```bash
  DATABASE_URL="sqlite:///<file-rong>" .venv/bin/python -m pytest -q
  ```
- **PR xếp chồng:** merge PR cha kèm `--delete-branch` làm GitHub **tự đóng** PR con trỏ vào
  nhánh đó, không retarget và **không reopen được**. Đổi base sang `main` TRƯỚC khi merge PR cha.
- **`git add -A` nuốt `uv.lock`** — dự án cố ý để untracked. Add từng đường dẫn cụ thể.
- **Harness verify** (scratchpad, session-specific, có thể mất): ingest+run_checks toàn bộ
  whitelist vào DB tạm, dump finding đã sort, diff trước/sau. **Mốc chuẩn hiện tại (2026-07-24):
  1.331 finding trên 12 cặp DN×năm** (đo lại code cũ = code mới sau C1 → C1 trung tính). Con số
  "419" trong ghi chú cũ ĐÃ LỖI THỜI (khác bộ dữ liệu/thời điểm) — đừng dùng làm tiêu chí. Chạy
  lại mỗi khi chạm tầng parse/check.
- **Kỷ luật số liệu:** số của `audit-hq-pilot/notes/` đếm theo luật parser CỦA PILOT, không
  phải sản phẩm — phải phát biểu lại theo luật đếm sản phẩm trước khi dùng làm tiêu chí. Xem
  [[tier-a-thu-tu-a1-truoc-a2]] và [[so-lieu-phai-co-mau-so-va-nguon-doc-lap]].
- **A1 trước A2, KHÔNG song song** — `notes/12` ghi sai, đã đính chính. A2 chạy trước A1 làm
  hỏng nặng thêm (đo được +20 finding CRITICAL giả).
- **Cổng đẳng thức là trọng tài** cho map cột — không tin nhãn/mô hình. Bug bắt được nhờ nó:
  số hạng đầu công thức `(5)+(6)-...` không có dấu, 004 GC "lọt" giả vì tồn đầu toàn 0.
- **ADR mới:** `.ai/DECISIONS.md` #15 (15 ADR tổng). Ghi rõ phần đã làm (M15) vs chưa (M15a/M16).
- `audit-hq-pilot` là repo anh em (git local, không remote), commit `7e8e438` đã đính chính
  `notes/12`. Prompt bàn giao gốc ở `audit-hq-pilot/.ai/STATUS.md`.
