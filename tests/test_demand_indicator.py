"""اختبارات مؤشر الطلب بجانب النتائج: `backend.main._demand_indicator_payload`.

يغطي نطاق التصفية (مناطق الطلب ← محافظاته ← منطقة أقرب نتيجة)، عدّ الشراء/
الإيجار، الترتيب، والسقف — حتى لا تعرض النتائج طلبات من خارج منطقة التقييم.
"""
from __future__ import annotations

import unittest

from backend.models import Listing, PropertyRequest


def _listing(code: str, transaction: str, area: str, governorate: str, published: str, phone: str = "") -> Listing:
    return Listing(
        code=code,
        transaction=transaction,
        governorate=governorate,
        area=area,
        property_type="بيت",
        detail_class="",
        price=None,
        price_text="",
        space=None,
        listing_mode="مباشر",
        summary=f"مطلوب {transaction} في {area}",
        features="",
        published_date=published,
        original_url=f"https://front.alforaij.com/Listing/Detail/{code}",
        source="الفريج",
        raw={"phone": phone, "publishedDate": published},
    )


class DemandIndicatorPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        from backend import main

        self.main = main

    def _listings(self):
        return [
            _listing("A1", "مطلوب للشراء", "السالمية", "محافظة حولي", "2026-08-10", "5000"),
            _listing("A2", "مطلوب للشراء", "السالمية", "محافظة حولي", "2026-08-01"),
            _listing("A3", "مطلوب للإيجار", "السالمية", "محافظة حولي", "2026-08-05"),
            _listing("B1", "مطلوب للشراء", "حولي", "محافظة حولي", "2026-08-02"),
            _listing("C1", "للبيع", "السالمية", "محافظة حولي", "2026-08-09"),  # عرض — لا يُعدّ طلبًا
        ]

    def test_filters_by_request_areas(self) -> None:
        request = PropertyRequest(raw_text="بيت في السالمية", transaction="للبيع", areas=["السالمية"])
        result = self.main._demand_indicator_payload(self._listings(), request)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["buyRequests"], 2)
        self.assertEqual(result["rentRequests"], 1)
        self.assertEqual(result["scope"], "السالمية")
        areas = {item["area"] for item in result["items"]}
        self.assertEqual(areas, {"السالمية"})

    def test_falls_back_to_governorates_when_no_area(self) -> None:
        request = PropertyRequest(raw_text="بيت في حولي", governorates=["محافظة حولي"])
        result = self.main._demand_indicator_payload(self._listings(), request)
        # السالمية + حولي في نفس المحافظة = 4 طلبات (B1 حولي + A1/A2/A3 السالمية)
        self.assertEqual(result["count"], 4)
        self.assertIn("محافظة حولي", result["scope"])

    def test_falls_back_to_top_result_area(self) -> None:
        request = PropertyRequest(raw_text="بيت")
        result = self.main._demand_indicator_payload(self._listings(), request, top_area="السالمية")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["scope"], "السالمية")

    def test_returns_empty_when_no_demand_in_scope(self) -> None:
        request = PropertyRequest(raw_text="بيت في الجهراء", areas=["المطلاع"])
        result = self.main._demand_indicator_payload(self._listings(), request)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["items"], [])

    def test_supply_rows_never_counted_as_demand(self) -> None:
        request = PropertyRequest(raw_text="")
        result = self.main._demand_indicator_payload(self._listings(), request)
        # بلا مناطق/محافظات/أقرب نتيجة → كل الطلبات (4) بلا العرض (C1)
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["buyRequests"] + result["rentRequests"], 4)

    def test_sorted_newest_first_and_limited_to_12(self) -> None:
        listings = [
            _listing(f"N{i}", "مطلوب للشراء", "السالمية", "محافظة حولي", f"2026-08-{i:02d}")
            for i in range(1, 20)
        ]
        request = PropertyRequest(raw_text="", areas=["السالمية"])
        result = self.main._demand_indicator_payload(listings, request)
        self.assertEqual(len(result["items"]), 12)
        dates = [item["publishedDate"] for item in result["items"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_payload_fields(self) -> None:
        request = PropertyRequest(raw_text="", areas=["السالمية"])
        result = self.main._demand_indicator_payload(self._listings(), request)
        item = next(i for i in result["items"] if i["code"] == "A1")
        self.assertEqual(item["transaction"], "مطلوب للشراء")
        self.assertEqual(item["phone"], "5000")
        self.assertEqual(item["originalUrl"], "https://front.alforaij.com/Listing/Detail/A1")


if __name__ == "__main__":
    unittest.main()
