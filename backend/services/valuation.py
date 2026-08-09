from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from backend.connectors.official_data import get_official_transaction_rate
from backend.connectors.official_indicators import get_official_rate as get_live_official_rate
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
    # ── حقول خاصة بعروض الإيجار (عند تفعيل is_rental) ──
    rental: bool = False
    monthly_rent: float | None = None
    annual_rent: float | None = None
    rent_per_sqm: float | None = None  # إيجار المتر شهريًا (د.ك/م²/شهر)
    median_rent: float | None = None  # وسيط الإيجارات الشهرية للمقارنات
    median_rent_per_sqm: float | None = None
    capital_value: float | None = None  # قيمة العقار التقديرية (أساس العائد)
    capital_value_kind: str = ""  # official_transactions | official | benchmark | missing
    rental_yield_percent: float | None = None  # الإيجار السنوي ÷ قيمة العقار


def is_rental(listing: Listing) -> bool:
    """هل هذا الإعلان عرض إيجار (شهري) وليس عرض بيع؟"""
    text = f"{listing.transaction or ''} {listing.listing_mode or ''}"
    return "للإيجار" in text or "ايجار" in text


def comparable_pool(
    target: Listing,
    listings: list[Listing],
    request: PropertyRequest | None = None,
) -> list[Listing]:
    """مقارنات صارمة: نفس المنطقة أولاً، وعند نقصها توسعة لنفس المحافظة (الجيران الأقرب)،
    ثم لمناطق الطلب الأخرى — ولا نقبل أبدًا مناطق خارج المحافظة غير مطلوبة.
    """
    allowed_areas: set[str] | None = None
    if request and request.areas:
        allowed_areas = set(request.areas)

    same_transaction = [
        row
        for row in listings
        if row.code != target.code
        and row.price
        and row.transaction == target.transaction
        and (row.property_type == target.property_type or row.detail_class == target.detail_class)
    ]

    same_area = [row for row in same_transaction if row.area == target.area]
    # توسعة محسوبة فقط عند نقص مقارنات نفس المنطقة: نفس المحافظة أولاً (الأقرب جغرافيًا وسعريًا)
    if len(same_area) >= 3:
        pool = same_area
    else:
        same_gov = [row for row in same_transaction if row.area != target.area and row.governorate == target.governorate]
        others: list[Listing] = []
        if allowed_areas:
            others = [
                row
                for row in same_transaction
                if row.area != target.area and row.governorate != target.governorate and row.area in allowed_areas
            ]
        pool = same_area + same_gov + others
    return sorted(pool, key=lambda row: (row.area == target.area, row.governorate == target.governorate, row.published_date), reverse=True)[:8]


def _sqm_rate(listing: Listing) -> float | None:
    if listing.price and listing.space:
        return listing.price / listing.space
    return None


def _capital_value_estimate(target: Listing) -> tuple[float | None, str]:
    """قيمة العقار التقديرية من المصادر الرسمية فقط (أساس حساب العائد الإيجاري).

    الترتيب: صفقات رسمية مسجلة ← مؤشر رسمي حي ← معيار المنطقة الرسمي.
    لا تُشتق من إعلانات الإيجار أبدًا (سعر متر الإيجار ليس سعر شراء).
    """
    if not target.space:
        return None, ""
    rate, count, window = get_official_transaction_rate(target.area)
    if rate:
        return rate * target.space, f"official_transactions|وسيط {count} صفقة رسمية مسجلة ({window})"
    live, src, _ = get_live_official_rate(target.area)
    if live:
        return live * target.space, f"official|المؤشر الرسمي لسعر المتر ({src})"
    official_val, _breakdown = calculate_valuation(target.area, target.space, [])
    if official_val:
        return official_val, "benchmark|المعيار الرسمي للمنطقة (سعر المتر × المساحة)"
    return None, ""


