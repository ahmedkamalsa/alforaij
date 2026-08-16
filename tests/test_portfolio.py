"""اختبارات وحدة محفظة المستثمر: التقييم من التوقعات وprice_trends، والعائد والتغير."""
import unittest

from backend.services.portfolio import (
    build_summary,
    estimate_current_value,
    expected_price_per_sqm,
    median_price_per_sqm,
)


FORECAST = [
    {"area": "السالمية", "expectedPricePerSqm": 1250.0},
    {"area": "الرميثية", "expectedPricePerSqm": 1100.0},
    {"area": "السالمية", "expectedPricePerSqm": 1300.0},  # أعلى قيمة تُفضَّل
]

TRENDS = [
    {"area": "السالمية", "property_type": "شقة", "month": "2026-06", "median_price_per_m2": 1000},
    {"area": "السالمية", "property_type": "شقة", "month": "2026-08", "median_price_per_m2": 1200},
    {"area": "السالمية", "property_type": "بيت", "month": "2026-08", "median_price_per_m2": 1400},
    {"area": "الرميثية", "property_type": "شقة", "month": "2026-07", "median_price_per_m2": 900},
]


class ExpectedPricePerSqmTest(unittest.TestCase):
    def test_matches_area_and_prefers_highest(self):
        self.assertEqual(expected_price_per_sqm("السالمية", FORECAST), 1300.0)

    def test_normalizes_hamza(self):
        self.assertEqual(expected_price_per_sqm("الأحمدي", [{"area": "الاحمدي", "expectedPricePerSqm": 1500.0}]), 1500.0)

    def test_unknown_area_returns_none(self):
        self.assertIsNone(expected_price_per_sqm("الفروانية", FORECAST))

    def test_empty_forecast_returns_none(self):
        self.assertIsNone(expected_price_per_sqm("السالمية", None))


class MedianPricePerSqmTest(unittest.TestCase):
    def test_type_specific_latest_month_wins(self):
        self.assertEqual(median_price_per_sqm("السالمية", "شقة", TRENDS), 1200.0)

    def test_area_only_fallback(self):
        # لا صفوف لنوع «أرض» في السالمية — يسقط لوسيط المنطقة (أحدث شهر)
        self.assertEqual(median_price_per_sqm("السالمية", "أرض", TRENDS), 1200.0)

    def test_unknown_area_returns_none(self):
        self.assertIsNone(median_price_per_sqm("الجهراء", "شقة", TRENDS))

    def test_empty_trends_returns_none(self):
        self.assertIsNone(median_price_per_sqm("السالمية", "شقة", None))


class EstimateCurrentValueTest(unittest.TestCase):
    def test_value_from_forecast(self):
        item = {"area": "السالمية", "property_type": "شقة", "space": 200, "purchase_price": 200000}
        est = estimate_current_value(item, FORECAST, TRENDS)
        self.assertEqual(est["estimatedValue"], 260000.0)
        self.assertEqual(est["pricePerSqm"], 1300.0)
        self.assertEqual(est["changePct"], 30.0)

    def test_yield_computed_from_rent(self):
        item = {"area": "السالمية", "space": 200, "purchase_price": 200000, "monthly_rent": 900}
        est = estimate_current_value(item, FORECAST, TRENDS)
        self.assertEqual(est["yieldPct"], 5.4)  # 900 × 12 / 200000

    def test_no_space_yields_no_value(self):
        item = {"area": "السالمية", "purchase_price": 200000}
        est = estimate_current_value(item, FORECAST, TRENDS)
        self.assertIsNone(est["estimatedValue"])
        self.assertIsNone(est["changePct"])

    def test_no_purchase_no_delta(self):
        item = {"area": "السالمية", "space": 200}
        est = estimate_current_value(item, FORECAST, TRENDS)
        self.assertEqual(est["estimatedValue"], 260000.0)
        self.assertIsNone(est["changePct"])
        self.assertIsNone(est["yieldPct"])

    def test_unknown_area_falls_back_to_trends_then_none(self):
        est = estimate_current_value({"area": "الجهراء", "space": 300}, None, TRENDS)
        self.assertIsNone(est["estimatedValue"])

    def test_nan_price_guarded(self):
        est = estimate_current_value({"area": "السالمية", "space": float("nan"), "purchase_price": 1}, FORECAST, TRENDS)
        self.assertIsNone(est["estimatedValue"])


class BuildSummaryTest(unittest.TestCase):
    def test_merges_estimates_without_mutating_input(self):
        items = [{"area": "السالمية", "space": 200, "purchase_price": 200000}]
        out = build_summary(items, FORECAST, TRENDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["estimatedValue"], 260000.0)
        self.assertNotIn("estimatedValue", items[0])  # لا تعديل للعنصر الأصلي

    def test_empty_items(self):
        self.assertEqual(build_summary([], FORECAST, TRENDS), [])


if __name__ == "__main__":
    unittest.main()
