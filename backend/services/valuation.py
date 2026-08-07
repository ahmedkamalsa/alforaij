from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from backend.connectors.official_data import get_official_transaction_rate
from backend.models import Listing, PropertyRequest, RankedListing
from backend.services.official_valuation import calculate_valuation, assess_deal_quality, derive_market_benchmark


@dataclass
class ValuationResult:
    label: str
    reason: str
    confidence: float
    deal_score: float
    market_median: float | None
    price_ratio: float | None
    evidence: list[dict[str, Any]]
    price_per_sqm: float | None = None
    median_per_sqm: float | None = None
    official_value: float | None = None
    official_breakdown: list[dict[str, Any]] | None = None
    official_source_kind: str = "missing"  # official_transactions | official | derived | missing
    official_window: str = ""  # نافذة الصفقات المستخدمة (آخر 24 شهرًا / كامل السجل)
    derived_evidence_count: int = 0  # عدد الأدلة الفعلية التي اشتُق منها سعر المتر
    comparables_count: int = 0
    comparable_scope: str = ""


def comparable_pool(
    target: Listing,
    listings: list[Listing],
    request: PropertyRequest | None = None,
) -> list[Listing]:
    """مقارنات صارمة: نفس المنطقة أولاً، ولا نقبل أي إعلان خارج مناطق الطلب أبدًا."""
    allowed_areas: set[str] | None = None
    if request and request.areas:
        allowed_areas = set(request.areas)

    candidates = [
        row
        for row in listings
        if row.code != target.code
        and row.price
        and row.transaction == target.transaction
        and (row.property_type == target.property_type or row.detail_class == target.detail_class)
        and (
            (allowed_areas is not None and row.area in allowed_areas)
            or (allowed_areas is None and (row.area == target.area or row.governorate == target.governorate))
        )
    ]

    same_area = [row for row in candidates if row.area == target.area]
    # توسعة محسوبة فقط عند نقص مقارنات نفس المنطقة (داخل مناطق الطلب)
    if len(same_area) >= 3:
        pool = same_area
    else:
        others = [row for row in candidates if row.area != target.area]
        pool = same_area + others
    return sorted(pool, key=lambda row: (row.area == target.area, row.published_date), reverse=True)[:8]


def _sqm_rate(listing: Listing) -> float | None:
    if listing.price and listing.space:
        return listing.price / listing.space
    return None


