from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from backend.models import Listing, PropertyRequest, RankedListing


@dataclass
class ValuationResult:
    label: str
    reason: str
    confidence: float
    deal_score: float
    market_median: float | None
    price_ratio: float | None
    evidence: list[dict[str, Any]]


def comparable_pool(target: Listing, listings: list[Listing]) -> list[Listing]:
    pool = [
        row
        for row in listings
        if row.code != target.code
        and row.price
        and row.transaction == target.transaction
        and (row.area == target.area or row.governorate == target.governorate)
        and (row.property_type == target.property_type or row.detail_class == target.detail_class)
    ]
    return sorted(pool, key=lambda row: (row.area == target.area, row.published_date), reverse=True)[:8]


from backend.services.official_valuation import calculate_valuation, assess_deal_quality

def price_label(target: Listing, comps: list[Listing]) -> ValuationResult:
    price = target.price
    clean = [row.price for row in comps if row.price]
    evidence = [
        {
            "code": row.code,
            "area": row.area,
            "price": row.price,
            "priceText": row.price_text,
            "space": row.space,
            "date": row.published_date,
            "url": row.original_url,
        }
        for row in comps[:5]
    ]
    
    # محاولة الحصول على التقييم الرسمي
    features = []
    if hasattr(target, 'features') and target.features:
        features.extend(target.features.split(" "))
        
    official_val, off_breakdown = calculate_valuation(target.area, target.space, features)

    if not price:
        return ValuationResult(
            label="لا يمكن الحكم على السعر",
            reason="السعر غير معلن، لذلك لا يمكن مقارنة السعر بوسيط السوق.",
            confidence=0.35,
            deal_score=35,
            market_median=None,
            price_ratio=None,
            evidence=evidence,
        )

    # إذا كان لدينا تقييم رسمي، سنستخدمه كأساس
    if official_val:
        label = assess_deal_quality(price, official_val)
        ratio = price / official_val
        reason = f"التقييم استند لبيانات رسمية لمتوسط المنطقة. القيمة العادلة المتوقعة {official_val:,.0f} د.ك، والمطلوب {price:,.0f} د.ك."
        
        # تحويل ratio إلى deal_score
        if ratio <= 0.85: deal_score = 100
        elif ratio <= 0.95: deal_score = 88
        elif ratio <= 1.05: deal_score = 74
        elif ratio <= 1.15: deal_score = 58
        else: deal_score = 30
        
        confidence = 0.85 # ثقة عالية للبيانات الرسمية
        
        return ValuationResult(
            label=label,
            reason=reason,
            confidence=confidence,
            deal_score=deal_score,
            market_median=official_val, # استخدام الرسمي كـ market median
            price_ratio=ratio,
            evidence=evidence,
        )

    if len(clean) < 3:
        market = median(clean) if clean else None
        # Sanity check: if the single/limited comparisons indicate a large mismatch, try to recover price from seed data
        if market and price and price < (market / 10):
            # try to find original seed listing by code
            try:
                from backend.config import SEED_LISTINGS_PATH
                import json
                if SEED_LISTINGS_PATH.exists():
                    seed_records = json.loads(SEED_LISTINGS_PATH.read_text(encoding='utf-8'))
                    seed_match = next((r for r in seed_records if str(r.get('code')) == str(target.code)), None)
                    if seed_match and seed_match.get('price'):
                        seed_price = float(seed_match['price'])
                        # accept seed price if it is much closer to market
                        if abs(seed_price - market) < abs(price - market) or seed_price > price * 10:
                            old_price = price
                            price = seed_price
                            evidence.insert(0, {"source": "seed_override", "note": f"Price replaced from seed data {old_price} -> {seed_price}"})
            except Exception:
                pass
        return ValuationResult(
            label="تقييم استرشادي ببيانات محدودة",
            reason=f"يوجد {len(clean)} مقارنة سعرية فقط، وهذا أقل من الحد الأدنى المفضل وهو 3 مقارنات.",
            confidence=0.45,
            deal_score=50,
            market_median=market,
            price_ratio=(price / market) if market else None,
            evidence=evidence,
        )

    market = median(clean)
    ratio = price / market if market else 1

    # Sanity override: إذا كان السعر الحالي بعيد جداً عن وسيط السوق (أقل من 10%) حاول استخدام بيانات seed المحلية إن وُجدت
    if market and price and ratio < 0.1:
        try:
            from backend.config import SEED_LISTINGS_PATH
            import json
            if SEED_LISTINGS_PATH.exists():
                seed_records = json.loads(SEED_LISTINGS_PATH.read_text(encoding='utf-8'))
                seed_match = next((r for r in seed_records if str(r.get('code')) == str(target.code)), None)
                if seed_match and seed_match.get('price'):
                    seed_price = float(seed_match['price'])
                    # قبول سعر الـ seed إذا كان أقرب لوسيط السوق أو على الأقل أكبر بعامل 10
                    if abs(seed_price - market) < abs(price - market) or seed_price > price * 10:
                        old_price = price
                        price = seed_price
                        ratio = price / market if market else ratio
                        evidence.insert(0, {"source": "seed_override", "note": f"تم استبدال السعر من بيانات seed {old_price} -> {seed_price}"})
        except Exception:
            pass

    basis = "المقارنة تمت على السعر الإجمالي للعروض المشابهة"
    if target.space:
        basis += " مع توفر مساحة الإعلان"
    else:
        basis += " لأن مساحة هذا الإعلان غير مذكورة، لذلك لم يتم حساب سعر المتر"

    if ratio <= 0.82:
        label = "لقطة ممتازة"
        reason = f"السعر أقل من وسيط المقارنات بنسبة كبيرة: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك. {basis}."
        deal_score = 100
    elif ratio <= 0.92:
        label = "أقل من السوق"
        reason = f"السعر أقل من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك. {basis}."
        deal_score = 88
    elif ratio <= 1.08:
        label = "سعر عادل"
        reason = f"السعر قريب من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك. {basis}."
        deal_score = 74
    elif ratio <= 1.18:
        label = "أعلى قليلاً"
        reason = f"السعر أعلى قليلًا من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك. {basis}."
        deal_score = 58
    elif ratio <= 1.35:
        label = "غالي"
        reason = f"السعر أعلى بوضوح من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك. {basis}."
        deal_score = 38
    else:
        label = "مبالغ فيه"
        reason = f"السعر أعلى كثيرًا من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك. {basis}."
        deal_score = 20

    confidence = min(0.9, 0.5 + len(clean) * 0.06)
    return ValuationResult(
        label=label,
        reason=reason,
        confidence=confidence,
        deal_score=deal_score,
        market_median=market,
        price_ratio=ratio,
        evidence=evidence,
    )


