from __future__ import annotations

import re
from collections import Counter
from typing import Any

from backend.models import Listing
from backend.services.request_parser import GOVERNORATE_AREAS


def is_demand_transaction(transaction: str) -> bool:
    """طلب (مطلوب للشراء/للإيجار) مقابل عرض (للبيع/للإيجار)."""
    return "مطلوب" in transaction


def is_sale_transaction(transaction: str) -> bool:
    """بيع أو شراء — تشمل «مطلوب للشراء» (كلمة «شراء» لا تحتوي «بيع»)."""
    return ("بيع" in transaction) or ("شراء" in transaction)


def is_rent_transaction(transaction: str) -> bool:
    """إيجار بصيغتي الهمزة (إيجار/ايجار/أجار)."""
    return ("إيجار" in transaction) or ("ايجار" in transaction) or ("أجار" in transaction)


def local_listing_to_row(listing: Listing) -> dict[str, Any]:
    """تحويل كائن Listing محلي (الفريج) إلى صف بنفس شكل market_listings.

    المحللات النقية تستهلك صفوفًا قياسية؛ هذا التحويل يجعل إعلانات الفريج
    (عرضًا وطلبًا) تدخل نفس التجميع بلا فرع خاص في منطق الحساب.
    """
    raw = listing.raw if isinstance(listing.raw, dict) else {}
    return {
        "source": listing.source or "الفريج",
        "transaction": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "property_type": listing.property_type,
        "price": listing.price,
        "space": listing.space,
        "phone": str(raw.get("phone") or ""),
        "fetched_at": str(raw.get("fetchedAt") or raw.get("publishedDate") or listing.published_date or ""),
        "original_url": listing.original_url,
        "code": listing.code,
    }


def local_listings_to_rows(listings: list[Listing]) -> list[dict[str, Any]]:
    """تحويل قائمة إعلانات الفريج المحلية إلى صفوف تحليل."""
    return [local_listing_to_row(listing) for listing in listings]


def _demand_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    """عدّ طلبات الشراء والإيجار (جهة الطلب) في مجموعة صفوف."""
    buy = rent = 0
    for row in rows:
        transaction = str(row.get("transaction") or "").strip()
        if not is_demand_transaction(transaction):
            continue
        if is_sale_transaction(transaction):
            buy += 1
        elif is_rent_transaction(transaction):
            rent += 1
    return {"buyRequests": buy, "rentRequests": rent}


