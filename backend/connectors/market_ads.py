"""موصل market_ads: إعلانات السوق الحية من قاعدة Supabase (مصدر بيانات لوحة العرض).

يقرأ الإعلانات الفعلية من جدول market_ads في Supabase ويحوّلها إلى
كائنات Listing تدخل في البحث والمطابقة والتقييم — فتعمل الفلاتر
على بيانات حقيقية بدل الاعتماد فقط على الملفات المحلية (seed_listings.json).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.supabase_store import fetch_market_ads

logger = logging.getLogger(__name__)

# خريطة region الإنجليزية ← العربية للمساعدة في مطابقة المناطق
_EN_TO_AR_REGION: dict[str, str] = {
    "mutlaa": "المطلاع",
    "mutlae": "المطلاع",
    "al-mutlaa": "المطلاع",
    "almutlaa": "المطلاع",
    "jahra": "الجهراء",
    "al-jahra": "الجهراء",
    "farwaniya": "الفروانية",
    "al-farwaniya": "الفروانية",
    "hawally": "حولي",
    "hawalli": "حولي",
    "salmiya": "السالمية",
    "salwa": "سلوى",
    "bayan": "بيان",
    "rumaithiya": "الرميثية",
    "jabriya": "الجابرية",
    "fahaheel": "الفحيحيل",
    "ahmadi": "الأحمدي",
    "al-ahmadi": "الأحمدي",
    "bnaid-al-qar": "بنيد القار",
    "dasman": "الدسمة",
    "sharq": "الشرق",
    "salem": "السالم",
    "ferdous": "الفردوس",
    "khaitan": "خيطان",
    "abulla": "عبدالله",
    "sabah-al-salem": "صباح السالم",
    "sabah-al-ahmed": "صباح الأحمد",
    "sabah-al-naser": "صباح الناصر",
    "jaber-al-ahmed": "جابر الأحمد",
    "saad-al-abdallah": "سعد العبدالله",
    "north-west-sulaibikhat": "شمال غرب الصليبيخات",
    "sulaibikhat": "الصليبيخات",
    "abu-fatira": "أبو فطيرة",
    "aqeela": "العقيلة",
}

_AR_TO_EN_REGION: dict[str, str] = {}
for en_name, ar_name in _EN_TO_AR_REGION.items():
    # لكل اسم عربي، نختار أقصر اسم إنجليزي (بدون al- إن أمكن)
    existing = _AR_TO_EN_REGION.get(ar_name)
    if existing is None or len(en_name) < len(existing):
        _AR_TO_EN_REGION[ar_name] = en_name

# تحويل property_type الإنجليزي ← العربي
_PT_FROM_EN: dict[str, str] = {
    "private_residential": "بيت",
    "apartment": "شقة",
    "land": "أرض",
    "building": "عمارة",
    "villa": "بيت",
    "office": "مكتب",
    "commercial": "تجاري",
    "shop": "محل",
}


def _region_ar(region: str) -> str:
    """تحويل اسم المنطقة الإنجليزي إلى العربي (إن أمكن)."""
    if not region:
        return ""
    lowered = region.strip().lower()
    if lowered in _EN_TO_AR_REGION:
        return _EN_TO_AR_REGION[lowered]
    return region


def _pt_ar(pt: str) -> str:
    """تحويل نوع العقار من الإنجليزي إلى العربي."""
    return _PT_FROM_EN.get(pt.strip().lower(), pt)


def _price_kwd(row: dict[str, Any]) -> float | None:
    """تحويل سعر الإعلان إلى دينار كويتي بقيمة منطقية.

    بيانات market_ads غير متناسقة: بعض الصفوف تخزن السعر بالملايين (2.0 → 2M)،
    وبعضها بالآلاف (300 → 300K)، وبعضها بالدينار مباشرة (310,000). لذلك نجرب
    المضاعفات الممكنة (×1 / ×1,000 / ×1,000,000) ونختار القيمة الواقعة في
    نطاق عقاري معقول (سعر المتر 50–20,000 د.ك/م²؛ السعر الكلي 5,000–50,000,000
    د.ك) — وإلا نعيد None ليُستبعد الصف الفاسد من التقييم بدل تشويه النتائج
    (مثل ظهور «300 د.ك» لعقار أو وسيط مقارنات بملايين زائفة).
    """
    land_area = row.get("land_area_m2")
    price_per = row.get("price_per_m2")
    asking = row.get("asking_price")
    try:
        area = float(land_area) if land_area else None
    except (TypeError, ValueError):
        area = None

    def _candidates(value: Any) -> list[float]:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return []
        return [v, v * 1000, v * 1_000_000]

    # سعر المتر × المساحة (الأدق): اختر المضاعف الذي يعطي معدلًا وسعرًا منطقيين
    if price_per is not None and area:
        for per in _candidates(price_per):
            total = per * area
            if 50 <= per <= 20_000 and 5_000 <= total <= 50_000_000:
                return total
    # الاحتياط: السعر الإجمالي المعلن (اختر المضاعف في نطاق عقاري معقول)
    if asking is not None:
        for total in _candidates(asking):
            if 5_000 <= total <= 50_000_000:
                return total
    return None


def search(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """قراءة الإعلانات الحية من market_ads المطابقة للطلب."""
    # محاولة قراءة باسم المنطقة العربي (لأن market_ads.region إنجليزي)
    en_regions = set()
    ar_regions = set()
    for area in request.areas:
        ar_regions.add(area)
        mapped = _AR_TO_EN_REGION.get(area)
        if mapped:
            en_regions.add(mapped)

    # نسأل Supabase أول region (الإنجليزي عند وجوده، العربي عند عدمه)
    # نجمع كل المطابقة في تمريرتين: بالإنجليزي والعربي
    all_rows: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    search_regions = list(en_regions) if en_regions else list(ar_regions)
    if not search_regions:
        # لا منطقة محددة: نجلب الكل
        all_rows = fetch_market_ads(
            transaction=request.transaction,
            property_type=request.property_type,
            limit=500,
        )
    else:
        for sr in search_regions:
            rows = fetch_market_ads(
                transaction=request.transaction,
                property_type=request.property_type,
                region=sr,
                limit=500,
            )
            for row in rows:
                rid = row.get("id")
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    all_rows.append(row)

    listings: list[Listing] = []
    for row in all_rows:
        region_ar = _region_ar(str(row.get("region") or ""))
        pt_ar = _pt_ar(str(row.get("property_type") or ""))
        price_kwd = _price_kwd(row)
        space = row.get("land_area_m2")

        # فلتر إضافي على المنطقة (بعد الجلب من Supabase)
        if request.areas and region_ar and region_ar not in request.areas:
            # ربما المنطقة في عنوان الإعلان العربي
            title = str(row.get("title") or "")
            if not any(ar_area in title for ar_area in request.areas):
                continue

        # فلتر نوع العقار
        if request.property_type and pt_ar and pt_ar != request.property_type:
            continue

        code = f"AD-{row.get('source_listing_id') or row.get('id')}"
        listing = Listing(
            code=code,
            transaction=request.transaction or "للبيع",
            governorate="",
            area=region_ar,
            property_type=pt_ar,
            detail_class="مصدر حي",
            price=price_kwd,
            price_text=f"{price_kwd:,.0f} د.ك" if price_kwd else "غير معلن",
            space=float(space) if space else None,
            listing_mode="حي",
            summary=str(row.get("title") or ""),
            features=str(row.get("title") or ""),
            published_date=str(row.get("published_at") or "")[:10],
            original_url=str(row.get("source_url") or ""),
            source=f"السوق المباشر ({row.get('source_name', 'غير معروف')})",
            raw={
                "source_name": str(row.get("source_name") or ""),
                "region": str(row.get("region") or ""),
                "asking_price": row.get("asking_price"),
                "price_per_m2": row.get("price_per_m2"),
                "price_kwd": price_kwd,
                "land_area_m2": space,
            },
        )
        listings.append(listing)

    return listings[:50], {
        "name": "السوق المباشر",
        "status": "success" if listings else "no_results",
        "records": len(listings),
        "candidates": len(all_rows),
        "responseMs": 0,
        "url": "",
        "note": (
            f"قراءة {len(all_rows)} إعلانًا حيًا من السوق المباشر"
            f" (بوشملان) عبر Supabase."
            if listings
            else "لا توجد إعلانات مباشرة تطابق الطلب في السوق المباشر."
        ),
    }