from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import asdict
from statistics import median

logger = logging.getLogger(__name__)

from backend.config import AGENT_ROUTER_API_KEY, AGENT_ROUTER_API_URL
from backend.models import PropertyRequest, RankedListing
from backend.services.ai_router import ai_chat, ai_chat_json, get_last_ai_attempts


AI_TIMEOUT_SECONDS = 12  # مهلة قصيرة حتى لا يعلق التحليل عند تعذر الاتصال


def _call_ai_analysis(
    request: PropertyRequest,
    top_listings: list[RankedListing],
    external_statuses: list[dict],
) -> dict | None:
    """استدعاء نموذج الذكاء الاصطناعي عبر AI Router مع Fallback تلقائي.

    يجرب: Ollama → Gemini → OpenRouter → AgentRouter
    يعيد None فقط عند فشل كل المزوّدين.
    """
    # Prepare data for LLM
    request_data = asdict(request)
    listings_data = []
    for item in top_listings[:10]:
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

    system_prompt = "You are a professional real estate consultant in Kuwait. Always respond in valid JSON format."
    user_prompt = f"""أنت مستشار عقاري كويتي محترف ومحلل بيانات خبير.
قم بتحليل طلب العميل والعقارات المطابقة التي تم العثور عليها.
رد بصيغة JSON فقط، بحيث يحتوي على المفاتيح التالية:
1. "executive_summary": خلاصة احترافية عن وضع السوق والأسعار.
2. "sources_evidence": أي المصادر قدمت أفضل البيانات ولماذا.
3. "missing_data": المعلومات المفقودة لتحسين الدقة.
4. "suggestions": اقتراحات مهنية للعميل.

طلب العميل:
{json.dumps(request_data, ensure_ascii=False, indent=2)}

العقارات المطابقة:
{json.dumps(listings_data, ensure_ascii=False, indent=2)}

حالة المصادر:
{json.dumps(sources_data, ensure_ascii=False, indent=2)}
"""

    try:
        result = ai_chat_json(system_prompt, user_prompt, temperature=0.4)
        if result and result.get("parsed"):
            parsed = result["parsed"]
            if isinstance(parsed, dict) and parsed.get("executive_summary"):
                parsed["_ai_provider"] = result.get("provider", "unknown")
                parsed["_ai_model"] = result.get("model", "unknown")
                parsed["_ai_attempts"] = result.get("attempts") or []
                return parsed
    except Exception as e:
        logger.warning("AI evaluator call via router failed: %s", e)
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
    fallback["_ai_provider"] = "local"
    fallback["_ai_model"] = "deterministic-fallback"
    fallback["_ai_attempts"] = get_last_ai_attempts()
    return fallback
