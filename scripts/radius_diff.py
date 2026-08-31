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
