# AI Agents Supabase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trackable AI providers, deterministic analysis agents, Supabase audit tables, and Arabic documentation.

**Architecture:** Keep valuation deterministic. Route AI through `backend/services/ai_router.py`; expose agent traces from a focused `analysis_agents.py`; persist AI/agent audit rows through `supabase_store.py`.

**Tech Stack:** Python 3.13, plain HTTP backend, Supabase REST, vanilla HTML/CSS/JS frontend.

## Global Constraints

- Do not make LLM output the source of prices or valuation numbers.
- Every external/free AI provider must have fallback.
- Supabase writes must be best-effort and must not break user analysis.
- Work in the current checkout because the repository already has many uncommitted changes.

---

### Task 1: AI Router Provider Upgrade

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/services/ai_router.py`
- Test: `tests/test_ai_router.py`

**Interfaces:**
- Produces: `_try_nvidia_nim(system, user, model="", temperature=0.4) -> dict | None`
- Produces: `get_last_ai_attempts() -> list[dict]`

- [x] Add NVIDIA config defaults.
- [x] Add provider implementation using OpenAI-compatible `/chat/completions`.
- [x] Track provider attempts.
- [x] Extend tests.

### Task 2: Analysis Agent Trace

**Files:**
- Create: `backend/services/analysis_agents.py`
- Modify: `backend/services/report_generator.py` or `backend/main.py`
- Test: `tests/test_analysis_agents.py`

**Interfaces:**
- Produces: `build_analysis_agent_trace(request, report, statuses, ai_insights) -> dict`

- [x] Build deterministic agent summary.
- [x] Include source, quality, valuation, demand, and report agents.
- [x] Attach trace to API report.
- [x] Add tests.

### Task 3: Supabase Audit Persistence

**Files:**
- Create: `supabase/migrations/024_ai_agents_audit.sql`
- Modify: `supabase/setup_all.sql`
- Modify: `backend/services/supabase_store.py`
- Test: `tests/test_supabase_store.py`

**Interfaces:**
- Produces: `save_ai_provider_runs(request, attempts) -> None`
- Produces: `save_analysis_agent_trace(request, trace) -> None`

- [x] Add idempotent migration.
- [x] Add best-effort persistence.
- [x] Add tests proving rows are shaped correctly.

### Task 4: Frontend Visibility

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

**Interfaces:**
- Consumes: `report.agentTrace`
- Displays: analysis agents and provider status in results.

- [x] Add compact trace panel.
- [x] Render only when analysis returns data.
- [x] Keep mobile layout without horizontal overflow.

### Task 5: Arabic Documentation And Verification

**Files:**
- Create/Modify: `README_AR.md`

- [x] Explain project, tabs, APIs, Supabase, AI providers, and deployment.
- [x] Run compile, pytest, JS checks, API smoke, and Playwright smoke.
