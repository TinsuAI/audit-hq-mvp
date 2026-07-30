# Tóm tắt ưu tiên — đợt chạy song song 2026-07-30

Nguồn: 11 file `.ai/notes/2026-07-30-*.md`, `.ai/sessions/2026-07-30-parallel-burst.md`, 16 nhánh git commit đêm nay (`git log main..<nhánh>`). Không lặp lại nội dung từng note — chỉ nêu phần đổi quyết định. Muốn chi tiết, mở đúng file được trích.

**Chưa nhánh nào chạy `pytest tests` đầy đủ.** Chưa nhánh nào được push hay merge. Đọc mục "Việc lập trình đã có nhánh" với giả định này.

---

## 1. Lỗi mất dữ liệu / sai số ra khách

Xếp theo hệ quả, nặng nhất trước.

1. **Trạng thái cán bộ (Xác nhận/Loại trừ/Đã ghi chú) và ghi chú tay biến mất mỗi lần chạy lại kiểm tra.** `app/pipeline/run_checks.py:78-104` xoá cứng toàn bộ `Finding` rồi insert lại, không `Finding()` nào truyền `status=` → mọi trạng thái cán bộ đã nhập bị đưa về `"new"` trong im lặng. Đã xảy ra thật (STATUS.md:125-141, đợt 004: 74→65 finding). Thiết kế sửa đã có đủ 4 vé T1-T4 (`finding_reviews` bảng riêng, khoá tự nhiên `(company_id, period_year, check_code, subject_key, book)`), **chưa cài đặt, chưa có vé mở**. — `2026-07-30-trang-thai-da-soat-finding.md`. Việc sửa `status`/`notes` hiện có bằng đúng khuôn mẫu này là quyết định RIÊNG (đụng `scoring.py:76,100,166`), chưa nằm trong 4 vé.

2. **Thang điểm rủi ro 0–1000 đọc ngược ý nghĩa dữ liệu.** PILOT_006/2025: 9.963 phát hiện nghiêm trọng (91% mẫu số) nhưng điểm hiển thị **54/1000** → nhãn "Có chênh lệch nhỏ". Nguyên nhân cấu trúc: mẫu số `max_raw=190` giả định 17 kiểm tra cùng kịch trần — raw cao nhất từng đo mới 12,9% trần. Đang hiển thị thật ở 3 màn cán bộ + báo cáo AI + chat AI + Excel export, dù STATUS.md 2026-07-29 đã ra chỉ thị ẩn. — `2026-07-30-adr-thang-diem-rui-ro.md` mục 5.0 (danh sách đầy đủ vị trí lộ, có file:line).

3. **`company.risk_score` là cache có thể lệch — khác điểm hiển thị ở màn khác, ngay bây giờ.** Không phải cùng vấn đề với mục 2 (đó là chọn thang nào; đây là một cột cache có thể cũ). `run_checks.py:187-192` và `recompute.py:53-59` gán `company.risk_score = max(...)` tại thời điểm gọi — không có bảo vệ "chỉ tăng"; điểm 1 năm giảm khi cán bộ "Loại trừ" một phát hiện hoặc khi thêm 1 check vào catalog. Trang danh sách DN đã né đúng (đọc `MAX(company_year_scores.score)` tươi, `companies.py:192-200`), nhưng **Excel export** (`app/pipeline/export.py:85`), **AI SQL tool** (`app/ai/sql_tool.py:99-105`), và **AI chat tools** (`app/ai/tools.py:394,548,567,733`) vẫn đọc cột cache cũ → cùng một DN có thể hiện điểm khác nhau ở màn danh sách so với export/chat. 1 nhánh đã sửa 1 điểm (`fix/ai-tools-stale-risk-score`); nhánh dự kiến sửa các điểm còn lại (`fix/stale-risk-score-remaining-sites`) **chưa có commit nào** (kiểm bằng `git log main..fix/stale-risk-score-remaining-sites` — rỗng). — `adr-thang-diem-rui-ro.md` mục 2.4(b), `2026-07-30-backlog-tu-code.md` dòng mục "Cao" đầu tiên.

