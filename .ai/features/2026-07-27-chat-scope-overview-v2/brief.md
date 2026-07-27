# E2E proof — chat gắn doanh nghiệp (ADR #20) + tổng quan AI v2 (ADR #21)

Ảnh chứng cho 9 vé: CHAT-1..4 (#28–#31) và TQ-1..5 (#32–#36).

## Chạy lại

Server throwaway riêng, **KHÔNG đụng DB live hay cổng 8200 của user**. Kill theo PID,
không bao giờ `pkill -f uvicorn`.

```bash
SCRATCH=<thư mục tạm>            # DB + log của lượt chụp
WORKDB="$SCRATCH/smoke.sqlite"; rm -f "$WORKDB"
DATABASE_URL="sqlite:///$WORKDB" .venv/bin/alembic upgrade head

setsid env DATABASE_URL="sqlite:///$WORKDB" \
    .venv/bin/uvicorn app.main:app --port 8327 --no-access-log \
    > "$SCRATCH/smoke-server.log" 2>&1 &
echo $! > "$SCRATCH/smoke.pid"

M_BASE=http://127.0.0.1:8327 DATABASE_URL="sqlite:///$WORKDB" PYTHONPATH=. \
    .venv/bin/python .ai/features/2026-07-27-chat-scope-overview-v2/ui_smoke.py

kill "$(cat "$SCRATCH/smoke.pid")"
```

`ui_smoke.py` tự seed rồi tự dọn (user `shot_tq` + `DEMO_CHAT_A`/`DEMO_CHAT_B`), nên
chạy nhiều lần không để lại rác.

## Ảnh

| # | Ảnh | Chứng minh |
|---|-----|-----------|
| 01 | `01_chat_nhom_theo_doanh_nghiep.png` | `/chat` nhóm theo doanh nghiệp: header section CHÍNH LÀ doanh nghiệp, số cuộc mỗi nhóm, "Chưa gán doanh nghiệp" xếp cuối, công tắc "Chỉ của tôi" BẬT sẵn |
| 02 | `02_doi_doanh_nghiep_cua_cuoc.png` | Hộp thoại đổi doanh nghiệp của một cuộc — ô chọn chỉ đổ doanh nghiệp cán bộ có quyền |
| 03 | `03_sidebar_chip_pham_vi_va_loc.png` | Sidebar giữ danh sách phẳng + chip "Cuộc mới gắn:" ở header + bộ lọc doanh nghiệp trong lịch sử |
| 04 | `04_bao_lech_pham_vi.png` | Lệch phạm vi: cuộc gắn An Phát trong khi trang đang xem Bình Minh → báo rõ + nút "Mở cuộc trò chuyện mới cho Công ty CP Bình Minh (Demo)". Không tự tách cuộc, không tự đổi nhãn |
| 05 | `05_bang_so_lieu_va_nhan_dinh.png` | Bảng số liệu 4 ô (tổng + mức · số mã + tỉ trọng top-5 + phủ 80% · phân vị & chiều lệch · so kỳ trước) và nhận định bốn mục với điểm nóng là LINK sang trang chi tiết mã. Nút "✨ Tạo tổng quan còn thiếu" ở thanh công cụ |
| 06 | `06_dang_viet_nhan_dinh.png` | Sinh chạy nền: **bảng số liệu đã hiện đầy đủ** trong khi chỗ nhận định còn "⏳ Đang viết nhận định… (công việc #1)" kèm link job — đúng tính chất "bảng hiện ngay, không chờ LLM" |
| 07 | `07_badge_can_doi_chieu.png` | Badge "⚠️ Cần đối chiếu số liệu" khi nhận định có con số (137) không khớp chuỗi nào trong bảng; kiểm tra 2 phát hiện (<10) nên mục phân bố bị bỏ; miễn trừ trách nhiệm là text tĩnh |
| 08 | `08_admin_ai_tach_theo_loai.png` | `/admin/ai` đọc sổ `ai_usage`: số lời gọi tách theo loại (trò chuyện / tổng quan) |

## Lỗi thật ảnh chụp bắt được

`.ai-scope-bar` và `.ai-scope-mismatch` khai `display: flex` — cùng specificity với
`[hidden]` và khai báo SAU nên thắng, khiến khối báo lệch phạm vi hiện **rỗng trên mọi
trang** dù JS đã ẩn. Đúng loại lỗi codebase đã ghi chú sẵn ở `.ai-history-panel`.
Đã thêm `[hidden] { display: none }` cho cả hai; ảnh 04 là bản sau khi sửa.

## Giới hạn của bộ ảnh

- Dữ liệu là **seed minh hoạ**, không phải dữ liệu pilot: các con số trong bảng và
  nhận định chỉ để chứng minh cách render, không có ý nghĩa nghiệp vụ.
- Nhận định trong ảnh 05/07 là JSON **dựng sẵn**, không gọi LLM thật — bộ ảnh chứng
  minh phần render + hậu kiểm, không chứng minh chất lượng model.
- Ô phân vị hiện **tên trường thô** (`M15_REPURPOSE`) vì khoá lấy thẳng từ `details`.
  Đọc được nhưng chưa có nhãn tiếng Việt; để lại làm việc riêng.
