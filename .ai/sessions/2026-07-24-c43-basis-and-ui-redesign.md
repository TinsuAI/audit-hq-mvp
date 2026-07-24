# 2026-07-24 — C4.3 số nhân (P-07) + tầm nhìn UI redesign

Phiên nối tiếp phân tích pilot. Ba mạch: đối chiếu localhost, chốt hướng C4.3, và nhận yêu cầu UI redesign.

## What Was Done

- **Đối chiếu pilot vs localhost.** localhost đã ingest 3 DN pilot qua pipeline thật: cid7=PILOT_002,
  cid8=PILOT_006 (2 kỳ), cid9/10=PILOT_004_EPE/GC (tách hai công ty). Chạy lại `run_checks` trên
  **bản copy** DB (không đụng instance) → **0 drift per-check** cả 4 công ty.
- **Sửa cấu hình kỳ 002.** 002 thiếu `company_periods` (ingest trước C1 → year-filter cũ, mất 3.014
  dòng tờ khai 2026). Re-ingest bằng code hiện tại (tự nhận cửa sổ tài chính) → giữ đủ 11.115 dòng.
  **279→48 finding, risk 65→7**; C1.1 181→2, C1.4 50→0. Backup DB trước khi ghi.
- **C4.3 export vs intake (P-07).** Đo cả hai cơ sở trên mọi DN (script validate: export tái tạo đúng
  finding đang lưu). Dữ liệu thật: 2.371→2.063 (−13%). Mổ nhóm tăng, mổ cột form M15a, hỏi Fable.
- **đề án §4.1 sửa** số nhân `xuất_khẩu_M15a`→`sản_lượng_sản_xuất_M15a` + bậc mâu thuẫn vật lý; ADR ở
  `audit-hq/.ai/DECISIONS.md`; html rebuild. **Chưa commit.**
- **UI redesign brief** `.ai/features/2026-07-24-parse-review-per-test-ux/brief.md` (3 workstream).

## Decisions Made

- **C4.3 số nhân = sản lượng sản xuất, không phải xuất khẩu** (ADR đề án 2026-07-24). Lý do quyết định:
  **đề án tự mâu thuẫn** — §4.1 ghi xuất khẩu nhưng kịch bản demo §6.3 dùng "sản xuất 1.000 cái". Sửa
  để hợp nhất, không phải đổi ngữ nghĩa.
- **Gộp trần vật lý vào C4.3** (bậc leo thang), không tách check riêng đợt này (Fable: tách ở ngưỡng
  1,0 đẻ 2.097 finding trùng trên 006-2025; C2 trình bày quy mô lớn mới là việc lớn chưa xong).
- **Số nhân đúng = cột (6) "Input from Production"**, loại (7) "Return from Customer". Với biểu chuẩn
  chỉ có cột gộp thì dùng cột đó (giả định trả lại ≈ 0).
- **Fable review (chạy model Fable):** khuyên đổi intake + gộp trần, không giữ export. Tự verify số của tôi.

## What Didn't Work — chuỗi đính chính (quan trọng)

Hướng C4.3 đảo **ba lần** trước khi chốt — ghi đủ để phiên sau không lặp:

1. **Turn 1 tôi nói "intake giảm nhiễu".** Quá mạnh. Đo ra hỗn hợp: DEMO2 2025 **tăng +158**.
2. **DEMO2 +158 là giả** — dữ liệu fixture seed tay (số 12/28/20 lặp y hệt). Loại khỏi benchmark.
   → **Bài học: benchmark của đề án phải loại DN demo.**
3. **Tôi gán nhầm 006 +42 là "cạnh biên actual=0 / mã vắng mặt M15".** SAI — chỉ 7/78 mã là loại đó,
   và **C4.1 đã bắt hết 7**. 71 mã còn lại là over-consumption THẬT (52 vượt trần vật lý) mà export
   basis đang GIẤU. Nên intake không "dời nhiễu" — nó lộ tín hiệu thật.
4. **`notes/13` P-07 cũ ghi "2.814→4.449 mã khớp".** Metric đó (±5% hai chiều, trên pilot scratch) **không
   khái quát** — đo finding-count trên dữ liệu sản phẩm thì 006-2024 lại TĂNG. Đã đính chính trong notes/13.
5. **Giả định "intake = sản lượng" chỉ đúng có điều kiện.** Form định nghĩa "nhập trong kỳ" = sản xuất
   (6) + khách trả lại (7). Biểu chuẩn (HONG_AN/002/006) gộp một cột; chỉ 004 tách. 004 xác nhận (7)=0.

## Cơ chế parse đã mổ (cho WS1 của UI redesign)

Quyết định cột hai tầng: (1) chọn sheet theo **nội dung** (`profile_sheets`, ngưỡng); (2) map cột —
form chuẩn dùng **vị trí cố định** (không kiểm nội dung, **rủi ro đọc nhầm âm thầm**), form lạ dùng
`resolve_m15a` đọc **công thức cân đối form tự khai** validate ≥98%. Layout lạ có công thức → xử vững;
không có + không giống chuẩn → không nạp (an toàn).

## Open Items

- **`/implement` C4.3** ở `c4_norm.py`: đổi số nhân, tách (6)/(7) trong `resolve_m15a`, skip mã
  không-nguồn, bậc mâu thuẫn vật lý. Chạy lại 6 demo + 3 pilot, giải thích từng finding đổi. Ngưỡng
  trần (đề xuất ≥2×) chốt ở họp cán bộ.
- **Commit** thay đổi đề án (cross-repo, chưa commit) + notes pilot.
- **UI redesign:** mở `/grill-with-docs` cho WS1 (brief đã sẵn).
- 002/006 báo cáo docx vẫn chưa viết (từ phiên trước).
- Fixture demo cid 1-6 sẽ đổi số khi sửa C4.3 → cần re-seed cho khớp kịch bản 5 phút.
