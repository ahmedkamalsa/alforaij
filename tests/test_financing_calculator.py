from __future__ import annotations

import unittest

from backend.services.financing_calculator import calculate_mortgage


def _amortization(loan: float, annual_rate: float, years: int) -> float:
    """صيغة القسط الثابت المستقلة — مرجع مستقل عن التنفيذ لتأكيد القيم."""
    monthly_interest = annual_rate / 12
    months = years * 12
    if monthly_interest > 0:
        return loan * (monthly_interest * (1 + monthly_interest) ** months) / ((1 + monthly_interest) ** months - 1)
    return loan / months


class KnownAmortizationScenarios(unittest.TestCase):
    """قيم مرجعية محسوبة بصيغة مستقلة (كل سيناريو يوثّق عقد المخرجات الحرفي)."""

    def test_default_parameters(self) -> None:
        result = calculate_mortgage(100_000)
        self.assertEqual(result["property_value"], 100_000)
        self.assertAlmostEqual(result["down_payment"], 30_000.0)
        self.assertAlmostEqual(result["loan_amount"], 70_000.0)
        self.assertAlmostEqual(result["monthly_payment"], 535.50, places=2)
        self.assertAlmostEqual(result["total_interest"], 26_389.15, places=2)
        self.assertEqual(result["interest_rate"], 0.045)
        self.assertEqual(result["years"], 15)

    def test_high_value_long_term(self) -> None:
        result = calculate_mortgage(250_000, down_payment_percent=0.40, interest_rate=0.05, years=20)
        self.assertAlmostEqual(result["down_payment"], 100_000.0)
        self.assertAlmostEqual(result["loan_amount"], 150_000.0)
        self.assertAlmostEqual(result["monthly_payment"], 989.93, places=2)
        self.assertAlmostEqual(result["total_interest"], 87_584.07, places=2)

    def test_small_loan_short_term(self) -> None:
        result = calculate_mortgage(45_000, down_payment_percent=0.25, interest_rate=0.035, years=10)
        self.assertAlmostEqual(result["down_payment"], 11_250.0)
        self.assertAlmostEqual(result["loan_amount"], 33_750.0)
        self.assertAlmostEqual(result["monthly_payment"], 333.74, places=2)
        self.assertAlmostEqual(result["total_interest"], 6_298.78, places=2)


class AmortizationFormulaEquivalence(unittest.TestCase):
    """كل قسط شهري يجب أن يطابق الصيغة المستقلة بدقة تصل إلى نصف فلس."""

    def test_monthly_payment_matches_independent_formula(self) -> None:
        for value, down_pct, rate, years in [
            (100_000, 0.30, 0.045, 15),
            (250_000, 0.40, 0.05, 20),
            (45_000, 0.25, 0.035, 10),
            (1_000_000, 0.50, 0.06, 30),
            (123_456.78, 0.35, 0.0475, 12),
            (5_000, 0.20, 0.03, 5),
        ]:
            with self.subTest(value=value, rate=rate, years=years):
                result = calculate_mortgage(value, down_payment_percent=down_pct, interest_rate=rate, years=years)
                loan = result["loan_amount"]
                expected = round(_amortization(loan, rate, years), 2)
                self.assertAlmostEqual(result["monthly_payment"], expected, delta=0.005)


class ConsistencyInvariants(unittest.TestCase):
    """دعائم داخلية يجب أن تصمد في كل السيناريوهات: الدفعة + القرض = القيمة، والفائدة = الكل - القرض."""

    def test_money_conservation_invariants(self) -> None:
        for value, down_pct, rate, years in [
            (100_000, 0.30, 0.045, 15),
            (250_000, 0.40, 0.05, 20),
            (60_000, 0.30, 0.0, 15),
            (45_000, 0.25, 0.035, 10),
            (1_000_000, 0.50, 0.06, 30),
            (123_456.78, 0.35, 0.0475, 12),
        ]:
            with self.subTest(value=value, down_pct=down_pct):
                result = calculate_mortgage(value, down_payment_percent=down_pct, interest_rate=rate, years=years)
                self.assertAlmostEqual(result["down_payment"], value * down_pct, places=2)
                self.assertAlmostEqual(result["loan_amount"], value - value * down_pct, places=2)
                self.assertEqual(result["property_value"], value)
                self.assertEqual(result["years"], years)
                self.assertEqual(result["interest_rate"], rate)
                # الفائدة المبلغ عنها = إجمالي الدفعات (بالقسط الدقيق) − القرض
                exact_total = _amortization(result["loan_amount"], rate, years) * years * 12
                self.assertAlmostEqual(result["total_interest"], exact_total - result["loan_amount"], delta=0.005)
                # كل مبلغ معروض مقرّب لفلسين
                self.assertEqual(round(result["monthly_payment"], 2), result["monthly_payment"])
                self.assertEqual(round(result["total_interest"], 2), result["total_interest"])


class ZeroInterestLoan(unittest.TestCase):
    """قرض بفائدة صفرية: القسط = القرض ÷ الأشهر، ولا فائدة إجمالية."""

    def test_zero_rate_has_no_interest(self) -> None:
        result = calculate_mortgage(60_000, down_payment_percent=0.30, interest_rate=0.0, years=15)
        self.assertAlmostEqual(result["monthly_payment"], 42_000 / 180, places=2)
        self.assertEqual(result["total_interest"], 0.0)
        # الإجمالي يُحسب من القسط الدقيق (غير المقرّب) — فيطابق القرض تمامًا
        exact_total = _amortization(result["loan_amount"], 0.0, 15) * 180
        self.assertAlmostEqual(exact_total, result["loan_amount"])

    def test_zero_rate_high_value(self) -> None:
        result = calculate_mortgage(500_000, down_payment_percent=0.40, interest_rate=0.0, years=10)
        self.assertAlmostEqual(result["loan_amount"], 300_000.0)
        self.assertAlmostEqual(result["monthly_payment"], 300_000 / 120, places=2)
        self.assertEqual(result["total_interest"], 0.0)


class InvalidInputs(unittest.TestCase):
    """قيم غير صالحة تُرجع قاموسًا فارغًا بدل الانفجار أو أرقام سلبية."""

    def test_non_positive_values_return_empty(self) -> None:
        for bad in (0, -1, -0.5, None):
            with self.subTest(bad=bad):
                self.assertEqual(calculate_mortgage(bad), {})


if __name__ == "__main__":
    unittest.main()
