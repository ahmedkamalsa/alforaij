from __future__ import annotations

import unittest

from backend.models import Listing
from backend.services.deduplication import deduplicate_ranked
from backend.services.matching import top_matches
from backend.services.report_generator import build_report
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


def rental_listing(code: str, price: float | None, space: float | None, area: str = "\u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629") -> Listing:
    """\u0639\u0631\u0636 \u0625\u064a\u062c\u0627\u0631 \u0634\u0647\u0631\u064a (\u0628\u0633\u0639\u0631 \u0634\u0647\u0631\u064a \u0645\u062b\u0644 450 \u062f.\u0643/\u0634\u0647\u0631)."""
    row = listing(code, price, space)
    row.transaction = "\u0644\u0644\u0625\u064a\u062c\u0627\u0631"
    row.area = area
    row.property_type = "\u0634\u0642\u0629"
    row.detail_class = "\u0634\u0642\u0629"
    row.price_text = f"{price} \u062f.\u0643/\u0634\u0647\u0631" if price else "\u063a\u064a\u0631 \u0645\u0639\u0644\u0646"
    row.summary = f"\u0634\u0642\u0629 \u0644\u0644\u0625\u064a\u062c\u0627\u0631 \u0641\u064a {area} \u0628\u0625\u064a\u062c\u0627\u0631 \u0634\u0647\u0631\u064a"
    return row


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

    def test_report_includes_decision_quality_and_source_trust(self) -> None:
        request = parse_request(
            "\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639 "
            "\u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631 \u0648\u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629 350 \u0623\u0644\u0641"
        )
        listings = [
            listing("AF-1", 350000, 400),
            listing("AF-2", 360000, 400),
            listing("AF-3", 380000, 400),
        ]
        enriched = enrich_rankings(request, top_matches(request, listings), listings)

        report = build_report(request, enriched, source_count=len(listings))
        item = report["results"][0]

        self.assertIn("decisionLine", item)
        self.assertIn("dataQuality", item)
        self.assertIn("sourceTrust", item)
        self.assertGreater(item["dataQuality"]["score"], 50)
        self.assertEqual(report["sourceStatus"][0]["trust"]["label"], "\u062f\u062e\u0644 \u0627\u0644\u062a\u0642\u064a\u064a\u0645")

    def test_report_includes_same_area_external_similar_ads_only(self) -> None:
        request = parse_request("للبيع بيت في صباح الناصر المساحة 400 متر السعر 280 ألف")
        target = listing("AF-94", 280000, 400)
        target.area = "صباح الناصر"
        target.governorate = "محافظة الفروانية"

        external_same = listing("OS-1", 300000, 410)
        external_same.source = "OpenSooq"
        external_same.area = "صباح الناصر"
        external_same.governorate = "محافظة الفروانية"
        external_same.original_url = "https://kw.opensooq.com/example"

        external_other_area = listing("OS-2", 250000, 400)
        external_other_area.source = "OpenSooq"
        external_other_area.area = "خيطان"
        external_other_area.governorate = "محافظة الفروانية"

        ranked = top_matches(request, [target, external_same, external_other_area], min_results=1)
        enriched = enrich_rankings(request, ranked, [target, external_same, external_other_area])
        report = build_report(request, enriched, source_count=1)

        similar = report["similarExternal"]
        self.assertEqual(similar["count"], 1)
        self.assertEqual(similar["items"][0]["code"], "OS-1")
        self.assertEqual(similar["items"][0]["area"], "صباح الناصر")
        self.assertEqual(similar["items"][0]["source"], "OpenSooq")
        self.assertNotEqual(similar["items"][0]["source"], "الفريج")

    def test_short_area_phrase_is_detected_as_sabah_al_naser(self) -> None:
        request = parse_request("بيت بمنطقة صباح الناصر 400م")

        self.assertEqual(request.areas, ["صباح الناصر"])
        self.assertEqual(request.property_type, "بيت")
        self.assertEqual(request.min_area, 400)

    def test_area_phrase_with_hidden_rtl_marks_is_detected(self) -> None:
        request = parse_request("\u200fبيت بمنطقة صباح الناصر 400م\u200e")

        self.assertEqual(request.areas, ["صباح الناصر"])
        self.assertEqual(request.property_type, "بيت")
        self.assertEqual(request.min_area, 400)

    def test_filter_overrides_area_without_chat_text(self) -> None:
        from backend.main import _apply_filter_overrides

        request = parse_request("")
        _apply_filter_overrides(
            request,
            {"areas": "صباح الناصر", "propertyType": "بيت", "minArea": "400", "budget": "350000"},
        )

        self.assertEqual(request.areas, ["صباح الناصر"])
        self.assertEqual(request.property_type, "بيت")
        self.assertEqual(request.min_area, 400)
        self.assertEqual(request.budget, 350000)

    def test_deduplication_removes_same_property_signature(self) -> None:
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639")
        listings = [
            listing("AF-1", 350000, 400, "\u0646\u0641\u0633 \u0627\u0644\u0648\u0635\u0641 \u062a\u0645\u0627\u0645\u0627"),
            listing("AF-2", 350000, 400, "\u0646\u0641\u0633 \u0627\u0644\u0648\u0635\u0641 \u062a\u0645\u0627\u0645\u0627"),
        ]
        deduped = deduplicate_ranked(enrich_rankings(request, top_matches(request, listings), listings))

        self.assertEqual(len(deduped), 1)

    def test_rental_listings_use_rental_calculation_not_sale(self) -> None:
        """\u062e\u0637 \u0627\u0644\u0625\u064a\u062c\u0627\u0631 \u0627\u0644\u0645\u0645\u064a\u0632: \u064a\u0642\u0627\u0631\u0646 \u0627\u0644\u0625\u064a\u062c\u0627\u0631 \u0627\u0644\u0634\u0647\u0631\u064a \u0628\u0648\u0633\u064a\u0637 \u0625\u064a\u062c\u0627\u0631\u0627\u062a \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0648\u0644\u064a\u0633 \u0628\u0633\u0639\u0631 \u0628\u064a\u0639 \u0625\u062c\u0645\u0627\u0644\u064a."""
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0634\u0642\u0629 \u0644\u0644\u0625\u064a\u062c\u0627\u0631 \u0641\u064a \u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629 \u0628\u0645\u064a\u0632\u0627\u0646\u064a\u0629 450")
        rentals = [
            rental_listing("AF-R1", 450, 80),
            rental_listing("AF-R2", 500, 80),
            rental_listing("AF-R3", 400, 80),
            rental_listing("AF-R4", 550, 90),
        ]

        ranked = top_matches(request, rentals)
        enriched = enrich_rankings(request, ranked, rentals)

        # \u0643\u0644 \u0646\u062a\u064a\u062c\u0629 \u0625\u064a\u062c\u0627\u0631 \u062a\u062d\u0645\u0644 \u0627\u0644\u062d\u0642\u0648\u0644 \u0627\u0644\u0625\u064a\u062c\u0627\u0631\u064a\u0629 \u0648\u0644\u064a\u0633 \u0645\u0646 \u0644\u0648\u0627\u0632\u0645 \u0627\u0644\u0628\u064a\u0639
        self.assertTrue(enriched)
        for it in enriched:
            ns = it.number_sources
            self.assertTrue(ns.get("rental", {}).get("value") is True)
            self.assertEqual(ns["annualRent"]["value"], it.listing.price * 12)
            self.assertIsNotNone(ns["price"]["display"])
            # \u0627\u0644\u0648\u0633\u064a\u0637 \u064a\u0628\u0642\u0649 \u0634\u0647\u0631\u064a\u064b\u0627 (\u062d\u0648\u0644\u064a 450-500) \u0648\u0644\u064a\u0633 \u0633\u0639\u0631 \u0628\u064a\u0639 \u0628\u0645\u0626\u0627\u062a \u0627\u0644\u0622\u0644\u0627\u0641
            self.assertLess(it.market_median or 0, 1000)

    def test_sale_listing_uses_sale_valuation_without_rental_flag(self) -> None:
        """\u0639\u0631\u0648\u0636 \u0627\u0644\u0628\u064a\u0639 \u062a\u062d\u062a\u0641\u0638 \u0628\u062e\u0637 \u0627\u0644\u0628\u064a\u0639 \u0627\u0644\u0639\u0627\u062f\u064a (\u0648\u0633\u064a\u0637 \u0628\u0645\u0626\u0627\u062a \u0627\u0644\u0622\u0644\u0627\u0641) \u0628\u062f\u0648\u0646 \u0639\u0644\u0627\u0645\u0629 \u0625\u064a\u062c\u0627\u0631."""
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a \u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629")
        sales = [
            listing("AF-S1", 150000, 80),
            listing("AF-S2", 160000, 80),
            listing("AF-S3", 140000, 80),
        ]
        for row in sales:
            row.area = "\u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629"
            row.property_type = "\u0634\u0642\u0629"
            row.detail_class = "\u0634\u0642\u0629"

        enriched = enrich_rankings(request, top_matches(request, sales), sales)
        self.assertTrue(enriched)
        for it in enriched:
            self.assertFalse(it.number_sources.get("rental", {}).get("value") is True)
            self.assertGreater(it.market_median or 0, 100000)

    def test_rental_request_matches_rent_offers_only(self) -> None:
        """\u0637\u0644\u0628 \u0625\u064a\u062c\u0627\u0631 \u064a\u0637\u0627\u0628\u0642 \u0639\u0631\u0648\u0636 \u0627\u0644\u0625\u064a\u062c\u0627\u0631 \u0641\u0642\u0637 \u0648\u0644\u064a\u0633 \u0639\u0631\u0648\u0636 \u0627\u0644\u0628\u064a\u0639."""
        request = parse_request("\u0627\u0628\u064a \u0634\u0642\u0629 \u0644\u0644\u0625\u064a\u062c\u0627\u0631 \u0641\u064a \u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629")
        self.assertEqual(request.transaction, "\u0645\u0637\u0644\u0648\u0628 \u0644\u0644\u0625\u064a\u062c\u0627\u0631")
        rentals = [rental_listing("AF-R1", 450, 80)]
        sale = listing("AF-S1", 150000, 80)
        sale.area = "\u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629"
        sale.property_type = "\u0634\u0642\u0629"
        sale.detail_class = "\u0634\u0642\u0629"
        ranked = top_matches(request, rentals + [sale])
        codes = [item[0].code for item in ranked]
        self.assertEqual(codes, ["AF-R1"])

    def test_explicit_area_request_excludes_other_areas_when_enough_results(self) -> None:
        """\u0639\u0646\u062f\u0645\u0627 \u062a\u062a\u0648\u0641\u0631 \u0646\u062a\u0627\u0626\u062c \u0643\u0627\u0641\u064a\u0629 (3+) \u0641\u064a \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0645\u0637\u0644\u0648\u0628\u0629 \u0644\u0627 \u062a\u0646\u062f\u0631\u062c \u0645\u0646\u0627\u0637\u0642 \u0623\u062e\u0631\u0649 (\u0644\u0627 \u062a\u0648\u0633\u0639\u0629)."""
        request = parse_request(
            "\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a "
            "\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"
        )
        wrong_area = listing("AF-salwa", 120000, 100)
        wrong_area.area = "\u0633\u0644\u0648\u0649"
        wrong_area.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u062d\u0648\u0644\u064a"
        wrong_area.summary = "\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a \u0633\u0644\u0648\u0649"
        wrong_area.property_type = "\u0634\u0642\u0629"
        in_area = [
            listing("AF-bnaid", 145000, 120),
            listing("AF-bnaid2", 148000, 125),
            listing("AF-bnaid3", 142000, 118),
        ]
        for item in in_area:
            item.area = "\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"
            item.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0639\u0627\u0635\u0645\u0629"
            item.summary = "\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a \u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"
            item.property_type = "\u0634\u0642\u0629"

        ranked = top_matches(request, [wrong_area, *in_area])
        codes = [item[0].code for item in ranked]

        self.assertNotIn("AF-salwa", codes)
        self.assertEqual(len(codes), 3)

    def test_scarce_area_expands_to_governorate_with_warning_and_lower_rank(self) -> None:
        """\u0639\u0646\u062f \u0646\u062f\u0631\u0629 \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u062a\u062a\u0648\u0633\u0639 \u0627\u0644\u0646\u062a\u0627\u0626\u062c \u0644\u0646\u0641\u0633 \u0627\u0644\u0645\u062d\u0627\u0641\u0638\u0629 \u0645\u0639 \u0648\u0633\u0645 \u0648\u0627\u0636\u062d \u0648\u062a\u0631\u062a\u064a\u0628 \u0623\u062f\u0646\u0649."""
        request = parse_request(
            "\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631 \u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631"
        )
        target = listing("AF-94", 280000, 400)
        target.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"
        target.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        gov_1 = listing("AF-314", 220000, 300)
        gov_1.area = "\u062e\u064a\u0637\u0627\u0646"
        gov_1.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        gov_2 = listing("AF-309", 420000, 400)
        gov_2.area = "\u0627\u0634\u0628\u064a\u0644\u064a\u0629"
        gov_2.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        far = listing("AF-110", 1250000, 530)
        far.area = "\u062d\u0648\u0644\u064a"
        far.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u062d\u0648\u0644\u064a"

        ranked = top_matches(request, [target, gov_1, gov_2, far], min_results=3)
        codes = [item[0].code for item in ranked]

        # \u0627\u0644\u062a\u0631\u062a\u064a\u0628 \u0627\u0644\u0635\u062d\u064a\u062d: \u0627\u0644\u0645\u0637\u0627\u0628\u0642 \u062f\u0627\u062e\u0644 \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0623\u0648\u0644\u0627\u064b\u060c \u062b\u0645 \u0627\u0644\u0645\u062d\u0627\u0641\u0638\u0629 \u0628\u062a\u062d\u0630\u064a\u0631\u060c \u0648\u0627\u0644\u0623\u0642\u0631\u0628 \u0645\u0633\u0627\u062d\u0629\u064b (400\u0645 \u0645\u0637\u0627\u0628\u0642\u0629) \u064a\u0633\u0628\u0642 \u0627\u0644\u0623\u0628\u0639\u062f (300\u0645).
        self.assertEqual(codes, ["AF-94", "AF-309", "AF-314"])
        self.assertNotIn("AF-110", codes)
        self.assertGreater(ranked[0][1], ranked[1][1])
        self.assertIn("\u062e\u0627\u0631\u062c \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0645\u0637\u0644\u0648\u0628\u0629", ranked[1][3][0])
        self.assertIn("\u062e\u0627\u0631\u062c \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0645\u0637\u0644\u0648\u0628\u0629", ranked[2][3][0])

    def test_very_scarce_area_falls_back_to_any_area(self) -> None:
        """\u0639\u0646\u062f\u0645\u0627 \u062a\u0643\u0648\u0646 \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0648\u0645\u062d\u0627\u0641\u0638\u062a\u0647\u0627 \u062e\u0627\u0648\u064a\u064a\u0646 \u062a\u0639\u0648\u062f \u0627\u0644\u0646\u062a\u0627\u0626\u062c \u0627\u0644\u0627\u0633\u062a\u0631\u0634\u0627\u062f\u064a\u0629 \u0645\u0646 \u0643\u0644 \u0627\u0644\u0645\u0646\u0627\u0637\u0642 \u0628\u062f\u0644 \u0627\u0644\u0628\u062d\u062b \u0627\u0644\u0641\u0627\u0631\u063a."""
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0627\u0644\u0631\u0642\u0629 \u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631")
        far_1 = listing("AF-303", 310000, 400)
        far_1.area = "\u0627\u0644\u0645\u0637\u0644\u0627\u0639"
        far_1.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u062c\u0647\u0631\u0627\u0621"
        far_2 = listing("AF-110", 1250000, 530)
        far_2.area = "\u062d\u0648\u0644\u064a"
        far_2.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u062d\u0648\u0644\u064a"

        ranked = top_matches(request, [far_1, far_2], min_results=3)
        codes = [item[0].code for item in ranked]

        self.assertEqual(len(codes), 2)
        self.assertTrue(any("\u062e\u0627\u0631\u062c \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0645\u0637\u0644\u0648\u0628\u0629" in w for _, _, _, warnings, _ in ranked for w in warnings))

    def test_mixed_rent_and_sale_text_prioritizes_sale_area(self) -> None:
        """\u0627\u0644\u0646\u0635 \u0627\u0644\u0645\u062e\u062a\u0644\u0637 (\u0628\u0642\u0627\u064a\u0627 \u0631\u0633\u0627\u0644\u0629 \u0625\u064a\u062c\u0627\u0631 + \u0625\u0639\u0644\u0627\u0646 \u0628\u064a\u0639) \u064a\u064f\u062d\u0633\u0645 \u0644\u0644\u0628\u064a\u0639 \u0648\u064a\u064f\u062d\u0635\u0631 \u0641\u064a \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0625\u0639\u0644\u0627\u0646."""
        request = parse_request(
            "\u0627\u064a\u062c\u0627\u0631 \u0634\u0642\u0629 \u0641\u064a \u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629 "
            "\u0644\u0644\u0628\u064a\u0639 \u0628\u064a\u062a \u0641\u064a \u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631 \u0627\u0644\u062c\u062f\u064a\u062f\u0629 \u0642\u0637\u0639\u0629 6 "
            "\u0627\u0644\u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631 \u0645\u0631\u0628\u0639 \u064a\u062a\u0643\u0648\u0646 \u0645\u0646 \u0646\u0635 \u0633\u0631\u062f\u0627\u0628 "
            "\u0648\u062f\u0648\u0631\u064a\u0646 \u0648\u0631\u0628\u0639 \u0645\u0639 \u0645\u0635\u0639\u062f \u062a\u0631\u0645\u064a\u0645 \u062d\u062f\u064a\u062b "
            "\u0633\u0646\u0629 2022 \u0627\u0644\u0633\u0639\u0631 280 \u0627\u0644\u0641 \u062f\u064a\u0646\u0627\u0631"
        )
        self.assertEqual(request.transaction, "\u0644\u0644\u0628\u064a\u0639")
        self.assertEqual(request.areas, ["\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"])
        self.assertEqual(request.property_type, "\u0628\u064a\u062a")
        self.assertEqual(request.min_area, 400)
        self.assertEqual(request.budget, 280000)

    def test_similar_sale_listing_with_close_space_still_ranked(self) -> None:
        """\u0625\u0639\u0644\u0627\u0646 \u0628\u064a\u0639 \u0645\u0634\u0627\u0628\u0647 \u0628\u0645\u0633\u0627\u062d\u0629 \u0642\u0631\u064a\u0628\u0629 \u064a\u0638\u0647\u0631 \u0641\u064a \u0627\u0644\u0646\u062a\u0627\u0626\u062c \u0628\u062f\u0631\u062c\u0629 \u0623\u062f\u0646\u0649 \u0648\u062a\u062d\u0630\u064a\u0631 \u0648\u0627\u0636\u062d \u0628\u062f\u0644 \u0627\u0644\u062d\u0630\u0641 \u0627\u0644\u0643\u0627\u0645\u0644."""
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631 \u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631 \u0645\u064a\u0632\u0627\u0646\u064a\u0629 280 \u0623\u0644\u0641")
        exact = listing("AF-94", 280000, 400)
        exact.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"
        close = listing("MJ-1", 450000, 500)
        close.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"
        # \u0628\u0639\u064a\u062f \u062c\u062f\u0627 \u0641\u064a \u0627\u0644\u0645\u0633\u0627\u062d\u0629 \u0648\u0628\u0627\u0647\u0638 \u0623\u064a\u0636\u064b\u0627 (\u0644\u0627 \u0646\u0642\u0627\u0637 \u0645\u064a\u0632\u0627\u0646\u064a\u0629) \u0644\u064a\u0628\u0642\u0649 \u0627\u0644\u062a\u0631\u062a\u064a\u0628 \u0645\u0637\u0627\u0628\u0642 \u2190 \u0642\u0631\u064a\u0628 \u2190 \u0628\u0639\u064a\u062f
        far = listing("AF-999", 500000, 150)
        far.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"

        ranked = top_matches(request, [exact, close, far])
        codes = [item[0].code for item in ranked]
        self.assertEqual(codes, ["AF-94", "MJ-1", "AF-999"])
        self.assertIn("\u0627\u0644\u0645\u0633\u0627\u062d\u0629 \u0642\u0631\u064a\u0628\u0629", ranked[1][3][0])

    def test_space_proximity_outweighs_budget_proximity(self) -> None:
        """\u0627\u0644\u0625\u0639\u0644\u0627\u0646 \u0627\u0644\u0623\u0642\u0631\u0628 \u0645\u0633\u0627\u062d\u0629\u064b (\u0648\u0644\u0648 \u0643\u0627\u0646 \u0633\u0639\u0631\u0647 \u0623\u0639\u0644\u0649 \u0645\u0646 \u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629) \u064a\u0633\u0628\u0642 \u0627\u0644\u0625\u0639\u0644\u0627\u0646 \u0627\u0644\u0623\u0628\u0639\u062f \u0645\u0633\u0627\u062d\u0629\u064b \u0648\u0644\u0643\u0646 \u0627\u0644\u0623\u0642\u0631\u0628 \u0633\u0639\u0631\u064b\u0627 \u0644\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629."""
        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631 \u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631 \u0645\u064a\u0632\u0627\u0646\u064a\u0629 280 \u0623\u0644\u0641")
        # \u0623\u0642\u0631\u0628 \u0645\u0633\u0627\u062d\u0629\u064b (500 \u0645\u0642\u0627\u0628\u0644 400 = \u0641\u0631\u0642 25%) \u0644\u0643\u0646 \u0633\u0639\u0631\u0647 \u0623\u0639\u0644\u0649 \u0645\u0646 \u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629
        near_space = listing("A-SPACE", 450000, 500)
        near_space.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"
        # \u0623\u0628\u0639\u062f \u0645\u0633\u0627\u062d\u0629\u064b (150 \u0645\u0642\u0627\u0628\u0644 400 = \u0641\u0631\u0642 62%) \u0644\u0643\u0646 \u0633\u0639\u0631\u0647 \u0642\u0631\u064a\u0628 \u062c\u062f\u0627\u064b \u0645\u0646 \u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629
        near_budget = listing("B-BUDGET", 300000, 150)
        near_budget.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"

        ranked = top_matches(request, [near_space, near_budget])
        codes = [item[0].code for item in ranked]
        self.assertEqual(codes, ["A-SPACE", "B-BUDGET"])
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_comparable_pool_expands_to_governorate_when_area_comps_scarce(self) -> None:
        """\u0639\u0646\u062f \u0646\u0642\u0635 \u0645\u0642\u0627\u0631\u0646\u0627\u062a \u0646\u0641\u0633 \u0627\u0644\u0645\u0646\u0637\u0642\u0629 \u062a\u064f\u0648\u0633\u0651\u0639 \u0627\u0644\u0645\u0642\u0627\u0631\u0646\u0627\u062a \u0644\u0646\u0641\u0633 \u0627\u0644\u0645\u062d\u0627\u0641\u0638\u0629 \u0648\u0644\u0627 \u062a\u062f\u062e\u0644 \u0645\u0646\u0627\u0637\u0642 \u0623\u062e\u0631\u0649."""
        from backend.services.valuation import comparable_pool

        request = parse_request("\u0645\u0637\u0644\u0648\u0628 \u0628\u064a\u062a \u0641\u064a \u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631 \u0645\u0633\u0627\u062d\u0629 400")
        target = listing("AF-94", 280000, 400)
        target.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"
        target.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        same_area = listing("AF-95", 290000, 400)
        same_area.area = "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0627\u0635\u0631"
        same_area.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        gov_1 = listing("AF-96", 300000, 400)
        gov_1.area = "\u062e\u064a\u0637\u0627\u0646"
        gov_1.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        gov_2 = listing("AF-97", 310000, 450)
        gov_2.area = "\u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        gov_2.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u0627\u0644\u0641\u0631\u0648\u0627\u0646\u064a\u0629"
        far = listing("AF-98", 500000, 400)
        far.area = "\u0627\u0644\u0633\u0627\u0644\u0645\u064a\u0629"
        far.governorate = "\u0645\u062d\u0627\u0641\u0638\u0629 \u062d\u0648\u0644\u064a"

        comps = comparable_pool(target, [target, same_area, gov_1, gov_2, far], request)
        codes = [row.code for row in comps]

        self.assertIn("AF-95", codes)
        self.assertIn("AF-96", codes)
        self.assertIn("AF-97", codes)
        self.assertNotIn("AF-98", codes)

    def test_governorate_mention_without_prefix_expands_to_its_areas(self) -> None:
        """ذكر محافظة بلا «محافظة» قبلها (مثل «بالعاصمة») يوسّع لمناطقها ولا يضيّعها."""
        request = parse_request("يبي ايجار مكتب بالعاصمة او حولي شي رخيص بحدود ٢٠٠")

        self.assertEqual(request.transaction, "مطلوب للإيجار")
        self.assertEqual(request.property_type, "تجاري")
        self.assertEqual(request.rent_budget, 200.0)
        self.assertIn("العاصمة", request.governorates)
        self.assertIn("حولي", request.areas)
        # مناطق العاصمة تُوسَّع (مثل الشرق) حتى لا يُفقد البحث عن العاصمة
        self.assertIn("الشرق", request.areas)
        self.assertIn("القبلة", request.areas)

    def test_area_only_request_does_not_expand_governorate(self) -> None:
        """طلب منطقة محددة (السالمية) يبقى محصورًا فيها ولا يتوسع لمحافظة حولي كلها."""
        request = parse_request("ايجار شقة في السالمية")

        self.assertEqual(request.areas, ["السالمية"])
        self.assertEqual(request.governorates, [])


    def test_parse_request_sulaibikhat_area(self) -> None:
        """«صليبيخات» تُلتقط كمنطقة، و«شمال غرب الصليبيخات» لا تتسع لمنطقة مضمّنة."""
        from backend.services.request_parser import parse_request

        r = parse_request("بيع بيت في صليبيخات 300 متر قديم بحدود 160 الف")
        self.assertEqual(r.areas, ["الصليبيخات"])
        r2 = parse_request("بيت شمال غرب الصليبيخات 400م")
        self.assertEqual(r2.areas, ["شمال غرب الصليبيخات"])


if __name__ == "__main__":
    unittest.main()
