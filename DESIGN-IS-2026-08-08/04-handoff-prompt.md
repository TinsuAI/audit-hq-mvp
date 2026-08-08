# 04 — Prompt bàn giao cho `/make-plan`

Tự chứa: phiên sau không thấy audit này trừ khi được trích vào đây.

````
/make-plan Redesign the customs-officer data-preparation flow of Audit-HQ MVP (upload → ingest → preview grid → column assignment → check results). Current design failed a Dieter Rams audit at 13/30, with critical gaps in principle #6 honest (0), #3 aesthetic (1), #4 understandable (1), #5 unobtrusive (1), #8 thorough (1), #10 as little design as possible (1).

Verdict paragraph (quoted from the audit):
> The officer flow scores 13/30 and the load-bearing principle #6 Honest scores 0 — the officer's statement about their own file is silently overridden by the system along three separate paths — so it must be redesigned from purpose, not refined.

Why redesign and not refine: the interaction model contradicts the data model. The assignment screen invites the officer to state three states per field (assigned / unassigned / confirmed-absent), but the adapter layer only knows one ("which column feeds which field"). The other two have no path down to where the file is actually read, so they are swallowed. That is an interface-architecture fault; no amount of CSS fixes it.

Preserve from current design:
- The backend domain model: ADR #18 (per-column evidence ladder), #23/#24 (source gate, remedy classes), #25 (column groups), #28 (declared field set) in `.ai/DECISIONS.md`. This is what makes the product worth anything.
- The two-level `not_evaluable` gate — `app/checks/sources.py:104-122`. Correct mechanism, only missing its adapter half.
- The copy ethic: 0 inflated claims and 0 dark patterns across 1,155 distinct strings; the risk score explicitly disclaims itself (`app/templates/companies_list.html:65`); `app/templates/base.html:108` states the officer holds the final decision. Keep this voice exactly.
- The idea of a transposed assignment table showing real data rows read through the chosen columns. Keep the idea; rebuild the expression.
- Brand tokens: `--c-brand-500 #1d3557`, the `--space-*` 4px scale (`app/static/style.css:57-65`), the `--fs-*` scale (`:71-78`).

Discard:
- The assumption that a column map is the only officer statement worth persisting. Evidence: `grep -rn "absent" app/adapters/` returns zero; `app/adapters/templates.py:210` re-merges the default column unconditionally. Caused failure on principle #6.
- Unconditional overwrite of `absent_fields` on every submit. Evidence: `app/routes/companies.py:1719` computes it unconditionally while `app/templates/document_file.html:224` only renders the checkbox when `has_choices`, and `app/pipeline/saved_map.py:101` overwrites regardless. Caused failure on principle #6 (silent data loss).
- Ten parallel label vocabularies on one screen. Evidence: `app/pipeline/file_page.py:44-60,81-85`, `app/adapters/evidence.py:45-56`, `app/static/cell-grid.js:186-192,420-455`. Caused failure on principles #4 and #5.
- The dead column-highlight feature. Evidence: `app/static/cell-grid.js:486` binds `input.review-idx`; no template emits that class. Caused failure on principle #10.

Top 5 moves from the audit (verbatim):
1. #6 Honest: carry all three field states down to the adapter — `absent_fields` must reach `parse_m15/m15a/m16/bcct` and remove that column from the read map; "unassigned" must persist instead of being re-merged to the default. Evidence: `grep -rn "absent" app/adapters/` → 0; `app/adapters/templates.py:210`.
2. #6 Honest: close the silent-wipe path — write `absent_fields` only when the form actually rendered those controls; otherwise leave the stored value alone. Evidence: `app/routes/companies.py:1719` + `app/templates/document_file.html:224` + `app/pipeline/saved_map.py:101`.
3. #4 Understandable + #5 Unobtrusive: collapse 10 label vocabularies to 3 — which column, how sure, what is left to do. `Đã gán` and `Đã kiểm` currently render as the same blue badge side by side on every column. Evidence: `app/pipeline/file_page.py:81-85` + `app/adapters/evidence.py:45-56`.
4. #8 Thorough: build the disabled and empty states and fix the focus ring. `:disabled` has no rule anywhere; `.empty-state` has no rule anywhere; the form focus ring contrasts 1.34 against a 3:1 threshold. Evidence: `app/static/style.css:846-850`.
5. #3 Aesthetic + #10 As little design as possible: enforce the token system and delete the corpse. 85 colour literals outside `:root`, 49 off-scale `font-size` declarations, 42 dead CSS classes, 13 duplicated selectors with conflicting values. Evidence: `app/static/style.css` throughout; `app/static/cell-grid.js:486`.

Redesign principles in priority order:
1. #6 Honest — every statement the officer makes about their file is either honored end-to-end or refused with a reason. Nothing the officer says is silently discarded, and no two screens ever disagree about the same field.
2. #4 Understandable — a first-time officer names every badge correctly without leaving the screen. Terms are defined where they are used, not only in a manual reachable from the global header.
3. #10 As little design as possible — one vocabulary per axis, one control per decision, nothing on screen that does not change what the officer does next.

Scope. In scope: the column-assignment screen, the preview grid, and the shared label/badge system across the officer flow. Out of scope: the check model, the risk score, the check catalog, the AI sidebar.

Constraints: Vietnamese UI with full diacritics, formal register (`AGENTS.md`). Jinja2 + plain CSS + plain JS — no front-end framework. Officers work in Excel daily; the design may assume spreadsheet literacy but not web-app literacy. Accessibility floor: WCAG AA on text (the flow currently has a 4.39 and a 2.55), keyboard reach for every primary action, and a skip link (currently absent).

Deliverables for the plan:
- New information architecture, not derived from the current screens.
- New primary flow, low-fi and labeled, compared side by side against today's 5-step / 8-step paths.
- States checklist: empty, loading, error, success, focus, disabled.
- Migration path for maps and absent-field statements already saved in `saved_column_maps`.
- Cutover criteria — when the current file page is retired.

Anti-patterns to guard against:
- Porting the current structure under new styling.
- Keeping both designs behind a flag indefinitely.
- Redesigning toward a trend rather than the principles above.
- Treating the Preserve list as optional — the backend domain model and the copy ethic are not up for redesign.
````
