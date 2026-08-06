# Đối chiếu các con số phát hiện — 2026-07-30

Mục đích: gỡ ba mâu thuẫn số liệu trong tài liệu để demo và số nói với khách không tự đá nhau.
Đo bằng `sqlite3.connect("file:audit_hq.sqlite?mode=ro", uri=True)` qua
`.venv/bin/python`, đọc thuần, không ghi. **Toàn bộ số trong mục 1 là số đo trên DB LOCAL**
(`/home/vp/workspace/client/audit-hq-mvp/audit_hq.sqlite`), đo lúc 2026-07-30. Cách phân biệt
với PROD: PROD chạy trên `audit-hq-demo.tinsu.ai`, DB nằm trong container (`db-data/audit_hq.sqlite`)
— không đọc được từ máy này trong phạm vi việc này (read-only, không SSH). Bất cứ chỗ nào dưới đây
ghi "theo STATUS.md" cho số PROD là trích lại lời khai của STATUS.md, KHÔNG phải số tôi tự đo.

## 1. Bảng thẩm quyền — số đo trực tiếp trên DB LOCAL, 2026-07-30

### 1.1 Tổng theo (pháp nhân, năm) và theo mức độ nghiêm trọng

| Pháp nhân | Năm | Nghiêm trọng | Cảnh báo | Thông tin | Tổng |
|---|---:|---:|---:|---:|---:|
| PILOT_002 | 2025 | 25 | 22 | 1 | 48 |
| PILOT_004 | 2025 | 61 | 7 | 6 | 74 |
| PILOT_006 | 2024 | 3.147 | 422 | 311 | 3.880 |
| PILOT_006 | 2025 | 9.963 | 904 | 129 | 10.996 |
| **Tổng cộng 4 dòng trên (3 pháp nhân)** | | **13.196** | **1.355** | **447** | **14.998** |

### 1.2 Theo bài kiểm tra (`check_code`)

| Pháp nhân/năm | Theo bài kiểm tra (mã: số dòng) |
|---|---|
| PILOT_002/2025 (48) | C1.1:2 · C3.1:2 · C3.2:14 · C3.3:3 · C4.3:27 |
| PILOT_004/2025 (74) | C1.1:33 · C1.2:4 · C1.3:15 · C1.4:2 · C1.6:1 · C1.7:1 · C3.2:1 · C3.3:4 · C4.1:5 · C4.3:8 |
| PILOT_006/2024 (3.880) | C1.1:419 · C1.2:3 · C1.3:32 · C1.4:5 · C1.6:1.660 · C1.7:618 · C3.2:467 · C3.3:67 · C4.1:17 · C4.3:564 · **COMBO_HS_GAMING:28** |
| PILOT_006/2025 (10.996) | C1.1:97 · C1.2:12 · C1.3:43 · C1.4:21 · C1.6:5.785 · C1.7:2.436 · C3.1:9 · C3.2:776 · C3.3:31 · C4.1:14 · C4.3:1.772 |

`COMBO_HS_GAMING` là một `check_code` thật trong bảng `findings` (không phải chuỗi trong `details`),
chỉ xuất hiện ở PILOT_006/2024, toàn bộ 28 dòng đều `severity='warning'`, 0 dòng ở 2025 — xác nhận đúng
lời STATUS.md.

## 2. Ba mâu thuẫn — nguồn gốc, có phải "sai" hay không

### 2.1 Critical PILOT_004/2025: 52 hay 61

**Không phải một số sai — hai môi trường khác thời điểm, chưa đồng bộ.**

- **61** = số hiện tại của DB LOCAL (đo trực tiếp mục 1.1 ở trên) **và** đồng thời là số PROD **trước**
  khi chạy lại check 004 ngày 2026-07-27 (`.ai/STATUS.md:162-181`, khối "CHẠY LẠI CHECK 004 TRÊN PROD").
  Toàn bộ 74 dòng finding PILOT_004/2025 trong DB local có `created_at = 2026-07-24 18:59:25` (một lượt
  ghi duy nhất) và `check_runs.data_version = 0` cho cả 17 check — tức là DB local **chưa từng nhận** lượt
  chạy lại 2026-07-27, vì lượt đó chạy **scoped, thẳng trong container PROD**
  (`python -m app.pipeline.run_checks --company PILOT_004 --year 2025 ...`), không đụng DB local.
