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
