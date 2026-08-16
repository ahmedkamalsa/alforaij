"""اختبارات البحث المحفوظ (المهمة 2): دالة المطابقة النقية بحث ↔ فرصة.

تغطي: المنطقة 40 + المحافظة 30 + النوع 30 + الميزانية 30، بوابة العملية،
والبحث الفارغ. بلا شبكة (قابل للتشغيل في CI).
"""
from __future__ import annotations

import unittest

from backend.services.search_matching import MATCH_THRESHOLD, match_search_to_item


def _item(**overrides) -> dict:
    base = {
        "area": "السالمية",
        "governorate": "محافظة حولي",
        "propertyType": "بيت",
        "transaction": "للبيع",
        "price": 280000,
    }
    base.update(overrides)
    return base


def _search(**overrides) -> dict:
    base = {
        "transaction_type": "مطلوب للشراء",
        "property_type": "بيت",
        "areas": ["السالمية"],
        "governorates": [],
        "price_min": 200000,
        "price_max": 350000,
    }
    base.update(overrides)
    return base


class MatchSearchTests(unittest.TestCase):
    def test_exact_match_scores_100(self) -> None:
        score = match_search_to_item(_search(), _item())
        self.assertEqual(score, 100.0)

    def test_area_mismatch_within_budget_loses_area_points(self) -> None:
        score = match_search_to_item(_search(), _item(area="حولي"))
        self.assertEqual(score, 60.0)  # نوع 30 + ميزانية 30

    def test_governorate_only_match_gives_30(self) -> None:
        search = _search(areas=[], governorates=["محافظة حولي"])
        score = match_search_to_item(search, _item())
        self.assertEqual(score, 90.0)  # محافظة 30 + نوع 30 + ميزانية 30

    def test_type_mismatch_loses_type_points(self) -> None:
        score = match_search_to_item(_search(), _item(propertyType="شقة"))
        self.assertEqual(score, 70.0)  # منطقة 40 + ميزانية 30

    def test_price_above_max_gets_partial(self) -> None:
        score = match_search_to_item(_search(), _item(price=450000))
        self.assertEqual(score, 85.0)  # منطقة 40 + نوع 30 + 15 قرب الميزانية

    def test_price_far_above_max_loses_budget(self) -> None:
        score = match_search_to_item(_search(), _item(price=900000))
        self.assertEqual(score, 70.0)  # منطقة 40 + نوع 30

    def test_transaction_conflict_excluded(self) -> None:
        score = match_search_to_item(_search(), _item(transaction="للإيجار"))
        self.assertEqual(score, 0.0)

    def test_empty_search_matches_nothing(self) -> None:
        score = match_search_to_item({}, _item())
        self.assertEqual(score, 0.0)

    def test_threshold_used_by_alerts(self) -> None:
        strong = match_search_to_item(_search(), _item())
        weak = match_search_to_item(_search(), _item(area="حولي", price=900000))
        self.assertGreaterEqual(strong, MATCH_THRESHOLD)
        self.assertLess(weak, MATCH_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
