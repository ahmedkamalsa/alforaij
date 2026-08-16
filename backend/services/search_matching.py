"""مطابقة البحث المحفوظ بالفرص (المهمة 2): درجة حتمية 0-100 بلا عشوائية.

تعيد استخدام فلسفة مطابقة العملاء (المنطقة 40 + النوع 30 + تقارب السعر 30)
مع معايير البحث المحفوظ: مناطق/محافظات متعددة + نوع + ميزانية (دنيا/قصوى).

بوابة العملية: تعارض صريح (بحث «للبيع» مقابل فرصة «للإيجار») يُسقط التطابق
تمامًا (0.0) — أما غياب معايير كليًا فيُسقط أيضًا (بحث فارغ لا يطابق شيئًا).
"""
from __future__ import annotations

import re
from typing import Any

_TRANSACTION_FAMILY: dict[str, str] = {
    "للبيع": "sale",
    "بيع": "sale",
    "مطلوب للشراء": "sale",
    "شراء": "sale",
    "نشتري": "sale",
    "للإيجار": "rent",
    "للايجار": "rent",
    "إيجار": "rent",
    "ايجار": "rent",
    "مطلوب للإيجار": "rent",
    "استأجر": "rent",
    "بدل": "swap",
}

MATCH_THRESHOLD = 40.0  # نفس عتبة مطابقة العملاء: دونها لا يُعد تطابقًا


def _family(transaction: str) -> str:
    return _TRANSACTION_FAMILY.get(str(transaction or "").strip(), "")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", "").strip())
        return number or None
    except (TypeError, ValueError):
        return None


def match_search_to_item(search: dict[str, Any], item: dict[str, Any]) -> float:
    """درجة تطابق بحث محفوظ لفرصة (0-100) — أعلى أفضل، دون 40 لا يُعد تطابقًا.

    - search: {transaction_type, property_type, areas[], governorates[],
               price_min, price_max}
    - item:   {transaction/propertyType, area, governorate, price}

    حتمية بالكامل: لا عشوائية ولا ترتيب يعتمد على التنفيذ.
    """
    area = str(item.get("area") or "").strip()
    governorate = str(item.get("governorate") or "").strip()
    item_type = str(item.get("propertyType") or item.get("property_type") or "").strip()
    item_transaction = str(item.get("transaction") or item.get("transaction_type") or "").strip()
    price = _to_float(item.get("price"))

    search_type = str(search.get("property_type") or "").strip()
    search_tx = str(search.get("transaction_type") or "").strip()
    search_areas = [str(a).strip() for a in (search.get("areas") or []) if str(a or "").strip()]
    search_govs = [str(g).strip() for g in (search.get("governorates") or []) if str(g or "").strip()]
    price_min = _to_float(search.get("price_min"))
    price_max = _to_float(search.get("price_max"))

    has_criteria = bool(search_tx or search_type or search_areas or search_govs or price_min or price_max)
    if not has_criteria:
        return 0.0

    # بوابة العملية: تعارض صريح بين العائلتين يُسقط التطابق
    if search_tx and item_transaction:
        fam = _family(search_tx)
        if fam and fam != "swap" and _family(item_transaction) != fam:
            return 0.0

    # بوابة المنطقة (حادة مثل مطابقة العملاء): البحث المحدد بمناطق لا يُنبّه
    # إلا لمنطقة ضمنها — حتى لا تصل تنبيهات من مناطق أخرى ولو تطابق النوع والميزانية.
    if area and search_areas:
        if area in search_areas:
            area_points = 40.0
        elif any(area in a or a in area for a in search_areas):
            area_points = 40.0  # منطقة متضمنة (إعلان «شمال غرب الصليبيخات» لبحث «الصليبيخات»)
        else:
            return 0.0
    else:
        area_points = 0.0

    points = 0.0

    # المنطقة/المحافظة: 40 (المحافظة فقط +30 — أضعف من المنطقة الصريحة)
    if area_points == 0.0 and governorate and search_govs and governorate in search_govs:
        area_points = 30.0
    points += area_points

    # نوع العقار: 30
    if item_type and search_type:
        if item_type == search_type:
            points += 30.0
        elif item_type in search_type or search_type in item_type:
            points += 18.0

    # الميزانية: 30
    if price is not None and (price_min is not None or price_max is not None):
        if price_min is not None and price_max is not None:
            if price_min <= price <= price_max:
                points += 30.0
            elif price <= price_max * 1.5:
                points += 15.0
        elif price_max is not None:
            if price <= price_max:
                points += 30.0
            elif price <= price_max * 1.5:
                points += 15.0
        elif price_min is not None and price >= price_min:
            points += 30.0

    return round(min(100.0, points), 1)
