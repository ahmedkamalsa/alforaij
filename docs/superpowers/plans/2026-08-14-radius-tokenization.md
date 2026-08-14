# Radius Tokenization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every literal `border-radius` value in `frontend/styles.css` with the existing `--radius-*` token scale (adding `--radius-xs`), normalizing the four drift magnitudes (7/9/10/14px) to the nearest token, with a computed-style snapshot diff proving that only the documented lines change.

**Architecture:** The token scale already exists in `:root` (`--radius-sm: 6px; --radius-md: 8px; --radius-lg: 12px; --radius-xl: 16px; --radius-pill: 999px`). This plan (1) adds the missing `--radius-xs: 3px`, (2) replaces literals via one deterministic Python script driven by an explicit value→token table, (3) validates with a **computed-style snapshot** taken before and after — the snapshot keys every radiused element by a stable selector and records its rendered radius, so the diff proves exact-value swaps are pixel-identical and drift normalizations touch only the documented lines.

**Tech Stack:** Pure CSS (no build step). Python 3.11 + pytest 8.4.2 for the backend regression gate. Playwright (Python) for the computed-style snapshot and the frontend suites. No new dependencies.

## Global Constraints

- **No Tailwind, no npm, no build step** — this project is deliberate dependency-free; tokens are plain CSS custom properties.
- **Do not tokenize** `border-radius: 50%` (circle semantics), `0`, or `inherit` — they are structural, not radius-scale.
- **Exact-value swaps are pixel no-ops** (8→`--radius-md`, 999→`--radius-pill`, 12→`--radius-lg`, 16→`--radius-xl`, 6→`--radius-sm`, 3→`--radius-xs`). Drift normalization (7/9/10/14) may shift radius by at most ±2px and is an intentional, documented refinement.
- The identity block (`.hero-brand-link` etc.) already uses `var(--radius-pill)` — the script must leave already-tokenized rules untouched.
- Test harness facts: full suite = `PYTHONIOENCODING=utf-8 python -m pytest tests/ -q` on **Python 3.11** (`/c/Users/hello/AppData/Local/Programs/Python/Python311/python`); frontend suites need a live API server on port 8000 (`ALFORAIJ_MOBILE_BASE`); sprint suite = `tests/playwright/testsprint_audit.py`, mobile = `scripts/run_mobile_checks.py`.
- Worktree state: main checkout has uncommitted changes (`styles.css` tokenization of the brand block, two new pytest files, `docs/art/`) — do not commit those in this plan's commits; commit only this plan's own files.

---

### Task 1: Add `--radius-xs` and build the baseline snapshot tool

**Files:**
- Modify: `frontend/styles.css` (add one token to the `:root` scale)
- Create: `scripts/radius_snapshot.py` (computed-radius snapshot — the verification tool both Tasks 2 and 3 rely on)
- Test: `tests/test_radius_snapshot.py`

**Interfaces:**
- Consumes: the existing `:root` scale (`--radius-sm/md/lg/xl/pill`), the live frontend at `ALFORAIJ_MOBILE_BASE` (default `http://127.0.0.1:8000/`).
- Produces: `scripts/radius_snapshot.py` with CLI `python scripts/radius_snapshot.py --out <path.json> [--base URL]` that writes one JSON object mapping `selector → rendered radius px` for every element whose computed `borderRadius` is non-zero. Task 2 and 3 run it before/after and diff.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_radius_snapshot.py
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_script_exists_and_produces_entries() -> None:
    """الأداة تكتب JSON بعدد إدخالات > 0 عند تشغيلها على خادم حي."""
    out = ROOT / ".freebuff" / "radius_snapshot_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "radius_snapshot.py"), "--out", str(out), "--base", base],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and len(data) > 0
    # كل قيمة رقمية بوحدة px
    assert all(str(v).endswith("px") for v in data.values())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/test_radius_snapshot.py -q`
Expected: FAIL with `FileNotFoundError` — `scripts/radius_snapshot.py` does not exist yet.

- [ ] **Step 3: Add the token and write the snapshot tool**

In `frontend/styles.css`, inside the `:root` radius block (currently `--radius-sm: 6px;` … `--radius-pill: 999px;`), insert as the first line of that block:

```css
  --radius-xs: 3px;
