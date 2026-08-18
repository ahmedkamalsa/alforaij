# AGENTS.md — منصة الفريج (alforaij-research-assistant)

## Environment & tooling
- Default `python` (3.13) has **no pytest**; run tests with Python 3.11: `/c/Users/hello/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/ -q` (pytest 8.4.2, baseline 245 passed).
- Playwright works on the default 3.13; `pypdf`/`reportlab` are on 3.11. `pdfplumber` is **not** installed.
- On Windows, prefix Python commands with `PYTHONIOENCODING=utf-8` — Arabic output otherwise breaks stdout.
- `npx skills find` returns low-install forks (e.g. a 130-install `just-scrape` clone); cross-check results against the skills.sh leaderboard before recommending — the canonical package usually lives under the original owner's repo.
- PIL cannot shape Arabic; use `arabic_reshaper` + `python-bidi` (both installed). Arabic-capable system fonts exist at `C:/Windows/Fonts/` (e.g. `arabtype.ttf`).

## Verification environment (Freebuff Preview)
- `preview_screenshot` is **unavailable** in this environment ("no frames") — verify rendering via `preview_snapshot` + `preview_evaluate` geometry probes + `preview_logs` instead.
- The Preview server serves **only the registered HTML file**; sibling asset paths 404. To display fonts/images in a preview doc, embed them as data URIs.
- Console 404s during dev against a static server are `/api/*` fallback noise — console messages don't carry URLs, so use **response-level** tracking to see which requests fail. On real static hosting `STATIC_SNAPSHOT_MODE` skips `/api/*` entirely.
- The app honors `prefers-color-scheme` when no localStorage preference exists (headless Chromium defaults to light) — theme-toggle checks must account for which theme actually applies.

## Verification discipline
- The `:focus-visible` ring is a **single unqualified rule** (currently ~`styles.css:352`) using `--ring-width/--ring-color/--ring-offset` tokens; `--ring-color` is `--brand-gold-300` (dark) / `--brand-navy-300` (light). It was consolidated in commit `b8a9197` (the earlier duplicate rule was deleted). Keep it single and later in the cascade, or a same-specificity rule will shadow it. Programmatic `.focus()` does NOT match `:focus-visible` — verify with real keyboard Tab (see `tests/playwright/focus_ring_check.py` / `focus_ring_board_check.py`: `ALFORAIJ_MOBILE_BASE=… python …/Python313/python.exe tests/playwright/focus_ring_check.py --dark|--light`). Component focus styles must not set `outline: none` in a `:focus-visible` block or the ring dies there (fixed for `.board-stat`, `.results-copy-sources`, `.development-card`).
- Full UI regression runs need the **API-backed server** (backend defaults to port 8000, serves frontend too): `ALFORAIJ_MOBILE_BASE=http://localhost:8000 python tests/playwright/testsprint_audit.py` → 33/33. Against a bare static server it yields 26/29 with 3 *known* static-mode failures.
- `scripts/run_mobile_checks.py` and `scripts/run_performance_checks.py` manage server lifecycle themselves (start → health wait → stop). Performance bounds: cold ≤8s, warm ≤2s (typical first load ~870ms).
- pypdf extracts Arabic as **presentation forms** — normalize with `unicodedata.normalize("NFKC", ...)` before string comparisons in tests.

## CI / GitHub Actions quirks
- `GITHUB_STEP_SUMMARY` Markdown links resolve relative to the **repository root** on GitHub.com, not the script's filesystem path. Use `docs/foo.md`, not `../docs/foo.md`.
- Daily scripts (`check_harvest_governorates.py`, `send_opportunity_alerts.py`) share an `_emit()` pattern: writes to `GITHUB_STEP_SUMMARY` if set, else stdout. Both are called from `.github/workflows/daily-data-update.yml`.

## Architecture & constraints
- **area_governorate_map import chain**: `main.py` re-exports `_area_governorate_map`, `_normalize_dashboard_place`, `_normalize_governorate_name` from `request_parser.py` (with `_` prefix aliases, `# noqa: E402`). Tests and scripts import from `main.py`, not directly from `request_parser.py`. If you move these functions, update 12+ import sites across `tests/` and `scripts/`.
- Deliberately dependency-free: stdlib Python + static HTML/JS/CSS. **No package.json, no Tailwind, no Node build** — don't add dependencies.
- Deployed sites are static snapshots (`STATIC_SNAPSHOT_MODE`): no live API on hosted URLs — all numbers visitors see are snapshot data. The live backend (`http.server` stdlib, port 8000) is not hosted anywhere.
- A PDF report subsystem exists and is tested: `backend/services/pdf_report.py` (reportlab + arabic_reshaper/bidi, Tahoma→DejaVu→Helvetica fallback) with `tests/test_pdf_report.py` (9 tests) — including a dedicated demand-indicator page when the report carries `demandIndicators` and generators in `scripts/generate_*_pdf.py`; `reports/*.pdf` are git-tracked deliverables. It loads logos from `frontend/assets/` via `__file__` (not CWD) — deleting/moving those PNGs silently degrades headers to a drawn «ف» fallback.
- **Three** workflows deploy on push to `main`, all watching `frontend/**`: `deploy-static.yml` (Netlify prod), `deploy-cloudflare-pages.yml`, and `deploy-alforaijboard.yml` (force-pushes the static frontend to the gh-pages branch of `ahmedkamalsa/alforaijboard` — live at `https://ahmedkamalsa.github.io/alforaijboard/`; needs `ALFORAIJBOARD_TOKEN`). Netlify/CF deploys are **guarded**: missing secrets emit `::warning::` and skip, never fail the workflow. That gh-pages URL serves the same unified app — it went stale once and showed the removed «لوحة الأرقام والفرص» button, which is why the workflow was re-added; never delete it while the URL must stay current.
- `pytest.yml` runs the backend suite (`python -m pytest tests/ -q`) on push/PR touching `backend/**` or `tests/**` (Python 3.11; no secrets needed — the `unittest`-in-sys.modules gate keeps network reads off in tests).

## Design system (frontend/styles.css)
- Brand identity: navy `#0a2f91` + gold `#e2c968`; Kufi display + Tajawal body; glass panels. Token layers live in `:root` (brand gold 100–900, navy 100–600, radius scale, ring, motion tokens) — consumed only in the identity block; ~150 hardcoded radius values remain elsewhere (drift 7/9/10/14px around the 8/10px norm).
- Brand button = circular icon + official name, navy/gold with hover color swap. Badge adapts on small screens (hide English sub-line, shrink name).

## Product decisions (user corrections — respect these)
- The «المصادر والتشغيل» tab was **deliberately deleted** — product has 5 main tabs (search / opportunities / board / insights / developments). Do not re-add it; tests assert 5.
- Never list un-integrated platforms (Property Finder, Aqarmap, Bayut, e.gov.kw, Kuwait Finder) as "unavailable" in the UI — only show real, working sources; integrate or omit.
- The standalone board page (`frontend/board.html` + its hero button) was **deleted** at user request; the board lives only as the embedded «لوحة السوق» tab in `index.html`. Light/dark toggle must exist.
- The xlsx exports on disk disagree: `offer-evidence.xlsx` = 275 records vs `offer-evidence (1).xlsx` = 171 (newer) — unresolved which is canonical; do not delete either without confirmation.
