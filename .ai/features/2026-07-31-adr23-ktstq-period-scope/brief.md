# E2E proof — ADR #23: cửa sổ kỳ · niên độ DN · template builtin · phạm vi KTSTQ 5 năm

Ảnh chứng cho 8 vé: BCCT-1..3 (#47–#49), NIENDO-1 (#50), TPL-1..2 (#51–#52),
KTSTQ-1..2 (#53–#54).

## Chạy lại

Server throwaway riêng, **KHÔNG đụng DB live hay cổng 8200 của user**. Kill theo PID,
không bao giờ `pkill -f uvicorn`.

```bash
SCRATCH=<thư mục tạm>            # DB + log của lượt chụp
WORKDB="$SCRATCH/smoke.sqlite"; rm -f "$WORKDB" "$WORKDB"-wal "$WORKDB"-shm
DATABASE_URL="sqlite:///$WORKDB" .venv/bin/alembic upgrade head

setsid env DATABASE_URL="sqlite:///$WORKDB" \
    .venv/bin/uvicorn app.main:app --port 8331 --no-access-log \
    > "$SCRATCH/smoke-server.log" 2>&1 &
echo $! > "$SCRATCH/smoke.pid"

M_BASE=http://127.0.0.1:8331 DATABASE_URL="sqlite:///$WORKDB" PYTHONPATH=. \
    .venv/bin/python .ai/features/2026-07-31-adr23-ktstq-period-scope/ui_smoke.py

kill "$(cat "$SCRATCH/smoke.pid")"
```

`ui_smoke.py` tự seed rồi tự dọn (user `shot_ktstq` + DN `DEMO_KTSTQ`), chạy nhiều
lần không để lại rác.

## Doanh nghiệp seed

`DEMO_KTSTQ` — niên độ **tháng 4** (`fiscal_start_month=4`), ngày quyết định kiểm tra
**01/08/2026** → cửa sổ kiểm tra `01/08/2021 – 01/08/2026`. Kỳ 2025 = 01/04/2025 –
31/03/2026; kỳ 2024 sửa tay thành kỳ chuyển tiếp 18 tháng (chồng lấn 2025); kỳ 2026
đọc cửa sổ **dương lịch** từ tiêu đề file (lệch niên độ DN); kỳ 2021 cắt đầu.

Tờ khai kỳ 2025: 9 dòng trong kỳ (thiếu hẳn quý 10–12/2025), 1 dòng ngoài cửa sổ,
1 dòng không ngày, 1 cặp trùng khoá chéo nhãn 2025/2026. M15 chỉ có ở kỳ 2025 → ba
kiểm tra cần M15a/M16 ghi `skip_reason`.

## Ảnh

| # | Ảnh | Chứng minh |
|---|-----|-----------|
| 01 | `01_banner_do_phu_bcct.png` | Banner độ phủ mỗi kỳ (#48): **1 dòng ngoài cửa sổ · 1 dòng không ngày · 2 dòng trùng khoá chéo nhãn** — mọi dòng đều đã lưu, không dòng nào bị bỏ. Nhãn kỳ ≠ dương lịch in kèm khoảng ngày `01/04/2025 – 31/03/2026` (#50). Kỳ sửa tay nhắc **Chạy kiểm tra**, không còn nhắc nạp lại dữ liệu (#49) |
| 02 | `02_khoang_thieu_va_chong_lan.png` | Khoảng thiếu nêu ĐÚNG `01/10/2025 – 31/12/2025` + cảnh báo cửa sổ kỳ 2025 chồng lấn kỳ 2024 (#49) — cảnh báo, không chặn |
| 03 | `03_cai_dat_nien_do_va_ngay_kiem_tra.png` | Cài đặt DN: chọn niên độ đúng 4 mốc đầu quý (#50) + ngày quyết định kiểm tra sau thông quan (#54), kèm giải thích đây chỉ là cách hiển thị |
| 04 | `04_badge_khop_mau_va_canh_bao_nien_do.png` | Badge **📐 Khớp mẫu: Mẫu 15 TT39 — bố cục chuẩn**, cột mang nguồn "Khớp mẫu có sẵn" và trạng thái **Đã kiểm** → cổng review tự qua (#51/#52). Đồng thời cảnh báo cửa sổ kỳ 2026 (dương lịch, đọc từ tiêu đề file) **lệch niên độ** DN — hệ thống không tự chọn hộ (#50) |
| 05 | `05_kiem_tra_chua_chay_thieu_nguon.png` | Khối "**3 kiểm tra chưa chạy được**… không có phát hiện nào ở đây KHÔNG có nghĩa là sạch", liệt kê C2.2/C2.4/C4.3 kèm nguồn còn thiếu (#53) |
| 06 | `06_phat_hien_ngoai_pham_vi.png` | Phát hiện kỳ 2021 gắn nhãn render-time **⏳ Ngoài phạm vi kiểm tra — hết thời hiệu, chỉ để tham khảo**; phát hiện VẪN hiển thị, không lưu state phạm vi nào trên dòng (#54) |
| 07 | `07_man_do_phu_pham_vi_5_nam.png` | Màn `/scope`: nói cả **khoảng ngày** (`01/08/2021 – 01/08/2026`) lẫn **danh sách kỳ** (2021…2026); mỗi kỳ phân loại cắt đầu · trọn trong phạm vi · cắt đuôi · chưa có BCQT; kỳ 2025 hiện **3 đã chạy · 3 chờ dữ liệu** đọc từ `skip_reason` (#53+#54) |

## Giới hạn bộ ảnh

- Dữ liệu là seed minh hoạ, không phải file BCQT thật — chứng minh **render + luật
  hiển thị**, không chứng minh chất lượng parse trên file thật. Vế parse có cổng
  riêng: hai cổng nghiệm thu delta finding trên 3 pilot (xem session log).
- Ảnh 04 dùng `data_files` seed sẵn (không có file trên đĩa) nên phải chụp TRƯỚC
  trang tài liệu — `sync_data_files` xoá dòng registry mà file đã không còn.
- Template builtin hiện chỉ nối vào đường parse **m15 / m15a**. Hai họ BCCT trong
  census chưa nối (adapter BCCT chưa có provenance) — xem "Còn mở" ở session log.