4. **Tổng quan AI báo "Đã xong" nhưng nội dung rỗng.** `request_timeout_s` không chặn được lời gọi (đợt thật 2026-07-27, gọi chạy 817 giây) + trạng thái `done` dù `content` rỗng. 2 nhánh sửa: `fix/ai-overview-timeout-and-empty-content`, `fix/overview-staleness-format` (bỏ sót định dạng cũ thiếu `aggregate_json` khi xét "đã cũ") — chưa merge.

5. **Tổng quan AI từng viết ra số không có trong dữ liệu** (PILOT_006/2024 C1.7/C3.2: model tự bịa 77,7% và 80,1%). Có cờ hậu kiểm "cần xem lại" chặn trước khi tới khách, nhưng cơ chế gốc (mục 4) vẫn sống trên prod.

6. **Nhãn kỹ thuật thô (`DIFF_PCT`, `M15_REPURPOSE`...) hiện ra thay vì tiếng Việt** ở bảng phân vị. Nhánh `fix/percentile-keys-guardrail` sửa, **chưa merge** — bug còn sống trên prod hôm nay.

7. **Đếm "N kiểm tra cùng gắn cờ mã X" phóng đại do các kiểm tra không độc lập.** `C1.3 ⊆ C1.1` (gần cấu trúc), `C1.7 ⊆ C1.6` (đúng trên toàn bộ dữ liệu đo được, chưa từng thấy trường hợp phá vỡ). Ở PILOT_006/2025: "3.215 mã bị ≥2 kiểm tra" thực chỉ còn **947 mã có ≥2 tín hiệu độc lập** sau khi trừ hấp thụ. Trùng đúng vấn đề đã ghi trong memory dự án `checks-khong-doc-lap-khi-dem-gop` — note đêm nay đo thêm bằng số thật và đưa thuật toán tính động (`app/checks/overlap.py`, chưa viết) thay vì bảng cố định. — `2026-07-30-chong-lan-giua-cac-kiem-tra.md`.

8. **Mã số thuế thật và tên pháp nhân thật nằm trong file đã git-tracked.** MST thật ở `tests/test_adapters.py:25,38,58`, `tests/test_anonymize.py` (nhiều dòng); tên pháp nhân thật ở `tests/test_anonymize.py:44`; MST pilot 004 (`0901051747`, đã ẩn danh trên prod thành `6944313927`) còn nguyên ở `.ai/DECISIONS.md:545`, `.ai/GLOSSARY.md:94`, `.ai/STATUS.md` (nhiều dòng); tên mã DN thật (`HONG_AN`/`GROWATT`/`KIM_LONG`/...) ở ~60 vị trí code thay vì `PILOT_xxx`. Không có file dữ liệu bị commit — chỉ chuỗi định danh. 1 nhánh (`chore/scrub-real-identifiers-from-tests`) sửa fixture test, **không đụng lịch sử git, không đụng ~60 vị trí code, không đụng docs**.

9. **7 route cấu hình AI (`/admin/ai/*`) không có test nào** — nếu handler lưu sai/không persist, chỉ lộ khi admin bấm nút thật trên UI. Đã có tiền lệ: key OpenRouter 401 mà `test_connection()` báo OK giả (memory dự án `openrouter-key-401`). — `backlog-tu-code.md`.

10. **`app_settings.py:97,178` nuốt lỗi parse `risk_tier_uppers`/`combos_enabled` không log**, cùng dạng tại `app/checks/scoring.py:55` (`except Exception` quanh `_active_tiers()`, âm thầm trả về `TIERS` hard-code cũ). Admin đổi ngưỡng rủi ro hoặc bật/tắt combo trong `/admin`, hệ thống báo lưu thành công; nếu giá trị lưu hỏng, đọc lại âm thầm rơi về mặc định cũ — admin không có cách nào biết cấu hình của mình không được áp dụng. Chưa có nhánh sửa. — `backlog-tu-code.md` dòng 27-28.

---

## 2. Quyết định chờ owner

