"""موصل official_market_indicators: أسعار المتر الرسمية من قاعدة Supabase.

يقرأ المؤشرات الرسمية (reference_land_price_per_m2) من جدول
official_market_indicators ويوفّر وسيط سعر المتر لكل منطقة — هذا يُجيب
مباشرة على سؤال المستخدم السابق «ليه لا توجد بيانات رسمية موثوقة
لسعر المتر في هذه المنطقة» — البيانات موجودة في القاعدة!

يوفر:
- search(): يعيد إعلانات مؤشرات رسمية تدخل في البحث
- get_official_rate(region_name): وسيط سعر المتر الرسمي لمنطقة (للتقييم)
"""

from __future__ import annotations

import logging
import threading
import time
from statistics import median
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.supabase_store import fetch_official_indicators
from backend.connectors.market_ads import _EN_TO_AR_REGION, _AR_TO_EN_REGION

logger = logging.getLogger(__name__)

# كاش قصير (10 دقائق) لنتائج أسعار المتر الرسمية: خط التقييم يستدعي الدالة لكل إعلان،
# فلا نضرب Supabase بطلب لكل إعلان — نعيد نفس النتيجة لنفس المنطقة خلال المدة.
_RATE_CACHE: dict[str, tuple[float, tuple[float | None, str, str]]] = {}
_RATE_CACHE_LOCK = threading.Lock()
_RATE_CACHE_TTL = 600


def get_official_rate(region_name: str) -> tuple[float | None, str, str]:
    """وسيط سعر المتر الرسمي لمنطقة من مؤشرات السوق.

    يعيد (سعر المتر, اسم المصدر, ملاحظة ثقة) أو (None, '', '') عند
    عدم توفر بيانات رسمية للمنطقة.

    هكذا يدخل التقييم الرسمي في احتساب القيمة العادلة (القيمة الرسمية
    مرجّحة أعلى من الإعلانات).
    """
    if not region_name:
        return None, "", ""
    key = region_name.strip().lower()
    now = time.time()
    with _RATE_CACHE_LOCK:
        cached = _RATE_CACHE.get(key)
        if cached and now - cached[0] < _RATE_CACHE_TTL:
            return cached[1]
    try:
        # جرب باسم المنطقة العربي أولاً، وإن لم يجد جرب الإنجليزي
        search_region = region_name.strip()
        en_name = _AR_TO_EN_REGION.get(search_region.lower())
        if en_name:
            search_region = en_name
        rows = fetch_official_indicators(region=search_region)
        if not rows:
            # جرب بالاسم العربي مباشرة
            rows = fetch_official_indicators(region=region_name.strip())

        candidates: list[tuple[float, str, str]] = []  # (rate, source, confidence)
        for row in rows:
            rate = row.get("reference_land_price_per_m2")
            if not rate:
                continue
            try:
                rate_f = float(rate)
            except (TypeError, ValueError):
                continue
            source = str(row.get("source_name") or "مؤشر رسمي")
            conf = str(row.get("confidence") or "medium")
            candidates.append((rate_f, source, conf))

        if not candidates:
            # خزّن الفراغ أيضًا (TTL قصير) حتى لا تُقصف Supabase بطلب لكل إعلان
            # في المناطق بلا بيانات رسمية أثناء خط التقييم.
            with _RATE_CACHE_LOCK:
                _RATE_CACHE[key] = (now, (None, "", ""))
            return None, "", ""

        rates = [c[0] for c in candidates]
        median_rate = round(median(rates), 2)
        best_source = candidates[0][1]
        notes = f"مؤشر رسمي: {best_source} (وسيط {len(rates)} مؤشرًا)"
        result = (median_rate, best_source, notes)
        with _RATE_CACHE_LOCK:
            _RATE_CACHE[key] = (now, result)
        return result

    except Exception as exc:
        logger.warning("official_indicators.get_official_rate failed: %s", exc)
        return None, "", ""


def search(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """قراءة المؤشرات الرسمية وعرضها كإعلانات تقييمية (تظهر في التحليل)."""
    rows = fetch_official_indicators()
    listings: list[Listing] = []
    seen_regions: set[str] = set()

    # المناطق المطلوبة (مع ترجمة العربي ← إنجليزي، بمقارنة حساسة لحالة الأحرف)
    requested_lower: set[str] = set()
    for a in (request.areas or []):
        requested_lower.add(a.lower())
        en_name = _AR_TO_EN_REGION.get(a.lower())
        if en_name:
            requested_lower.add(en_name.lower())

    for row in rows:
        region = str(row.get("region") or "")
        region_lower = region.lower()
        if not region or region_lower in seen_regions:
            continue
        seen_regions.add(region_lower)

        if requested_lower and region_lower not in requested_lower:
            continue

        rate = row.get("reference_land_price_per_m2")
        cap_rate = row.get("prevailing_cap_rate")
        try:
            rate_f = float(rate) if rate else None
            cap_f = float(cap_rate) if cap_rate else None
        except (TypeError, ValueError):
            rate_f = cap_f = None

        source = str(row.get("source_name") or "مؤشر رسمي")
        quarter = str(row.get("source_quarter") or "")

        listing = Listing(
            code=f"OFFIND-{region}",
            transaction="",
            governorate="",
            area=region,
            property_type=str(row.get("property_type") or "عقارات"),
            detail_class="مؤشر رسمي",
            price=rate_f,
            price_text=f"{rate_f:,.0f} د.ك/م²" if rate_f else "غير متوفر",
            space=None,
            listing_mode="رسمي",
            summary=(
                f"سعر المتر المرجعي في {region}: {rate_f:,.0f} د.ك/م² ({source} - {quarter})"
                if rate_f
                else f"مؤشر رسمي في {region} بلا سعر متر مرجعي ({source} - {quarter})"
            ),
            features=(
                f"مؤشر رسمي | سعر المتر: {rate_f:,.0f} د.ك/م² | المصدر: {source} | {quarter}"
                if rate_f
                else f"مؤشر رسمي | بلا سعر متر | المصدر: {source} | {quarter}"
            )
            + (f" | نسبة الرسملة: {cap_f:.1%}" if cap_f else ""),
            published_date=str(row.get("effective_from") or "")[:10],
            original_url="",
            source="مؤشرات رسمية",
            raw={
                "official_rate": rate_f,
                "cap_rate": cap_f,
                "source_name": source,
                "quarter": quarter,
                "confidence": str(row.get("confidence") or ""),
                "notes": str(row.get("notes") or ""),
            },
        )
        listings.append(listing)

    return listings, {
        "name": "مؤشرات رسمية",
        "status": "success" if listings else "no_data",
        "records": len(listings),
        "candidates": len(rows),
        "responseMs": 0,
        "url": "",
        "note": (
            f"قراءة {len(rows)} مؤشرًا رسميًا لأسعار المتر"
            + (f"؛ منها {len(listings)} في المناطق المطلوبة" if request.areas else ".")
            + " هذه الأسعار تدخل كمرجع تقييم مرجّح (أعلى مصداقية من الإعلانات)."
            if rows
            else "لا توجد مؤشرات رسمية مستوردة بعد في جدول official_market_indicators."
        ),
    }