def _rental_price_label(target: Listing, comps: list[Listing]) -> ValuationResult:
    """خط حساب مميز لعروض الإيجار: الإيجار الشهري/السنوي، إيجار المتر،
    وسيط إيجارات المنطقة، قيمة العقار التقديرية، والعائد الإيجاري السنوي.

    الإيجار يختلف جوهريًا عن البيع: السعر قيمة شهرية وليست إجمالية،
    والتقييم يقارنها بوسيط الإيجارات في المنطقة، والعائد = الإيجار السنوي ÷ قيمة العقار.
    """
    monthly = target.price
    annual = (monthly * 12) if monthly else None
    rent_per_sqm = (monthly / target.space) if (monthly and target.space) else None
    clean = [row.price for row in comps if row.price]
    median_rent = median(clean) if clean else None
    sqm_rates = [row.price / row.space for row in comps if row.price and row.space]
    median_rent_sqm = median(sqm_rates) if sqm_rates else None
    ratio = (monthly / median_rent) if (monthly and median_rent) else None

    capital_value, capital_kind_raw = _capital_value_estimate(target)
    capital_kind = capital_kind_raw.split("|")[0] if capital_kind_raw else "missing"
    capital_note = capital_kind_raw.split("|")[1] if "|" in (capital_kind_raw or "") else ""
    yield_pct = (annual / capital_value * 100) if (annual and capital_value) else None

    evidence = [
        {
            "code": row.code,
            "source": row.source,
            "area": row.area,
            "price": row.price,
            "priceText": row.price_text,
            "space": row.space,
            "date": row.published_date,
            "url": row.original_url,
        }
        for row in comps[:5]
    ]
    same_area_count = sum(1 for row in comps if row.area == target.area)
    scope = "نفس المنطقة" if same_area_count >= 3 else ("نفس المنطقة + توسعة محدودة" if comps else "بدون مقارنات")

    if not monthly:
        return ValuationResult(
            label="لا يمكن الحكم على الإيجار",
            reason="الإيجار غير معلن، لذلك لا يمكن مقارنته بوسيط إيجارات المنطقة.",
            confidence=0.35,
            deal_score=35,
            market_median=median_rent,
            price_ratio=None,
            evidence=evidence,
            price_per_sqm=rent_per_sqm,
            median_per_sqm=median_rent_sqm,
            official_value=capital_value,
            official_source_kind="rental",
            comparables_count=len(clean),
            comparable_scope=scope,
            rental=True,
            monthly_rent=None,
            annual_rent=None,
            rent_per_sqm=rent_per_sqm,
            median_rent=median_rent,
            median_rent_per_sqm=median_rent_sqm,
            capital_value=capital_value,
            capital_value_kind=capital_kind,
            rental_yield_percent=None,
        )

    if not median_rent:
        return ValuationResult(
            label="تقييم استرشادي ببيانات محدودة",
            reason=(
                f"لا توجد عروض إيجار كافية للمقارنة في {target.area or 'المنطقة'}، "
                f"فلم يُحكم على عدالة الإيجار بشكل قاطع."
            ),
            confidence=0.45,
            deal_score=50,
            market_median=None,
            price_ratio=None,
            evidence=evidence,
            price_per_sqm=rent_per_sqm,
            median_per_sqm=median_rent_sqm,
            official_value=capital_value,
            official_source_kind="rental",
            comparables_count=len(clean),
            comparable_scope=scope,
            rental=True,
            monthly_rent=monthly,
            annual_rent=annual,
            rent_per_sqm=rent_per_sqm,
            median_rent=None,
            median_rent_per_sqm=median_rent_sqm,
            capital_value=capital_value,
            capital_value_kind=capital_kind,
            rental_yield_percent=yield_pct,
        )

    # عدالة الإيجار: نسبة الإيجار المطلوب إلى وسيط إيجارات المنطقة
    if ratio <= 0.82:
        label = "إيجار ممتاز"
        reason = f"الإيجار أقل من وسيط إيجارات المنطقة بوضوح: {monthly:,.0f} د.ك/شهر مقابل وسيط {median_rent:,.0f} د.ك/شهر."
        deal_score = 100
    elif ratio <= 0.92:
        label = "أقل من السوق"
        reason = f"الإيجار أقل من وسيط إيجارات المنطقة: {monthly:,.0f} د.ك/شهر مقابل وسيط {median_rent:,.0f} د.ك/شهر."
        deal_score = 88
    elif ratio <= 1.08:
        label = "إيجار عادل"
        reason = f"الإيجار قريب من وسيط إيجارات المنطقة: {monthly:,.0f} د.ك/شهر مقابل وسيط {median_rent:,.0f} د.ك/شهر."
        deal_score = 74
    elif ratio <= 1.18:
        label = "أعلى قليلاً"
        reason = f"الإيجار أعلى قليلًا من وسيط إيجارات المنطقة: {monthly:,.0f} د.ك/شهر مقابل وسيط {median_rent:,.0f} د.ك/شهر."
        deal_score = 58
    elif ratio <= 1.35:
        label = "غالي"
        reason = f"الإيجار أعلى بوضوح من وسيط إيجارات المنطقة: {monthly:,.0f} د.ك/شهر مقابل وسيط {median_rent:,.0f} د.ك/شهر."
        deal_score = 38
    else:
        label = "مبالغ فيه"
        reason = f"الإيجار أعلى كثيرًا من وسيط إيجارات المنطقة: {monthly:,.0f} د.ك/شهر مقابل وسيط {median_rent:,.0f} د.ك/شهر."
        deal_score = 20

    basis = f"المقارنة تمت داخل {scope} على الإيجار الشهري للعروض المشابهة"
    if target.space and median_rent_sqm:
        basis += f"، وإيجار المتر للمطلوب {rent_per_sqm:,.0f} د.ك/م²/شهر مقابل وسيط {median_rent_sqm:,.0f} د.ك/م²/شهر"
    if yield_pct is not None and capital_note:
        basis += f"، والعائد الإيجاري السنوي المتوقع {yield_pct:.1f}% (الإيجار السنوي {annual:,.0f} د.ك ÷ قيمة العقار التقديرية {capital_value:,.0f} د.ك — {capital_note})"
    reason = f"{reason} {basis}."
    confidence = min(0.9, 0.5 + len(clean) * 0.06)
    if capital_kind == "official_transactions":
        confidence = max(confidence, 0.9)
    elif capital_kind == "official":
        confidence = max(confidence, 0.85)
    return ValuationResult(
        label=label,
        reason=reason,
        confidence=confidence,
        deal_score=deal_score,
        market_median=median_rent,
        price_ratio=round(ratio, 3),
        evidence=evidence,
        price_per_sqm=rent_per_sqm,
        median_per_sqm=median_rent_sqm,
        official_value=capital_value,
        official_source_kind="rental",
        comparables_count=len(clean),
        comparable_scope=scope,
        rental=True,
        monthly_rent=monthly,
        annual_rent=annual,
        rent_per_sqm=rent_per_sqm,
        median_rent=median_rent,
        median_rent_per_sqm=median_rent_sqm,
        capital_value=capital_value,
        capital_value_kind=capital_kind,
        rental_yield_percent=round(yield_pct, 2) if yield_pct is not None else None,
    )


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
    # 2) المؤشر الرسمي الحي (جدول official_market_indicators): سعر المتر المرجعي الرسمي
    #    للمنطقة من بيانات Supabase الحية — يُجيب مباشرة على «لا توجد بيانات رسمية لسعر المتر»
    if target.space:
        live_rate, live_source, _live_note = get_live_official_rate(target.area)
        if live_rate:
            official_val = live_rate * target.space
            breakdown = [
                {
                    "factor": f"سعر المتر المرجعي من المؤشرات الرسمية ({live_source})",
                    "value": official_val,
                }
            ]
            return official_val, breakdown, "official", 1, ""
    # 3) المعيار الرسمي للمنطقة (سعر المتر الرسمي × المساحة)
    official_val, official_breakdown = calculate_valuation(target.area, target.space, features)
    if official_val:
        return official_val, official_breakdown, "official", 0, ""
    # 4) سعر المتر المشتق من الإعلانات الفعلية في المنطقة
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
    # عروض الإيجار لها خط حساب مميز (إيجار شهري/سنوي + عائد) — لا يُطبَّق عليها منطق البيع أبدًا
    if is_rental(target):
        return _rental_price_label(target, comps)
    price = target.price
    clean = [row.price for row in comps if row.price]
    evidence = [
        {
            "code": row.code,
            "source": row.source,
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

    # التقييم: عند توفر 3 مقارنات سوقية فعلية في نفس السياق نستخدم وسيط السوق
    # كرقم العرض الرئيسي، ونبقي المؤشر الرسمي كدليل إضافي. هذا يمنع أن يطغى
    # معيار رسمي محافظ على مجموعة عروض بيع واضحة مثل شقق السالمية.
    if official_val and (official_kind == "official_transactions" or len(clean) < 2):
        label = assess_deal_quality(price, official_val)
        ratio = price / official_val
        sqm_text = f" وسعر المتر المتوقع {official_val / target.space:,.0f} د.ك/م²." if target.space else ""
        breakdown_text = "، ".join(
            f"{item.get('factor')}: {item.get('value'):,.0f} د.ك"
            for item in (official_breakdown or [])
            if item.get("value")
        )
        if official_kind == "official_transactions":
            basis = (
                f"استند التقييم إلى سجل الصفقات الرسمية المسجلة في {target.area} "
                f"({official_window}) — المرجع الأعلى مصداقية من الإعلانات."
            )
            confidence = 0.9
        elif official_kind == "official":
            basis = f"استند التقييم إلى التقييم الرسمي لسعر المتر في {target.area}."
            confidence = 0.85
        else:
            basis = (
                f"لا يوجد معيار رسمي منشور لسعر المتر في {target.area}، "
                f"فاستُخدم سعر المتر المشتق من الإعلانات الفعلية في المنطقة."
            )
            confidence = min(0.8, 0.45 + len(clean) * 0.05)
        fair_pct = (price / official_val * 100) if official_val else 0.0
        reason = (
            f"القيمة العادلة المتوقعة للعقار {official_val:,.0f} د.ك مقابل السعر المطلوب "
            f"{price:,.0f} د.ك، أي ما يعادل {fair_pct:,.0f}% من القيمة العادلة.{sqm_text} "
            f"{basis}"
            + (f" تفصيل الحساب: {breakdown_text}." if breakdown_text else "")
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
    # ── خط شفافية مميز لعروض الإيجار: إيجار شهري/سنوي، إيجار المتر، وسيط الإيجارات، العائد ──
    if valuation.rental:
        comp_codes = [item["code"] for item in valuation.evidence]
        rent_source = (
            f"وسيط الإيجارات الشهرية للمقارنات ({valuation.comparable_scope}): {', '.join(comp_codes) if comp_codes else 'لا توجد مقارنات كافية'}"
        )
        capital_source = "قيمة العقار التقديرية غير متوفرة (تحتاج مساحة + مصدر رسمي)"
        if valuation.capital_value and valuation.capital_value_kind == "official_transactions":
            capital_source = "سعر المتر من الصفقات الرسمية المسجلة في المنطقة × المساحة (أساس العائد الإيجاري)"
        elif valuation.capital_value and valuation.capital_value_kind == "official":
            capital_source = "المؤشر الرسمي الحي لسعر المتر × المساحة (أساس العائد الإيجاري)"
        elif valuation.capital_value and valuation.capital_value_kind == "benchmark":
            capital_source = "المعيار الرسمي للمنطقة (سعر المتر × المساحة) كأساس تقديري للعائد"
        return {
            "rental": {"value": True, "display": "إيجار شهري", "source": "عرض للإيجار — خط حساب مميز عن البيع"},
            "price": {
                "value": listing.price,
                "display": f"{listing.price:,.0f} د.ك/شهر" if listing.price else "غير معلن",
                "source": "الإيجار الشهري المطلوب في الإعلان",
            },
            "annualRent": {
                "value": valuation.annual_rent,
                "display": f"{valuation.annual_rent:,.0f} د.ك/سنة" if valuation.annual_rent else "غير محسوب",
                "source": "الإيجار الشهري × 12 شهرًا",
            },
            "space": {
                "value": listing.space,
                "source": listing.raw.get("spaceSource") if listing.space else "غير مذكورة في الإعلان، ولم تدخل في حساب إيجار المتر",
            },
            "pricePerSqm": {
                "value": valuation.rent_per_sqm,
                "display": f"{valuation.rent_per_sqm:,.0f} د.ك/م²/شهر" if valuation.rent_per_sqm else "غير محسوب",
                "source": "الإيجار الشهري ÷ مساحة الإعلان",
            },
            "marketMedian": {
                "value": valuation.median_rent,
                "display": f"{valuation.median_rent:,.0f} د.ك/شهر" if valuation.median_rent else "غير متوفر",
                "source": rent_source,
            },
            "medianPerSqm": {
                "value": valuation.median_rent_per_sqm,
                "display": f"{valuation.median_rent_per_sqm:,.0f} د.ك/م²/شهر" if valuation.median_rent_per_sqm else "غير محسوب",
                "source": "وسيط إيجار المتر الشهري بين عروض الإيجار المتاحة",
            },
            "officialValue": {
                "value": valuation.capital_value,
                "display": f"{valuation.capital_value:,.0f} د.ك" if valuation.capital_value else "غير متوفر",
                "source": capital_source,
            },
            "rentalYield": {
                "value": valuation.rental_yield_percent,
                "display": f"{valuation.rental_yield_percent:.1f}% سنويًا" if valuation.rental_yield_percent is not None else "غير محسوب",
                "source": "الإيجار السنوي ÷ قيمة العقار التقديرية — يقارن العائد بشراء العقار بدل تأجيره",
            },
            "priceRatio": {
                "value": valuation.price_ratio,
                "source": "الإيجار الشهري المطلوب ÷ وسيط الإيجارات الشهرية في المنطقة",
            },
            "comparablesCount": {
                "value": valuation.comparables_count,
                "source": f"عدد عروض الإيجار الداخلة في التقييم ({valuation.comparable_scope})",
            },
            "confidence": {
                "value": valuation.confidence,
                "source": (
                    "ثقة عالية جدًا لأن قيمة العقار الأساس اشتُقت من صفقات رسمية مسجلة في المنطقة"
                    if valuation.capital_value_kind == "official_transactions"
                    else (
                        "ثقة عالية لأن قيمة العقار الأساس اشتُقت من مؤشر رسمي حي لسعر المتر"
                        if valuation.capital_value_kind == "official"
                        else f"ثقة من {valuation.comparables_count} عروض إيجار في المنطقة + المعيار الرسمي للمنطقة"
                    )
                ),
            },
        }

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