1. **Thang điểm rủi ro 0–1000** — giữ / đổi mẫu số theo giá trị lớn nhất quan sát (đã loại, xem bằng chứng số PILOT_002 nhảy 53→125 khi sửa dữ liệu DN khác) / hiệu chỉnh 5 ngưỡng hạng (đã loại, không tự dời theo khi catalog đổi) / bỏ hẳn dùng số đếm theo mức độ (khuyến nghị). Kèm 5 câu hỏi mở: khoá sắp xếp thay `-score`, giữ hay tắt `/admin/risk-tiers`, giữ `_explain_score` cho ai, nhu cầu xếp hạng đa-DN có thật không, có gộp chung quyết định với mục 7 dưới không. — `adr-thang-diem-rui-ro.md` mục 6.

2. **Ngưỡng C1.6/C1.7.** C1.6 không có ngưỡng độ lớn, đo cho thấy không có sàn số lượng nào (kể cả 1.000 chiếc, rất cao so với median 49) đưa số phát hiện xuống mức xử lý được mà không phải là ngưỡng tuỳ ý (không neo luật). C1.7 ngưỡng % có cơ sở nghiệp vụ nhưng phân bố dồn cực gần 100% nên dời ngưỡng 10%→99% chỉ giảm 19%. Cần owner: (a) có đặt sàn vận hành cho C1.6 không và giá trị bao nhiêu, (b) có thêm dải severity trên 25% cho C1.7 không, (c) xác minh nghiệp vụ PILOT_006 có thật tăng hơn gấp đôi 2024→2025 (21%→55%) hay là lỗi nạp dữ liệu — đo lường không trả lời được câu này. — `2026-07-30-hieu-chinh-nguong-c16-c17.md`.

3. **MST/tên pháp nhân thật trong lịch sử git.** Xoá khỏi HEAD dễ (đã có nhánh scrub một phần); xoá khỏi lịch sử là thao tác phá huỷ (rewrite history), cần owner chốt có làm hay không trước khi bất kỳ ai động vào.

4. **Bật lại combo.** Khuyến nghị: giữ TẮT, sửa `c4_norm.py` theo P-07 trước (số nhân = sản lượng, hiện vẫn dùng xuất khẩu — **chưa sửa**, `fix/c43-multiplier-p07` đang chờ merge), đo lại, rồi mới bật. 3/4 combo hiện cho giao=0 vì vế C2.1/C2.3/C5.1 rỗng tuyệt đối trên toàn bộ dữ liệu pilot — không phụ thuộc P-07. Cờ bật/tắt là toàn cục (không tách riêng từng combo). — `2026-07-30-bat-lai-combo.md`.

5. **Cách hiển thị chồng lấn.** Ẩn hẳn dòng finding bị hấp thụ (VD C1.7 khi đã có C1.6) khỏi danh sách chi tiết, hay chỉ đổi số đếm ở tiêu đề? Khuyến nghị giữ nguyên dòng chi tiết (C1.6/C1.7 mang ý nghĩa khác nhau dù bao hàm). Có nên thêm ngưỡng cỡ mẫu tối thiểu cho containment (2 bao hàm chỉ đúng ở PILOT_004/2025 mẫu n=4-5, sai ở 006 quần thể lớn hơn) hay cứ tin đúng-là-đúng theo từng kỳ? — `chong-lan-giua-cac-kiem-tra.md` câu hỏi mở #1, #4.

6. **Check động X.1 — chặn trước, cần quyền đọc DB prod.** X.1 trong DB local (`status=draft`, lọc tồn kho âm) **không phải** bản X.1 mà STATUS.md 2026-07-27 mô tả đang `published` trên prod (`cross_table_match` trùng C1.1). Không thể quyết publish/unpublish/xoá cho tới khi đọc được `sql_snippet` thật trên prod — việc đầu tiên không phụ thuộc phương án nào. — `2026-07-30-xu-ly-check-x1.md`.

7. **Cột "Rủi ro nghiệp vụ" ở trang danh mục công khai `/danh-muc-kiem-tra`** quy kết hành vi ("thổi phồng định mức để điều tiết...") thay vì mô tả trung tính — đã có nhánh gỡ (`fix/catalog-public-risk-column`), cần owner xác nhận hướng gỡ hẳn (không phải sửa câu chữ) là đúng.

