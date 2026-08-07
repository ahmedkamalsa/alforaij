from __future__ import annotations

from dataclasses import asdict

from backend.connectors.external_search import external_search_links
from backend.models import PropertyRequest, RankedListing
from backend.services.source_registry import source_registry


def ranked_to_dict(item: RankedListing) -> dict:
    from backend.services.financing_calculator import calculate_mortgage
    listing = item.listing
    financing = calculate_mortgage(listing.price) if listing.price else {}
    
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
        "listingType": getattr(listing, 'listing_type', "غير محدد"),
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
        "financing": financing,
    }


def build_report(
    request: PropertyRequest,
    items: list[RankedListing],
    source_count: int,
    external_statuses: list[dict] | None = None,
    ai_insights: dict | None = None,
) -> dict:
    top = items[0] if items else None
    scope_note = "، ".join(request.areas) if request.areas else "كل المناطق"
    summary = "لم يتم العثور على نتائج كافية داخل بيانات الفريج."
    if top:
        summary = (
            f"أفضل نتيجة مبدئية هي {top.listing.code} في {top.listing.area} "
            f"بسعر {top.listing.price_text or 'غير معلن'}، وحكم السعر: {top.valuation_label}. "
            f"درجة التوصية {int(top.recommendation_score)} من 100، والثقة {int(top.confidence * 100)}% "
            f"اعتمادًا على {len(top.comparables)} مقارنة متاحة"
            + (" داخل المنطقة المطلوبة." if request.areas else " داخل البيانات المتاحة.")
        )

    external_plan = [
        {"name": "توسيع Q8Aqar", "status": "منفذ ✓", "action": "يقرأ الآن صفحات التفاصيل نفسها لتحسين السعر والمساحة بدل الرابط فقط، مع الإبقاء على العنوان كأساس."},
        {"name": "Sakan", "status": "منفذ جزئيًا", "action": "يحاول الآن استخراج الإعلانات من الحالة المضمّنة في الصفحة عند توفرها، وإلا يبقى دليل توفر وعدد متاح."},
        {"name": "الصفقات الرسمية", "status": "منفذ ✓", "action": "تُقرأ من جدول official_transactions في Supabase وملف محلي، وتُستخدم كوسيط سوق مرجّح أعلى من الإعلانات في التقييم (أعلى مصداقية)."},
        {"name": "منصات توسعة جديدة", "status": "منفذ ✓", "action": "أُضيف Aqarat و4Sale كموصلين حيين بنفس قواعد الفلترة والدليل، ومرورهما بسجل تشغيل المصادر."},
        {"name": "مصادر مكاتب / API شريك", "status": "الخطوة التالية", "action": "ربط API أو Feed من مكاتب عقارية عند توفره، ثم تمريره بنفس فلاتر الدليل وتسجيل التشغيل."},
    ]

    if ai_insights:
        # Build a richer summary from AI insights
        analysis_heading = (
            "تحليل الخبير العقاري (ذكاء اصطناعي)"
            if ai_insights.get("analysisMethod") == "ai"
            else "تحليل محلي احترافي"
        )
        rich_summary = f"**{analysis_heading}:**\n{ai_insights.get('executive_summary', '')}\n\n"
        rich_summary += f"**الأدلة والمصادر المستعملة:**\n{ai_insights.get('sources_evidence', '')}\n\n"
        rich_summary += f"**اقتراحات للعميل:**\n{ai_insights.get('suggestions', '')}"
        summary = rich_summary
        
        # Override plan if AI provided missing data
        if "missing_data" in ai_insights and ai_insights["missing_data"]:
            external_plan.insert(0, {
                "name": "نواقص البيانات المكتشفة (AI)",
                "status": "مطلوب لتأكيد التقييم",
                "action": ai_insights["missing_data"]
            })

    return {
        "request": asdict(request),
        "aiInsights": ai_insights or {},
        "searchScope": {
            "areas": request.areas,
            "note": (
                f"تم حصر البحث والتقييم في المناطق المطلوبة فقط: {scope_note}"
                if request.areas
                else "لم يحدد الطلب منطقة، فشمل البحث كل المناطق المتاحة."
            ),
        },
        "analysisMethod": (ai_insights or {}).get("analysisMethod", "none"),
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
        "externalSourcePlan": external_plan,
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
