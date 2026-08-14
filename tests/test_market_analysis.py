from __future__ import annotations

import unittest

from backend.services.market_analysis import (
    build_market_analytics,
    build_market_insights,
    clean_outliers,
    median,
)


class MedianTests(unittest.TestCase):
    def test_median_empty_is_none(self) -> None:
        self.assertIsNone(median([]))

    def test_median_odd_count_rounds_to_one_decimal(self) -> None:
        self.assertEqual(median([1, 2, 3]), 2.0)
        self.assertEqual(median([1.0, 2.15, 3.0]), 2.1)

    def test_median_even_count_averages_middle_two(self) -> None:
        self.assertEqual(median([1, 2, 3, 4]), 2.5)
        self.assertEqual(median([10, 20]), 15.0)

    def test_median_single_value(self) -> None:
        self.assertEqual(median([42]), 42.0)


class CleanOutliersTests(unittest.TestCase):
    def test_small_samples_untouched(self) -> None:
        values = [1, 2, 3]
        self.assertEqual(clean_outliers(values), values)

    def test_flat_distribution_untouched(self) -> None:
        values = [5, 5, 5, 5]
        self.assertEqual(clean_outliers(values), values)

    def test_removes_extreme_value_by_3x_iqr(self) -> None:
        values = [100, 110, 120, 130, 140, 9000]
        cleaned = clean_outliers(values)
        self.assertNotIn(9000, cleaned)
        self.assertIn(100, cleaned)
        self.assertIn(140, cleaned)


class MarketAnalyticsTests(unittest.TestCase):
    def _rows(self):
        return [
            {"source": "Mourjan", "transaction": "للبيع", "property_type": "بيت", "area": "صباح الناصر", "governorate": "الفروانية", "price": 450000, "space": 500, "phone": "5000", "fetched_at": "2026-08-01T10:00:00"},
            {"source": "Mourjan", "transaction": "للبيع", "property_type": "بيت", "area": "صباح الناصر", "governorate": "الفروانية", "price": 460000, "space": 500, "phone": "5000", "fetched_at": "2026-08-02T10:00:00"},
            {"source": "OpenSooq", "transaction": "للإيجار", "property_type": "شقة", "area": "حولي", "governorate": "", "price": 2500, "space": 120, "phone": "", "fetched_at": "2026-08-01T09:00:00"},
            {"source": "", "transaction": "", "property_type": "", "area": "", "governorate": "", "price": "bad", "space": None, "phone": "", "fetched_at": "2026-08-01T08:00:00"},
        ]

    def test_totals_and_source_buckets(self) -> None:
        result = build_market_analytics(self._rows())
        self.assertEqual(result["totals"]["rows"], 4)
        self.assertEqual(result["totals"]["sources"], 3)  # غير معروف يُضاف للمجهول
        self.assertEqual(result["totals"]["areas"], 2)
        self.assertEqual(result["totals"]["governorates"], 1)
        by_name = {s["source"]: s for s in result["sources"]}
        self.assertEqual(by_name["Mourjan"]["count"], 2)
        self.assertEqual(by_name["Mourjan"]["phones"], 2)
        self.assertEqual(by_name["Mourjan"]["price"]["median"], 455000.0)
        self.assertEqual(by_name["OpenSooq"]["price"]["median"], 2500.0)
        # السعر غير الصالح لم يكسر الدفعة — صف مجهول المصدر دخل كمصدر «غير معروف»
        self.assertIn("غير معروف", by_name)

    def test_empty_rows_return_empty_totals(self) -> None:
        result = build_market_analytics([])
        self.assertEqual(result["totals"]["rows"], 0)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["areas"], [])


class MarketInsightsTests(unittest.TestCase):
    def _rows(self):
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

    def test_yield_and_totals(self) -> None:
        result = build_market_insights(self._rows())
        areas = {a["area"]: a for a in result["areas"]}
        hawally = areas["حولي"]
        self.assertAlmostEqual(hawally["rentalYield"], 5.0, places=1)
        self.assertEqual(hawally["medianSalePerM2"], 2000.0)
        self.assertEqual(hawally["governorate"], "حولي")  # مستنتجة من خريطة المحلل
        self.assertIsNone(areas["الفروانية"]["rentalYield"])
        self.assertIsNone(areas["المنقف"]["rentalYield"])  # إيجار واحد → حارس الموثوقية
        self.assertEqual(result["sampleTotals"], {"sale": 7, "rent": 3})
        self.assertEqual(len(areas), 3)

    def test_series_needs_two_months(self) -> None:
        result = build_market_insights(self._rows())
        areas_in_series = {s["area"] for s in result["series"]}
        self.assertIn("حولي", areas_in_series)
        self.assertNotIn("الفروانية", areas_in_series)
        self.assertIn("2026-08", result["months"])

    def test_market_direction_stable_on_flat_series(self) -> None:
        rows = [
            {"area": "أ", "governorate": "", "transaction": "للبيع", "price": 1000, "space": 100, "fetched_at": "2026-07-01T00:00:00"},
            {"area": "أ", "governorate": "", "transaction": "للبيع", "price": 1000, "space": 100, "fetched_at": "2026-08-01T00:00:00"},
        ]
        result = build_market_insights(rows)
        self.assertEqual(result["market"]["direction"], "مستقر")
        self.assertEqual(result["market"]["changePct"], 0.0)

    def test_empty_rows(self) -> None:
        result = build_market_insights([])
        self.assertEqual(result["areas"], [])
        self.assertEqual(result["series"], [])
        self.assertEqual(result["sources"], [])


if __name__ == "__main__":
    unittest.main()
