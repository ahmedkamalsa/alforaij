from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from backend.models import Listing, PropertyRequest, RankedListing


@dataclass
class ValuationResult:
    label: str
    reason: str
    confidence: float
    market_median: float | None
    price_ratio: float | None
    deal_score: float
    evidence: list[dict]


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


def price_label(price: float | None, comps: list[Listing]) -> ValuationResult:
    clean = [row.price for row in comps if row.price]
    evidence = [
        {"code": row.code, "area": row.area, "price": row.price, "priceText": row.price_text, "url": row.original_url}
        for row in comps[:5]
    ]
    if not price:
        return ValuationResult(
            label="لا يمكن الحكم على السعر",
            reason="السعر غير معلن، لذلك لا يمكن مقارنة السعر بوسيط السوق.",
            confidence=0.35,
            market_median=None,
            price_ratio=None,
            deal_score=35,
            evidence=evidence,
        )
    if len(clean) < 3:
        return ValuationResult(
            label="تقييم استرشادي ببيانات محدودة",
            reason=f"يوجد {len(clean)} مقارنة سعرية فقط، وهذا أقل من الحد الأدنى المفضل وهو 3 مقارنات.",
            confidence=0.45,
            market_median=median(clean) if clean else None,
            price_ratio=None,
            deal_score=50,
            evidence=evidence,
        )

    market = median(clean)
    ratio = price / market if market else 1
    if ratio <= 0.82:
        label = "لقطة ممتازة"
        reason = f"السعر أقل من وسيط المقارنات بنسبة كبيرة: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك."
        deal_score = 100
    elif ratio <= 0.92:
        label = "أقل من السوق"
        reason = f"السعر أقل من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك."
        deal_score = 88
    elif ratio <= 1.08:
        label = "سعر عادل"
        reason = f"السعر قريب من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك."
        deal_score = 74
    elif ratio <= 1.18:
        label = "أعلى قليلاً"
        reason = f"السعر أعلى قليلًا من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك."
        deal_score = 58
    elif ratio <= 1.35:
        label = "غالي"
        reason = f"السعر أعلى بوضوح من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك."
        deal_score = 38
    else:
        label = "مبالغ فيه"
        reason = f"السعر أعلى كثيرًا من وسيط المقارنات: {price:,.0f} د.ك مقابل وسيط {market:,.0f} د.ك."
        deal_score = 20

    confidence = min(0.9, 0.5 + len(clean) * 0.06)
    return ValuationResult(
        label=label,
        reason=reason,
        confidence=confidence,
        market_median=market,
        price_ratio=ratio,
        deal_score=deal_score,
        evidence=evidence,
    )


def recommendation_score(match_score: float, valuation: ValuationResult, warnings: list[str]) -> float:
    missing_penalty = min(12, len(warnings) * 3)
    score = (match_score * 0.62) + (valuation.deal_score * 0.28) + (valuation.confidence * 10) - missing_penalty
    return round(max(0, min(100, score)), 1)


def enrich_rankings(request: PropertyRequest, ranked, all_listings: list[Listing]) -> list[RankedListing]:
    output: list[RankedListing] = []
    for listing, score, reasons, warnings in ranked:
        comps = comparable_pool(listing, all_listings)
        valuation = price_label(listing.price, comps)
        if valuation.evidence:
            reasons.append("تم استخدام عروض مشابهة من نفس المنطقة أو المحافظة")
        else:
            warnings.append("لا توجد مقارنات كافية للتقييم")
        if request.income and listing.property_type in {"عمارة", "تجاري"}:
            reasons.append("الطلب يحتوي دخل عقاري؛ يلزم تقييم دخل تفصيلي عند توفر صفقات")
        output.append(
            RankedListing(
                listing=listing,
                match_score=round(score, 1),
                valuation_label=valuation.label,
                valuation_reason=valuation.reason,
                confidence=round(valuation.confidence, 2),
                recommendation_score=recommendation_score(score, valuation, warnings),
                market_median=valuation.market_median,
                price_ratio=round(valuation.price_ratio, 3) if valuation.price_ratio else None,
                reasons=reasons,
                warnings=warnings,
                comparables=valuation.evidence,
            )
        )
    output.sort(key=lambda item: (item.recommendation_score, item.match_score, item.confidence), reverse=True)
    return output
