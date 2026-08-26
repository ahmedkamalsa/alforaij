# Chat Agents And Concise IA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the chatbot answer by exact intent/region/source while simplifying the main platform navigation and visible actions.

**Architecture:** Keep the current Python stdlib backend and static HTML/JS frontend. Add a small backend chat-agent service that wraps existing request parsing/reporting, fix misleading frontend fallback behavior, and reduce visible UI clutter by moving secondary actions behind concise labels and menus.

**Tech Stack:** Python 3.11/3.13 stdlib, existing backend services, static HTML/CSS/JS, Supabase, existing MCP server.

## Global Constraints

- Do not introduce React, Node build steps, or new frontend frameworks.
- Do not delete existing user workflows: export, save search, WhatsApp, metrics, and source evidence must remain reachable.
- Do not bypass SSL verification to hide external-source failures.
- Arabic UI copy must be short and user-facing: default answer first, details second.
- Do not revert pre-existing dirty or untracked project files.

---

## File Structure

- `backend/services/request_parser.py`: Fix Arabic intent and area/space extraction.
- `backend/services/chat_agents.py`: Add lightweight agent result helpers for intent, region, source, data quality, and answer.
- `backend/main.py`: Attach `chatGuidance` to analyze responses and preserve auth/tier failures.
- `mcp_server/tools.py`: Add `alforaij_answer_chat_query` using backend chat-agent logic.
- `mcp_server/smoke_test.py`: Add a smoke assertion for the new tool.
- `frontend/app.js`: Stop converting 401/403/429 analyze failures to static reports; render concise guidance and error messages.
- `frontend/index.html`: Reduce top-level tabs and search toolbar labels.
- `frontend/styles.css`: Support compact top navigation/action menu without breaking mobile.
- `tests/test_analysis.py` or `tests/test_request_parser.py`: Cover Arabic intent/area fixes.
- `tests/test_server_tier.py`: Cover frontend-facing tier failure contract if existing server tests support it.

---

### Task 1: Parser Accuracy For Arabic Chat

**Files:**
- Modify: `backend/services/request_parser.py`
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `parse_request(text: str)`
- Produces: correct `PropertyRequest.transaction`, `areas`, `min_area`, and `max_area`

- [ ] **Step 1: Write failing tests**

```python
def test_rental_request_phrase_means_wanted_rent():
    req = parse_request("ابي شقة للإيجار في السالمية")
    assert req.transaction == "مطلوب للإيجار"
    assert "السالمية" in req.areas

def test_area_word_without_unit_is_parsed():
    req = parse_request("مطلوب بيت في السالمية بحدود 300 ألف مساحة 400")
    assert req.min_area == 400
    assert req.max_area == 400
```

- [ ] **Step 2: Run targeted parser tests**

Run: `python -m pytest tests/test_analysis.py -q`
Expected before fix: at least one parser failure.

- [ ] **Step 3: Implement minimal parser changes**

Check wanted words before offer words when the sentence contains `ابي/أبي/ابغى/مطلوب` with rent words. Add a regex for `مساحة 400` without a unit.

- [ ] **Step 4: Re-run targeted parser tests**

Run: `python -m pytest tests/test_analysis.py -q`
Expected: parser tests pass.

---

### Task 2: Lightweight Chat Agents

**Files:**
- Create: `backend/services/chat_agents.py`
- Modify: `backend/main.py`
- Test: add focused tests if endpoint helpers are already testable

**Interfaces:**
- Produces: `build_chat_guidance(request, report, source_mode=None) -> dict`
- Output keys: `intent`, `regionDecision`, `sourcePlan`, `dataQuality`, `answer`

- [ ] **Step 1: Create service with pure functions**

```python
def build_chat_guidance(request, report, source_mode=None):
    return {
        "intent": {...},
        "regionDecision": {...},
        "sourcePlan": {...},
        "dataQuality": {...},
        "answer": "..."
    }
```

