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
        ), mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), \
             mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), \
             mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
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
        ), mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), \
             mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), \
             mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
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

    # ── تحليلات السوق (الموجة 1): عائد الإيجار واتجاه سعر المتر ──

    def _insights_rows(self):
        return [
            # حولي: بيع 600,000 د.ك / 300م + إيجار 2,500 — عائد = (2500*12)/600000 = 5%
            {"area": "حولي", "governorate": "", "transaction": "للبيع", "price": 600000, "space": 300, "fetched_at": "2026-07-10T08:00:00"},
            {"area": "حولي", "governorate": "", "transaction": "للبيع", "price": 600000, "space": 300, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "حولي", "governorate": "", "transaction": "للإيجار", "price": 2500, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "حولي", "governorate": "", "transaction": "للإيجار", "price": 2500, "space": None, "fetched_at": "2026-08-12T08:00:00"},
            # منطقة عينة إيجار واحدة فقط → عائد غير محسوب (حارس الموثوقية)
            {"area": "المنقف", "governorate": "", "transaction": "للبيع", "price": 300000, "space": 200, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "المنقف", "governorate": "", "transaction": "للبيع", "price": 310000, "space": 200, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "المنقف", "governorate": "", "transaction": "للإيجار", "price": 1200, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            # صف بلا منطقة أو بلا سعر يُتجاهل
            {"area": "", "governorate": "", "transaction": "للبيع", "price": 100, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "الرميثية", "governorate": "", "transaction": "للبيع", "price": 0, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            # منطقة بيع فقط → بلا عائد لكن بمتوسط سعر المتر
            {"area": "الفروانية", "governorate": "", "transaction": "بيع", "price": 200000, "space": 400, "fetched_at": "2026-08-10T08:00:00"},
        ]

    def test_fetch_market_insights_yield_and_totals(self) -> None:
        from unittest import mock

        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "market_listings_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=self._insights_rows()):
            result = supabase_store.fetch_market_insights()
        self.assertTrue(result["tableOk"])
        areas = {a["area"]: a for a in result["areas"]}
        # حولي: عائد 5% + سعر متر 2000 + محافظة مستنتجة من خريطة المحلل
        hawally = areas["حولي"]
        self.assertAlmostEqual(hawally["rentalYield"], 5.0, places=1)
        self.assertEqual(hawally["medianSalePerM2"], 2000.0)
        self.assertEqual(hawally["governorate"], "حولي")
        self.assertIsNone(areas["الفروانية"]["rentalYield"])
        # المنقف: عينتا بيع لكن إيجار واحد → العائد غير محسوب (حارس الموثوقية)
        self.assertIsNone(areas["المنقف"]["rentalYield"])
        # sampleTotals يعدّ كل الصفوف (حتى عديمة المنطقة/السعر) — التصفية داخل المناطق
        self.assertEqual(result["sampleTotals"], {"sale": 7, "rent": 3})
        self.assertEqual(len(areas), 3)  # حولي والفروانية والمنقف (ذواتا منطقة وسعر صالح)

    def test_fetch_market_insights_series_needs_two_months(self) -> None:
        from unittest import mock

        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "market_listings_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=self._insights_rows()):
            result = supabase_store.fetch_market_insights()
        # حولي لها نقطتان (07 و08) → تدخل السلسلة؛ الفروانية نقطة واحدة → لا
        areas_in_series = {s["area"] for s in result["series"]}
        self.assertIn("حولي", areas_in_series)
        self.assertNotIn("الفروانية", areas_in_series)
        self.assertIn("2026-08", result["months"])

    def test_fetch_market_insights_tolerates_missing_table(self) -> None:
        from unittest import mock

        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "market_listings_table_available", return_value=False):
            result = supabase_store.fetch_market_insights()
        self.assertFalse(result["tableOk"])
        self.assertEqual(result["areas"], [])