def _official_valuation(
    target: Listing, comps: list[Listing] | None = None
) -> tuple[float | None, list[dict[str, Any]], str, int, str]:
    """القيمة العادلة: صفقات رسمية إن وُجدت، ثم معيار رسمي، ثم سعر متر مشتق من الإعلانات.

    ترتيب المراجع (أعلى مصداقية أولًا): صفقات رسمية مسجلة ← معيار رسمي للمنطقة ←
    وسيط الإعلانات الفعلية في المنطقة. حتمي بالكامل — بلا عشوائية.
    يعيد (القيمة، التفصيل، نوع المرجع، عدد الأدلة، نافذة الصفقات الزمنية).
    """
    features: list[str] = []
    if target.features:
        features.extend(target.features.split(" "))
    # 1) الصفقات الرسمية: مرجع مرجّح أعلى من الإعلانات عند توفر صفقات بنفس المنطقة
    if target.space:
        official_rate, official_count, official_window = get_official_transaction_rate(target.area)
        if official_rate:
            official_val = official_rate * target.space
            breakdown = [
                {
                    "factor": (
                        f"سعر المتر من الصفقات الرسمية المسجلة ({official_window}) — "
                        f"وسيط {official_count} صفقة فعلية في المنطقة"
                    ),
                    "value": official_val,
                }
            ]
            return official_val, breakdown, "official_transactions", official_count, official_window
    # 2) المعيار الرسمي للمنطقة (سعر المتر الرسمي × المساحة)
    official_val, official_breakdown = calculate_valuation(target.area, target.space, features)
    if official_val:
        return official_val, official_breakdown, "official", 0, ""
    # 3) سعر المتر المشتق من الإعلانات الفعلية في المنطقة
    rate, count = derive_market_benchmark(target.area, comps or [])
    if rate and target.space:
        derived_val = rate * target.space
        breakdown = [
            {
                "factor": f"سعر المتر المشتق من السوق (وسيط {count} إعلان فعلي في المنطقة)",
                "value": derived_val,
            }
        ]
        return derived_val, breakdown, "derived", count, ""
    return None, [], "missing", 0, ""


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

    price_per_sqm = _sqm_rate(target)
    sqm_rates = [rate for rate in (_sqm_rate(row) for row in comps) if rate]
    median_per_sqm = median(sqm_rates) if sqm_rates else None
    official_val, official_breakdown, official_kind, official_count, official_window = _official_valuation(target, comps)
    same_area_count = sum(1 for row in comps if row.area == target.area)
    scope = "نفس المنطقة" if same_area_count >= 3 else ("نفس المنطقة + توسعة محدودة" if comps else "بدون مقارنات")

    common = dict(
        price_per_sqm=price_per_sqm,
        median_per_sqm=median_per_sqm,
        official_value=official_val,
        official_breakdown=official_breakdown or [],
        official_source_kind=official_kind,
        official_window=official_window,
        derived_evidence_count=official_count,
        comparables_count=len(clean),
        comparable_scope=scope,
    )

    if not price:
        return ValuationResult(
            label="لا يمكن الحكم على السعر",
            reason="السعر غير معلن، لذلك لا يمكن مقارنة السعر بوسيط السوق.",
            confidence=0.35,
            deal_score=35,
            market_median=None,
            price_ratio=None,
            evidence=evidence,
            **common,
        )

    # التقييم: معيار رسمي إن وُجد، وإلا سعر متر مشتق من السوق الفعلي — دائمًا بإفصاح شفاف
    if official_val:
        label = assess_deal_quality(price, official_val)
        ratio = price / official_val
        sqm_text = f" وسعر المتر المتوقع {official_val / target.space:,.0f} د.ك/م²." if target.space else ""
        breakdown_text = "، ".join(
            f"{item.get('factor')}: {item.get('value'):,.0f} د.ك"
            for item in (official_breakdown or [])
            if item.get("value")
        )
        if official_kind == "official_transactions":
            basis = f"التقييم استند لسجل الصفقات الرسمية المسجلة في {target.area} ({official_window}) — أعلى مصداقية من الإعلانات."
            confidence = 0.9
        elif official_kind == "official":
            basis = f"التقييم استند للتقييم الرسمي لسعر المتر في {target.area}."
            confidence = 0.85
        else:
            basis = (
                f"لا يوجد معيار رسمي منشور لسعر المتر في {target.area}، "
                f"فاستُخدم سعر المتر المشتق من الإعلانات الفعلية في المنطقة."
            )
            confidence = min(0.8, 0.45 + len(clean) * 0.05)
        reason = (
            f"{basis} "
            f"القيمة العادلة المتوقعة {official_val:,.0f} د.ك، والمطلوب {price:,.0f} د.ك.{sqm_text}"
            + (f" تفصيله: {breakdown_text}." if breakdown_text else "")
        )
        if ratio <= 0.85:
            deal_score = 100
        elif ratio <= 0.95:
            deal_score = 88
        elif ratio <= 1.05:
            deal_score = 74
        elif ratio <= 1.15:
            deal_score = 58
        else:
            deal_score = 30
        return ValuationResult(
            label=label,
            reason=reason,
            confidence=confidence,
            deal_score=deal_score,
            market_median=official_val,
            price_ratio=ratio,
            evidence=evidence,
            **common,
        )

    if len(clean) < 3:
        market = median(clean) if clean else None
        if market and price and price < (market / 10):
            price = _try_seed_override(target, market, price, evidence)
        return ValuationResult(
            label="تقييم استرشادي ببيانات محدودة",
            reason=(
                f"يوجد {len(clean)} مقارنة سعرية فقط في {target.area or 'المنطقة'}، "
                f"وهذا أقل من الحد الأدنى المفضل وهو 3 مقارنات لثقة أعلى."
            ),
            confidence=0.45,
            deal_score=50,
            market_median=market,
            price_ratio=(price / market) if market else None,
            evidence=evidence,
            **common,
        )

    market = median(clean)
    ratio = price / market if market else 1
    if market and price and ratio < 0.1:
        price = _try_seed_override(target, market, price, evidence)
        ratio = price / market if market else ratio

    basis = f"المقارنة تمت داخل {scope} على السعر الإجمالي للعروض المشابهة"
    if target.space:
        basis += f"، وسعر المتر للمطلوب {price / target.space:,.0f} د.ك/م² مقابل وسيط {median_per_sqm:,.0f} د.ك/م²" if median_per_sqm else ""
    else:
        basis += "، لأن مساحة هذا الإعلان غير مذكورة لم يُحسب سعر المتر"

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
        **common,
    )


