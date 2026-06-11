# Session 2026-06-11 — Empower AI Chat Assistant + loạt fix demo (live)

Bắt đầu từ build `8d6b6c5`/`54d5f33`. Kết thúc build live **`11bbcdd`**, 11 commit,
510 tests pass. Toàn bộ đã deploy prod + verify (phần lớn bằng Playwright headless).
Session kết thúc khi user gõ `/handoff` ngay sau khi phát hiện cost tracking sai
(còn 2 việc nóng chưa làm — xem Open Items).

## What Was Done

### 1. Empower Chat Assistant (commit `12d98ae`) — feature lớn
Mở rộng AI assistant từ 6 tool đọc → **12 tool**, giữ nguyên kiến trúc tool-use loop:
- `app/ai/sql_tool.py` (mới): **SQL chỉ-đọc** trên 6 view tạo-runtime
  (`v_findings/v_m15/v_m15a/v_m16/v_bcct/v_company_scores`). Guard nhiều lớp: chỉ 1 câu
  SELECT/WITH, allowlist view + **denylist cứng `users`/`ai_settings`/`sqlite_master`**
  (vì `query_only` chỉ chặn ghi không chặn đọc secret), `PRAGMA query_only=ON`, LIMIT
  cap, progress-handler timeout. Chạy qua chính `db: Session` của request (dùng chung
  DB với test in-memory + prod WAL).
- Tool mới: `query_sql`, `export_excel` (link tải file mặc định), `export_query_excel`
  (Excel tùy biến từ SQL, nhúng câu SQL để truy nguồn — endpoint `GET /api/chat/export-query`),
  `propose_check_run` (đề xuất → nút xác nhận → `POST /api/chat/run-checks` enqueue job),
  `generate_report`, `explain_score`.
- Frontend (`_ai_sidebar.html`/`sidebar.js`/`sidebar.css`): **dải cảnh báo hallucination
  luôn-hiện**, footer nhắc kiểm chứng, chip tải Excel, nút xác nhận hành động.
- Verify Playwright 8/8 trên prod.

### 2. Sửa AI giải thích điểm SAI → đúng rate-based (`2cd471d`,`bc83e12`,`6ce96a0`,`2631618`)
- **Gốc:** chính system prompt dạy mô hình cộng-dồn sai ("🔴10·🟡3·🔵1" trông như để
  cộng) + ghi số bịa. AI trả "250×10=2500".
- Viết lại mục chấm điểm trong prompt (rate-based, bão hoà, max_raw) + thêm tool
  **`explain_score`** trả breakdown thật → AI giải thích từ số liệu (`168 = round(1000×
  31.94/190)`, C4.3 kịch khung…). Thêm `n_rules`.
- **Thẻ breakdown điểm trên trang DN** (`company_detail.html`): hiện công thức + bảng
  từng bài + badge "kịch khung" + mẫu số, lấy từ `CompanyYearScore.breakdown` thật.
- Đổi từ ngữ toàn hệ: **"phép"→"bài kiểm tra"**, bỏ "trần/bão hoà"→"kịch khung",
  "độ phơi nhiễm"→"quy mô dữ liệu".

### 3. Fix count + format + recompute (`0eb13d8`,`afd4006`,`5c6c7fd`)
- `search_findings`/`query_raw_data`: `count` = TỔNG thật (func.count), không phải số
  dòng đã cắt (trước báo 20 khi thật 93).
- `_format_cell`: số nhỏ (định mức ~0.0018) không bị làm tròn về "0.00" (dùng `:.6g`).
- **Recompute điểm ngay khi đổi status finding** (`recompute_company_year`) — trước đây
  bấm "Loại trừ" điểm không đổi (chỉ tính lúc run_checks).

### 4. Sự cố demo + chuyển provider (`cc39228`,`11bbcdd`)
- Demo lỗi: Gemini phát tool-call song song (index=None) → accumulator gộp args
  `{...}{...}` → 400. Fix accumulator (khoá index→id) + `_clean_tool_args` + `run_tool`
  raw_decode khoan dung.
- Thêm **402 vào fallback** → OpenRouter hết tiền tự rớt sang Gemini.
- Cuối cùng chốt: **primary OpenRouter/Claude Sonnet 4, fallback Gemini free**.

