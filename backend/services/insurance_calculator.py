"""حاسبة التأمين العقاري — الكويت.

أنواع التأمين العقاري في الكويت:
1. تأمين الممتلكات (Property Insurance): يغطي الأضرار الفعلية للعقار
2. تأمين المسؤولية المدنية (Liability): يغطي المسؤولية القانونية
3. تأمين المحتويات (Contents): يغطي الأثاث والمحتويات

ملاحظة: الفوائد تقريبية وتتغير حسب tuổi العقار ونوعه وموقعه.

المصادر:
- التأمين الوطني (Kuwait National Insurance)
- شركة الكويت للتأمين
- بوبيان للتأمين
"""
from __future__ import annotations

from typing import Optional

# ── أنواع التأمين وأسعارها السنوية (%) ──
INSURANCE_TYPES = {
    "property": {
        "name": "تأمين الممتلكات",
        "name_en": "Property Insurance",
        "rate_min": 0.15,  # 0.15% من قيمة العقار سنوياً
        "rate_max": 0.35,  # 0.35% للعقار القديم
        "description": "يغطي الأضرار الفعلية للعقار (حريق، فيضان، زلزال)",
        "features": ["تغطية شاملة للعقار", "تعويض عن الأضرار الفعلية", "حماية من الكوارث الطبيعية"],
    },
    "contents": {
        "name": "تأمين المحتويات",
        "name_en": "Contents Insurance",
        "rate_min": 0.20,  # 0.20% من قيمة المحتويات سنوياً
        "rate_max": 0.50,
        "description": "يغطي الأثاث والأجهزة والمحتويات الداخلية",
        "features": ["تغطية الأثاث والأجهزة", "تعويض عن السرقة", "حماية أثناء النقل"],
    },
    "liability": {
        "name": "تأمين المسؤولية المدنية",
        "name_en": "Liability Insurance",
        "rate_min": 0.05,  # 0.05% سنوياً
        "rate_max": 0.15,
        "description": "يغطي المسؤولية القانونية عن الأضرار للآخرين",
        "features": ["حماية من الدعاوى القضائية", "تغطية إصابات الزوار", "مسؤولية الممتلكات"],
    },
    "comprehensive": {
        "name": "التأمين الشامل",
        "name_en": "Comprehensive Insurance",
        "rate_min": 0.30,  # 0.30% من قيمة العقار سنوياً
        "rate_max": 0.60,
        "description": "يجمع الممتلكات + المحتويات + المسؤولية المدنية",
        "features": ["تغطية شاملة للعقار والمحتويات", "حماية شاملة من جميع المخاطر", "خدمة صيانة واصلاح"],
    },
}

# ── عوامل الخصم ──
DISCOUNT_FACTORS = {
    "new_building": 0.15,  # عقار جديد (< 5 سنوات) → خصم 15%
    "security_system": 0.10,  # نظام أمان → خصم 10%
    "fire_alarm": 0.05,  # إنذار حريق → خصم 5%
    "multi_year": 0.08,  # تأمين 3+ سنوات → خصم 8%
}

# ── حدود التأمين الأدنى ──
MIN_INSURANCE_AMOUNT = 50000  # 50,000 د.ك
MAX_INSURANCE_AMOUNT = 5000000  # 5,000,000 د.ك


def calculate_insurance(
    property_value: float,
    insurance_type: str = "property",
    contents_value: float = 0,
    building_age: int = 0,
    has_security: bool = False,
    has_fire_alarm: bool = False,
    years: int = 1,
) -> dict:
    """حساب التأمين العقاري.
    
    Args:
        property_value: قيمة العقار بالدينار الكويتي
        insurance_type: نوع التأمين (property/contents/liability/comprehensive)
        contents_value: قيمة المحتويات (للحساب المحتويات)
        building_age: عمر البناء بالسنوات
        has_security: هل يوجد نظام أمان
        has_fire_alarm: هل يوجد إنذار حريق
        years: مدة التأمين بالسنوات
    
    Returns:
        تفاصيل التأمين مع التكلفة
    """
    if property_value <= 0:
        return {"error": "قيمة العقار يجب أن تكون أكبر من صفر"}
    
    if property_value < MIN_INSURANCE_AMOUNT:
        return {"error": f"الحد الأدنى للتأمين {MIN_INSURANCE_AMOUNT:,.0f} د.ك"}
    
    if property_value > MAX_INSURANCE_AMOUNT:
        return {"error": f"الحد الأقصى للتأمين {MAX_INSURANCE_AMOUNT:,.0f} د.ك"}
    
    insurance_info = INSURANCE_TYPES.get(insurance_type, INSURANCE_TYPES["property"])
    
    # حساب نسبة التأمين بناءً على عمر العقار
    base_rate = insurance_info["rate_min"]
    max_rate = insurance_info["rate_max"]
    
    if building_age <= 5:
        rate = base_rate
    elif building_age <= 10:
        rate = base_rate + (max_rate - base_rate) * 0.3
    elif building_age <= 20:
        rate = base_rate + (max_rate - base_rate) * 0.6
    else:
        rate = max_rate
    
    # حساب الخصومات
    discounts = []
    total_discount = 0
    
    if building_age <= 5:
        discounts.append({"name": "عقار جديد", "percent": DISCOUNT_FACTORS["new_building"]})
        total_discount += DISCOUNT_FACTORS["new_building"]
    
    if has_security:
        discounts.append({"name": "نظام أمان", "percent": DISCOUNT_FACTORS["security_system"]})
        total_discount += DISCOUNT_FACTORS["security_system"]
    
    if has_fire_alarm:
        discounts.append({"name": "إنذار حريق", "percent": DISCOUNT_FACTORS["fire_alarm"]})
        total_discount += DISCOUNT_FACTORS["fire_alarm"]
    
    if years >= 3:
        discounts.append({"name": "تأمين متعدد السنوات", "percent": DISCOUNT_FACTORS["multi_year"]})
        total_discount += DISCOUNT_FACTORS["multi_year"]
    
    # تطبيق الخصم
    final_rate = rate * (1 - total_discount)
    
    # حساب التكلفة
    annual_cost = property_value * (final_rate / 100)
    
    # إضافة تأمين المحتويات إذا كان شامل
    contents_cost = 0
    if insurance_type == "comprehensive" and contents_value > 0:
        contents_rate = 0.25  # 0.25% سنوياً
        contents_cost = contents_value * (contents_rate / 100)
    
    total_annual = annual_cost + contents_cost
    total_cost = total_annual * years
    
    return {
        "property_value": property_value,
        "insurance_type": insurance_type,
        "type_name": insurance_info["name"],
        "type_name_en": insurance_info["name_en"],
        "description": insurance_info["description"],
        "features": insurance_info["features"],
        "building_age": building_age,
        "base_rate": round(rate, 4),
        "final_rate": round(final_rate, 4),
        "discounts": discounts,
        "total_discount": round(total_discount * 100, 1),
        "annual_cost": round(annual_cost, 2),
        "contents_value": contents_value,
        "contents_cost": round(contents_cost, 2),
        "total_annual": round(total_annual, 2),
        "years": years,
        "total_cost": round(total_cost, 2),
        "monthly_cost": round(total_annual / 12, 2),
    }


