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
from typing import Any, Callable

logger = logging.getLogger(__name__)

from backend.connectors.market_ads import search as search_market_ads
from backend.connectors.alhisba_public import fetch_public_deals
from backend.connectors.official_data import search as search_official_transactions
from backend.connectors.official_indicators import search as search_official_indicators
from backend.models import Listing, PropertyRequest
from backend.services.request_parser import KNOWN_AREAS as REQUEST_KNOWN_AREAS
from backend.services.request_parser import PROPERTY_TYPES, normalize_text, detect_seller_type, extract_area_range, excluded_numbers, text_has_area, extract_rental_income, detect_area_in_text


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

# سجل آلية الجلب لكل مصدر — شفافية كاملة في التقرير: كيف تُجلب البيانات فعلًا وما
# نقطة النهاية الحقيقية. الحقيقة التقنية: لا توجد REST APIs عامة لهذه البوابات
# (جرّبنا api.4sale.com.kw وwp-json لـ Q8Aqar — غير متاحة)، فالمتاح هو ما تسمح
# الصفحة العامة بقراءته: حمولة JSON مضمّنة (بيانات التطبيق نفسها) أو بيانات منظمة
# (JSON-LD) أو فحص روابط HTML — وهذا ما نستهلكه، مع حفظ الرابط الأصلي لكل إعلان
# كدليل في قاعدة المعرفة (market_listings.original_url).
SOURCE_MECHANISMS: dict[str, dict[str, str]] = {
    "OpenSooq": {
        "method": "حمولة JSON مضمّنة (__NEXT_DATA__) من صفحات البيع والإيجار — مسح جرد كامل بترقيم الصفحات + بحث حي بالعبارة",
        "endpoint": "https://kw.opensooq.com/en/property/property-for-sale?page=… (و property-for-rent)",
    },
    "Mourjan": {
        "method": "بيانات منظمة JSON-LD + فحص روابط الصفحة",
        "endpoint": "https://www.mourjan.com/kw/kuwait/properties/…",
    },
    "Q8Aqar": {
        "method": "JSON مضمّن + فحص روابط + صفحات التفاصيل للسعر/المساحة",
        "endpoint": "https://q8aqar.com/… (لا REST عام — wp-json محجوب)",
    },
    "4Sale": {
        "method": "فحص روابط HTML لأحدث العقارات (لا API عام — النطاق الحالي q84sale.com)",
        "endpoint": "https://www.q84sale.com/en/latest/property/…",
    },
    "Waseet": {
        "method": "فحص روابط HTML وصفحات التفاصيل",
        "endpoint": "https://www.waseet.net/kw/ar/search/?q=…",
    },
    "Nabdaqar": {
        "method": "فحص روابط HTML",
        "endpoint": "https://nabdaqar.com/?qr=…",
    },
    "Sakan": {
        "method": "الحالة المضمّنة في الصفحة عند توفرها (وإلا فحص روابط)",
        "endpoint": "https://sakan.co/en/…",
    },
    "Aqarat": {
        "method": "فحص روابط HTML",
        "endpoint": "https://aqarat.com/search?q=…",
    },
    "Bu3qar": {
        "method": "فحص روابط HTML",
        "endpoint": "https://www.bu3qar.com/?s=…",
    },
    "Yebtah": {
        "method": "بيانات ItemList منظمة (JSON-LD) من صفحتي البيع والإيجار",
        "endpoint": "https://yebtah.com/en/for_sale · /en/for_rent",
    },
    "PropertyFinder": {
        "method": "بيانات منظمة JSON-LD/حمولة مضمّنة من صفحات البحث؛ غير قابل للوصول من شبكات الخوادم حاليًا (مهلة زمنية) ويُعاد فحصه يوميًا",
        "endpoint": "https://www.propertyfinder.kw/en/search?l=1&ob=pd&page=… (و property-for-rent)",
    },
    "Aqarmap": {
        "method": "بيانات منظمة JSON-LD من صفحات النتائج؛ النسخة الكويتية متوقفة والمسار /kw/ يعيد بوابة مصر (يُتحقق من هوية الصفحة أولًا)",
        "endpoint": "https://aqarmap.com/kw/… (يُعاد توجيهه حاليًا إلى مصر)",
    },
    "Bayut": {
        "method": "فحص روابط HTML وبيانات JSON-LD؛ محمي بنظام captcha (hb.captcha.bayut.com) يمنع القراءة البرمجية",
        "endpoint": "https://www.bayut.com/kuwait/…",
    },
    "الحسبة العامة": {
        "method": "تغذية رسمية من موقع الحسبة (صفقات موثقة بمواعيد وأرقام قسائم)",
        "endpoint": "https://alhisba.com/…",
    },
    "الصفقات الرسمية": {
        "method": "تغذية رسمية CSV/JSON عبر OFFICIAL_TRANSACTIONS_SOURCE + الحسبة العامة",
        "endpoint": "متغير — يُضبط عبر OFFICIAL_TRANSACTIONS_SOURCE",
    },
}


def source_mechanism(name: str) -> dict[str, str]:
    """آلية الجلب المعروفة لمصدر (method + endpoint) أو افتراض شفاف عند عدم التصنيف."""
    return SOURCE_MECHANISMS.get(name, {
        "method": "فحص HTML للصفحة العامة (لا REST API عام)",
        "endpoint": "رابط البحث الفعلي المستخدم وقت التشغيل",
    })