def build_demand_indicators(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """مؤشرات الطلب من سجلات «مطلوب» (شراء/إيجار) — عدّ + اتجاه شهري (نقية).

    - لكل منطقة ومحافظة: عدّ طلبات الشراء والإيجار (من إعلانات الفريج المحلية
      والمنصات الخارجية المحصودة مثل قسم «مطلوب» في 4Sale).
    - سلسلة شهرية لعدد الطلبات (من fetched_at) لرسم الاتجاه.
    - توزيع حسب المنصة (source) بشفافية: يعرف المتصفح من أين جاءت كل طلبات.
    متسامح: بلا صفوف طلب تعيد عدّادات صفرية بدل كسر المتصل.
    """
    by_area: dict[str, dict[str, Any]] = {}
    by_gov: dict[str, dict[str, Any]] = {}
    by_platform: dict[str, dict[str, Any]] = {}
    monthly: dict[str, dict[str, int]] = {}
    area_gov = _area_to_governorate_map()
    for row in rows:
        transaction = str(row.get("transaction") or "").strip()
        if not is_demand_transaction(transaction):
            continue
        is_buy = is_sale_transaction(transaction)
        is_rent = is_rent_transaction(transaction)
        if not (is_buy or is_rent):
            continue
        area = str(row.get("area") or "").strip() or "غير محددة"
        gov = str(row.get("governorate") or "").strip() or "غير محددة"
        # صفوف الحصاد الخارجي (مثل «مطلوب» 4Sale) تُخزَّن بلا محافظة رغم أن منطقتها
        # معروفة — نعبئ المحافظة من خريطة المنطقة الرسمية حتى لا تتكدس كل الطلبات
        # تحت «غير محددة» في بُعد المحافظات.
        if gov == "غير محددة" and area != "غير محددة" and area in area_gov:
            gov = f"محافظة {area_gov[area]}"
        # توحيد شكل المحافظة (محافظة الأحمدي == محافظة الاحمدي) عبر المصادر حتى لا
        # تنقسم دلاء نفس المحافظة في الـ payload وفي العرض.
        gov = re.sub(r"[إأآا]", "ا", gov)
        source = str(row.get("source") or "").strip() or "غير محدد"
        month = str(row.get("fetched_at") or "")[:7]

        area_bucket = by_area.setdefault(area, {"area": area, "governorate": gov, "buy": 0, "rent": 0})
        gov_bucket = by_gov.setdefault(gov, {"governorate": gov, "buy": 0, "rent": 0})
        platform_bucket = by_platform.setdefault(source, {"source": source, "buy": 0, "rent": 0})
        if is_buy:
            area_bucket["buy"] += 1
            gov_bucket["buy"] += 1
            platform_bucket["buy"] += 1
        elif is_rent:
            area_bucket["rent"] += 1
            gov_bucket["rent"] += 1
            platform_bucket["rent"] += 1
        if len(month) == 7:
            month_bucket = monthly.setdefault(month, {"month": month, "buy": 0, "rent": 0})
            if is_buy:
                month_bucket["buy"] += 1
            elif is_rent:
                month_bucket["rent"] += 1

    def _finalize(bucket: dict[str, Any]) -> dict[str, Any]:
        return {**bucket, "total": int(bucket["buy"]) + int(bucket["rent"])}

    areas = sorted((_finalize(b) for b in by_area.values()), key=lambda a: (-a["total"], a["area"]))
    governorates = sorted((_finalize(b) for b in by_gov.values()), key=lambda g: (-g["total"], g["governorate"]))
    platforms = sorted((_finalize(b) for b in by_platform.values()), key=lambda p: (-p["total"], p["source"]))
    series = [monthly[m] for m in sorted(monthly)]
    totals = {
        "buyRequests": sum(b["buy"] for b in by_area.values()),
        "rentRequests": sum(b["rent"] for b in by_area.values()),
    }
    totals["total"] = totals["buyRequests"] + totals["rentRequests"]
    for platform in platforms:
        platform["sharePct"] = round(platform["total"] / totals["total"] * 100, 1) if totals["total"] else 0.0
    return {
        "totals": totals,
        "areas": areas,
        "governorates": governorates,
        "platforms": platforms,
        "series": series,
    }


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 1)