- **52** = số PROD **sau** lượt chạy lại 07-27, theo lời khai của `.ai/STATUS.md:167-168`: xoá 9 dòng
  trùng đơn vị thứ hai (C1.1 33→28, C1.3 15→13, C3.3 4→2), trong đó 3 dòng xoá đúng là CRITICAL sai
  (lỗi trục đơn vị MTR/ROLL). Số 52 **đã được xác nhận lại** trong tài liệu khách xem
  `app/static/docs/phan-tich-pilot/index.html:643` ("52 nghiêm trọng · 7 cảnh báo · 6 thông tin", tổng 65
  dòng 638) — tức khớp PROD hiện hành theo cách độc lập với STATUS.md.
- Việc tôi có thể xác nhận trong phạm vi việc này: **local = 61 đúng cho local**. Việc **PROD = 52** tôi
  không tự đo được (không có quyền đọc DB PROD ở đây) — chỉ trích lại STATUS.md + tài liệu tĩnh nói trên.
- `.ai/notes/2026-07-30-kich-ban-demo-5-phut.md:34` đã tự phát hiện đúng vụ này trước tôi và ghi rõ:
  "STATUS có một khối đo khác (61·7·6) từ một lượt đo read-only trên DB local ngày 2026-07-29/30, chưa đối
  chiếu với số prod — phải verify lại số hiện trên màn hình ngay trước giờ demo".

### 2.2 Tổng finding prod: 14.989 hay 14.998; và 10.996, 3.880/3.852

**14.989 vs 14.998: cùng nguyên nhân với mục 2.1 — không phải số sai, là số trước/sau lượt fix 07-27.**

- 14.998 = 48 (002) + 74 (004, số cũ) + 14.876 (006, không đổi) — số PROD **trước** 07-27, và cũng là số
  hiện tại của DB LOCAL (mục 1.1: 48+74+3.880+10.996 = 14.998).
- 14.989 = 48 + 65 (004, số mới sau khi xoá 9 dòng) + 14.876 — số PROD **sau** 07-27, theo
  `.ai/STATUS.md:168-169` và tài liệu khách `phan-tich-pilot/index.html`.
- **10.996** (PILOT_006/2025): không có mâu thuẫn — khớp DB local, khớp mọi trích dẫn trong STATUS.md và
  các note, vì PILOT_006 hoàn toàn không bị đụng bởi lượt fix 004 (`STATUS.md:169`: "002/006 KHÔNG đụng").
- **3.880 vs 3.852** (PILOT_006/2024): **không phải mâu thuẫn thời gian — là khác mẫu số, cả hai đều đúng
  cùng lúc.** 3.880 = tổng thô toàn bộ finding 2024, gồm 28 dòng `COMBO_HS_GAMING` (xác nhận mục 1.2, toàn
  bộ severity=warning). 2025 có 0 dòng `COMBO_HS_GAMING`. Khi so sánh biến động 2024→2025 theo cùng một bộ
  bài kiểm tra (không tính bài combo chỉ tồn tại một phía), mẫu số đúng của 2024 là 3.880 − 28 = **3.852**.
  STATUS.md tự giải thích việc này ở dòng 55-56. Quy tắc dùng: nói "tổng phát hiện 2024" → dùng 3.880; nói
  "so với 2025 theo cùng bộ bài kiểm tra" → dùng 3.852.

### 2.3 Số test pass: 873 hay 863 pass + 12 skip

**Không phải số sai — đo ở hai thời điểm cách nhau 3 ngày, bộ test đã đổi giữa hai lần đo.**

- **873** = số "test pass" ghi trong `.ai/STATUS.md` ba chỗ (dòng 97, 109, 155), cả ba đều thuộc các khối
  ngày **2026-07-27**, gắn với nhánh `fix/badge-wording` (PR #43, đã merge — `c869912`, cộng 2 commit sau
  đó `46067a9`, `c640b93`). Không có số skip đi kèm ở thời điểm đó.
