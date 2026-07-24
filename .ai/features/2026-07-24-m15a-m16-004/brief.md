# M15a mở rộng + M16 định mức thực tế cho 004 (ADR #15)

## Vấn đề
004 (EPE + GC) ghi Mẫu 15a với bố cục lệch chuẩn: mã ở cột 2, tách cột con, số biểu
KHÔNG ổn định giữa DN. Đường cột cố định trượt → `select_sheet` báo `SheetNotFound` →
`content_slots` không nhận m15a → **004 không nạp M15a** → C4.3/C1.4 không chạy. Mẫu 16
của 004 có 2 cột định mức (kỹ thuật c7, thực tế c8); adapter đọc c7 (sai — kiểm tra hải
quan dùng thực tế).

## Cách làm
- **M15a bố cục mở rộng** (`extended_layout.resolve_m15a`): suy map cột từ dòng đánh số,
  **cổng đẳng thức cân đối** (khớp ≥98% dòng) + **xác định `export_qty` theo NHÃN** cột
  ("xuất khẩu"/"Export this year"), phải là số hạng TRỪ trong đẳng thức, và DUY NHẤT.
  Không xác thực được → trả None → không nạp (thà thiếu hơn sai). Khai triển nhãn gộp
  `(8ab)`=8a+8b (KHÔNG gồm 8c) cho sổ GC.
- **Discovery**: `content_slots` thử thêm đường mở rộng cho m15a.
- **M16**: chọn cột định mức theo nhãn "thực tế/Actual" khi có cả cột "kỹ thuật" — DN
  một cột ĐM giữ nguyên (6 DN whitelist bất biến).
- **Bằng chứng có lưu** (badge, không hộp đen): `DataFile.parse_layout` + `parse_detail`
  (migration `f5a6b7c8d9e0`). Badge ở trang Tài liệu + note ở trang Dữ liệu gốc: bố cục,
  đẳng thức khớp N/N, nhãn cột export/ĐM đã chọn.

## Kết quả (dữ liệu thật)
- 004 EPE: M15a 43 dòng (đẳng thức 43/43, export ← "Export this year"), M16 664 dòng
  (ĐM thực tế c8). Phát hiện 111→98, **C4.3 fire (8)**.
- 004 GC: M15a 2 dòng (2/2), M16 216 dòng. **C1.4 fire (2)** sau khi sửa kỳ tay
  (header GC ghi sai FY2024, dữ liệu là FY2025 — override 2025-04-01..2026-03-31).
- 6 DN whitelist: harness nạp mới **419 → 419 y hệt** (từng DN) — trung tính, không regression.
- Full suite 583 pass, ruff clean.

## Screenshots
- `01_documents_badges.png` — trang Tài liệu 004 EPE: badge "bố cục mở rộng · đẳng thức
  43/43" (M15/M15a) + "ĐM thực tế · cột 8" (M16).
- `02_data_m15a_parse_note.png` — trang Dữ liệu gốc M15a: note đẳng thức + cột xuất khẩu
  chọn theo nhãn.
