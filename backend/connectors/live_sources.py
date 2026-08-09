from __future__ import annotations

import gzip
import html
import http.client
import json
import logging
import re
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

from backend.connectors.market_ads import search as search_market_ads
from backend.connectors.alhisba_public import fetch_public_deals
from backend.connectors.official_data import search as search_official_transactions
from backend.connectors.official_indicators import search as search_official_indicators
from backend.models import Listing, PropertyRequest
from backend.services.request_parser import KNOWN_AREAS as REQUEST_KNOWN_AREAS
from backend.services.request_parser import PROPERTY_TYPES, normalize_text, detect_seller_type, extract_area_range, excluded_numbers, text_has_area


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = 12
MAX_ATTEMPTS = 2
RETRY_DELAY = 0.6
TRANSIENT_EXTRA_ATTEMPTS = 2  # الأخطاء العابرة (DNS/مهلة/قطع اتصال) تحصل على محاولتين إضافيتين
TRANSIENT_RETRY_DELAY = 0.8  # مهلة متصاعدة إضافية لكل محاولة عابرة

_FetchResult = tuple[str, int, float, str | None, int]  # (body, status, ms, error, attempts)
_fetch_cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, _FetchResult]] = {}
_fetch_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 900  # 15 دقيقة

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


def fetch_url(url: str, extra_headers: dict[str, str] | None = None) -> tuple[str, int, float, str | None, int]:
    """جلب رابط مع إعادة محاولة ودعم gzip وكاش قصير ووكيل متصفح حديث.

    يعيد (body, status, ms, error, attempts): آخر عنصر هو عدد المحاولات الفعلية
    التي جرت (يشمل الناجحة — يُسجَّل في حالة المصدر للسجل الدوري).
    """
    # مفتاح التخزين يتضمن الرؤوس حتى لا تتصادم طلبات مختلفة لنفس الرابط
    cache_key = (url, tuple(sorted((extra_headers or {}).items())))
    # Cache hit (يمنع إعادة جلب نفس الصفحة في نفس الجلسة)
    with _fetch_cache_lock:
        cached = _fetch_cache.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

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

    last_error: str | None = None
    last_ms = round((time.perf_counter() - started) * 1000, 1)
    attempts_made = 0
    # الأخطاء العابرة تُعاد محاولتها أكثر من غيرها (حتى 4 مرات بمهلة متصاعدة)
    # لأنها غالبًا لحظية (انقطاع DNS/مهلة/قطع اتصال) وتنجح عند الإعادة،
    # بينما الخطأ الحقيقي (HTTP 403/404...) لا يتحسن بإعادة المحاولة المطولة.
    for attempt in range(MAX_ATTEMPTS + TRANSIENT_EXTRA_ATTEMPTS):
        attempts_made += 1
        request = urllib.request.Request(url, headers=headers)
        # مهلة متناقصة مع كل إعادة محاولة حتى لا يطول انتظار المصدر المتعثر كثيرًا
        attempt_timeout = max(3, TIMEOUT - (3 * attempt))
        try:
            with urllib.request.urlopen(request, timeout=attempt_timeout) as response:
                raw = response.read()
                ce = response.headers.get("Content-Encoding", "")
                if ce == "gzip" or (raw and raw[:2] == b"\x1f\x8b"):
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                body = raw.decode("utf-8", errors="replace")
                ms = round((time.perf_counter() - started) * 1000, 1)
                result = (body, response.status, ms, None, attempts_made)
                with _fetch_cache_lock:
                    _fetch_cache[cache_key] = (time.time(), result)
                logger.debug("Fetch OK %s (%.0fms، %d محاولات)", url, ms, attempts_made)
                return result
        except Exception as exc:
            last_error = str(exc)
            last_ms = round((time.perf_counter() - started) * 1000, 1)
            transient = _is_transient_error(exc)
            attempts_for_type = MAX_ATTEMPTS + (TRANSIENT_EXTRA_ATTEMPTS if transient else 0)
            logger.debug("Fetch attempt %d/%d failed for %s: %s", attempts_made, attempts_for_type, url, last_error)
            if attempt >= attempts_for_type - 1:
                break
            time.sleep(RETRY_DELAY + (TRANSIENT_RETRY_DELAY * attempt if transient else 0))
    result = ("", 0, last_ms, last_error, attempts_made)
    return result


