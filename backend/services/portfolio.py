"""محفظة المستثمر المجانية — تقييم القيمة الحالية للعقارات المسجلة.

القيمة التقديرية = المساحة × سعر المتر المتوقع في المنطقة (من لقطة التوقعات
expectedPricePerSqm)، مع سقوط إلى وسيط price_trends (منطقة+نوع، ثم منطقة فقط)
عند غياب التوقع. العائد = الإيجار السنوي ÷ سعر الشراء.

كل الدوال نقية بلا شبكة — قابلة للاختبار مباشرة.
"""
from __future__ import annotations

import re
from typing import Any

_AR_TATWEEL = re.compile(r"[\u0640]")


def _norm(text: Any) -> str:
    s = _AR_TATWEEL.sub("", str(text or "")).strip()
    s = (
        s.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
        .replace("ـ", "")
    )
    return re.sub(r"\s+", " ", s).strip()


def _to_num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and f != float("inf") and f != float("-inf") else None


def expected_price_per_sqm(area: str, forecast: list[dict[str, Any]] | None) -> float | None:
    """سعر المتر المتوقع للمنطقة من لقطة التوقعات (أعلى قيمة إن تكررت المنطقة)."""
    if not forecast:
        return None
    target = _norm(area)
    best: float | None = None
    for entry in forecast:
        if not isinstance(entry, dict):
            continue
        if _norm(entry.get("area")) != target:
            continue
        value = _to_num(entry.get("expectedPricePerSqm"))
        if value is not None and value > 0 and (best is None or value > best):
            best = value
    return best


def median_price_per_sqm(
    area: str, property_type: str, trends: list[dict[str, Any]] | None
) -> float | None:
    """سعر المتر من price_trends: أحدث شهر لمنطقة+نوع، ثم منطقة فقط."""
    if not trends:
        return None
    area_n = _norm(area)
    type_n = _norm(property_type)
    by_type: dict[tuple[str, str], tuple[str, float]] = {}
    by_area: dict[str, tuple[str, float]] = {}
    for t in trends:
        if not isinstance(t, dict):
            continue
        value = _to_num(t.get("median_price_per_m2"))
        if value is None or value <= 0:
            continue
        month = str(t.get("month") or "")
        row_area = _norm(t.get("area"))
        row_type = _norm(t.get("property_type"))
        if row_area != area_n:
            continue
        prev_area = by_area.get(area_n)
        if prev_area is None or month > prev_area[0]:
            by_area[area_n] = (month, value)
        if row_type and row_type == type_n:
            prev_type = by_type.get((area_n, type_n))
            if prev_type is None or month > prev_type[0]:
                by_type[(area_n, type_n)] = (month, value)
    if (area_n, type_n) in by_type:
        return by_type[(area_n, type_n)][1]
    if area_n in by_area:
        return by_area[area_n][1]
    return None


def estimate_current_value(
    item: dict[str, Any],
    forecast: list[dict[str, Any]] | None = None,
    trends: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """تقييم عقار واحد: القيمة الحالية + التغير مقابل سعر الشراء + العائد السنوي."""
    space = _to_num(item.get("space"))
    purchase = _to_num(item.get("purchase_price"))
    rent = _to_num(item.get("monthly_rent"))
    per_sqm = expected_price_per_sqm(item.get("area") or "", forecast)
    if per_sqm is None:
        per_sqm = median_price_per_sqm(item.get("area") or "", item.get("property_type") or "", trends)
    value = round(space * per_sqm, 2) if space and per_sqm else None
    change_pct = (
        round((value - purchase) / purchase * 100, 1) if value is not None and purchase else None
    )
    yield_pct = round(rent * 12 / purchase * 100, 1) if rent and purchase else None
    return {
        "estimatedValue": value,
        "pricePerSqm": per_sqm,
        "changePct": change_pct,
        "yieldPct": yield_pct,
    }


def build_summary(
    items: list[dict[str, Any]] | None,
    forecast: list[dict[str, Any]] | None = None,
    trends: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """تقييم كل عقارات المستخدم دفعة واحدة (بدون تغيير العناصر الأصلية)."""
    result: list[dict[str, Any]] = []
    for item in items or []:
        merged = dict(item)
        merged.update(estimate_current_value(item, forecast, trends))
        result.append(merged)
    return result