def _encode_url(url: str) -> str:
    """ترميز الأحرف غير ASCII في الرابط قبل الطلب (urllib يتطلب ASCII).

    الروابط العربية (مثل صفحات OpenSooq بقسم عقارات-للبيع) تفشل بدونه بخطأ
    `'ascii' codec can't encode` — نرمّز المسار والاستعلام مع إبقاء البنية
    والترميزات الموجودة كما هي (لا ترميز مزدوج).
    """
    try:
        url.encode("ascii")
        return url
    except UnicodeEncodeError:
        pass
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%:@")
    query = urllib.parse.quote(parts.query, safe="=&%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def fetch_url(url: str, extra_headers: dict[str, str] | None = None) -> tuple[str, int, float, str | None, int]:
    """جلب رابط مع إعادة محاولة ودعم gzip وكاش قصير ووكيل متصفح حديث.

    يعيد (body, status, ms, error, attempts): آخر عنصر هو عدد المحاولات الفعلية
    التي جرت (يشمل الناجحة — يُسجَّل في حالة المصدر للسجل الدوري). الروابط غير
    ASCII تُرمَّز تلقائيًا (انظر _encode_url) قبل الطلب.
    """
    request_url = _encode_url(url)
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
        request = urllib.request.Request(request_url, headers=headers)
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
    # استجابة فعلية من الخادم — بعضها عابر يُعاد (410/429/503: حماية WAF أو
    # تحميل مؤقت من المواقع يظهر ويختفي) والباقي حقيقي لا يتحسن بالإعادة.
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (410, 429, 503)
    # DNS (getaddrinfo)، مهلة، قطع/رفض اتصال، خطأ مقبس/نظام
    if isinstance(exc, (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return _is_transient_error(reason) if isinstance(reason, BaseException) else False
    if isinstance(exc, (http.client.RemoteDisconnected, http.client.HTTPException, ssl.SSLError)):
        return True
    return False


def _is_transient_block(error: str | None) -> bool:
    """هل الفشل حجب مؤقت من WAF (410/429/503) يستحق انتظارًا متباعدًا؟

    fetch_url يعيد status=0 عند الفشل، لذا نفحص نص الخطأ (مثل «HTTP Error 410: Gone»).
    """
    text = error or ""
    return any(code in text for code in ("410", "429", "503"))


# تحويل الأرقام العربية الهندية (٠-٩) وفواصلها إلى الإنجليزية (0-9) عند دخول النص
# — كل الأرقام المعروضة في المنصة بالإنجليزية مهما كان مصدر النص.
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    value = value.translate(_AR_DIGITS)
    return re.sub(r"\s+", " ", value).strip()


def detect_area(text: str) -> str:
    """منطقة كويتية من نص الإعلان (عنوان + وصف). تفويض للكاشف المشترك في
    request_parser: أطول تطابق أولًا + أسماء مرادفة (عربي/إنجليزي) + صيغ بلا
    مسافات — فالمناطق الناقصة من القائمة المحلية (المنصورية، السرة، النسيم...)
    تُكتشف من القائمة الكاملة المعتمدة."""
    return detect_area_in_text(text)


def detect_property_type(text: str, fallback: str = "") -> str:
    normalized = normalize_text(text)
    # صيغ الجمع الشائعة في عناوين 4Sale (شقق تمليك، بيوت وشقق، فلل، عماير، قسائم،
    # اراضي) كانت تسقط كلها إلى «عقارات» لأن الكاشف كان يطابق المفرد فقط.
    if any(word in normalized for word in ("عماره", "بنايه", "عماير", "عمائر", "عمارات", "استثماري")):
        return "عمارة"
    if any(word in normalized for word in ("ارض", "اراضي", "قسيمه", "قسايم", "قسائم")):
        return "أرض"
    if any(word in normalized for word in ("شقه", "شقق", "دوبلكس")):
        return "شقة"
    if any(word in normalized for word in ("بيت", "بيوت", "فيلا", "فلل", "منزل", "منازل", "هدام")):
        return "بيت"
    return fallback or "عقارات"


def parse_price(text: str, fallback: Any = None) -> float | None:
    normalized = normalize_text(text).replace(",", "")
    # Try "X الف" / "X مليون" patterns
    patterns = [
        r"([0-9]+(?:\.[0-9]+)?)\s*مليون",
        # رقم يليه «م/متر/م²» مساحة لا سعر — مثال حي: «مطلوب عقار سكني للإيجار 200م
        # 550 د.ك» كانت تلتقط 200 (المساحة) بدل الميزانية 550.
        r"(?:السعر|سعر البيع|المطلوب|بياع|الثمن|الايجار|ايجار|الاجار)[:\s]*([0-9]+(?:\.[0-9]+)?)(?!\s*م(?:تر|2|²|\s|$))\s*(مليون|الف|ألف|دينار|د\.ك|دك)?",
        r"([0-9]+(?:\.[0-9]+)?)\s*(مليون|الف|ألف)\s*(?:دينار|د\.ك|دك)?",
        # صيغة 4Sale والمواقع الإنجليزي: «850 KWD» / «1,300 KWD» — المبلغ بوحدة الدينار مباشرة
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*KWD",
        # رقم + عملة مباشرة دون كلمة مفتاح: «550 د.ك» في عناوين الطلب (بعد تجاوز
        # رقم المساحة). الحارس value > 100 يطرد أسعار 4Sale الوهمية «1 د.ك».
        r"([0-9]+(?:\.[0-9]+)?)\s*(دينار|د\.ك|دك)\b",
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
    # «ايجار»/«إيجار» بمختلف الصيغ (للايجار/الايجار/ايجار) — تُفحص قبل «بيع» لأن
    # إعلانات الإيجار قد لا تحمل «للايجار» صراحةً (مثل «الايجار دور في عماير»)
    if "ايجار" in normalized or "إيجار" in normalized or "ايجار" in text:
        return "للإيجار"
    if "للبيع" in normalized or "بيع" in normalized or "بيع" in text:
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
    # الدخل الإيجاري المذكور في الإعلان («مؤجر ب 1200 شهرياً»، «دخله 20 الف»…) —
    # أساس حساب العائد الإيجاري السنوي لِعروض البيع المؤجرة
    rental_income, rental_income_period = extract_rental_income(full_text)

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
    if transaction == "للإيجار" and price_value and price_value < 30:
        # إيجار شهري أقل من 30 د.ك رقم وهمي/عنصر نائب من المصدر (مثل "1" أو "20" في OpenSooq)
        # أو إعلان «للاتصال» بسعر مضلل. لا نخترع رقمًا بديلًا؛ نستبعد السعر من التقييم
        # حتى لا تظهر فرصة وهمية بأفضل صفقة.
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
        rental_income=rental_income,
        rental_income_period=rental_income_period,
        raw={
            "priceSource": (
                f"استخراج مباشر من صفحة {source}، والرقم عومل كألف د.ك لأنه بيع {property_type}"
                if inferred_thousands
                else f"رقم السعر منخفض وغير موثوق ({property_type} — {transaction})، لذلك لم يدخل في التقييم"
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


def _opensooq_items(body: str) -> list[dict[str, Any]]:
    """إعلانات السوق المفتوح من حمولة __NEXT_DATA__ المضمّنة في صفحة قائمة.

    تعيد عناصر العقارات فقط (cat1 RealEstate) — مستخدمة في البحث الحي والجرد
    الكامل معًا حتى لا يتكرر منطق الاستخراج.
    """
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', body, re.S)
    if not match:
        return []
    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    items: list[dict[str, Any]] = []
    for item in walk_dicts(next_data):
        if "title" not in item or "post_url" not in item:
            continue
        cat1 = str(item.get("cat1_code", ""))
        if cat1 and "RealEstate" not in cat1:
            continue
        items.append(item)
    return items


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
        seen_ids: set[str] = set()
        for item in _opensooq_items(body):
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


def scan_opensooq_inventory(
    *,
    max_pages: int = 6,
    max_total: int = 500,
    block_retries: int = 3,
    block_delay: float = 20.0,
) -> tuple[list[Listing], dict[str, Any]]:
    """مسح جرد كامل للسوق المفتوح: كل صفحات أقسام البيع والإيجار.

    صفحة OpenSooq الواحدة تعرض نحو 30 إعلانًا من كل أنواع العقارات (شقق/بيوت/
    فلل/أراضٍ/عمارات/تجاري) عبر قسمي property-for-sale و property-for-rent مع
    ترقيم صفحات. البحث الحي كان يقتطع الصفحة الأولى فقط (نحو 60 إعلانًا من
    القسمين)، فتُفقد بقية الجرد. هذا المسح يمشي صفحات القسمين حتى نهايتهما
    (أو سقف max_pages) ويزيل التكرار بالكود، فيتراكم جرد السوق المفتوح كاملًا
    في قاعدة المعرفة (market_listings) مثل بيانات الفريج المحلية تمامًا.
    """
    sections = [("property-for-sale", "للبيع"), ("property-for-rent", "للإيجار")]
    listings: list[Listing] = []
    seen_codes: set[str] = set()
    candidates = 0
    pages_read = 0
    max_ms = 0.0
    detail_notes: list[str] = []
    for section, transaction in sections:
        for page in range(1, max_pages + 1):
            # المسار الصحيح يحمل مقطع property/: /en/property/property-for-sale
            # (بدونه يعيد الموقع 410 Gone لأنه مسار غير موجود)
            url = f"https://kw.opensooq.com/en/property/{section}" + (f"?page={page}" if page > 1 else "")
            body, status, ms, error, attempts = fetch_url(url)
            max_ms = max(max_ms, ms)
            if not body or error:
                # حماية WAF عند OpenSooq (410/429...) تأتي وتذهب بنوافذ قصيرة —
                # نعيد محاولة الصفحة بانتظار متباعد (block_delay) قبل الاستسلام،
                # حتى يمر الحصاد في النافذة المسموحة غالبًا بدل إسقاط الجرد كاملًا.
                blocked = _is_transient_block(error) or (status in (410, 429, 503))
                note = (error or f"HTTP {status}")[:90]
                if blocked and page == 1:
                    waited = 0
                    for retry in range(block_retries):
                        time.sleep(block_delay)
                        waited += block_delay
                        body, status, ms, error, attempts = fetch_url(url)
                        max_ms = max(max_ms, ms)
                        if body and not error:
                            note = f"نجح بعد {int(waited)}ث انتظار"
                            break
                    else:
                        note = (error or f"HTTP {status}")[:90]
                if not body or error:
                    if len(detail_notes) < 2:
                        detail_notes.append(f"{section} p{page}: {note}")
                    break
            items = _opensooq_items(body)
            candidates += len(items)
            pages_read += 1
            new_on_page = 0
            for item in items:
                code = "OS-" + str(item.get("id") or item.get("post_url", "").rstrip("/").split("/")[-1])
                if code in seen_codes:
                    continue
                seen_codes.add(code)
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
                    transaction=transaction,
                    fallback_type=opensooq_type_from_item(item, ""),
                )
                listings.append(listing)
                new_on_page += 1
                if len(listings) >= max_total:
                    break
            if new_on_page == 0 or len(listings) >= max_total:
                break
            # مسافة قصيرة بين الصفحات — نزور الموقع برفق ولا نستفز حماية WAF
            time.sleep(0.8)
        if len(listings) >= max_total:
            break
    status = "success" if listings else ("no_results" if pages_read else "failed")
    note_parts = [f"مسح {pages_read} صفحة", f"جرد {len(listings)} إعلانًا"]
    note_parts.extend(detail_notes)
    return listings, {
        "name": "OpenSooq (جرد كامل)",
        "status": status,
        "records": len(listings),
        "candidates": candidates,
        "attempts": 0,
        "responseMs": round(max_ms, 1),
        "url": "https://kw.opensooq.com/en/property/property-for-sale (+ ترقيم الصفحات)",
        "note": "، ".join(note_parts),
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


def _detail_fields(body: str) -> dict[str, Any]:
    """استخراج السعر والمساحة والمنطقة والمحافظة والهاتف من صفحة تفاصيل إعلان.

    الوسوم الوصفية أولًا ثم JSON-LD ثم نص صريح — لكل حقل على حدة حتى يكتمل
    الإعلان من صفحة التفاصيل عندما لا تحمل القائمة السابقة الحقل. الهاتف يُستخرج
    من روابط wa.me/tel ومن JSON المضمّن (4Sale) ومن نص الصفحة (Mourjan).
    """
    price, space = _detail_price_space(body)
    area, governorate = _detail_place(body)
    phone = _detail_phone(body)
    fields: dict[str, Any] = {}
    if price is not None:
        fields["price"] = price
    if space is not None:
        fields["space"] = space
    if area:
        fields["area"] = area
    if governorate:
        fields["governorate"] = governorate
    if phone:
        fields["phone"] = phone
    return fields


# أرقام معروفة لدعم المواقع (ليست أرقام معلنين) — تُستبعد من الاستخراج دائمًا
_SUPPORT_PHONES: set[str] = {
    "9651844474",  # 4Sale الهاتف الساخن
    "96522260016",  # OpenSooq الكويت
    "9651844555",  # Mourjan/غيرها من الخطوط الساخنة العامة إن ظهرت
}


def _normalize_phone(raw: Any) -> str:
    """تطبيع رقم كويتي إلى E.164 (+965xxxxxxxx) مع تجاهل أرقام الدعم."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return ""
    # أرقام الدعم المعروفة — ليست أرقام معلنين
    if digits in _SUPPORT_PHONES:
        return ""
    if digits.startswith("00965"):
        digits = digits[5:]
    if digits.startswith("965") and len(digits) == 11:
        return "+" + digits
    if len(digits) == 8 and digits[0] in "569":
        return "+965" + digits
    return ""


def _detail_phone(body: str) -> str:
    """استخراج رقم تواصل المعلن من صفحة تفاصيل إعلان.

    الترتيب (الأكثر صرامة أولًا):
      1) روابط واتساب المباشرة wa.me/<رقم> (Q8Aqar يضعها صراحة في الصفحة),
      2) روابط اتصال tel:+<رقم> (Mourjan),
      3) JSON مضمّن بمفاتيح phone/contacts/mobile (4Sale يضع رقم البائع فيه),
      4) نمط رقم كويتي محمول في النص الصريح للصفحة.
    يعيد الرقم بصيغة E.164 أو سلسلة فارغة إذا لم يوجد رقم معلن.
    """
    # 1) wa.me — أوضح إشارة لرقم معلن
    for match in re.finditer(r"wa\.me/(\+?[0-9\s-]{8,16})", body, re.I):
        normalized = _normalize_phone(match.group(1))
        if normalized:
            return normalized
    # 2) tel: — روابط اتصال مباشرة
    for match in re.finditer(r"tel:([0-9+\s-]{8,16})", body, re.I):
        normalized = _normalize_phone(match.group(1))
        if normalized:
            return normalized
    # 3) JSON مضمّن: phone / contacts / mobile (4Sale …)
    for key in ("phone", "contacts", "mobile", "mobile_number", "phone_number"):
        for match in re.finditer(r'"' + key + r'"\s*:\s*("[^"]{6,24}"|\[[^\]]{6,160}\])', body, re.I):
            raw = match.group(1)
            values: list[str] = []
            if raw.startswith("["):
                values = re.findall(r'"([0-9+\s-]{6,24})"', raw)
            else:
                values = [raw.strip('"')]
            for value in values:
                normalized = _normalize_phone(value)
                if normalized:
                    return normalized
    # 4) نمط محمول كويتي في النص الصريح بشرط سياق اتصال قريب (اتصل/جوال/واتساب/…)
    #    — يمنع التقاط أرقام إعلانات مشابهة مذكورة في نفس الصفحة
    text = clean_text(body)
    for match in re.finditer(r"(?:\+?965[\s-]?)?[569]\d{7}", text):
        window = text[max(0, match.start() - 90):match.end()]
        if re.search(r"اتصل|جوال|هاتف|واتساب|للتواصل|تواصل|mobile|whatsapp|phone|call", window, re.I):
            normalized = _normalize_phone(match.group(0))
            if normalized:
                return normalized
    return ""


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


def _detail_place(body: str) -> tuple[str, str]:
    """استخراج المنطقة والمحافظة من صفحة تفاصيل إعلان (JSON-LD address ثم وسوم ثم نص صريح)."""
    area = ""
    governorate = ""
    # JSON-LD address هو الأكثر دقة (addressLocality/addressRegion)
    for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        for node in walk_dicts(data):
            if not isinstance(node, dict):
                continue
            addr = node.get("address") or {}
            if not isinstance(addr, dict):
                continue
            locality = str(addr.get("addressLocality") or addr.get("addressRegion") or "")
            if locality and not area:
                area = detect_area(locality)
            region = str(addr.get("addressRegion") or "")
            if region and not governorate:
                governorate = _detail_governorate(region)
    # وسوم العنوان (og:title / title) تكمل ما لم يظهر في JSON-LD
    if not area or not governorate:
        for pattern in (
            r'property="og:title"\s+content="([^"]+)"',
            r'<title[^>]*>(.*?)</title>',
        ):
            match = re.search(pattern, body, re.I | re.S)
            if not match:
                continue
            title_text = clean_text(match.group(1))
            if not area:
                area = detect_area(title_text)
            if not governorate:
                governorate = _detail_governorate(title_text)
            if area and governorate:
                break
    return area, governorate


def _detail_governorate(text: str) -> str:
    """محافظة كويتية من نص إنجليزي/عربي (العاصمة/حولي/الفروانية/الأحمدي/الجهراء/مبارك الكبير)."""
    lowered = text.lower()
    for key, gov in (
        (("al-asimah", "capital", "kuwait city", "كويت سيتي"), "محافظة العاصمة"),
        (("hawally", "hawalli", "حولي", "السالمية", "الجابرية", "الرميثية", "بيان", "سلوى"), "محافظة حولي"),
        (("farwaniya", "الفروانية", "خيطان", "الفردوس", "الرابية", "العارضية"), "محافظة الفروانية"),
        (("ahmadi", "الأحمدي", "الفحيحيل", "المهبولة", "الوفرة"), "محافظة الأحمدي"),
        (("jahra", "الجهراء", "المطلاع", "القصر", "النعيم"), "محافظة الجهراء"),
        (("mubarak", "مبارك الكبير", "صباح السالم", "أبو فطيرة", "القرين"), "محافظة مبارك الكبير"),
    ):
        if any(token in lowered for token in key):
            return gov
    return ""


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


def enrich_listings_from_details(
    listings: list[Listing],
    *,
    max_pages: int = 10,
    workers: int = 4,
) -> dict[str, Any]:
    """وكيل إكمال التفاصيل: يقرأ صفحة تفاصيل كل إعلان ناقص لاستكمال الحقول المفقودة.

    الإعلانات القادمة من صفحات القوائم (Q8Aqar/Mourjan/OpenSooq/…) كثيرًا ما تفتقر
    للسعر أو المساحة أو المنطقة لأن قائمة البحث تعرض ملخصًا فقط. هذا الوكيل:
      1) يحدد الإعلانات التي ينقصها سعر أو مساحة أو منطقة أو محافظة،
      2) يجلب صفحة التفاصيل الخاصة بها بالتوازي (حد أقصى max_pages لئلا يطيل زمن التحليل)،
      3) يستخرج الحقول الناقصة من الصفحة (وسوم + JSON-LD + نص صريح)،
      4) يحدّث الإعلان في مكانه حتى تكتمل بياناته قبل المطابقة بالفلاتر والتقييم،
      5) يوثّق ما اكتمل في listing.raw["enrichedFromDetails"] ليكون شفافًا في التقرير.

    يعيد إحصائية: كم صفحة قُرئت، كم إعلان اكتمل، وما الحقول المستكملة، وما فشل.
    """
    incomplete = [
        listing for listing in listings
        if listing.original_url
        and (
            not listing.price
            or not listing.space
            or not listing.area
            or not listing.governorate
            or not listing.phone
        )
    ]
    if not incomplete:
        return {"status": "no_data", "read": 0, "enriched": 0, "fields": {}, "failed": 0, "note": "كل الإعلانات مكتملة — لا حاجة لقراءة تفاصيل."}
    # أولوية المصادر التي تعرض هاتف المعلن في صفحة التفاصيل (Q8Aqar/Mourjan/4Sale…)
    # حتى تُستنفد ميزانية القراءة اليومية على ما يعطي هاتفًا فعلًا، بينما يبقى
    # OpenSooq (الرقم خلف زر كشف) آخر الخيارات إن وُسِّعت الميزانية مستقبلًا.
    phone_sources = ("Q8Aqar", "Mourjan", "4Sale", "بوعقار", "Bu3qar", "السوق المباشر")
    incomplete.sort(key=lambda listing: 0 if any(s in listing.source for s in phone_sources) else 1)
    targets = incomplete[:max_pages]

    def _fetch_one(listing: Listing) -> tuple[Listing, dict[str, Any]]:
        body, _status, _ms, error, _attempts = fetch_url(listing.original_url)
        if not body or error:
            return listing, {"error": error or "صفحة فارغة"}
        return listing, _detail_fields(body)

    results: list[tuple[Listing, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for listing, fields in pool.map(_fetch_one, targets):
            results.append((listing, fields))

    fields_filled: dict[str, int] = {}
    enriched = 0
    failed = 0
    for listing, fields in results:
        if fields.get("error"):
            failed += 1
            continue
        changed: list[str] = []
        if not listing.price and fields.get("price"):
            listing.price = float(fields["price"])
            listing.price_text = f"{listing.price:,.0f} د.ك"
            changed.append("price")
        if not listing.space and fields.get("space"):
            listing.space = float(fields["space"])
            changed.append("space")
        if not listing.area and fields.get("area"):
            listing.area = str(fields["area"])
            changed.append("area")
        if not listing.governorate and fields.get("governorate"):
            listing.governorate = str(fields["governorate"])
            changed.append("governorate")
        if not listing.phone and fields.get("phone"):
            listing.phone = str(fields["phone"])
            changed.append("phone")
        if changed:
            enriched += 1
            for field in changed:
                fields_filled[field] = fields_filled.get(field, 0) + 1
            raw = dict(listing.raw or {})
            raw["enrichedFromDetails"] = {
                "fields": changed,
                "url": listing.original_url,
                "note": "أُكملت الحقول الناقصة من صفحة تفاصيل الإعلان نفسها.",
            }
            listing.raw = raw

    parts = [f"قراءة {len(targets)} صفحة تفاصيل"]
    if enriched:
        parts.append(f"اكتمل {enriched} إعلان")
    if fields_filled:
        labels = {"price": "سعر", "space": "مساحة", "area": "منطقة", "governorate": "محافظة", "phone": "هاتف"}
        filled = ", ".join(f"{labels.get(k, k)}: {v}" for k, v in sorted(fields_filled.items()))
        parts.append(f"({filled})")
    if failed:
        parts.append(f"فشل {failed} صفحة")
    return {
        "status": "success" if enriched else ("failed" if failed else "no_data"),
        "read": len(targets),
        "enriched": enriched,
        "fields": fields_filled,
        "failed": failed,
        "note": "، ".join(parts),
    }


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


# 4Sale انتقلت إلى نطاق q84sale.com (النطاقات القديمة kuwait.4sale.com / 4sale.com.kw
# محجوبة أو منتهية DNS). العقارات تُقرأ من صفحات /en/property/{1..n} (75 إعلانًا لكل
# صفحة) مع فحص DNS سريع قبل الجلب حتى لا تُهدر عشرات الثواني على نطاق ميت.
_FOUR_SALE_BASE = "https://www.q84sale.com"
_FOUR_SALE_HOST = "www.q84sale.com"
_FOUR_SALE_PAGES = 3  # صفحات 1..3 — نحو 225 إعلانًا يفلترها مسار المطابقة حسب منطقة الطلب


def search_four_sale(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """منصة 4Sale الكويتية (q84sale.com) بفحص روابط HTML، مع بديل OpenSooq عند التعذر.

    احترافيًا: يُفحص DNS للنطاق أولًا — إن لم يُحل (حجب جغرافي/نطاق ميت) نفشل فورًا
    نحو البديل بدل انتظار مهلات الجلب (كانت 31.8 ثانية على نطاق ميت). عند نجاح DNS
    تُقرأ صفحات العقارات العامة (1..3) وتُفلتر لاحقًا حسب منطقة الطلب.
    """
    started = time.perf_counter()
    try:
        socket.gethostbyname(_FOUR_SALE_HOST)
    except Exception as dns_error:
        return _four_sale_fallback(request, f"DNS: {dns_error}", round((time.perf_counter() - started) * 1000, 1), 0)

    url = f"{_FOUR_SALE_BASE}/en/property/1"
    listings: list[Listing] = []
    candidates = 0
    attempts = 0
    error: str | None = None
    ms = 0.0
    for page in range(1, _FOUR_SALE_PAGES + 1):
        page_url = f"{_FOUR_SALE_BASE}/en/property/{page}"
        body, status, page_ms, page_error, page_attempts = fetch_url(page_url)
        attempts += page_attempts
        ms += page_ms
        if page_error:
            error = page_error
            break
        page_listings, page_candidates = _scan_link_listings(
            request,
            source="4Sale",
            base_url=_FOUR_SALE_BASE,
            body=body,
            href_pattern=r'<a[^>]*href="(/en/listing/[^"]+)"[^>]*>(.*?)</a>',
            code_prefix="4S",
        )
        candidates += page_candidates
        listings.extend(page_listings)
        if not page_candidates:
            break  # آخر صفحة متاحة — لا مزيد من الصفحات

    # إزالة التكرار عبر الصفحات (الإعلانات المثبّتة تظهر في أكثر من صفحة)
    seen_codes: set[str] = set()
    unique: list[Listing] = []
    for listing in listings:
        if listing.code in seen_codes:
            continue
        seen_codes.add(listing.code)
        unique.append(listing)
    listings = unique

    if error and not listings:
        return _four_sale_fallback(request, error, round(ms, 1), attempts)
    return listings[:50], _link_search_result(
        "4Sale", listings, candidates, round(ms, 1), url, error, body,
        f"تم فحص {candidates} إعلانًا في 4Sale ({_FOUR_SALE_BASE}).", attempts,
    )


def _four_sale_fallback(request: PropertyRequest, reason: str, ms: float, attempts: int) -> tuple[list[Listing], dict[str, Any]]:
    """مصدر بديل (OpenSooq) عند تعذر 4Sale، مع تقرير شفاف بالسبب والبديل."""
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
            "url": f"{_FOUR_SALE_BASE}/en/latest/property/0",
            "note": (
                f"تعذر الوصول إلى 4Sale ({reason}) — استُخدم المصدر البديل {fb_name} "
                f"بنفس شروط البحث وأسفر عن {len(fb_listings)} نتيجة مطابقة (معلّمة في بيانات النتيجة)."
            ),
        }
    return [], {
        "name": "4Sale",
        "status": "failed",
        "records": 0,
        "candidates": 0,
        "attempts": attempts,
        "responseMs": ms,
        "url": f"{_FOUR_SALE_BASE}/en/latest/property/0",
        "note": f"تعذر الوصول إلى 4Sale ({reason})، والمصدر البديل {fb_name} فشل أيضًا ({fb_status.get('note', '')}).",
    }


# ---------------------------------------------------------------------------
# إعلانات «مطلوب» في 4Sale: قسم مخصص للطلبات (مطلوب عقار للبيع/للإيجار)
# ---------------------------------------------------------------------------
# 4Sale هو المصدر الخارجي الوحيد بين المنصات المحصودة الذي ينشر قسمًا مخصصًا
# لإعلانات الطلب («مطلوب عقار للبيع» / «مطلوب عقار للإيجار») — OpenSooq وQ8Aqar
# لا يملكان فئة «مطلوب» (تحقق فعلي من الصفحات). تُصنَّف هذه الإعلانات
# «مطلوب للشراء/للإيجار» صراحةً حسب القسم فتدخل في مؤشرات الطلب (demand) مع
# بيانات الفريج المحلية بدل أن تُفقد أو تُعدّ عروضًا.
_FOUR_SALE_WANTED_SECTIONS: list[tuple[str, str]] = [
    ("wanted-property-for-sale", "مطلوب للشراء"),
    ("wanted-property-for-rent", "مطلوب للإيجار"),
]
_FOUR_SALE_WANTED_PAGES = 3  # صفحات 1..3 من كل قسم طلب


def _four_sale_wanted_from_page(
    body: str,
    transaction: str,
    seen_codes: set[str],
    max_total: int,
) -> tuple[list[Listing], int]:
    """استخراج إعلانات «مطلوب» من صفحة 4Sale لقسم محدد — دالة نقية قابلة للاختبار.

    تُصنَّف المعاملة صراحةً حسب القسم (مطلوب للشراء/للإيجار) لا بالاعتماد على
    عنوان الإعلان: عناوين الطلب قد لا تحمل «للبيع/للإيجار» صراحةً (مثل
    «مطلوب شقة في السالمية»)، والتصنيف الخاطئ كان سيجعلها تظهر كعروض.
    """
    listings: list[Listing] = []
    candidates = 0
    for href, title_html in re.findall(r'<a[^>]*href="(/ar/listing/[^"]+)"[^>]*>(.*?)</a>', body, re.S | re.I):
        candidates += 1
        title_clean = clean_text(title_html)
        if not title_clean or len(title_clean) < 5:
            continue
        code = f"4S-{href.rstrip('/').split('/')[-1]}"
        if code in seen_codes:
            continue
        seen_codes.add(code)
        listing = listing_from_text(
            source="4Sale",
            code=code,
            url=urllib.parse.urljoin(_FOUR_SALE_BASE, href),
            title=title_clean,
            description=title_clean,
            price=extract_price_from_title(title_clean) or parse_price(title_clean),
            transaction=transaction,
            fallback_type="عقارات",
            space_override=extract_space_from_title(title_clean),
        )
        listing.raw = {**(getattr(listing, "raw", None) or {}), "demandSection": transaction}
        listings.append(listing)
        if len(listings) >= max_total:
            break
    return listings, candidates


def scan_four_sale_wanted(
    *,
    max_pages: int = _FOUR_SALE_WANTED_PAGES,
    max_total: int = 200,
) -> tuple[list[Listing], dict[str, Any]]:
    """مسح جرد «مطلوب» في 4Sale: قسمي طلبات الشراء والإيجار (صفحات 1..n).

    يعيد إعلانات الطلب المنشورة (تُحفظ في market_listings كطلبات) مع حالة مصدر
    موحدة. DNS ميت → فشل فوري بنفس نمط search_four_sale.
    """
    started = time.perf_counter()
    try:
        socket.gethostbyname(_FOUR_SALE_HOST)
    except Exception as dns_error:
        return [], _link_search_result(
            "4Sale (مطلوب)", [], 0, round((time.perf_counter() - started) * 1000, 1),
            f"{_FOUR_SALE_BASE}/ar/property/for-sale/wanted-property-for-sale/1",
            f"DNS: {dns_error}", "",
            "تعذر الوصول إلى 4Sale — DNS لا يحل النطاق.", 0,
        )

    listings: list[Listing] = []
    seen_codes: set[str] = set()
    candidates = 0
    pages_read = 0
    max_ms = 0.0
    first_url = ""
    last_body = ""
    for section, transaction in _FOUR_SALE_WANTED_SECTIONS:
        for page in range(1, max_pages + 1):
            url = f"{_FOUR_SALE_BASE}/ar/property/{section}/{page}"
            first_url = first_url or url
            body, status, ms, error, attempts = fetch_url(url)
            max_ms = max(max_ms, ms)
            if not body or error:
                break
            pages_read += 1
            last_body = body
            page_listings, page_candidates = _four_sale_wanted_from_page(
                body, transaction, seen_codes, max_total - len(listings)
            )
            candidates += page_candidates
            listings.extend(page_listings)
            if len(listings) >= max_total:
                break
        if len(listings) >= max_total:
            break
    note = (
        f"تم مسح {pages_read} صفحة في قسمي «مطلوب» بـ 4Sale — {len(listings)} طلبًا "
        f"(شراء/إيجار) منشورًا يُحتسب في مؤشر الطلب."
    )
    return listings, _link_search_result(
        "4Sale (مطلوب)", listings, candidates, round(max_ms, 1), first_url, None, last_body, note, pages_read,
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


# ─── Yebtah (منصة كويتية حديثة — بيانات ItemList منظمة بلا REST عام) ─────────

# أسماء Yebtah إنجليزية («in Salmiya, Hawalli - 45,000 KWD») — نحولها لعربية
# حتى تطابق فلاتر المنطقة/المحافظة وتدخل في التقييم والمقارنات مثل باقي المصادر.
YEBTAH_GOVERNORATES: dict[str, str] = {
    "Hawalli": "محافظة حولي",
    "Al Asimah": "محافظة العاصمة",
    "Asimah": "محافظة العاصمة",
    "Jahra": "محافظة الجهراء",
    "Ahmadi": "محافظة الأحمدي",
    "Farwaniya": "محافظة الفروانية",
    "Mubarak Al-Kabeer": "محافظة مبارك الكبير",
    "Mubarak Al Kabeer": "محافظة مبارك الكبير",
}

YEBTAH_AREAS: dict[str, str] = {
    "Salmiya": "السالمية",
    "Hawalli": "حولي",
    "Jabriya": "الجابرية",
    "Salwa": "سلوى",
    "Bayan": "بيان",
    "Al-Mutlaa": "المطلاع",
    "Mutlaa": "المطلاع",
    "Sabah Al-Ahmad City": "صباح الأحمد",
    "Sabah Al-Ahmad": "صباح الأحمد",
    "Jahra": "الجهراء",
    "Ahmadi": "الأحمدي",
    "Fahaheel": "الفحيحيل",
    "Farwaniya": "الفروانية",
    "Khaitan": "خيطان",
    "Qurtuba": "قرطبة",
    "Mishrif": "مشرف",
    "Salam": "سلام",
    "Rumaithiya": "الرميثية",
    "Dasma": "الدسمة",
    "Sharq": "الشرق",
    "Bnaid Al-Qar": "بنيد القار",
    "Sabah Al-Salem": "صباح السالم",
    "Ferdous": "الفردوس",
    "North West Sulaibikhat": "شمال غرب الصليبيخات",
    "Adan": "العدان",
    "Abu Fatira": "أبو فطيرة",
    "Funaitis": "فنطاس",
    "Naeem": "نعيم",
    "Ardiya": "العارضية",
    "Sulaibiya": "الصليبية",
    "Sabhan": "صبحان",
    "Rai": "الراي",
}


def _yebtah_place(name: str) -> tuple[str, str]:
    """استخراج (منطقة عربية، محافظة عربية) من «… in Salmiya, Hawalli - 45,000 KWD»."""
    match = re.search(r"\bin\s+([^,]+?)\s*,\s*([^,-]+)", name, re.I)
    if not match:
        return "", ""
    area_en = match.group(1).strip()
    gov_en = match.group(2).strip()
    return YEBTAH_AREAS.get(area_en, area_en), YEBTAH_GOVERNORATES.get(gov_en, "")


def _yebtah_type(name: str, fallback: str) -> str:
    lowered = name.lower()
    if any(word in lowered for word in ("apartment", "duplex", "flat", "studio")):
        return "شقة"
    if any(word in lowered for word in ("land", "plot", "ground")):
        return "أرض"
    if any(word in lowered for word in ("building", "tower", "shop", "office", "floor", "commercial")):
        return "عمارة"
    if any(word in lowered for word in ("villa", "house", "chalet", "home", "farm")):
        return "بيت"
    return fallback or "عقارات"


def _yebtah_transaction(name: str, fallback: str) -> str:
    lowered = name.lower()
    if "for rent" in lowered:
        return "للإيجار"
    if "for sale" in lowered:
        return "للبيع"
    return fallback


def _yebtah_price(name: str) -> float | None:
    match = re.search(r"-\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*KWD", name, re.I)
    return float(match.group(1).replace(",", "")) if match else None


def _yebtah_bedrooms(name: str) -> int | None:
    """عدد غرف النوم من «6-Bed Chalet …» أو «Studio»."""
    match = re.search(r"(\d+)\s*-?\s*bed", name, re.I)
    if match:
        return int(match.group(1))
    if "studio" in name.lower():
        return 0
    return None


def _yebtah_arabic_summary(
    name: str,
    transaction: str,
    area_ar: str,
    gov_ar: str,
    price: float | None,
    fallback_type: str,
) -> str:
    """بناء وصف عربي مقروء من بيانات Yebtah بدل العنوان الإنجليزي الخام
    («6-Bed Chalet For Sale in Ahmadi …» ← «شاليه 6 غرف للبيع في الأحمدي — 95,000 د.ك»)."""
    prop_type = _yebtah_type(name, fallback_type)
    beds = _yebtah_bedrooms(name)
    parts = [prop_type]
    if beds is not None:
        parts.append(f"{beds} غرفة" if beds > 0 else "استوديو")
    parts.append(transaction or "")
    location_parts = [part for part in (area_ar, gov_ar) if part]
    if location_parts:
        parts.append("في " + "، ".join(location_parts))
    summary = "، ".join(part for part in parts if part)
    if price:
        # نفس قاعدة التحويل في listing_from_text: بيع بيت/أرض/عمارة بأقل من 10 آلاف
        # يُفهم كألف د.ك (المصادر تكتب «95 KWD» وتعني 95,000) — نعرض السعر الفعلي الموحّد
        display_price = price
        if transaction == "للبيع" and prop_type in {"بيت", "أرض", "عمارة"} and price < 10_000:
            display_price = price * 1000
        summary += f" — {display_price:,.0f} د.ك"
    return summary or clean_text(name)[:200]


def _fetch_yebtah_page(mode: str, fallback_transaction: str) -> tuple[list[Listing], dict[str, Any]]:
    """جلب صفحة Yebtah (for_sale/for_rent) وتحويل كروت ItemList إلى إعلانات."""
    url = f"https://yebtah.com/en/{mode}"
    body, status, ms, error, attempts = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0
    if body:
        for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("@type") != "ItemList":
                continue
            for element in data.get("itemListElement", []):
                item = element.get("item", element) if isinstance(element, dict) else {}
                name = str(item.get("name") or "").strip()
                href = str(item.get("url") or "").strip()
                if not name or not href:
                    continue
                candidates += 1
                code = "YEB-" + href.rstrip("/").split("/")[-1]
                transaction = _yebtah_transaction(name, fallback_transaction)
                area_ar, gov_ar = _yebtah_place(name)
                price = _yebtah_price(name)
                # العنوان الإنجليزي الخام لا يفيد المستخدم — نبني وصفًا عربيًا مقروءًا
                # («شاليه 6 غرف للبيع في الأحمدي — 95,000 د.ك») مع حفظ النص الأصلي للدليل.
                arabic = _yebtah_arabic_summary(name, transaction, area_ar, gov_ar, price, "")
                listing = listing_from_text(
                    source="Yebtah",
                    code=code,
                    url=href,
                    title=arabic,
                    description=arabic,
                    price=price,
                    transaction=transaction,
                    fallback_type=_yebtah_type(name, ""),
                )
                # المنطقة/المحافظة إنجليزية في الاسم → نملأ العربية المعادلة للفلاتر والتقييم
                listing.area = area_ar or listing.area
                listing.governorate = gov_ar or listing.governorate
                # النص الإنجليزي الأصلي يُحفظ كدليل وليس كملخص معروض
                listing.raw = dict(listing.raw or {})
                listing.raw["originalTitle"] = name
                listings.append(listing)
    return listings, {
        "status": "success" if listings else ("no_results" if not error else "failed"),
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
        "responseMs": ms,
        "url": url,
        "note": error or "بيانات ItemList منظمة (الاسم + رابط التفاصيل) — المنطقة/المحافظة معرّبة للمطابقة.",
    }


def search_yebtah(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """Yebtah — منصة كويتية حديثة (yebtah.com) بلا REST API عام.

    صفحتا /en/for_sale و /en/for_rent تعرضان ItemList منظمًا فيه كل إعلان اسمه
    (مثل «6-Bed Villa For Sale in Sharq, Al Asimah - 45,000 KWD») ورابط تفاصيله.
    الطلب المحدد (بيع/إيجار) يجلب الصفحة المناسبة؛ الطلب العريض (حصاد يومي)
    يجلب الصفحتين لتراكم إعلانات البيع والإيجار معًا في market_listings.
    """
    transaction = transaction_from_request(request)
    modes = ["for_rent"] if transaction == "للإيجار" else (["for_sale", "for_rent"] if not request.raw_text.strip() and not request.transaction else ["for_sale"])
    # الطلب العريض (حصاد يومي فارغ): لا نفلتر بالمعاملة حتى تراكم البيع والإيجار معًا
    is_broad = not request.raw_text.strip() and not request.transaction and not request.areas and not request.property_type
    merged: list[Listing] = []
    seen: set[str] = set()
    candidates = 0
    attempts = 0
    ms_total = 0.0
    first_url = ""
    errors: list[str] = []
    for mode in modes:
        listings, status = _fetch_yebtah_page(mode, transaction)
        candidates += status.get("candidates", 0) or 0
        attempts = max(attempts, status.get("attempts") or 0)
        ms_total += status.get("responseMs") or 0
        first_url = first_url or status.get("url") or ""
        if status.get("status") == "failed":
            errors.append(str(status.get("note") or ""))
        for listing in listings:
            if listing.code in seen:
                continue
            seen.add(listing.code)
            if is_broad or request_matches_listing(request, listing):
                merged.append(listing)
    return merged[:80], {
        "name": "Yebtah",
        "status": "success" if merged else ("no_results" if not errors else "failed"),
        "records": len(merged),
        "candidates": candidates,
        "attempts": attempts,
        "responseMs": ms_total,
        "url": first_url,
        "note": " | ".join(errors) if errors else (
            "بيانات ItemList منظمة من صفحات Yebtah (بيع وإيجار عند الحصاد العريض) مع روابط التفاصيل."
        ),
    }


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


# --- المنصات المرشحة (Property Finder / Aqarmap / Bayut) ---
# منصات عقارية كويتية معروفة لكنها غير متاحة حاليًا للجلب البرمجي من شبكات
# الخوادم (حجب جغرافي/مهلة، توقف خدمة، أو حماية captcha). الموصلات مكتوبة
# بنفس نمط بقية المصادر وتُحاول الجلب فعليًا عبر fetch_url وتستخرج عند توفر
# الوصول، وتسجّل حالتها الحقيقية بشفافية بدل ادعاء نجاح وهمي. سجل الحجب يمنع
# إعادة المحاولة المتكررة داخل نافذة زمنية حتى لا تُبطئ عمليات البحث المتكررة
# بانتظار منصات متعثرة، ثم تنتهي النافذة فيُعاد الفحص تلقائيًا.
_CANDIDATE_MEMO: dict[str, tuple[float, dict[str, Any]]] = {}
_CANDIDATE_LOCK = threading.Lock()
CANDIDATE_MEMO_SECONDS = 30 * 60  # نافذة الحجب بين فحصين للمنصة المتعثرة


def _candidate_attempt(
    name: str,
    url: str,
    request: PropertyRequest,
    parse: Callable[[str, PropertyRequest], tuple[list[Listing], int, dict[str, Any] | None]],
) -> tuple[list[Listing], dict[str, Any]]:
    """محاولة جلب منصة مرشحة مع سجل حجب قصير العمر.

    - الاستدعاء داخل نافذة الحجب يعيد حالة المسجَّلة فورًا (لا إعادة فحص).
    - الفشل الفعلي يُسجَّل في الذاكرة بنافذة 30 دقيقة ثم يُعاد الفحص تلقائيًا —
      فبمجرد توفر الوصول تبدأ النتائج في دخول البحث والتقييم وقاعدة المعرفة
      دون أي تدخل يدوي.
    - parse تعيد (قائمة الإعلانات، عدد المرشحين، حالة قسرية أو None). الحالة
      القسرية (مثل «discontinued» عند عودة بوابة أخرى) تُسجَّل كما هي.
    """
    with _CANDIDATE_LOCK:
        memo = _CANDIDATE_MEMO.get(name)
        if memo and time.time() - memo[0] < CANDIDATE_MEMO_SECONDS:
            st = dict(memo[1])
            st["note"] = st.get("note", "") + " (إعادة فحص أثناء سجل الحجب)"
            return [], st
    body, status, ms, error, attempts = fetch_url(url)
    listings: list[Listing] = []
    candidates = 0
    forced: dict[str, Any] | None = None
    if body:
        listings, candidates, forced = parse(body, request)
        if forced is None:
            lowered = body[:4000].lower()
            if any(token in lowered for token in ("captcha", "challenge", "access denied")):
                forced = {
                    "name": name,
                    "status": "blocked",
                    "records": 0,
                    "candidates": candidates,
                    "attempts": attempts,
                    "responseMs": ms,
                    "url": url,
                    "note": "حماية captcha/تحدٍ من الموقع تمنع القراءة البرمجية حاليًا.",
                }
    if forced is not None:
        forced.setdefault("name", name)
        forced.setdefault("attempts", attempts)
        forced.setdefault("responseMs", ms)
        forced.setdefault("url", url)
        with _CANDIDATE_LOCK:
            _CANDIDATE_MEMO[name] = (time.time(), forced)
        return [], forced
    if not body or error:
        reason = error or f"HTTP {status}"
        st = {
            "name": name,
            "status": "blocked",
            "records": 0,
            "candidates": candidates,
            "attempts": attempts,
            "responseMs": ms,
            "url": url,
            "note": f"غير متاح حاليًا من الشبكة الخادمة ({reason[:110]}). يُعاد الفحص تلقائيًا في التحديث اليومي.",
        }
        with _CANDIDATE_LOCK:
            _CANDIDATE_MEMO[name] = (time.time(), st)
        return [], st
    with _CANDIDATE_LOCK:
        _CANDIDATE_MEMO.pop(name, None)
    return listings[:50], {
        "name": name,
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "candidates": candidates,
        "attempts": attempts,
        "responseMs": ms,
        "url": url,
        "note": (
            f"تم استخراج {len(listings)} إعلانًا من بيانات الصفحة."
            if listings
            else "الصفحة متاحة لكن لا نتائج مطابقة للطلب."
        ),
    }


def _jsonld_real_estate_nodes(body: str) -> list[dict[str, Any]]:
    """عقد عقارية منظمة (RealEstateListing/Product/Offer) من حمولات JSON-LD مع إزالة التكرار بالرابط."""
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_json in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        for node in walk_dicts(data):
            if not isinstance(node, dict):
                continue
            node_type = node.get("@type")
            if isinstance(node_type, list):
                node_type = node_type[0] if node_type else ""
            if str(node_type) not in ("RealEstateListing", "Product", "Offer"):
                continue
            item_url = str(node.get("url") or "")
            if not item_url:
                continue
            if item_url in seen:
                continue
            seen.add(item_url)
            nodes.append(node)
    return nodes


def _listing_from_jsonld_node(
    request: PropertyRequest,
    *,
    source: str,
    node: dict[str, Any],
    code_prefix: str,
) -> Listing:
    """Listing من عقدة JSON-LD (RealEstateListing/Product) بنفس قواعد بقية المصادر."""
    item_url = str(node.get("url") or "")
    offer = node.get("offers")
    price_raw = None
    if isinstance(offer, dict):
        price_raw = offer.get("price")
    elif isinstance(offer, list) and offer:
        first = offer[0]
        price_raw = first.get("price") if isinstance(first, dict) else None
    if price_raw is None:
        price_raw = node.get("price")
    code = f"{code_prefix}-{item_url.rstrip('/').split('/')[-1]}"
    return listing_from_text(
        source=source,
        code=code,
        url=item_url,
        title=str(node.get("name") or ""),
        description=str(node.get("description") or ""),
        price=float(price_raw) if price_raw not in (None, "") else None,
        transaction=transaction_from_request(request),
        fallback_type=request.property_type,
    )


def search_propertyfinder(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """Property Finder Kuwait — يحاول صفحات البحث ويستخرج إعلانات JSON-LD عند توفر الوصول."""
    mode = "rent" if transaction_from_request(request) == "للإيجار" else "buy"
    query = (" ".join(request.areas) or request.raw_text or "").strip()
    url = f"https://www.propertyfinder.kw/en/{mode}?l=1&ob=pd&q={urllib.parse.quote(query)}"

    def _parse(body: str, req: PropertyRequest) -> tuple[list[Listing], int, dict[str, Any] | None]:
        nodes = _jsonld_real_estate_nodes(body)
        listings: list[Listing] = []
        seen: set[str] = set()
        for node in nodes:
            listing = _listing_from_jsonld_node(req, source="PropertyFinder", node=node, code_prefix="PF")
            if listing.code in seen:
                continue
            seen.add(listing.code)
            if request_matches_listing(req, listing):
                listings.append(listing)
        return listings, len(nodes), None

    return _candidate_attempt("PropertyFinder", url, request, _parse)


def search_aqarmap(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """Aqarmap Kuwait — يتحقق من هوية الصفحة أولًا (النسخة الكويتية متوقفة حاليًا)."""
    query = (" ".join(request.areas) or request.raw_text or "").strip()
    url = f"https://aqarmap.com/kw/?q={urllib.parse.quote(query)}"

    def _parse(body: str, req: PropertyRequest) -> tuple[list[Listing], int, dict[str, Any] | None]:
        # فحص الهوية: /kw/ يعيد حاليًا بوابة مصر — لا تُلتقط بيانات بوابة أخرى كبيانات كويتية
        if "عقارماب مصر" in body or "aqarmap.com.eg" in body.lower():
            return [], 0, {
                "name": "Aqarmap",
                "status": "discontinued",
                "records": 0,
                "candidates": 0,
                "note": "النسخة الكويتية من عقارماب متوقفة — الموقع يعيد بوابة مصر حاليًا، ولا تُؤخذ بياناتها كبيانات كويتية.",
            }
        nodes = _jsonld_real_estate_nodes(body)
        listings: list[Listing] = []
        seen: set[str] = set()
        for node in nodes:
            listing = _listing_from_jsonld_node(req, source="Aqarmap", node=node, code_prefix="AQ")
            if listing.code in seen:
                continue
            seen.add(listing.code)
            if request_matches_listing(req, listing):
                listings.append(listing)
        return listings, len(nodes), None

    return _candidate_attempt("Aqarmap", url, request, _parse)


def search_bayut(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """Bayut Kuwait — محمي بنظام captcha؛ يُسجَّل الحجب بشفافية ويُعاد الفحص يوميًا."""
    mode = "to-rent" if transaction_from_request(request) == "للإيجار" else "for-sale"
    query = (" ".join(request.areas) or request.raw_text or "").strip()
    if query:
        url = f"https://www.bayut.com/kuwait/en/property/{mode}/{urllib.parse.quote(query)}"
    else:
        url = f"https://www.bayut.com/kuwait/en/property/{mode}"

    def _parse(body: str, req: PropertyRequest) -> tuple[list[Listing], int, dict[str, Any] | None]:
        nodes = _jsonld_real_estate_nodes(body)
        listings: list[Listing] = []
        seen: set[str] = set()
        for node in nodes:
            listing = _listing_from_jsonld_node(req, source="Bayut", node=node, code_prefix="BY")
            if listing.code in seen:
                continue
            seen.add(listing.code)
            if request_matches_listing(req, listing):
                listings.append(listing)
        return listings, len(nodes), None

    return _candidate_attempt("Bayut", url, request, _parse)


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
    ("Yebtah", search_yebtah),
    ("PropertyFinder", search_propertyfinder),
    ("Aqarmap", search_aqarmap),
    ("Bayut", search_bayut),
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
        mech = source_mechanism(name)
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
            "fetchMethod": mech["method"],
            "endpoint": mech["endpoint"],
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
    progress_cb: Callable[[str, dict], None] | None = None,
) -> tuple[list[Listing], list[dict[str, Any]]]:
    """تشغيل كل المصادر بالتوازي لتقليل زمن الانتظار الإجمالي بدل التسلسل (حتى 84 ثانية سابقًا).

    يسجّل نتيجة كل مصدر (الحالة + السبب + المدة + عدد المحاولات) مرة واحدة لكل تشغيل
    عبر log_source_run مع منع تكرار الرسالة نفسها في الفحص الدوري.

    progress_cb (اختياري): يُستدعى مرتين لكل مصدر — عند بدء تشغيله (status="running")
    وعند انتهائه بالحالة النهائية — لبثّ تقدم حي إلى الواجهة أثناء البحث.
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
        futures: dict = {}
        for name, search in searchers:
            futures[pool.submit(search, request)] = name
            if progress_cb:
                progress_cb(name, {"name": name, "status": "running", "records": 0, "candidates": 0})
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
            # شفافية آلية الجلب: إرفاق fetchMethod + endpoint باسم المصدر لكل حالة
            mech = source_mechanism(name)
            statuses.append({**status, "fetchMethod": mech["method"], "endpoint": mech["endpoint"]})
            log_source_run(status)
            if progress_cb:
                progress_cb(name, {**status, "fetchMethod": mech["method"], "endpoint": mech["endpoint"]})
    return listings, statuses