8. **Số lượng kiểm tra MVP: tài liệu ghi 16, code có 17.** `CLAUDE.md`/`AGENTS.md` ghi "16 kiểm tra MVP", nhưng `app/checks/registry.py` đăng ký đúng 17 `CheckSpec`. Xác nhận độc lập ở `2026-07-30-developer-onboarding-map.md` dòng 479-484 và `2026-07-30-kich-ban-demo-5-phut.md` dòng 157-158 ("nếu bị hỏi trực tiếp trong demo, trả lời 17"). Owner cần xác nhận: phạm vi đã mở rộng có chủ đích hay tài liệu chưa cập nhật.

---

## 3. Việc lập trình đã có nhánh

18 nhánh có commit thật (16 dưới tên dự kiến + 2 nhánh `perf/*` chốt tên muộn hơn), tất cả tại `main` + N
commit, **chưa nhánh nào chạy `pytest tests` đầy đủ hay `ruff check` toàn repo**. Một nhánh thứ 17,
`perf/company-periods-year-source`, còn **uncommitted** trong worktree `agent-ab8e92fa2797a6c73`
(sửa `app/routes/companies.py` + test mới) — chưa sẵn sàng xét gộp.

**Điểm nóng migration:** `feat/finding-reviews-t1` (migration `cdbe8615226a`) và `perf/book-partial-indexes`
(migration `d4e5f6a7b8c9`) cùng khai `down_revision=c5d6e7f8a9b0` (head hiện tại của `main`) — gộp cả hai
nguyên trạng sẽ tạo **2 alembic head** cùng lúc. Rechain đơn giản là đủ: gộp `feat/finding-reviews-t1`
trước, rồi sửa `down_revision` trong `d4e5f6a7b8c9_book_partial_indexes.py` thành `cdbe8615226a`, chạy
`alembic upgrade head`/`alembic heads` xác nhận đúng 1 head trước khi gộp `perf/book-partial-indexes`.
Nguồn thứ tự gộp 7 nhánh commit sớm nhất (không xung đột dòng, xác nhận bằng `git merge-tree --write-tree`):
`fix/percentile-keys-guardrail` → `docs/punchlist-7-glossary` → `fix/c43-multiplier-p07` (cùng đụng
`GLOSSARY.md`, không chồng dòng) → `feat/findings-export-xlsx` (độc lập) → `fix/ai-overview-timeout-and-empty-content`
→ `fix/overview-staleness-format` (chạy lại `tests/test_ws3_overview.py` sau khi gộp cả hai) →
`fix/xstar-book-label` (đụng `.ai/STATUS.md`, nơi `main` có sửa uncommitted — **phải commit/stash
STATUS.md trên main trước**). — `2026-07-30-ke-hoach-gop-nhanh.md`.

| Nhánh | Nội dung | Commit |
|---|---|---|
| `feat/finding-reviews-t1` | Model + migration `FindingReview` — vé T1 của mục 1.1 | `d933a83` |
| `perf/book-partial-indexes` | 3 index partial `WHERE book IS NOT NULL` trên norms/nvl_balances/sp_balances (mục 4) | `08db8cd` |
| `fix/ai-tools-stale-risk-score` | 1/5 điểm đọc cache rủi ro cũ (mục 1.3) | `4c38f90` |
| `fix/stale-risk-score-remaining-sites` | Dự kiến sửa 4 điểm còn lại — **0 commit, rỗng** | — |
| `fix/c43-multiplier-p07` | C4.3 đổi số nhân theo P-07 (chặn quyết định combo, mục 2.4) | `4bf5333` |
| `fix/ai-overview-timeout-and-empty-content` | Timeout + content rỗng báo done (mục 1.4) | `12c7fb9` |
| `fix/overview-staleness-format` | Bỏ sót định dạng cũ khi xét "đã cũ" (mục 1.4) | `c14334d` |
| `fix/percentile-keys-guardrail` | Gỡ khoá chết `PERCENTILE_KEYS["C3.2"]` + test khoá (mục 1.6) | `ef80f32`, `58d9383` |
| `fix/xstar-book-label` | Check X.\* mang `book` theo dòng (punch-list 8) | `2f8bbfa` |
| `fix/catalog-public-risk-column` | Gỡ cột "Rủi ro nghiệp vụ" khỏi trang công khai (mục 2.7) | `03817b0` |
| `feat/findings-export-xlsx` | Thêm cột `book`/`period`/`evidence_refs` vào export | `852773b` |
| `chore/scrub-real-identifiers-from-tests` | Xoá MST/tên thật khỏi fixture test — chỉ HEAD, không đụng lịch sử (mục 1.8) | `e3420ef` |
| `fix/ai-error-logging-no-raw-body` | Ngừng log nguyên văn lỗi API (có thể chứa lại prompt) | `c080506` |
| `fix/wording-pass-remainder` | Hoàn tất PR #43 — từ vựng trang cấu hình AI admin | `c640b93` |
| `test/traceability-invariant` | Test khoá truy nguồn cho cả 17 kiểm tra built-in | `a7dab04` |
| `docs/fix-stale-claims` | Sửa 4 khẳng định lỗi thời trong BACKLOG/GLOSSARY/AGENTS/README | `8737939` |
| `docs/punchlist-7-glossary` | Sửa lệch GLOSSARY/ADR #19 | `9eca1d5` |

