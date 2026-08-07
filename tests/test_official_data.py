from __future__ import annotations

import datetime as _dt
import unittest
from unittest import mock

from backend.connectors import official_data


class OfficialDataTests(unittest.TestCase):
    def _seed(self, rows: list[dict]) -> mock.patch:
        """حقن صفوف في الكاش الموحد (الصفوف + فهرس المناطق المبني مسبقًا)."""
        return mock.patch.object(
            official_data,
            "_load_cached",
            return_value=(rows, official_data._build_area_index(rows)),
        )

    def test_rate_median_from_transactions(self) -> None:
        with self._seed(
            [
                {"area": "خيطان", "price": "216000", "space": "300"},
                {"area": "خيطان", "price": "240000", "space": "300"},
                {"area": "خيطان", "price": "210000", "space": "300"},
                {"area": "السالمية", "price": "500000", "space": "400"},
            ]
        ):
            rate, count, window = official_data.get_official_transaction_rate("خيطان")
            self.assertEqual(count, 3)
            # الوسيط: 720 (216k/300), 800 (240k/300), 700 (210k/300) → 720
            self.assertEqual(rate, 720.0)
            # بلا تواريخ تُستخدم نافذة «كامل السجل المتاح»
            self.assertIn("كامل", window)
            missing, missing_count, _missing_window = official_data.get_official_transaction_rate("الرميثية")
            self.assertIsNone(missing)
            self.assertEqual(missing_count, 0)

    def test_search_returns_listings_filtered_by_area(self) -> None:
        rows = [
            {"reference": "MOJ-1", "area": "خيطان", "property_type": "بيت", "price": 216000, "space": 300, "date": "2026-07-01"},
            {"reference": "MOJ-2", "area": "السالمية", "property_type": "شقة", "price": 500000, "space": 400, "date": "2026-07-02"},
        ]
        from backend.services.request_parser import parse_request

        request = parse_request("بيت للبيع في خيطان")
        with self._seed(rows):
            listings, status = official_data.search(request)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].code, "OFF-MOJ-1")
        self.assertEqual(listings[0].area, "خيطان")
        self.assertEqual(listings[0].source, "الصفقات الرسمية")
        self.assertEqual(status["status"], "success")
        self.assertIn("مرجّح", status["note"])

    def test_search_tolerant_when_no_data(self) -> None:
        from backend.services.request_parser import parse_request

        request = parse_request("بيت للبيع في خيطان")
        with self._seed([]):
            listings, status = official_data.search(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "no_data")
        self.assertIn("import_official_transactions", status["note"])

    def test_transaction_listing_builds_clean_listing(self) -> None:
        listing = official_data._transaction_listing(
            {"reference": "MOJ-9", "area": "السالمية", "property_type": "بيت", "price": "450000", "space": "400"},
            0,
        )
        self.assertEqual(listing.price, 450000.0)
        self.assertEqual(listing.space, 400.0)
        self.assertEqual(listing.detail_class, "صفقة رسمية مسجلة")

    def test_valuation_uses_official_transactions_as_top_reference(self) -> None:
        """الصفقات الرسمية تتصدر مراجع التقييم قبل المعيار الرسمي والإعلانات."""
        from backend.models import Listing
        from backend.services import valuation

        target = Listing(
            code="T1", transaction="للبيع", governorate="", area="خيطان", property_type="بيت",
            detail_class="", price=220000, price_text="220,000 د.ك", space=300, listing_mode="",
            summary="", features="", published_date="", original_url="", source="الفريج",
        )
        comps = [
            Listing(
                code=f"C{i}", transaction="للبيع", governorate="", area="خيطان", property_type="بيت",
                detail_class="", price=240000, price_text="", space=300, listing_mode="",
                summary="", features="", published_date="", original_url="", source="الفريج",
            )
            for i in range(3)
        ]
        # صفقات رسمية بوسيط 800 د.ك/م² مقابل معيار خيطان الرسمي 720
        # بعد إعادة الهندسة أصبحت الدالة مستوردة في valuation، فتهجينها هناك
        with mock.patch.object(
            valuation, "get_official_transaction_rate", return_value=(800.0, 2, "آخر 24 شهرًا")
        ), self._seed([]):
            value, breakdown, kind, count, window = valuation._official_valuation(target, comps)
            self.assertEqual(kind, "official_transactions")
            self.assertEqual(value, 240000.0)
            self.assertEqual(count, 2)
            self.assertIn("الصفقات الرسمية", breakdown[0]["factor"])
            self.assertIn("24 شهرًا", window)

            result = valuation.price_label(target, comps)
            self.assertEqual(result.official_source_kind, "official_transactions")
            self.assertEqual(result.official_window, "آخر 24 شهرًا")
            self.assertGreaterEqual(result.confidence, 0.9)

    def test_number_sources_does_not_crash_when_price_missing_but_official_value_set(self) -> None:
        """انحدار: إعلان بلا سعر مع معيار رسمي متاح كان يهوي بـ market_median=None."""
        from backend.models import Listing
        from backend.services import valuation

        no_price = Listing(
            code="NOPRICE", transaction="للبيع", governorate="", area="خيطان", property_type="بيت",
            detail_class="", price=None, price_text="غير معلن", space=300, listing_mode="",
            summary="", features="", published_date="", original_url="", source="الفريج",
        )
        comps = []
        with mock.patch.object(
            valuation, "get_official_transaction_rate", return_value=(None, 0, "")
        ), self._seed([]):
            result = valuation.price_label(no_price, comps)
            sources = valuation.number_sources(no_price, result)
        # لا انهيار، والوسيط يعرض القيمة الرسمية بأمان (لا None :,.0f)
        self.assertIn("د.ك", sources["marketMedian"]["source"])

    def test_recent_window_preferred_when_enough_recent_transactions(self) -> None:
        """الصفقات الحديثة (آخر 24 شهرًا) تتصدر الوسيط عند توفر ≥3 منها."""
        today = _dt.date.today()
        recent_date = (today - _dt.timedelta(days=10)).isoformat()
        old_date = (today - _dt.timedelta(days=1000)).isoformat()
        with self._seed(
            [
                # ثلاث حديثات: 800, 700, 720 → وسيط 720
                {"area": "خيطان", "price": "240000", "space": "300", "date": recent_date},
                {"area": "خيطان", "price": "210000", "space": "300", "date": recent_date},
                {"area": "خيطان", "price": "216000", "space": "300", "date": recent_date},
                # قديمة جدًا: 1500 و1000 (لا تدخل في النافذة الحديثة)
                {"area": "خيطان", "price": "450000", "space": "300", "date": old_date},
                {"area": "خيطان", "price": "300000", "space": "300", "date": old_date},
            ]
        ):
            rate, count, window = official_data.get_official_transaction_rate("خيطان")
        self.assertEqual(count, 3)
        self.assertEqual(rate, 720.0)
        self.assertIn("24 شهرًا", window)

    def test_falls_back_to_full_history_when_few_recent(self) -> None:
        """عند قلة الحديثة (<3) يسقط الوسيط لكامل السجل مع الإفصاح."""
        today = _dt.date.today()
        recent_date = (today - _dt.timedelta(days=10)).isoformat()
        old_date = (today - _dt.timedelta(days=1000)).isoformat()
        with self._seed(
            [
                # حديثة واحدة فقط (720) + قديمتان (600 و800) → وسيط الكل 720
                {"area": "خيطان", "price": "216000", "space": "300", "date": recent_date},
                {"area": "خيطان", "price": "180000", "space": "300", "date": old_date},
                {"area": "خيطان", "price": "240000", "space": "300", "date": old_date},
            ]
        ):
            rate, count, window = official_data.get_official_transaction_rate("خيطان")
        self.assertEqual(count, 3)
        self.assertEqual(rate, 720.0)
        self.assertIn("كامل", window)

    def test_merge_rows_deduplicates_same_reference(self) -> None:
        """الصفقة المحفوظة في Supabase وفي الملف المحلي تُحتسب مرة واحدة فقط."""
        supabase = [{"reference": "MOJ-1", "area": "خيطان", "price": 216000, "space": 300}]
        local = [{"reference": "MOJ-1", "area": "خيطان", "price": 216000, "space": 300},
                 {"reference": "MOJ-2", "area": "السالمية", "price": 500000, "space": 400}]
        merged = official_data._merge_rows(supabase, local)
        self.assertEqual(len(merged), 2)
        self.assertEqual({r["reference"] for r in merged}, {"MOJ-1", "MOJ-2"})

    def test_merge_rows_prefers_supabase_row(self) -> None:
        """عند التضارب تبقى نسخة Supabase (الأحدث) هي المعتمدة."""
        supabase = [{"reference": "MOJ-1", "area": "خيطان", "price": 240000, "space": 300}]
        local = [{"reference": "MOJ-1", "area": "خيطان", "price": 216000, "space": 300}]
        merged = official_data._merge_rows(supabase, local)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["price"], 240000)

    def test_comma_formatted_prices_parse_correctly(self) -> None:
        """فواصل الآلاف في CSV ('450,000') لا تكسر التحويل إلى رقم."""
        rate = official_data._row_rate({"price": "450,000", "space": "300"})
        self.assertEqual(rate, 1500.0)
        listing = official_data._transaction_listing(
            {"reference": "MOJ-9", "area": "السالمية", "property_type": "بيت",
             "price": "450,000", "space": "300"},
            0,
        )
        self.assertEqual(listing.price, 450000.0)
        self.assertEqual(listing.space, 300.0)

    def test_search_excludes_unknown_area_when_areas_requested(self) -> None:
        """صفقة بلا منطقة لا تتسرب إلى بحث منطقة محددة."""
        from backend.services.request_parser import parse_request

        rows = [
            {"reference": "MOJ-1", "area": "خيطان", "property_type": "بيت", "price": 216000, "space": 300},
            {"reference": "MOJ-2", "area": "", "property_type": "بيت", "price": 400000, "space": 300},
        ]
        request = parse_request("بيت للبيع في خيطان")
        with self._seed(rows), mock.patch.object(official_data, "load_transactions", return_value=rows):
            listings, status = official_data.search(request)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].code, "OFF-MOJ-1")
        self.assertEqual(status["status"], "success")

    def test_sakan_extractor_preserves_arabic(self) -> None:
        """استخراج Sakan لا يشوّه النص العربي متعدد البايتات."""
        from backend.connectors.live_sources import _extract_sakan_embedded

        body = (
            "<script>window.__LIST = {" +
            '"listings": [{"title": "بيت للبيع في خيطان", "url": "/en/buy/house/farwaniya/khaitan/x1", "price": 220000}]' +
            "};</script>"
        )
        found = _extract_sakan_embedded(body)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["title"], "بيت للبيع في خيطان")
        self.assertEqual(found[0]["price"], 220000)

    def test_sakan_extractor_handles_escaped_quotes_in_json_parse(self) -> None:
        """JSON.parse بمحتوى يحتوي اقتباسات مائلة لا يُقتطع (انحدار regex)."""
        from backend.connectors.live_sources import _extract_sakan_embedded

        body = (
            "<script>const d = JSON.parse(" +
            '"{\\\"title\\\": \\\"بيت زاوية في خيطان\\\", \\\"url\\\": \\\"/en/buy/house/farwaniya/khaitan/x2\\\", \\\"price\\\": 320000}"' +
            ");</script>"
        )
        found = _extract_sakan_embedded(body)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["title"], "بيت زاوية في خيطان")
        self.assertEqual(found[0]["price"], 320000)

    def test_to_float_accepts_arabic_indic_digits(self) -> None:
        """الأرقام العربية الهندية (٢٢٠٠٠٠) في CSV محلي تُقرأ كأرقام."""
        self.assertEqual(official_data._to_float("٢٢٠٠٠٠"), 220000.0)
        self.assertEqual(official_data._to_float("٢٢٠,٠٠٠"), 220000.0)
        self.assertIsNone(official_data._to_float(""))
        self.assertIsNone(official_data._to_float(None))

    def test_source_id_derived_from_registry_for_new_sources(self) -> None:
        """المصادر الجديدة تُسجَّل بمعرفاتها الصحيحة من السجل لا بأسماء منخفضة."""
        from backend.services.supabase_store import _source_id_for

        self.assertEqual(_source_id_for("Aqarat"), "aqarat")
        self.assertEqual(_source_id_for("4Sale"), "four_sale")
        self.assertEqual(_source_id_for("الصفقات الرسمية"), "official_transactions")

    def test_source_id_short_name_does_not_false_match(self) -> None:
        """اسم قصير مثل «عقار» لا يُلتقط داخل «بوعقار» أو «التسجيل العقاري»."""
        from backend.services.supabase_store import _source_id_for

        short_id = _source_id_for("عقار")
        self.assertNotEqual(short_id, "bu3qar")
        self.assertNotEqual(short_id, "official_transactions")

    def test_number_sources_does_not_crash_with_official_transactions_kind(self) -> None:
        """انحدار ثانٍ: kind=official_transactions بلا وسيط إعلانات (market_median=None)."""
        from backend.models import Listing
        from backend.services import valuation

        no_price = Listing(
            code="NOPRICE2", transaction="للبيع", governorate="", area="خيطان", property_type="بيت",
            detail_class="", price=None, price_text="غير معلن", space=300, listing_mode="",
            summary="", features="", published_date="", original_url="", source="الفريج",
        )
        comps = []
        # وسيط صفقات رسمية 800 د.ك/م² → official_value=240,000 لكن لا إعلانات → market_median=None
        with mock.patch.object(
            valuation, "get_official_transaction_rate", return_value=(800.0, 2, "آخر 24 شهرًا")
        ), self._seed([]):
            result = valuation.price_label(no_price, comps)
            sources = valuation.number_sources(no_price, result)
        self.assertEqual(result.official_source_kind, "official_transactions")
        self.assertIsNone(result.market_median)
        # لا انهيار، والوسيط المعروض يسقط على القيمة الرسمية الآمنة
        self.assertIn("الصفقات الرسمية", sources["marketMedian"]["source"])
        self.assertIn("240,000", sources["marketMedian"]["source"])


if __name__ == "__main__":
    unittest.main()
