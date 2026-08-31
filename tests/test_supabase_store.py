from __future__ import annotations

import unittest
from unittest import mock

from backend.models import Listing
from backend.services.supabase_store import (
    listing_row,
    persist_analysis,
    save_ai_provider_runs,
    save_analysis_agent_trace,
    save_search_history,
)
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

    def test_search_history_uses_default_top_data_quality_without_results(self) -> None:
        request = parse_request("بيت 400م في السالمية بحدود 250000 دينار")
        captured = {}

        def fake_post(table, rows, **kwargs):
            captured["table"] = table
            captured["rows"] = rows

        with mock.patch("backend.services.supabase_store._post", side_effect=fake_post):
            save_search_history(request, {"summary": "لا توجد نتائج", "results": []}, [])

        self.assertEqual(captured["table"], "search_history")
        self.assertEqual(captured["rows"][0]["top_data_quality"], "لا توجد نتيجة عليا")

    def test_ai_provider_runs_shape(self) -> None:
        request = parse_request("بيت للبيع في السالمية")
        calls = []

        def fake_post(table, rows, **kwargs):
            calls.append((table, rows))

        attempts = [{"provider": "nvidia_nim", "model": "minimaxai/minimax-m3", "status": "success", "responseMs": 321}]
        with mock.patch("backend.services.supabase_store._post", side_effect=fake_post):
            save_ai_provider_runs(request, attempts)

        self.assertEqual(calls[0][0], "ai_provider_runs")
        self.assertEqual(calls[0][1][0]["provider"], "nvidia_nim")
        self.assertEqual(calls[0][1][0]["metadata"]["model"], "minimaxai/minimax-m3")

    def test_analysis_agent_trace_shape(self) -> None:
        request = parse_request("بيت للبيع في السالمية")
        calls = []

        def fake_post(table, rows, **kwargs):
            calls.append((table, rows))

        trace = {
            "agents": [
                {
                    "id": "intent_agent",
                    "name": "وكيل فهم الطلب",
                    "status": "done",
                    "summary": "فهم الطلب",
                    "outputs": {"area": "السالمية", "budget": 250000},
                }
            ]
        }
        with mock.patch("backend.services.supabase_store._post", side_effect=fake_post):
            save_analysis_agent_trace(request, trace)

        self.assertEqual(calls[0][0], "analysis_agent_runs")
        self.assertEqual(calls[1][0], "analysis_agent_steps")
        self.assertEqual(calls[0][1][0]["agent_id"], "intent_agent")
        self.assertEqual(calls[1][1][0]["step_key"], "area")


if __name__ == "__main__":
    unittest.main()
