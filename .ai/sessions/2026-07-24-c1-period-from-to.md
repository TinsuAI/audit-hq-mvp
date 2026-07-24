# Session 2026-07-24 — C1 `period_from`/`period_to` (full-stack → prod)

Implement C1 kỳ báo cáo custom-date, full-stack, merge + deploy prod trong 1 session.
Commits: `ca07e8c` (feat) → `f5d2c0c` (merge PR #2) → `1ebb59f` (docs STATUS, `[skip ci]`).
ADR liên quan: **#16** (`.ai/DECISIONS.md`). Brief: `.ai/features/2026-07-23-c1-period-from-to/`.

## What Was Done

**Backend:**
- Bảng `company_periods(company_id, period_year, period_from, period_to, is_manual)`, unique
  `(company_id, period_year)` — `app/models/company_period.py` + migration `e4f5a6b7c8d9`.
- `app/pipeline/period.py`: `resolve_period_bounds` (ưu tiên manual > tiêu đề file > dương lịch,
  upsert, KHÔNG ghi đè `is_manual`), `default_bounds`, `in_period`, `load_period_windows`.
- `app/pipeline/ingest.py`: đổi 2 điểm lọc BCCT (đếm stats + vòng insert) từ
  `declaration_date.year == year` sang cửa sổ `period_from ≤ date ≤ period_to`; ghi
  `DeclarationLine.period_year = year` (**nhãn kỳ**, tách khỏi `declaration_date`).

**Frontend:**
- Route `POST /companies/{code}/documents/period` (validate `from≤to`, lưu `is_manual=True`,
  `reset=1` → `is_manual=False`). `company_documents.html`: form sửa kỳ + banner "nạp lại để áp
  dụng" + nút về mặc định.
- `load_period_windows` truyền vào `company_detail` + `item_detail`: nhãn "năm tài chính
  dd/mm–dd/mm" ở tab năm (sup TC + tooltip), dòng chú dưới tab, phụ đề 2 section item_detail,
  tooltip cột Năm. **DN dương lịch không đổi gì.**

**Kiểm chứng:**
- 22 test mới (model/bounds/filter/route/render): `tests/test_company_periods.py`,
  `test_period_bounds.py`, `test_company_period_route.py`. Full suite xanh (`pytest -q` exit 0,
  `ruff` clean).
- Harness (scratchpad, DB tạm): **PILOT_002 phục hồi đúng 3.014/11.115 dòng** (cửa sổ tự đọc
  header `2025-04-01..2026-03-31`, `bcct_other_year=0`); whitelist **1.331 finding BẤT BIẾN**.
- 3 ảnh proof: `.ai/features/2026-07-23-c1-period-from-to/screenshots/{01_documents_period_editable,
  02_company_detail_fiscal_label, 03_item_detail_fiscal_dates}.png`.

**Ship:** PR #2 → merge `f5d2c0c` → CI (`deploy.yml`: test+lint → build → restart →
`alembic upgrade head` → healthcheck) xanh → prod `audit-hq-demo.tinsu.ai` `/healthz` 200,
`build_sha=f5d2c0c` khớp. Migration `e4f5a6b7c8d9` đã áp lên DB prod.

## Decisions Made

- **Đường RẺ** (window filter + `period_year`=nhãn), KHÔNG đường ĐẦY ĐỦ (thêm from/to vào 214
  tham chiếu — `notes/12` "KHÔNG làm" #4 loại). Khả thi nhờ ADR #13 chốt `period_year` là khoá
  join: sửa 1 điểm gán nhãn, cả pipeline (17 check + scoring + item-detail + inject) tự đúng.
  Đã verify `app/checks/` KHÔNG chỗ nào suy năm từ `declaration_date`.
- **Grain** per `(company, period_year)` + cờ `is_manual` (re-ingest tôn trọng bản sửa tay).
- **Default dương lịch** khi header thiếu ngày → 6 DN whitelist bất biến.
- **Re-apply tường minh** (nút Nạp/Chạy sẵn có), không auto-reingest ngầm.
- **Hiển thị** chỉ hiện cửa sổ khi kỳ ≠ dương lịch (`load_period_windows` lọc sẵn).
- **Không đụng catalog/đề án**: đổi *dòng nào vào kỳ* + schema, không đổi mô tả check (khác B2/B4).
- **Git:** commit message tiếng Anh (RULES), **không trailer co-author** (rule user > mặc định
  harness). Docs commit dùng **`[skip ci]`** để không redeploy prod cho thay đổi docs-only.

## What Didn't Work

- **Mốc "419" trong STATUS cũ LỖI THỜI** — harness thật cho **1.331** finding trên 12 cặp; đo
  baseline code cũ (stash `ingest.py`) cũng **1.331** → C1 trung tính, không regression. Đã đính
  chính STATUS. Đừng dùng 419 làm tiêu chí.
- **`pkill -f uvicorn` giết luôn dev server :8200 của user** (đang chạy nền từ Jul23) khi tôi
  định kill server throwaway :8321. Phải `setsid` restart lại :8200. Bài học → memory
  [[dev-server-do-not-pkill]]: kill server theo **PID cụ thể**, `setsid` cho server throwaway.
- **`ui_smoke._purge` lần đầu thiếu xoá dòng con** (NvlBalance/DeclarationLine) → FK constraint
  chặn `DELETE companies` → để sót DN `SHOT_C1` trong DB local. Đã purge thủ công (đúng thứ tự
  FK) + sửa `_purge`.

## Open Items

- **Cảnh báo cửa sổ SỬA TAY chồng lấn chéo năm** — hiện chưa; giới hạn manual-only có chủ đích
  (đường tự động FY liền kề không chồng). Nếu làm: khi lưu kỳ, kiểm CompanyPeriod năm liền kề,
  cảnh báo nếu chồng. Xem ADR #16.
- **Reload dữ liệu PILOT_002/004 lên prod** để hưởng phục hồi dòng — prod hiện KHÔNG có file
  nguồn 002/004 (10/14 DN prod thiếu file). Cần upload/chạy lại từ file mới thấy tác dụng.
- **Edge chưa xử lý:** tờ khai bổ sung/trễ ngày NGOÀI cửa sổ nhưng DN quyết toán kỳ trước → hiện
  gán theo NGÀY (không theo "khai ở sổ kỳ nào"). Pilot = 0 ca. Mitigate: sửa kỳ tay + `bcct_other_year`.
- **Roadmap tiếp** (Next Steps STATUS): M15a mở rộng + cột định mức M16 của 004 (mở khoá
  C4.3/C1.4 cho 004); rồi B2/B4/hệ số nhân — **chặn bởi đề án** (phải update `../audit-hq/` trước).
