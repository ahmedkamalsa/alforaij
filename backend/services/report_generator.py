from __future__ import annotations

from dataclasses import asdict

from backend.models import PropertyRequest, RankedListing


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
        "valuationLabel": item.valuation_label,
        "confidence": item.confidence,
        "reasons": item.reasons,
        "warnings": item.warnings,
        "comparables": item.comparables,
    }


def build_report(request: PropertyRequest, items: list[RankedListing], source_count: int) -> dict:
    top = items[0] if items else None
    summary = "لم يتم العثور على نتائج كافية داخل بيانات الفريج."
    if top:
        summary = (
            f"أفضل نتيجة مبدئية هي {top.listing.code} في {top.listing.area} "
            f"بسعر {top.listing.price_text or 'غير معلن'}، وتصنيف السعر: {top.valuation_label}. "
            f"درجة الثقة {int(top.confidence * 100)}% لأنها مبنية على {len(top.comparables)} مقارنة متاحة."
        )
    return {
        "request": asdict(request),
        "sourceStatus": [
            {
                "name": "الفريج",
                "status": "success",
                "records": source_count,
                "note": "تم البحث في نسخة بيانات الفريج المحلية المستخرجة من لوحة alforaijboard.",
            },
            {
                "name": "مصادر خارجية",
                "status": "not_configured",
                "records": 0,
                "note": "جاهزة كهيكل Connectors، لكنها تحتاج APIs أو موافقة على البحث الخارجي المنظم.",
            },
        ],
        "summary": summary,
        "results": [ranked_to_dict(item) for item in items],
        "limitations": [
            "التقييم استرشادي وليس تقييمًا رسميًا.",
            "النتائج تعتمد على البيانات المتاحة محليًا وقت التشغيل.",
            "العقار قد لا يكون متاحًا فعليًا حتى لو ظهر في البيانات.",
        ],
    }

