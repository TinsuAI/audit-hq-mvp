# Thiết kế lại luồng tải lên → nạp dữ liệu

Spec: issue #80 · ADR #24 và #25 · vé #81–#93, #95 · lỗi trang lỗi tách riêng ở #94 → PR #96.

## Ảnh E2E

Sinh bằng `ui_smoke.py` cạnh file này (`.venv/bin/python .ai/features/2026-08-07-upload-ingest-redesign/ui_smoke.py`).
Chạy thật: seed DB throwaway + file Excel thật trên đĩa, uvicorn ở cổng tự do, đăng nhập
bằng cookie ký sẵn, kill server theo PID group. **Dữ liệu bịa**, không phải doanh nghiệp thật.

Ảnh chứng minh phần RENDER và luồng, không chứng minh adapter đọc đúng cột từ file thật.

Xem `screenshots/README.md` cho chú thích từng ảnh.

## Điều ảnh KHÔNG cho thấy

- Ca một workbook phục vụ ba biểu hiện một dòng ba nhãn: `sync_data_files` đối chiếu lại
  với đĩa ở mỗi lần vào trang và phân loại file theo tên/thư mục, nên bản ghi m15a/m16
  do seed tạo bị prune. Ca này có test ở `tests/test_period_files.py`.
- Ca trích xuất 164,6 giây của file 71,3MB: file thật không có trong môi trường chụp.
