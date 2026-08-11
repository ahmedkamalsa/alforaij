"""أفضل الفرص والتوقعات: تحليل حتمي بالكامل مبني على المصادر والأدلة والتقييم (بلا أي عشوائية).

الفئات الزمنية:
- يومية: إعلانات آخر 7 أيام
- أسبوعية: آخر 30 يومًا
- شهرية: آخر 90 يومًا
- سنوية: آخر 365 يومًا
+ توقعات لكل منطقة: اتجاه سعر المتر (صاعد/هابط/مستقر) من مقارنة الوسيط الحديث بالقديم.
+ ربط كل فرصة بالعملاء المحتملين (المنطقة/النوع/السعر) من ملف العملاء.

درجة الثقة = 50% مصداقية المصدر + 30% ثقة التقييم + 20% قوة الأدلة (حتمية بلا عشوائية).
"""
from __future__ import annotations

import csv
import logging
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

logger = logging.getLogger(__name__)

# حدود الأسعار الواقعية — تُستخدم في الفرص والبحث/التقييم معًا لمنع تسلل
# الأسعار النائبة/الوهمية من صفحات المصادر (9,999 / 5,000 د.ك بيع، 70 د.ك إيجار).
# مبني على أدنى سوق محلي فعلي (41,000 د.ك بيع / 250 د.ك إيجار) بهامش أمان.
MIN_SALE_PRICE = 20_000
MIN_RENT_PRICE = 120


def has_realistic_price(listing: Any) -> bool:
    """هل سعر الإعلان واقعي؟

    يمرّر: الإعلانات بلا سعر (طلبات شراء/إيجار تُستخدم للعملاء)، المؤشرات
    الرسمية (سعر المتر المرجعي)، وطلبات «مطلوب». يرفض الأسعار الوهمية النائبة
    من صفحات المصادر فقط (أقل من الحد الواقعي حسب نوع العملية).
    """
    if not listing.price:
        return True
    raw = getattr(listing, "raw", None) or {}
    if getattr(listing, "listing_mode", "") == "رسمي" or raw.get("official"):
        return True
    tx = str(listing.transaction or "")
    if tx.startswith("مطلوب"):
        return True
    floor = MIN_RENT_PRICE if tx.startswith("للإيجار") else MIN_SALE_PRICE
    return listing.price >= floor


from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import (
    broad_combo_requests,
    enrich_listings_from_details,
    scan_opensooq_inventory,
    search_combo_sources,
    search_external_sources,
)
from backend.models import PropertyRequest
from backend.services.official_valuation import get_area_benchmark
from backend.services.valuation import comparable_pool, price_label

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLIENTS_PATH = DATA_DIR / "potential_leads.csv"


def _listing_row(listing: Any) -> dict[str, Any]:
    """تمثيل JSON خفيف للإعلان المحصود من السوق الخارجي لحفظه في قاعدة المعرفة."""
    return {
        "code": listing.code,
        "source": listing.source,
        "transaction": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "property_type": listing.property_type,
        "detail_class": listing.detail_class,
        "price": listing.price,
        "price_text": listing.price_text,
        "space": listing.space,
        "listing_mode": listing.listing_mode,
        "summary": listing.summary,
        "features": listing.features,
        "published_date": listing.published_date or None,
        "original_url": listing.original_url,
        "phone": getattr(listing, "phone", "") or None,
    }

# مصداقية المصادر (ثابتة من السجل الرسمي للمصادر)
SOURCE_TRUST: dict[str, float] = {
    "الفريج": 0.95,
    "Mourjan": 0.7,
    "OpenSooq": 0.65,
    "Q8Aqar": 0.6,
    "Sakan": 0.5,
    "Waseet": 0.6,
    "نبض عقار (NabdAqar)": 0.75,
    "نبض عقار": 0.75,
    "NabdAqar": 0.75,
    "بوعقار / بوشملان (Bu3qar)": 0.75,
    "بوعقار": 0.75,
    "Bu3qar": 0.75,
    "Aqarat": 0.6,
    "4Sale": 0.55,
    "السوق المباشر": 0.75,
    "مؤشرات رسمية": 1.0,
    "الصفقات الرسمية": 1.0,
    "الحسبة - الصفقات المسجلة العامة": 0.9,
}

TIERS = [
    ("daily", "يومية", 7, "إعلانات آخر 7 أيام"),
    ("weekly", "أسبوعية", 30, "إعلانات آخر 30 يومًا"),
    ("monthly", "شهرية", 90, "إعلانات آخر 90 يومًا"),
    ("yearly", "سنوية", 365, "إعلانات آخر 365 يومًا"),
]


def _listing_kind(listing) -> str:
    """تصنيف الإعلان: مباشر / مكتب / غير محدد (من listing_mode).

    يقسم السوق إلى إعلانات مباشرة (المالك/الوسيط المباشر) وإعلانات مكاتب عقارية،
    حتى يفصل المستخدم بينهما بفلتر ويقارن وساطة كل نوع.
    """
    mode = str(getattr(listing, "listing_mode", "") or "")
    if "مباشر" in mode:
        return "مباشر"
    if "مكتب" in mode:
        return "مكتب"
    return "غير محدد"


def _days_ago(published: str) -> int | None:
    try:
        day = datetime.strptime(str(published)[:10], "%Y-%m-%d").date()
        return (date.today() - day).days
    except (ValueError, TypeError):
        return None


def _source_trust(source: str) -> float:
    """مصداقية المصدر مع مطابقة الجذر قبل القوسين: «السوق المباشر (بوشملان)» ← «السوق المباشر».

    الأسماء الحية تحمل تفاصيل المصدر الداخلي بين قوسين (مثل اسم الموقع الفعلي)
    فلا تطابق حرفيًا مفاتيح SOURCE_TRUST.
    """
    trust = SOURCE_TRUST.get(source)
    if trust is not None:
        return trust
    base = source.split(" (")[0].strip()
    return SOURCE_TRUST.get(base, 0.5)


