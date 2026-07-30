# Developer onboarding map — Audit-HQ MVP

Durable architecture map. Does not duplicate `.ai/STATUS.md` (current sprint state,
today's blockers, live data counts) — read that separately for "what's happening
right now." This file answers "how is the system built" and should stay accurate
across many STATUS.md rewrites. Vietnamese domain terms are kept where they are the
real vocabulary (used in code comments, model names, UI copy) and explained on
first use.

## 1. What the system does, in ten lines

Hải quan (customs) officers upload enterprise Excel files — BCQT (báo cáo quyết
toán, settlement report) forms Mẫu 15/15a/16 and BCCT (báo cáo chi tiết, customs
declaration detail export from VNACCS/ECUS) — for one company × year.
`app/adapters/*.py` parses each Excel form into typed rows (`app/pipeline/ingest.py`
orchestrates). Rows land in four "Tầng 1" (layer 1, raw-fact) tables:
`nvl_balances`, `sp_balances`, `norms`, `declaration_lines` (`app/models/bcqt.py`,
`app/models/declaration.py`). 17 built-in checks (`app/checks/c1..c6_*.py`,
registry at `app/checks/registry.py`) run over Tầng 1 and write `Finding` rows
(`app/models/finding.py`) — "Tầng 2" — each carrying `evidence_refs` back to the
Tầng 1 row(s) that produced it. Checks run asynchronously through a job queue
(`app/jobs/`), never inline in a request handler. A rate-based scorer
(`app/checks/scoring.py`) turns findings into a 0–1000 risk score per
(company, year), stored in `CompanyYearScore`. Server-rendered Jinja2 screens
(`app/routes/companies.py` + `app/templates/`) show companies, findings, raw data
drill-down (`app/items/`), and an Excel export (`app/pipeline/export.py`). An
optional AI assistant (`app/ai/`) answers questions over the same DB read-only
through OpenAI-compatible tool-calling, and can generate a per-check natural-
language "overview" (`app/ai/overview*.py`) — LLM output is always split from a
Python-computed number table, never trusted for the numbers themselves.

## 2. Module map

### `app/adapters/` — Excel → typed rows
Owns: reading one Excel workbook into a dataclass of rows. Entry points:
`parse_bcct`, `parse_m15`, `parse_m15a`, `parse_m16` (re-exported from
`app/adapters/__init__.py:1-4`). Supporting modules: `sheet_select.py` (pick the
right sheet by column-label content, not by sheet name — `app/adapters/
sheet_select.py:1-13`), `layout.py` (find the header row + first data row),
`extended_layout.py` (infer column mapping from a file's own numbered row `(1)
(2)…` when the standard layout doesn't match, verified against the form's own
balance equation — ADR #15), `form_signature.py` (hash a form's header shape to
key a saved column-map), `evidence.py` (per-column confidence: `officer-confirmed`
> `header-matched` > `balance-checked` > `position-only` — ADR #18). Depended on
by: `app/pipeline/ingest.py`, `app/pipeline/validate.py`, `app/pipeline/
discover.py`. **Seam — new Excel form/slot:** add a `parse_*` function here, a
`SLOT_*` entry in `app/models/data_file.py:28-47`, and wire it into
`app/pipeline/ingest.py`'s `_SETTLEMENT_PARSERS` (`app/pipeline/ingest.py:66`).

### `app/checks/` — the 17 rule functions + registry
Owns: rule logic reading Tầng 1, scoring, dynamic (admin-authored) checks.
`registry.py` holds `SPECS: dict[str, CheckSpec]` (metadata: code, group, title,
severity) and `CHECK_COLUMNS` (which `(slot, field)` each check reads, used to
decide which checks to re-run when a column mapping changes — `app/checks/
registry.py:377-413`). `c1_quantity.py` .. `c6_cross_period.py` each expose a
`CHECKS: dict[str, fn]` merged into `ALL_CHECKS` in `app/checks/__init__.py:1-8`
(17 entries, verified: `C1.1-4,1.6,1.7 / C2.1-4 / C3.1-3 / C4.1,4.3 / C5.1 / C6.1`).
`sql_runner.py` + `spec_gen.py` implement admin-authored "extended" checks
(`X.*` codes) written in read-only SQL or restricted Python, composed via an
LLM tool-loop at authoring time — this is the one place `app/checks/` imports
`app.ai` (`spec_gen.py`), and it runs only when an admin drafts a check, never
during `run_checks()`. `scoring.py` (rate-based score, replaces an older linear
"legacy" scorer kept only for `compute_risk_score`/`inject_findings` backward
compat), `denominators.py` (rate denominators per rule scope: `nvl`/`tp`/`m16`),
`combos.py` (meta-findings, `COMBO_*` codes, when several findings co-occur),
`company_type.py` (DNCX/GIA_CONG/SXXK detection from declaration customs codes),
`uom.py` (unit-of-measure canonicalization for C3.3). Depended on by:
`app/pipeline/run_checks.py`, `app/ai/system_prompt.py`, `app/ai/tools.py`.
**Seam — new built-in check:** one file `app/checks/cN_*.py` with a function
`check_cN_x(session, company_id, year) -> list[Finding]` added to that module's
`CHECKS` dict (pattern: `app/checks/c1_quantity.py:522-529`), a `register(CheckSpec(...))`
call in `registry.py`, an entry in `CHECK_COLUMNS` if it reads Tầng 1 columns
individually, and re-export in `app/checks/__init__.py`. Per AGENTS.md: one test
file `tests/test_checks/test_cN_*.py`.

### `app/pipeline/` — orchestration between adapters, checks, and the DB
`ingest.py` — `ingest(company_code, year, ...)`: wipes and reloads Tầng 1 rows for
a (company, year), enforces the "book" (settlement ledger, §3) plan before
deleting old data (`IngestPlanError`, `app/pipeline/ingest.py:69-75`), bumps
`CompanyPeriod.data_version`. `run_checks.py` — `run_checks(company_code, year,
only=None)`: the single place that deletes+reruns findings, upserts `CheckRun`
and `CompanyYearScore`, recomputes `company.risk_score` (see §4 for the trap
here). `discover.py` — finds candidate files on disk for a (company, year, slot).
`period.py` — infers `(period_from, period_to)` for a period_year. `validate.py`
— pre-ingest sanity check producing Vietnamese-language diagnosis when a file
doesn't match the expected layout (`UploadDiagnosis`), independent of AI.
`recompute.py` — rescoring from *existing* findings without re-running checks
(used after an officer changes a finding's status). `saved_map.py` — persisted
column maps keyed by `(company, slot, form fingerprint)`. `data_files.py` —
syncs the `data_files` registry table with the filesystem. `export.py` — Excel
report generation. `run_all.py` — batch CLI over every company × year found on
disk. **Seam — new pipeline stage:** most stages are plain functions taking a
`Session`; call from a route or job handler, not from another pipeline module
unless already imported that way (adapters intentionally do not import
`pipeline.validate` to avoid a cycle — `app/adapters/layout.py:6-8`).

### `app/routes/` — HTTP surface (FastAPI routers, Jinja2 templates)
`companies.py` is the largest file: company list/detail, upload, documents
review/re-ingest, run-checks trigger, findings table, Excel export download.
`admin.py` (UOM canonical/alias), `admin_ai.py` (`/admin/ai` settings),
`admin_checks.py` (`/admin/checks` — author/publish dynamic `X.*` checks),
`admin_risk_tiers.py`, `admin_users.py`, `admin_audit.py` (access log viewer).
`ai.py` — `POST /api/chat`, the chat endpoint. `catalog.py` — public read-only
`/danh-muc-kiem-tra` view of the full 49-check catalog (`app/catalog_full.py`,
distinct from the 17 implemented `SPECS`). `chat_page.py` — full-page chat UI
shell. `docs.py` — renders `docs/*.md`. `jobs.py` — job status pages + unread
badge. All routers are wired in `app/main.py:128-139`; a new router file must be
added there. **Seam — new route:** add a path function to the relevant router
file (or a new router + `app.include_router(...)` in `app/main.py`). Every
`{code}`-scoped company route must call `get_company_or_404` (`app/scoping.py`)
— out-of-scope company returns 404, never 403, to avoid revealing existence
(`app/scoping.py:8-9`).

### `app/jobs/` — async job queue
`app/models/job.py` defines `Job`, `JobKind` (`RUN_CHECKS`, `BATCH_RUN`,
`AI_OVERVIEW`, `AI_OVERVIEW_BATCH`; `INGEST_AND_RUN` is declared at
`app/models/job.py:21` but has no handler registered anywhere in `app/` — dead
enum member, see Unresolved) and `JobStatus`. `app/jobs/__init__.py` —
`register_handler`, `enqueue_job`. `app/jobs/worker.py` — `JobWorker` (a daemon
thread per process), `claim_next_job` (atomic `UPDATE ... WHERE status='queued'`
claim), `recover_zombie_jobs` (marks `RUNNING` jobs older than 1h as `FAILED` on
startup — `app/jobs/worker.py:26,64-81`). `app/jobs/handlers.py` — the actual
handler bodies (`run_checks_handler`, `run_batch_handler`); AI job handlers live
in `app/ai/overview.py` (`run_overview_job`, `run_overview_batch_job`).
Two `JobWorker` instances run in the same process (`app/main.py:108-113`): one
excludes `AI_JOB_KINDS`, one accepts only them — this is deliberate, so a slow
LLM call never blocks the check-running queue (ADR #21 §5). **Seam — new job
kind:** add to the `JobKind` enum (`app/models/job.py:19-25`), write a handler
`(payload: dict, session: Session) -> dict | None` in `app/jobs/handlers.py` (or
a dedicated module), call `register_handler(JobKind.X, handler)` in the
`lifespan()` block of `app/main.py:82-96`. If the handler calls an LLM, add the
kind to `AI_JOB_KINDS` (`app/models/job.py:29-31`) so it routes to the AI
worker.

### `app/ai/` — assistant, read-only tools, per-check overview
`client.py` — OpenAI-SDK client factory + primary/fallback chain. `config.py` —
DB-backed settings (`ai_settings` table) with a 30s process-level cache; env vars
only seed first-run defaults (see §4/§6 for the test-isolation trap this
causes). `tools.py` — `TOOL_SCHEMAS` (OpenAI function-calling schema) +
`TOOL_REGISTRY: dict[str, Callable]` (`app/ai/tools.py:826-838`), all read-only.
`sql_tool.py` — the one tool that runs LLM-generated SQL, gated by an allowlist
of `v_*` views, `PRAGMA query_only=ON`, and a hard `LIMIT`. `system_prompt.py` —
assembles head instructions + check catalog + page context. `guardrails.py` —
post-process regex filters (forbidden phrases implying the AI "decided" something
on the officer's behalf). `limits.py` — rate limit + daily budget cap, raised as
`HTTPException` before the LLM call. `cost.py` — static USD/1M-token pricing
table. `usage.py` — `record_usage`, the single append-only ledger writer
(`ai_usage` table) all billable calls must go through (ADR #21 §10).
`overview.py` / `overview_stats.py` / `overview_content.py` — the per-check
"tổng quan" (overview): `overview_stats.py` computes a number table in pure
Python (`aggregate_json`, shown even if the LLM fails), `overview_content.py`
sends only that table to the LLM and post-verifies every number in the model's
prose is a literal substring of the pre-formatted table (`app/ai/
overview_content.py:1-11`) — flags `needs_review` on mismatch rather than
silently publishing. `retention.py` — 24h background cleanup loop.
`ingest_doctor.py` — optional LLM escalation when `pipeline/validate.py`'s
heuristics can't explain a bad file; not called from any check or ingest path
by default. `conversation_scope.py` — the "which company is this chat about"
inference (ADR #20), always filtered through `scoping.py`'s
`allowed_company_codes` so a scope label can never widen access.
**Seam — new AI tool:** add a schema object to `TOOL_SCHEMAS` and an
implementation function in `app/ai/tools.py`, register it in `TOOL_REGISTRY`
(`app/ai/tools.py:826-838`); gate behind a settings flag via `_GATED_TOOLS`
(`app/ai/tools.py:842`) if it should be toggleable; add to
`_GUARD_COMPANY_CODE` (`app/ai/tools.py:863`) or `_INJECT_ALLOWED`
(`app/ai/tools.py:868`) for company-scope enforcement.

### `app/models/` + `app/database.py` — schema
See §3.

### `app/items/` — item-level (mã NVL/TP) drill-down
`operations.py` — customs-code → import/export/other classification table
(Thông tư 38/2015, sửa đổi 39/2018). `aggregations.py` — DB queries for one
item's history across `NvlBalance`/`SpBalance`/`Norm`/`DeclarationLine`.
`charts.py` — pure geometry functions (sparkline points, waterfall, sankey) with
no Jinja/DOM coupling, unit-tested directly.

### Cross-cutting: `app/auth.py`, `app/auth_users.py`, `app/scoping.py`,
`app/app_settings.py`, `app/audit.py`, `app/login_guard.py`, `app/books.py`,
`app/slugs.py`, `app/catalog_full.py`, `app/version.py`. Notably `app/
app_settings.py` is a *second*, independent 30s cache (runtime toggles like
`combos_enabled`) from `app/ai/config.py`'s settings cache — same pattern,
different table, both process-local (multi-worker deploys see up to 30s
propagation lag, documented at `app/app_settings.py:5-6`).

## 3. The data model that matters

Engine setup: `app/database.py:10-12` — one SQLAlchemy engine bound to
`settings.database_url` **at module import time**; SQLite pragmas set on every
connection (`app/database.py:15-28`): `foreign_keys=ON`, `journal_mode=WAL`,
`busy_timeout=5000`. `SessionLocal` is `autoflush=False, autocommit=False`
(`app/database.py:12`) — objects added to a session are not visible to queries
on that same session until an explicit `flush()`/`commit()` (see the score-cache
trap in §6).

**Companies.** `companies` (`app/models/company.py:9-23`): `code` (internal key,
used for filesystem paths and AI references), `slug` (URL-facing, stable once
set), `risk_score` (a denormalized cache — see §6, do not trust it as current
truth). `company_periods` (`app/models/company_period.py:19-34`): one row per
(company, year), carries the inferred or officer-set `(period_from, period_to)`
window and `data_version` (an integer bumped on every `ingest()`, independent of
wall-clock — used for staleness detection, not a timestamp,
`app/models/company_period.py:27-30`).

**Tầng 1 (raw fact) tables**, all keyed by `(company_id, period_year, ...)`:
`nvl_balances` (Mẫu 15, NVL = nguyên vật liệu / raw material balance,
`app/models/bcqt.py:9-33`), `sp_balances` (Mẫu 15a, SP/TP = thành phẩm /
finished-goods balance, `app/models/bcqt.py:36-59`), `norms` (Mẫu 16,
material-per-product consumption norms, `app/models/bcqt.py:62-83`),
`declaration_lines` (BCCT, `app/models/declaration.py:14-41`). Each of the
first three carries a `book: str | None` column (`app/models/bcqt.py:17,44,70`).
`declaration_lines` never carries `book` — one declaration list is shared across
all books of a legal entity (`app/models/data_file.py:45-47`).

**Book (sổ quyết toán) semantics.** A "book" is a settlement sub-ledger: one
legal entity (pháp nhân) can run more than one customs regime type in parallel
(e.g. its own EPE — chế xuất/export-processing — production plus GC —
gia công/toll-processing — for another owner) and each regime keeps its own
Mẫu 15/15a/16 with independent opening/closing balances
(`.ai/GLOSSARY.md:107-111`). `book IS NULL` on a Tầng 1 row means "single-book
entity, this axis doesn't apply" — no book chrome shown. `book IS NULL` on a
`Finding` (`app/models/finding.py:26`) is different and **overloaded**: at a
single-book entity it means the same "not applicable"; at a *multi-book* entity
(`app.books.is_multi_book`, `app/books.py:72-74`, true when ≥2 non-null books
exist in that company's year of Tầng 1 data) it means the finding is
**cross-book** — produced by a check that reconciles the declaration list
(shared, book-less) against the UNION of all books, and therefore cannot be
attributed to one book (`.ai/GLOSSARY.md:119-124`). The UI renders this third
state as "Liên sổ" (`app/books.py:25`, param `?book=chung`), kept separate from
"Tất cả" (= EPE ∪ GC ∪ Liên sổ) — never silently folded into either real book.
`app.books.company_books()` derives the book set from Tầng 1 data only, never
from findings, because a clean book with 0 findings is still a book
(`app/books.py:51-56`).

**Findings (Tầng 2).** `findings` (`app/models/finding.py:11-39`):
`(company_id, period_year, check_code)` + `severity`, `subject_key` (the item/
material code the finding is about), `evidence_refs` (JSON list of `{"table":
str, "id"|"filter": ...}` pointing back to Tầng 1 — never a hard FK, by design,
ADR #12), `status` (new/... — officer-editable, survives re-run). No unique
constraint on `(company_id, period_year, check_code, subject_key)` — a check's
`run_checks()` wipes and reinserts the whole set for its codes every run (see
§4), so ids are not stable identifiers across runs.

**Check bookkeeping (WS3).** `check_runs` (`app/models/check_run.py:22-44`) — one
row per `(company_id, period_year, check_code)`, upserted on *every* run of
`run_checks()` including 0-finding runs (cannot be derived from `findings.
created_at`, which has no row when a check fires nothing —
`app/models/check_run.py:1-9`). `check_overviews`
(`app/models/check_overview.py:34-87`) — one row per `(company_id, period_year,
check_code)`, holds the LLM-authored `sections_json` plus the independently
computed `aggregate_json`, and `based_on_run_at`/`based_on_data_version`
snapshots used to detect staleness against `check_runs.ran_at` and
`company_periods.data_version`.

**Jobs.** `jobs` (`app/models/job.py:41-69`): `kind`, `payload` (JSON),
`status` (queued/running/done/failed), `result`/`error`.

**AI.** `ai_settings` (key-value config, `app/models/ai.py:23-37`),
`ai_conversations` (one row per chat thread, `company_id` nullable — ADR #20,
`app/models/ai.py:40-63`), `ai_messages` (one row per turn, audit trail,
`app/models/ai.py:102-129`), `ai_usage` (append-only cost ledger, the only
source the daily budget cap reads, distinct from the cost fields duplicated on
`ai_messages`/`check_overviews` — `app/models/ai.py:66-99`).

**Scoring.** `company_year_scores` (`app/models/score.py:17-34`) — one row per
(company, year), the current source of truth for risk score. `companies.
risk_score` is a derived, denormalized cache of `max(company_year_scores.score)`
across years for that company — see §6 for why this drifts.

## 4. Invariants a change must not break

1. **Every finding traces back to a Tầng 1 row via `evidence_refs`.**
   Enforced by convention in each check's `_evidence_*` helper (e.g.
   `app/checks/c1_quantity.py:24-47`), not by a DB constraint (ADR #12 chose
   JSON filter refs over hard FKs, `.ai/DECISIONS.md:84-95`). **Guarding test:
   only for dynamic (`X.*`) checks** — `tests/test_dynamic_checks/
   test_sql_runner.py:50`, `tests/test_dynamic_checks/
   test_pipeline_integration.py:41`. None of `tests/test_checks/test_c1..c6_*.py`
   assert `evidence_refs is not None`/shape for the 17 built-in checks — they
   assert `subject_key`/`severity`/`book`, not traceability. **No guarding test
   for the built-in check path.**

2. **Checks run through the job queue, never synchronously inside a request
   handler.** The normal path: `POST /companies/{code}/run-checks`
   (`app/routes/companies.py:1405-1459`) always calls `enqueue_job(...,
   kind=RUN_CHECKS|BATCH_RUN)` and redirects to `/jobs/{id}` — never calls
   `run_checks()` directly. **Documented exception:** the confirm-review path
   at `app/routes/companies.py:1298-1300` runs `run_checks()` inline as a
   "rare fallback" when the session user row can't be resolved to a DB user
   (`ur is None`), with a Vietnamese comment acknowledging it. **No test
   exercises this fallback branch** (grepped `tests/` for the comment text and
   for direct calls to `run_checks(` outside a job handler in that code path —
   none found). Guarding tests that exist: `tests/test_jobs/test_dispatch.py`
   (job lifecycle), `tests/test_ws3_foundation.py` (checks `run_checks()`
   itself is job-queue-invoked-equivalent by testing `check_runs` upsert
   behavior across repeated calls) — none of these assert routes never call
   `run_checks` synchronously; that's enforced only by code review.

3. **LLM calls never happen inside rule logic.** `app/checks/` imports
   `app.ai` in exactly one place — `spec_gen.py`, which composes a *check
   definition* from natural language at authoring time (admin clicks "soạn
   check"), not during `run_checks()`/`sql_runner.run_check()` execution.
   Verified by `grep -rl "app\.ai" app/checks/` → only `spec_gen.py`. **No
   automated test or lint rule enforces this** — it's an architectural
   convention checked by inspection, not CI.

4. **Findings are deleted and recreated on every check re-run; ids are not
   stable.** `run_checks()` issues a `DELETE ... WHERE check_code IN
   codes_to_run` before re-inserting (`app/pipeline/run_checks.py:78-104`).
   **Guarding test for dynamic checks:** `tests/test_dynamic_checks/
   test_pipeline_integration.py:55` (`test_sql_check_findings_wiped_on_rerun`)
   and `:72` (`test_scoped_rerun_of_dynamic_check_does_not_duplicate`).
   **For built-in checks:** no test directly asserts a `Finding.id` changes
   across two `run_checks()` calls; `tests/test_ws3_foundation.py` tests that
   `check_runs.finding_count` matches the live finding count after re-run,
   which indirectly requires the wipe-then-reinsert behavior but does not name
   it as an id-instability guarantee. Because finding ids are unstable,
   anything that stores a raw `finding.id` across a check re-run (rather than
   `(company_id, period_year, check_code, subject_key)`) will silently point
   at the wrong row or a deleted one — `app/pipeline/data_files.py`'s comment
   at `app/routes/companies.py:1258-1262` calls this out explicitly for why
   `evidence_refs` filters by material/product code, not by Tầng-1 row id.

5. **A settlement Tầng 1 ingest plan that would lose a book raises before
   deleting anything.** `IngestPlanError` (`app/pipeline/ingest.py:69-75`) is
   raised *before* the delete-then-reload of `(company, year)` — silent book
   loss during re-ingest was judged worse than a loud failure. No test file
   name surfaced for this specifically in the grep pass; check
   `tests/test_ingest_book.py` if touching this path (not read in full during
   this survey — see Unresolved).

## 5. How to run it

```bash
make install        # venv + pip install -e ".[dev]"
make migrate         # alembic upgrade head (config: alembic.ini, dir: migrations/)
make dev              # uvicorn app.main:app --reload --host 0.0.0.0 --port 8200
make test              # pytest (testpaths = tests/, from pyproject.toml)
make lint                # ruff check app tests scripts
make format                # ruff format app tests scripts
make migration              # alembic revision --autogenerate (prompts for message)
```
(`Makefile:1-40`; note `make dev` binds port 8200, not the `localhost:8000` the
README currently states — README is stale on this point.)

**Tests must not run against the ambient dev DB.** `settings.database_url`
defaults to `sqlite:///./audit_hq.sqlite` (`app/settings.py:9`) — the real,
large, pilot-data-filled file that sits at the repo root
(`/home/vp/workspace/client/audit-hq-mvp/audit_hq.sqlite`, ~337MB at the time of
this survey). `app/database.py`'s engine binds to that URL **at import time**
(`app/database.py:10-12`), and `tests/conftest.py`'s autouse fixture
`_ensure_default_schema` (`tests/conftest.py:23-32`) runs
`Base.metadata.create_all()` against that *default* engine, not an isolated one
— most fixtures use an isolated in-memory `session` fixture (`tests/
conftest.py:35-69`), but any code path that calls `get_setting(...)` or similar
without passing `db=` explicitly falls through to `SessionLocal()`
(`app/ai/config.py:196-197`) and reads/writes the real dev DB. Always run:
```bash
DATABASE_URL="sqlite:///<empty-file-path>" .venv/bin/python -m pytest -q
```
CI (`.github/workflows/deploy.yml:6-22`) gets this "for free" because it runs
in a fresh checkout with no ambient `audit_hq.sqlite`, and only runs **after**
merge to `main` (`on: push branches:[main]`) — there is no PR-time check, so a
false-green run on a developer's machine is the only signal before merge.

## 6. Traps that have actually cost time before

- **SQLite WAL sidecar files.** The DB runs `journal_mode=WAL`
  (`app/database.py:26`); recently committed data can live in `audit_hq.sqlite-
  wal` until checkpointed. `cp audit_hq.sqlite backup.sqlite` (main file only)
  silently produces a stale backup missing anything not yet checkpointed —
  this has caused a `no such column` error after a copy missed a migration's
  data. Copy/back up all three files (`{db},-wal,-shm`), or `PRAGMA
  wal_checkpoint(TRUNCATE)` first, or use `sqlite3.Connection.backup()`
  (pattern used in `scripts/guide_screenshots.py:20-21`). The backup command
  recorded in `.ai/STATUS.md` (plain `cp`) is not WAL-safe.

- **CSS `[hidden]` loses the specificity fight.** Three confirmed instances,
  same bug shape: a class selector with `display: flex` declared *after* the
  attribute selector `[hidden] { display: none }` wins on specificity-then-
  source-order, so `hidden` stops actually hiding the element. Fixed at
  `app/static/sidebar.css:99-102` (`.ai-history-panel[hidden]`),
  `app/static/sidebar.css:536-539` (`.ai-scope-bar[hidden]`), and
  `app/static/style.css:1956-1958` (`.draft-overlay[hidden]`) by adding an
  explicit `.class[hidden] { display: none }` rule after the flex/grid
  declaration. Any new toggle-shown element with a non-`display:none` visible
  state needs this pairing from the start.

- **The `company.risk_score` cache only reflects the max across years and can
  drift from `company_year_scores` after a scoring-rule change.**
  `run_checks()` sets `company.risk_score = max(all_scores_with_current)`
  (`app/pipeline/run_checks.py:187-192`), same pattern in
  `app/pipeline/recompute.py:53-59`. This field is **not** recomputed when
  denominators/rules change — only when `run_checks()`/`recompute.py` next
  touches that (company, year). A real incident: two companies with identical
  underlying data showed different list-page scores (30 vs 28) because one had
  been re-scored after a rule change (C2.4 threshold, denominator changed) and
  one hadn't (`.ai/sessions/2026-06-11-demo-data-upload-decouple-validate-
  ai.md:87-91`). Fixed for the human-facing page:
  `app/routes/companies.py:181-197` (`list_companies`) now reads
  `max(CompanyYearScore.score)` directly and ignores the cache, guarded by
  `tests/test_companies_list.py:1-2,43-58`
  (`test_list_shows_max_cys_not_stale_risk_score`, sets a deliberately-stale
  `Company.risk_score` and asserts the page shows the fresh value instead).
  **Not fixed for the AI tool surface:** `app/ai/tools.py:548`
  (`_list_companies`, backing the `list_companies` AI tool) still orders and
  reports by `Company.risk_score.desc()` — the same stale field, unguarded by
  an equivalent test (`tests/test_ai_tools.py:180`,
  `test_list_companies_sorted_by_risk`, seeds `Company.risk_score` directly and
  never exercises `CompanyYearScore` staleness). `app/ai/sql_tool.py:101`
  exposes the same cached column through a view. A rule change today can make
  the human company list and the AI's answer to "top 3 riskiest companies"
  disagree, and nothing in the test suite would catch it.

- **`autoflush=False` sessions mean writes inside the same request/job aren't
  visible to a subsequent query until `flush()`.** `SessionLocal` is created
  with `autoflush=False` (`app/database.py:12`). `run_checks()` relies on this
  explicitly: it calls `s.flush()` before reading back `Finding` rows for combo
  detection (`app/pipeline/run_checks.py:138`) and again before reading
  `all_year_findings` for scoring (`app/pipeline/run_checks.py:152`) — omitting
  either flush would silently score/combo against a stale (pre-this-run)
  finding set rather than raising.

- **Never `pkill -f uvicorn` / `pkill -f "uvicorn.*PORT"` on this machine.**
  The user's own dev server (typically on `:8200`) can share process-name
  patterns with a throwaway server spun up for screenshots, and `pkill -f`
  matching against the full command line can match its own invocation string
  and kill the wrong (or the calling) process. A prior incident:
  `pkill -f "uvicorn.*8222"` killed the shell that issued it because the
  command line itself contained the pattern
  (`.ai/sessions/2026-06-11-demo-data-upload-decouple-validate-ai.md:76-77`).
  Kill throwaway servers by PID from a pidfile, `setsid` them, and never target
  by name/pattern.

## 7. First-task checklist

**Changing or adding a check (`C*`/`X.*`):**
1. Read `.ai/DECISIONS.md`'s ADR #18 block (WS1 evidence model, ~line 300) if
   the check reads a Tầng 1 column individually rather than as a sum — that
   determines whether `balance-checked` parse evidence is strong enough.
2. Read the relevant `app/checks/cN_*.py` file and its `_evidence_*` helpers.
3. Add/adjust the `CHECK_COLUMNS` entry in `app/checks/registry.py:377-413` if
   the set of `(slot, field)` the check reads changes — this drives which
   checks re-run automatically when an officer edits a column mapping
   (`app/routes/companies.py:1258-1300`).
4. Write `tests/test_checks/test_cN_*.py` first (AGENTS.md, `/tdd` skill) with
   a 3-5 row Excel-shaped fixture via `tests/conftest.py`'s `add_nvl`/`add_sp`/
   `add_decl` helpers.
5. Run with an isolated `DATABASE_URL` (§5) before considering it green.
6. If the check's description/threshold differs from the 49-check catalog in
   the sibling `audit-hq` repo, stop — CLAUDE.md/AGENTS.md forbid changing
   catalog semantics here before the sibling repo (`de-an-audit-hq.md`) is
   updated.

**Changing or adding a screen (`app/routes/*.py` + template):**
1. Identify the router file that owns the URL prefix (§2 module map).
2. Confirm the route calls `get_company_or_404` (`app/scoping.py`) if it's
   `{code}`-scoped — 404, not 403, on out-of-scope access.
3. If the change triggers check execution, go through `enqueue_job` +
   `JobKind`, not a direct `run_checks()` call (§4 invariant 2) — check
   `app/routes/companies.py:1405-1459` as the canonical pattern.
4. Templates live under `app/templates/`; static assets under `app/static/` —
   if adding a JS-toggled element, pair its visible-state rule with an
   explicit `.class[hidden] { display: none }` override (§6).
5. Screenshot proof convention (if UI-visible): committed proof goes to
   `.ai/features/<slug>/screenshots/` next to a `ui_smoke.py`; scratch
   screenshots stay in the gitignored throwaway dir. Never run against the
   user's live `:8200` server or its DB.

## Unresolved

- `JobKind.INGEST_AND_RUN` (`app/models/job.py:21`) has no registered handler
  anywhere under `app/` — unclear whether it's planned-but-unbuilt or dead code
  left from a refactor. Did not find a session/ADR note explaining it.
- `tests/test_ingest_book.py` exists and its name suggests it covers the
  `IngestPlanError` book-loss-prevention path (§4 invariant 5), but it was not
  read in full during this survey — confirm its coverage before relying on it
  as the guard for that invariant.
- CLAUDE.md and AGENTS.md both state "16 kiểm tra MVP" (16 MVP checks); the
  registry currently has 17 registered `CheckSpec` entries
  (`ALL_CHECKS`/`SPECS` both length 17, verified by import). Not flagged
  elsewhere as an intentional catalog change in `.ai/DECISIONS.md`'s ADR
  index — likely just a stale count in the two rule files, but confirm with
  the user before treating either number as authoritative.
- README.md says `make dev` serves on `localhost:8000`; the Makefile binds
  `--port 8200`. Cosmetic, but will cost a new developer a few minutes.
