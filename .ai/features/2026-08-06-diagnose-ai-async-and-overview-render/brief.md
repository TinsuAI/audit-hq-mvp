# `/diagnose-ai` chạy ở hàng đợi + tổng quan AI không đổ JSON thô

Nhánh `fix/diagnose-ai-async-and-overview-render`. Hai việc rời nhau, cùng một phiên.

## Cách chạy lại

Server throwaway, DB riêng trong scratchpad. **Không đụng cổng 8200 của user**, và
không bao giờ `pkill -f uvicorn` — nó giết luôn tiến trình của user; dừng theo PID.

```
WORKDB=<scratchpad>/shots.sqlite
DATABASE_URL="sqlite:///$WORKDB" setsid \
    .venv/bin/uvicorn app.main:app --port 8334 --no-access-log > /tmp/uv.log 2>&1 &
echo $! > /tmp/uv.pid

M_BASE=http://127.0.0.1:8334 DATABASE_URL="sqlite:///$WORKDB" PYTHONPATH=. \
    .venv/bin/python .ai/features/2026-08-06-diagnose-ai-async-and-overview-render/ui_smoke.py

kill -TERM -$(cat /tmp/uv.pid)
```

Sửa template xong **phải khởi động lại server rồi mới chụp** — uvicorn chạy không
`--reload`, tiến trình cũ giữ template cũ.

Script tự dọn: `_purge()` xoá `shot_aidiag` + `DEMO_AI_DIAG` trong khối `finally`.

## Ảnh chứng minh gì, và KHÔNG chứng minh gì

| Ảnh | Chứng minh |
|---|---|
| `01_form_tai_len_bcct_nhieu_file` | Ô BCCT ghi "(chọn được nhiều file)" + câu dặn *không gộp tay*. Đây là PR #78 đã merge, chụp kèm vì cùng một đường đi của cán bộ. |
| `02_job_chan_doan_khoi_rieng` | Chẩn đoán AI thành **khối riêng** trên trang công việc, giữ ngắt đoạn. Trước đây văn bản này bị ép vào một ô bảng dưới nhãn thô `ai_result`. Nhãn loại job là "AI chẩn đoán cấu trúc file", và link cuối trang về **Tài liệu** (chẩn đoán hay kết luận "ghim trang tính rồi nạp lại", việc đó làm ở đó). |
| `03_tong_quan_parse_duoc_bon_muc` | Chuỗi JSON có **xuống dòng thật bên trong một chuỗi** nay parse được → bốn mục (nhận định · điểm nóng · đề xuất). Trước bản vá, đúng chuỗi này trả `None`. |
| `04_tong_quan_khong_do_json_tho` | Parse trượt → "Chưa viết được nhận định — AI trả về sai định dạng", trỏ vào nút 🔄 Tạo lại, và nói rõ bảng số liệu vẫn tính từ dữ liệu. **Không còn khối JSON giữa trang.** |
| `05_tong_quan_nguyen_van_trong_details` | Nguyên văn AI trả về vẫn giữ, trong `<details>` gập sẵn — mất lỗi thì hết chẩn đoán được, nhưng nó không phải thứ đập vào mắt cán bộ. |

**Ảnh KHÔNG chứng minh việc chạy ở hàng đợi.** "Request trả ngay thay vì chờ 120 giây
rồi 524" là tính chất **thời gian**, ảnh tĩnh không nói được. Chỗ chứng minh là
`tests/test_diagnose_ai_job.py::test_diagnose_ai_does_not_call_the_llm_inside_the_request`
— nó đỏ trước bản vá. Cố tình **không** seed job trạng thái `queued` để chụp: server
này chạy worker AI thật, nó nhặt job đó chạy mất trước khi kịp chụp.

## Dữ liệu trong ảnh: cái gì thật, cái gì bịa

- **Bịa:** pháp nhân `DEMO_AI_DIAG`, 7 finding (4 × C1.1, 3 × C2.1), văn bản chẩn đoán
  ở job. Mã NPL và tên DN là bịa, không phải dữ liệu DN thật.
- **Thật:** bảng số liệu trong panel tổng quan gọi `build_stats()` THẬT trên finding đã
  seed — không dán số vào `aggregate_json`. Và `sections_json` chạy `parse_sections()`
  + `finalize_sections()` THẬT trên chuỗi model, không dán dict bốn mục vào. Vì thế ảnh
  03 chứng minh được **parse**, không chỉ render.
- **Không gọi LLM.** `api_key` seed là chuỗi giả, chỉ để `ai_enabled` bật cho nút
  🔄 Tạo lại hiện ra.

## Ghi chú kỹ thuật

`RAW_BAD` trong script là JSON **cụt giữa chừng** (mô phỏng chạm `max_tokens`) —
`parse_sections` trả `None` và **đúng là phải trả None**: không đoán phần thiếu. Đó là
lý do ảnh 04/05 dùng ca này thay vì ca xuống dòng: ca xuống dòng nay đã parse được.

Còn mở: chưa đọc được `content` thật của dòng tổng quan trên prod (DB dev có 0 dòng
`check_overviews`), nên giả thuyết "ký tự điều khiển thô" là cơ chế **tái hiện được
trong phòng thí nghiệm**, chưa phải chẩn đoán đã xác nhận cho đúng dòng đã chụp màn
hình 06/08. Lớp thứ hai (không đổ JSON ra màn) đúng bất kể nguyên nhân.
