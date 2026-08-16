"""اختبارات معالجة الإعلانات القديمة (جودة البيانات): الكسح والحالة.

التغطية: ختم last_seen_at/status عند الحفظ، حد الكسح، نداء PATCH الصحيح،
وفلتر status=active الافتراضي في الجلب وقراءات التحليل. بلا شبكة.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from backend.services import supabase_store


class SaveStampsTests(unittest.TestCase):
    def test_save_stamps_last_seen_and_active(self) -> None:
        rows = [{"code": "MJ-1", "area": "النهضة", "price": 400000}]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_post") as post:
            supabase_store.save_market_listings(rows)
        stamped = post.call_args.args[1][0]
        self.assertEqual(stamped["status"], "active")
        self.assertTrue(stamped["last_seen_at"])
        # ختم قابل للتحليل كـ ISO زمني
        datetime.fromisoformat(stamped["last_seen_at"])

    def test_save_reactivates_previous_stale(self) -> None:
        # إعلان كان stale يظهر مجددًا → يُختم active (ردّ النشاط عند الظهور)
        rows = [{"code": "MJ-2", "status": "stale", "last_seen_at": "2026-07-01T00:00:00+00:00"}]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_post") as post:
            supabase_store.save_market_listings(rows)
        stamped = post.call_args.args[1][0]
        self.assertEqual(stamped["status"], "active")
        self.assertNotEqual(stamped["last_seen_at"], "2026-07-01T00:00:00+00:00")


class StaleCutoffTests(unittest.TestCase):
    def test_cutoff_is_iso_utc_and_aged(self) -> None:
        cutoff = supabase_store._stale_cutoff(14)
        parsed = datetime.fromisoformat(cutoff)
        self.assertIsNotNone(parsed.tzinfo)  # UTC صريح
        now = datetime.now(timezone.utc)
        self.assertLess(parsed, now - timedelta(days=13))
        self.assertGreater(parsed, now - timedelta(days=15))


class SweepTests(unittest.TestCase):
    def test_sweep_patches_old_active_rows_to_stale(self) -> None:
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_patch") as patch:
            result = supabase_store.mark_stale_market_listings(days=14)
        self.assertEqual(result["status"], "swept")
        self.assertEqual(result["days"], 14)
        filters, payload = patch.call_args.args[1], patch.call_args.args[2]
        self.assertEqual(filters["status"], "neq.stale")
        self.assertTrue(filters["last_seen_at"].startswith("lt."))
        self.assertEqual(payload, {"status": "stale"})

    def test_sweep_not_configured(self) -> None:
        with mock.patch.object(supabase_store, "is_configured", return_value=False), \
             mock.patch.object(supabase_store, "_patch") as patch:
            result = supabase_store.mark_stale_market_listings()
        self.assertEqual(result["status"], "not_configured")
        patch.assert_not_called()

    def test_sweep_failure_contained(self) -> None:
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_patch", side_effect=RuntimeError("HTTP 500")):
            result = supabase_store.mark_stale_market_listings()
        self.assertEqual(result["status"], "failed")
        self.assertIn("500", result["error"])


class FetchStatusTests(unittest.TestCase):
    def _fetch(self, **kwargs) -> str:
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows") as fetch:
            supabase_store.fetch_market_listings(**kwargs)
        return fetch.call_args.args[0]

    def test_default_filters_active(self) -> None:
        endpoint = self._fetch(limit=10)
        self.assertIn("status=eq.active", endpoint)
        self.assertIn("limit=10", endpoint)

    def test_status_none_reads_full_history(self) -> None:
        endpoint = self._fetch(limit=10, status=None)
        self.assertNotIn("status=", endpoint)

    def test_explicit_status_used(self) -> None:
        endpoint = self._fetch(limit=10, status="stale")
        self.assertIn("status=eq.stale", endpoint)


class AnalysisRowsTests(unittest.TestCase):
    def test_analysis_excludes_stale(self) -> None:
        with mock.patch.object(supabase_store, "market_listings_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows") as fetch, \
             mock.patch.object(supabase_store, "market_analysis") as analysis, \
             mock.patch.object(supabase_store, "load_listings", return_value=[]):
            analysis.local_listings_to_rows.return_value = []
            supabase_store._analysis_rows(5000, "market_listings")
        endpoint = fetch.call_args.args[0]
        self.assertIn("status=eq.active", endpoint)


if __name__ == "__main__":
    unittest.main()