def compare_insurance_options(
    property_value: float,
    contents_value: float = 0,
    building_age: int = 0,
    years: int = 1,
) -> dict:
    """مقارنة خيارات التأمين المتاحة.
    
    Args:
        property_value: قيمة العقار
        contents_value: قيمة المحتويات
        building_age: عمر البناء
        years: مدة التأمين
    
    Returns:
        مقارنة شاملة بين أنواع التأمين
    """
    if property_value <= 0:
        return {"error": "قيمة العقار يجب أن تكون أكبر من صفر"}
    
    options = []
    for insurance_type in INSURANCE_TYPES.keys():
        result = calculate_insurance(
            property_value=property_value,
            insurance_type=insurance_type,
            contents_value=contents_value,
            building_age=building_age,
            years=years,
        )
        if "error" not in result:
            options.append(result)
    
    # ترتيب حسب التكلفة (الأقل أولاً)
    options.sort(key=lambda x: x.get("total_annual", 0))
    
    # أفضل خيار (الأقل تكلفة)
    best = options[0] if options else None
    
    return {
        "property_value": property_value,
        "contents_value": contents_value,
        "building_age": building_age,
        "years": years,
        "options": options,
        "best_option": best,
        "recommendation": _build_recommendation(options, best, contents_value),
    }


def _build_recommendation(options: list, best: dict | None, contents_value: float) -> dict:
    """بناء توصية ذكية."""
    if not best:
        return {"summary": "لا توجد خيارات تأمين متاحة"}
    
    summary_parts = [
        f"أفضل خيار: {best['type_name']} بتكلفة {best['total_annual']:,.0f} د.ك/سنة"
    ]
    
    if contents_value > 0:
        summary_parts.append(f"يتضمن تأمين المحتويات ({contents_value:,.0f} د.ك)")
    
    if best.get("total_discount", 0) > 0:
        summary_parts.append(f"خصم {best['total_discount']:.0f}%")
    
    # مقارنة بين الأعلى والأدنى
    if len(options) >= 2:
        diff = options[-1]["total_annual"] - options[0]["total_annual"]
        if diff > 0:
            summary_parts.append(f"فرق {diff:,.0f} د.ك/سنة بين الأعلى والأدنى")
    
    return {
        "summary": " — ".join(summary_parts),
        "best_code": best.get("insurance_type"),
        "best_annual": best.get("total_annual"),
    }


def format_insurance_result(result: dict) -> str:
    """تنسيق النتيجة للعرض."""
    if "error" in result:
        return result["error"]
    
    lines = [
        f"🛡️ التأمين العقاري — {result.get('type_name', '')}",
        f"💰 قيمة العقار: {result.get('property_value', 0):,.0f} د.ك",
        f"📅 المدة: {result.get('years', 1)} سنة",
        f"📊 النسبة: {result.get('final_rate', 0):.2f}%",
        "",
        f"💵 التكلفة السنوية: {result.get('total_annual', 0):,.0f} د.ك",
        f"📅 التكلفة الشهرية: {result.get('monthly_cost', 0):,.0f} د.ك",
        f"💳 الإجمالي: {result.get('total_cost', 0):,.0f} د.ك",
    ]
    
    if result.get("discounts"):
        lines.append("\n📉 الخصومات:")
        for d in result["discounts"]:
            lines.append(f"  • {d['name']}: {d['percent']*100:.0f}%")
    
    return "\n".join(lines)
