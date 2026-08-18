from __future__ import annotations

import re
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import normalize_text, text_has_area


def add_component(breakdown: list[dict[str, Any]], name: str, points: float, reason: str) -> None:
    breakdown.append({"name": name, "points": round(points, 1), "reason": reason})


GOV_EXPAND_WARNING = "خارج المنطقة المطلوبة (من نفس المحافظة)"
ANY_EXPAND_WARNING = "خارج المنطقة المطلوبة (توسعة استرشادية)"


def score_listing(
    request: PropertyRequest,
    listing: Listing,
    expansion: str = "none",
    allowed_govs: set[str] | None = None,
) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
    """تسجيل مطابقة إعلان لطلب.

    expansion: "none" (صارم — مناطق الطلب فقط)، "governorate" (يسمح بنفس المحافظة
    عند ندرة النتائج بنقاط جزئية ووسم واضح)، أو "any" (توسعة استرشادية أخيرة حتى
    لا يبقى البحث فارغًا في المناطق النادرة).
    """
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    breakdown: list[dict[str, Any]] = []

    if request.transaction:
        if request.transaction == "مطلوب للشراء" and listing.transaction == "للبيع":
            score += 25
            reason = "طلب شراء يقابله عرض بيع مناسب."
            reasons.append(reason)
            add_component(breakdown, "نوع العملية", 25, reason)
        elif request.transaction == "مطلوب للإيجار" and listing.transaction == "للإيجار":
            score += 25
            reason = "طلب إيجار يقابله عرض إيجار مناسب."
            reasons.append(reason)
            add_component(breakdown, "نوع العملية", 25, reason)
        elif request.transaction in {"مطلوب للشراء", "مطلوب للإيجار"} and listing.transaction == request.transaction:
            score += 5
            reason = "هذه نتيجة طلب مشابه وليست عرضًا مباشرًا."
            warnings.append(reason)
            add_component(breakdown, "نوع العملية", 5, reason)
        elif request.transaction in listing.transaction or listing.transaction in request.transaction:
            score += 25
            reason = "نوع المعاملة مطابق."
            reasons.append(reason)
            add_component(breakdown, "نوع العملية", 25, reason)
        else:
            reason = f"المطلوب {request.transaction} والإعلان {listing.transaction}."
            warnings.append(reason)
            add_component(breakdown, "نوع العملية", 0, reason)
            return 0, reasons, warnings, breakdown

    if request.property_type:
        if request.property_type in (listing.property_type + " " + listing.detail_class):
            score += 15
            reason = f"نوع العقار مطابق أو قريب: {listing.property_type or listing.detail_class}."
            reasons.append("نوع العقار قريب من الطلب")
            add_component(breakdown, "نوع العقار", 15, reason)
        else:
            reason = f"المطلوب {request.property_type} والإعلان {listing.property_type}."
            warnings.append(reason)
            add_component(breakdown, "نوع العقار", 0, reason)
            if listing.property_type and listing.property_type != "عقارات":
                return 0, reasons, warnings, breakdown

    if request.areas:
        area_evidence = " ".join([listing.area, listing.governorate, listing.summary, listing.features])
        if any(text_has_area(area, area_evidence) for area in request.areas):
            score += 25
            shown_area = listing.area or "مذكورة في نص الإعلان"
            reason = f"منطقة الإعلان {shown_area} ضمن مناطق الطلب."
            reasons.append("المنطقة مطابقة")
            add_component(breakdown, "المنطقة", 25, reason)
        elif expansion == "governorate" and listing.governorate and allowed_govs and listing.governorate in allowed_govs:
            # توسعة محسوبة لنفس المحافظة عند ندرة نتائج المنطقة: نقاط جزئية + وسم واضح
            score += 10
            reason = f"منطقة الإعلان {listing.area} خارج المناطق المطلوبة لكنها من نفس المحافظة ({listing.governorate})."
            warnings.append(GOV_EXPAND_WARNING)
            add_component(breakdown, "المنطقة", 10, reason)
        elif expansion == "any":
            # توسعة استرشادية أخيرة حتى لا يبقى البحث فارغًا في المناطق النادرة
            score += 5
            reason = f"منطقة الإعلان {listing.area} خارج المناطق المطلوبة — نتيجة استرشادية لتعويض ندرة الإعلانات."
            warnings.append(ANY_EXPAND_WARNING)
            add_component(breakdown, "المنطقة", 5, reason)
        elif expansion == "broad":
            # توسعة عريضة — لا يوجد أي نتيجة في كل المناطق: يعرض إعلانات نفس النوع
            # من أي منطقة حتى لا يبقى المستخدم بلا نتيجة.
            score += 3
            reason = f"منطقة الإعلان {listing.area} خارج المناطق المطلوبة — نتيجة عريضة لتعويض غياب النتائج."
            warnings.append("نتيجة عريضة — خارج المنطقة المطلوبة")
            add_component(breakdown, "المنطقة", 3, reason)
        else:
            reason = f"لا يوجد دليل أن الإعلان داخل {', '.join(request.areas)}."
            warnings.append(reason)
            add_component(breakdown, "المنطقة", 0, reason)
            # Strict area filtering: if user specified an area, reject if not match
            return 0, reasons, warnings, breakdown
    else:
        score += 5
        add_component(breakdown, "المنطقة", 5, "لم يحدد الطلب منطقة، لذلك لم يتم استبعاد الإعلان بسبب الموقع.")

    # Exact space matching vs range matching
    if request.min_area or request.max_area:
        if listing.space:
            min_area = request.min_area or 0
            max_area = request.max_area or 10**9
            # If user requested an exact space (e.g. 400m2), apply a graded tolerance:
            # exact (±10%) keeps full points; nearby (±25%) partial; acceptable (±50%) low;
            # beyond that 0 points — but never hides the listing so similar sale ads stay visible
            if min_area == max_area and min_area > 0:
                diff_ratio = abs(listing.space - min_area) / min_area
                # المساحة خاصية جوهرية للعقار: وزنها عند كل فئة يعلو على وزن تقارب السعر
                # في الفئة المقابلة حتى لا يتفوق إعلان بعيد المساحة أقرب سعرًا على الأقرب مساحةً
                if diff_ratio <= 0.10:
                    score += 15
                    reason = f"المساحة {listing.space:g} م² مطابقة تقريباً للمطلوب ({min_area:g} م²)."
                    reasons.append("المساحة مطابقة للمطلوب")
                    add_component(breakdown, "المساحة", 15, reason)
                elif diff_ratio <= 0.25:
                    score += 10
                    reason = f"المساحة {listing.space:g} م² قريبة من المطلوب ({min_area:g} م²)."
                    warnings.append("المساحة قريبة وليست مطابقة بالضبط")
                    add_component(breakdown, "المساحة", 10, reason)
                elif diff_ratio <= 0.50:
                    score += 5
                    reason = f"المساحة {listing.space:g} م² ضمن نطاق مقبول قريب من المطلوب ({min_area:g} م²)."
                    warnings.append("المساحة أكبر أو أصغر بوضوح من المطلوب")
                    add_component(breakdown, "المساحة", 5, reason)
                else:
                    reason = f"مساحة الإعلان {listing.space:g} م² مختلفة بوضوح عن المطلوب ({min_area:g} م²)."
                    warnings.append("المساحة مختلفة بوضوح عن المطلوب")
                    add_component(breakdown, "المساحة", 0, reason)
            elif min_area <= listing.space <= max_area:
                score += 15
                reason = f"مساحة الإعلان {listing.space:g} م² داخل النطاق المطلوب {min_area:g}-{max_area:g} م²."
                reasons.append("المساحة ضمن النطاق المطلوب")
                add_component(breakdown, "المساحة", 15, reason)
            else:
                reason = f"مساحة الإعلان {listing.space:g} م² خارج النطاق المطلوب."
                warnings.append("المساحة خارج النطاق المطلوب")
                add_component(breakdown, "المساحة", 0, reason)
        else:
            reason = "مساحة الإعلان غير مذكورة، لذلك لم تدخل في نقاط المطابقة ولا في سعر المتر."
            warnings.append("المساحة غير معلنة")
            add_component(breakdown, "المساحة", 0, reason)

    target_budget = request.rent_budget or request.budget
    if target_budget and listing.price:
        delta = abs(listing.price - target_budget) / max(target_budget, 1)
        # وزن الميزانية عند كل فئة أقل من وزن المساحة في الفئة المقابلة:
        # المساحة خاصية جوهرية (15/10/5) بينما تقارب السعر عامل تفضيلي (8/4/4)
        if delta <= 0.08:
            score += 8
            reason = f"السعر {listing.price:,.0f} د.ك قريب جدًا من الميزانية {target_budget:,.0f} د.ك."
            reasons.append("السعر قريب جدًا من الميزانية")
            add_component(breakdown, "الميزانية", 8, reason)
        elif delta <= 0.2:
            score += 4
            reason = f"السعر {listing.price:,.0f} د.ك قريب من الميزانية {target_budget:,.0f} د.ك."
            reasons.append("السعر قريب من الميزانية")
            add_component(breakdown, "الميزانية", 4, reason)
        elif listing.price > target_budget:
            reason = f"السعر {listing.price:,.0f} د.ك أعلى من الميزانية {target_budget:,.0f} د.ك."
            warnings.append("السعر أعلى من الميزانية")
            add_component(breakdown, "الميزانية", 0, reason)
        else:
            reason = f"السعر {listing.price:,.0f} د.ك أقل من الميزانية {target_budget:,.0f} د.ك."
            reasons.append("السعر أقل من الميزانية")
            add_component(breakdown, "الميزانية", 4, reason)
            score += 4

    searchable = normalize_text(" ".join([listing.summary, listing.features, listing.detail_class]))
    
    # Feature scoring
    for feature in request.features + request.condition:
        if normalize_text(feature) in searchable:
            score += 3
            reason = f"يوجد عامل مطلوب: {feature}."
            reasons.append(reason)
            add_component(breakdown, "المواصفات", 3, reason)
            
    # Site features scoring (corner, main street, etc)
    if hasattr(request, 'site_features') and request.site_features:
        for s_feature in request.site_features:
            if normalize_text(s_feature) in searchable:
                 score += 7
                 reason = f"ميزة الموقع المطلوبة متوفرة: {s_feature}."
                 reasons.append(reason)
                 add_component(breakdown, "الموقع", 7, reason)
            else:
                 reason = f"ميزة الموقع المطلوبة غير واضحة: {s_feature}."
                 warnings.append(reason)
                 add_component(breakdown, "الموقع", 0, reason)

    # Seller Type bonus
    if hasattr(listing, 'listing_type') and listing.listing_type == "مباشر":
         score += 2
         reason = "الإعلان من المالك مباشرة (بدون عمولة)."
         reasons.append(reason)
         add_component(breakdown, "نوع العرض", 2, reason)

    if not listing.price:
        warnings.append("السعر غير معلن")
    if not listing.space and not any(item["name"] == "المساحة" for item in breakdown):
        warnings.append("المساحة غير معلنة")
        add_component(breakdown, "المساحة", 0, "المساحة غير مذكورة في الإعلان.")

    return min(score, 100), reasons, warnings, breakdown


