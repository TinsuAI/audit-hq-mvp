# 2026-07-31 — KTSTQ 5 năm: grounding → grill → ADR #23 → 8 ticket

## What Was Done

Chuẩn bị cho demo 2026-08-01 (công ty sắp bị KTSTQ, phạm vi = ngày Kiểm tra − 5 năm,
không trùng trọn kỳ quyết toán). KHÔNG đụng code sản phẩm — toàn bộ output là
docs + tickets.

1. **Grounding (đọc code + census dữ liệu thật):**
   - Xác nhận defect: `ingest.py:330` BỎ dòng BCCT ngoài cửa sổ kỳ ngay lúc nạp;
     `bcct_other_year` chỉ in CLI (`run_all.py:74`) — web UI không thấy; sửa cửa sổ
     sau nạp (`companies.py:1356`) không phục hồi được, phải re-upload.
   - Setting kỳ hiện per `(DN, năm)` (`company_periods`), không có default mức DN.
   - Census cấu trúc **475 file / 976 sheet** (11 DN, script scratchpad, chỉ in
     aggregate — không in tên file/DN thật): BCCT 22 vân tay, family ECUS chi tiết
     phủ 10/11 DN; m15a family chuẩn 8 DN + biến thể 55 sheet DN03/DN04; đuôi dài
     one-off per-DN. Kết luận: template toàn cục cho family lớn + saved map per-DN
     (đã có) cho đuôi. Caveat: phân loại theo từ khoá ≥2 hit, số đuôi là ước lượng.
   - Phương án 4 ticket: `.ai/notes/2026-07-31-ktstq-5-nam-template-ky-quyet-toan.md`.
2. **Research pháp lý** (background agent, nguồn Công báo PDF):
   `.ai/notes/2026-07-31-research-ky-ke-toan-bcqt-ktstq.md` — 4 kết luận chính:
   kỳ BCQT = năm tài chính, hạn 90 ngày (giữ nguyên qua kh.32 Đ.1 TT 121/2025, hiệu
   lực 01/02/2026); KHÔNG có quy ước tên "năm tài chính 20XX" chính thức (định danh
   pháp lý = khoảng ngày); niên độ lệch phải 12 tháng tròn từ đầu quý (Đ.12 Luật KT
   2015; quy tắc gộp kỳ đầu/cuối ĐÃ SỬA từ 01/01/2025 bởi Luật 56/2024); KTSTQ 5 năm
   neo NGÀY ĐĂNG KÝ TỜ KHAI (kh.3 Đ.77 Luật HQ 2014); mẫu 01/QĐKT để "Phạm vi kiểm
   tra" là dòng trống tự do.
3. **Grill 9 câu** (Q1–Q9, user chốt từng câu) → **ADR #23** trong `.ai/DECISIONS.md`.
4. **8 ticket GitHub #47–#54** theo format repo (Xây gì / Tiêu chí nghiệm thu /
   Chặn bởi): BCCT-1..3 (#47→#48→#49), NIENDO-1 (#50), TPL-1..2 (#51→#52),
   KTSTQ-1..2 (#53, #54 chặn bởi #48+#53). 4 điểm vào song song: #47, #50, #51, #53.

## Decisions Made (chi tiết ở ADR #23 — đây là tóm tắt)

- **T1:** `declaration_lines.period_year` = nhãn nạp/provenance; tư cách thuộc kỳ
  tính lúc QUERY qua MỘT helper `declaration_scope` (dated → cửa sổ, undated → nhãn).
  Trùng chéo nhãn / thiếu phủ / chồng lấn cửa sổ: CẢNH BÁO, không dedup, không chặn.
  Sửa cửa sổ bump `data_version` cùng transaction. HAI cổng nghiệm thu: query-swap
  delta 0 trên 3 pilot; fresh re-ingest delta chỉ gồm dòng trước đây bị drop.
- **T2:** `companies.fiscal_start_month` ∈ {1,4,7,10} default 1; nhãn năm = NĂM BẮT
  ĐẦU (vì luật không có quy ước tên → nhãn là khoá nội bộ); mọi màn hiện nhãn kỳ
  ≠ dương lịch in kèm khoảng ngày. Chuỗi suy: manual > header > fiscal default >
  dương lịch, header lệch default → cảnh báo.
- **T3:** template builtin sống trong CODE (yêu cầu tương lai ĐÃ CHỐT: sau này quản
  lý qua UI); evidence source mới `builtin-template` rank giữa header-matched và
  officer-confirmed → khớp = TỰ QUA cổng review; map officer per-DN thắng template.
- **T4:** phạm vi KTSTQ là VIEW — `companies.audit_decision_date` nullable, cửa sổ
  `[D−5y, D]` tính không lưu, tag render-time; `registry.requires` +
  `check_runs.skip_reason` để hết "0 finding = sạch giả" (defect chung, không riêng
  kỳ đuôi). Tương lai: bảng `audit_engagements`, chưa build.

## What Didn't Work

- **vbpl.vn từ chối kết nối, thuvienphapluat.vn trả 403** cho agent — research phải
  tải PDF Công báo từ chinhphu.vn và quét text trực tiếp. Lần sau tra luật: đi
  thẳng Công báo, đừng mất thời gian với hai nguồn kia.
- Census v1 dùng `tail -60` nuốt mất phần đầu output — phải ghi ra file rồi đọc.
  Phân loại slot bằng keyword ≥2 hit quá lỏng (m15 chỉ match 12 sheet, khả năng
  nhiều sheet M15 thật bị nhãn khác thắng điểm) — đủ cho kết luận cấu trúc, KHÔNG
  dùng số này làm phân loại sạch.

## Open Items

- **Demo 2026-08-01:** không ticket nào ship kịp. Demo bằng đồ có sẵn: flow review
  cấu trúc lạ (detect → xác nhận cột → map lưu tái dùng chéo năm), sửa cửa sổ kỳ
  tay; câu hỏi 5 năm trả lời bằng phương án màn độ phủ. **TRÁNH làm live:** nạp
  BCCT dương lịch vào DN đã set kỳ lệch (drop im lặng trên web UI — còn nguyên tới
  khi #48 ship).
- Implement #47/#50/#51/#53 (song song được), mỗi vé một session mới `/tdd` + `/rev`.
- Việc treo từ các session trước KHÔNG đổi (xem các block STATUS cũ): lỗi
  `run_checks` xoá `status`/`notes` cán bộ khi re-run (chưa có vé), punch-list 7/8,
  ADR nhãn sổ, PR #43, disk server 97%.
