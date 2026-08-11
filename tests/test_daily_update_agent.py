from __future__ import annotations

import unittest
from unittest import mock


class DailyUpdateAgentTests(unittest.TestCase):
    def test_run_daily_update_agent_writes_success_status(self) -> None:
        from backend.services import daily_update_agent

        snapshot = {"tiers": {"daily": {"items": []}}, "totalScored": 0}
        with mock.patch.object(daily_update_agent, "is_configured", return_value=True), \
            mock.patch.object(daily_update_agent, "sync_source_registry"), \
            mock.patch.object(daily_update_agent, "load_listings", return_value=[]), \
            mock.patch.object(daily_update_agent, "save_listings"), \
            mock.patch.object(daily_update_agent, "fetch_latest_opportunities", return_value=None), \
            mock.patch.object(daily_update_agent, "build_opportunities", return_value=snapshot), \
            mock.patch.object(daily_update_agent, "save_opportunities"), \
            mock.patch.object(daily_update_agent, "supabase_data_summary", return_value={"tables": {}}), \
            mock.patch.object(daily_update_agent, "save_update_notifications"), \
            mock.patch.object(daily_update_agent, "_write_status"):
            result = daily_update_agent.run_daily_update_agent(include_external=False)

        self.assertEqual(result["status"], "success")
        self.assertIn("build_and_save_opportunities", [step["name"] for step in result["steps"]])

    def test_build_price_trends_groups_medians_by_area_type_month(self) -> None:
        from backend.services.daily_update_agent import _build_price_trends

        external = [
            {"area": "النهضة", "property_type": "بيت", "transaction": "للبيع", "price": 300000, "space": 400, "fetched_at": "2026-08-05T09:00:00"},
            {"area": "النهضة", "property_type": "بيت", "transaction": "للبيع", "price": 320000, "space": 400, "fetched_at": "2026-08-06T09:00:00"},
            {"area": "حولي", "property_type": "شقة", "transaction": "للإيجار", "price": 500, "space": None, "fetched_at": "2026-07-20T09:00:00"},
            {"area": "النهضة", "property_type": "بيت", "transaction": "للبيع", "price": None, "fetched_at": "2026-08-07T09:00:00"},  # بلا سعر — يُستبعد
        ]
        rows = _build_price_trends(external, [])

        self.assertEqual(len(rows), 2)  # النهضة/بيت/2026-08 + حولي/شقة/2026-07 (بدون سعر يُستبعد)
        by_key = {(r["area"], r["property_type"], r["month"]) : r for r in rows}
        nahda = by_key[("النهضة", "بيت", "2026-08")]
        self.assertEqual(nahda["median_price"], 310000.0)  # وسيط 300k و320k
        self.assertEqual(nahda["median_price_per_m2"], 775.0)  # 310000/400
        self.assertEqual(nahda["sample_count"], 2)
        hawally = by_key[("حولي", "شقة", "2026-07")]
        self.assertEqual(hawally["median_price"], 500.0)
        self.assertIsNone(hawally["median_price_per_m2"])  # بلا مساحة

    def test_build_price_trends_merges_local_listings(self) -> None:
        from backend.services.daily_update_agent import _build_price_trends

        class _Listing:
            def __init__(self) -> None:
                self.area = "السالمية"
                self.property_type = "شقة"
                self.transaction = "للإيجار"
                self.price = 350.0
                self.space = 90.0
                self.published_date = "2026-08-01"

        rows = _build_price_trends([], [_Listing()])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["area"], "السالمية")
        self.assertEqual(rows[0]["month"], "2026-08")
        self.assertAlmostEqual(rows[0]["median_price_per_m2"], 3.9, places=1)


if __name__ == "__main__":
    unittest.main()
