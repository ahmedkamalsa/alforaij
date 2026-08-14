from __future__ import annotations

import unittest

from backend.models import Listing, RankedListing
from backend.services.deduplication import deduplicate_ranked


def _listing(**overrides) -> Listing:
    base = {
        "code": "AF-T",
        "transaction": "للبيع",
        "governorate": "الفروانية",
        "area": "الرابية",
        "property_type": "بيت",
        "detail_class": "بيت",
        "price": 300000.0,
        "price_text": "300,000 د.ك",
        "space": 400.0,
        "listing_mode": "مباشر",
        "summary": "بيت جديد في الرابية قريب من المسجد والجمعية",
        "features": "",
        "published_date": "2026-08-01",
        "original_url": "https://front.alforaij.com/Listing/Detail/T",
    }
    base.update(overrides)
    return Listing(**base)


def _ranked(code: str = "AF-1", **listing_overrides) -> RankedListing:
    return RankedListing(
        listing=_listing(code=code, **listing_overrides),
        match_score=0.9,
        valuation_label="سعر عادل",
        valuation_reason="مقارنة سوقية",
        confidence=0.74,
        deal_score=0.5,
        recommendation_score=0.7,
        market_median=310000.0,
        price_ratio=0.97,
        match_breakdown=[],
        recommendation_breakdown=[],
        number_sources={},
        reasons=[],
        warnings=[],
        comparables=[],
    )


class DeduplicateRanked(unittest.TestCase):
    def test_empty_input_returns_empty_list(self) -> None:
        self.assertEqual(deduplicate_ranked([]), [])

    def test_exact_duplicates_collapse_to_one(self) -> None:
        a = _ranked("AF-1")
        b = _ranked("AF-2")
        c = _ranked("AF-3")
        result = deduplicate_ranked([a, b, c])
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], a, "يُحتفظ بأول ظهور فقط")

    def test_keeps_first_occurrence_and_preserves_order(self) -> None:
        a = _ranked("AF-1")
        b = _ranked("AF-2", price=310000.0)
        c = _ranked("AF-3")  # تكرار للعنصر a
        result = deduplicate_ranked([a, b, c])
        self.assertEqual([r.listing.code for r in result], ["AF-1", "AF-2"])
        self.assertIs(result[0], a)

    def test_summary_tail_beyond_first_twelve_words_is_ignored(self) -> None:
        # 14 كلمة — أول 12 متطابقة، والاختلاف يقع في الكلمتين 13 و14 فقط
        a = _ranked("AF-1", summary="بيت جديد في الرابية قريب من المسجد والجمعية والشوارع المؤدية إلى السوق القديم العريق")
        b = _ranked("AF-2", summary="بيت جديد في الرابية قريب من المسجد والجمعية والشوارع المؤدية إلى السوق الحديث العصري")
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 1)

    def test_summary_difference_at_twelfth_word_is_kept(self) -> None:
        # الاختلاف داخل نافذة الـ 12 كلمة الأولى — يجب بقاؤهما
        a = _ranked("AF-1", summary="بيت جديد في الرابية قريب من المسجد والجمعية والشوارع المؤدية إلى السوق القديم العريق")
        b = _ranked("AF-2", summary="بيت جديد في الرابية قريب من المسجد والجمعية والشوارع المؤدية إلى الحديقة الحديثة العصري")
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 2)

    def test_summary_difference_within_first_words_is_kept(self) -> None:
        a = _ranked("AF-1", summary="بيت جديد في الرابية قريب من المسجد")
        b = _ranked("AF-2", summary="بيت قديم في الرابية قريب من المسجد")
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 2)

    def test_summary_whitespace_is_normalized(self) -> None:
        a = _ranked("AF-1", summary="بيت   جديد   في الرابية")
        b = _ranked("AF-2", summary="بيت جديد في الرابية")
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 1)

    def test_missing_or_empty_summary_collapse(self) -> None:
        a = _ranked("AF-1", summary=None)
        b = _ranked("AF-2", summary="")
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 1)

    def test_different_price_is_kept(self) -> None:
        a = _ranked("AF-1", price=300000.0)
        b = _ranked("AF-2", price=300001.0)
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 2)

    def test_different_area_or_transaction_is_kept(self) -> None:
        a = _ranked("AF-1", area="الرابية")
        b = _ranked("AF-2", area="الفردوس")
        c = _ranked("AF-3", transaction="إيجار")
        result = deduplicate_ranked([a, b, c])
        self.assertEqual(len(result), 3)

    def test_space_none_empty_and_zero_collapse_to_same_key(self) -> None:
        """السلوك الفعلي: None و 0.0 و '' كلها تتحول إلى '' في المفتاح — تُعامل كتكرار واحد."""
        a = _ranked("AF-1", space=None)
        b = _ranked("AF-2", space=0.0)
        c = _ranked("AF-3", space="")
        result = deduplicate_ranked([a, b, c])
        self.assertEqual(len(result), 1)

    def test_real_space_value_differs_from_missing(self) -> None:
        a = _ranked("AF-1", space=None)
        b = _ranked("AF-2", space=400.0)
        result = deduplicate_ranked([a, b])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
