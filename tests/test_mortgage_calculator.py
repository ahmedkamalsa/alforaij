"""اختبارات حاسبة الرهن العقاري — بنوك الكويت.

تغطي:
- حساب القسط الشهري
- حساب إجمالي الفائدة
- مقارنة البنوك الأربعة
- الدفعة المقدمة والمدة
- نسبة الراتب
- التوصية الذكية
"""
from __future__ import annotations

import unittest

from backend.services.mortgage_calculator import (
    calculate_monthly_payment,
    calculate_total_interest,
    compare_banks,
    KUWAIT_BANKS,
)


class MonthlyPaymentTests(unittest.TestCase):
    """اختبارات حساب القسط الشهري."""

    def test_basic_calculation(self) -> None:
        """حساب أساسي: قرض 100,000 بفائدة 5% لمدة 20 سنة."""
        payment = calculate_monthly_payment(100000, 5.0, 20)
        self.assertGreater(payment, 0)
        self.assertLess(payment, 1000)  # لا يمكن أن يكون أكبر من القرض

    def test_zero_interest(self) -> None:
        """فائدة صفر = القرض ÷عدد الأشهر (120000 / 144 = 833.33)."""
        payment = calculate_monthly_payment(120000, 0.0, 12)
        self.assertAlmostEqual(payment, 833.33, places=2)

    def test_zero_loan(self) -> None:
        """قرض صفر = قسط صفر."""
        self.assertEqual(calculate_monthly_payment(0, 5.0, 20), 0.0)

    def test_higher_rate_means_higher_payment(self) -> None:
        """فائدة أعلى = قسط أعلى."""
        low = calculate_monthly_payment(100000, 4.0, 20)
        high = calculate_monthly_payment(100000, 6.0, 20)
        self.assertGreater(high, low)

    def test_shorter_term_means_higher_payment(self) -> None:
        """مدة أقصر = قسط أعلى."""
        long = calculate_monthly_payment(100000, 5.0, 25)
        short = calculate_monthly_payment(100000, 5.0, 15)
        self.assertGreater(short, long)


class TotalInterestTests(unittest.TestCase):
    """اختبارات حساب إجمالي الفائدة."""

    def test_positive_interest(self) -> None:
        """إجمالي الفائدة موجب."""
        interest = calculate_total_interest(100000, 660, 20)
        self.assertGreater(interest, 0)

    def test_zero_interest_case(self) -> None:
        """فائدة صفر = لا فائدة إضافية."""
        interest = calculate_total_interest(120000, 1000, 10)
        # المدفوع = 1000 * 120 = 120,000 = القرض
        self.assertAlmostEqual(interest, 0.0, places=0)


class BankComparisonTests(unittest.TestCase):
    """اختبارات مقارنة البنوك."""

    def test_returns_four_banks(self) -> None:
        """النتيجة تتضمن 4 بنوك."""
        result = compare_banks(250000, 30, 20)
        self.assertEqual(len(result["banks"]), 4)

    def test_all_banks_have_monthly_payment(self) -> None:
        """كل بنك له قسط شهري."""
        result = compare_banks(250000, 30, 20)
        for bank in result["banks"]:
            self.assertGreater(bank["monthly_payment"], 0)

    def test_sorted_by_monthly_payment(self) -> None:
        """البنوك مرتبة حسب القسط الشهري (الأقل أولاً)."""
        result = compare_banks(250000, 30, 20)
        payments = [b["monthly_payment"] for b in result["banks"]]
        self.assertEqual(payments, sorted(payments))

    def test_best_bank_is_lowest(self) -> None:
        """أفضل بنك = أقل قسط شهري."""
        result = compare_banks(250000, 30, 20)
        self.assertIsNotNone(result["best_bank"])
        self.assertIn(result["best_bank"], KUWAIT_BANKS)

    def test_boubyan_has_lowest_rate(self) -> None:
        """بوبيان له أقل فائدة."""
        self.assertLess(KUWAIT_BANKS["Boubyan"]["rate"], KUWAIT_BANKS["CBK"]["rate"])

    def test_down_payment_affects_loan(self) -> None:
        """الدفعة المقدمة تؤثر على مبلغ القرض."""
        r30 = compare_banks(250000, 30, 20)
        r50 = compare_banks(250000, 50, 20)
        self.assertGreater(r30["loan_amount"], r50["loan_amount"])

    def test_years_affects_payment(self) -> None:
        """المدة تؤثر على القسط الشهري."""
        r15 = compare_banks(250000, 30, 15)
        r25 = compare_banks(250000, 30, 25)
        # مدة أطول = قسط أقل
        self.assertGreater(r15["banks"][0]["monthly_payment"], r25["banks"][0]["monthly_payment"])

    def test_salary_ratio_calculation(self) -> None:
        """نسبة القسط من الراتب تُحسب عند توفير الراتب."""
        result = compare_banks(250000, 30, 20, salary=2000)
        for bank in result["banks"]:
            self.assertIsNotNone(bank["salary_ratio"])
            self.assertGreater(bank["salary_ratio"], 0)

    def test_affordable_flag(self) -> None:
        """علامة affordable = القسط أقل من 40% من الراتب."""
        result = compare_banks(100000, 50, 20, salary=5000)
        for bank in result["banks"]:
            self.assertTrue(bank["affordable"])  # قسط صغير + راتب كبير

    def test_recommendation_exists(self) -> None:
        """التوصية موجودة."""
        result = compare_banks(250000, 30, 20)
        self.assertIn("recommendation", result)
        self.assertIn("summary", result["recommendation"])

    def test_invalid_price(self) -> None:
        """سعر غير صالح = خطأ."""
        result = compare_banks(0, 30, 20)
        self.assertIn("error", result)

    def test_financing_calculator_fields(self) -> None:
        """الحقول الأساسية موجودة."""
        result = compare_banks(300000, 25, 15)
        self.assertEqual(result["property_value"], 300000)
        self.assertEqual(result["down_payment_pct"], 25)
        self.assertEqual(result["requested_years"], 15)
        self.assertGreater(result["down_payment_amount"], 0)
        self.assertGreater(result["loan_amount"], 0)


class KuwaitBanksDataTests(unittest.TestCase):
    """اختبارات بيانات البنوك."""

    def test_all_banks_have_required_fields(self) -> None:
        """كل بنك له الحقول المطلوبة."""
        required = ["name", "name_en", "rate", "max_years", "max_finance_pct", "features", "url"]
        for code, info in KUWAIT_BANKS.items():
            for field in required:
                self.assertIn(field, info, f"{code} missing {field}")

    def test_rates_are_reasonable(self) -> None:
        """الفوائد معقولة (2% - 8%)."""
        for code, info in KUWAIT_BANKS.items():
            self.assertGreaterEqual(info["rate"], 2.0, f"{code} rate too low")
            self.assertLessEqual(info["rate"], 8.0, f"{code} rate too high")

    def test_max_years_are_reasonable(self) -> None:
        """المدة معقولة (10 - 30 سنة)."""
        for code, info in KUWAIT_BANKS.items():
            self.assertGreaterEqual(info["max_years"], 10)
            self.assertLessEqual(info["max_years"], 30)


if __name__ == "__main__":
    unittest.main()
