from __future__ import annotations

import unittest

from backend.connectors.live_sources import listing_from_text


class LiveSourceParsingTests(unittest.TestCase):
    def test_external_house_sale_small_price_is_treated_as_thousands(self) -> None:
        listing = listing_from_text(
            source="OpenSooq",
            code="OS-test",
            url="https://example.test",
            title="\u0644\u0644\u0628\u064a\u0639 \u0641\u064a\u0644\u0627 \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639",
            description="\u0627\u0644\u0633\u0639\u0631 320",
            price=320,
            transaction="\u0644\u0644\u0628\u064a\u0639",
            fallback_type="\u0628\u064a\u062a",
        )

        self.assertEqual(listing.price, 320000)
        self.assertIn("\u0639\u0648\u0645\u0644 \u0643\u0623\u0644\u0641", listing.raw["priceSource"])


if __name__ == "__main__":
    unittest.main()
