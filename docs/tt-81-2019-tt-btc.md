---
so_van_ban: 81/2019/TT-BTC
ten_ngan: Quản lý rủi ro hải quan
co_quan_ban_hanh: Bộ Tài chính
nguoi_ky: Vũ Thị Mai (Thứ trưởng)
ngay_ban_hanh: 2019-11-15
ngay_hieu_luc: 2020-01-01
status: active
sua_doi_boi:
  - so_van_ban: 06/2024/TT-BTC
    ngay_hieu_luc: 2024-03-15
    note: "Chưa fetch chi tiết — cần ingest sau"
pham_vi:
  - quan ly rui ro hai quan
  - phan loai tuan thu doanh nghiep
  - phan loai rui ro nguoi khai
  - kiem tra hai quan
key_articles:
  - Điều 10: 5 mức tuân thủ pháp luật
  - Điều 11: Tiêu chí Mức 1 (DN ưu tiên)
  - Điều 12: Cơ chế đánh giá tự động hàng ngày
  - Điều 14: 9 hạng rủi ro người khai hải quan
  - Phụ lục I: Danh mục chỉ số thông tin quản lý rủi ro
  - Phụ lục II-V: Tiêu chí cụ thể Mức 2-5
url_nguon:
  - https://thuvienphapluat.vn/van-ban/Xuat-nhap-khau/Thong-tu-81-2019-TT-BTC-quan-ly-rui-ro-trong-hoat-dong-nghiep-vu-hai-quan-429474.aspx
  - https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=198479
ngay_fetch: 2026-05-26
relevance_audit_hq: critical
---

# Thông tư 81/2019/TT-BTC — Quản lý rủi ro trong hoạt động nghiệp vụ hải quan

## Vì sao văn bản này quan trọng với Audit-HQ

TT 81/2019 là khung pháp lý **chính thức của TCHQ** về phân loại rủi ro doanh nghiệp xuất nhập khẩu. Audit-HQ là công cụ **bổ sung** (phát hiện rủi ro dữ liệu BCQT) — không thay thế, không được nhầm với hệ thống phân loại chính thức.

**Hệ quả thiết kế:**
- KHÔNG dùng nhãn "Mức 1-5" cho điểm Audit-HQ → sẽ nhầm với TT 81.
- KHÔNG tự xếp DN vào hạng rủi ro 1-9 → đó là thẩm quyền TCHQ tự động đánh giá lúc 00:00 hàng ngày (Điều 12).
- Output Audit-HQ là **input bổ sung** cho cán bộ HQ, không phải kết luận tuân thủ.

---

## Điều 10 — Phân loại 5 Mức tuân thủ pháp luật

Người khai hải quan được phân loại 5 mức:

| Mức | Tên | Cơ chế xác định |
|---|---|---|
| **Mức 1** | Doanh nghiệp ưu tiên | Công nhận chính thức (Điều 11, theo NĐ 08/2015 Điều 10 + TT 72/2015) |
| **Mức 2** | Tuân thủ cao | Không vi phạm 365 ngày, tổng phạt ≤1% tổng tờ khai |
| **Mức 3** | Tuân thủ trung bình | Không vi phạm 365 ngày, tổng phạt ≤1% (mục III) + 2% (mục IV) |
| **Mức 4** | Tuân thủ thấp | Không vi phạm buôn lậu 365 ngày, tổng phạt ≤2% (mục III) + 3% (mục IV) |
| **Mức 5** | Không tuân thủ | Có vi phạm ngoài phạm vi Mức 4 |

**Điểm cốt lõi**: Tiêu chí phân loại 5 Mức dựa trên **vi phạm pháp luật thực tế** (xử phạt hành chính, buôn lậu, trốn thuế, nợ thuế) — KHÔNG dựa trên chất lượng dữ liệu BCQT/M15/M16. Đây là khác biệt then chốt với Audit-HQ.

## Điều 11 — Tiêu chí Mức 1 (DN ưu tiên)

Áp dụng quy định tại **Điều 10 NĐ 08/2015/NĐ-CP** và **TT 72/2015/TT-BTC** (chế độ DN ưu tiên).

→ Cần fetch NĐ 08/2015 + TT 72/2015 để biết chi tiết.

