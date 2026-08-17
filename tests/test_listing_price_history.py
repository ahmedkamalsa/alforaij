"""اختبارات سجل سعر العقار: تسجيل سعر كل إعلان عند كل ظهور في الحصاد.

التغطية: تصفية الصفوف بلا سعر/بلا كود، طيّ التكرار داخل الدفعة، ختم seen_at،
تجزئة الدفعات (250)، عدم استخدام upsert (سجل تراكمي)، والتسامح مع فشل
الكتابة دون كسر اليومي. بلا شبكة.
"""
from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock

from backend.services import supabase_store


class RecordPriceHistoryTests(unittest.TestCase):
    def _record(self, rows, *, configured: bool = True) -> mock.MagicMock:
        with mock.patch.object(supabase_store, "is_configured", return_value=configured), \
             mock.patch.object(supabase_store, "_post") as post:
            result = supabase_store.record_listing_price_history(rows)
        self._last_result = result
        return post

    def test_empty_rows(self) -> None:
        post = self._record([])
        self.assertEqual(self._last_result["status"], "empty")
        post.assert_not_called()

    def test_not_configured(self) -> None:
        post = self._record([{"code": "MJ-1", "price": 100}], configured=False)
        self.assertEqual(self._last_result["status"], "not_configured")
        post.assert_not_called()

    def test_filters_invalid_rows(self) -> None:
        rows = [
            {"code": "MJ-1", "price": 300000},            # صالح
            {"code": "", "price": 100},                   # بلا كود
            {"code": "MJ-2"},                             # بلا سعر
            {"code": "MJ-3", "price": 0},                 # سعر صفري
            {"code": "MJ-4", "price": "غير معلن"},         # سعر غير رقمي
            {"code": "STATIC", "price": 500},             # كود وهمي
            {"code": "MJ-5", "price": 120},               # صالح
        ]
        post = self._record(rows)
        posted = post.call_args.args[1]
        self.assertEqual([r["code"] for r in posted], ["MJ-1", "MJ-5"])
        self.assertEqual(self._last_result["status"], "saved")
        self.assertEqual(self._last_result["count"], 2)

    def test_stamps_seen_at_and_fields(self) -> None:
        post = self._record([{
            "code": "4S-abc-1",
            "source": "4Sale",
            "area": "السالمية",
            "property_type": "بيت",
            "transaction": "للبيع",
            "price": 250000,
            "price_text": "250,000 د.ك",
        }])
        row = post.call_args.args[1][0]
        datetime.fromisoformat(row["seen_at"])  # ختم ISO زمني صالح
        self.assertEqual(row["code"], "4S-abc-1")
        self.assertEqual(row["price"], 250000)
        self.assertEqual(row["area"], "السالمية")
        self.assertEqual(row["source"], "4Sale")

    def test_dedupes_same_code_within_batch(self) -> None:
        # نفس الإعلان ظهر مرتين في الحصاد نفسه → يُسجَّل مرة واحدة فقط
        post = self._record([
            {"code": "OS-1", "price": 90000},
            {"code": "OS-1", "price": 90000},
            {"code": "OS-2", "price": 60000},
        ])
        posted = post.call_args.args[1]
        self.assertEqual(len(posted), 2)
        self.assertEqual([r["code"] for r in posted], ["OS-1", "OS-2"])

    def test_batches_by_250(self) -> None:
        rows = [{"code": f"OS-{index}", "price": 1000 + index} for index in range(600)]
        post = self._record(rows)
        self.assertEqual(post.call_count, 3)
        sizes = [len(call.args[1]) for call in post.call_args_list]
        self.assertEqual(sizes, [250, 250, 100])

    def test_append_only_no_upsert(self) -> None:
        # سجل تراكمي: لا on_conflict ولا resolution=merge — كل ظهور صف جديد
        post = self._record([{"code": "MJ-9", "price": 200000}])
        kwargs = post.call_args.kwargs
        self.assertFalse(kwargs.get("upsert", False))

    def test_failure_contained(self) -> None:
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_post", side_effect=RuntimeError("HTTP 500")):
            result = supabase_store.record_listing_price_history([{"code": "MJ-10", "price": 1}])
        self.assertEqual(result["status"], "failed")
        self.assertIn("500", result["error"])

    def test_all_invalid_rows_returns_empty(self) -> None:
        post = self._record([{"code": "MJ-11"}, {"price": 0}])
        self.assertEqual(self._last_result["status"], "empty")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
