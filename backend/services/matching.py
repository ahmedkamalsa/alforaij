from __future__ import annotations

import re
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import normalize_text, text_has_area


def add_component(breakdown: list[dict[str, Any]], name: str, points: float, reason: str) -> None:
    breakdown.append({"name": name, "points": round(points, 1), "reason": reason})


def score_listing(request: PropertyRequest, listing: Listing) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
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
            # If user requested an exact space (e.g. 400m2), apply a strict tolerance (e.g., +/- 10%)
            if min_area == max_area and min_area > 0:
                tolerance = 0.10 * min_area
                if abs(listing.space - min_area) <= tolerance:
                     score += 15
                     reason = f"المساحة {listing.space:g} م² مطابقة تقريباً للمطلوب ({min_area:g} م²)."
                     reasons.append("المساحة مطابقة للمطلوب")
                     add_component(breakdown, "المساحة", 15, reason)
                else:
                     reason = f"مساحة الإعلان {listing.space:g} م² لا تتطابق بدقة مع المطلوب ({min_area:g} م²)."
                     warnings.append("المساحة غير مطابقة")
                     add_component(breakdown, "المساحة", 0, reason)
                     # For exact space requests, this is a strong rejection criteria
                     return 0, reasons, warnings, breakdown
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
        if delta <= 0.08:
            score += 10
            reason = f"السعر {listing.price:,.0f} د.ك قريب جدًا من الميزانية {target_budget:,.0f} د.ك."
            reasons.append("السعر قريب جدًا من الميزانية")
            add_component(breakdown, "الميزانية", 10, reason)
        elif delta <= 0.2:
            score += 5
            reason = f"السعر {listing.price:,.0f} د.ك قريب من الميزانية {target_budget:,.0f} د.ك."
            reasons.append("السعر قريب من الميزانية")
            add_component(breakdown, "الميزانية", 5, reason)
        elif listing.price > target_budget:
            reason = f"السعر {listing.price:,.0f} د.ك أعلى من الميزانية {target_budget:,.0f} د.ك."
            warnings.append("السعر أعلى من الميزانية")
            add_component(breakdown, "الميزانية", 0, reason)
        else:
            reason = f"السعر {listing.price:,.0f} د.ك أقل من الميزانية {target_budget:,.0f} د.ك."
            reasons.append("السعر أقل من الميزانية")
            add_component(breakdown, "الميزانية", 8, reason)
            score += 8

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


def top_matches(
    request: PropertyRequest,
    listings: list[Listing],
    limit: int = 20,
) -> list[tuple[Listing, float, list[str], list[str], list[dict[str, Any]]]]:
    ranked = []
    for listing in listings:
        score, reasons, warnings, breakdown = score_listing(request, listing)
        if score > 0:
            ranked.append((listing, score, reasons, warnings, breakdown))
    # Sort by score, then by published date if available
    ranked.sort(key=lambda item: (item[1], item[0].published_date or ""), reverse=True)
    return ranked[:limit]