## Điều 12 — Đánh giá tự động hàng ngày

> "Hệ thống công nghệ thông tin tự động đánh giá vào 00 giờ hàng ngày... trên cơ sở tích hợp, xử lý dữ liệu thông tin hải quan theo các tiêu chí..."

**Không công bố công thức toán học** trong văn bản. Hệ thống tự đánh giá dựa trên tiêu chí Phụ lục II-V.

## Điều 14 — 9 Hạng mức rủi ro người khai hải quan

| Hạng | Mô tả |
|---|---|
| 1 | Doanh nghiệp ưu tiên |
| 2 | Rủi ro rất thấp |
| 3 | Rủi ro thấp |
| 4 | Rủi ro trung bình |
| 5 | Rủi ro cao |
| 6 | Rủi ro rất cao |
| 7-9 | DN mới / hoạt động < 365 ngày (3 hạng phân biệt theo ngành nghề) |

**Khác Mức tuân thủ**: 9 hạng rủi ro là **kết quả phân loại tổng hợp** (Mức tuân thủ + ngành nghề + lịch sử XNK + cảnh báo nội bộ). Mức tuân thủ là 1 đầu vào.

## Phụ lục I — Danh mục chỉ số thông tin quản lý rủi ro

**Không có chỉ số/score cụ thể**. Đây là *danh mục thông tin* mà hệ thống thu thập:
- Thông tin DN (mã số thuế, ngành nghề, lịch sử, quan hệ liên kết)
- Thông tin hàng hóa, phương tiện, người tham gia
- Tổ chức liên quan (đối tác, kho, vận tải)

→ Không có "công thức tính điểm rủi ro" công bố. Phù hợp WCO Compendium: framework, không phải formula.

## Phụ lục II-V — Tiêu chí định lượng Mức 2-5

Có thresholds **rate-based**:
- "Tổng số lần xử phạt ≤ 1% / 2% / 3% tổng số tờ khai trong 365 ngày"
- "Không nợ thuế quá 90 ngày"
- "Không bị xử phạt buôn lậu/trốn thuế trong 365 ngày"

→ Pattern: rate (phạt / tờ khai) + absolute carve-out (buôn lậu zero tolerance). Pattern này **đồng bộ với khuyến nghị WCO/AEO** (rate-based + binary gates cho vi phạm nghiêm trọng).

---

## Áp dụng vào Audit-HQ scoring (decisions ghi trong feature brief 2026-05-26)

1. **Đặt tên neutral**, KHÔNG dùng "Mức N":
   - 0-100: Dữ liệu nhất quán 🟢
   - 101-300: Có chênh lệch nhỏ 🟢
   - 301-600: Cần rà soát 🟡
   - 601-850: Có dấu hiệu bất thường 🟠
   - 851-1000: Bất thường nghiêm trọng 🔴

2. **Disclaimer trong UI footer** (mỗi trang có score):
   > "Đây là chỉ số rủi ro dữ liệu BCQT do Audit-HQ tính từ phát hiện chênh lệch giữa các báo cáo. KHÔNG phải đánh giá tuân thủ pháp luật theo Thông tư 81/2019/TT-BTC. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan."

3. **Công thức rate-based** (đồng bộ pattern Phụ lục II-V của TT 81):
   - `rule_rate = min(1, findings / denominator)` cho mỗi check
   - Severity weight 10/3/1 nhân vào
   - Rescale 0-1000

## Câu hỏi mở cho session sau

- **TT 06/2024**: TT 81/2019 đã được sửa đổi bởi TT 06/2024/TT-BTC (hiệu lực 2024-03-15). Cần fetch để biết thay đổi gì về tiêu chí Mức 2-5.
- **TT 72/2015** + **NĐ 08/2015 Đ10**: Chi tiết chế độ DN ưu tiên (Mức 1) — cần fetch nếu Audit-HQ mở rộng phân tích DN ưu tiên.
- **Quyết định 2218/QĐ-TCHQ**: Quy trình 5 bước quản lý rủi ro — fetch để hiểu workflow nội bộ TCHQ.

---

*Fetched 2026-05-26 từ thuvienphapluat.vn. Body có thể không đầy đủ 100% — khi cần điều khoản chính xác, đọc trực tiếp văn bản gốc tại URL nguồn.*