def _score_all(
    request: PropertyRequest,
    listings: list[Listing],
    expansion: str = "none",
    allowed_govs: set[str] | None = None,
) -> list[tuple[Listing, float, list[str], list[str], list[dict[str, Any]]]]:
    ranked = []
    for listing in listings:
        score, reasons, warnings, breakdown = score_listing(request, listing, expansion=expansion, allowed_govs=allowed_govs)
        if score > 0:
            ranked.append((listing, score, reasons, warnings, breakdown))
    ranked.sort(key=lambda item: (item[1], item[0].published_date or ""), reverse=True)
    return ranked


def top_matches(
    request: PropertyRequest,
    listings: list[Listing],
    limit: int = 50,
    min_results: int = 3,
) -> list[tuple[Listing, float, list[str], list[str], list[dict[str, Any]]]]:
    """مطابقة على أربع مراحل حتى لا يبقى البحث فارغًا:

    1) صارمة: مناطق الطلب فقط.
    2) توسعة لنفس المحافظة عند ندرة النتائج.
    3) توسعة لكل المناطق (استرشادية).
    4) [جديد] توسعة أخيرة للم橦وب/للإيجار: عند غياب النتائج بالكامل، يبحث
       في كل الإعلانات من نفس نوع العقار حتى لا يبقى المستخدم بلا نتيجة —
       مع وسم "توسعة عريضة" واضح.
    """
    ranked = _score_all(request, listings, expansion="none")
    if request.areas and len(ranked) < min_results:
        requested_govs = {
            item.governorate
            for item in listings
            if item.area in set(request.areas) and item.governorate
        }
        gov_ranked = _score_all(request, listings, expansion="governorate", allowed_govs=requested_govs)
        if len(gov_ranked) > len(ranked):
            ranked = gov_ranked
        if len(ranked) < min_results:
            any_ranked = _score_all(request, listings, expansion="any")
            if len(any_ranked) > len(ranked):
                ranked = any_ranked
    # المرحلة 4: توسعة عريضة — عند غياب النتائج بالكامل، يبحث في كل الإعلانات
    # من نفس نوع العقار (بيع/إيجار) حتى لا يبقى المستخدم بلا نتيجة.
    if len(ranked) == 0 and request.transaction:
        broad_ranked = _score_all(request, listings, expansion="broad")
        if len(broad_ranked) > len(ranked):
            ranked = broad_ranked
    return ranked[:limit]