def _try_seed_override(target: Listing, market: float, price: float, evidence: list[dict[str, Any]]) -> float:
    """استعادة سعر أصلح من بيانات seed إذا كان السعر الحالي بعيدًا جدًا عن السوق."""
    try:
        from backend.config import SEED_LISTINGS_PATH
        import json

        if not SEED_LISTINGS_PATH.exists():
            return price
        seed_records = json.loads(SEED_LISTINGS_PATH.read_text(encoding="utf-8"))
        seed_match = next((r for r in seed_records if str(r.get("code")) == str(target.code)), None)
        if not seed_match or not seed_match.get("price"):
            return price
        seed_price = float(seed_match["price"])
        if abs(seed_price - market) < abs(price - market) or seed_price > price * 10:
            old_price = price
            evidence.insert(0, {"source": "seed_override", "note": f"تم استبدال السعر من بيانات seed {old_price:,.0f} -> {seed_price:,.0f}"})
            return seed_price
    except Exception:
        pass
    return price


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
    # عند وجود قيمة رسمية قد لا يُملأ وسيط السوق (مثل إعلان بلا سعر) — نستخدم القيمة الرسمية كعرض آمن
    market_value = valuation.market_median if valuation.market_median is not None else valuation.official_value
    market_source = f"وسيط أسعار المقارنات ({valuation.comparable_scope}): {', '.join(comp_codes) if comp_codes else 'لا توجد مقارنات كافية'}"
    if valuation.official_value:
        if valuation.official_source_kind == "official_transactions":
            market_source = (
                f"وسيط الصفقات الرسمية المسجلة في المنطقة ({valuation.official_window or 'كامل السجل المتاح'}) "
                f"× المساحة = {market_value:,.0f} د.ك (وسيط {valuation.derived_evidence_count} صفقة رسمية)"
            )
        elif valuation.official_source_kind == "official":
            market_source = f"التقييم الرسمي للمنطقة (سعر المتر × المساحة) = {market_value:,.0f} د.ك"
        else:
            market_source = f"سعر المتر المشتق من السوق × المساحة = {market_value:,.0f} د.ك (وسيط {valuation.derived_evidence_count or valuation.comparables_count} إعلان فعلي في المنطقة)"
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
        "pricePerSqm": {
            "value": valuation.price_per_sqm,
            "display": f"{valuation.price_per_sqm:,.0f} د.ك/م²" if valuation.price_per_sqm else "غير محسوب",
            "source": "سعر المطلوب ÷ مساحة الإعلان",
        },
        "marketMedian": {
            "value": valuation.market_median,
            "source": market_source,
        },
        "medianPerSqm": {
            "value": valuation.median_per_sqm,
            "display": f"{valuation.median_per_sqm:,.0f} د.ك/م²" if valuation.median_per_sqm else "غير محسوب",
            "source": "وسيط سعر المتر بين المقارنات المتاحة",
        },
        "officialValue": {
            "value": valuation.official_value,
            "display": f"{valuation.official_value:,.0f} د.ك" if valuation.official_value else "غير متوفر",
            "source": (
                (
                    "وسيط سعر المتر من الصفقات الرسمية المسجلة في المنطقة × مساحة الإعلان، تفصيله: "
                    if valuation.official_source_kind == "official_transactions"
                    else (
                        "التقييم الرسمي لسعر المتر في المنطقة × مساحة الإعلان، تفصيله: "
                        if valuation.official_source_kind == "official"
                        else f"لا يوجد معيار رسمي منشور لسعر المتر في هذه المنطقة؛ سعر المتر مشتق من وسيط {valuation.derived_evidence_count or valuation.comparables_count} إعلان فعلي، تفصيله: "
                    )
                )
                + "; ".join(
                    f"{item.get('factor')} {item.get('value'):,.0f} د.ك"
                    for item in (valuation.official_breakdown or [])
                    if item.get("value")
                )
                if valuation.official_value
                else "لا توجد بيانات رسمية موثوقة لسعر المتر في هذه المنطقة، ولا مقارنات سوقية كافية لاشتقاقها"
            ),
        },
        "priceRatio": {
            "value": valuation.price_ratio,
            "source": (
                (
                    "السعر المطلوب ÷ وسيط الصفقات الرسمية"
                    if valuation.official_source_kind == "official_transactions"
                    else ("السعر المطلوب ÷ التقييم الرسمي للمنطقة" if valuation.official_source_kind == "official" else "السعر المطلوب ÷ سعر المتر المشتق من السوق")
                )
                if valuation.official_value
                else "السعر المطلوب ÷ وسيط أسعار المقارنات"
            ),
        },
        "confidence": {
            "value": valuation.confidence,
            "source": (
                "ثقة عالية جدًا لأن التقييم استند لصفقات رسمية مسجلة في المنطقة"
                if valuation.official_source_kind == "official_transactions"
                else (
                    "ثقة عالية لأن التقييم استند لبيانات رسمية لسعر المتر في المنطقة"
                    if valuation.official_source_kind == "official"
                    else (
                        f"ثقة متوسطة من {valuation.derived_evidence_count or valuation.comparables_count} مقارنة سوقية اشتُق منها سعر المتر (بلا عشوائية)"
                        if valuation.official_source_kind == "derived"
                        else "50% أساس + 6% لكل مقارنة سعرية، بحد أقصى 90%"
                    )
                )
            ),
        },
        "comparablesCount": {
            "value": valuation.comparables_count,
            "source": f"عدد المقارنات السعرية الداخلة في التقييم ({valuation.comparable_scope})",
        },
    }


def enrich_rankings(request: PropertyRequest, ranked, all_listings: list[Listing]) -> list[RankedListing]:
    output: list[RankedListing] = []
    for item in ranked:
        listing, score, reasons, warnings, match_breakdown = item
        comps = comparable_pool(listing, all_listings, request)
        valuation = price_label(listing, comps)
        if valuation.evidence:
            reasons.append(f"تم استخدام مقارنات داخل {valuation.comparable_scope}")
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
