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
        page.goto(args.base, wait_until="load", timeout=60000)
        page.wait_for_selector(".main-tabs", timeout=15000)
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
