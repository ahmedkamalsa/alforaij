from __future__ import annotations

import unittest

from backend.models import Listing
from backend.services.opportunities import (
    _demand_match_score,
    _listing_kind,
    build_market_matching,
    build_opportunity_delta,
)


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
        "summary": "",
        "features": "",
        "published_date": "2026-08-01",
        "original_url": "https://front.alforaij.com/Listing/Detail/T",
    }
    base.update(overrides)
    return Listing(**base)


def _sale_item(code: str = "AF-T", area: str = "الرابية", price: float = 300000.0) -> dict:
    return {
        "code": code,
        "source": "الفريج",
        "listingType": "مباشر",
        "governorate": "الفروانية",
        "area": area,
        "propertyType": "بيت",
        "transaction": "للبيع",
        "rental": False,
        "price": price,
        "priceText": f"{price:,.0f} د.ك",
        "score": 90,
        "valuationLabel": "سعر عادل",
        "valuationReason": "مقارنة سوقية",
        "marketMedian": 310000,
        "evidence": [{"code": "AF-1", "source": "الفريج", "price": 290000}],
        "clients": [],
        "url": "https://front.alforaij.com/Listing/Detail/T",
    }


def _rent_item(code: str = "AF-R", area: str = "الرابية", price: float = 400.0) -> dict:
    return {
        "code": code,
        "source": "الفريج",
        "listingType": "غير محدد",
        "governorate": "الفروانية",
        "area": area,
        "propertyType": "بيت",
        "transaction": "للإيجار",
        "rental": True,
        "price": price,
        "priceText": f"{price:,.0f} د.ك/شهر",
        "score": 85,
        "valuationLabel": "إيجار عادل",
        "valuationReason": "مقارنة إيجارية",
        "marketMedian": 420,
        "evidence": [],
        "clients": [],
        "url": "https://front.alforaij.com/Listing/Detail/R",
    }


class TestListingKind(unittest.TestCase):
    def test_direct_office_unknown(self) -> None:
        self.assertEqual(_listing_kind(_listing(listing_mode="مباشر")), "مباشر")
        self.assertEqual(_listing_kind(_listing(listing_mode="مكتب")), "مكتب")
        self.assertEqual(_listing_kind(_listing(listing_mode="مكتب (عرض إيجار)")), "مكتب")
        self.assertEqual(_listing_kind(_listing(listing_mode="مباشر (طلب شراء)")), "مباشر")
        self.assertEqual(_listing_kind(_listing(listing_mode="غير محدد")), "غير محدد")
        self.assertEqual(_listing_kind(_listing(listing_mode="")), "غير محدد")


class TestDemandMatchScore(unittest.TestCase):
    def test_full_match(self) -> None:
        demand = {"area": "الرابية", "governorate": "الفروانية", "propertyType": "بيت", "budget": 300000}
        score, reasons = _demand_match_score(demand, _sale_item())
        self.assertEqual(score, 100.0)
        self.assertIn("نفس المنطقة", reasons)
        self.assertIn("نفس نوع العقار", reasons)
        self.assertIn("السعر ضمن الميزانية", reasons)

    def test_partial_match_governorate(self) -> None:
        demand = {"area": "العارضية", "governorate": "الفروانية", "propertyType": "بيت", "budget": 300000}
        score, _reasons = _demand_match_score(demand, _sale_item())
        self.assertGreaterEqual(score, 40)
        self.assertLess(score, 100)

    def test_mismatch_below_threshold(self) -> None:
        demand = {"area": "حولي", "governorate": "حولي", "propertyType": "عمارة", "budget": 50000}
        score, _reasons = _demand_match_score(demand, _sale_item())
        self.assertLess(score, 40)


class TestBuildMarketMatching(unittest.TestCase):
    def test_matches_demand_to_supply(self) -> None:
        snapshot = {
            "tiers": {
                "daily": {"items": [_sale_item(), _rent_item()]},
                "weekly": {"items": [_sale_item()]},
            }
        }
        demand = [
            {"code": "AF-8", "transaction": "مطلوب للشراء", "kind": "buy", "area": "الرابية",
             "governorate": "الفروانية", "propertyType": "بيت", "budget": 300000, "budgetText": "300,000 د.ك",
             "summary": "مطلوب بيت", "url": "", "source": "الفريج", "listingType": "مباشر"},
            {"code": "AF-9", "transaction": "مطلوب للإيجار", "kind": "rent", "area": "الرابية",
             "governorate": "الفروانية", "propertyType": "بيت", "budget": 400, "budgetText": "400 د.ك",
             "summary": "مطلوب إيجار", "url": "", "source": "الفريج", "listingType": "غير محدد"},
        ]
        result = build_market_matching(snapshot, demand_requests=demand)
        self.assertEqual(result["demandCount"], 2)
        self.assertEqual(result["matchedDemandCount"], 2)
        self.assertEqual(result["byKind"], {"buy": 1, "rent": 1, "sell": 0})
        buy = next(r for r in result["requests"] if r["kind"] == "buy")
        self.assertGreaterEqual(buy["matchCount"], 1)
        self.assertEqual(buy["matches"][0]["code"], "AF-T")
        # فرصة البيع لا تُطابق طلب الإيجار والعكس
        rent = next(r for r in result["requests"] if r["kind"] == "rent")
        for match in rent["matches"]:
            self.assertTrue(match.get("rental"))
        # الفرص الأكثر طلبًا تشمل عرض البيع
        self.assertTrue(any(h["code"] == "AF-T" for h in result["hotOffers"]))
        self.assertGreaterEqual(next(h for h in result["hotOffers"] if h["code"] == "AF-T")["demandCount"], 1)

    def test_empty_snapshot_falls_back(self) -> None:
        result = build_market_matching({}, demand_requests=[])
        self.assertEqual(result["demandCount"], 0)
        self.assertEqual(result["hotOffers"], [])


class TestBuildOpportunityDelta(unittest.TestCase):
    def test_new_removed_price_drop(self) -> None:
        previous = {"tiers": {"daily": {"items": [
            _sale_item(code="A", price=300000),
            _sale_item(code="B", price=400000),
            _sale_item(code="C", price=200000),
        ]}}}
        current = {"tiers": {"daily": {"items": [
            _sale_item(code="A", price=300000),
            _sale_item(code="B", price=350000),  # انخفاض
            _sale_item(code="D", price=500000),  # جديد
        ]}}}
        result = build_opportunity_delta(previous, current)
        self.assertTrue(result["hasPrevious"])
        self.assertEqual(result["counts"], {"added": 1, "removed": 1, "priceDrops": 1})
        self.assertEqual(result["added"][0]["code"], "D")
        self.assertEqual(result["added"][0]["change"], "new")
        self.assertIn("راسل العملاء", result["added"][0]["guidance"])
        self.assertEqual(result["removed"][0]["code"], "C")
        self.assertEqual(result["removed"][0]["change"], "removed")
        self.assertIn("أزله من العروض", result["removed"][0]["guidance"])
        drop = result["priceDrops"][0]
        self.assertEqual(drop["code"], "B")
        self.assertEqual(drop["oldPrice"], 400000)
        self.assertEqual(drop["price"], 350000)
        self.assertIn("انخفض السعر", drop["guidance"])

    def test_no_previous_means_everything_new(self) -> None:
        current = {"tiers": {"daily": {"items": [_sale_item(code="A")]}}}
        result = build_opportunity_delta(None, current)
        self.assertFalse(result["hasPrevious"])
        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["counts"]["removed"], 0)


if __name__ == "__main__":
    unittest.main()
