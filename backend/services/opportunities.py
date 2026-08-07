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
import re
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import search_external_sources
from backend.models import PropertyRequest
from backend.services.official_valuation import get_area_benchmark
from backend.services.valuation import comparable_pool, price_label

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLIENTS_PATH = DATA_DIR / "potential_leads.csv"

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
    "Sakan": 0.5,
    "الصفقات الرسمية": 1.0,
}

TIERS = [
    ("daily", "يومية", 7, "إعلانات آخر 7 أيام"),
    ("weekly", "أسبوعية", 30, "إعلانات آخر 30 يومًا"),
    ("monthly", "شهرية", 90, "إعلانات آخر 90 يومًا"),
    ("yearly", "سنوية", 365, "إعلانات آخر 365 يومًا"),
]


def _days_ago(published: str) -> int | None:
    try:
        day = datetime.strptime(str(published)[:10], "%Y-%m-%d").date()
        return (date.today() - day).days
    except (ValueError, TypeError):
        return None


def _evidence_count(valuation) -> int:
    return valuation.comparables_count


def _confidence(source: str, valuation) -> float:
    """ثقة حتمية: 50% مصداقية المصدر + 30% ثقة التقييم + 20% قوة الأدلة."""
    trust = SOURCE_TRUST.get(source, 0.5)
    evidence_factor = min(1.0, 0.35 + _evidence_count(valuation) * 0.13)
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
    except Exception:
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


def _listing_opportunity(listing, valuation, clients: list[dict[str, Any]]) -> dict[str, Any]:
    confidence = _confidence(listing.source, valuation)
    opportunity = {
        "code": listing.code,
        "source": listing.source,
        "governorate": listing.governorate,
        "area": listing.area,
        "propertyType": listing.property_type or listing.detail_class,
        "transaction": listing.transaction,
        "price": listing.price,
        "priceText": listing.price_text or f"{listing.price:,.0f} د.ك",
        "space": listing.space,
        "publishedDate": listing.published_date,
        "daysAgo": _days_ago(listing.published_date),
        "url": listing.original_url,
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
        "evidence": [{"code": e.get("code"), "area": e.get("area"), "price": e.get("price")} for e in valuation.evidence[:4]],
    }
    # ربط العملاء المحتملين
    matched: list[dict[str, Any]] = []
    for client in clients:
        if not client.get("phones"):
            continue
        c_score, c_reasons = _client_score(client, listing.area, opportunity["propertyType"], listing.price)
        if c_score >= 40:
            matched.append({
                "area": client.get("area"),
                "type": client.get("type"),
                "price": client.get("price"),
                "phones": client.get("phones"),
                "message": client.get("message"),
                "matchScore": c_score,
                "reasons": c_reasons,
            })
    matched.sort(key=lambda m: m["matchScore"], reverse=True)
    opportunity["clients"] = matched[:3]
    return opportunity


def _area_forecast(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """توقعات لكل منطقة: وسيط سعر المتر حديث (≤30 يوم) مقابل قديم، واتجاه، وسعر المتر المتوقع."""
    buckets: dict[str, dict[str, list[float]]] = {}
    for item in scored:
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
            phones = [normalize_phone(p) for p in re.split(r"[|،,]+", str(client.get("phones") or "")) if normalize_phone(p)]
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


def build_opportunities(limit_per_tier: int = 8, include_external: bool = True) -> dict[str, Any]:
    """يبني لقطة الفرص الحالية: فئات زمنية + توقعات + عملاء محتملون، مع مصادر وأدلة وثقة حتمية.

    include_external: يدمج الإعلانات الحية من المصادر الخارجية المتصلة (الفريج محليًا +
    Mourjan/OpenSooq/... عبر الإنترنت) مع الإفصاح عن المصادر التي أسهمت.
    """
    listings = load_listings()
    clients = _load_clients()
    external_statuses: list[dict[str, Any]] = []
    if include_external:
        try:
            external_listings, external_statuses = search_external_sources(_broad_request())
            listings.extend(external_listings)
        except Exception as exc:
            external_statuses = [{"name": "المصادر الخارجية", "status": "failed", "records": 0, "note": str(exc)}]

    scored: list[dict[str, Any]] = []
    skipped_rentals = 0
    for listing in listings:
        if not listing.price:
            continue
        # خط التقييم الحالي يقارن السعر بوسيط الشراء (سعر المتر × المساحة)،
        # فلا تدخل عروض الإيجار في الفرص حتى لا يظهر إيجار شهري بقيمة «عادلة» بالمئات الآلاف
        if "للإيجار" in (listing.transaction or "") or "للإيجار" in (listing.listing_mode or ""):
            skipped_rentals += 1
            continue
        comps = comparable_pool(listing, listings)
        valuation = price_label(listing, comps)
        scored.append(_listing_opportunity(listing, valuation, clients))
    scored.sort(key=lambda item: item["score"], reverse=True)

    tiers: dict[str, dict[str, Any]] = {}
    for key, label, days, description in TIERS:
        items = [item for item in scored if item.get("daysAgo") is not None and item["daysAgo"] <= days]
        tiers[key] = {
            "label": label,
            "description": description,
            "items": items[:limit_per_tier],
        }

    contributing = [
        s.get("name")
        for s in external_statuses
        if s.get("status") in ("success", "connected") or s.get("records")
    ]
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "generatedDate": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totalListings": len(listings),
        "totalScored": len(scored),
        "skippedRentals": skipped_rentals,
        "totalClients": len(clients),
        "includeExternal": bool(include_external),
        "contributingSources": contributing,
        "confidenceMethod": "الثقة = 50% مصداقية المصدر + 30% ثقة التقييم + 20% قوة الأدلة (حتمية بلا عشوائية)",
        "rentalNote": (
            "عروض الإيجار مستبعدة من الفرص لأن خط التقييم الحالي يقارن السعر بوسيط الشراء "
            "(سعر المتر × المساحة) ولا يصلح لحكم أسعار الإيجار."
            if skipped_rentals
            else ""
        ),
        "officialDataNote": (
            "لا توجد قاعدة بيانات رسمية حية تنشر سعر المتر لكل منطقة في الكويت؛ "
            "المصادر الرسمية المتاحة هي إحصاءات وزارة العدل (التسجيل العقاري) وتقارير بيت التمويل الكويتي "
            "وبنك الكويت الوطني، وكلها لا تنشر سعر المتر التفصيلي لكل منطقة. لذلك عند غياب معيار رسمي "
            "تُشتق القيمة من وسيط الإعلانات الفعلية في نفس المنطقة مع الإفصاح الكامل عن عدد الأدلة."
        ),
        "tiers": tiers,
        "forecast": _area_forecast(scored),
    }