- **863 passed + 12 skipped** (= 875 test được thu thập) = lượt chạy toàn bộ (`pytest tests`) tối nay
  2026-07-30 trên DB lạnh (cold DB), theo lời khai trong yêu cầu việc này — tôi không tự chạy lại pytest
  (nằm ngoài phạm vi read-only + hạn 10 phút).
- Giữa 07-27 và 07-30, `main` nhận thêm nhiều commit (PR #46 `docs/pilot-analysis` đã merge — xem
  `git log`; cộng 17 nhánh song song đang mở worktree theo `.ai/STATUS.md:3-7`), nên tổng số test tăng từ
  873 lên 875 là hợp lý (test mới thêm), không phải lỗi đo.
- Cơ chế 12 skip: `tests/test_adapters.py:16-19` và `tests/test_discover.py:9` có
  `pytest.mark.skipif(not DATA_ROOT.exists(), ...)` — bộ test này tự skip khi thư mục `data/` (symlink dữ
  liệu Excel thật, gitignored) không có mặt. DB lạnh / checkout mới thường không có symlink này gắn sẵn —
  khớp đúng cơ chế skip đã biết (memory note "Local data symlink mismatch"). Chưa xác nhận chính xác 12
  test nào skip (không chạy lại pytest trong việc này) — đây là cơ chế nhiều khả năng nhất, không phải số
  đã đếm tận tay.
- Kết luận: 873 **đúng khi viết** (07-27, một nhánh cụ thể, môi trường có data symlink); 863+12 là lượt đo
  **sau, đầy đủ hơn, khác môi trường** — cả hai không mâu thuẫn nhau, cái sau đơn giản là mới hơn.

## 3. Danh sách số có thể trích dẫn — mỗi số kèm: giá trị / đếm gì / mẫu số / ngày đo / local hay prod

| Giá trị | Đếm gì | Mẫu số | Ngày đo | Local/Prod |
|---|---|---|---|---|
| **74** (61 nghiêm trọng · 7 cảnh báo · 6 thông tin) | Tổng finding PILOT_004/2025 | Toàn bộ `findings` company_id=9, period_year=2025 | 2026-07-30 (đo lại), gốc ghi lúc 2026-07-24 | **LOCAL** |
| **65** (52 nghiêm trọng · 7 cảnh báo · 6 thông tin) | Tổng finding PILOT_004/2025 sau khi xoá 9 dòng trùng đơn vị | như trên | 2026-07-27 | **PROD** (theo STATUS.md + `phan-tich-pilot/index.html`, chưa tự đo) |
| **14.998** | Tổng finding 3 pháp nhân (002+004+006) | Toàn bộ bảng `findings` | 2026-07-30 (đo lại), gốc 2026-07-25 | **LOCAL**, và = PROD trước 2026-07-27 |
| **14.989** | Tổng finding 3 pháp nhân, sau fix 004 | như trên, trừ 9 dòng đã xoá | 2026-07-27 | **PROD** (chưa tự đo) |
| **10.996** | Tổng finding PILOT_006/2025 | Toàn bộ `findings` company_id=8, period_year=2025 | 2026-07-30 | **LOCAL = PROD** (không đổi, xác nhận khớp mọi nguồn) |
| **3.880** | Tổng finding PILOT_006/2024 (gồm 28 COMBO_HS_GAMING) | Toàn bộ `findings` company_id=8, period_year=2024 | 2026-07-30 | **LOCAL = PROD** |
| **3.852** | Tổng finding PILOT_006/2024, trừ 28 dòng `COMBO_HS_GAMING` để so cùng bộ bài kiểm tra với 2025 | như trên, `check_code NOT LIKE 'COMBO_%'` | 2026-07-30 | **LOCAL = PROD** |
| **873** | Test pass, không tính skip | `pytest tests` trên nhánh `fix/badge-wording`/PR #43 | 2026-07-27 | môi trường có `data/` symlink |
| **863 passed + 12 skipped** | Kết quả `pytest tests` đầy đủ | Toàn bộ test hiện có trên `main` (875 test) | 2026-07-30 (tối nay, DB lạnh) | môi trường không có `data/` symlink |

