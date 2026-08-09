from __future__ import annotations

import unittest
from unittest import mock

from backend.models import Listing
from backend.services.supabase_store import listing_row, persist_analysis
from backend.services.request_parser import parse_request


class SupabaseStoreTests(unittest.TestCase):
    def test_listing_row_maps_model_to_supabase_columns(self) -> None:
        listing = Listing(
            code="AF-1",
            transaction="للبيع",
            governorate="محافظة الجهراء",
            area="المطلاع",
            property_type="بيت",
            detail_class="بيت",
            price=350000,
            price_text="350 ألف د.ك",
            space=400,
            listing_mode="مباشر",
            summary="بيت للبيع",
            features="شارع واحد",
            published_date="2026-08-03",
            original_url="https://example.test/1",
            source="الفريج",
            raw={"x": 1},
        )

        row = listing_row(listing)

        self.assertEqual(row["transaction_type"], "للبيع")
        self.assertEqual(row["property_type"], "بيت")
        self.assertEqual(row["raw"], {"x": 1})

    def test_persist_analysis_is_noop_when_supabase_not_configured(self) -> None:
        request = parse_request("شقة للبيع في بنيد القار")

        # محاكاة بيئة غير مضبوطة بغض النظر عن ملف .env الحالي
        with mock.patch("backend.services.supabase_store.SUPABASE_URL", ""), mock.patch(
            "backend.services.supabase_store.SUPABASE_SERVICE_ROLE_KEY", ""
        ):
            result = persist_analysis(request, {"results": []}, [])

        self.assertEqual(result["status"], "not_configured")

    def test_persist_analysis_tolerates_missing_search_history_table(self) -> None:
        request = parse_request("\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a \u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631")
        report = {
            "summary": "\u062a\u0642\u0631\u064a\u0631 \u062a\u062c\u0631\u064a\u0628\u064a",
            "results": [
                {
                    "code": "AF-1",
                    "source": "\u0627\u0644\u0641\u0631\u064a\u062c",
                    "area": "\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631",
                    "price": 145000,
                    "recommendationScore": 80,
                    "dataQuality": {"score": 90, "label": "\u0642\u0648\u064a\u0629"},
                    "numberSources": {},
                }
            ],
        }
        statuses = [{"name": "\u0627\u0644\u0641\u0631\u064a\u062c", "status": "success", "records": 1}]

        def fake_post(table, rows, **kwargs):
            if table == "search_history":
                raise RuntimeError("HTTP 404 relation does not exist")

        with mock.patch("backend.services.supabase_store.SUPABASE_URL", "https://example.supabase.co"), mock.patch(
            "backend.services.supabase_store.SUPABASE_SERVICE_ROLE_KEY", "service-key"
        ), mock.patch("backend.services.supabase_store._post", side_effect=fake_post) as post:
            result = persist_analysis(request, report, statuses)

        self.assertEqual(result["status"], "saved")
        self.assertIn("search_history", [call.args[0] for call in post.call_args_list])


if __name__ == "__main__":
    unittest.main()
