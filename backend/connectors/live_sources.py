from __future__ import annotations

import gzip
import html
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import KNOWN_AREAS as REQUEST_KNOWN_AREAS
from backend.services.request_parser import PROPERTY_TYPES, normalize_text, detect_seller_type, extract_area_range, text_has_area


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = 12

AREA_SLUGS = {
    "المطلاع": {"q8aqar": "mutlae", "sakan_governorate": "Jahra", "sakan_city": "almutlaa", "mourjan_q": "المطلاع"},
    "شمال غرب الصليبيخات": {"q8aqar": "north-west-sulaibikhat", "sakan_governorate": "Jahra", "sakan_city": "north-west-sulaibikhat", "mourjan_q": "شمال غرب الصليبيخات"},
    "ابو فطيرة": {"q8aqar": "abu-fatira", "sakan_governorate": "mubarak-al-kabir", "sakan_city": "abu-fatira", "mourjan_q": "ابو فطيرة"},
    "أبو فطيرة": {"q8aqar": "abu-fatira", "sakan_governorate": "mubarak-al-kabir", "sakan_city": "abu-fatira", "mourjan_q": "أبو فطيرة"},
    "السالمية": {"q8aqar": "salmiya", "sakan_governorate": "hawally", "sakan_city": "salmiya", "mourjan_q": "السالمية"},
    "الجابرية": {"q8aqar": "jabriya", "sakan_governorate": "hawally", "sakan_city": "jabriya", "mourjan_q": "الجابرية"},
    "الرميثية": {"q8aqar": "rumaithiya", "sakan_governorate": "hawally", "sakan_city": "rumaithiya", "mourjan_q": "الرميثية"},
    "صباح السالم": {"q8aqar": "sabah-al-salem", "sakan_governorate": "mubarak-al-kabir", "sakan_city": "sabah-al-salem", "mourjan_q": "صباح السالم"},
    "الفردوس": {"q8aqar": "ferdous", "sakan_governorate": "Farwaniya", "sakan_city": "al-firdous", "mourjan_q": "الفردوس"},
    "خيطان": {"q8aqar": "khaitan", "sakan_governorate": "Farwaniya", "sakan_city": "khaitan", "mourjan_q": "خيطان"},
    "حولي": {"q8aqar": "hawalli", "sakan_governorate": "hawally", "sakan_city": "hawally", "mourjan_q": "حولي"},
    "بنيد القار": {"q8aqar": "bnaid-al-qar", "sakan_governorate": "al-asimah", "sakan_city": "bnaid-al-qar", "mourjan_q": "بنيد القار"},
    "الفحيحيل": {"q8aqar": "fahaheel", "sakan_governorate": "ahmadi", "sakan_city": "fahaheel", "mourjan_q": "الفحيحيل"},
    "الجهراء": {"q8aqar": "jahra", "sakan_governorate": "Jahra", "sakan_city": "jahra", "mourjan_q": "الجهراء"},
    "الفروانية": {"q8aqar": "farwaniya", "sakan_governorate": "Farwaniya", "sakan_city": "farwaniya", "mourjan_q": "الفروانية"},
    "الأحمدي": {"q8aqar": "ahmadi", "sakan_governorate": "ahmadi", "sakan_city": "ahmadi", "mourjan_q": "الأحمدي"},
    "سلوى": {"q8aqar": "salwa", "sakan_governorate": "hawally", "sakan_city": "salwa", "mourjan_q": "سلوى"},
    "بيان": {"q8aqar": "bayan", "sakan_governorate": "hawally", "sakan_city": "bayan", "mourjan_q": "بيان"},
    "العقيلة": {"q8aqar": "aqeela", "sakan_governorate": "ahmadi", "sakan_city": "aqeela", "mourjan_q": "العقيلة"},
    "صباح الأحمد": {"q8aqar": "sabah-al-ahmed", "sakan_governorate": "ahmadi", "sakan_city": "sabah-al-ahmed", "mourjan_q": "صباح الأحمد"},
    "صباح الاحمد": {"q8aqar": "sabah-al-ahmed", "sakan_governorate": "ahmadi", "sakan_city": "sabah-al-ahmed", "mourjan_q": "صباح الاحمد"},
    "جابر الأحمد": {"q8aqar": "jaber-al-ahmed", "sakan_governorate": "Jahra", "sakan_city": "jaber-al-ahmed", "mourjan_q": "جابر الأحمد"},
    "جابر الاحمد": {"q8aqar": "jaber-al-ahmed", "sakan_governorate": "Jahra", "sakan_city": "jaber-al-ahmed", "mourjan_q": "جابر الاحمد"},
    "سعد العبدالله": {"q8aqar": "saad-al-abdallah", "sakan_governorate": "Jahra", "sakan_city": "saad-al-abdallah", "mourjan_q": "سعد العبدالله"},
    "صباح الناصر": {"q8aqar": "sabah-al-naser", "sakan_governorate": "Farwaniya", "sakan_city": "sabah-al-naser", "mourjan_q": "صباح الناصر"},
    "الدسمة": {"q8aqar": "dasman", "sakan_governorate": "al-asimah", "sakan_city": "dasman", "mourjan_q": "الدسمة"},
}

