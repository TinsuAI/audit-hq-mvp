# UI + ingest theo sổ quyết toán (5 ticket 2SỔ) — E2E proof

**Ngày:** 2026-07-25 · **ADR:** #19 + Revision — UI + upload · **PR:** #23 (merged, build `1b903c7`) ·
**Session:** `.ai/sessions/2026-07-25-2so-ui-ingest.md`

Chụp trên DB THROWAWAY (job tmp, port 8324), seed một pháp nhân nhiều sổ `DEMO_004`
(EPE 104 mã · 34 phát hiện · GC 37 mã · 0 phát hiện · Chung 40) — KHÔNG đụng DB live
hay server :8200. Chi tiết chạy: `ui_smoke.py` (docstring).

## Screenshots
| # | Ảnh | Chứng minh |
|---|-----|-----------|
| 01 | `01_company_strip_split_pills.png` | Strip theo sổ (EPE 104·34 \| GC 37·0 \| Chung 40) + segmented `Tất cả·Sổ EPE·Sổ GC·Chung` + dòng split per-check (`Sổ: EPE 14`, `Sổ: Chung 22`) + pill book mỗi finding (EPE/Chung). Điểm 30/1000. |
| 02 | `02_filter_epe.png` | Lọc `?book=EPE` — chỉ finding sổ EPE; Chung KHÔNG bị kéo vào. Điểm/strip giữ toàn pháp nhân. |
| 03 | `03_filter_gc_clean_empty_state.png` | Lọc sổ GC (sổ sạch) → empty-state "Sổ GC (gia công) đã được đánh giá — 0 phát hiện trên 37 mã NVL" (khác no-data / chưa-chạy). |
| 04 | `04_filter_chung.png` | Lọc `?book=chung` → phát hiện liên sổ (`Finding.book IS NULL`), không lẫn EPE/GC. |
| 05 | `05_finding_detail_book_field.png` | `finding_detail` field "Sổ quyết toán: Sổ EPE (chế xuất)". |
| 06 | `06_review_book_selector.png` | Màn review WS1: selector "Sổ quyết toán (loại hình)" (value EPE, datalist EPE/GC, default "1 sổ (dùng chung)"). Branch B. |

## Reproduce
```
WORK=$CLAUDE_JOB_DIR/tmp/2so_smoke.sqlite; RAW=$CLAUDE_JOB_DIR/tmp/2so_raw
export DATABASE_URL=sqlite:///$WORK RAW_DATA_PATH=$RAW PYTHONPATH=.
.venv/bin/uvicorn app.main:app --port 8324 --no-access-log &   # kill theo PID, KHÔNG pkill
M_BASE=http://127.0.0.1:8324 .venv/bin/python .ai/features/2026-07-25-2so-ui-ingest/ui_smoke.py
```