- [ ] **Step 2: Attach guidance to `/api/analyze` success**

Set `report["chatGuidance"] = build_chat_guidance(...)` after report construction.

- [ ] **Step 3: Test with a direct POST**

Run local server and post: `مطلوب بيت في السالمية بحدود 300 ألف مساحة 400`.
Expected: response has `chatGuidance.regionDecision` and concise `answer`.

---

### Task 3: Frontend Analyze Failure Contract

**Files:**
- Modify: `frontend/app.js`

**Interfaces:**
- Consumes: `postJson("/api/analyze", payload)`
- Produces: no `staticAnalyzeReport` on 401/403/429 or `tier_limit`

- [ ] **Step 1: Locate analyze fallback**

Find the catch block in `postJson()` that returns `staticAnalyzeReport(payload)`.

- [ ] **Step 2: Split failure handling**

For HTTP 401/403/429, throw an error with server message. Use static fallback only for static-host/no-API conditions.

- [ ] **Step 3: Render a clear chat message**

Display login/tier/network message in the assistant bubble and do not render fake zero-result reports.

- [ ] **Step 4: Browser smoke test**

Run the local app and send an anonymous query.
Expected: 403 shows login/tier message, not "قاعدة البيانات static".

---

### Task 4: Concise Main Navigation

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

**Interfaces:**
- Consumes: existing `data-main-tab`/`data-main-panel` behavior
- Produces: visible top-level paths `بحث`, `فرص`, `السوق`, `تحديثات`, `حساب`

- [ ] **Step 1: Rename and merge tabs**

Keep panels intact but make the visible top navigation concise. `السوق` should reveal board/insights as internal choices.

- [ ] **Step 2: Move account entry**

Expose `حساب` as the account entry and keep saved searches/alerts inside account flows.

- [ ] **Step 3: Keep admin/secondary pages reachable**

Move metrics, WhatsApp, classifications, and why-free links into a secondary "المزيد" or footer/admin area.

- [ ] **Step 4: Test tab switching**

Click each top-level tab and confirm existing panels still appear.

---

### Task 5: Search Action Simplification

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

**Interfaces:**
- Consumes: existing button IDs for `downloadReportBtn`, `downloadPdfBtn`, `clearChatBtn`, `toggleCustomSearchBtn`
- Produces: one visible primary chat action; secondary actions grouped

- [ ] **Step 1: Replace toolbar copy**

Use short labels: `بحث`, `مسح`, `PDF`, `JSON`, `نبّهني`.

- [ ] **Step 2: Hide export actions until a report exists**

Keep event listeners and IDs unchanged so download behavior still works.

- [ ] **Step 3: Verify mobile layout**

Use browser screenshot at desktop and mobile widths. Expected: no overlapping buttons/text.

---

### Task 6: MCP Chat Tool

**Files:**
- Modify: `mcp_server/tools.py`
- Modify: `mcp_server/smoke_test.py`

**Interfaces:**
- Produces MCP tool: `alforaij_answer_chat_query`
- Inputs: `text`, `include_external`, `include_local`, `source_mode`, `format`
- Output: `intent`, `regionDecision`, `sourcePlan`, `answer`, `results`, `warnings`, `evidence`

- [ ] **Step 1: Register tool metadata**

Add tool definition next to current MCP tools.

- [ ] **Step 2: Reuse backend service**

Call parser/analyzer helpers rather than duplicating business rules.

- [ ] **Step 3: Smoke test**

Run: `python mcp_server/smoke_test.py`
Expected: all smoke checks pass including the new tool.

---

## Self-Review

- Spec coverage: parser, chat guidance, frontend fallback, UI IA, and MCP are represented.
- Placeholder scan: no task uses TBD/TODO/fill-in language.
- Type consistency: `chatGuidance`, `regionDecision`, `sourcePlan`, `dataQuality`, and `answer` use the same names across backend/frontend/MCP.