PROPERTY_SLUGS = {
    "بيت":   {"q8aqar": "houses",    "sakan": "house",     "mourjan": "villas-and-houses", "waseet": "بيوت"},
    "شقة":   {"q8aqar": "apartments","sakan": "apartment", "mourjan": "apartments",         "waseet": "شقق"},
    "أرض":   {"q8aqar": "lands",     "sakan": "land",      "mourjan": "lands",              "waseet": "اراضي"},
    "عمارة": {"q8aqar": "buildings", "sakan": "building",  "mourjan": "buildings",          "waseet": "عمارات"},
}

KNOWN_AREAS = list(dict.fromkeys(list(AREA_SLUGS.keys()) + REQUEST_KNOWN_AREAS + [
    "الدوحة", "مشرف", "الجهراء", "الأندلس", "الاندلس",
]))


def fetch_url(url: str, extra_headers: dict[str, str] | None = None) -> tuple[str, int, float, str | None]:
    """Fetch URL with gzip support and a modern browser User-Agent."""
    started = time.perf_counter()
    headers: dict[str, str] = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ar,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            ce = response.headers.get("Content-Encoding", "")
            if ce == "gzip" or (raw and raw[:2] == b"\x1f\x8b"):
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            body = raw.decode("utf-8", errors="replace")
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
    # Try "X الف" / "X مليون" patterns
    patterns = [
        r"([0-9]+(?:\.[0-9]+)?)\s*مليون",
        r"(?:السعر|سعر البيع|المطلوب|بياع|الثمن)[:\s]*([0-9]+(?:\.[0-9]+)?)\s*(مليون|الف|ألف|دينار|د\.ك|دك)?",
        r"([0-9]+(?:\.[0-9]+)?)\s*(مليون|الف|ألف)\s*(?:دينار|د\.ك|دك)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        value = float(match.group(1))
        unit = (match.group(2) if match.lastindex and match.lastindex >= 2 else "") or ""
        if "مليون" in unit:
            value *= 1_000_000
        elif "الف" in unit or "ألف" in unit:
            value *= 1000
        if value > 100:  # Sanity: prices in KD should be > 100
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


def extract_space_from_title(text: str) -> float | None:
    """Extract space from short listing titles like 'بيت 400م' or 'مساحة 375 م'."""
    normalized = normalize_text(text)
    # Pattern: number followed by م or متر
    patterns = [
        r"مساح[هة]\s*([0-9]+(?:\.[0-9]+)?)\s*م",
        r"([0-9]+(?:\.[0-9]+)?)\s*م(?:تر|2|²|\s|$)",
        r"([0-9]+)\s*(?:متر مربع|م مربع)",
    ]
    for p in patterns:
        m = re.search(p, normalized)
        if m:
            val = float(m.group(1))
            if 100 <= val <= 10000:  # Reasonable space range
                return val
    return None


def extract_price_from_title(text: str) -> float | None:
    """Extract price from short listing titles like 'بيت 350 الف' or 'السعر 1.2 مليون'."""
    normalized = normalize_text(text)
    # Million pattern
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*مليون", normalized)
    if m:
        return float(m.group(1)) * 1_000_000
    # Thousand pattern
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:الف|ألف)", normalized)
    if m:
        val = float(m.group(1)) * 1000
        if val > 10_000:
            return val
    return None


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
    space_override: float | None = None,
) -> Listing:
    full_text = f"{title} {description}"
    area = detect_area(full_text)
    space = space_override or parse_space(full_text) or extract_space_from_title(full_text)
    property_type = detect_property_type(full_text, fallback_type)

    # Use parsed price from text first; fall back to provided price
    price_value = extract_price_from_title(full_text) or parse_price(full_text, price)
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
                f"استخراج مباشر من صفحة {source}، والرقم عومل كألف د.ك لأنه بيع {property_type}"
                if inferred_thousands
                else f"استخراج مباشر من نص إعلان {source}"
            ),
            "spaceSource": "مستخرجة من نص الإعلان" if space else "غير مذكورة",
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
        # Also parse JSON-LD
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
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or "تم البحث بعبارة الطلب واستخراج النتائج القابلة للقراءة من بيانات الصفحة.",
    }


