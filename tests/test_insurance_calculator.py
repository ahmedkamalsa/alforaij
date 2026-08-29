"""اختبارات حاسبة التأمين العقاري — الكويت.

تغطي:
- حساب تكلفة التأمين
- مقارنة خيارات التأمين
- الخصومات
- الحدود الأدنى والأقصى
"""
from __future__ import annotations

import unittest

from backend.services.insurance_calculator import (
    calculate_insurance,
    compare_insurance_options,
    INSURANCE_TYPES,
    MIN_INSURANCE_AMOUNT,
    MAX_INSURANCE_AMOUNT,
)


class InsuranceCalculationTests(unittest.TestCase):
    """اختبارات حساب التأمين."""

    def test_basic_property_insurance(self) -> None:
        """تأمين الممتلكات الأساسي."""
        result = calculate_insurance(300000, "property")
        self.assertGreater(result["annual_cost"], 0)
        self.assertEqual(result["insurance_type"], "property")

    def test_comprehensive_insurance(self) -> None:
        """التأمين الشامل مع محتويات."""
        result = calculate_insurance(300000, "comprehensive", contents_value=50000)
        self.assertGreater(result["contents_cost"], 0)
        self.assertGreater(result["total_annual"], result["annual_cost"])

    def test_new_building_discount(self) -> None:
        """عقار جديد = خصم."""
        result = calculate_insurance(300000, "property", building_age=2)
        self.assertGreater(result["total_discount"], 0)
        self.assertEqual(len(result["discounts"]), 1)

    def test_security_discount(self) -> None:
        """نظام أمان = خصم."""
        result = calculate_insurance(300000, "property", has_security=True)
        self.assertGreater(result["total_discount"], 0)

    def test_multi_year_discount(self) -> None:
        """تأمين 3+ سنوات = خصم."""
        result = calculate_insurance(300000, "property", years=3)
        self.assertGreater(result["total_discount"], 0)

    def test_invalid_price(self) -> None:
        """سعر غير صالح."""
        result = calculate_insurance(0, "property")
        self.assertIn("error", result)

    def test_too_low_price(self) -> None:
        """سعر أقل من الحد الأدنى."""
        result = calculate_insurance(10000, "property")
        self.assertIn("error", result)

    def test_too_high_price(self) -> None:
        """سعر يتجاوز الحد الأقصى."""
        result = calculate_insurance(10000000, "property")
        self.assertIn("error", result)


class InsuranceComparisonTests(unittest.TestCase):
    """اختبارات مقارنة التأمين."""

    def test_returns_multiple_options(self) -> None:
        """النتيجة تتضمن عدة خيارات."""
        result = compare_insurance_options(300000)
        self.assertGreater(len(result["options"]), 0)

    def test_sorted_by_cost(self) -> None:
        """الخيارات مرتبة حسب التكلفة."""
        result = compare_insurance_options(300000)
        costs = [o["total_annual"] for o in result["options"]]
        self.assertEqual(costs, sorted(costs))

    def test_has_best_option(self) -> None:
        """النتيجة تتضمن أفضل خيار."""
        result = compare_insurance_options(300000)
        self.assertIsNotNone(result["best_option"])

    def test_has_recommendation(self) -> None:
        """النتيجة تتضمن توصية."""
        result = compare_insurance_options(300000)
        self.assertIn("recommendation", result)
        self.assertIn("summary", result["recommendation"])

    def test_invalid_price(self) -> None:
        """سعر غير صالح."""
        result = compare_insurance_options(0)
        self.assertIn("error", result)


class InsuranceTypesTests(unittest.TestCase):
    """اختبارات بيانات أنواع التأمين."""

    def test_all_types_have_required_fields(self) -> None:
        """كل نوع له الحقول المطلوبة."""
        required = ["name", "name_en", "rate_min", "rate_max", "description", "features"]
        for code, info in INSURANCE_TYPES.items():
            for field in required:
                self.assertIn(field, info, f"{code} missing {field}")

    def test_rates_are_reasonable(self) -> None:
        """النسب معقولة (0.01% - 1%)."""
        for code, info in INSURANCE_TYPES.items():
            self.assertGreaterEqual(info["rate_min"], 0.01, f"{code} rate too low")
            self.assertLessEqual(info["rate_max"], 1.0, f"{code} rate too high")


if __name__ == "__main__":
    unittest.main()
