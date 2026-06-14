# Feature showcase page (public)

**Goal:** a single, self-contained HTML page showcasing all Audit-HQ features —
emphasizing the AI assistant / smart capabilities — to share publicly (no login).

## What ships

- `app/static/showcase.html` — self-contained page (inline CSS, base64 JPEG images,
  tiny lightbox JS). ~1.3 MB. Full professional Vietnamese prose.
  **Visual style is the system's own** (`app/static/style.css` tokens): light bg
  `#f6f7f9` + white cards, navy `#1d3557` header bar identical to the app, system
  button/card/badge styles, amber demo banner on top. Bright, not dark; no invented
  landing-page chrome. Screenshots are retina (2×) viewport crops, demo banner hidden.
- **AI section presents capabilities for officers, not tools.** No function names, no
  "tool use" jargon — six plain-language capability cards. The admin AI config screen
  is intentionally excluded (it is dev/admin configuration, not an officer feature).
- Public route `GET /showcase` in `app/main.py` (NO `require_user`) → served to anyone.
  Also reachable at `/static/showcase.html`. Auth on every other route is unchanged.
- Live URL after deploy: **https://audit-hq-demo.tinsu.ai/showcase**

## Sections

Hero → stats → **Trợ lý AI (centerpiece)** → nạp dữ liệu (AI ingest doctor) → 16 kiểm tra
+ 4 combo → chấm điểm minh bạch → truy nguồn → tổng quan → phân quyền + nhật ký → tài liệu → CTA.

The AI band leads on purpose: 6 capability cards, the 12 read-only tools as chips, and 3
screenshots (grounded tool-use answer, @mention, admin AI config + usage).

## Reproduce

Images are committed PNGs (this folder + chat-redesign + permissions-auth folders).
`build_showcase.py` recompresses them PNG→JPEG via ImageMagick `convert`, base64-embeds
into the template, writes `app/static/showcase.html`.

```bash
.venv/bin/python .ai/features/2026-06-14-showcase/build_showcase.py     # rebuild HTML
PYTHONPATH=. .venv/bin/python .ai/features/2026-06-14-showcase/ui_smoke.py  # re-capture screenshots (dev :8200)
```

`ui_smoke.py` seeds a temp admin `shot_show`, captures the core pages, and deletes it.
Deterministic, no LLM calls. Chat screenshots are reused from the chat-redesign feature.

## Notes

- All data shown is anonymized demo data (DN_xxx) — page states this explicitly.
- Screenshots taken at year 2022 for DN_003 (risk 148/1000) to show a non-trivial score
  with the scoring-breakdown `<details>` expanded.
