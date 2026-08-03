from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import extract_area_range, normalize_text


USER_AGENT = "Mozilla/5.0 (compatible; AlforaijResearchAssistant/1.0)"
TIMEOUT = 8

AREA_SLUGS = {
    "المطلاع": {"q8aqar": "mutlae", "sakan_governorate": "Jahra", "sakan_city": "almutlaa"},
    "ابو فطيرة": {"q8aqar": "abu-fatira", "sakan_governorate": "mubarak-al-kabir", "sakan_city": "abu-fatira"},
    "أبو فطيرة": {"q8aqar": "abu-fatira", "sakan_governorate": "mubarak-al-kabir", "sakan_city": "abu-fatira"},
    "السالمية": {"q8aqar": "salmiya", "sakan_governorate": "hawally", "sakan_city": "salmiya"},
    "الجابرية": {"q8aqar": "jabriya", "sakan_governorate": "hawally", "sakan_city": "jabriya"},
    "الرميثية": {"q8aqar": "rumaithiya", "sakan_governorate": "hawally", "sakan_city": "rumaithiya"},
    "صباح السالم": {"q8aqar": "sabah-al-salem", "sakan_governorate": "mubarak-al-kabir", "sakan_city": "sabah-al-salem"},
    "الفردوس": {"q8aqar": "ferdous", "sakan_governorate": "Farwaniya", "sakan_city": "al-firdous"},
    "خيطان": {"q8aqar": "khaitan", "sakan_governorate": "Farwaniya", "sakan_city": "khaitan"},
    "حولي": {"q8aqar": "hawalli", "sakan_governorate": "hawally", "sakan_city": "hawally"},
}

PROPERTY_SLUGS = {
    "بيت": {"q8aqar": "houses", "sakan": "house", "mourjan": "villas-and-houses"},
    "شقة": {"q8aqar": "apartments", "sakan": "apartment", "mourjan": "apartments"},
    "أرض": {"q8aqar": "lands", "sakan": "land", "mourjan": "lands"},
    "عمارة": {"q8aqar": "buildings", "sakan": "building", "mourjan": "buildings"},
}

KNOWN_AREAS = list(AREA_SLUGS.keys()) + [
    "الدوحة",
    "مشرف",
    "الجهراء",
    "جابر الأحمد",
    "جابر الاحمد",
    "الأندلس",
    "الاندلس",
    "سلوى",
    "صباح الأحمد",
    "صباح الاحمد",
]


def fetch_url(url: str) -> tuple[str, int, float, str | None]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="replace")
            return body, response.status, round((time.perf_counter() - started) * 1000, 1), None
    except Exception as exc:
        return "", 0, round((time.perf_counter() - started) * 1000, 1), str(exc)


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def detect_area(text: str) -> str:
    normalized = normalize_text(text)
    for area in KNOWN_AREAS:
        if normalize_text(area) in normalized:
            return area
    return ""


def detect_property_type(text: str, fallback: str = "") -> str:
    normalized = normalize_text(text)
    if any(word in normalized for word in ("عماره", "بنايه", "استثماري")):
        return "عمارة"
    if any(word in normalized for word in ("ارض", "قسيمه")):
        return "أرض"
    if any(word in normalized for word in ("شقه", "دوبلكس")):
        return "شقة"
    if any(word in normalized for word in ("بيت", "فيلا", "منزل", "هدام")):
        return "بيت"
    return fallback or "عقارات"