```

Create `scripts/radius_snapshot.py`:

```python
"""التقط قيم border-radius المحسوبة لكل عنصر — أداة تحقق قبل/بعد لتحويل التوكينات.

الاستخدام:
    python scripts/radius_snapshot.py --out snapshot_before.json [--base URL]
    # ... بعد تغيير styles.css ...
    python scripts/radius_snapshot.py --out snapshot_after.json [--base URL]
    # قارن: python scripts/radius_diff.py --before a.json --after b.json
"""
from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://127.0.0.1:8000/"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.base, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(500)
        data = page.evaluate(
            """() => {
                const out = {};
                for (const el of document.querySelectorAll('*')) {
                    const cs = getComputedStyle(el);
                    const r = cs.borderRadius;
                    if (r && r !== '0px') {
                        const cls = (el.className && typeof el.className === 'string')
                            ? '.' + el.className.trim().split(/\\s+/).join('.') : el.tagName.toLowerCase();
                        out[cls + (el.id ? '#' + el.id : '')] = r;
                    }
                }
                return out;
            }"""
        )
        browser.close()

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"[radius-snapshot] {len(data)} entries -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/test_radius_snapshot.py -q` (with a server on port 8000: `PYTHONIOENCODING=utf-8 python -m backend.main &`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/styles.css scripts/radius_snapshot.py tests/test_radius_snapshot.py
git commit -m "feat(css): add --radius-xs and radius snapshot tool"
```

---

### Task 2: Mechanical exact-value replacement (pixel no-op)

**Files:**
- Modify: `frontend/styles.css` (replace literals 3/6/8/12/16/999px with tokens)
- Create: `scripts/radius_replace.py` (deterministic table-driven rewriter)

**Interfaces:**
- Consumes: the snapshot tool from Task 1 (take the `before` snapshot first), the value→token table below.
- Produces: a `styles.css` where the six exact magnitudes no longer appear as literals, and `scripts/radius_diff.py` for the before/after comparison (also used by Task 3).

- [ ] **Step 1: Take the baseline snapshot**

Run (server on 8000):
```bash
python scripts/radius_snapshot.py --out .freebuff/radius_before_exact.json --base http://127.0.0.1:8000/
```
Expected: prints `[radius-snapshot] N entries -> ...` with N ≥ 60.

- [ ] **Step 2: Write the rewriter (failing first: no diff tool yet)**

Create `scripts/radius_diff.py`:

```python
"""قارن لقطتين من radius_snapshot وأبلغ عن أي عنصر تغيّر نصف قطره.

الإخراج: قائمة بالعناصر المتغيرة (كلاس#id، القيمة قبل، القيمة بعد).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--max-lines", type=int, default=40)
    args = ap.parse_args()

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    changed = {k: (before.get(k), v) for k, v in after.items() if before.get(k) != v}
    # عناصر اختفت أو ظهرت أيضًا
    for k in before:
        if k not in after:
            changed[k] = (before[k], None)
    print(f"[radius-diff] {len(changed)} changed entries")
    for i, (k, (a, b)) in enumerate(changed.items()):
        if i >= args.max_lines:
            print(f"  ... and {len(changed) - args.max_lines} more")
            break
        print(f"  {k}: {a} -> {b}")
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Write the failing test for the rewriter**

```python
# tests/test_radius_replace.py
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RadiusReplaceMapping(unittest.TestCase):
    """جدول التحويل يجب أن يطابق المواصفة: قيم دقيقة → التوكين نفسه، بلا 50%/0/inherit."""

    def test_exact_mapping_table(self) -> None:
        from scripts.radius_replace import EXACT_MAP

        self.assertEqual(EXACT_MAP, {
            "3px": "var(--radius-xs)",
            "6px": "var(--radius-sm)",
            "8px": "var(--radius-md)",
            "12px": "var(--radius-lg)",
            "16px": "var(--radius-xl)",
            "999px": "var(--radius-pill)",
        })
        for excluded in ("50%", "0", "inherit"):
            self.assertNotIn(excluded, EXACT_MAP)

    def test_rewriter_replaces_literals_in_sample(self) -> None:
        from scripts.radius_replace import rewrite

        sample = "a { border-radius: 8px; }\nb { border-radius: 50%; }\nc { border-radius: 999px; }\n"
        out = rewrite(sample)
        self.assertIn("border-radius: var(--radius-md);", out)
        self.assertIn("border-radius: 50%;", out)  # لا تُلمس
        self.assertNotIn("border-radius: 8px;", out)
        self.assertNotIn("border-radius: 999px;", out)
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/test_radius_replace.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts.radius_replace`.

- [ ] **Step 5: Implement the rewriter**

Create `scripts/radius_replace.py`:

```python
"""استبدال قيم border-radius الحرفية بتوكينات --radius-* — جدول صريح لا منطق خفي.

لا تُلمس: 50% (دوائر) و 0 و inherit و أي سطر يستخدم var(--radius-...) أصلًا.
الاستخدام: python scripts/radius_replace.py frontend/styles.css --apply
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# القيم الدقيقة: الاستبدال لا يغيّر أي بكسل (نفس القيمة عبر التوكين)
EXACT_MAP = {
    "3px": "var(--radius-xs)",
    "6px": "var(--radius-sm)",
    "8px": "var(--radius-md)",
    "12px": "var(--radius-lg)",
    "16px": "var(--radius-xl)",
    "999px": "var(--radius-pill)",
}

