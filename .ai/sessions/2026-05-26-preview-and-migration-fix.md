# Session 2026-05-26 — Preview endpoint + migration fix

## What was done

### 1. Fix migration 646b92a93768 (critical bug)

Migration `646b92a93768_add_check_definitions_table` was auto-generated with an empty `upgrade()` (`pass` only). Alembic stamped the version but never created the table — production showed `no such table: check_definitions` despite `alembic current` reporting `head`.

Root cause: migrations are baked into the Docker image at build time (`COPY migrations ./migrations` in Dockerfile). Running `alembic upgrade` on the old container executed the empty migration.

Fix:
1. Added actual DDL to `upgrade()`: `op.create_table(...)` with all columns + 3 indexes
2. Committed and pushed the fix
3. Rebuilt Docker image on prod to pick up new migration file
4. `alembic stamp 46b3bcaebbe4` + `alembic upgrade head` to re-run migration properly

### 2. Create and publish check X.1 in production

Created `CheckDefinition` X.1 directly via Python in the Docker container:
- kind: `cross_table_match`
- Compares `nvl_balances.import_qty` (sum per material_code) vs `declaration_lines.quantity` (sum per item_code, filter customs_code IN ['E11','E31'])
- Thresholds: <1%→null, <5%→info, <10%→warning, ≥10%→critical
- Status: PUBLISHED immediately

Enqueued BATCH_RUN job #5 for DN_001 — produced 10 X.1 findings for 2023, including one at 80.2% deviation (critical: material BBD).

### 3. Preview endpoint + UI panel (TDD)

**New endpoint:** `POST /admin/checks/{check_id}/preview`
- Body: `{company_code: str, year: int}`
- Runs `DynamicCheckRunner.run()` dry-run — no findings written to DB
- Returns: `{findings: [{title, severity, subject_key, details}], count, error}`
- 404 if check not found; error JSON if company not found

**Template changes:**
- `checks_detail` route now passes `companies` list to template context
- Added "▶ Chạy thử" panel at bottom of `admin_checks_detail.html`: company select + year input + button + inline results table with severity colors

**5 new tests** in `TestPreviewCheck`: returns findings, no findings, unknown company → error, 404 on missing check, requires admin.

**Total tests: 390 (76 in test_dynamic_checks/, 11 in test_spec_gen.py newly tracked)**

## Commits this session

- `1515875` — fix(migration): add actual DDL to check_definitions migration
- `6acc6ca` — feat(admin): add preview endpoint and UI panel for dynamic checks

## What didn't work / lessons

- `docker compose exec -T -e DB_DATA_PATH=...` does NOT override env vars already set in the container's environment (set by docker-compose.yml). The `DATABASE_URL` was already set, so `-e DB_DATA_PATH` was irrelevant.
- Empty alembic autogenerate: happens when the model isn't discovered at autogenerate time (likely missing import in `env.py` or `Base` metadata). Always verify migration file has actual DDL before running in production.

## Open items

1. Run BATCH_RUN for DN_002, DN_003, DN_004 to get X.1 findings on all companies
2. AI spec gen test with real Gemini (requires `model_deep` setting configured in `/admin/ai-settings`)
3. Edit check spec from detail page (currently read-only)
4. Scores will be stale after X.1 findings — may want to recompute (`scripts/recompute_all_scores.py`)