def search_mourjan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    mode = "rental" if transaction_from_request(request) == "للإيجار" else "for-sale"
    area_meta = first_area_meta(request)
    mourjan_q = area_meta.get("mourjan_q") or (" ".join(request.areas) if request.areas else request.raw_text)
    query = urllib.parse.urlencode({"q": mourjan_q})
    url = f"https://www.mourjan.com/kw/kuwait/properties/{mode}/?{query}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0

    # Pattern 1: ad-card with widget id
    ad_pattern = re.compile(
        r'<div class="ad[^"]*"[^>]*>.*?<div class=widget id=([0-9]+)>.*?<a class=link href=([^\s>]+)[^>]*>.*?<div dir=auto class="content ar">(.*?)</div>',
        re.S,
    )
    for code_id, href, description in ad_pattern.findall(body):
        candidates += 1
        url_abs = urllib.parse.urljoin("https://www.mourjan.com", href)
        full_desc = clean_text(description)
        price = extract_price_from_title(full_desc) or parse_price(full_desc)
        listing = listing_from_text(
            source="Mourjan",
            code=f"MJ-{code_id}",
            url=url_abs,
            title="",
            description=full_desc,
            price=price,
            transaction=mourjan_transaction_from_href(href, transaction_from_request(request)),
            fallback_type=mourjan_type_from_href(href, request.property_type),
        )
        if request_matches_listing(request, listing):
            listings.append(listing)

    # Pattern 2: JSON-LD structured data
    for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") not in ("RealEstateListing", "Offer", "Product"):
                continue
            candidates += 1
            item_url = item.get("url", "")
            code = "MJ-LD-" + item_url.rstrip("/").split("/")[-1]
            offer = item.get("offers", item)
            price_raw = offer.get("price") or item.get("price")
            listing = listing_from_text(
                source="Mourjan",
                code=code,
                url=item_url,
                title=item.get("name", ""),
                description=item.get("description", ""),
                price=float(price_raw) if price_raw else None,
                transaction=transaction_from_request(request),
                fallback_type=request.property_type,
            )
            if request_matches_listing(request, listing):
                listings.append(listing)

    return listings[:30], {
        "name": "Mourjan",
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or "تم استخراج كروت إعلانات عامة من HTML الصفحة مع استخراج السعر من النص.",
    }


