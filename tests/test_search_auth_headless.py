#!/usr/bin/env python3
"""Headless verification of the search authorization fix.

Tests that:
  1. sourceMode='local' → allowed without login (was always OK)
  2. sourceMode='all'   → allowed without login (was broken, now fixed)
  3. sourceMode='source' → blocked without login (still requires auth)
  4. sourceMode='custom' → blocked without login (still requires auth)

Drives the actual handler code via the live HTTP server.
"""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def assert_test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} — {detail}")


def analyze(source_mode, timeout=60):
    """Call /api/analyze with given sourceMode, no auth header, fast=True for speed."""
    data = json.dumps({
        "text": "شقة 200 متر",
        "sourceMode": source_mode,
        "jobId": f"auth-test-{source_mode}",
        "fast": True,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/analyze",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.time() - start
            body = json.loads(resp.read().decode())
            return resp.status, body, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = e.read().decode("utf-8", errors="replace")
        try:
            body_json = json.loads(body)
        except Exception:
            body_json = {"raw": body[:300]}
        return e.code, body_json, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return 0, {"error": str(e)}, elapsed


def main():
    global PASS, FAIL

    print("=" * 60)
    print("  Search Authorization Fix — Headless Verification")
    print("=" * 60)

    # ── Test 1: sourceMode='local' → should always work ──
    print("\n[1] sourceMode='local' (no auth)")
    status, body, elapsed = analyze("local", timeout=30)
    assert_test(f"HTTP 200 (got {status})", status == 200, f"body={json.dumps(body)[:200]}")
    assert_test("Has 'results' key", "results" in body, f"keys={list(body.keys())}")
    assert_test("Has 'summary' key", "summary" in body or "report" in body, f"keys={list(body.keys())}")
    print(f"    ({elapsed:.1f}s, {len(body.get('results', []))} results)")

    # ── Test 2: sourceMode='all' → THE FIX — should work without login ──
    print("\n[2] sourceMode='all' (no auth) — THE FIX")
    status, body, elapsed = analyze("all", timeout=60)
    assert_test(f"HTTP 200 (got {status})", status == 200, f"body={json.dumps(body)[:300]}")
    assert_test("Has 'results' key", "results" in body, f"keys={list(body.keys())}")
    assert_test("Results count > 0", len(body.get("results", [])) > 0, f"count={len(body.get('results', []))}")
    assert_test("No tier_limit error", body.get("error") != "tier_limit",
                f"error={body.get('error')}, message={body.get('message', '')[:100]}")
    print(f"    ({elapsed:.1f}s, {len(body.get('results', []))} results)")

    # ── Test 3: sourceMode='source' → should be blocked ──
    print("\n[3] sourceMode='source' (no auth) — should require login")
    status, body, elapsed = analyze("source", timeout=30)
    assert_test(f"HTTP 403 (got {status})", status == 403, f"status={status}, body={json.dumps(body)[:200]}")
    assert_test("Error is tier_limit", body.get("error") == "tier_limit",
                f"error={body.get('error')}")
    print(f"    ({elapsed:.1f}s)")

    # ── Test 4: sourceMode='custom' → should be blocked ──
    print("\n[4] sourceMode='custom' (no auth) — should require login")
    status, body, elapsed = analyze("custom", timeout=30)
    assert_test(f"HTTP 403 (got {status})", status == 403, f"status={status}, body={json.dumps(body)[:200]}")
    assert_test("Error is tier_limit", body.get("error") == "tier_limit",
                f"error={body.get('error')}")
    print(f"    ({elapsed:.1f}s)")

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