def _is_transient_error(exc: BaseException) -> bool:
    """هل الخطأ عابر (يستحق إعادة محاولة إضافية) أم حقيقي (لا يتحسن بالإعادة)؟"""
    # استجابة فعلية من الخادم (403/404...) — لا نعيد محاولة طويلة عليها
    if isinstance(exc, urllib.error.HTTPError):
        return False
    # DNS (getaddrinfo)، مهلة، قطع/رفض اتصال، خطأ مقبس/نظام
    if isinstance(exc, (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return _is_transient_error(reason) if isinstance(reason, BaseException) else False
    if isinstance(exc, (http.client.RemoteDisconnected, http.client.HTTPException, ssl.SSLError)):
        return True
    return False


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
    excluded_values = set(excluded_numbers(normalized).values())
    # Pattern: number followed by م or متر
    patterns = [
        r"مساح[هة]\s*([0-9]+(?:\.[0-9]+)?)\s*م",
        r"([0-9]+(?:\.[0-9]+)?)\s*م(?:تر|2|²|\s|$)",
        r"([0-9]+)\s*(?:متر مربع|م مربع)",
    ]
    for p in patterns:
        for m in re.finditer(p, normalized):
            val = float(m.group(1))
            if 100 <= val <= 10000 and val not in excluded_values:  # Reasonable space range, ليس واجهة/ارتداد
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
    for area in sorted(request.areas, key=len, reverse=True):
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
    weak_price = False
    if (
        transaction == "للبيع"
        and property_type in {"بيت", "أرض", "عمارة"}
        and price_value
        and price_value < 10_000
    ):
        price_value *= 1000
        inferred_thousands = True
    if (
        transaction == "للبيع"
        and property_type in {"بيت", "أرض", "عمارة"}
        and price_value
        and price_value < 80_000
    ):
        # بيع بيت/أرض بهذا السعر في الكويت غالبًا رقم مختصر أو ناقص من المصدر.
        # لا نخترع رقمًا بديلًا؛ نستبعد السعر من التقييم حتى لا تظهر فرصة وهمية.
        price_value = None
        weak_price = True
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
                else f"رقم السعر منخفض وغير موثوق لبيع {property_type}، لذلك لم يدخل في التقييم"
                if weak_price
                else f"استخراج مباشر من نص إعلان {source}"
            ),
            "dataWarnings": "سعر خارجي منخفض/ناقص لم يدخل في التقييم" if weak_price else "",
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
    body, status, ms, error, attempts = fetch_url(url)
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
    return listings[:50], {
        "name": "OpenSooq",
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
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
    body, status, ms, error, attempts = fetch_url(url)
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

    return listings[:50], {
        "name": "Mourjan",
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
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
    body, status, ms, error, attempts = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0

    # Pattern: anchor tags with full detail URLs
    seen_codes: set[str] = set()
    raw_items: list[tuple[str, str, str]] = []  # (href, title_clean, code)
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
        raw_items.append((href, title_clean, code))

    # توسيع Q8Aqar: قراءة صفحات التفاصيل نفسها لتحسين السعر/المساحة (فقط لما تكون ناقصة أو محتاجة تحقق)
    # نقتصر على العناصر التي تفتقر للسعر أو المساحة لئلا نطيل زمن التحليل بلا فائدة
    need_detail = [
        href for href, _t, _c in raw_items
        if not (extract_price_from_title(_t) or parse_price(_t)) or not extract_space_from_title(_t)
    ]
    detail = search_q8aqar_details(need_detail) if need_detail else {}
    detail_linked = 0
    for href, title_clean, code in raw_items:
        price = extract_price_from_title(title_clean) or parse_price(title_clean)
        space = extract_space_from_title(title_clean)
        extra_price, extra_space = detail.get(href, (None, None))
        if extra_price and (not price or abs(extra_price - price) / price > 0.05):
            price = extra_price
            detail_linked += 1
        if extra_space and not space:
            space = extra_space
            detail_linked += 1
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

    note = f"تم فحص {candidates} رابطًا"
    if detail:
        note += f"، وقراءة {len(detail)} صفحة تفاصيل (تحسين السعر/المساحة في {detail_linked} حالة)"
    note += ". السعر والمساحة تُستخرج من العنوان ثم تُحسَّن من صفحات التفاصيل عند توفرها."
    return listings[:50], {
        "name": "Q8Aqar",
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
        "responseMs": ms,
        "url": url,
        "note": error or note,
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
    body, status, ms, error, attempts = fetch_url(url)
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

    return listings[:50], {
        "name": "Waseet",
        "status": "success" if listings else ("no_results" if (body and not error) else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
        "responseMs": ms,
        "url": url,
        "note": error or f"تم البحث في وسيط الكويت. فحص {candidates} كرت إعلان.",
    }


def _scan_link_listings(
    request: PropertyRequest,
    *,
    source: str,
    base_url: str,
    body: str,
    href_pattern: str,
    code_prefix: str,
    code_part: int | None = None,
    min_title_len: int = 5,
    flags: int = re.S | re.I,
) -> tuple[list[Listing], int]:
    """فحص روابط إعلانات (نمط <a href>…</a>) في صفحة مصدر رابطي.

    يستخرج العنوان والسعر والمساحة من نص الرابط، يبني Listing مطابقًا للطلب،
    ويزيل التكرار بالكود. code_part: عند None يُستخدم آخر جزء من الرابط ككود،
    وإلا الجزء المحدد (مع سقوط لعداد المرشحين عند غيابه كما في NabdAqar).
    """
    listings: list[Listing] = []
    seen_codes: set[str] = set()
    candidates = 0
    for href, title_html in re.findall(href_pattern, body, flags):
        candidates += 1
        title_clean = clean_text(title_html)
        if not title_clean or len(title_clean) < min_title_len:
            continue
        parts = href.rstrip("/").split("/")
        if code_part is not None:
            code = f"{code_prefix}-{parts[code_part] if len(parts) > code_part else candidates}"
        else:
            code = f"{code_prefix}-{parts[-1]}"
        if code in seen_codes:
            continue
        seen_codes.add(code)
        price = extract_price_from_title(title_clean) or parse_price(title_clean)
        space = extract_space_from_title(title_clean)
        listing = listing_from_text(
            source=source,
            code=code,
            url=urllib.parse.urljoin(base_url, href),
            title=title_clean,
            description=title_clean,
            price=price,
            transaction=detect_transaction(title_clean, transaction_from_request(request)),
            fallback_type=request.property_type,
            space_override=space,
        )
        if request_matches_listing(request, listing):
            listings.append(listing)
    return listings, candidates


def _link_search_result(
    name: str,
    listings: list[Listing],
    candidates: int,
    ms: float,
    url: str,
    error: str | None,
    body: str,
    note: str,
    attempts: int = 1,
) -> dict[str, Any]:
    """بنية الحالة الموحدة للمصادر الرابطية (نجاح/لا نتائج/فشل)."""
    return {
        "name": name,
        "status": "success" if listings else ("no_results" if (body and not error) else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
        "responseMs": ms,
        "url": url,
        "note": error or note,
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
    body, status, ms, error, attempts = fetch_url(url)
    listings, candidates = _scan_link_listings(
        request,
        source="نبض عقار (NabdAqar)",
        base_url="https://nabdaqar.com",
        body=body,
        href_pattern=r'<a\s+href="(/ad-details/[^"]+)"[^>]*>(.*?)</a>',
        code_prefix="NABD",
        code_part=2,
        min_title_len=4,
        flags=re.S,
    )

    return listings[:50], _link_search_result(
        "نبض عقار (NabdAqar)", listings, candidates, ms, url, error, body,
        f"تم فحص {candidates} إعلان في نبض عقار.", attempts,
    )


def _detail_price_space(body: str) -> tuple[float | None, float | None]:
    """استخراج السعر والمساحة من صفحة تفاصيل إعلان (وسوم وصفية أولًا ثم JSON-LD ثم نص صريح)."""
    price: float | None = None
    space: float | None = None
    # الوسوم الوصفية هي الأكثر صرامة (product:price:amount / og:price:amount)
    for pattern in (
        r'property="product:price:amount"\s+content="([0-9.,]+)"',
        r'name="price"\s+content="([0-9.,]+)"',
        r'property="og:price:amount"\s+content="([0-9.,]+)"',
    ):
        match = re.search(pattern, body, re.I)
        if match:
            price = float(match.group(1).replace(",", ""))
            break
    for pattern in (
        r'property="product:property:size"\s+content="([0-9.,]+)"',
        r'name="size"\s+content="([0-9.,]+)"',
    ):
        match = re.search(pattern, body, re.I)
        if match:
            space = float(match.group(1).replace(",", ""))
            break
    # JSON-LD يكمل ما لم تظهره الوسوم
    for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        for node in walk_dicts(data):
            if not isinstance(node, dict):
                continue
            offers = node.get("offers") or {}
            price = price or _number(offers.get("price") if isinstance(offers, dict) else None)
            price = price or _number(node.get("price"))
            floor = node.get("floorSize") or node.get("floor_size") or node.get("area")
            space = space or _number(floor)
    # نص صريح: سعر ضمن العناوين الرئيسية فقط (حماية من أرقام جانبية)
    if not price:
        price = extract_price_from_title(clean_text(body)[:2000]) or parse_price(clean_text(body)[:2000])
    if not space:
        space = extract_space_from_title(clean_text(body)[:2000])
    return price, space


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def search_q8aqar_details(hrefs: list[str]) -> dict[str, tuple[float | None, float | None]]:
    """قراءة صفحات التفاصيل نفسها لاستخراج السعر والمساحة (توسيع Q8Aqar).

    يُجلب حتى 3 صفحات بالتوازي حتى لا يطيل زمن التحليل (الفشل في صفحة لا يوقف الباقي).
    يعيد {href: (price, space)} للمواقع التي نجح استخراجها.
    """
    detail: dict[str, tuple[float | None, float | None]] = {}
    if not hrefs:
        return detail

    def _fetch_one(href: str) -> tuple[str, float | None, float | None]:
        body, _status, _ms, error, _attempts = fetch_url(href)
        if not body or error:
            return href, None, None
        price, space = _detail_price_space(body)
        return href, price, space

    with ThreadPoolExecutor(max_workers=3) as pool:
        for href, price, space in pool.map(_fetch_one, hrefs[:3]):
            if price or space:
                detail[href] = (price, space)
    return detail


def _extract_sakan_embedded(body: str) -> list[dict[str, Any]]:
    """محاولة قراءة إعلانات Sakan من الحالة المضمّنة في الصفحة (window.__… أو JSON.parse).

    الموقع يعرض البيانات عبر JavaScript، لذلك نمسح أي كتلة JSON كبيرة تحمل
    مفاتيح تشبه الإعلانات (title + price أو listing) ونستخرج منها إعلانات صالحة.
    """
    blobs: list[str] = []
    # JSON.parse('…') أو JSON.parse(…)
    # ملاحظة: فك الإحلالات يجب ألا يمر عبر unicode_escape لأنه يشوّه العربية
    # متعددة البايتات؛ نكتفي بفك الاقتباسات المائلة ونترك \uXXXX ليتولاه json.loads.
    for match in re.finditer(r"JSON\.parse\(\s*(['\"])((?:[^'\"\\]|\\.)*)\1\s*\)", body, re.S):
        raw = match.group(2)
        blobs.append(raw.replace('\\"', '"').replace("\\'", "'"))
    # window.__X = {...}
    for match in re.finditer(r"window\.__[A-Za-z0-9_]*\s*=\s*(\{.*?\});", body, re.S):
        blobs.append(match.group(1))
    found: list[dict[str, Any]] = []
    for blob in blobs:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for node in walk_dicts(data):
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or node.get("name") or "")
            url = str(node.get("url") or node.get("slug") or node.get("listing_url") or "")
            price = _number(node.get("price"))
            if not title or not url or price is None:
                continue
            if "sakan.co" not in url and not url.startswith("/en/"):
                continue
            found.append(node)
    return found


def search_sakan(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """Sakan: محاولة استخراج إعلانات حقيقية من الحالة المضمّنة، مع الاحتفاظ بعداد المتاح كاحتياط."""
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
    body, status, ms, error, attempts = fetch_url(url)
    listings: list[Listing] = []
    embedded = _extract_sakan_embedded(body) if body else []
    seen: set[str] = set()
    for node in embedded:
        url_value = str(node.get("url") or "")
        full_url = url_value if url_value.startswith("http") else urllib.parse.urljoin("https://sakan.co", url_value)
        code = "SAK-" + (full_url.rstrip("/").split("/")[-1] or "0")
        if code in seen:
            continue
        seen.add(code)
        price = _number(node.get("price"))
        space = _number(node.get("area")) or _number(node.get("size")) or extract_space_from_title(str(node.get("title") or ""))
        listing = listing_from_text(
            source="Sakan",
            code=code,
            url=full_url,
            title=str(node.get("title") or ""),
            description=str(node.get("description") or node.get("title") or ""),
            price=price,
            transaction=detect_transaction(str(node.get("title") or ""), transaction_from_request(request)),
            fallback_type=request.property_type,
            space_override=space,
        )
        if request_matches_listing(request, listing):
            listings.append(listing)

    count = 0
    count_match = re.search(r"([0-9,]+)\s+(?:available|properties|listing)", body, re.I)
    count = int(count_match.group(1).replace(",", "")) if count_match else 0
    ar_count_match = re.search(r"(\d[\d,]*)\s+(?:عقار|نتيجة|إعلان)", body)
    if ar_count_match and not count:
        count = int(ar_count_match.group(1).replace(",", ""))
    if listings:
        note = f"تم استخراج {len(listings)} إعلانًا من البيانات المضمّنة في الصفحة (الخطة: إدخال Sakan في التقييم)."
        status_name = "success"
    elif embedded:
        note = f"وجدت الحالة المضمّنة {len(embedded)} عنصرًا لكن لم يثبت أي إعلان أنه نفس المنطقة والنوع والعملية. متاح بالصفحة: {count}."
        status_name = "no_results"
    elif body and not error:
        note = (
            "تم الوصول لصفحة Sakan؛ البيانات تُعرض عبر JavaScript ولا تظهر كبنية منظمة قابلة للقراءة "
            "من HTML العام حتى بعد مسح الحالة المضمّنة. "
            f"الصفحة تُشير إلى توفر {count} عقار."
        )
        status_name = "page_reachable"
    else:
        note = error or "تعذر الوصول إلى Sakan"
        status_name = "failed"
    return listings, {
        "name": "Sakan",
        "status": status_name,
        "records": len(listings),
        "candidates": len(embedded),
        "attempts": attempts,
        "availableCount": count,
        "responseMs": ms,
        "url": url,
        "note": note,
    }


def search_aqarat(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """منصة Aqarat (مصدر توسعة جديد في الخطة): البحث عن إعلانات عقارية كويتية."""
    area_query = " ".join(request.areas) if request.areas else ""
    prop_word = request.property_type or "عقار"
    transaction_word = transaction_from_request(request)
    search_q = f"{prop_word} {transaction_word} {area_query}".strip()
    url = f"https://aqarat.com/search?q={urllib.parse.quote(search_q)}"
    body, status, ms, error, attempts = fetch_url(url)
    listings, candidates = _scan_link_listings(
        request,
        source="Aqarat",
        base_url="https://aqarat.com",
        body=body,
        href_pattern=r'<a\s+href="([^"]*(?:property|listing|real-estate|detail)[^"]*)"[^>]*>(.*?)</a>',
        code_prefix="AQR",
    )
    return listings[:50], _link_search_result(
        "Aqarat", listings, candidates, ms, url, error, body,
        f"تم فحص {candidates} إعلانًا في Aqarat.", attempts,
    )


def search_four_sale(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """منصة 4Sale الكويتية، مع مصدر بديل (OpenSooq الكويت) عند تعذر الوصول.

    عند فشل الاتصال (خطأ عابر مثل DNS أو مهلة أو حظر) تُعاد المحاولة تلقائيًا
    داخل fetch_url، ثم يُجرَّب المصدر البديل OpenSooq بنفس شروط الطلب حتى لا
    يضيع هذا الموقع من التقييم، مع إفصاح شفاف في حالة المصدر عن السبب والبديل.
    """
    area_query = " ".join(request.areas) if request.areas else ""
    prop_word = request.property_type or "عقار"
    search_q = f"{prop_word} {area_query}".strip()
    url = f"https://kuwait.4sale.com/real-estate?search_text={urllib.parse.quote(search_q)}"
    body, status, ms, error, attempts = fetch_url(url)
    listings, candidates = _scan_link_listings(
        request,
        source="4Sale",
        base_url="https://kuwait.4sale.com",
        body=body,
        href_pattern=r'<a\s+href="([^"]*(?:real-estate/|listing/|properties/)[^"]*)"[^>]*>(.*?)</a>',
        code_prefix="4S",
    )
    if error and not listings:
        # تعذر الوصول إلى 4Sale: جرّب المصدر البديل OpenSooq الكويت بنفس شروط الطلب
        fb_listings, fb_status = search_opensooq(request)
        fb_name = fb_status.get("name", "OpenSooq")
        for listing in fb_listings:
            listing.raw["fallbackFor"] = "4Sale"
        if fb_listings:
            return fb_listings[:50], {
                "name": "4Sale",
                "status": "fallback",
                "records": len(fb_listings),
                "candidates": fb_status.get("candidates", 0),
                "attempts": attempts,
                "responseMs": fb_status.get("responseMs", ms),
                "url": url,
                "note": (
                    f"تعذر الوصول إلى 4Sale ({error}) حتى بعد إعادة المحاولة — "
                    f"استُخدم المصدر البديل {fb_name} بنفس شروط البحث وأسفر عن "
                    f"{len(fb_listings)} نتيجة مطابقة (معلّمة في بيانات النتيجة)."
                ),
            }
        # البديل فشل أيضًا: تقرير شفاف بفشل الموقعين
        return [], {
            "name": "4Sale",
            "status": "failed",
            "records": 0,
            "candidates": 0,
            "attempts": attempts,
            "responseMs": ms,
            "url": url,
            "note": (
                f"تعذر الوصول إلى 4Sale ({error})، وجرّبنا المصدر البديل {fb_name} "
                f"لكنه فشل أيضًا ({fb_status.get('note', '')})."
            ),
        }
    return listings[:50], _link_search_result(
        "4Sale", listings, candidates, ms, url, error, body,
        f"تم فحص {candidates} إعلانًا في 4Sale.", attempts,
    )


def search_bu3qar(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """
    Bu3qar / Boshamlan (بوعقار / بوشملان) is a prominent Kuwait real estate platform.
    """
    area_query = " ".join(request.areas) if request.areas else ""
    prop_word = request.property_type or "عقار"
    transaction_word = transaction_from_request(request)
    search_q = f"{prop_word} {transaction_word} {area_query}".strip()
    url = f"https://www.bu3qar.com/?s={urllib.parse.quote(search_q)}"
    body, status, ms, error, attempts = fetch_url(url)
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

    return listings[:50], _link_search_result(
        "بوعقار / بوشملان (Bu3qar)", listings, candidates, ms, url, error, body,
        f"تم فحص {candidates} إعلان في بوعقار / بوشملان.", attempts,
    )


def search_alhisba_public_deals(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    from backend.connectors.official_data import _transaction_listing

    rows, meta = fetch_public_deals()
    listings: list[Listing] = []
    for index, row in enumerate(rows):
        area = str(row.get("area") or "")
        if request.areas and not any(text_has_area(requested, area) for requested in request.areas):
            continue
        listing = _transaction_listing(row, index)
        if request.property_type and request.property_type != "عقارات":
            if request.property_type not in (listing.property_type + " " + listing.detail_class):
                continue
        listings.append(listing)
    status = dict(meta)
    status["records"] = len(listings)
    status["candidates"] = len(rows)
    status["note"] = (
        "الحسبة تعرض صفقات مسجلة ومزادات وروابط إعلانات شبيهة في الصفحة العامة؛ "
        "تدخل هنا كدليل مرجعي للسعر وليست إعلانًا متاحًا للبيع."
    )
    return listings, status


SEARCHERS: list[tuple[str, Any]] = [
    ("OpenSooq", search_opensooq),
    ("Mourjan", search_mourjan),
    ("Q8Aqar", search_q8aqar),
    ("Sakan", search_sakan),
    ("Waseet", search_waseet),
    ("NabdAqar", search_nabdaqar),
    ("Bu3qar", search_bu3qar),
    ("Aqarat", search_aqarat),
    ("4Sale", search_four_sale),
    ("الحسبة", search_alhisba_public_deals),
    ("السوق المباشر", search_market_ads),
    ("مؤشرات رسمية", search_official_indicators),
    ("الصفقات الرسمية", search_official_transactions),
]

# التركيبات العريضة للفحص المركّب: أنواع العقار الرئيسية × المعاملات.
# الطلب الفارغ كان يفحص بيوت البيع فقط عبر Q8Aqar وبيوعات OpenSooq ويُسقط
# شققهم وأراضيهم وإيجاراتهم — هذه التركيبات تصل بفرص كل منصة لأقصى عدد ممكن.
BROAD_COMBOS: list[tuple[str, str]] = [
    ("بيت", "للبيع"),
    ("شقة", "للبيع"),
    ("أرض", "للبيع"),
    ("بيت", "للإيجار"),
    ("شقة", "للإيجار"),
    ("أرض", "للإيجار"),
]


def broad_combo_requests() -> list[PropertyRequest]:
    """طلبات عريضة مركّبة: بيت/شقة/أرض × بيع/إيجار بدل طلب فارغ واحد.

    كل طلب يحدد النوع والمعاملة فيوجه المصادر ذات البنية النوعية
    (Q8Aqar/OpenSooq) لصفحات كل فئة على حدة.
    """
    return [
        PropertyRequest(raw_text="", property_type=ptype, transaction=transaction)
        for ptype, transaction in BROAD_COMBOS
    ]


def search_combo_sources(
    combos: list[PropertyRequest] | None = None,
    source_names: list[str] | None = None,
) -> tuple[list[Listing], list[dict[str, Any]]]:
    """مسح عريض مركّب: يفحص عدة أنواع/معاملات عبر المصادر ذات البنية النوعية.

    يشغّل كل مصدر على كل تركيبة (بيت/شقة/أرض × بيع/إيجار) بالتوازي، يدمج
    الإعلانات الفريدة فقط (إزالة التكرار بالكود — الصفحات المتقاطعة تُجلب مرة
    واحدة عبر الكاش)، ويسجّل تشغيل كل تركيبة، ويعيد حالة مجمّعة واحدة لكل
    مصدر بعدد النتائج الفريدة والتركيبات الناجحة/الفاشلة.
    """
    if combos is None:
        combos = broad_combo_requests()
    if source_names is None:
        source_names = ["Q8Aqar", "OpenSooq"]
    search_by_name = dict(SEARCHERS)
    tasks = [
        (name, search_by_name[name], combo)
        for name in source_names
        if name in search_by_name
        for combo in combos
    ]
    if not tasks:
        return [], []

    raw: dict[str, list[tuple[list[Listing], dict[str, Any]]]] = {name: [] for name in source_names}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(tasks)))) as pool:
        futures = {pool.submit(search, combo): (name, combo) for name, search, combo in tasks}
        for future, (name, combo) in futures.items():
            try:
                combo_listings, status = future.result()
            except Exception as exc:  # فشل تركيبة واحدة لا يوقف بقية المسح
                logger.warning("Broad combo %s (%s/%s) failed: %s", name, combo.property_type, combo.transaction, exc)
                combo_listings, status = [], {
                    "name": name, "status": "failed", "records": 0, "candidates": 0,
                    "responseMs": 0, "note": f"خطأ غير متوقع: {exc}",
                }
            raw[name].append((combo_listings, status))
            # سجل دقيق لكل تركيب — منع التكرار الدوري يمنع تضخم السجل
            combo_log = dict(status)
            combo_log["name"] = f"{name} ({combo.property_type} {combo.transaction})"
            log_source_run(combo_log)

    listings: list[Listing] = []
    seen_codes: set[str] = set()
    statuses: list[dict[str, Any]] = []
    for name in source_names:
        results = raw.get(name) or []
        if not results:
            continue
        merged: list[Listing] = []
        ok = failed = no_results = 0
        candidates = 0
        max_attempts = 0
        max_ms = 0.0
        first_url = ""
        detail_notes: list[str] = []
        for combo_listings, status in results:
            st = status.get("status")
            if st == "success":
                ok += 1
            elif st == "failed":
                failed += 1
            else:
                no_results += 1
            candidates += status.get("candidates", 0) or 0
            max_attempts = max(max_attempts, status.get("attempts") or 0)
            max_ms = max(max_ms, status.get("responseMs") or 0)
            first_url = first_url or status.get("url") or ""
            note = status.get("note")
            if note and len(detail_notes) < 2:
                detail_notes.append(str(note)[:80])
            for listing in combo_listings:
                if listing.code in seen_codes:
                    continue
                seen_codes.add(listing.code)
                merged.append(listing)
        summary = (
            f"مسح عريض {len(results)} تركيبات (بيت/شقة/أرض × بيع/إيجار): "
            f"{ok} نجحت، {no_results} بلا نتائج، {failed} فشلت — {len(merged)} إعلانًا فريدًا."
        )
        if detail_notes:
            summary += " | " + " — ".join(detail_notes)
        statuses.append({
            "name": name,
            "status": (
                "failed"
                if ok == 0 and failed and no_results == 0
                else ("success" if ok else "no_results")
            ),
            "records": len(merged),
            "candidates": candidates,
            "attempts": max_attempts,
            "responseMs": max_ms,
            "url": first_url,
            "note": summary,
        })
        listings.extend(merged)
    return listings, statuses


# المفتاح (اسم المصدر، الحالة) فقط — محدد العدد (عدد المصادر × الحالات) فلا ينمو بلا حدود
# ولا يتأثر بتغير النصوص/الأعداد في الملاحظات بين الطلبات.
_SOURCE_LOG_MEM: dict[tuple[str, str], tuple[float, int]] = {}
_SOURCE_LOG_LOCK = threading.Lock()
SOURCE_LOG_DEBOUNCE_SECONDS = 300  # نفس المصدر بنفس النتيجة لا يُسجل أكثر من مرة في هذه النافذة


def log_source_run(status: dict[str, Any]) -> None:
    """تسجيل تشغيل مصدر واحد (نجاح/فشل + السبب + المدة + عدد المحاولات).

    منع التكرار الدوري: داخل نافذة زمنية تُحتسب التكرارات نفسها دون تسجيل،
    وعند انتهاء النافذة يُسجل سطر واحد فقط يحمل عدد المرات التي كُتمت
    (فلا يتضخم السجل في الفحص الدوري كل 5 دقائق أو في كل تحليل).
    """
    name = str(status.get("name") or "مصدر")
    st = str(status.get("status") or "unknown")
    ms = status.get("responseMs")
    attempts = status.get("attempts")
    attempts_text = f"{attempts}" if attempts is not None else "—"  # المصادر المحلية بلا جلب HTTP
    records = status.get("records", 0)
    note = str(status.get("note") or "")[:120]
    key = (name, st)
    now = time.time()
    with _SOURCE_LOG_LOCK:
        prev = _SOURCE_LOG_MEM.get(key)
        if prev:
            when, count = prev
            if now - when < SOURCE_LOG_DEBOUNCE_SECONDS:
                _SOURCE_LOG_MEM[key] = (when, count + 1)
                return  # مكرر داخل النافذة — يُحتسب ولا يُسجل
            suppressed = count
        else:
            suppressed = 0
        _SOURCE_LOG_MEM[key] = (now, 0)
    suffix = f" (كرر نفسه {suppressed} مرة في النافذة الأخيرة دون تسجيل)" if suppressed else ""
    level = logging.WARNING if st == "failed" else logging.INFO
    logger.log(
        level,
        "مصدر %s → %s | %dms | محاولات %s | نتائج %d | %s%s",
        name, st, ms or 0, attempts_text, records, note, suffix,
    )


def search_external_sources(
    request: PropertyRequest,
    selected_sources: list[str] | None = None,
) -> tuple[list[Listing], list[dict[str, Any]]]:
    """تشغيل كل المصادر بالتوازي لتقليل زمن الانتظار الإجمالي بدل التسلسل (حتى 84 ثانية سابقًا).

    يسجّل نتيجة كل مصدر (الحالة + السبب + المدة + عدد المحاولات) مرة واحدة لكل تشغيل
    عبر log_source_run مع منع تكرار الرسالة نفسها في الفحص الدوري.
    """
    listings: list[Listing] = []
    statuses: list[dict[str, Any]] = []
    selected = {name.strip() for name in (selected_sources or []) if name.strip()}
    searchers = [(name, search) for name, search in SEARCHERS if not selected or name in selected]
    if not searchers:
        return [], [
            {
                "name": "مصادر خارجية",
                "status": "no_data",
                "records": 0,
                "candidates": 0,
                "note": f"لا يوجد مصدر مطابق للاختيار: {', '.join(sorted(selected))}",
            }
        ]
    with ThreadPoolExecutor(max_workers=len(searchers)) as pool:
        futures = {pool.submit(search, request): name for name, search in searchers}
        for future, name in futures.items():
            try:
                source_listings, status = future.result()
            except Exception as exc:  # حماية: أي خطأ غير متوقع في مصدر لا يوقف التحليل
                logger.warning("External source '%s' failed unexpectedly: %s", name, exc)
                source_listings = []
                status = {
                    "name": name,
                    "status": "failed",
                    "records": 0,
                    "candidates": 0,
                    "note": f"خطأ غير متوقع: {exc}",
                }
            listings.extend(source_listings)
            statuses.append(status)
            log_source_run(status)
    return listings, statuses