### Hạ tầng
- Xử sự cố **đĩa tinsu đầy 100%** chặn deploy (runner ENOSPC): xoá 6 backup DB cũ,
  `docker image prune -a` (chỉ 3.7MB — image đều gắn container), `builder prune`
  (~1.6GB) → đủ cho runner sống + build. Rebuild các lần sau thay image cũ → giờ còn
  ~8G trống.
- Khởi động lại GitHub runner qua **screen** (service systemd cần sudo password).

## Decisions Made

- **SQL tool = view chỉ-đọc thay vì tool aggregate tham-số-hoá** (user chọn). Bảo mật
  bằng allowlist view + denylist bảng nhạy cảm + query_only — vì câu hỏi cán bộ rất mở.
- **propose_check_run KHÔNG tự chạy** — AI đề xuất, cán bộ bấm nút (giữ "thẩm quyền con
  người"). Job qua hệ `jobs` sẵn có (tránh GOTCHA `run_checks(only=…)` xoá combo).
- **Views tạo runtime idempotent, KHÔNG migration** — để dev/test(in-memory)/prod giống nhau.
- **§4 tổ hợp mềm hoá** thành "minh hoạ/giả thuyết" — sau khi review thấy 4 combo là
  giả thuyết chuyên gia chưa kiểm chứng, 2 cặp hơi trùng tín hiệu, 1 cặp (C2.1+C4.3)
  thực ra là cờ chất-lượng-dữ-liệu không phải hành vi.
- **Chuyển Claude→Gemini→Claude+Gemini-fallback** theo diễn biến (bug Gemini → Claude;
  hết tiền OpenRouter → Gemini; user đưa key OpenRouter mới → Claude primary + Gemini fb).
- **Recompute 1-năm từ findings hiện có** (không chạy lại check) — đúng cho đổi-status,
  không đụng findings/combo.

## What Didn't Work / Hớ

- **`docker image prune -a` chỉ thu 3.7MB** — tưởng giải phóng 47GB nhưng mọi image đều
  đang gắn container. Cái cứu thật là `builder prune` (~1.6GB) + rebuild thay image cũ.
- **Lệnh nhiều dòng qua `ssh.exe` bị nuốt newline** → screen runner ban đầu không chạy.
  Phải dùng `;` phân tách trên một dòng.
- **Copy DB chỉ file `.sqlite` (WAL mode) → mất dữ liệu trong `-wal`** → bản copy verify
  thiếu cột `industry` (migration mới nằm trong WAL). Phải copy cả `-wal/-shm` hoặc đọc
  qua SQLAlchemy. (Đã ghi memory.)
- **Cost dashboard SAI ~3×** (phát hiện cuối session): `cost.py` PRICING thiếu key
  `anthropic/claude-sonnet-4` → rơi vào DEFAULT `$1/$5` thay vì `$3/$15` → báo $2.2 trong
  khi tiền thật ~$6.7. User đốt ~$5 (key bạn) + ~$2 (key mới). **CHƯA FIX.**
- **Gemini free-tier 429** khi 1 lượt gọi nhiều tool (6 calls) — không phải bug, là quota.

## Open Items (NÓNG — user /handoff giữa chừng)

1. **Fix `app/ai/cost.py` PRICING** — thêm entry thật cho claude-sonnet-4 / haiku-4-5 /
   opus-4-7 + gemini-2.5-flash/lite/pro. Hiện dashboard đếm thiếu ~3×, không tin được.
2. **Quyết provider để khỏi đốt tiền:** đề xuất **đảo Gemini lên primary (free, đã chạy
   sạch sau fix streaming), Claude làm fallback**. User chọn Claude-primary trước đó
   nhưng gõ /handoff sau khi biết cost — cần hỏi lại.
3. **Combo +20 điểm tổ hợp — review logic** ("note lại, quyết sau"). Flat +20 cho mọi
   combo (kể cả combo chất-lượng-dữ-liệu) + magnitude tuỳ tiện + nhị phân thô. Hướng:
   badge không-tính-điểm / có-cấp-có-trần / trọng số khác nhau.
4. **Runner + đĩa tinsu** — runner screen có thể đã chết (kiểm tra trước push); đĩa 97%
   cần dọn cho an toàn lâu dài (sudo password → cần user).
5. **Combo §4 / combos.py chưa đồng bộ** — doc đã mềm hoá nhưng `combos.py` descriptions
   vẫn giọng khẳng định ("tạo định mức ảo", "cố tình"). Nếu muốn nhất quán thì sửa code
   (nhưng CLAUDE.md: sửa catalog đề án trước).
