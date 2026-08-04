from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import KNOWN_AREAS as REQUEST_KNOWN_AREAS
from backend.services.request_parser import extract_area_range, normalize_text, text_has_area


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
    "بنيد القار": {"q8aqar": "bnaid-al-qar", "sakan_governorate": "al-asimah", "sakan_city": "bnaid-al-qar"},
}

PROPERTY_SLUGS = {
    "بيت": {"q8aqar": "houses", "sakan": "house", "mourjan": "villas-and-houses"},
    "شقة": {"q8aqar": "apartments", "sakan": "apartment", "mourjan": "apartments"},
    "أرض": {"q8aqar": "lands", "sakan": "land", "mourjan": "lands"},
    "عمارة": {"q8aqar": "buildings", "sakan": "building", "mourjan": "buildings"},
}

KNOWN_AREAS = list(dict.fromkeys(list(AREA_SLUGS.keys()) + REQUEST_KNOWN_AREAS + [
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
]))


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
    for area in KNOWN_AREAS:
        if text_has_area(area, text):
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
        fallback_text = str(fallback)
        match = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)", fallback_text)
        if not match:
            return None
        value = float(match.group(1).replace(",", ""))
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


def detect_transaction(text: str, fallback: str) -> str:
    normalized = normalize_text(text)
    if "للايجار" in normalized or "للإيجار" in text:
        return "للإيجار"
    if "للبيع" in normalized or "بيع" in normalized:
        return "للبيع"
    return fallback


def property_slug(request: PropertyRequest, source: str) -> str:
    return PROPERTY_SLUGS.get(request.property_type, PROPERTY_SLUGS["بيت"]).get(source, "")


def first_area_meta(request: PropertyRequest) -> dict[str, str]:
    for area in request.areas:
        if area in AREA_SLUGS:
            return AREA_SLUGS[area]
    return {}


def request_matches_listing(request: PropertyRequest, listing: Listing) -> bool:
    expected_transaction = transaction_from_request(request)
    if listing.transaction and listing.transaction != expected_transaction:
        return False
    if request.property_type and request.property_type not in (listing.property_type + " " + listing.detail_class):
        return False
    if request.areas:
        searchable = " ".join([listing.area, listing.governorate, listing.summary, listing.features])
        if not any(text_has_area(area, searchable) for area in request.areas):
            return False
    return True


def mourjan_type_from_href(href: str, fallback: str) -> str:
    lowered = href.lower()
    if "/apartments/" in lowered:
        return "شقة"
    if "/buildings/" in lowered:
        return "عمارة"
    if "/lands/" in lowered:
        return "أرض"
    if "/villas-and-houses/" in lowered or "/houses/" in lowered:
        return "بيت"
    return fallback


def mourjan_transaction_from_href(href: str, fallback: str) -> str:
    lowered = href.lower()
    if "/rental/" in lowered or "/for-rent/" in lowered:
        return "للإيجار"
    if "/for-sale/" in lowered:
        return "للبيع"
    return fallback


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


def walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk_dicts(child))
    return found


def opensooq_type_from_item(item: dict[str, Any], fallback: str) -> str:
    code = " ".join(str(item.get(key, "")) for key in ("cat2_code", "cat3_code", "title"))
    normalized = code.lower()
    if "apartment" in normalized or text_has_area("شقة", code):
        return "شقة"
    if "building" in normalized:
        return "عمارة"
    if "land" in normalized:
        return "أرض"
    if "house" in normalized or "villa" in normalized:
        return "بيت"
    return fallback


def opensooq_transaction_from_item(item: dict[str, Any], fallback: str) -> str:
    code = " ".join(str(item.get(key, "")) for key in ("cat1_code", "cat2_code", "title", "masked_description"))
    normalized = code.lower()
    if "rent" in normalized or "للايجار" in normalize_text(code) or "للإيجار" in code:
        return "للإيجار"
    if "sale" in normalized or "للبيع" in normalize_text(code):
        return "للبيع"
    return fallback


