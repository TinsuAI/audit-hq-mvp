# Đối chiếu độ tin cậy adapter với ADR #18 (WS1)

Phạm vi: `app/adapters/m15.py`, `app/adapters/m15a.py`, `app/adapters/bcct.py`,
`app/adapters/extended_layout.py`, `app/adapters/evidence.py`, `app/checks/registry.py`,
`app/pipeline/saved_map.py`, `app/pipeline/data_files.py`, `app/routes/companies.py`,
`app/templates/document_review.html`, `app/templates/company_documents.html`. Đối chiếu với
`.ai/DECISIONS.md` mục 18 (dòng 300–377) và Revision WS2/WS3 cùng ADR.

## (a) Tin cậy đến từ nhãn bằng chứng mỗi cột, không từ đẳng thức cân đối

**CONFIRMED.**

- `app/adapters/evidence.py:24-29` định nghĩa bốn nguồn xếp hạng đúng thứ tự ADR quy định
  (`officer-confirmed` > `header-matched` · `balance-checked` > `position-only`).
- Đường CHUẨN (`evidence_m15_standard`, `evidence.py:179-208`; `evidence_m15a_standard`,
  `evidence.py:211-238`) tính `header-matched` bằng cách quét TIÊU ĐỀ tại đúng vị trí cột
  (`_header_matched`, `evidence.py:117-119`), và chỉ dùng đẳng thức (`_balance_ok`,
  `evidence.py:122-137`) làm phương án dự phòng khi tiêu đề không khớp.
