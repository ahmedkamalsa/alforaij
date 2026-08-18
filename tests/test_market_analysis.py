from __future__ import annotations

import unittest

from backend.models import Listing
from backend.services.market_analysis import (
    build_demand_indicators,
    build_market_analytics,
    build_market_insights,
    clean_outliers,
    is_demand_transaction,
    is_rent_transaction,
    is_sale_transaction,
    local_listing_to_row,
    local_listings_to_rows,
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
        # نفس خريطة اللوحة المعتمدة: «حولي» كمنطقة تُحسم لمحافظتها الكنسية
        self.assertEqual(hawally["governorate"], "محافظة حولي")
        self.assertIsNone(areas["الفروانية"]["rentalYield"])
        self.assertIsNone(areas["المنقف"]["rentalYield"])  # إيجار واحد → حارس الموثوقية
        self.assertEqual(result["sampleTotals"], {"sale": 7, "rent": 3, "buyRequests": 0, "rentRequests": 0})
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


class TransactionClassificationTests(unittest.TestCase):
    def test_sale_helpers_cover_buy_requests(self) -> None:
        # «مطلوب للشراء» لا تحتوي «بيع» — هذا كان العيب الخفي (تُسقط من جانب البيع)
        self.assertTrue(is_sale_transaction("مطلوب للشراء"))
        self.assertTrue(is_sale_transaction("للبيع"))
        self.assertFalse(is_rent_transaction("مطلوب للشراء"))

    def test_rent_helpers_cover_rent_requests(self) -> None:
        self.assertTrue(is_rent_transaction("مطلوب للإيجار"))
        self.assertTrue(is_rent_transaction("للإيجار"))
        self.assertFalse(is_sale_transaction("مطلوب للإيجار"))

    def test_demand_flag_distinguishes_requests(self) -> None:
        self.assertTrue(is_demand_transaction("مطلوب للشراء"))
        self.assertTrue(is_demand_transaction("مطلوب للإيجار"))
        self.assertFalse(is_demand_transaction("للبيع"))
        self.assertFalse(is_demand_transaction("للإيجار"))


class DemandInInsightsTests(unittest.TestCase):
    def test_requests_counted_in_sample_totals(self) -> None:
        rows = [
            {"area": "حولي", "transaction": "مطلوب للشراء", "price": 500000, "space": 300, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "حولي", "transaction": "مطلوب للإيجار", "price": 800, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "حولي", "transaction": "للبيع", "price": 600000, "space": 300, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "حولي", "transaction": "للإيجار", "price": 2500, "space": None, "fetched_at": "2026-08-10T08:00:00"},
        ]
        result = build_market_insights(rows)
        self.assertEqual(
            result["sampleTotals"],
            {"sale": 1, "rent": 1, "buyRequests": 1, "rentRequests": 1},
        )

    def test_demand_budgets_do_not_pollute_supply_medians(self) -> None:
        # ميزانية طلب شراء (500,000) لا تدخل وسيط البيع، وميزانية طلب إيجار لا تدخل وسيط الإيجار
        rows = [
            {"area": "السالمية", "transaction": "للبيع", "price": 120000, "space": 200, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "السالمية", "transaction": "مطلوب للشراء", "price": 500000, "space": 200, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "السالمية", "transaction": "للإيجار", "price": 250, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "السالمية", "transaction": "للإيجار", "price": 350, "space": None, "fetched_at": "2026-08-10T08:00:00"},
            {"area": "السالمية", "transaction": "مطلوب للإيجار", "price": 5000, "space": None, "fetched_at": "2026-08-10T08:00:00"},
        ]
        result = build_market_insights(rows)
        area = next(a for a in result["areas"] if a["area"] == "السالمية")
        self.assertEqual(area["saleCount"], 1)
        self.assertEqual(area["medianSalePrice"], 120000.0)
        self.assertEqual(area["rentCount"], 2)
        self.assertEqual(area["medianRent"], 300.0)


class DemandInAnalyticsTests(unittest.TestCase):
    def test_analytics_transactions_and_demand_breakdown(self) -> None:
        rows = [
            {"source": "4Sale", "transaction": "للبيع", "area": "حولي", "governorate": "", "property_type": "بيت", "price": 100, "space": None, "fetched_at": ""},
            {"source": "الفريج", "transaction": "مطلوب للشراء", "area": "المطلاع", "governorate": "الجهراء", "property_type": "بيت", "price": None, "space": None, "fetched_at": ""},
            {"source": "الفريج", "transaction": "مطلوب للإيجار", "area": "الجهراء القديمة", "governorate": "الجهراء", "property_type": "سكن", "price": None, "space": None, "fetched_at": ""},
        ]
        result = build_market_analytics(rows)
        self.assertEqual(result["totals"]["transactions"]["مطلوب للشراء"], 1)
        self.assertEqual(result["totals"]["transactions"]["مطلوب للإيجار"], 1)
        self.assertEqual(result["totals"]["demand"], {"buyRequests": 1, "rentRequests": 1})
        by_name = {s["source"]: s for s in result["sources"]}
        self.assertEqual(by_name["الفريج"]["count"], 2)


class DemandIndicatorsTests(unittest.TestCase):
    def _rows(self):
        return [
            {"area": "المطلاع", "governorate": "محافظة الجهراء", "transaction": "مطلوب للشراء", "fetched_at": "2026-07-20T00:00:00"},
            {"area": "المطلاع", "governorate": "محافظة الجهراء", "transaction": "مطلوب للشراء", "fetched_at": "2026-08-01T00:00:00"},
            {"area": "الجهراء القديمة", "governorate": "محافظة الجهراء", "transaction": "مطلوب للإيجار", "fetched_at": "2026-08-05T00:00:00"},
            {"area": "العيون", "governorate": "محافظة الجهراء", "transaction": "مطلوب للشراء", "fetched_at": "2026-08-02T00:00:00"},
            {"transaction": "للبيع", "area": "حولي", "governorate": "محافظة حولي", "fetched_at": "2026-08-01T00:00:00"},
            {"area": "", "transaction": "مطلوب للشراء", "fetched_at": "2026-08-03T00:00:00"},
        ]

    def test_counts_per_area_and_governorate(self) -> None:
        result = build_demand_indicators(self._rows())
        self.assertEqual(result["totals"], {"buyRequests": 4, "rentRequests": 1, "total": 5})
        by_area = {a["area"]: a for a in result["areas"]}
        self.assertEqual(by_area["المطلاع"], {"area": "المطلاع", "governorate": "محافظة الجهراء", "buy": 2, "rent": 0, "total": 2})
        self.assertEqual(by_area["الجهراء القديمة"]["rent"], 1)
        self.assertIn("غير محددة", by_area)  # منطقة فارغة تُجمَّع تحت «غير محددة»
        by_gov = {g["governorate"]: g for g in result["governorates"]}
        self.assertEqual(by_gov["محافظة الجهراء"]["buy"], 3)
        self.assertEqual(by_gov["محافظة الجهراء"]["rent"], 1)

    def test_areas_sorted_by_total_desc(self) -> None:
        result = build_demand_indicators(self._rows())
        totals = [a["total"] for a in result["areas"]]
        self.assertEqual(totals, sorted(totals, reverse=True))
        self.assertEqual(result["areas"][0]["area"], "المطلاع")

    def test_monthly_series(self) -> None:
        result = build_demand_indicators(self._rows())
        by_month = {s["month"]: s for s in result["series"]}
        self.assertEqual(by_month["2026-07"], {"month": "2026-07", "buy": 1, "rent": 0})
        self.assertEqual(by_month["2026-08"]["buy"], 3)
        self.assertEqual(by_month["2026-08"]["rent"], 1)

    def test_supply_rows_ignored_and_empty_tolerant(self) -> None:
        result = build_demand_indicators([{"area": "حولي", "transaction": "للبيع", "fetched_at": "2026-08-01T00:00:00"}])
        self.assertEqual(result["totals"]["total"], 0)
        self.assertEqual(result["areas"], [])
        empty = build_demand_indicators([])
        self.assertEqual(empty["totals"], {"buyRequests": 0, "rentRequests": 0, "total": 0})
        self.assertEqual(empty["platforms"], [])

    def test_platform_breakdown_transparent(self) -> None:
        rows = self._rows() + [
            # طلبات خارجية من 4Sale — تدخل التوزيع بشفافية
            {"area": "السالمية", "source": "4Sale", "transaction": "مطلوب للإيجار", "fetched_at": "2026-08-10T00:00:00"},
            {"area": "السالمية", "source": "4Sale", "transaction": "مطلوب للشراء", "fetched_at": "2026-08-11T00:00:00"},
        ]
        result = build_demand_indicators(rows)
        by_source = {p["source"]: p for p in result["platforms"]}
        # الصفوف المحلية بلا مفتاح source تُجمَّع تحت «غير محدد»
        self.assertEqual(by_source["غير محدد"]["total"], 5)
        self.assertEqual(by_source["4Sale"], {"source": "4Sale", "buy": 1, "rent": 1, "total": 2, "sharePct": 28.6})
        # إجمالي المنصات يساوي إجمالي الطلبات
        self.assertEqual(sum(p["total"] for p in result["platforms"]), result["totals"]["total"])
        # مرتبة تنازليًا
        totals = [p["total"] for p in result["platforms"]]
        self.assertEqual(totals, sorted(totals, reverse=True))


class LocalRowsConversionTests(unittest.TestCase):
    def _listing(self, transaction: str = "مطلوب للشراء") -> Listing:
        return Listing(
            code="AF-315",
            transaction=transaction,
            governorate="محافظة الجهراء",
            area="المطلاع",
            property_type="بيت",
            detail_class="طلب بيت/فيلا",
            price=None,
            price_text="",
            space=None,
            listing_mode="مباشر",
            summary="",
            features="",
            published_date="2026-08-01",
            original_url="https://front.alforaij.com/Listing/Detail/315",
            source="الفريج",
            raw={"phone": "55559950", "publishedDate": "2026-08-01"},
        )

    def test_listing_to_row_shape(self) -> None:
        row = local_listing_to_row(self._listing())
        self.assertEqual(row["transaction"], "مطلوب للشراء")
        self.assertEqual(row["area"], "المطلاع")
        self.assertEqual(row["source"], "الفريج")
        self.assertEqual(row["phone"], "55559950")
        self.assertEqual(row["fetched_at"], "2026-08-01")
        self.assertEqual(row["original_url"], "https://front.alforaij.com/Listing/Detail/315")

    def test_merged_local_and_external_rows(self) -> None:
        local = local_listings_to_rows([self._listing(), self._listing("مطلوب للإيجار")])
        external = [{"source": "4Sale", "transaction": "للبيع", "area": "المطلاع", "governorate": "محافظة الجهراء", "property_type": "بيت", "price": 120000, "space": 300, "fetched_at": "2026-08-01T00:00:00"}]
        result = build_market_insights(local + external)
        self.assertEqual(result["sampleTotals"]["buyRequests"], 1)
        self.assertEqual(result["sampleTotals"]["rentRequests"], 1)
        self.assertEqual(result["sampleTotals"]["sale"], 1)
        by_name = {s["source"]: s for s in result["sources"]}
        self.assertEqual(by_name["الفريج"]["count"], 2)
        self.assertEqual(by_name["4Sale"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
