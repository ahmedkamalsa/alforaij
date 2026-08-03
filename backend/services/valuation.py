from __future__ import annotations

from statistics import median

from backend.models import Listing, PropertyRequest, RankedListing


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


def price_label(price: float | None, comps: list[Listing]) -> tuple[str, float, list[dict]]:
    clean = [row.price for row in comps if row.price]
    evidence = [
        {"code": row.code, "area": row.area, "price": row.price, "priceText": row.price_text, "url": row.original_url}
        for row in comps[:5]
    ]
    if not price:
        return "لا يمكن الحكم على السعر", 0.35, evidence
    if len(clean) < 3:
        return "تقييم استرشادي ببيانات محدودة", 0.45, evidence
    market = median(clean)
    ratio = price / market if market else 1
    if ratio <= 0.82:
        label = "لقطة ممتازة"
    elif ratio <= 0.92:
        label = "أقل من السوق"
    elif ratio <= 1.08:
        label = "سعر عادل"
    elif ratio <= 1.18:
        label = "أعلى قليلًا"
    elif ratio <= 1.35:
        label = "غالي"
    else:
        label = "مبالغ فيه"
    confidence = min(0.9, 0.5 + len(clean) * 0.06)
    return label, confidence, evidence


def enrich_rankings(request: PropertyRequest, ranked, all_listings: list[Listing]) -> list[RankedListing]:
    output: list[RankedListing] = []
    for listing, score, reasons, warnings in ranked:
        comps = comparable_pool(listing, all_listings)
        label, confidence, evidence = price_label(listing.price, comps)
        if evidence:
            reasons.append("تم استخدام عروض مشابهة من نفس المنطقة أو المحافظة")
        else:
            warnings.append("لا توجد مقارنات كافية للتقييم")
        if request.income and listing.property_type in {"عمارة", "تجاري"}:
            reasons.append("الطلب يحتوي دخل عقاري؛ يلزم تقييم دخل تفصيلي عند توفر صفقات")
        output.append(
            RankedListing(
                listing=listing,
                match_score=round(score, 1),
                valuation_label=label,
                confidence=round(confidence, 2),
                reasons=reasons,
                warnings=warnings,
                comparables=evidence,
            )
        )
    return output

