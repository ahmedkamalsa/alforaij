from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import asdict
from statistics import median

logger = logging.getLogger(__name__)

from backend.config import AGENT_ROUTER_API_KEY, AGENT_ROUTER_API_URL
from backend.models import PropertyRequest, RankedListing


AI_TIMEOUT_SECONDS = 12  # مهلة قصيرة حتى لا يعلق التحليل عند تعذر الاتصال


def _call_ai_analysis(
    request: PropertyRequest,
    top_listings: list[RankedListing],
    external_statuses: list[dict],
) -> dict | None:
    """استدعاء نموذج الذكاء الاصطناعي الخارجي. يعيد None عند غياب المفتاح أو فشل الاتصال."""
    if not AGENT_ROUTER_API_KEY:
        return None

    # Prepare data for LLM
    request_data = asdict(request)
    listings_data = []
    for item in top_listings[:10]:  # Limit to top 10 to save context window
        listings_data.append({
            "code": item.listing.code,
            "source": item.listing.source,
            "governorate": item.listing.governorate,
            "area": item.listing.area,
            "property_type": item.listing.property_type,
            "price_text": item.listing.price_text,
            "space": item.listing.space,
            "summary": item.listing.summary,
            "features": item.listing.features,
            "valuation_label": item.valuation_label,
            "valuation_reason": item.valuation_reason,
        })

    sources_data = [{"name": s.get("name"), "status": s.get("status"), "records": s.get("records")} for s in external_statuses]

    prompt = f"""أنت مستشار عقاري كويتي محترف ومحلل بيانات خبير.
قم بتحليل طلب العميل والعقارات المطابقة التي تم العثور عليها.
رد بصيغة JSON فقط، بدون أي نصوص إضافية، بحيث يحتوي الـ JSON على المفاتيح التالية:
1. "executive_summary": خلاصة احترافية تلخص وضع السوق والأسعار المتاحة بناءً على طلب العميل.
2. "sources_evidence": فقرة تشرح أي المصادر (مثل Q8Aqar, Sakan, Alforaij، أو غيرها) قدمت أفضل بيانات وأدلة للتقييم الحالي ولماذا.
3. "missing_data": ما هي مصادر البيانات المهمة أو المعلومات المفقودة التي كانت ستجعل التقييم أكثر دقة (مثل: صفقات وزارة العدل الرسمية لهذه القطعة المحددة).
4. "suggestions": اقتراحات مهنية للعميل (مثل: زيادة الميزانية، تغيير المنطقة المستهدفة، أو التركيز على زاوية معينة).

طلب العميل:
{json.dumps(request_data, ensure_ascii=False, indent=2)}

العقارات المطابقة (الأدلة):
{json.dumps(listings_data, ensure_ascii=False, indent=2)}

حالة المصادر:
{json.dumps(sources_data, ensure_ascii=False, indent=2)}
"""

    payload = {
        "model": "gpt-4o-mini",  # Standard model
        "messages": [
            {"role": "system", "content": "You are a professional real estate consultant. Always respond in valid JSON format."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AGENT_ROUTER_API_KEY}",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(AGENT_ROUTER_API_URL, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if isinstance(parsed, dict) and parsed.get("executive_summary"):
                    return parsed
    except Exception as e:
        logger.warning("AI evaluator call failed: %s", e)
    return None


def fallback_professional_analysis(
    request: PropertyRequest,
    top_listings: list[RankedListing],
    external_statuses: list[dict],
) -> dict:
    """تحليل احترافي محلي (بدون API) يضمن نتيجة مهنية دائمًا حتى عند غياب المفتاح أو فشل الاتصال."""
    top = top_listings[:5]
    areas = "، ".join(dict.fromkeys(item.listing.area for item in top if item.listing.area)) or "غير محددة"

    # هل النتائج إيجار؟ الصياغة تختلف: إيجار شهري مقابل وسيط إيجارات (وليست أسعار شراء).
    # الملخص يخص أفضل نتيجة (top[0]) تحديدًا — نشتق الوضع من نفس النتيجة التي تُوصف.
    rental_mode = bool(
        top_listings
        and (top_listings[0].number_sources or {}).get("rental", {}).get("value") is True
    )
    price_word = "الإيجار" if rental_mode else "السعر"

    summary_parts: list[str] = []
    if top:
        best = top[0]
        price_display = best.listing.price_text or "غير معلن"
        summary_parts.append(
            f"أفضل توصية حسب البيانات المتاحة هي {best.listing.code} في {best.listing.area or areas} "
            f"بـ{price_word} {price_display}، وحكم التقييم «{best.valuation_label}» بثقة {int(best.confidence * 100)}%."
        )
    else:
        summary_parts.append("لم تتوفر عروض مطابقة كافية داخل البيانات الحالية لتكوين توصية موثوقة.")

    medians = [item.market_median for item in top if item.market_median]
    if medians:
        representative = median(medians)
        summary_parts.append(
            f"وسيط {'الإيجارات الشهرية' if rental_mode else 'أسعار المقارنات'} المتاح يقارب {representative:,.0f} د.ك."
        )
    summary_parts.append("التقييم استرشادي مبني على العروض المتاحة وقت البحث وليس تقييمًا رسميًا.")

    evidence_parts: list[str] = []
    working = [s for s in external_statuses if s.get("status") in ("success", "connected") or s.get("records")]
    if working:
        evidence_parts.append(
            "المصادر الحية التي أسهمت بنتائج: " + "، ".join(str(s.get("name")) for s in working) + "."
        )
    else:
        evidence_parts.append(
            "لم تسهم المصادر الخارجية بنتائج مطابقة وقت البحث؛ اعتمد التحليل على بيانات الفريج المحلية."
        )
    failed = [s for s in external_statuses if s.get("status") == "failed"]
    if failed:
        evidence_parts.append(
            "تعذر الوصول إلى: " + "، ".join(str(s.get("name")) for s in failed) + " (قد يكون حظرًا مؤقتًا أو تغييرًا في بنية الموقع)."
        )

    missing_parts = [
        "صفقات وزارة العدل الرسمية لنفس المنطقة ونوع العقار",
        "مساحات ومواصفات دقيقة لجميع العروض المقارنة",
        "سعر المتر الرسمي للمنطقة عند توفر قاعدة بيانات موثوقة",
    ]
    if not top:
        missing_parts.append("عروض مطابقة إضافية (توسيع نطاق المناطق أو تعديل الفلاتر)")

    suggestions_parts = [
        "التحقق من الصفقات الرسمية الأحدث قبل اتخاذ قرار الشراء" if not rental_mode else "التحقق من عروض الإيجار الأحدث في المنطقة قبل اتخاذ القرار",
        "معاينة العقار فعليًا والتأكد من الواجهة والمساحة والموقع",
        f"التفاوض على {'الإيجار' if rental_mode else 'السعر'} استنادًا إلى وسيط المقارنات المعروض في كل نتيجة",
    ]
    if request.budget:
        suggestions_parts.append("متابعة الإعلانات الجديدة ضمن الميزانية المحددة في التقرير")

    return {
        "executive_summary": " ".join(summary_parts),
        "sources_evidence": " ".join(evidence_parts),
        "missing_data": "؛ ".join(missing_parts),
        "suggestions": "؛ ".join(suggestions_parts),
    }


def generate_professional_analysis(
    request: PropertyRequest,
    top_listings: list[RankedListing],
    external_statuses: list[dict],
) -> dict:
    """تحليل احترافي: يحاول AI أولاً، ويعود تلقائيًا لتحليل محلي احترافي عند غياب المفتاح أو فشل الاتصال."""
    ai = _call_ai_analysis(request, top_listings, external_statuses)
    if ai:
        ai["analysisMethod"] = "ai"
        return ai
    fallback = fallback_professional_analysis(request, top_listings, external_statuses)
    fallback["analysisMethod"] = "local"
    return fallback
