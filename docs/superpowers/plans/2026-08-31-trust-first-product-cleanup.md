# Trust-First Product Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline execution for this plan in the current working tree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the platform's first impression, reliability, and maintainability without a risky full rewrite.

**Architecture:** Keep the current stdlib Python backend and vanilla frontend. Apply narrow fixes in source connectors, API response behavior, and the first-screen UI layer.

**Tech Stack:** Python 3.13, vanilla HTML/CSS/JS, Supabase REST, agent-browser for smoke/a11y verification.

## Global Constraints

- Preserve existing Arabic RTL UX.
- Do not remove user-facing features.
- Delete only confirmed generated or unreferenced files.
- Avoid framework migration in this pass.
- Use focused tests and a browser smoke test before completion.

---

### Task 1: Reliability Fixes

**Files:**
- Modify: `backend/connectors/market_ads.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `backend.services.request_parser.detect_area_in_text(text: str) -> str`
- Produces: bounded `/api/health` and safer `/api/analyze` behavior

- [x] Add the missing `detect_area_in_text` import in `market_ads.py`.
- [x] Bound slow Supabase source-count calls in `_build_health_payload`.
- [x] Bound slow post-report persistence/demand calls in `/api/analyze`.
- [x] Ensure `/api/analyze` pushes a terminal progress state on exceptions.
- [x] Run focused backend tests.

### Task 2: First-Screen UX & Accessibility

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/app.js`
- Modify: `frontend/components/a11y-enhancements.js`

**Interfaces:**
- Consumes: existing `sendChat`, `switchMainTab`, and progress UI
- Produces: clearer search-first screen and valid tab semantics

- [x] Move secondary more navigation outside the ARIA tablist.
- [x] Add explicit labels/roles for result live region.
- [x] Make the first screen search-first by reducing hero height and ordering search before results/tools.
- [x] Sync `aria-selected` when `switchMainTab` changes tabs.
- [x] Run browser and a11y checks.

### Task 3: Cleanup

**Files:**
- Remove: generated review screenshots created during this audit.
- Evaluate: untracked office/presentation artifacts only after reference scan.

**Interfaces:**
- Produces: cleaner working tree without deleting likely user assets.

- [x] Search references before deletion.
- [x] Remove confirmed temporary files.
- [x] Report files intentionally left untouched.

### Task 4: Verification

**Files:**
- No implementation files unless verification reveals regressions.

**Interfaces:**
- Produces: evidence-backed status.

- [x] Run targeted pytest suite.
- [x] Start local server and run browser smoke test.
- [x] Run agent-browser a11y audit.
- [x] Summarize remaining risks.
