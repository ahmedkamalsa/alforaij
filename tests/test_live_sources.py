from __future__ import annotations

import unittest

from backend.connectors.live_sources import first_area_meta, listing_from_text
from backend.services.request_parser import parse_request


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

    def test_bnaid_al_qar_routes_to_real_source_slugs(self) -> None:
        request = parse_request(
            "\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a "
            "\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"
        )

        self.assertEqual(first_area_meta(request)["q8aqar"], "bnaid-al-qar")
        self.assertEqual(first_area_meta(request)["sakan_city"], "bnaid-al-qar")

    # ------------------------------------------------------------------
    # توسيع Q8Aqar (قراءة صفحات التفاصيل) + Sakan المضمّن + منصات التوسعة
    # ------------------------------------------------------------------
    def test_detail_price_space_extracts_from_jsonld_and_meta(self) -> None:
        from backend.connectors.live_sources import _detail_price_space

        body = (
            '<meta property="product:price:amount" content="225,000">'
            '<meta property="product:property:size" content="300">'
            "<script type=\"application/ld+json\">"
            '{"@type": "RealEstateListing", "price": 220000, "floorSize": 290}'
            "</script>"
        )
        price, space = _detail_price_space(body)
        self.assertEqual(price, 225000)
        self.assertEqual(space, 300)

    def test_detail_price_space_falls_back_to_text(self) -> None:
        from backend.connectors.live_sources import _detail_price_space

        body = "<h1>بيت للبيع في خيطان السعر 220 الف مساحة 300 م</h1>"
        price, space = _detail_price_space(body)
        self.assertEqual(price, 220000)
        self.assertEqual(space, 300)

    def test_sakan_embedded_extraction(self) -> None:
        from backend.connectors.live_sources import _extract_sakan_embedded

        body = (
            "<script>window.__DATA__ = {"
            '"listings": [{"title": "House for sale in Khaitan", '
            '"url": "/en/detail/khaitan-house-1", "price": 220000, "area": 300}]'
            "};</script>"
        )
        items = _extract_sakan_embedded(body)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 220000)
        self.assertIn("/en/", items[0]["url"])

    def test_sakan_search_is_tolerant_and_keeps_availability(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        with mock.patch.object(live_sources, "fetch_url", return_value=("", 0, 1.0, "net down")):
            listings, status = live_sources.search_sakan(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "failed")

    def test_new_marketplaces_tolerate_failures(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        for searcher in (live_sources.search_aqarat, live_sources.search_four_sale):
            with mock.patch.object(live_sources, "fetch_url", return_value=("", 0, 1.0, "net down")):
                listings, status = searcher(request)
            self.assertEqual(listings, [])
            self.assertEqual(status["status"], "failed")

    def test_official_transactions_searcher_is_wired(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        names = [name for name, _fn in live_sources.SEARCHERS]
        self.assertIn("الصفقات الرسمية", names)
        self.assertIn("Aqarat", names)
        self.assertIn("4Sale", names)
        request = parse_request("بيت للبيع في خيطان")
        with mock.patch("backend.connectors.official_data.load_transactions", return_value=[]):
            listings, status = live_sources.search_official_transactions(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "no_data")


if __name__ == "__main__":
    unittest.main()
