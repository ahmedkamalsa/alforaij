from __future__ import annotations

import unittest

from backend.models import Listing
from backend.services.deduplication import deduplicate_ranked
from backend.services.matching import top_matches
from backend.services.request_parser import parse_request
from backend.services.valuation import enrich_rankings


def listing(code: str, price: float | None, space: float | None, summary: str = "") -> Listing:
    return Listing(
        code=code,
        transaction="\u0644\u0644\u0628\u064a\u0639",
        governorate="\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u062c\u0647\u0631\u0627\u0621",
        area="\u0627\u0644\u0645\u0637\u0644\u0627\u0639",
        property_type="\u0628\u064a\u062a",
        detail_class="\u0628\u064a\u062a/\u0641\u064a\u0644\u0627",
        price=price,
        price_text=f"{price} \u062f.\u0643" if price else "\u063a\u064a\u0631 \u0645\u0639\u0644\u0646",
        space=space,
        listing_mode="\u0645\u0628\u0627\u0634\u0631",
        summary=summary or "\u0628\u064a\u062a \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639 \u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631",
        features="\u0634\u0627\u0631\u0639 \u0648\u0627\u062d\u062f",
        published_date="2026-08-03",
        original_url="https://front.alforaij.com/Listing/Detail/test",
    )


class AnalysisTests(unittest.TestCase):
    def test_matching_and_valuation_return_ranked_items(self) -> None:
        request = parse_request(
            "\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639 "
            "\u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631 \u0648\u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629 350 \u0623\u0644\u0641"
        )
        listings = [
            listing("AF-1", 350000, 400),
            listing("AF-2", 360000, 400),
            listing("AF-3", 380000, 400),
            listing("AF-4", 500000, 600),
        ]

        ranked = top_matches(request, listings)
        enriched = enrich_rankings(request, ranked, listings)

        self.assertGreater(enriched[0].match_score, 50)
        self.assertTrue(enriched[0].comparables)
        self.assertIn(enriched[0].valuation_label, {
            "\u0644\u0642\u0637\u0629 \u0645\u0645\u062a\u0627\u0632\u0629",
            "\u0623\u0642\u0644 \u0645\u0646 \u0627\u0644\u0633\u0648\u0642",
            "\u0633\u0639\u0631 \u0639\u0627\u062f\u0644",
            "\u0623\u0639\u0644\u0649 \u0642\u0644\u064a\u0644\u064b\u0627",
            "\u063a\u0627\u0644\u064a",
            "\u0645\u0628\u0627\u0644\u063a \u0641\u064a\u0647",
        })

    def test_deduplication_removes_same_property_signature(self) -> None:
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639")
        listings = [
            listing("AF-1", 350000, 400, "\u0646\u0641\u0633 \u0627\u0644\u0648\u0635\u0641 \u062a\u0645\u0627\u0645\u0627"),
            listing("AF-2", 350000, 400, "\u0646\u0641\u0633 \u0627\u0644\u0648\u0635\u0641 \u062a\u0645\u0627\u0645\u0627"),
        ]
        deduped = deduplicate_ranked(enrich_rankings(request, top_matches(request, listings), listings))

        self.assertEqual(len(deduped), 1)


if __name__ == "__main__":
    unittest.main()