def recommendation_breakdown(match_score: float, valuation: ValuationResult, warnings: list[str]) -> tuple[float, list[dict[str, Any]]]:
    match_points = round(match_score * 0.62, 1)
    deal_points = round(valuation.deal_score * 0.28, 1)
    confidence_points = round(valuation.confidence * 10, 1)
    missing_penalty = min(12, len(warnings) * 3)
    total = round(max(0, min(100, match_points + deal_points + confidence_points - missing_penalty)), 1)
    return total, [
        {"name": "مطابقة الطلب", "value": match_score, "weight": "62%", "points": match_points},
        {"name": "جاذبية السعر", "value": valuation.deal_score, "weight": "28%", "points": deal_points},
        {"name": "الثقة", "value": round(valuation.confidence * 100), "weight": "10%", "points": confidence_points},
        {"name": "خصم نقص البيانات", "value": len(warnings), "weight": "3 نقاط لكل تحذير حتى 12", "points": -missing_penalty},
        {"name": "درجة التوصية النهائية", "value": total, "weight": "الناتج", "points": total},
    ]


def number_sources(listing: Listing, valuation: ValuationResult) -> dict[str, Any]:
    comp_codes = [item["code"] for item in valuation.evidence]
    return {
        "price": {
            "value": listing.price,
            "display": listing.price_text,
            "source": listing.raw.get("priceSource") or "حقل السعر في بيانات الفريج",
        },
        "space": {
            "value": listing.space,
            "source": listing.raw.get("spaceSource") if listing.space else "غير مذكورة في الإعلان، ولم تدخل في حساب سعر المتر",
        },
        "marketMedian": {
            "value": valuation.market_median,
            "source": f"وسيط أسعار المقارنات: {', '.join(comp_codes) if comp_codes else 'لا توجد مقارنات كافية'}",
        },
        "priceRatio": {
            "value": valuation.price_ratio,
            "source": "السعر المطلوب ÷ وسيط أسعار المقارنات",
        },
        "confidence": {
            "value": valuation.confidence,
            "source": "50% أساس + 6% لكل مقارنة سعرية، بحد أقصى 90%",
        },
    }


def enrich_rankings(request: PropertyRequest, ranked, all_listings: list[Listing]) -> list[RankedListing]:
    output: list[RankedListing] = []
    for item in ranked:
        listing, score, reasons, warnings, match_breakdown = item
        comps = comparable_pool(listing, all_listings)
        valuation = price_label(listing, comps)
        if valuation.evidence:
            reasons.append("تم استخدام عروض مشابهة من نفس المنطقة أو المحافظة")
        else:
            warnings.append("لا توجد مقارنات كافية للتقييم")
        if request.income and listing.property_type in {"عمارة", "تجاري"}:
            reasons.append("الطلب يحتوي دخل عقاري؛ يلزم تقييم دخل تفصيلي عند توفر صفقات")

        rec_score, rec_breakdown = recommendation_breakdown(score, valuation, warnings)
        output.append(
            RankedListing(
                listing=listing,
                match_score=round(score, 1),
                valuation_label=valuation.label,
                valuation_reason=valuation.reason,
                confidence=round(valuation.confidence, 2),
                deal_score=valuation.deal_score,
                recommendation_score=rec_score,
                market_median=valuation.market_median,
                price_ratio=round(valuation.price_ratio, 3) if valuation.price_ratio else None,
                match_breakdown=match_breakdown,
                recommendation_breakdown=rec_breakdown,
                number_sources=number_sources(listing, valuation),
                reasons=reasons,
                warnings=warnings,
                comparables=valuation.evidence,
            )
        )
    output.sort(key=lambda row: (row.recommendation_score, row.match_score, row.confidence), reverse=True)
    return output