---

## 4. Đã đo, chưa cần làm gì

- **Không có N+1 theo dòng finding** ở `company_detail`. Điểm chậm thật là 2 truy vấn quét sai bảng (vô điều kiện quét `norms`/`declaration_lines` để trả lời câu company_periods đã có sẵn) — 47-70% thời gian query. 2 sửa an toàn-ngay đã định vị chính xác: đổi nguồn `data_years` sang `company_periods` (đang ở `perf/company-periods-year-source`, **chưa commit**) và thêm 3 index partial `WHERE book IS NOT NULL` (đã commit, `perf/book-partial-indexes`, `08db8cd`) — nhưng **không khẩn**, không phải bug, chỉ là tối ưu chưa lên lịch. — `2026-07-30-hieu-nang-man-phat-hien.md`.
- **6/17 kiểm tra built-in chưa từng có finding nào** trên toàn bộ dữ liệu 3 DN pilot (C2.1, C2.2, C2.3, C2.4, C5.1, C6.1) — xác nhận bằng truy vấn điều kiện thô trên Tầng 1, không phải check hỏng, chỉ là dữ liệu pilot chưa chạm điều kiện.
- **`book` không cần vào khoá nhận diện finding hôm nay** — không cặp (check, subject_key) nào trải >1 book trong dữ liệu hiện có. Rủi ro còn treo duy nhất: `COMBO_UNDECLARED_SOURCE` chưa kiểm được vì C5.1 chưa từng fire.
- **`subject_key` một mình không đủ làm khoá** (material_code/product_code trùng chuỗi ở ≥9 mã thật do BOM nhiều cấp) — đã có trong thiết kế khoá tự nhiên `(subject_type, subject_key)` của mục 1.7, không phát sinh việc mới.
- **X.\* `book=NULL` không phải khác biệt so với C1.1** — C1.1 cũng luôn để `book` trống theo đúng chủ đích thiết kế; khung punch-list 8 gắn nhãn "khác biệt" là hiểu chưa chính xác.
- **Chi phí ghi thêm 1 index composite trên `findings`**: +20-30ms mỗi lần xoá-tạo-lại ~11.000 dòng — đo được, không phải chi phí lớn, chỉ cần nhớ khi cân nhắc mục "an toàn ngay" ở trên.

---

## Ba việc tiếp theo

1. **Mở vé cài đặt `finding_reviews` (T1-T4, đã có nhánh T1)** — đây là lỗi mất dữ liệu cán bộ đang chạy thật, thiết kế đã sẵn, không chờ quyết định gì thêm.
2. **Owner chốt ADR #22 (thang điểm)** — mọi nhánh đụng `risk_score`/`scoring.py` (3 nhánh) nên gộp review sau khi có quyết định, tránh sửa hai lần. Trong lúc chờ, merge `fix/ai-tools-stale-risk-score` và hoàn tất `fix/stale-risk-score-remaining-sites` (hiện rỗng) — sửa cache-drift độc lập với việc chọn thang điểm nào.
3. **Chạy `pytest tests` + `ruff check app tests scripts` trên từng nhánh trước khi merge bất kỳ nhánh nào** — chưa nhánh nào được kiểm, và ít nhất 3 nhánh đụng chồng lấn file (`scoring`/`companies.py`/`ai/`).