_RULE = re.compile(r"border-radius:\s*([^;{}]+);")


def rewrite(css: str) -> str:
    def repl(m: re.Match) -> str:
        value = m.group(1).strip()
        if value.startswith("var(") or value in ("50%", "0", "inherit"):
            return m.group(0)  # لا تلمس
        if value in EXACT_MAP:
            return f"border-radius: {EXACT_MAP[value]};"
        return m.group(0)  # قيم الانحراف تعالج في Task 3

    return _RULE.sub(repl, css)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/radius_replace.py frontend/styles.css [--apply]")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"file not found: {path}")
        return 2
    css = path.read_text(encoding="utf-8")
    out = rewrite(css)
    if "--apply" in sys.argv:
        path.write_text(out, encoding="utf-8")
        print(f"[radius-replace] written {path}")
    else:
        print("[radius-replace] dry-run (no --apply):", "unchanged" if out == css else "would change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the tests to verify they pass, then apply**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/test_radius_replace.py -q`
Expected: PASS (2 passed).

Run: `python scripts/radius_replace.py frontend/styles.css --apply`
Expected: `[radius-replace] written frontend/styles.css`

- [ ] **Step 7: Verify pixel no-op with the snapshot diff**

Run (server on 8000):
```bash
python scripts/radius_snapshot.py --out .freebuff/radius_after_exact.json --base http://127.0.0.1:8000/
python scripts/radius_diff.py --before .freebuff/radius_before_exact.json --after .freebuff/radius_after_exact.json
```
Expected: `[radius-diff] 0 changed entries` — **صفر تغيير بكسل** للقيم الدقيقة.

- [ ] **Step 8: Commit**

```bash
git add frontend/styles.css scripts/radius_replace.py scripts/radius_diff.py tests/test_radius_replace.py
git commit -m "refactor(css): tokenize exact border-radius values (pixel no-op)"
```

---

### Task 3: Normalize the drift magnitudes (7/9/10/14px)

**Files:**
- Modify: `frontend/styles.css`
- Modify: `scripts/radius_replace.py` (extend with `DRIFT_MAP` and the allowed-delta check)

**Interfaces:**
- Consumes: exact replacement from Task 2; the four drift values remain as literals: 7px (8 occurrences), 9px (6), 10px (23), 14px (3).
- Produces: `styles.css` with zero radius literals outside the excluded set; a drift report mapping each touched line to its old→new value and delta.

- [ ] **Step 1: Take the pre-drift snapshot**

Run:
```bash
python scripts/radius_snapshot.py --out .freebuff/radius_before_drift.json --base http://127.0.0.1:8000/
```
Expected: prints entries count.

- [ ] **Step 2: Write the failing test for the drift mapping**

```python
# tests/test_radius_replace.py (append)
    def test_drift_mapping_deltas_within_2px(self) -> None:
        from scripts.radius_replace import DRIFT_MAP, EXACT_MAP

        # كل توكين → قيمته بالبكسل (مرجع موثوق في الاختبار نفسه)
        TOKEN_PX = {
            "var(--radius-xs)": 3,
            "var(--radius-sm)": 6,
            "var(--radius-md)": 8,
            "var(--radius-lg)": 12,
            "var(--radius-xl)": 16,
            "var(--radius-pill)": 999,
        }

        self.assertEqual(set(DRIFT_MAP.values()) <= set(TOKEN_PX), True)
        for literal, token in DRIFT_MAP.items():
            self.assertNotIn(literal, EXACT_MAP)  # لا تتكرر القيم بين الجدولين
            delta = abs(int(literal.replace("px", "")) - TOKEN_PX[token])
            self.assertLessEqual(delta, 2)  # القاعدة: الانحراف ≤ 2px عن أقرب توكين
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/test_radius_replace.py -q`
Expected: FAIL with `AttributeError: module 'scripts.radius_replace' has no attribute 'DRIFT_MAP'`.

- [ ] **Step 4: Implement the drift mapping and per-line report**

In `scripts/radius_replace.py`, after `EXACT_MAP`, add:

```python
# قيم الانحراف: تطبيع مقصود وموثق إلى أقرب توكين (الفرق ≤ 2px).
# 7px و 9px انحرافات حول 6/8؛ 10px و 14px انحرافات حول 12.
DRIFT_MAP = {
    "7px": "var(--radius-sm)",   # 6px — فرق 1px
    "9px": "var(--radius-md)",   # 8px — فرق 1px
    "10px": "var(--radius-lg)",  # 12px — فرق 2px
    "14px": "var(--radius-lg)",  # 12px — فرق 2px
}
```

Change `rewrite()` to consult `DRIFT_MAP` when the value is not in `EXACT_MAP`, and add `--report` mode that prints each changed line number:

```python
def rewrite(css: str, report: list | None = None) -> str:
    def repl(m: re.Match) -> str:
        value = m.group(1).strip()
        if value.startswith("var(") or value in ("50%", "0", "inherit"):
            return m.group(0)
        target = EXACT_MAP.get(value) or DRIFT_MAP.get(value)
        if target is None:
            return m.group(0)
        if report is not None:
            line_no = css[: m.start()].count("\n") + 1
            report.append((line_no, value, target))
        return f"border-radius: {target};"

    return _RULE.sub(repl, css)
```

Update `main()` so that with `--report` it prints the table `line: old -> new` before writing.

- [ ] **Step 5: Run the test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/test_radius_replace.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Apply and inspect the drift report**

Run:
```bash
python scripts/radius_replace.py frontend/styles.css --apply --report
```
Expected: a table of exactly **40 lines** (8×7px + 6×9px + 23×10px + 3×14px) — each with delta ≤ 2px. Review the table; any line whose element is a full pill (aspect ratio near 1:2 or a toggle) should be re-checked: if it looks wrong, change that occurrence back to `--radius-pill` manually with a comment, and note it in the commit message.

- [ ] **Step 7: Verify the snapshot diff shows exactly the documented deltas**

Run:
```bash
python scripts/radius_snapshot.py --out .freebuff/radius_after_drift.json --base http://127.0.0.1:8000/
python scripts/radius_diff.py --before .freebuff/radius_before_drift.json --after .freebuff/radius_after_drift.json --max-lines 60
```
Expected: every changed entry is one of the 40 documented lines, each delta exactly `-1px`, `-2px`, or `+2px`. **No other entry changed** — this proves the exact swaps from Task 2 stayed intact and no unrelated style was touched.

- [ ] **Step 8: Sweep for leftovers**

Run:
```bash
grep -nE "border-radius: (7|9|10|14)px" frontend/styles.css
```
Expected: zero matches. Also confirm excluded values remain: `grep -cE "border-radius: (50%|0|inherit)" frontend/styles.css` → unchanged from baseline.

- [ ] **Step 9: Commit**

```bash
git add frontend/styles.css scripts/radius_replace.py tests/test_radius_replace.py
git commit -m "refactor(css): normalize drift border-radius values to nearest token"
```

---

### Task 4: Full regression gate

**Files:** none modified — verification only.

**Interfaces:** Consumes the final `styles.css`.

- [ ] **Step 1: Backend suite**

Run: `PYTHONIOENCODING=utf-8 /c/Users/hello/AppData/Local/Programs/Python/Python311/python -m pytest tests/ -q`
Expected: `245 passed`.

- [ ] **Step 2: Frontend suites against the live API server**

Run (server on 8000):
```bash
ALFORAIJ_MOBILE_BASE=http://127.0.0.1:8000/ PYTHONIOENCODING=utf-8 python tests/playwright/testsprint_audit.py
```
Expected: `النتيجة: 33/33 نجحت`.

Run:
```bash
PYTHONIOENCODING=utf-8 python scripts/run_mobile_checks.py
```
Expected: `كل فحوص الجوال ناجحة ✅`.

- [ ] **Step 3: Final snapshot sanity**

Run: `python scripts/radius_diff.py --before .freebuff/radius_before_exact.json --after .freebuff/radius_after_drift.json`
Expected: the same 40 documented drift entries and nothing else — the complete, audited change set.

- [ ] **Step 4: Stop the server and report**

Kill the backend started for this task. Report: exact counts before/after (`grep -c "border-radius:" styles.css`), the 40-line drift report summary, and the three suite results above.

---

## Self-Review

**Spec coverage:** Task 1 adds the missing token + tooling; Task 2 handles the six exact values as a pixel no-op; Task 3 handles the four drift values with the ±2px rule and per-line report; Task 4 is the full regression gate. The excluded set (50%/0/inherit) is asserted in tests, not just documented. Every requirement in the Global Constraints maps to at least one asserted step (no-Tailwind → pure CSS edits; identity block untouched → `rewrite()` skips `var(...)`; Python 3.11 harness → commands pinned).

**Placeholder scan:** No TBD/TODO. Every code step contains the full file content or the exact diff to apply; every runnable step has the exact command and its expected output.

**Type consistency:** `EXACT_MAP`/`DRIFT_MAP` are `dict[str, str]` in both the implementation and the tests; `rewrite(css, report=None)` signature matches the test call `rewrite(sample)`; `radius_diff.py` flags (`--before`, `--after`, `--max-lines`) match Task 2's invocation; `radius_snapshot.py` flags (`--out`, `--base`) match Task 1's test and both snapshot invocations.
