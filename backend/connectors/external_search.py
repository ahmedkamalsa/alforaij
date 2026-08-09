from __future__ import annotations

from urllib.parse import quote_plus

from backend.models import PropertyRequest


EXTERNAL_SOURCES = [
    {
        "id": "sakan",
        "name": "Sakan",
        "url": "https://sakan.co/en",
        "site": "sakan.co",
        "status": "live_conditional",
    },
    {
        "id": "opensooq",
        "name": "السوق المفتوح الكويت",
        "url": "https://kw.opensooq.com",
        "site": "kw.opensooq.com",
        "status": "live_scored",
    },
    {
        "id": "mourjan",
        "name": "مرجان الكويت",
        "url": "https://www.mourjan.com/kw/",
        "site": "mourjan.com/kw",
        "status": "live_scored",
    },
    {
        "id": "q8aqar",
        "name": "دليل عقارات الكويت Q8Aqar",
        "url": "https://www.q8aqar.com",
        "site": "q8aqar.com",
        "status": "live_scored",
    },
    {
        "id": "waseet",
        "name": "وسيط الكويت",
        "url": "https://www.waseet.net/kw/ar",
        "site": "waseet.net/kw",
        "status": "live_scored",
    },
    {
        "id": "nabdaqar",
        "name": "نبض عقار",
        "url": "https://nabdaqar.com",
        "site": "nabdaqar.com",
        "status": "live_scored",
    },
    {
        "id": "bu3qar",
        "name": "بوعقار / بوشملان",
        "url": "https://www.bu3qar.com",
        "site": "bu3qar.com",
        "status": "live_scored",
    },
    {
        "id": "aqarat",
        "name": "Aqarat",
        "url": "https://aqarat.com",
        "site": "aqarat.com",
        "status": "live_conditional",
    },
    {
        "id": "four_sale",
        "name": "4Sale",
        "url": "https://kuwait.4sale.com/real-estate",
        "site": "kuwait.4sale.com/real-estate",
        "status": "live_conditional",
    },
]


def request_query(request: PropertyRequest) -> str:
    parts = [
        request.transaction,
        request.property_type,
        " ".join(request.areas),
        f"{request.min_area:g} متر" if request.min_area else "",
        f"{request.budget:g} د.ك" if request.budget else "",
        f"{request.rent_budget:g} د.ك" if request.rent_budget else "",
    ]
    query = " ".join(part for part in parts if part).strip()
    return query or request.raw_text


def external_search_links(request: PropertyRequest) -> list[dict[str, str]]:
    query = request_query(request)
    links: list[dict[str, str]] = []
    for source in EXTERNAL_SOURCES:
        google_query = quote_plus(f"site:{source['site']} {query}")
        if source["status"] == "live_scored":
            evidence_status = (
                "مصدر له موصل حي. يدخل في التقييم فقط إذا أعاد إعلانًا مطابقًا بسعر/مساحة/رابط واضح؛ "
                "وهذا الرابط للمراجعة اليدوية الإضافية."
            )
        elif source["status"] == "live_conditional":
            evidence_status = (
                "مصدر مفحوص آليًا بشروط. قد يظهر كمساعد فقط إذا لم يعطِ بيانات إعلان منظمة، "
                "وهذا الرابط للمراجعة اليدوية."
            )
        else:
            evidence_status = "رابط مراجعة يدوي؛ لا يدخل وحده في التقييم."
        links.append(
            {
                "id": source["id"],
                "name": source["name"],
                "status": "موصل حي + رابط مراجعة" if source["status"].startswith("live") else "رابط بحث خارجي",
                "url": f"https://www.google.com/search?q={google_query}",
                "directUrl": source["url"],
                "evidenceStatus": evidence_status,
            }
        )
    return links