def _confidence(source: str, valuation) -> float:
    """ثقة حتمية: 50% مصداقية المصدر + 30% ثقة التقييم + 20% قوة الأدلة."""
    trust = _source_trust(source)
    evidence_factor = min(1.0, 0.35 + valuation.comparables_count * 0.13)
    return round(min(1.0, trust * 0.5 + valuation.confidence * 0.3 + evidence_factor * 0.2), 2)


def _opportunity_score(deal_score: float, confidence: float) -> float:
    """درجة الفرصة: 65% جاذبية السعر + 35% الثقة (بدون أي عنصر عشوائي)."""
    return round(min(100.0, deal_score * 0.65 + confidence * 100 * 0.35), 1)


def _load_csv_clients() -> list[dict[str, Any]]:
    if not CLIENTS_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(CLIENTS_PATH, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append({key: (value or "").strip() for key, value in row.items()})
    except Exception:
        return []
    return rows


def _load_supabase_clients() -> list[dict[str, Any]]:
    """قراءة العملاء المحفوظين في Supabase (يُضافون من الواجهة) ودمجهم مع ملف العملاء."""
    try:
        from backend.services.supabase_store import fetch_clients
        rows = fetch_clients()
    except Exception as exc:
        logger.warning("Failed to load clients from Supabase: %s", exc)
        return []
    clients: list[dict[str, Any]] = []
    for row in rows:
        price_value = row.get("price")
        price_text = ""
        if price_value not in (None, ""):
            try:
                price_text = f"{float(price_value):,.0f}"
            except (TypeError, ValueError):
                price_text = str(price_value)
        clients.append({
            "code": f"LEAD-{row.get('id')}",
            "area": str(row.get("area") or ""),
            "type": str(row.get("type") or ""),
            "price": price_text,
            "phones": str(row.get("phone") or ""),
            "message": str(row.get("note") or ""),
            "source": "supabase",
        })
    return clients


def _load_clients() -> list[dict[str, Any]]:
    """كل العملاء المحتملين: ملف CSV + قاعدة Supabase (الأحدث أولًا)."""
    return _load_csv_clients() + _load_supabase_clients()


def _client_score(client: dict[str, Any], listing_area: str, listing_type: str, price: float | None) -> tuple[float, list[str]]:
    """درجة مطابقة العميل للفرصة: المنطقة 40 + النوع 30 + تقارب السعر 30. حتمية."""
    points = 0.0
    reasons: list[str] = []
    if client.get("area") and listing_area and client["area"] == listing_area:
        points += 40
        reasons.append("نفس المنطقة")
    elif client.get("area") and listing_area and listing_area in client.get("area", ""):
        points += 25
        reasons.append("منطقة قريبة/متضمنة")
    if client.get("type") and listing_type and client["type"] == listing_type:
        points += 30
        reasons.append("نفس نوع العقار")
    elif client.get("type") and listing_type and listing_type in client.get("type", ""):
        points += 18
        reasons.append("نوع عقار قريب")
    if price:
        try:
            # قد يأتي السعر بصيغة نصية بفواصل («350,000») من قائمة Supabase المنسقة
            client_price = float(str(client.get("price") or 0).replace(",", "").strip())
            if client_price and 0.7 <= price / client_price <= 1.3:
                points += 30
                reasons.append("السعر ضمن نطاق العميل")
            elif client_price and price <= client_price * 1.5:
                points += 15
                reasons.append("السعر قريب من نطاق العميل")
        except (TypeError, ValueError):
            pass
    return round(min(100.0, points), 1), reasons


def _client_budget(client: dict[str, Any]) -> float | None:
    try:
        value = float(str(client.get("price") or "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value or None


def _deal_profit(client: dict[str, Any], listing_price: float | None) -> dict[str, Any]:
    budget = _client_budget(client)
    if not budget or not listing_price:
        return {
            "clientBudget": budget,
            "potentialProfitKwd": None,
            "profitReason": "لا يمكن حساب المكسب لأن ميزانية العميل أو سعر الإعلان غير مكتمل.",
        }
    spread = budget - listing_price
    if spread <= 0:
        return {
            "clientBudget": budget,
            "potentialProfitKwd": 0,
            "profitReason": "سعر الإعلان ليس أقل من ميزانية العميل، لذلك لا يوجد هامش شراء مباشر.",
        }
    return {
        "clientBudget": budget,
        "potentialProfitKwd": round(spread, 0),
        "profitReason": f"ميزانية العميل {budget:,.0f} د.ك ناقص سعر الإعلان {listing_price:,.0f} د.ك.",
    }


def _extract_budget_from_text(text: str) -> float | None:
    """استخراج ميزانية شراء من نص طلب («بحدود 300 الف»، «حدود 250 ألف»، «ميزانية 180-200»).

    القيمة بالدينار الكويتي؛ «ألف/الف» تُضرب في 1000. تُرجع None عند عدم وجود ميزانية واضحة.
    """
    normalized = " ".join((text or "").split())
    # إزالة أرقام الهواتف الكويتية كاملة من النص حتى لا تُلتقط كجزء من الميزانية
    normalized = re.sub(r"(?:\+?965)?\s?[24569]\d{7}", " ", normalized)
    pattern = re.compile(
        r"(?:بحدود|حدود|بحدود|في حدود|بحدو|الميزانية|ميزانية|بميزانية)?\s*"
        r"(\d{2,6})\s*(?:الف|ألف|الف دينار|ألف دينار)?"
        r"(?:\s*(?:الى|إلى|الي|او|أو|-|ـ)\s*(\d{2,6})\s*(?:الف|ألف)?)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(normalized):
        first = int(match.group(1))
        thousand = "الف" in (match.group(0) or "") or "ألف" in (match.group(0) or "")
        low = first * 1000 if thousand else first
        if low < 5_000 or low > 50_000_000:
            continue
        high_raw = match.group(2)
        if high_raw:
            high = int(high_raw) * (1000 if thousand else 1)
            # نطاق: الوسيط (مثل «180 الى 200 الف» → 190,000)
            return round((low + high) / 2, 0)
        return float(low)
    return None


def clients_from_demand_listings(listings: list[Any]) -> list[dict[str, Any]]:
    """حوّل إعلانات الطلب (مطلوب للشراء) من الفريج أو المواقع الخارجية إلى عملاء محتملين."""
    clients: list[dict[str, Any]] = []
    phone_pattern = re.compile(r"(?:\+?965)?\s?[24569]\d{7}")
    for listing in listings:
        tx = str(getattr(listing, "transaction", "") or "")
        if "مطلوب" not in tx or "شراء" not in tx:
            continue
        text = " ".join([
            str(getattr(listing, "summary", "") or ""),
            str(getattr(listing, "features", "") or ""),
            str(getattr(listing, "seller_info", "") or ""),
        ])
        phones = "|".join(dict.fromkeys(match.replace(" ", "") for match in phone_pattern.findall(text)))
        if not phones:
            continue
        # ميزانية العميل: حقل السعر إن وُجد، وإلا تُستخرج من نص الطلب («بحدود 300 الف»)
        # حتى تُحسب فرص المكسب الرقمية للطلبات التي لا تحمل سعرًا صريحًا.
        price = getattr(listing, "price", None)
        if not price:
            price = _extract_budget_from_text(text)
        clients.append({
            "code": f"DEMAND-{getattr(listing, 'code', '')}",
            "area": getattr(listing, "area", "") or "",
            "type": getattr(listing, "property_type", "") or getattr(listing, "detail_class", "") or "",
            "price": f"{float(price):,.0f}" if price else "",
            "phones": phones,
            "message": text[:300],
            "source": getattr(listing, "source", "") or "market_demand",
        })
    return clients


def match_clients_for_listing(
    clients: list[dict[str, Any]],
    listing_area: str,
    listing_type: str,
    price: float | None,
) -> list[dict[str, Any]]:
    """ربط العملاء المحتملين بفرصة/نتيجة بيعية (المنطقة 40 + النوع 30 + تقارب السعر 30).

    دالة مشتركة تُستخدم في الفرص وفي نتائج التحليل الفردي حتى يتسق الربط في كل مكان.
    تُرجع الأفضل 3 فقط.
    """
    matched: list[dict[str, Any]] = []
    for client in clients:
        if not client.get("phones"):
            continue
        client_area = str(client.get("area") or "").strip()
        if client_area and listing_area and client_area != listing_area and listing_area not in client_area:
            continue
        c_score, c_reasons = _client_score(client, listing_area, listing_type, price)
        if c_score >= 40:
            profit = _deal_profit(client, price)
            matched.append({
                "area": client.get("area"),
                "type": client.get("type"),
                "price": client.get("price"),
                "phones": client.get("phones"),
                "message": client.get("message"),
                "source": client.get("source") or "csv",
                "matchScore": c_score,
                "reasons": c_reasons,
                **profit,
            })
    matched.sort(key=lambda m: m["matchScore"], reverse=True)
    return matched[:3]


def _listing_opportunity(listing, valuation, clients: list[dict[str, Any]]) -> dict[str, Any]:
    confidence = _confidence(listing.source, valuation)
    rental = bool(getattr(valuation, "rental", False))
    days_ago = _days_ago(listing.published_date)
    # الإعلان الحي القادم من فحص المصادر الخارجية الآن بلا تاريخ يُعتبر حديثًا (يوم 0)
    # حتى تدخل كل منصات المواقع/التطبيقات فئات الفرص اليومية وليس الفريج فقط.
    if days_ago is None and listing.source != "الفريج":
        days_ago = 0
    opportunity = {
        "code": listing.code,
        "source": listing.source,
        "listingType": _listing_kind(listing),
        "governorate": listing.governorate,
        "area": listing.area,
        "propertyType": listing.property_type or listing.detail_class,
        "transaction": listing.transaction,
        "rental": rental,
        "price": listing.price,
        "priceText": listing.price_text or f"{listing.price:,.0f} د.ك",
        "space": listing.space,
        "publishedDate": listing.published_date,
        "daysAgo": days_ago,
        "url": listing.original_url,
        "phone": getattr(listing, "phone", "") or "",
        "summary": listing.summary,
        "dealScore": valuation.deal_score,
        "confidence": confidence,
        "valuationLabel": valuation.label,
        "valuationReason": valuation.reason,
        "marketMedian": valuation.market_median,
        "pricePerSqm": round(valuation.price_per_sqm, 1) if valuation.price_per_sqm else None,
        "officialValue": valuation.official_value,
        "officialSourceKind": valuation.official_source_kind,
        "comparablesCount": valuation.comparables_count,
        "comparableScope": valuation.comparable_scope,
        "score": _opportunity_score(valuation.deal_score, confidence),
        # كل دليل يحمل مصدره وسعره ورابطه حتى تُعرض صناديق دليل لكل موقع في بطاقة الفرصة
        "evidence": [
            {
                "code": e.get("code"),
                "area": e.get("area"),
                "price": e.get("price"),
                "priceText": e.get("priceText"),
                "source": e.get("source"),
                "url": e.get("url"),
            }
            for e in valuation.evidence[:4]
        ],
    }
    # حقول إضافية لعروض الإيجار (شهري/سنوي/متر/عائد) — تظهر في بطاقة الفرصة عند الإيجار
    if rental:
        opportunity["monthlyRent"] = valuation.monthly_rent
        opportunity["annualRent"] = valuation.annual_rent
        opportunity["rentPerSqm"] = round(valuation.rent_per_sqm, 1) if valuation.rent_per_sqm else None
        opportunity["medianRent"] = valuation.median_rent
        opportunity["capitalValue"] = valuation.capital_value
        opportunity["rentalYieldPercent"] = valuation.rental_yield_percent
    # ربط العملاء المحتملين — يُربط بعروض البيع فقط؛ ميزانية شراء العميل لا تُقارن بإيجار شهري
    opportunity["clients"] = (
        []
        if rental
        else match_clients_for_listing(clients, listing.area, opportunity["propertyType"], listing.price)
    )
    return opportunity


def _score_listings(listings, clients: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    """تقييم كل إعلان عرض (بيع/إيجار) وترتيبه بخط حسابه المميز.

    - طلبات «مطلوب…» (جانب الطلب) تُستبعد من الفرص لأنها إشارات طلب لا عروضًا —
      لكنها تبقى متاحة لتبويب «العرض والطلب» عبر _demand_requests().
    - حارس الجودة: السعر غير المنطقي (مثل «2 د.ك» لإيجار أو «500 د.ك» لبيع) إشارة
      فشل استخراج من صفحة المصدر لا فرصة حقيقية — يُستبعد حتى لا يلوث «أفضل الفرص».
    - عروض الإيجار تدخل بخط حسابها المميز (إيجار شهري/سنوي + عائد إيجاري)،
      فلا يُخلط إيجار شهري بسعر بيع إجمالي أبدًا.
    """
    scored: list[dict[str, Any]] = []
    skipped_demand = 0
    skipped_unreal = 0
    for listing in listings:
        if not listing.price:
            continue
        # المؤشرات الرسمية لا تدخل الفرص (سعر المتر المرجعي ليس عرضًا)
        if getattr(listing, "listing_mode", "") == "رسمي":
            continue
        tx = str(listing.transaction or "")
        if tx.startswith("مطلوب"):
            skipped_demand += 1
            continue
        # أسعار وهمية/نائبة من صفحات المصادر (9,999 / 5,000 د.ك بيع، 70 د.ك إيجار) تمرّ
        # بالحدود المنخفضة السابقة وتتصدر «أفضل الفرص» كأنها صفقات حقيقية.
        if not has_realistic_price(listing):
            skipped_unreal += 1
            continue
        comps = comparable_pool(listing, listings)
        valuation = price_label(listing, comps)
        scored.append(_listing_opportunity(listing, valuation, clients))
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored, skipped_demand, skipped_unreal


def _market_supply() -> list[dict[str, Any]]:
    """كل عروض السوق المتاحة المقيّمة (بيع + إيجار) — أساس التوفيق العملي مع الطلبات."""
    scored, _skipped_demand, _skipped_unreal = _score_listings(load_listings(), _load_clients())
    return scored


_DEMAND_TYPE_HINTS = ["شقة", "أرض", "عمارة", "مكتب", "محل", "تجاري"]


def _demand_property_type(listing) -> str:
    """نوع العقار المطلوب من detail_class أو نص الطلب — فارغ يعني «أي نوع»."""
    dc = str(listing.detail_class or "")
    if "بيت" in dc or "فيلا" in dc:
        return "بيت"
    for hint in _DEMAND_TYPE_HINTS:
        if hint in dc:
            return hint
    text = f"{listing.summary} {listing.features}"
    for hint in ["بيت", "فيلا", "شقة", "أرض", "عمارة"]:
        if hint in text:
            return "بيت" if hint == "فيلا" else hint
    return ""


def _demand_requests() -> list[dict[str, Any]]:
    """طلبات السوق «مطلوب…»: طلب شراء / طلب إيجار / طلب بيع — جانب الطلب في التوفيق العملي."""
    out: list[dict[str, Any]] = []
    for listing in load_listings():
        tx = str(listing.transaction or "")
        if not tx.startswith("مطلوب"):
            continue
        if "شراء" in tx:
            kind = "buy"
        elif "إيجار" in tx:
            kind = "rent"
        else:
            kind = "sell"
        out.append({
            "code": listing.code,
            "transaction": tx,
            "kind": kind,
            "area": listing.area,
            "governorate": listing.governorate,
            "propertyType": _demand_property_type(listing),
            "budget": listing.price,
            "budgetText": f"{listing.price:,.0f} د.ك" if listing.price else None,
            "summary": (listing.summary or "")[:240],
            "url": listing.original_url,
            "source": listing.source,
            "listingMode": listing.listing_mode,
            "listingType": _listing_kind(listing),
        })
    return out


def _demand_match_score(demand: dict[str, Any], item: dict[str, Any]) -> tuple[float, list[str]]:
    """درجة التوفيق بين طلب السوق وفرصة متاحة: المنطقة 40 + النوع 30 + السعر 30. حتمية بلا عشوائية."""
    points = 0.0
    reasons: list[str] = []
    area = item.get("area") or ""
    if demand.get("area") and area and demand["area"] == area:
        points += 40
        reasons.append("نفس المنطقة")
    elif (
        demand.get("governorate")
        and item.get("governorate")
        and demand["governorate"] == item.get("governorate")
    ):
        points += 25
        reasons.append("نفس المحافظة")
    want_type = demand.get("propertyType") or ""
    if want_type:
        if want_type == (item.get("propertyType") or ""):
            points += 30
            reasons.append("نفس نوع العقار")
        else:
            points += 8
            reasons.append("نوع عقار مختلف")
    else:
        points += 20
        reasons.append("طلب دون تحديد نوع (أي نوع)")
    budget = demand.get("budget")
    price = item.get("price")
    if budget and price:
        try:
            ratio = price / float(budget)
            if 0.7 <= ratio <= 1.3:
                points += 30
                reasons.append("السعر ضمن الميزانية")
            elif ratio <= 1.5:
                points += 15
                reasons.append("السعر قريب من الميزانية")
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return round(min(100.0, points), 1), reasons


def build_market_matching(
    snapshot: dict[str, Any] | None = None,
    demand_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """التوفيق العملي بين العرض والطلب.

    جانب العرض: الفرص المتاحة المقيّمة (بيع + إيجار) من اللقطة الحالية،
    أو إعادة تقييم حية عند غيابها. جانب الطلب: طلبات «مطلوب للشراء / للإيجار».
    كل طلب يُقابل بأفضل الفرص المطابقة (منطقة/محافظة + نوع + ميزانية) مع تقييم
    كل فرصة ومصادرها، ويُبرز «الفرص الأكثر طلبًا» ليتصرف الوسيط بسرعة.
    """
    snapshot = snapshot or {}
    pool: dict[str, dict[str, Any]] = {}
    for tier in (snapshot.get("tiers") or {}).values():
        for item in tier.get("items") or []:
            code = item.get("code")
            if code and code not in pool:
                pool[code] = item
    supply = list(pool.values())
    if not supply:
        supply = _market_supply()

    requests: list[dict[str, Any]] = []
    for demand in demand_requests if demand_requests is not None else _demand_requests():
        matches: list[dict[str, Any]] = []
        for item in supply:
            if demand["kind"] == "buy" and item.get("rental"):
                continue
            if demand["kind"] == "rent" and not item.get("rental"):
                continue
            score, reasons = _demand_match_score(demand, item)
            if score >= 40:
                match = dict(item)
                match["matchScore"] = score
                match["matchReasons"] = reasons
                matches.append(match)
        matches.sort(key=lambda m: (m["matchScore"], m.get("score") or 0), reverse=True)
        requests.append({**demand, "matchCount": len(matches), "matches": matches[:5]})

    demand_counts: Counter = Counter()
    for demand in requests:
        for match in demand["matches"]:
            demand_counts[match.get("code")] += 1
    hot: list[dict[str, Any]] = []
    for item in supply:
        count = demand_counts.get(item.get("code"), 0)
        if count:
            hot_item = dict(item)
            hot_item["demandCount"] = count
            hot.append(hot_item)
    hot.sort(key=lambda h: (h["demandCount"], h.get("score") or 0), reverse=True)

    by_kind = {"buy": 0, "rent": 0, "sell": 0}
    for demand in requests:
        by_kind[demand["kind"]] = by_kind.get(demand["kind"], 0) + 1
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "demandCount": len(requests),
        "matchedDemandCount": sum(1 for r in requests if r["matchCount"]),
        "byKind": by_kind,
        "supplyCount": len(supply),
        "requests": requests,
        "hotOffers": hot[:15],
        "note": (
            "التوفيق العملي بين العرض والطلب: كل طلب «مطلوب للشراء/للإيجار» يُقابل بأفضل الفرص "
            "المتاحة المقيّمة (نفس المنطقة/المحافظة + نوع العقار + الميزانية)، مع تقييم كل فرصة "
            "ومصادرها — حتمي بلا عشوائية."
        ),
    }


def _flat_tier_items(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """كل الفرص من كل الفئات الزمنية (بإزالة التكرار بالكود) كقاموس بالكود."""
    pool: dict[str, dict[str, Any]] = {}
    for tier in ((snapshot or {}).get("tiers") or {}).values():
        for item in tier.get("items") or []:
            code = item.get("code")
            if code and code not in pool:
                pool[code] = item
    return pool


def build_opportunity_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """ما الجديد وما حذف وما انخفض سعره بين آخر لقطتين — مع إرشاد التعامل مع كل حالة.

    - الجديد: فرصة دخلت السوق → راسل العملاء المطابقين فورًا.
    - المحذوف: اختفى إعلان → أزله من العروض المرسلة وأبلغ المهتمين.
    - انخفاض السعر: تحسّنت الفرصة → أبلغ العملاء المطابقين بالفرصة المحسّنة.
    """
    prev_items = _flat_tier_items(previous)
    curr_items = _flat_tier_items(current)

    added: list[dict[str, Any]] = []
    for code, item in curr_items.items():
        if code in prev_items:
            continue
        added.append({
            "code": code,
            "area": item.get("area"),
            "propertyType": item.get("propertyType"),
            "priceText": item.get("priceText"),
            "price": item.get("price"),
            "valuationLabel": item.get("valuationLabel"),
            "score": item.get("score"),
            "url": item.get("url"),
            "source": item.get("source"),
            "listingType": item.get("listingType"),
            "clients": (item.get("clients") or [])[:3],
            "change": "new",
            "guidance": "فرصة جديدة في السوق — راسل العملاء المطابقين فورًا قبل المنافسين.",
        })

    removed: list[dict[str, Any]] = []
    for code, item in prev_items.items():
        if code in curr_items:
            continue
        removed.append({
            "code": code,
            "area": item.get("area"),
            "propertyType": item.get("propertyType"),
            "priceText": item.get("priceText"),
            "price": item.get("price"),
            "valuationLabel": item.get("valuationLabel"),
            "url": item.get("url"),
            "source": item.get("source"),
            "change": "removed",
            "guidance": "اختفى الإعلان من السوق — أزله من العروض المرسلة وأبلغ العملاء المهتمين (قد يكون حُجز أو سُحب).",
        })

    price_drops: list[dict[str, Any]] = []
    for code, item in curr_items.items():
        prev = prev_items.get(code)
        if not prev or not item.get("price") or not prev.get("price"):
            continue
        if item["price"] < prev["price"]:
            price_drops.append({
                "code": code,
                "area": item.get("area"),
                "propertyType": item.get("propertyType"),
                "priceText": item.get("priceText"),
                "price": item.get("price"),
                "oldPrice": prev.get("price"),
                "oldPriceText": prev.get("priceText"),
                "valuationLabel": item.get("valuationLabel"),
                "score": item.get("score"),
                "url": item.get("url"),
                "clients": (item.get("clients") or [])[:3],
                "change": "price_drop",
                "guidance": "انخفض السعر — أبلغ العملاء المطابقين بالفرصة المحسّنة فورًا.",
            })

    added.sort(key=lambda d: d.get("score") or 0, reverse=True)
    price_drops.sort(key=lambda d: (d.get("oldPrice") or 0) - (d.get("price") or 0), reverse=True)
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "hasPrevious": bool(prev_items),
        "counts": {"added": len(added), "removed": len(removed), "priceDrops": len(price_drops)},
        "added": added[:20],
        "removed": removed[:20],
        "priceDrops": price_drops[:20],
        "note": (
            "مقارنة آخر لقطتين للفرص: الجديد (فرصة دخلت السوق) والمحذوف (اختفى إعلان) "
            "وانخفاض الأسعار — مع إرشاد التعامل مع كل حالة ليتصرف الوسيط بسرعة وباحترافية."
        ),
    }


def _area_forecast(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """توقعات لكل منطقة: وسيط سعر المتر حديث (≤30 يوم) مقابل قديم، واتجاه، وسعر المتر المتوقع."""
    buckets: dict[str, dict[str, list[float]]] = {}
    for item in scored:
        # توقعات سعر المتر خاصة بسوق البيع/الشراء فقط — إيجار المتر الشهري لا يُخلط بسعر متر البيع
        if item.get("rental"):
            continue
        area = item["area"] or "غير محددة"
        rate = item.get("pricePerSqm")
        if not rate:
            continue
        bucket = buckets.setdefault(area, {"recent": [], "older": []})
        (bucket["recent"] if (item.get("daysAgo") is not None and item["daysAgo"] <= 30) else bucket["older"]).append(rate)

    forecasts: list[dict[str, Any]] = []
    for area, bucket in buckets.items():
        recent = median(bucket["recent"]) if bucket["recent"] else None
        older = median(bucket["older"]) if bucket["older"] else None
        official_rate = get_area_benchmark(area)
        expected = official_rate or recent or older
        if recent and older and older > 0:
            change = (recent - older) / older * 100
            if change >= 3:
                direction = "صاعد"
            elif change <= -3:
                direction = "هابط"
            else:
                direction = "مستقر"
        elif recent and not older:
            direction = "صاعد (جديد)"
            change = None
        else:
            direction = "مستقر (بيانات محدودة)"
            change = None
        forecasts.append({
            "area": area,
            "recentMedian": round(recent, 1) if recent else None,
            "olderMedian": round(older, 1) if older else None,
            "changePercent": round(change, 1) if change is not None else None,
            "direction": direction,
            "expectedPricePerSqm": round(expected, 1) if expected else None,
            "officialRate": round(official_rate, 1) if official_rate else None,
            "sourceKind": "official" if official_rate else "derived",
            "sampleCount": len(bucket["recent"]) + len(bucket["older"]),
        })
    forecasts.sort(key=lambda f: (f["expectedPricePerSqm"] or 0), reverse=True)
    return forecasts


def _broad_request() -> PropertyRequest:
    """طلب عريض لمسح المصادر الخارجية الحية بحثًا عن فرص إضافية."""
    return PropertyRequest(raw_text="")


def normalize_phone(phone: str) -> str:
    """تطبيع رقم الهاتف لرابط WhatsApp: أرقام فقط، مع كود الدولة عند غيابه.

    - 555xxxxx (8 أرقام كويتي) → 965555xxxxx
    - 01xxxxxxxxx (11 رقمًا مصريًا) → 201xxxxxxxxx
    - الأرقام الدولية (+965… / +20…) تُترك كما هي بعد إزالة +.
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("01") and len(digits) == 11:
        # رقم مصري محمول: 01xxxxxxxxx
        return "20" + digits[1:]
    if not digits.startswith("965") and len(digits) <= 10:
        digits = "965" + digits.lstrip("0")
    return digits


def append_csv_client(client: dict[str, Any]) -> dict[str, Any]:
    """إضافة/تحديث عميل محتمل في ملف العملاء المحلي (CSV) بمفتاح رقم الهاتف.

    تُستخدم كاحتياط دائم حتى عند غياب Supabase: تُكتب الصفوف بنفس رؤوس
    potential_leads.csv حتى تندمج تلقائيًا مع بقية العملاء في الفرص.
    """
    phone = str(client.get("phone") or client.get("phones") or "").strip()
    if not phone:
        return {"status": "error", "error": "رقم الهاتف مطلوب"}
    rows = _load_csv_clients()
    headers = ["code", "area", "type", "price", "space", "publishedDate", "url", "phones", "message"]
    next_code = 1
    for row in rows:
        if row.get("phones") == phone:
            return {"status": "exists", "code": row.get("code")}
        match = re.fullmatch(r"LEAD-(\d+)", str(row.get("code") or ""))
        if match:
            next_code = max(next_code, int(match.group(1)) + 1)
    new_row = {
        "code": f"LEAD-{next_code}",
        "area": client.get("area") or "",
        "type": client.get("type") or "",
        "price": client.get("price") or "",
        "space": "",
        "publishedDate": "",
        "url": "",
        "phones": phone,
        "message": client.get("note") or "",
    }
    try:
        with open(CLIENTS_PATH, "a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            if not CLIENTS_PATH.stat().st_size:
                writer.writeheader()
            writer.writerow(new_row)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "added", "code": new_row["code"]}


def build_whatsapp_alerts(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """تنبيهات واتساب: مقارنة اللقطة السابقة بالحالية لاكتشاف الفرص الجديدة وانخفاض الأسعار.

    تُبنى الرسائل من قوالب outreach_whatsapp_messages.txt لكل عميل محتمل مطابق،
    مع رابط wa.me جاهز للفتح/النسخ.
    """
    alerts: list[dict[str, Any]] = []
    current_items = (current.get("tiers") or {}).get("daily", {}).get("items", []) or []
    previous_items: dict[str, dict[str, Any]] = {}
    if previous:
        previous_items = {
            item.get("code"): item
            for item in ((previous.get("tiers") or {}).get("daily", {}).get("items", []) or [])
        }

    for item in current_items:
        code = item.get("code")
        prev = previous_items.get(code)
        change = None
        old_price = None
        if prev is None:
            change = "new"
        elif item.get("price") and prev.get("price") and item["price"] < prev["price"]:
            change = "price_drop"
            old_price = prev.get("price")
        if not change:
            continue
        clients = item.get("clients") or []
        if not clients:
            continue
        price_text = item.get("priceText") or f"{item.get('price'):,.0f} د.ك"
        if change == "price_drop":
            old_text = f"{old_price:,.0f} د.ك" if old_price else "السعر السابق"
            message = (
                f"السلام عليكم، معك [اسمك]. انخفض سعر إعلان {code} في {item.get('area') or 'المنطقة'} "
                f"إلى {price_text} (كان {old_text}) — {item.get('valuationLabel') or ''}. "
                f"هل ترغب بمتابعة التفاصيل أو موعد معاينة؟ شكرًا."
            )
        else:
            message = (
                f"السلام عليكم، معك [اسمك]. فرصة جديدة: {item.get('propertyType') or 'عقار'} "
                f"في {item.get('area') or 'المنطقة'} بسعر {price_text} — {item.get('valuationLabel') or ''}. "
                f"هل لديكم مشترين مهتمين؟ أرسل موعد معاينة أو طلب التفاصيل. شكرًا."
            )
        phone_clients = [c for c in clients if c.get("phones")]
        for client in phone_clients:
            phones = [p for p in (normalize_phone(x) for x in re.split(r"[|،,]+", str(client.get("phones") or ""))) if p]
            if not phones:
                continue
            alerts.append({
                "code": code,
                "area": item.get("area"),
                "change": change,
                "price": item.get("price"),
                "priceText": price_text,
                "oldPrice": old_price,
                "clientArea": client.get("area"),
                "clientType": client.get("type"),
                "matchScore": client.get("matchScore"),
                "phones": [f"+{p}" for p in phones],
                "waLinks": [f"https://wa.me/{p}" for p in phones],
                "message": message,
                "url": item.get("url"),
            })

    alerts.sort(key=lambda a: (a.get("change") == "price_drop", a.get("matchScore") or 0), reverse=True)
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(alerts),
        "alerts": alerts[:20],
        "note": (
            "التنبيهات تُبنى من مقارنة آخر لقطتين: فرص جديدة دخلت اليومية أو انخفض سعرها، "
            "لكل عميل محتمل مطابق — استبدل [اسمك] قبل الإرسال."
        ),
    }


def build_history_series(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """أرشفة الأداء: سلسلة زمنية لوسيط سعر المتر لكل منطقة عبر اللقطات المحفوظة."""
    series: dict[str, list[dict[str, Any]]] = {}
    dates: list[str] = []
    for snap in snapshots:  # أقدم → أحدث
        generated = str(snap.get("generated_at") or "")[:16].replace("T", " ")
        if generated and generated not in dates:
            dates.append(generated)
        forecast = snap.get("forecast") or []
        for entry in forecast:
            area = entry.get("area")
            value = entry.get("expectedPricePerSqm")
            if not area or not value:
                continue
            series.setdefault(area, []).append({"date": generated, "value": float(value)})
    output = []
    for area, points in series.items():
        points = sorted(points, key=lambda p: p["date"])
        if not points:
            continue
        first = points[0]["value"]
        last = points[-1]["value"]
        change = ((last - first) / first * 100) if first else 0
        direction = "صاعد" if change >= 3 else ("هابط" if change <= -3 else "مستقر")
        output.append({
            "area": area,
            "points": points,
            "first": round(first, 1),
            "latest": round(last, 1),
            "changePercent": round(change, 1),
            "direction": direction,
        })
    output.sort(key=lambda entry: entry["latest"], reverse=True)
    return {"dates": dates, "series": output[:15], "snapshotCount": len(snapshots)}


def build_opportunities(limit_per_tier: int = 30, include_external: bool = True, return_external: bool = False) -> dict[str, Any]:
    """يبني لقطة الفرص الحالية: فئات زمنية + توقعات + عملاء محتملون، مع مصادر وأدلة وثقة حتمية.

    include_external: يدمج الإعلانات الحية من المصادر الخارجية المتصلة (الفريج محليًا +
    Mourjan/OpenSooq/... عبر الإنترنت) مع الإفصاح عن المصادر التي أسهمت.
    return_external: يعيد أيضًا إعلانات السوق الخارجية المحصودة (مسلسلة) تحت مفتاح
    `externalListings` ليتسنى حفظها في قاعدة المعرفة (market_listings) — قاعدة البيانات
    تتراكم كل إعلانات المواقع مثل بيانات الفريج المحلية تمامًا.
    """
    listings = load_listings()
    clients = _load_clients()
    external_statuses: list[dict[str, Any]] = []
    external_rows: list[dict[str, Any]] = []
    if include_external:
        try:
            external_listings, external_statuses = search_external_sources(_broad_request())
            # توسيع الفحص العريض: أنواع ومعاملات متعددة (بيوت/شقق/أراضٍ × بيع/إيجار)
            # عبر Q8Aqar/OpenSooq حتى تصل فرص كل منصة لأقصى عدد ممكن — الطلب الفارغ
            # كان يفحص بيوت البيع فقط عبر Q8Aqar وبيوعات OpenSooq ويُسقط إيجاراتهم.
            combo_listings, combo_statuses = search_combo_sources(broad_combo_requests(), ["Q8Aqar", "OpenSooq"])
            external_listings.extend(combo_listings)
            external_statuses.extend(combo_statuses)
            # جرد السوق المفتوح الكامل: صفحة القائمة الواحدة تُظهر نحو 30 إعلانًا من
            # كل الأنواع، والبحث الحي يقتطع الصفحة الأولى فقط — هذا المسح يمشي صفحات
            # قسمي البيع والإيجار كاملًا حتى يتراكم جرد OpenSooq في قاعدة المعرفة
            # (market_listings) مثل بيانات الفريج المحلية، وكل نوع يظهر في اللوحة.
            _inventory, _inventory_status = scan_opensooq_inventory()
            external_listings.extend(_inventory)
            external_statuses.append(_inventory_status)
            # وكيل إكمال التفاصيل: يقرأ صفحة تفاصيل كل إعلان ناقص (سعر/مساحة/منطقة/هاتف)
            # حتى تُقيَّم الإعلانات ببيانات كاملة وتُحفظ في قاعدة المعرفة مكتملة. سقف 40
            # صفحة في الحصاد (وليس 15) لملء هواتف الإعلانات الجديدة أسرع — كل صفحة خفيفة
            # (38-180KB) بسرعة 4 طلبات متوازية، والمصادر التي تعرض الهاتف لها الأولوية.
            _enrich = enrich_listings_from_details(external_listings, max_pages=40)
            if _enrich.get("enriched"):
                external_statuses.append({
                    "name": "وكيل إكمال التفاصيل",
                    "status": _enrich.get("status"),
                    "records": _enrich.get("enriched", 0),
                    "candidates": _enrich.get("read", 0),
                    "note": _enrich.get("note", ""),
                })
                logger.info("harvest: %s", _enrich.get("note"))
            # إزالة التكرار بالكود: نفس الإعلان قد يظهر في المسح العام والمسح المركّب
            seen_codes = {listing.code for listing in listings}
            for listing in external_listings:
                if listing.code in seen_codes:
                    continue
                seen_codes.add(listing.code)
                listings.append(listing)
                if return_external:
                    external_rows.append(_listing_row(listing))
        except Exception as exc:
            logger.warning("External sources scan failed: %s", exc)
            external_statuses = [{"name": "المصادر الخارجية", "status": "failed", "records": 0, "note": str(exc)}]

    clients = clients + clients_from_demand_listings(listings)
    scored, skipped_demand, skipped_unreal = _score_listings(listings, clients)

    tiers: dict[str, dict[str, Any]] = {}
    for key, label, days, description in TIERS:
        items = [item for item in scored if item.get("daysAgo") is not None and item["daysAgo"] <= days]
        tiers[key] = {
            "label": label,
            "description": description,
            "items": items[:limit_per_tier],
        }

    contributing = list(dict.fromkeys(
        s.get("name")
        for s in external_statuses
        if s.get("status") in ("success", "connected") or s.get("records")
    ))
    result = {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "generatedDate": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totalListings": len(listings),
        "totalScored": len(scored),
        "totalClients": len(clients),
        "includeExternal": bool(include_external),
        "contributingSources": contributing,
        "confidenceMethod": "الثقة = 50% مصداقية المصدر + 30% ثقة التقييم + 20% قوة الأدلة (حتمية بلا عشوائية)",
        "rentalCount": sum(1 for item in scored if item.get("rental")),
        "saleCount": sum(1 for item in scored if not item.get("rental")),
        "skippedDemandCount": skipped_demand,
        "skippedUnrealCount": skipped_unreal,
        "rentalNote": "",
        "officialDataNote": (
            "لا توجد قاعدة بيانات رسمية حية تنشر سعر المتر لكل منطقة في الكويت؛ "
            "المصادر الرسمية المتاحة هي إحصاءات وزارة العدل (التسجيل العقاري) وتقارير بيت التمويل الكويتي "
            "وبنك الكويت الوطني، وكلها لا تنشر سعر المتر التفصيلي لكل منطقة. لذلك عند غياب معيار رسمي "
            "تُشتق القيمة من وسيط الإعلانات الفعلية في نفس المنطقة مع الإفصاح الكامل عن عدد الأدلة."
        ),
        "tiers": tiers,
        "forecast": _area_forecast(scored),
    }
    if return_external:
        result["externalListings"] = external_rows
    return result


def build_weekly_digest(snapshot: dict[str, Any], top_n: int = 10) -> dict[str, Any]:
    """موجز أسبوعي: أفضل 10 فرص بيع لكل عميل محتمل مع رسالة واتساب جاهزة للإرسال.

    - تُجمع الفرص من كل الفئات الزمنية (بإزالة التكرار بالكود).
    - تُقتصر على عروض البيع فقط: ميزانية شراء العميل لا تُقارن بإيجار شهري.
    - لكل عميل تُحسب درجة المطابقة (المنطقة 40 + النوع 30 + تقارب السعر 30) لكل فرصة،
      ويُؤخذ الأعلى 10 بترتيب (درجة المطابقة ثم درجة الفرصة).
    - تُبنى رسالة واتساب مخصصة: تحية + سياق العميل + قائمة مرقمة بمصادر أدلة كل فرصة.
    """
    pool: dict[str, dict[str, Any]] = {}
    for tier in (snapshot.get("tiers") or {}).values():
        for item in tier.get("items") or []:
            code = item.get("code")
            if code and code not in pool:
                pool[code] = item
    sale_items = [item for item in pool.values() if not item.get("rental")]

    digests: list[dict[str, Any]] = []
    for client in _load_clients():
        if not client.get("phones"):
            continue
        phones = [p for p in (normalize_phone(x) for x in re.split(r"[|،,]+", str(client.get("phones") or ""))) if p]
        if not phones:
            continue
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in sale_items:
            match, _reasons = _client_score(client, item.get("area"), item.get("propertyType"), item.get("price"))
            if match >= 40:
                scored.append((match, item))
        scored.sort(key=lambda pair: (pair[0], pair[1].get("score") or 0), reverse=True)
        top = [item for _match, item in scored[:top_n]]
        if not top:
            continue
        budget = str(client.get("price") or "").strip()
        label = " - ".join(x for x in (client.get("area"), client.get("type")) if x) or "عميل محتمل"
        lines = [
            f"السلام عليكم، معك [اسمك]. هذه أفضل {len(top)} فرص هذا الأسبوع تناسب طلبكم: {label}"
            + (f" (ميزانية {budget} د.ك)" if budget else "")
            + ":"
        ]
        for i, item in enumerate(top, 1):
            price = item.get("priceText") or f"{item.get('price'):,.0f} د.ك"
            valuation = item.get("valuationLabel") or ""
            sources = list(dict.fromkeys(
                e.get("source") for e in (item.get("evidence") or []) if e.get("source")
            ))
            source_text = f" — المصادر: {', '.join(sources)}" if sources else ""
            url = item.get("url")
            lines.append(
                f"{i}. {item.get('code')} — {item.get('area') or 'غير محددة'} — {price} — {valuation}{source_text}"
                + (f"\n   🔗 {url}" if url else "")
            )
        lines.append("\nهل ترغب بمتابعة التفاصيل أو حجز موعد معاينة؟ شكرًا.")
        message = "\n".join(lines)
        digests.append({
            "client": {"area": client.get("area"), "type": client.get("type"), "price": budget},
            "phones": [f"+{p}" for p in phones],
            "opportunities": top,
            "message": message,
            "matchCount": len(top),
        })
    digests.sort(key=lambda d: d["matchCount"], reverse=True)
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(digests),
        "note": (
            "موجز أسبوعي تلقائي: أفضل 10 فرص بيع لكل عميل محتمل حسب منطقه ونوع عقاره وميزانيته، "
            "بدرجة مطابقة حتمية ومصادر أدلة لكل فرصة — استبدل [اسمك] قبل الإرسال."
        ),
        "digests": digests,
    }