def search_opensooq(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    if request.raw_text.strip():
        url = f"https://kw.opensooq.com/en/find?{urllib.parse.urlencode({'term': request.raw_text})}"
    else:
        path = "property/property-for-rent" if transaction_from_request(request) == "للإيجار" else "property/property-for-sale"
        url = f"https://kw.opensooq.com/en/{path}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0
    if body:
        next_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', body, re.S)
        if next_match:
            try:
                next_data = json.loads(next_match.group(1))
            except json.JSONDecodeError:
                next_data = {}
            seen_ids: set[str] = set()
            for item in walk_dicts(next_data):
                if "title" not in item or "post_url" not in item:
                    continue
                cat1 = str(item.get("cat1_code", ""))
                if cat1 and "RealEstate" not in cat1:
                    continue
                candidates += 1
                code = "OS-" + str(item.get("id") or item.get("post_url", "").rstrip("/").split("/")[-1])
                if code in seen_ids:
                    continue
                seen_ids.add(code)
                description = " ".join(
                    str(item.get(key, ""))
                    for key in ("masked_description", "description", "nhood_label", "nhood_reporting", "city_label")
                    if item.get(key)
                )
                listing = listing_from_text(
                    source="OpenSooq",
                    code=code,
                    url=urllib.parse.urljoin("https://kw.opensooq.com", str(item.get("post_url", ""))),
                    title=str(item.get("title", "")),
                    description=description,
                    price=item.get("price_amount") or item.get("price"),
                    transaction=opensooq_transaction_from_item(item, transaction_from_request(request)),
                    fallback_type=opensooq_type_from_item(item, request.property_type),
                )
                if request_matches_listing(request, listing):
                    listings.append(listing)
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
                    candidates += 1
                    offer = product.get("offers", {})
                    code = "OS-" + str(product.get("url", "").rstrip("/").split("/")[-1])
                    listing = listing_from_text(
                        source="OpenSooq",
                        code=code,
                        url=product.get("url", ""),
                        title=product.get("name", ""),
                        description=product.get("description", ""),
                        price=offer.get("price"),
                        transaction=transaction_from_request(request),
                        fallback_type=request.property_type,
                    )
                    if request_matches_listing(request, listing):
                        listings.append(listing)
    return listings[:30], {
        "name": "OpenSooq",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or "تم البحث بعبارة الطلب واستخراج النتائج القابلة للقراءة من بيانات الصفحة.",
    }


def search_mourjan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    mode = "rental" if transaction_from_request(request) == "للإيجار" else "for-sale"
    query = urllib.parse.urlencode({"q": " ".join(request.areas) or request.raw_text})
    url = f"https://www.mourjan.com/kw/kuwait/properties/{mode}/?{query}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0
    ad_pattern = re.compile(
        r'<div class="ad[^"]*"[^>]*>.*?<div class=widget id=([0-9]+)>.*?<a class=link href=([^>]+)>.*?<div dir=auto class="content ar">(.*?)</div>',
        re.S,
    )
    for code, href, description in ad_pattern.findall(body):
        candidates += 1
        url_abs = urllib.parse.urljoin("https://www.mourjan.com", href)
        listing = listing_from_text(
            source="Mourjan",
            code=f"MJ-{code}",
            url=url_abs,
            title="",
            description=description,
            price=None,
            transaction=mourjan_transaction_from_href(href, transaction_from_request(request)),
            fallback_type=mourjan_type_from_href(href, request.property_type),
        )
        if request_matches_listing(request, listing):
            listings.append(listing)
    return listings[:30], {
        "name": "Mourjan",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "candidates": candidates,
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
    candidates = 0
    for href, title in re.findall(r'<a href="(https://q8aqar\.com/details/realestate/[0-9]+/)">(.*?)</a>', body, re.S):
        candidates += 1
        title_clean = clean_text(title)
        code = "Q8-" + href.rstrip("/").split("/")[-1]
        listing = listing_from_text(
            source="Q8Aqar",
            code=code,
            url=href,
            title=title_clean,
            description=title_clean,
            price=None,
            transaction=detect_transaction(title_clean, transaction_from_request(request)),
            fallback_type=request.property_type,
        )
        if request_matches_listing(request, listing):
            listings.append(listing)
    return listings[:20], {
        "name": "Q8Aqar",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or f"تم فحص {candidates} رابطًا من صفحة المنطقة. دخل التقييم فقط ما أثبت نفس المنطقة والنوع والعملية.",
    }


def check_sakan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    area_meta = first_area_meta(request)
    part = property_slug(request, "sakan")
    buy_or_rent = "rent" if transaction_from_request(request) == "للإيجار" else "buy"
    gov = area_meta.get("sakan_governorate", "")
    city = area_meta.get("sakan_city", "")
    if gov and city:
        url = f"https://sakan.co/en/{buy_or_rent}/{part}/{gov}/{city}"
    elif gov:
        url = f"https://sakan.co/en/{buy_or_rent}/{part}/{gov}"
    else:
        url = f"https://sakan.co/en/{buy_or_rent}/{part}"
    body, status, ms, error = fetch_url(url)
    count_match = re.search(r"([0-9,]+)\s+available", body, re.I)
    count = int(count_match.group(1).replace(",", "")) if count_match else 0
    note = "تم الوصول للصفحة، لكن الإعلانات التفصيلية لا تظهر كبيانات منظمة في HTML العام."
    return [], {
        "name": "Sakan",
        "status": "page_reachable" if body else "failed",
        "records": 0,
        "candidates": 0,
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