def parse_price(text: str, fallback: Any = None) -> float | None:
    normalized = normalize_text(text).replace(",", "")
    patterns = [
        r"(?:السعر|سعر البيع|المطلوب|بياع)[:\s]*([0-9]+(?:\.[0-9]+)?)\s*(مليون|الف|ألف|دينار|د\.ك|دك)?",
        r"([0-9]+(?:\.[0-9]+)?)\s*(مليون|الف|ألف)\s*(?:دينار|د\.ك|دك)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        value = float(match.group(1))
        unit = match.group(2) or ""
        if "مليون" in unit:
            value *= 1_000_000
        elif "الف" in unit or "ألف" in unit:
            value *= 1000
        return value
    if fallback not in (None, ""):
        try:
            value = float(str(fallback).replace(",", ""))
        except ValueError:
            return None
        if value < 10_000 and any(word in normalized for word in ("الف", "ألف")):
            value *= 1000
        return value
    return None


def parse_space(text: str) -> float | None:
    min_area, max_area, _excluded = extract_area_range(text)
    return min_area if min_area == max_area else min_area


def transaction_from_request(request: PropertyRequest) -> str:
    if request.transaction in {"للإيجار", "مطلوب للإيجار"}:
        return "للإيجار"
    return "للبيع"


def property_slug(request: PropertyRequest, source: str) -> str:
    return PROPERTY_SLUGS.get(request.property_type, PROPERTY_SLUGS["بيت"]).get(source, "")


def first_area_meta(request: PropertyRequest) -> dict[str, str]:
    for area in request.areas:
        if area in AREA_SLUGS:
            return AREA_SLUGS[area]
    return AREA_SLUGS.get("المطلاع", {})


def listing_from_text(
    *,
    source: str,
    code: str,
    url: str,
    title: str,
    description: str,
    price: float | None,
    transaction: str,
    fallback_type: str,
) -> Listing:
    full_text = f"{title} {description}"
    area = detect_area(full_text)
    space = parse_space(full_text)
    property_type = detect_property_type(full_text, fallback_type)
    price_value = parse_price(full_text, price)
    inferred_thousands = False
    if (
        transaction == "للبيع"
        and property_type in {"بيت", "أرض", "عمارة"}
        and price_value
        and price_value < 10_000
    ):
        price_value *= 1000
        inferred_thousands = True
    return Listing(
        code=code,
        transaction=transaction,
        governorate="",
        area=area,
        property_type=property_type,
        detail_class="مصدر خارجي",
        price=price_value,
        price_text=f"{price_value:,.0f} د.ك" if price_value else "غير معلن",
        space=space,
        listing_mode="خارجي مباشر",
        summary=clean_text(description or title)[:420],
        features=clean_text(description or title),
        published_date="",
        original_url=url,
        source=source,
        raw={
            "priceSource": (
                f"استخراج مباشر من صفحة {source}، والرقم عومل كألف د.ك لأنه بيع {property_type} والرقم أقل من 10,000"
                if inferred_thousands
                else f"استخراج مباشر من صفحة {source}"
            ),
            "spaceSource": "مذكورة صراحة في نص المصدر الخارجي" if space else "غير مذكورة",
            "external": True,
        },
    )


def search_opensooq(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    path = "property/property-for-rent" if transaction_from_request(request) == "للإيجار" else "property/property-for-sale"
    url = f"https://kw.opensooq.com/en/{path}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    if body:
        for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            graphs = data.get("@graph", []) if isinstance(data, dict) else []
            for graph in graphs:
                if graph.get("@type") != "ItemList":
                    continue
                for element in graph.get("itemListElement", []):
                    product = element.get("item", {})
                    if product.get("@type") != "Product":
                        continue
                    offer = product.get("offers", {})
                    code = "OS-" + str(product.get("url", "").rstrip("/").split("/")[-1])
                    listings.append(
                        listing_from_text(
                            source="OpenSooq",
                            code=code,
                            url=product.get("url", ""),
                            title=product.get("name", ""),
                            description=product.get("description", ""),
                            price=offer.get("price"),
                            transaction=transaction_from_request(request),
                            fallback_type=request.property_type,
                        )
                    )
    return listings[:30], {
        "name": "OpenSooq",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "responseMs": ms,
        "url": url,
        "note": error or "تم استخراج نتائج منظمة من JSON-LD العام في الصفحة.",
    }


def search_mourjan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    mode = "rental" if transaction_from_request(request) == "للإيجار" else "for-sale"
    query = urllib.parse.urlencode({"q": " ".join(request.areas) or request.raw_text})
    url = f"https://www.mourjan.com/kw/kuwait/properties/{mode}/?{query}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    ad_pattern = re.compile(
        r'<div class="ad[^"]*"[^>]*>.*?<div class=widget id=([0-9]+)>.*?<a class=link href=([^>]+)>.*?<div dir=auto class="content ar">(.*?)</div>',
        re.S,
    )
    for code, href, description in ad_pattern.findall(body):
        url_abs = urllib.parse.urljoin("https://www.mourjan.com", href)
        listings.append(
            listing_from_text(
                source="Mourjan",
                code=f"MJ-{code}",
                url=url_abs,
                title="",
                description=description,
                price=None,
                transaction=transaction_from_request(request),
                fallback_type=request.property_type,
            )
        )
    return listings[:30], {
        "name": "Mourjan",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "responseMs": ms,
        "url": url,
        "note": error or "تم استخراج كروت إعلانات عامة من HTML الصفحة.",
    }


def search_q8aqar(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    mode = "forrent" if transaction_from_request(request) == "للإيجار" else "forsale"
    area_meta = first_area_meta(request)
    part = property_slug(request, "q8aqar")
    area_slug = area_meta.get("q8aqar", "")
    url = f"https://q8aqar.com/{mode}/{part}/{area_slug}/" if area_slug else f"https://q8aqar.com/{mode}/{part}/"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    for href, title in re.findall(r'<a href="(https://q8aqar\.com/details/realestate/[0-9]+/)">(.*?)</a>', body, re.S):
        title_clean = clean_text(title)
        code = "Q8-" + href.rstrip("/").split("/")[-1]
        listings.append(
            listing_from_text(
                source="Q8Aqar",
                code=code,
                url=href,
                title=title_clean,
                description=title_clean,
                price=None,
                transaction=transaction_from_request(request),
                fallback_type=request.property_type,
            )
        )
    return listings[:20], {
        "name": "Q8Aqar",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "responseMs": ms,
        "url": url,
        "note": error or "تم استخراج روابط تفاصيل معلنة من صفحة المنطقة العامة.",
    }


def check_sakan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    area_meta = first_area_meta(request)
    part = property_slug(request, "sakan")
    buy_or_rent = "rent" if transaction_from_request(request) == "للإيجار" else "buy"
    gov = area_meta.get("sakan_governorate", "Jahra")
    city = area_meta.get("sakan_city", "")
    url = f"https://sakan.co/en/{buy_or_rent}/{part}/{gov}/{city}".rstrip("/")
    body, status, ms, error = fetch_url(url)
    count_match = re.search(r"([0-9,]+)\s+available", body, re.I)
    count = int(count_match.group(1).replace(",", "")) if count_match else 0
    note = "تم الوصول للصفحة، لكن الإعلانات التفصيلية لا تظهر كبيانات منظمة في HTML العام."
    return [], {
        "name": "Sakan",
        "status": "page_reachable" if body else "failed",
        "records": 0,
        "availableCount": count,
        "responseMs": ms,
        "url": url,
        "note": error or note,
    }


def search_external_sources(request: PropertyRequest) -> tuple[list[Listing], list[dict[str, Any]]]:
    listings: list[Listing] = []
    statuses: list[dict[str, Any]] = []
    for searcher in (search_opensooq, search_mourjan, search_q8aqar, check_sakan):
        source_listings, status = searcher(request)
        listings.extend(source_listings)
        statuses.append(status)
    return listings, statuses
