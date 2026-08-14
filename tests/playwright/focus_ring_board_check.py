"""Extend the Tab check to the embedded board tab's interactive elements.

Clicks the لوحة السوق tab, then walks Tab through its focusables and
reports the applied :focus-visible outline on each.
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
            page.evaluate(
                """(theme) => {
                localStorage.setItem("alforaij_theme", theme);
                document.documentElement.dataset.theme = theme;
            }""",
                theme,
            )
            page.reload(wait_until="networkidle")

        theme = page.evaluate("document.documentElement.dataset.theme || 'dark'")
        ring_var = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--ring-color').trim()"
        )

        # Open the board tab
        page.evaluate("""() => {
            const tab = [...document.querySelectorAll('button.main-tab')]
                .find(b => b.textContent.includes('لوحة السوق'));
            if (tab) tab.click();
        }""")
        page.wait_for_timeout(800)

        # Count focusables, then walk Tab from body through all of them
        page.evaluate("document.body.focus()")
        total = page.evaluate(
            "document.querySelectorAll('button, a, input, textarea, select, [tabindex]:not([tabindex=\"-1\"])').length"
        )
        samples = []
        seen = set()
        for _ in range(total):
            page.keyboard.press("Tab")
            info = page.evaluate("""() => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                const cs = getComputedStyle(el);
                return {
                    tag: el.tagName,
                    id: el.id || "",
                    cls: (typeof el.className === 'string' ? el.className : '').slice(0, 40),
                    outlineStyle: cs.outlineStyle,
                    outlineWidth: cs.outlineWidth,
                    outlineColor: cs.outlineColor,
                    matchesFV: el.matches(':focus-visible'),
                    inBoard: !!el.closest('.board-panel, #boardSection, .board-section'),
                };
            }""")
            if not info:
                continue
            key = f"{info['tag']}|{info['id']}|{info['cls']}|{info['inBoard']}"
            if key in seen:
                continue
            seen.add(key)
            samples.append(info)
            if len(samples) >= 60:
                break

        browser.close()

    board_samples = [s for s in samples if s["inBoard"]]
    failures = [s for s in samples if s["matchesFV"] and s["outlineStyle"] not in ("solid",)]
    print(json.dumps({
        "theme": theme,
        "ringVar": ring_var,
        "tabbed": total,
        "sampled": len(samples),
        "boardSampled": len(board_samples),
        "boardFailures": [s for s in board_samples if s["matchesFV"] and s["outlineStyle"] not in ("solid",)],
        "failures": failures[:5],
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