def search_q8aqar(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """
    Q8Aqar uses server-side rendering but buries data in JavaScript.
    Strategy: scrape the listing page for hrefs + anchor text (which often contains
    price and space), then use the title text to extract data.
    """
    mode = "forrent" if transaction_from_request(request) == "للإيجار" else "forsale"
    area_meta = first_area_meta(request)
    part = property_slug(request, "q8aqar")
    area_slug = area_meta.get("q8aqar", "")
    url = (
        f"https://q8aqar.com/{mode}/{part}/{area_slug}/"
        if area_slug
        else f"https://q8aqar.com/{mode}/{part}/"
    )
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0

    # Pattern: anchor tags with full detail URLs
    seen_codes: set[str] = set()
    for href, title_html in re.findall(
        r'<a\s+href="(https://q8aqar\.com/details/realestate/[0-9]+/)"[^>]*>(.*?)</a>',
        body,
        re.S,
    ):
        candidates += 1
        title_clean = clean_text(title_html)
        if not title_clean or len(title_clean) < 5:
            continue
        code = "Q8-" + href.rstrip("/").split("/")[-1]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        price = extract_price_from_title(title_clean) or parse_price(title_clean)
        space = extract_space_from_title(title_clean)
        listing = listing_from_text(
            source="Q8Aqar",
            code=code,
            url=href,
            title=title_clean,
            description=title_clean,
            price=price,
            transaction=detect_transaction(title_clean, transaction_from_request(request)),
            fallback_type=request.property_type,
            space_override=space,
        )
        if request_matches_listing(request, listing):
            listings.append(listing)

    return listings[:20], {
        "name": "Q8Aqar",
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or f"تم فحص {candidates} رابطًا. السعر والمساحة تُستخرج من نص عنوان الإعلان مباشرة.",
    }


def search_sakan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """
    Sakan uses JavaScript rendering; the public HTML page doesn't contain listing data.
    We fetch the page to get a count of available properties and provide a direct deep link.
    """
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
    count_match = re.search(r"([0-9,]+)\s+(?:available|properties|listing)", body, re.I)
    count = int(count_match.group(1).replace(",", "")) if count_match else 0
    # Also look for Arabic count
    ar_count_match = re.search(r"(\d[\d,]*)\s+(?:عقار|نتيجة|إعلان)", body)
    if ar_count_match and not count:
        count = int(ar_count_match.group(1).replace(",", ""))
    note = (
        "تم الوصول لصفحة Sakan. البيانات مُعرَّضة عبر JavaScript ولا تظهر في HTML العام. "
        f"الصفحة تُشير إلى توفر {count} عقار."
        if not error else error
    )
    return [], {
        "name": "Sakan",
        "status": "page_reachable" if (body and not error) else "failed",
        "records": 0,
        "candidates": 0,
        "availableCount": count,
        "responseMs": ms,
        "url": url,
        "note": note,
    }


def search_waseet(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """
    Waseet (وسيط) is a classifieds platform available in Kuwait.
    It renders structured listings in its HTML for easy scraping.
    """
    prop_slug = property_slug(request, "waseet") or "بيوت"
    transaction_word = "للايجار" if transaction_from_request(request) == "للإيجار" else "للبيع"
    area_query = " ".join(request.areas) if request.areas else ""
    search_q = f"{prop_slug} {transaction_word} {area_query}".strip()
    url = f"https://www.waseet.net/kw/ar/search/?q={urllib.parse.quote(search_q)}&category=real-estate"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0

    if body:
        # Try JSON-LD first
        for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            items = (
                data.get("itemListElement", [])
                if isinstance(data, dict) and data.get("@type") == "ItemList"
                else (data if isinstance(data, list) else [data])
            )
            for element in items:
                item = element.get("item", element)
                if not isinstance(item, dict):
                    continue
                item_url = item.get("url", "")
                code = "WS-" + item_url.rstrip("/").split("/")[-1]
                candidates += 1
                offer = item.get("offers", {})
                price_raw = offer.get("price") if isinstance(offer, dict) else None
                listing = listing_from_text(
                    source="Waseet",
                    code=code,
                    url=item_url,
                    title=item.get("name", ""),
                    description=item.get("description", ""),
                    price=float(price_raw) if price_raw else None,
                    transaction=transaction_from_request(request),
                    fallback_type=request.property_type,
                )
                if request_matches_listing(request, listing):
                    listings.append(listing)

        # Fallback: scrape listing cards from HTML
        if not listings:
            card_pattern = re.compile(
                r'<(?:article|div)[^>]+class="[^"]*(?:ad|listing|item|card)[^"]*"[^>]*>(.*?)</(?:article|div)>',
                re.S | re.I,
            )
            for card_html in card_pattern.findall(body):
                candidates += 1
                card_text = clean_text(card_html)
                link_match = re.search(r'href="(/[^"]+)"', card_html)
                if not link_match:
                    continue
                card_url = urllib.parse.urljoin("https://www.waseet.net", link_match.group(1))
                code = "WS-" + card_url.rstrip("/").split("/")[-1]
                price = extract_price_from_title(card_text) or parse_price(card_text)
                space = extract_space_from_title(card_text)
                listing = listing_from_text(
                    source="Waseet",
                    code=code,
                    url=card_url,
                    title=card_text[:200],
                    description=card_text,
                    price=price,
                    transaction=transaction_from_request(request),
                    fallback_type=request.property_type,
                    space_override=space,
                )
                if request_matches_listing(request, listing):
                    listings.append(listing)

    return listings[:20], {
        "name": "Waseet",
        "status": "success" if listings else ("no_results" if (body and not error) else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or f"تم البحث في وسيط الكويت. فحص {candidates} كرت إعلان.",
    }


def search_nabdaqar(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """
    NabdAqar (نبض عقار) is a major Kuwaiti real estate marketplace.
    """
    area_query = " ".join(request.areas) if request.areas else ""
    prop_word = request.property_type or "عقار"
    transaction_word = transaction_from_request(request)
    search_q = f"{prop_word} {transaction_word} {area_query}".strip()
    url = f"https://nabdaqar.com/?qr={urllib.parse.quote(search_q)}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0

    if body:
        seen_codes: set[str] = set()
        for href, title_html in re.findall(
            r'<a\s+href="(/ad-details/[^"]+)"[^>]*>(.*?)</a>',
            body,
            re.S,
        ):
            candidates += 1
            title_clean = clean_text(title_html)
            if not title_clean or len(title_clean) < 4:
                continue
            parts = href.rstrip("/").split("/")
            code = "NABD-" + (parts[2] if len(parts) > 2 else str(candidates))
            if code in seen_codes:
                continue
            seen_codes.add(code)
            full_url = urllib.parse.urljoin("https://nabdaqar.com", href)
            price = extract_price_from_title(title_clean) or parse_price(title_clean)
            space = extract_space_from_title(title_clean)
            listing = listing_from_text(
                source="نبض عقار (NabdAqar)",
                code=code,
                url=full_url,
                title=title_clean,
                description=title_clean,
                price=price,
                transaction=detect_transaction(title_clean, transaction_from_request(request)),
                fallback_type=request.property_type,
                space_override=space,
            )
            if request_matches_listing(request, listing):
                listings.append(listing)

    return listings[:20], {
        "name": "نبض عقار (NabdAqar)",
        "status": "success" if listings else ("no_results" if (body and not error) else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or f"تم فحص {candidates} إعلان في نبض عقار.",
    }


def search_bu3qar(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """
    Bu3qar / Boshamlan (بوعقار / بوشملان) is a prominent Kuwait real estate platform.
    """
    area_query = " ".join(request.areas) if request.areas else ""
    prop_word = request.property_type or "عقار"
    transaction_word = transaction_from_request(request)
    search_q = f"{prop_word} {transaction_word} {area_query}".strip()
    url = f"https://www.bu3qar.com/?s={urllib.parse.quote(search_q)}"
    body, status, ms, error = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0

    if body:
        seen_codes: set[str] = set()
        for href in set(re.findall(r'href="(/product-details/[^"]+)"', body)):
            candidates += 1
            parts = href.rstrip("/").split("/")
            code = "BU3-" + (parts[2] if len(parts) > 2 else str(candidates))
            if code in seen_codes:
                continue
            seen_codes.add(code)
            full_url = urllib.parse.urljoin("https://www.bu3qar.com", href)
            raw_title = urllib.parse.unquote(parts[-1]).replace("-", " ") if len(parts) > 3 else "إعلان بوعقار"
            title_clean = clean_text(raw_title)
            price = extract_price_from_title(title_clean) or parse_price(title_clean)
            space = extract_space_from_title(title_clean)
            listing = listing_from_text(
                source="بوعقار / بوشملان (Bu3qar)",
                code=code,
                url=full_url,
                title=title_clean,
                description=title_clean,
                price=price,
                transaction=detect_transaction(title_clean, transaction_from_request(request)),
                fallback_type=request.property_type,
                space_override=space,
            )
            if request_matches_listing(request, listing):
                listings.append(listing)

    return listings[:20], {
        "name": "بوعقار / بوشملان (Bu3qar)",
        "status": "success" if listings else ("no_results" if (body and not error) else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "responseMs": ms,
        "url": url,
        "note": error or f"تم فحص {candidates} إعلان في بوعقار / بوشملان.",
    }


def search_external_sources(request: PropertyRequest) -> tuple[list[Listing], list[dict[str, Any]]]:
    listings: list[Listing] = []
    statuses: list[dict[str, Any]] = []
    for searcher in (search_opensooq, search_mourjan, search_q8aqar, search_sakan, search_waseet, search_nabdaqar, search_bu3qar):
        source_listings, status = searcher(request)
        listings.extend(source_listings)
        statuses.append(status)
    return listings, statuses
