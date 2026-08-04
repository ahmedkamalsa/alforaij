from __future__ import annotations

from dataclasses import asdict

from backend.connectors.external_search import external_search_links
from backend.models import PropertyRequest, RankedListing
from backend.services.source_registry import source_registry


def ranked_to_dict(item: RankedListing) -> dict:
    listing = item.listing
    return {
        "code": listing.code,
        "source": listing.source,
        "transaction": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "propertyType": listing.property_type,
        "detailClass": listing.detail_class,
        "price": listing.price,
        "priceText": listing.price_text,
        "space": listing.space,
        "listingMode": listing.listing_mode,
        "summary": listing.summary,
        "features": listing.features,
        "publishedDate": listing.published_date,
        "originalUrl": listing.original_url,
        "matchScore": item.match_score,
        "recommendationScore": item.recommendation_score,
        "valuationLabel": item.valuation_label,
        "valuationReason": item.valuation_reason,
        "confidence": item.confidence,
        "dealScore": item.deal_score,
        "marketMedian": item.market_median,
        "priceRatio": item.price_ratio,
        "matchBreakdown": item.match_breakdown,
        "recommendationBreakdown": item.recommendation_breakdown,
        "numberSources": item.number_sources,
        "reasons": item.reasons,
        "warnings": item.warnings,
        "comparables": item.comparables,
    }


def build_report(
    request: PropertyRequest,
    items: list[RankedListing],
    source_count: int,
    external_statuses: list[dict] | None = None,
) -> dict:
    top = items[0] if items else None
    summary = "لم يتم العثور على نتائج كافية داخل بيانات الفريج."
    if top:
        summary = (
            f"أفضل نتيجة مبدئية هي {top.listing.code} في {top.listing.area} "
            f"بسعر {top.listing.price_text or 'غير معلن'}، وحكم السعر: {top.valuation_label}. "
            f"درجة التوصية {int(top.recommendation_score)} من 100، والثقة {int(top.confidence * 100)}% "
            f"اعتمادًا على {len(top.comparables)} مقارنة متاحة."
        )
    return {
        "request": asdict(request),
        "rankingMethod": {
            "title": "طريقة ترتيب النتائج",
            "note": "الترتيب ليس حسب الثقة وحدها. درجة التوصية تجمع مطابقة الطلب، جاذبية السعر مقابل وسيط المقارنات، درجة الثقة، وخصم البيانات الناقصة.",
            "weights": {
                "matchScore": "62%",
                "dealScore": "28%",
                "confidence": "10%",
                "missingDataPenalty": "خصم حتى 12 نقطة",
            },
            "thresholds": [
                "لقطة ممتازة: السعر لا يتجاوز 82% من وسيط المقارنات.",
                "أقل من السوق: السعر لا يتجاوز 92% من وسيط المقارنات.",
                "سعر عادل: بين 92% و108% من وسيط المقارنات.",
                "أعلى قليلاً: حتى 118%.",
                "غالي: حتى 135%.",
                "مبالغ فيه: أعلى من 135%.",
            ],
        },
        "sourceStatus": [
            {
                "name": "الفريج",
                "status": "success",
                "records": source_count,
                "note": "تم البحث في نسخة بيانات الفريج المحلية المستخرجة من لوحة alforaijboard.",
            },
            *[
                {
                    "name": status.get("name", "مصدر خارجي"),
                    "status": status.get("status", "unknown"),
                    "records": status.get("records", 0),
                    "candidates": status.get("candidates", status.get("records", 0)),
                    "responseMs": status.get("responseMs"),
                    "url": status.get("url"),
                    "note": status.get("note", ""),
                    "availableCount": status.get("availableCount"),
                }
                for status in (external_statuses or [])
            ],
        ],
        "sourceRegistry": source_registry(),
        "externalSourcePlan": [
            {"name": "توسيع Q8Aqar", "status": "الخطوة التالية", "action": "قراءة صفحات التفاصيل نفسها لاستخراج السعر والمساحة بدل رابط فقط عند توفرها."},
            {"name": "Sakan", "status": "يحتاج endpoint أو API", "action": "لا يدخل في التقييم حتى نحصل على بيانات إعلان تفصيلية لا مجرد عداد صفحة."},
            {"name": "صفقات رسمية", "status": "أعلى أولوية للتقييم", "action": "استيراد صفقات وزارة العدل/مصدر رسمي إلى Supabase واستخدامها كوسيط سوق مرجح."},
        ],
        "externalSearchLinks": external_search_links(request),
        "summary": summary,
        "results": [ranked_to_dict(item) for item in items],
        "limitations": [
            "التقييم استرشادي وليس تقييمًا رسميًا.",
            "النتائج تعتمد على البيانات المتاحة محليًا وقت التشغيل.",
            "العقار قد لا يكون متاحًا فعليًا حتى لو ظهر في البيانات.",
            "نتائج المواقع الخارجية تعتمد على ما تسمح الصفحة العامة بقراءته وقت البحث.",
        ],
    }