def clean_outliers(values: list[float]) -> list[float]:
    """إزالة القيم الشاذة بمعيار 3×IQR (للعينات ≥4) قبل حساب الوسيط.

    الأسعار المهرطبة من صفحات الإعلانات (مثل إيجار 127 ألف شهريًا أو بيع 9
    آلاف لمنطقة سكنية) تُشوّه الوسيط والعائد؛ هذا التنظيف يجعل المتوسطات
    ممثلة للعرض الفعلي دون حذف بيانات حقيقية عند العينات الصغيرة.
    """
    if len(values) < 4:
        return values
    ordered = sorted(values)
    q1 = ordered[len(ordered) // 4]
    q3 = ordered[(3 * len(ordered)) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return values
    lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
    return [v for v in values if lo <= v <= hi]


def _area_to_governorate_map() -> dict[str, str]:
    """خريطة رسمية منطقة ← محافظة (من المحلل) لتغطية الصفوف بلا محافظة مخزنة."""
    area_gov: dict[str, str] = {}
    for gov, areas in GOVERNORATE_AREAS.items():
        for area in areas:
            area_gov.setdefault(area, gov)
    return area_gov


def build_market_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """تحليلات الحصاد المتراكم من market_listings لكل موقع على حدة (نقية).

    تُجمَّع الصفوف (كل المواقع) في Python لأن REST لا يدعم group-by:
    - لكل مصدر: عدد الإعلانات، خلط المعاملات، أنواع العقار، المناطق،
      وسيط السعر والمساحة (حيثما وُجدت أرقام صالحة).
    - المناطق الأكثر تغطية (ترتيب تنازلي).
    متسامح: صفوف فارغة تعيد تجميعًا فارغًا بدل كسر المتصل.
    """
    by_source: dict[str, dict[str, Any]] = {}
    area_counts: dict[str, int] = {}
    gov_counts: dict[str, int] = {}
    trans_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    last_fetched = ""
    for row in rows:
        source = str(row.get("source") or "غير معروف").strip() or "غير معروف"
        bucket = by_source.setdefault(source, {
            "source": source,
            "count": 0,
            "transactions": {},
            "propertyTypes": set(),
            "areas": set(),
            "governorates": set(),
            "prices": [],
            "spaces": [],
            "phones": 0,
            "lastFetched": "",
        })
        bucket["count"] += 1
        if row.get("phone"):
            bucket["phones"] += 1
        transaction = str(row.get("transaction") or "").strip()
        property_type = str(row.get("property_type") or "").strip()
        area = str(row.get("area") or "").strip()
        governorate = str(row.get("governorate") or "").strip()
        if transaction:
            bucket["transactions"][transaction] = bucket["transactions"].get(transaction, 0) + 1
            trans_counts[transaction] = trans_counts.get(transaction, 0) + 1
        if property_type:
            bucket["propertyTypes"].add(property_type)
            type_counts[property_type] = type_counts.get(property_type, 0) + 1
        if area:
            bucket["areas"].add(area)
            area_counts[area] = area_counts.get(area, 0) + 1
        if governorate:
            bucket["governorates"].add(governorate)
            gov_counts[governorate] = gov_counts.get(governorate, 0) + 1
        try:
            price = float(row.get("price"))
            if price and price > 0:
                bucket["prices"].append(price)
        except (TypeError, ValueError):
            pass
        try:
            space = float(row.get("space"))
            if space and space > 0:
                bucket["spaces"].append(space)
        except (TypeError, ValueError):
            pass
        fetched = str(row.get("fetched_at") or "")
        if fetched > bucket["lastFetched"]:
            bucket["lastFetched"] = fetched
        if fetched > last_fetched:
            last_fetched = fetched

    sources = []
    for bucket in by_source.values():
        sources.append({
            "source": bucket["source"],
            "count": bucket["count"],
            "transactions": bucket["transactions"],
            "propertyTypes": sorted(bucket["propertyTypes"]),
            "areas": sorted(bucket["areas"]),
            "governorates": sorted(bucket["governorates"]),
            "price": {"median": median(bucket["prices"]), "min": min(bucket["prices"]) if bucket["prices"] else None, "max": max(bucket["prices"]) if bucket["prices"] else None},
            "space": {"median": median(bucket["spaces"])},
            "phones": bucket["phones"],
            "lastFetched": bucket["lastFetched"],
        })
    sources.sort(key=lambda item: item["count"], reverse=True)
    areas = sorted(area_counts.items(), key=lambda pair: pair[1], reverse=True)[:30]
    return {
        "totals": {
            "rows": len(rows),
            "sources": len(sources),
            "areas": len(area_counts),
            "governorates": len(gov_counts),
            "transactions": trans_counts,
            "propertyTypes": type_counts,
            "lastFetched": last_fetched,
            "demand": _demand_breakdown(rows),
        },
        "sources": sources,
        "areas": [{"area": area, "count": count} for area, count in areas],
    }


def build_market_insights(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """تحليلات السوق الموجة 1: عائد الإيجار واتجاه سعر المتر لكل منطقة (نقية).

    - لكل منطقة: وسيط سعر البيع، وسيط سعر المتر للبيع، وسيط الإيجار، وسيط
      إيجار المتر، ثم **عائد الإيجار** = (وسيط الإيجار × 12) ÷ وسيط سعر البيع × 100.
    - سلسلة شهرية لسعر متر البيع لكل منطقة (من fetched_at).
    - اتجاه الوسيط الإجمالي للمحافظات.
    متسامح: صفوف فارغة تعيد تجميعًا فارغًا بدل كسر المتصل.
    """
    area_gov = _area_to_governorate_map()

    by_area: dict[str, dict[str, Any]] = {}
    for row in rows:
        area = str(row.get("area") or "").strip()
        if not area:
            continue
        transaction = str(row.get("transaction") or "").strip()
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if not price or price <= 0:
            continue
        try:
            space = float(row.get("space"))
        except (TypeError, ValueError):
            space = None
        per_m2 = price / space if space and space > 0 else None
        governorate = str(row.get("governorate") or "").strip() or area_gov.get(area, "")
        bucket = by_area.setdefault(area, {
            "area": area,
            "governorate": governorate,
            "salePrices": [],
            "salePerM2": [],
            "rentPrices": [],
            "rentPerM2": [],
            "monthlyPerM2": {},  # month -> [per_m2]
        })
        # ميزانيات الطلب (مطلوب للشراء/للإيجار) ليست أسعار عرض — تُعدّ في sampleTotals
        # لكنها لا تدخل وسيطات العرض حتى لا تُشوّه سعر السوق (مطلوب للشراء كان
        # يُسقط سابقًا لغياب «بيع» في نصه، بينما مطلوب للإيجار كان يدخل الإيجار!)
        is_demand = is_demand_transaction(transaction)
        is_rent = is_rent_transaction(transaction) and not is_demand
        is_sale = is_sale_transaction(transaction) and not is_demand
        if is_rent:
            bucket["rentPrices"].append(price)
            if per_m2:
                bucket["rentPerM2"].append(per_m2)
        elif is_sale:
            bucket["salePrices"].append(price)
            if per_m2:
                bucket["salePerM2"].append(per_m2)
                month = str(row.get("fetched_at") or "")[:7]
                if len(month) == 7:
                    bucket["monthlyPerM2"].setdefault(month, []).append(per_m2)

    # سلسلة شهرية عامة لاتجاه السوق (وسيط سعر المتر لكل أشهر الحصاد)
    monthly_all: dict[str, list[float]] = {}
    for row in rows:
        tx = str(row.get("transaction") or "")
        if not is_sale_transaction(tx) or is_demand_transaction(tx):
            continue
        try:
            _p = float(row.get("price"))
            _s = float(row.get("space"))
        except (TypeError, ValueError):
            continue
        if _p <= 0 or _s <= 0:
            continue
        month = str(row.get("fetched_at") or "")[:7]
        if len(month) == 7:
            monthly_all.setdefault(month, []).append(_p / _s)
    overall_series = [
        {"month": m, "perM2": median(v)}
        for m, v in sorted(monthly_all.items())
        if median(v) is not None
    ]
    market_direction = "مستقر"
    market_change = 0.0
    if len(overall_series) >= 2:
        first, last = overall_series[0]["perM2"], overall_series[-1]["perM2"]
        if first:
            market_change = round((last - first) / first * 100, 1)
            market_direction = "صاعد" if market_change >= 3 else ("هابط" if market_change <= -3 else "مستقر")

    areas = []
    for bucket in by_area.values():
        clean_sale = clean_outliers(bucket["salePrices"])
        clean_sale_per_m2 = clean_outliers(bucket["salePerM2"])
        clean_rent = clean_outliers(bucket["rentPrices"])
        clean_rent_per_m2 = clean_outliers(bucket["rentPerM2"])
        sale_median = median(clean_sale)
        sale_per_m2 = median(clean_sale_per_m2)
        rent_median = median(clean_rent)
        rent_per_m2 = median(clean_rent_per_m2)
        # عائد الإيجار فقط عند توفر بيع وإيجار معًا (بعد التنظيف) بحد أدنى لعينتين
        # لكل منهما، وسعر بيع أكبر من الإيجار السنوي — وإلا يبقى غير محسوب بدل
        # عرض نسب مضللة من عينات مفردة أو أرقام مهرطبة.
        sale_ok = len(clean_sale) >= 2
        rent_ok = len(clean_rent) >= 2
        yield_pct = None
        yield_note = ""
        if sale_ok and rent_ok and sale_median and rent_median and sale_median > rent_median * 12:
            computed = round((rent_median * 12) / sale_median * 100, 2)
            # سقف واقعي: عائد > 15% يكاد دائمًا يكون خطأ بيانات لا فرصة حقيقية
            if 0 < computed <= 15:
                yield_pct = computed
                yield_note = "high" if (len(clean_sale) >= 5 and len(clean_rent) >= 5) else "low"
        areas.append({
            "area": bucket["area"],
            "governorate": bucket["governorate"],
            "saleCount": len(bucket["salePrices"]),
            "rentCount": len(bucket["rentPrices"]),
            "outliersRemoved": len(bucket["salePrices"]) - len(clean_sale) + len(bucket["rentPrices"]) - len(clean_rent),
            "medianSalePrice": sale_median,
            "medianSalePerM2": sale_per_m2,
            "medianRent": rent_median,
            "medianRentPerM2": rent_per_m2,
            "rentalYield": yield_pct,
            "yieldNote": yield_note,
        })
    areas.sort(key=lambda a: (a["rentalYield"] is not None, a["rentalYield"] or 0), reverse=True)

    # سلسلة شهرية لسعر متر البيع: خط لكل منطقة (آخر 8 أشهر) للمناطق ذات بيانات كافية
    months = sorted({m for b in by_area.values() for m in b["monthlyPerM2"]})[-8:]
    series = []
    for bucket in by_area.values():
        pts = []
        for month in months:
            values = bucket["monthlyPerM2"].get(month) or []
            month_median = median(values)
            if month_median is not None:
                pts.append({"month": month, "perM2": month_median})
        if len(pts) >= 2:
            series.append({"area": bucket["area"], "points": pts})
    series.sort(key=lambda s: -max(p["perM2"] for p in s["points"]))
    series = series[:12]

    # وسيط سعر المتر للمحافظات (من مناطقها) — ترتيب تنازلي
    gov_buckets: dict[str, list[float]] = {}
    for area in areas:
        if area["medianSalePerM2"] and area["governorate"]:
            gov_buckets.setdefault(area["governorate"], []).append(area["medianSalePerM2"])
    governorates = [
        {"governorate": gov, "medianSalePerM2": median(values)}
        for gov, values in gov_buckets.items()
    ]
    governorates.sort(key=lambda g: g["medianSalePerM2"] or 0, reverse=True)

    # تفصيل المصادر: أي المواقع غذّت هذا التحليل وبكم (يشمل الفريج المحلي)
    _source_counter = Counter(str(row.get("source") or "غير معروف").strip() for row in rows if str(row.get("area") or "").strip())
    sources = [
        {"source": name, "count": count, "sharePct": round(count / len(rows) * 100, 1)}
        for name, count in _source_counter.most_common()
    ]

    return {
        "areas": areas,
        "series": series,
        "months": months,
        "governorates": governorates,
        "sources": sources,
        "market": {
            "direction": market_direction,
            "changePct": market_change,
            "series": overall_series,
        },
        "sampleTotals": {
            "sale": sum(1 for r in rows if is_sale_transaction(str(r.get("transaction") or "")) and not is_demand_transaction(str(r.get("transaction") or ""))),
            "rent": sum(1 for r in rows if is_rent_transaction(str(r.get("transaction") or "")) and not is_demand_transaction(str(r.get("transaction") or ""))),
            **_demand_breakdown(rows),
        },
    }
