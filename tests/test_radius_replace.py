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


if __name__ == "__main__":
    unittest.main()
