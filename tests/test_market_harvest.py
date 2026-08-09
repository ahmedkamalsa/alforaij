from __future__ import annotations

import unittest


class TestMarketHarvest(unittest.TestCase):
    """اختبارات حصاد إعلانات السوق الخارجية في قاعدة المعرفة (market_listings)."""

    def _external_listing(self):
        from backend.models import Listing

        return Listing(
            code="MJ-TEST-1",
            transaction="للبيع",
            governorate="الفروانية",
            area="صباح الناصر",
            property_type="بيت",
            detail_class="مصدر حي",
            price=450000,
            price_text="450,000 د.ك",
            space=500,
            listing_mode="مكتب",
            summary="بيت للبيع في صباح الناصر",
            features="زاوية",
            published_date="2026-08-01",
            original_url="https://example.com/mj-test-1",
            source="Mourjan",
        )

    def test_return_external_includes_serialized_rows(self) -> None:
        from unittest import mock

        from backend.services import opportunities

        ext = self._external_listing()
        with mock.patch(
            "backend.services.opportunities.search_external_sources",
            return_value=([ext], [{"name": "Mourjan", "status": "success", "records": 1}]),
        ), mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])):
            snapshot = opportunities.build_opportunities(include_external=True, return_external=True)
        rows = snapshot.get("externalListings", [])
        self.assertTrue(rows)
        row = next(r for r in rows if r["code"] == "MJ-TEST-1")
        self.assertEqual(row["area"], "صباح الناصر")
        self.assertEqual(row["price"], 450000)
        self.assertEqual(row["source"], "Mourjan")
        self.assertEqual(row["transaction"], "للبيع")
        self.assertEqual(row["original_url"], "https://example.com/mj-test-1")

    def test_return_external_false_omits_key(self) -> None:
        from unittest import mock

        from backend.services import opportunities

        with mock.patch(
            "backend.services.opportunities.search_external_sources",
            return_value=([self._external_listing()], []),
        ), mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])):
            snapshot = opportunities.build_opportunities(include_external=True, return_external=False)
        self.assertNotIn("externalListings", snapshot)

    def test_save_market_listings_saved(self) -> None:
        from unittest import mock

        from backend.services import supabase_store

        rows = [{"code": "MJ-TEST-1", "area": "صباح الناصر", "price": 450000, "source": "Mourjan"}]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_post") as post:
            result = supabase_store.save_market_listings(rows)
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["count"], 1)
        args = post.call_args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(args[0], "market_listings")
        self.assertEqual(args[1][0]["code"], "MJ-TEST-1")
        self.assertTrue(kwargs.get("upsert"))
        self.assertEqual(kwargs.get("conflict"), "code")

    def test_save_market_listings_tolerates_missing_table(self) -> None:
        from unittest import mock

        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(
                 supabase_store,
                 "_post",
                 side_effect=RuntimeError("HTTP 404 Could not find the table 'public.market_listings'"),
             ):
            result = supabase_store.save_market_listings([{"code": "X"}])
        self.assertEqual(result["status"], "failed")
        self.assertIn("404", result["error"])

    def test_save_market_listings_empty_and_not_configured(self) -> None:
        from unittest import mock

        from backend.services import supabase_store

        self.assertEqual(supabase_store.save_market_listings([])["status"], "empty")
        with mock.patch.object(supabase_store, "is_configured", return_value=False):
            self.assertEqual(supabase_store.save_market_listings([{"code": "X"}])["status"], "not_configured")
