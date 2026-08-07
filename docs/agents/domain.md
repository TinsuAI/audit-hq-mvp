# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo is **single-context**, but it does **not** use the stock `CONTEXT.md` + `docs/adr/` layout. Its glossary and decision log already exist under `.ai/` and predate these skills. Read those instead — do not create `CONTEXT.md`, `CONTEXT-MAP.md`, or `docs/adr/`.

## Before exploring, read these

| Stock skill term | This repo's file |
| ---------------- | ---------------- |
| `CONTEXT.md` (glossary / ubiquitous language) | `.ai/GLOSSARY.md` |
| `docs/adr/` (architectural decisions) | `.ai/DECISIONS.md` |

Also worth reading before starting work, per `AGENTS.md`: `.ai/STATUS.md` (current state) and the last 2–3 files in `.ai/sessions/`.

`.ai/GLOSSARY.md` defines terms only — no spec, no implementation detail. Identifiers stay in English; prose is Vietnamese with full accents. Follow that convention when adding to it.

## ADR format

`.ai/DECISIONS.md` is a single file, not one file per decision. Entries are grouped under a date heading and numbered:

```markdown
## 2026-07-31 — <short title for the batch>

### 23. <the decision> (2026-07-31, grilling)

**Quyết định:** …

**Lý do:** …

**Alternatives loại:** …
```

Decisions are referenced elsewhere (STATUS, session notes, code comments) as **ADR #N**, so a number, once published, is permanent. Never renumber existing entries.

To add a decision: append a new `## <date> — <title>` section at the end of the file and continue the global sequence from the highest `### N.` already used. The `2026-08-06` section restarted its numbering at `### 1.` — that is drift, not the convention. Continue from the highest number in the file, not from the last section's.

Record a decision only when it is hard to reverse and the reasoning would otherwise be lost. Routine implementation choices do not go here.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `.ai/GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

Business semantics that are *not* project vocabulary — the meaning of a check, the numbering of the 50-check catalog — live in the đề án repo at `../audit-hq/de-an-audit-hq.md` (§4–7). Per `AGENTS.md`, check descriptions are changed there first, never here.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR #18 (parse confidence by evidence label) — but worth reopening because…_

ADRs in this file supersede each other in place: several carry a `SỬA ADR #N` note in their heading. When an ADR you're relying on has been superseded, follow the superseding one.