## 4. Nơi trong repo còn ghi số cũ chưa gắn caveat — cần sửa một lượt

Không sửa trong việc này (chỉ đọc). Liệt kê để sửa sau:

- `.ai/STATUS.md:23` — "004/2025 30→61·7·6" (khối "THANG ĐIỂM", ngày 2026-07-30) — số 61 là số LOCAL
  trước fix, ghi cạnh các số khác không có caveat, dễ đọc nhầm là số hiện hành. Nên ghi rõ "(DB local,
  chưa áp lượt fix 07-27 — PROD hiện là 52)".
- `.ai/notes/2026-07-30-adr-thang-diem-rui-ro.md:68` — dòng bảng "PILOT_004 / 2025 | 61 | 7 | 6 | 74" —
  cùng vấn đề, là bảng chi tiết đứng sau số ở STATUS.md:23. Cần caveat tương tự.
- `.ai/STATUS.md:97,109,155` — "873 test pass" (ba chỗ, khối ngày 2026-07-27) — đã cũ 3 ngày so với lượt
  chạy đầy đủ tối 2026-07-30 (863 passed + 12 skipped). Không sai khi viết, nhưng nếu còn được trích làm
  "tình trạng test hiện tại" thì cần cập nhật.
- `.ai/STATUS.md:276` — "Tổng finding prod = 14.998" (khối ngày 2026-07-25, trước lượt nạp 004 hai sổ và
  trước fix 07-27) — đúng tại thời điểm viết, đã bị khối ngày 07-27 (dòng 168) ghi đè bằng 14.989. Ai đọc
  rời khối này (không đọc tiếp xuống 07-27) sẽ lấy nhầm số cũ.
- `.ai/notes/2026-07-30-hieu-nang-man-phat-hien.md:10` — "`findings`: 14.998 dòng" — số này **đúng cho
  LOCAL** (khớp phép đo ở mục 1 việc này), nhưng ghi không kèm nhãn "đo trên DB local" nên người đọc dễ
  hiểu nhầm là số PROD hiện hành (vốn là 14.989). Không sai, nhưng thiếu nhãn môi trường.
- `.claude/worktrees/agent-*/` (khoảng 20 thư mục worktree của đợt chạy song song 17 luồng hôm nay,
  `.ai/STATUS.md:3-7`) — mỗi thư mục có bản sao `.ai/STATUS.md` và
  `app/static/docs/phan-tich-pilot/index.html` tại thời điểm nhánh được tạo, mang y nguyên các số ở trên.
  Đây là bản sao tạm của git worktree, không phải vị trí tài liệu bền — sẽ tự hết khi các luồng đóng hoặc
  merge; không liệt kê từng file:line vì sẽ biến mất, không cần sửa tay.

## 5. Nơi đã đúng / đã tự đối chiếu — không cần sửa

- `app/static/docs/phan-tich-pilot/index.html:529,530,638,643` — dùng đúng số PROD sau fix (65 · 52 ·
  25 điểm), khớp STATUS.md khối 07-27.
- `.ai/notes/2026-07-30-kich-ban-demo-5-phut.md:23,27-34` — đã tự phát hiện và ghi rõ chênh lệch 61 vs 52,
  dặn verify lại trên màn hình trước giờ demo thay vì đọc thuộc lòng số trong kịch bản.
- `.ai/notes/2026-07-30-chong-lan-giua-cac-kiem-tra.md:115-116` và
  `.ai/sessions/2026-07-29-dashboard-ux-prototype.md:55-56` — giải thích đúng và nhất quán vụ 3.880 vs
  3.852 (28 dòng `COMBO_HS_GAMING`).
- `.ai/STATUS.md:569-570` — tự ghi rõ "14.989 finding sau khi chạy lại check 004 ngày 2026-07-27 (trước đó
  14.998 — xem khối đầu file)" — đây là khối tổng kết đúng, nên dùng làm điểm neo khi cần trích dẫn nhanh.
