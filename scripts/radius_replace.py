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

# قيم الانحراف: تطبيع مقصود وموثق إلى أقرب توكين (الفرق ≤ 2px).
# 7px و 9px انحرافات حول 6/8؛ 10px و 14px انحرافات حول 12.
DRIFT_MAP = {
    "7px": "var(--radius-sm)",   # 6px — فرق 1px
    "9px": "var(--radius-md)",   # 8px — فرق 1px
    "10px": "var(--radius-lg)",  # 12px — فرق 2px
    "14px": "var(--radius-lg)",  # 12px — فرق 2px
}

_RULE = re.compile(r"border-radius:\s*([^;{}]+);")


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


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/radius_replace.py frontend/styles.css [--apply] [--report]")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"file not found: {path}")
        return 2
    css = path.read_text(encoding="utf-8")
    report: list = []
    out = rewrite(css, report=report if "--report" in sys.argv else None)
    if "--report" in sys.argv and report:
        print(f"[radius-replace] drift report ({len(report)} lines):")
        for line_no, old, target in report:
            print(f"  line {line_no}: {old} -> {target}")
    if "--apply" in sys.argv:
        path.write_text(out, encoding="utf-8")
        print(f"[radius-replace] written {path}")
    else:
        print("[radius-replace] dry-run (no --apply):", "unchanged" if out == css else "would change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
