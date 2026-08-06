from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import asdict

from backend.config import AGENT_ROUTER_API_KEY, AGENT_ROUTER_API_URL
from backend.models import PropertyRequest, RankedListing

def generate_professional_analysis(
    request: PropertyRequest,
    top_listings: list[RankedListing],
    external_statuses: list[dict]
) -> dict | None:
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
        "model": "gpt-4o-mini", # Standard model
        "messages": [
            {"role": "system", "content": "You are a professional real estate consultant. Always respond in valid JSON format."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AGENT_ROUTER_API_KEY}"
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(AGENT_ROUTER_API_URL, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)
    except Exception as e:
        print(f"AI Evaluator Error: {e}")
        return None
    
    return None
