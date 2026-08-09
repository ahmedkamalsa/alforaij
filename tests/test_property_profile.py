from __future__ import annotations

import unittest

from backend.models import Listing
from backend.services.property_profile import detect_property_profile


def listing(text: str, property_type: str = "بيت") -> Listing:
    return Listing(
        code="T-1",
        transaction="للبيع",
        governorate="",
        area="",
        property_type=property_type,
        detail_class="",
        price=100000,
        price_text="100,000 د.ك",
        space=400,
        listing_mode="",
        summary=text,
        features=text,
        published_date="",
        original_url="",
    )


class PropertyProfileTests(unittest.TestCase):
    def test_government_credit_bank_profile(self) -> None:
        profile = detect_property_profile(listing("للبيع بيت حكومي مطلوب لبنك الائتمان 32000 د.ك شهادة الأوصاف جاهزة"))

        self.assertEqual(profile["assetClass"], "بيت")
        self.assertEqual(profile["tenure"], "حكومي/رعاية سكنية")
        self.assertEqual(profile["financeStatus"], "مرتبط ببنك الائتمان/الإسكان")
        self.assertEqual(profile["legalStatus"], "مذكور مستند/وثيقة")
        self.assertTrue(profile["flags"])

    def test_investment_commercial_profile(self) -> None:
        profile = detect_property_profile(listing("قسيمة صناعية مؤجرة بالكامل فيها 41 محل تجاري", "تجاري"))

        self.assertEqual(profile["assetClass"], "أرض/قسيمة")
        self.assertEqual(profile["usage"], "تجاري/صناعي")
        self.assertGreaterEqual(profile["confidence"], 55)


if __name__ == "__main__":
    unittest.main()
