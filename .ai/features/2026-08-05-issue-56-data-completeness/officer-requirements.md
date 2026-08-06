# Officer requirements — meeting roundup (issue #56)

**Source:** GitHub issue [#56](https://github.com/TinsuAI/audit-hq-mvp/issues/56), opened 2026-08-04.
Two AI summaries of the **same** two recordings (rec-11: 19'24", rec-12: 55'42"), HQ officer + dev.
Transcription: `faster-whisper large-v3`, CPU, int8 — number and proper-noun accuracy is limited, see
[Reliability](#what-is-not-reliable).

The issue body states **one** requirement; the artifacts carry **22 action items**. This file
consolidates the business side only. Implementation scoping lives in `brief.md` next to it.

Domain terms kept in Vietnamese deliberately — they are identifiers, not prose.

---

## 1. The model everything else hangs off

The officer's material flow, stated at rec-11 00:31 and repeated at rec-12 39:49:

- **Tồn đầu kỳ was already consumed against the previous period's norms.** It does not need a
  current-year norm.
- **A current-year norm is required only when something came in this period** — nhập / sản xuất
  trong kỳ > 0. That is the trigger, not the xuất column.
- Corollary he stated explicitly: a mã with tồn đầu kỳ > 0 and nhập trong kỳ = 0 (only drawing down
  last year's stock) **needs no norm for this year**, and the current tool wrongly warns on it.
- When a mã has no norm for year Y, **fall back to year Y-1's norm and overlay the two**, rather
  than treating it as norm-less. Norms legitimately differ year to year — năng suất lao động and
  cải tiến kỹ thuật change them, and an inspection team accepts that if the DN explains it
  (rec-12 40:41).

That chain is what turned Rydon's "114 thành phẩm thiếu định mức" into 142 → 16 →
**5 genuinely missing**. The 114 was mostly the tool applying the wrong trigger.

> ⚠️ **The two summaries contradict each other here.** One says "tồn đầu kỳ AND nhập trong kỳ both
> = 0 → no norm needed" — self-contradictory (nothing exists at all) and inconsistent with rec-11
> 00:31. The other says "tồn đầu kỳ > 0, nhập trong kỳ = 0 → no norm needed", which agrees with
> everything else he said. **Working assumption: the second reading.** This is the single most
> important rule in the issue; confirm with him before building on it.

## 2. Why he refused to look at the Takagi output

Objections about validity, not presentation:

- **rec-11 01:08** — "thiếu 100 cái để nhân": with norms missing, the multiplication runs over an
  incomplete set, so the output is not wrong-by-a-bit, it is meaningless. He will not review it.
- **rec-11 02:43** — missing norms bias the result **in a known direction**: theoretical
  consumption is understated, so the reported gap understates the real one. Filling the missing
  norms makes findings worse, not better.
- **rec-11 01:15–01:25** — the machine may only follow an explicit chain A→B→C. It must not infer
  across mismatched codes. Exact match only; one character off is not a match, and the tool must
  say so instead of guessing.
- **rec-12** — "sai từ cái nút cúc áo đầu tiên thì cả cái áo sẽ bị lệch": one wrong answer and he
  stops trusting the tool. Hence the completeness table must come *before* any computed number.

## 3. Limits he set himself — the tool is not supposed to conclude

Caps the scope of everything else:

- HQ data has **only tờ khai + định mức**. No tồn đầu kỳ from the DN's books, no **dở dang**
  (rec-11 02:54–04:42).
- Production is continuous; the 31/12 cut-off is a formality, so any period comparison is
  approximate by nature.
- Therefore the tool is **"kiểm tra nhanh", "tương đối"** — enough to surface an abnormality and
  demand giải trình from the DN, **not** enough to conclude an audit finding (rec-11 05:10).
- One exception he named: if a material goes **negative before dở dang is even considered**, that
  alone proves the norm is wrong (rec-11 04:49).
- Dở dang đầu kỳ and dở dang cuối kỳ must be carried as **explicit assumptions**, not silently
  omitted.

## 4. The column-by-column criteria (rec-11 05:19–07:53)

He answered "anh cần tiêu chí nào" one column at a time. This is the actual requirements list.

| # | Column | What he wants | Verdict he expects |
|---|---|---|---|
| 0 | — | **Bảng thừa/thiếu định mức**: which mã thành phẩm have no norm, listed by code, not a total | Blocks everything else |
| 1 | Số dư đầu kỳ | VLOOKUP DN report against HQ data, catch `#N/A`. Plus: sum quantities and **count tờ khai** (HQ 100 vs DN 99) and name the missing/extra ones | Hard error |
| 2 | Nhập trong kỳ | Compare against quantities on tờ khai | **Not an error.** Nhập trả lại, chuyển kho, tái nhập are legitimate under kế toán rules → output a list for the DN to explain |
| 3 | Xuất trong kỳ | Cannot be checked directly ("tiệt"). Only approximate: **số thành phẩm sản xuất trong kỳ × định mức** | Flag mã where tiêu hao exceeds xuất sản xuất |

Column 3: the multiplier is **sản xuất trong kỳ**, not xuất khẩu.

## 5. Data-honesty rules (rec-12)

Detecting fabricated numbers rather than accounting differences:

- **Integer rule** — finished-goods stock and each xuất kho must be whole numbers. "10,5 chiếc cúc"
  or "10,5 cái tivi" in a biên bản kiểm kê means the number was made up ("bốc thuốc toàn diện",
  05:18). The reasonableness test is unit-dependent: a cuộn chỉ cut into lengths yields plausible
  fractions, a discrete item does not.
- Biên bản kiểm kê and số dư đầu kỳ **already disagree** at many DNs (00:37).
- A nhập kho record that doesn't reconcile to the original opening stock is a dishonesty indicator
  (end of rec-12).
- Suspicion to check for: the DN sends an **old norm file**, not the one actually filed with
  customs (25:13).

## 6. New inputs he's asking for

- **Three import buttons**: thành phẩm, nguyên vật liệu, biên bản kiểm kê. If the DN merges them
  into one file, the tool splits it — or allow importing three times.
- **Bảng đối chiếu mã** supplied by the DN: internal codes vs codes declared to customs match only
  **~50%**. Without it, matching is impossible (see §2, exact-match-only).
- **Form mapping**: DN files follow an older thông tư than the tool expects (mẫu 15 / 15A / 16).
- **A normalization step before analysis** — every accounting package exports a different shape.
- Later expansion: biên bản tự kê, tài khoản kế toán 152 / 154 / 155.
- **Tờ khai sửa (AMA)** are not filtered out today; only huỷ are. Numbers are overstated until that
  is fixed.
- Keep the two report types separate — Takagi has both **02 (SXXK)** and **04 (gia công)**; they
  must not be mixed.

## 7. Output requirements

Short, with highlights, and **every number traceable to its source row**. Plus a drill-up: from a
số dư back to each individual phiếu xuất kho, so the balance can be rebuilt.

---

## What is not reliable

Came through speech-to-text. Confirm with him rather than coding from:

- Circular and form numbers — "Thông tư 21", "121", "mẫu 15A / 15 / 16". One summary heard 21, the
  other 121. See the project rule on citing law: consolidated version + effective date, from the
  Công báo PDF, not a web copy.
- Tài khoản numbers — 152/154/155 in one summary, 152/153 in the other.
- All figures: 17.171.000 vs 171.342, 2.004, định mức 1,12, "63 mã" vs "5 mã", 114/142/16.
- Mã and DN names: NVLC2 vs NVLC2-003, M16 vs "Mũ 16", Rydon/Raidon, Asahi/Yoko.

## Two questions to settle before any code

1. The §1 exclusion rule — which of the two contradictory readings is correct.
2. Whether column 3's multiplier is sản xuất trong kỳ (`sp_balances.intake_qty`) rather than the
   `export_qty` the code uses today. Everything downstream multiplies by it.
