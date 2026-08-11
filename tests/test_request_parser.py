from __future__ import annotations

import unittest

from backend.services.request_parser import parse_request


class RequestParserTests(unittest.TestCase):
    def test_area_and_setback_are_separate(self) -> None:
        request = parse_request("\u0645\u0633\u0627\u062d\u0629 400 \u0645\u062a\u0631 \u0648\u0627\u0631\u062a\u062f\u0627\u062f 40 \u0645\u062a\u0631")

        self.assertEqual(request.min_area, 400)
        self.assertEqual(request.max_area, 400)
        self.assertEqual(request.excluded_area_numbers.get("\u0627\u0631\u062a\u062f\u0627\u062f"), 40)

    def test_frontage_and_street_width_are_not_property_area(self) -> None:
        request = parse_request("\u0648\u0627\u062c\u0647\u0629 25 \u0645\u062a\u0631 \u0648\u0634\u0627\u0631\u0639 \u0639\u0631\u0636 30 \u0645\u062a\u0631")

        self.assertIsNone(request.min_area)
        self.assertIsNone(request.max_area)
        self.assertEqual(request.excluded_area_numbers.get("\u0648\u0627\u062c\u0647\u0647"), 25)
        self.assertEqual(request.excluded_area_numbers.get("\u0634\u0627\u0631\u0639 \u0639\u0631\u0636"), 30)

    def test_income_area_and_sale_price_are_distinct(self) -> None:
        request = parse_request(
            "\u0639\u0645\u0627\u0631\u0629 \u062f\u062e\u0644\u0647\u0627 9000 "
            "\u0648\u0645\u0633\u0627\u062d\u062a\u0647\u0627 750 \u0645\u062a\u0631 "
            "\u0648\u0633\u0639\u0631\u0647\u0627 \u0645\u0644\u064a\u0648\u0646 \u0648200"
        )

        self.assertEqual(request.property_type, "\u0639\u0645\u0627\u0631\u0629")
        self.assertEqual(request.income, 9000)
        self.assertEqual(request.min_area, 750)
        self.assertEqual(request.budget, 1_200_000)

    def test_bnaid_al_qar_request_is_understood(self) -> None:
        request = parse_request(
            "\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a "
            "\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"
        )

        self.assertEqual(request.transaction, "\u0644\u0644\u0628\u064a\u0639")
        self.assertEqual(request.property_type, "\u0634\u0642\u0629")
        self.assertEqual(request.areas, ["\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"])


    def test_square_al_khair_mall_detects_sabah_al_ahmad(self) -> None:
        request = parse_request(
            "شاليه للبيع قريب من "
            "مول سكوير الخير"
        )

        self.assertEqual(request.transaction, "للبيع")
        self.assertIn("صباح الأحمد", request.areas)


if __name__ == "__main__":
    unittest.main()


class RentalIncomeExtractionTests(unittest.TestCase):
    """استخراج الدخل الإيجاري من نص الإعلان وصيغه المختلفة."""

    def _extract(self, text: str):
        from backend.services.request_parser import extract_rental_income
        return extract_rental_income(text)

    def test_mojar_monthly(self) -> None:
        amount, period = self._extract("مؤجر ب 1200 شهرياً")
        self.assertEqual(amount, 1200)
        self.assertEqual(period, "monthly")

    def test_mojar_without_b_and_period_defaults_monthly(self) -> None:
        amount, period = self._extract("شاليه مؤجره 1200")
        self.assertEqual(amount, 1200)
        self.assertEqual(period, "monthly")

    def test_mojar_bashahr(self) -> None:
        amount, period = self._extract("مؤجرة بـ 350 بالشهر")
        self.assertEqual(amount, 350)
        self.assertEqual(period, "monthly")

    def test_dakhlaha_annual(self) -> None:
        amount, period = self._extract("عمارة دخلها 9000")
        self.assertEqual(amount, 9000)
        self.assertEqual(period, "annual")

    def test_dakhla_thousands_word(self) -> None:
        amount, period = self._extract("بيت دخله 20 الف")
        self.assertEqual(amount, 20000)
        self.assertEqual(period, "annual")

    def test_dakhla_short_number_scaled(self) -> None:
        amount, period = self._extract("عمارة دخله 25")
        self.assertEqual(amount, 25000)
        self.assertEqual(period, "annual")

    def test_ejara_monthly(self) -> None:
        amount, period = self._extract("شقة ايجارها 400 شهرياً")
        self.assertEqual(amount, 400)
        self.assertEqual(period, "monthly")

    def test_qeemt_ejara(self) -> None:
        amount, period = self._extract("قيمه ايجارها 30 الف سنوياً")
        self.assertEqual(amount, 30000)
        self.assertEqual(period, "annual")

    def test_arabic_digits_normalized(self) -> None:
        amount, period = self._extract("مؤجر ب ١٢٠٠ شهرياً")
        self.assertEqual(amount, 1200)
        self.assertEqual(period, "monthly")

    def test_no_income(self) -> None:
        amount, period = self._extract("بيت للبيع في بيان قطعه 12")
        self.assertIsNone(amount)
        self.assertEqual(period, "")

    def test_user_ad_full_text(self) -> None:
        # نص إعلان المستخدم الأصلي: مؤجر ب 1200 شهرياً على مراجعة 260 ألف
        amount, period = self._extract(
            "للبيع شاليه صف ثاني المساحه 454 م بطن وظهر ارتداد فوق 100 متر "
            "في المرحلة الثالثه قريب من مول سكوير الخير مكون دورين ونصف ومسبح "
            "سبع غرف ماستر وصالتين وداونيه وغرفه عامله ماستر وغرفه حارس ماستر "
            "مؤثث بالكامل ومطبخ مجهز بالكامل مؤجر ب 1200 شهرياً مراجعة 260 الف "
            "بدون اخلاء وثيقه حره"
        )
        self.assertEqual(amount, 1200)
        self.assertEqual(period, "monthly")

    def test_parse_request_carries_income_and_period(self) -> None:
        request = parse_request("شاليه للبيع مؤجر ب 1200 شهرياً مراجعة 260 الف")
        self.assertEqual(request.income, 1200)
        self.assertEqual(request.income_period, "monthly")
        self.assertEqual(request.budget, 260000)


if __name__ == "__main__":
    unittest.main()
