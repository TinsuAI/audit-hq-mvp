# 004 — hai loại hình (một pháp nhân, hai sổ quyết toán)

**Ngày:** 2026-07-25 · **ADR:** #19 (`.ai/DECISIONS.md`) · **Memory:** `pilot-004-epe-gc-merge`, `local-db-schema-drift`

## Vấn đề
Pilot 004 (MST `0901051747`) là **một** DNCX vừa sản xuất tự sở hữu vừa gia công, nhưng lưu thành **hai**
company row (`PILOT_004_EPE` id 9, `PILOT_004_GC` id 10) với tờ khai NHÂN ĐÔI. Mỗi sổ chỉ đối chiếu tờ
khai với M15 của RIÊNG nó → C1.2 báo "thiếu M15" cho mã thuộc sổ kia: **99 finding, 91 giả**
(verified: GC 70 = 66 giả + 4 thật; EPE 29 = 25 giả + 4 thật).

## Cách sửa
Mô hình "1 pháp nhân = 1 sổ tờ khai dùng chung + N sổ quyết toán, mỗi sổ một loại hình". Cột `book` trên
`nvl_balances`/`sp_balances`/`norms`/`findings`. Check cross-layer (C1.1/C1.2/C1.4) đối chiếu tờ khai với
UNION các sổ; check nội-sổ (C4.1/C4.3/C6.1/C3.3) `GROUP BY book`. C1.1/C1.4 gộp theo `(mã, đơn vị)` —
không cộng MTR + ROLL. 6 check sửa code, 8 check chỉ gắn nhãn `book` để truy nguồn. Toàn bộ test-first
(680 pass; single-book `book=NULL` giữ nguyên hành vi → 002/006 không đổi).

## Kết quả (collapse 004: id 9 + id 10 → `PILOT_004`)
| | trước | sau |
|---|---|---|
| **C1.2** | 99 | **4** |
| C1.1 | 50 | 33 |
| tổng finding | 187 | **74** |

Screenshots (chụp trên BẢN COPY đã collapse — DB throwaway, KHÔNG đụng DB live hay :8200 của user):
- `01_companies_list.png` — 004 giờ là MỘT pháp nhân `DEMO_004` (MST 0901051747), badge 2025 = 61•7•6 = 74.
- `02_company_004_findings.png` — trang DN `DEMO_004`, điểm 30/100, C1.2 = 4, C1.1 = 33, đủ nhóm check.

## Chưa làm
- **Live-apply**: cần (1) dừng server :8200, (2) vá schema drift DB live (thêm `data_version` + `book`),
  rồi chạy collapse + `run_checks` trên DB live. Xem `local-db-schema-drift`.
- UI breakdown per-sổ (EPE/GC) — **hoãn sang session sau; GRILL/design trước khi build** (owner
  chốt 2026-07-25). Hiện `book` chỉ ở tầng dữ liệu (findings/nvl/sp/norms + evidence filter), KHÔNG
  route/template nào render. Bản tối thiểu gợi ý: badge `book` trên finding có `book`, + đếm "sổ EPE:
  N · sổ GC: M" ở header DN 004. Pass này chỉ sửa số + gắn nhãn `book` trên finding.

## Reproduce
```
WORK=<đường dẫn bản copy đã collapse>
DATABASE_URL=sqlite:///$WORK .venv/bin/uvicorn app.main:app --port 8323 --no-access-log &
M_BASE=http://127.0.0.1:8323 DATABASE_URL=sqlite:///$WORK PYTHONPATH=. \
    .venv/bin/python .ai/features/2026-07-25-004-two-loai-hinh/ui_smoke.py
```
