"""اختبارات خط تنبيه الفرص (المهمة 3): فرق اللقطتين + مطابقة الأبحاث + منع التكرار.

بلا شبكة: لقطتان اصطناعيتان + أبحاث محفوظة اصطناعية، وتغطية الرسالة لكل تغيير.
"""
from __future__ import annotations

import unittest

from backend.services.opportunity_alerts import (
    build_alert_message,
    build_alert_rows,
    filter_unsent_alerts,
    find_changes,
    match_searches_to_change,
)


def _item(code: str, area: str = "السالمية", price: float = 280000, transaction: str = "للبيع") -> dict:
    return {
        "code": code,
        "area": area,
        "governorate": "محافظة حولي",
        "transaction": transaction,
        "propertyType": "بيت",
        "price": price,
        "priceText": f"{price:,.0f} د.ك",
        "valuationLabel": "لقطة ممتازة",
        "url": f"https://example.com/{code}",
    }


def _snapshot(items: list[dict]) -> dict:
    return {"generatedAt": "2026-08-16T03:00:00", "tiers": {"daily": {"items": items}}}


def _search(secret: str = "s1", area: str = "السالمية", enabled: bool = True) -> dict:
    return {
        "id": 1,
        "user_secret": secret,
        "name": "بيت في السالمية",
        "request_text": "بيت 400م في السالمية",
        "transaction_type": "مطلوب للشراء",
        "property_type": "بيت",
        "areas": [area],
        "governorates": [],
        "price_min": 200000,
        "price_max": 350000,
        "alert_enabled": enabled,
    }


class FindChangesTests(unittest.TestCase):
    def test_new_and_price_drop_detected(self) -> None:
        previous = _snapshot([_item("OLD-1"), _item("DROP-1", price=300000)])
        current = _snapshot([_item("OLD-1"), _item("DROP-1", price=270000), _item("NEW-1")])
        changes = find_changes(previous, current)
        by_code = {c["opportunity_code"]: c for c in changes}
        self.assertIn("NEW-1", by_code)
        self.assertEqual(by_code["NEW-1"]["change"], "new")
        self.assertEqual(by_code["DROP-1"]["change"], "price_drop")
        self.assertEqual(by_code["DROP-1"]["oldPriceText"], "300,000 د.ك")
        self.assertNotIn("OLD-1", by_code)  # لم يتغير

    def test_no_previous_means_all_new(self) -> None:
        changes = find_changes(None, _snapshot([_item("A"), _item("B")]))
        self.assertEqual(len(changes), 2)
        self.assertTrue(all(c["change"] == "new" for c in changes))


class MatchingTests(unittest.TestCase):
    def test_matching_search_found(self) -> None:
        change = find_changes(_snapshot([_item("X")]), _snapshot([_item("X"), _item("N1")]))[0]
        matches = match_searches_to_change([_search()], change)
        self.assertEqual(len(matches), 1)
        self.assertGreaterEqual(matches[0]["score"], 40)

    def test_disabled_alert_excluded(self) -> None:
        change = find_changes(_snapshot([]), _snapshot([_item("N1")]))[0]
        matches = match_searches_to_change([_search(enabled=False)], change)
        self.assertEqual(matches, [])

    def test_non_matching_area_excluded(self) -> None:
        change = find_changes(_snapshot([]), _snapshot([_item("N1", area="الفروانية")]))[0]
        matches = match_searches_to_change([_search()], change)
        self.assertEqual(matches, [])

    def test_transaction_conflict_excluded(self) -> None:
        change = find_changes(_snapshot([]), _snapshot([_item("N1", transaction="للإيجار")]))[0]
        matches = match_searches_to_change([_search()], change)
        self.assertEqual(matches, [])


class MessageTests(unittest.TestCase):
    def test_new_message_mentions_search(self) -> None:
        change = find_changes(_snapshot([]), _snapshot([_item("N1")]))[0]
        message = build_alert_message(change, _search())
        self.assertIn("فرصة جديدة", message)
        self.assertIn("بيت في السالمية", message)
        self.assertIn("280,000 د.ك", message)

    def test_price_drop_message(self) -> None:
        previous = _snapshot([_item("D1", price=300000)])
        current = _snapshot([_item("D1", price=270000)])
        change = find_changes(previous, current)[0]
        message = build_alert_message(change, _search())
        self.assertIn("انخفض سعر", message)
        self.assertIn("كان 300,000 د.ك", message)


class DedupTests(unittest.TestCase):
    def test_no_duplicate_within_batch(self) -> None:
        previous = _snapshot([_item("X")])
        current = _snapshot([_item("X"), _item("N1")])
        rows = build_alert_rows(previous, current, [_search(), _search(secret="s1")])
        keys = [(r["user_secret"], r["opportunity_code"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_double_run_filters_existing(self) -> None:
        previous = _snapshot([_item("X")])
        current = _snapshot([_item("X"), _item("N1")])
        first = build_alert_rows(previous, current, [_search()])
        existing = [(r["user_secret"], r["opportunity_code"]) for r in first]
        second = filter_unsent_alerts(build_alert_rows(previous, current, [_search()]), existing)
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
