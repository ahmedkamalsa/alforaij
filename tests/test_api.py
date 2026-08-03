from __future__ import annotations

import unittest

from backend.connectors.alforaij import _safe_space, load_listings


class DataLoadingTests(unittest.TestCase):
    def test_seed_or_dashboard_payload_loads(self) -> None:
        listings = load_listings()
        self.assertGreaterEqual(len(listings), 1)

    def test_loaded_listing_keeps_space_as_missing_when_source_is_missing(self) -> None:
        listings = load_listings()
        missing_space = [row for row in listings if row.raw.get("spaceSource") == "\u063a\u064a\u0631 \u0645\u0630\u0643\u0648\u0631\u0629"]
        if not missing_space:
            self.skipTest("No missing-space rows in current seed.")
        self.assertIsNone(missing_space[0].space)

    def test_safe_space_rejects_setback_value_even_if_raw_space_exists(self) -> None:
        row = {
            "space": 40,
            "spaceSource": "\u0645\u0630\u0643\u0648\u0631\u0629 \u0635\u0631\u0627\u062d\u0629 \u0641\u064a \u0646\u0635 \u0627\u0644\u0625\u0639\u0644\u0627\u0646",
            "detailText": "\u0628\u064a\u062a \u062f\u0648\u0631\u064a\u0646 \u064a\u062a\u0645\u064a\u0632 \u0628\u0627\u0631\u062a\u062f\u0627\u062f 40 \u0645\u062a\u0631",
        }

        self.assertIsNone(_safe_space(row))


if __name__ == "__main__":
    unittest.main()
