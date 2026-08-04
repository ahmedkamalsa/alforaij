from __future__ import annotations

import unittest

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

        result = persist_analysis(request, {"results": []}, [])

        self.assertEqual(result["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
