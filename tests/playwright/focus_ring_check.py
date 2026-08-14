"""Real keyboard-Tab check for the :focus-visible ring.

Pressing Tab via CDP Input is trusted keyboard input, so the focused
element matches :focus-visible exactly as a real user tabbing would.
Prints JSON: {theme, ringVar, samples: [{tag, id, outlineStyle,
outlineWidth, outlineColor, ringExpected}]} and exits non-zero if any
focused element shows outline-style: none.

Usage: ALFORAIJ_MOBILE_BASE=http://localhost:8000 python focus_ring_check.py [--light]
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("ALFORAIJ_MOBILE_BASE", "http://localhost:8000")
LIGHT = "--light" in sys.argv
DARK = "--dark" in sys.argv


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{BASE}/index.html", wait_until="networkidle")
        if LIGHT or DARK:
            theme = "light" if LIGHT else "dark"
            page.evaluate("""(theme) => {
                localStorage.setItem("alforaij_theme", theme);
                document.documentElement.dataset.theme = theme;
            }""", theme)
            page.reload(wait_until="networkidle")

        theme = page.evaluate("document.documentElement.dataset.theme || 'dark'")
        ring_var = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--ring-color').trim()"
        )

        # Focus the body first so the next Tab is a real keyboard move.
        page.evaluate("document.body.focus()")
        samples = []
        seen = set()
        for _ in range(12):
            page.keyboard.press("Tab")
            info = page.evaluate("""() => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                const cs = getComputedStyle(el);
                return {
                    tag: el.tagName,
                    id: el.id || "",
                    cls: (typeof el.className === 'string' ? el.className : '').slice(0, 30),
                    outlineStyle: cs.outlineStyle,
                    outlineWidth: cs.outlineWidth,
                    outlineColor: cs.outlineColor,
                    outlineOffset: cs.outlineOffset,
                    matchesFV: el.matches(':focus-visible'),
                };
            }""")
            if not info:
                continue
            key = f"{info['tag']}|{info['id']}|{info['cls']}"
            if key in seen:
                continue
            seen.add(key)
            samples.append(info)

        browser.close()

    failures = [s for s in samples if s["outlineStyle"] in ("none", "auto", "dotted")]
    print(json.dumps({
        "theme": theme,
        "ringVar": ring_var,
        "samples": samples,
        "failures": failures,
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
