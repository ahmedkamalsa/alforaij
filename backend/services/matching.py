from __future__ import annotations

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import normalize_text


def score_listing(request: PropertyRequest, listing: Listing) -> tuple[float, list[str], list[str]]:
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    if request.transaction:
        if request.transaction == "مطلوب للشراء" and listing.transaction == "للبيع":
            score += 28
            reasons.append("طلب شراء يقابله عرض بيع مناسب")
        elif request.transaction == "مطلوب للإيجار" and listing.transaction == "للإيجار":
            score += 28
            reasons.append("طلب إيجار يقابله عرض إيجار مناسب")
        elif request.transaction in {"مطلوب للشراء", "مطلوب للإيجار"} and listing.transaction == request.transaction:
            score += 6
            warnings.append("هذه نتيجة طلب مشابه وليست عرضًا مباشرًا")
        elif request.transaction in listing.transaction or listing.transaction in request.transaction:
            score += 25
            reasons.append("نوع المعاملة مطابق")

    if request.property_type and request.property_type in (listing.property_type + " " + listing.detail_class):
        score += 18
        reasons.append("نوع العقار قريب من الطلب")

    if request.areas:
        normalized_area = normalize_text(listing.area)
        if any(normalize_text(area) in normalized_area for area in request.areas):
            score += 28
            reasons.append("المنطقة مطابقة")
        elif listing.governorate and any(normalize_text(area) in normalize_text(listing.governorate) for area in request.areas):
            score += 8
            reasons.append("المحافظة قريبة من الطلب")
    else:
        score += 5

    if request.min_area or request.max_area:
        if listing.space:
            min_area = request.min_area or 0
            max_area = request.max_area or 10**9
            if min_area <= listing.space <= max_area:
                score += 15
                reasons.append("المساحة ضمن النطاق المطلوب")
            else:
                warnings.append("المساحة خارج النطاق المطلوب")
        else:
            warnings.append("لا توجد مساحة معلنة للمقارنة")

    target_budget = request.rent_budget or request.budget
    if target_budget and listing.price:
        delta = abs(listing.price - target_budget) / max(target_budget, 1)
        if delta <= 0.08:
            score += 12
            reasons.append("السعر قريب جدًا من الميزانية")
        elif delta <= 0.2:
            score += 7
            reasons.append("السعر قريب من الميزانية")
        elif listing.price > target_budget:
            warnings.append("السعر أعلى من الميزانية")

    searchable = normalize_text(" ".join([listing.summary, listing.features, listing.detail_class]))
    for feature in request.features + request.condition:
        if normalize_text(feature) in searchable:
            score += 4
            reasons.append(f"يوجد عامل مطلوب: {feature}")

    if not listing.price:
        warnings.append("السعر غير معلن")
    if not listing.space:
        warnings.append("المساحة غير معلنة")

    return min(score, 100), reasons, warnings


def top_matches(request: PropertyRequest, listings: list[Listing], limit: int = 20) -> list[tuple[Listing, float, list[str], list[str]]]:
    ranked = []
    for listing in listings:
        score, reasons, warnings = score_listing(request, listing)
        if score > 0:
            ranked.append((listing, score, reasons, warnings))
    ranked.sort(key=lambda item: (item[1], item[0].published_date), reverse=True)
    return ranked[:limit]