- Đường MỞ RỘNG (`evidence_m15_extended`/`evidence_m15a_extended`, `evidence.py:263-275`) gán
  toàn bộ cột là `balance-checked` — đúng như ADR mô tả ("mọi cột là balance-checked, đẳng thức
  không phân biệt hai cột cùng dấu").
- Điểm mấu chốt của ADR — đẳng thức khớp KHÔNG đủ cho cột dùng riêng lẻ — được cài đặt đúng ở
  `app/checks/registry.py:454-467` (`review_state`): cột tiêu thụ riêng lẻ (`INDIVIDUAL`) mà
  nguồn tốt nhất chỉ là `balance-checked` → vẫn bị đẩy về `needs_review`, không được coi là đã
  xác thực. Đối chiếu từng chữ với `.ai/DECISIONS.md:327-329` — khớp nguyên văn quy tắc.

## (b) Mọi vai trò cột có nguồn bằng chứng ghi lại cho cán bộ, không fallback âm thầm về vị trí

**CONFIRMED cho slot m15/m15a/m16 · DIVERGES cho slot bcct (nhưng có tự khai phạm vi trong ADR).**

- `CHECK_COLUMNS` (`app/checks/registry.py:377-413`) khai đủ cột số của m15/m15a/m16 mà 8 check
  Tầng D đọc; `review_state` (`registry.py:454-467`) buộc MỌI cột được tiêu thụ mà rơi về
  `position-only` phải thành `needs_review` — không có đường nào để một cột `position-only` được
  tiêu thụ mà vẫn hiện `verified`.
- `app/adapters/bcct.py:56-70`: cột đọc thuần theo `_COL` cố định, `BcctFile` (`bcct.py:45-51`)
  KHÔNG có trường `provenance`/evidence nào. Không badge, không cổng review nào áp cho slot này.
  Đây là fallback vị trí ÂM THẦM đúng nghĩa đen. Tuy nhiên `registry.py:374-376` tự khai rõ:
  "cột BCCT/HS (C3.1/C3.2/C6.1) chưa mô hình hoá ở WS1" — nên đây không phải lệch so với ADR,
  mà là giới hạn phạm vi ADR tự thừa nhận, chưa làm.
- Tín hiệu bị bỏ sót (không phải "silent fallback" nhưng là chỗ hổng): `SavedColumnMap` lưu
  `confirmed_by`/`confirmed_at` (`app/models/saved_column_map.py:43-46`) nhưng KHÔNG template
  nào (`document_review.html`, `company_documents.html`, `company_data.html`) render hai trường
  này — cán bộ không thấy ai đã xác nhận map hay xác nhận lúc nào, dù dữ liệu đã có sẵn.

## (c) Cột gộp Mẫu 15a (sản xuất + trả lại) xử lý như MỘT cột theo form chuẩn; file lệch chuẩn được PHÁT HIỆN, không bị đọc sai

**CONFIRMED.**

- Form chuẩn (HONG_AN/002/006) chỉ có MỘT cột "Lượng sản phẩm nhập trong kỳ" = sản xuất + trả lại
  gộp — đúng như `app/adapters/m15a.py:63-74` (`_COL["intake_qty"] = 5`, một cột duy nhất) và ghi
  chú `evidence.py:86-94` (`_M15A_HDR_KW["intake_qty"]`, không tách nhãn con).
- File lệch chuẩn (004 tách "Input from Production"/"Return from Customer" thành hai cột riêng)
  làm `select_sheet` trượt (không đủ 2 nhãn đúng VỊ TRÍ, `sheet_select.py:91-97`) → rơi sang
  `select_extended_m15a` (`m15a.py:88-95`). Ở đường này, `resolve_m15a`
  (`extended_layout.py:338-387`) tái dựng `intake_qty` bằng CỘNG các cột số hạng dương còn lại
  sau khi trừ cột `opening` (`extended_layout.py:373-381`: `intake_qty = [c for c in plus_cols if
  c not in opening]`) — tức gộp lại đúng sản xuất + trả lại thành một cột, khớp ngữ nghĩa form
  chuẩn, KHÔNG đọc nhầm.
- Đã dò một kịch bản rủi ro hơn: nếu file lệch chuẩn tình cờ vẫn đạt ngưỡng điểm của đường CHUẨN
  (mã hàng + tồn đầu vẫn đúng vị trí, các cột sau bị dịch vì chèn cột) thì `_COL` cố định sẽ đọc
  lệch `repurpose_qty`/`export_qty`/`other_out_qty`/`closing_qty`. Kịch bản này VẪN bị chặn: cột
  `export_qty` khi đó không khớp tiêu đề tại đúng vị trí (`_header_matched` thất bại) và đẳng thức
  `_balance_ok` cũng thất bại (cột lệch không còn cộng đúng), nên `export_qty` rơi về
  `position-only` → `review_state` (`registry.py:463-464`) trả `needs_review` vì `export_qty` là
  cột tiêu thụ RIÊNG LẺ của C1.4/C4.3 (`registry.py:381,406`). Cổng review kích, không lọt.

## (d) Khi adapter không chắc, HỎI cán bộ thay vì đoán và tiến hành

**CONFIRMED về hành vi thực tế — nhưng đây là bản MẠNH HƠN chữ ADR ghi, và ADR/UI copy tự mâu
thuẫn với chính hành vi này.**

- Hành vi thật: `documents_ingest_year` (`app/routes/companies.py:571-593`) chạy `dry_run=True`
  trước, tính `review_gate`, và nếu `should_stop_for_review(gate)` → **REDIRECT NGAY**
  (`companies.py:585-593`), KHÔNG chạm tới đoạn `run_ingest(...)` commit thật (`companies.py:596`
  trở xuống). File dừng ở trạng thái `analyzed` (chưa ghi dòng Tầng 1) cho tới khi cán bộ tự sửa
  hoặc xác nhận map qua `POST .../documents/file/{id}/review`
  (`app/routes/companies.py:1149-1163`, `document_review.html`). Đây đúng là "hỏi cán bộ trước
  khi tiến hành", không phải đoán.
- **Mâu thuẫn nội bộ:** chính comment ngay phía trên đoạn redirect
  (`companies.py:573-574`: *"cảnh báo, không chặn — check vẫn chạy sau khi parsed"*) và banner UI
  (`app/templates/company_documents.html:117`: *"Cảnh báo, KHÔNG chặn: bấm ⤵️ Nạp dữ liệu để tiếp
  tục; kiểm tra vẫn chạy và phát hiện sẽ kèm cờ 'dựa trên cột chưa xác nhận'"*) đều khẳng định mô
  hình WARN-NOT-BLOCK — đúng như bullet gốc của ADR #18 (`.ai/DECISIONS.md:332`: *"CẢNH BÁO, KHÔNG
  CHẶN: check vẫn chạy, finding vẫn hiện, kèm cờ 'dựa trên cột chưa xác nhận'"*). Nhưng code ba
  dòng dưới comment đó (`companies.py:585-593`) làm điều NGƯỢC LẠI: chặn hẳn, không commit, không
  có finding nào được tạo (vì chưa có dòng Tầng 1). Bấm nút "⤵️ Nạp dữ liệu" như banner chỉ dẫn sẽ
  CHẠY LẠI đúng route này, gặp lại cùng `needs_review`, và bị redirect lần nữa — không có đường
  nào từ nút đó dẫn tới commit. Nút thực sự tiến hành được là "🔎 Xem & xác nhận cột" dẫn tới màn
  `document_review.html`, một route KHÁC.
- Hệ quả: bullet "CẢNH BÁO, KHÔNG CHẶN" của ADR #18 gốc (`DECISIONS.md:332`) đã bị **SỬA NGẦM**
  bởi quyết định vòng đời file trong CHÍNH ADR đó (`DECISIONS.md:346-353`, "DỪNG chờ cán bộ bấm
  khi needs_review") mà không có dòng nào đánh dấu là SỬA — hai bullet cùng một ADR nói hai điều
  khác nhau, và code theo bullet sau. UI copy (`company_documents.html:117`) chưa cập nhật theo,
  nên đang mô tả sai hành vi thật cho cán bộ đọc.

## Hậu quả cụ thể của điểm lệch (d)

Không tìm thấy đường nào khiến MỘT SỐ SAI thật sự lọt tới check, vì cổng chặn cứng (không phải
cảnh báo) — mạnh hơn yêu cầu tối thiểu của ADR. Hậu quả thực tế nằm ở tính đúng-sai của TÀI LIỆU,
không phải dữ liệu:
- Cờ finding `"dựa trên cột chưa xác nhận"` mà ADR (`DECISIONS.md:332`) và UI
  (`company_documents.html:117`) đều hứa hẹn KHÔNG TỒN TẠI trong schema: `Finding`
  (`app/models/finding.py:11-39`) không có cột nào biểu diễn nó, và về nguyên lý không thể có —
  vì `needs_review` chặn commit nên check không có dòng Tầng 1 để chạy, tức KHÔNG BAO GIỜ có
  finding "dựa trên cột chưa xác nhận" được sinh ra. Đây là nhãn/tính năng đã hứa nhưng KHÔNG THỂ
  sinh (dead promise, không phải dead code — code liên quan còn chưa được viết).
- Cán bộ đọc banner sẽ hiểu sai quy trình: tưởng bấm "Nạp dữ liệu" là chấp nhận rủi ro rồi đi
  tiếp, thực tế phải qua màn xác nhận cột riêng. Rủi ro vận hành (thao tác sai kỳ vọng), không
  phải rủi ro số liệu.

## Chiều ngược — tín hiệu tính mà cán bộ không thấy / nhãn không thể sinh

- **Không thấy:** `SavedColumnMap.confirmed_by` / `confirmed_at`
  (`app/models/saved_column_map.py:43-46`) được ghi mỗi lần xác nhận map nhưng không render ở bất
  kỳ template nào đã kiểm (`document_review.html`, `company_documents.html`, `company_data.html`)
  — không tìm thấy trong toàn bộ `app/templates/`.
- **Không thể sinh (dead promise):** cờ finding `"dựa trên cột chưa xác nhận"` — xem mục Hậu quả
  ở trên; hứa ở cả ADR gốc lẫn UI copy, không có cột lưu trữ, và về logic không đường nào tạo ra
  nó vì gate chặn trước khi có dòng để check đọc.
- Không phát hiện nhãn bằng chứng nào (`officer-confirmed`/`header-matched`/`balance-checked`/
  `position-only`) là dead branch thật — cả bốn đều có đường sinh ra được và đều được test qua dữ
  liệu (grep `resolve_officer_confirmed`, `_header_matched`, `_balance_ok`, và nhánh else cuối mỗi
  hàm `evidence_*`).

## Tổng kết bốn nhận định

| # | Nhận định | Kết luận |
|---|---|---|
| (a) | Tin cậy từ nhãn bằng chứng mỗi cột, không từ đẳng thức | CONFIRMED |
| (b) | Mọi vai trò cột có nguồn bằng chứng, không fallback âm thầm | CONFIRMED (m15/m15a/m16) · bcct ngoài phạm vi ADR (tự khai) |
| (c) | Cột gộp 15a xử lý đúng, file lệch bị phát hiện | CONFIRMED |
| (d) | Không chắc → hỏi cán bộ, không đoán | CONFIRMED hành vi (mạnh hơn ADR yêu cầu) · DIVERGES ở lời văn ADR/UI ("cảnh báo không chặn" + cờ finding hứa nhưng không tồn tại) |
