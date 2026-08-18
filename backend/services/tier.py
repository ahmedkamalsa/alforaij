"""نظام الخطط (Tiers) — يحدد المميزات والحدود لكل خطة.

الخطوط:
- free: الأساسي (مجاني) — 20بحث يومياً، 5 مقارنات، بدون PDF
- trial: تجريبي (7 أيام) — كل مميزات المحترف مجاناً
- pro: المحترف — غير محدود + PDF + تنبيهات + دعم أول
- enterprise: المؤسسات — Pro + API + حسابات متعددة + SLA

_EXTRA OPTIONS:
- pay_per_report: 5 د.ك لتقرير PDF واحد (بدون اشتراك)
- referral: إحالة 3 أصدقاء = شهر محترف مجاني

الاستخدام:
    from backend.services.tier import TIER_CONFIG, check_feature, check_usage

    if not check_feature(user_tier, "pdf_reports"):
        return {"error": "ميزة PDF متاحة فقط في الخطة المحترفة"}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TierFeature:
    """ميزة مع حد أو حالة تفعيل."""
    enabled: bool = True
    limit: int | None = None  # None = غير محدود
    description: str = ""


@dataclass(frozen=True)
class TierConfig:
    """تعريف خطة كاملة."""
    name: str
    name_en: str
    price_kwd_monthly: int | None = None  # None = مخصص (مؤسسي)
    price_kwd_yearly: int | None = None
    features: dict[str, TierFeature] = field(default_factory=dict)


# ─── تعريف الخطط ───

TIER_CONFIG: dict[str, TierConfig] = {
    "free": TierConfig(
        name="الأساسي",
        name_en="Free",
        price_kwd_monthly=0,
        price_kwd_yearly=0,
        features={
            "search": TierFeature(enabled=True, limit=20, description="بحث يومياً"),
            "comparisons": TierFeature(enabled=True, limit=5, description="مقارنات لكل بحث"),
            "dashboard_view": TierFeature(enabled=True, description="لوحة السوق (عرض فقط)"),
            "basic_analysis": TierFeature(enabled=True, description="تحليل مقارن أساسي"),
            "pdf_reports": TierFeature(enabled=False, description="تقارير PDF احترافية"),
            "opportunity_alerts": TierFeature(enabled=False, description="تنبيهات الفرص اليومية"),
            "official_data": TierFeature(enabled=False, description="مقارنات رسمية + صفقات موثقة"),
            "advanced_analytics": TierFeature(enabled=False, description="تحليل السوق المتقدم + المؤشرات"),
            "cloud_storage": TierFeature(enabled=False, description="حفظ التقارير في السحابة"),
            "api_access": TierFeature(enabled=False, description="API للمطورين"),
            "multi_user": TierFeature(enabled=False, description="حسابات متعددة"),
            "priority_support": TierFeature(enabled=False, description="دعم أول"),
            "sla": TierFeature(enabled=False, description="SLA 99.9% uptime"),
        },
    ),
    "trial": TierConfig(
        name="تجريبي",
        name_en="Trial",
        price_kwd_monthly=0,
        price_kwd_yearly=0,
        features={
            "search": TierFeature(enabled=True, limit=None, description="بحث غير محدود (7 أيام)"),
            "comparisons": TierFeature(enabled=True, limit=None, description="مقارنات غير محدودة"),
            "dashboard_view": TierFeature(enabled=True, description="لوحة السوق كاملة"),
            "basic_analysis": TierFeature(enabled=True, description="تحليل مقارن أساسي"),
            "pdf_reports": TierFeature(enabled=True, description="تقارير PDF احترافية (7 أيام)"),
            "opportunity_alerts": TierFeature(enabled=True, description="تنبيهات الفرص اليومية (7 أيام)"),
            "official_data": TierFeature(enabled=True, description="مقارنات رسمية + صفقات موثقة"),
            "advanced_analytics": TierFeature(enabled=True, description="تحليل السوق المتقدم + المؤشرات"),
            "cloud_storage": TierFeature(enabled=True, description="حفظ التقارير في السحابة"),
            "api_access": TierFeature(enabled=False, description="API للمطورين"),
            "multi_user": TierFeature(enabled=False, description="حسابات متعددة"),
            "priority_support": TierFeature(enabled=False, description="دعم أول"),
            "sla": TierFeature(enabled=False, description="SLA 99.9% uptime"),
        },
    ),
    "pro": TierConfig(
        name="المحترف",
        name_en="Pro",
        price_kwd_monthly=15,
        price_kwd_yearly=144,
        features={
            "search": TierFeature(enabled=True, limit=None, description="بحث غير محدود"),
            "comparisons": TierFeature(enabled=True, limit=None, description="مقارنات غير محدودة"),
            "dashboard_view": TierFeature(enabled=True, description="لوحة السوق كاملة"),
            "basic_analysis": TierFeature(enabled=True, description="تحليل مقارن أساسي"),
            "pdf_reports": TierFeature(enabled=True, description="تقارير PDF احترافية كاملة"),
            "opportunity_alerts": TierFeature(enabled=True, description="تنبيهات الفرص اليومية (واتساب)"),
            "official_data": TierFeature(enabled=True, description="مقارنات رسمية + صفقات موثقة"),
            "advanced_analytics": TierFeature(enabled=True, description="تحليل السوق المتقدم + المؤشرات"),
            "cloud_storage": TierFeature(enabled=True, description="حفظ التقارير في السحابة"),
            "api_access": TierFeature(enabled=False, description="API للمطورين"),
            "multi_user": TierFeature(enabled=False, description="حسابات متعددة"),
            "priority_support": TierFeature(enabled=True, limit=24, description="دعم أول (24 ساعة)"),
            "sla": TierFeature(enabled=False, description="SLA 99.9% uptime"),
        },
    ),
    "enterprise": TierConfig(
        name="المؤسسات",
        name_en="Enterprise",
        price_kwd_monthly=None,  # مخصص
        price_kwd_yearly=None,
        features={
            "search": TierFeature(enabled=True, limit=None, description="بحث غير محدود"),
            "comparisons": TierFeature(enabled=True, limit=None, description="مقارنات غير محدودة"),
            "dashboard_view": TierFeature(enabled=True, description="لوحة السوق كاملة"),
            "basic_analysis": TierFeature(enabled=True, description="تحليل مقارن أساسي"),
            "pdf_reports": TierFeature(enabled=True, description="تقارير PDF احترافية كاملة"),
            "opportunity_alerts": TierFeature(enabled=True, description="تنبيهات الفرص اليومية (واتساب)"),
            "official_data": TierFeature(enabled=True, description="مقارنات رسمية + صفقات موثقة"),
            "advanced_analytics": TierFeature(enabled=True, description="تحليل السوق المتقدم + المؤشرات"),
            "cloud_storage": TierFeature(enabled=True, description="حفظ التقارير في السحابة"),
            "api_access": TierFeature(enabled=True, description="API للمطورين"),
            "multi_user": TierFeature(enabled=True, description="حسابات متعددة"),
            "priority_support": TierFeature(enabled=True, limit=2, description="دعم أول (ساعتين)"),
            "sla": TierFeature(enabled=True, description="SLA 99.9% uptime"),
        },
    ),
}


def get_tier_config(tier: str) -> TierConfig | None:
    """الحصول على إعدادات خطة معينة."""
    return TIER_CONFIG.get(tier)


def check_feature(tier: str, feature: str) -> bool:
    """التحقق مما إذا كانت ميزة معينة متاحة في خطة معينة."""
    config = TIER_CONFIG.get(tier)
    if not config:
        return False
    feat = config.features.get(feature)
    if not feat:
        return False
    return feat.enabled


def get_feature_limit(tier: str, feature: str) -> int | None:
    """الحصول على حد ميزة معينة (None = غير محدود)."""
    config = TIER_CONFIG.get(tier)
    if not config:
        return 0
    feat = config.features.get(feature)
    if not feat or not feat.enabled:
        return 0
    return feat.limit


def check_usage(tier: str, feature: str, current_usage: int) -> dict[str, Any]:
    """التحقق من استخدام المستخدم مقابل الحد المسموح.

    Returns:
        dict مع:
        - allowed: bool — هل يمكنه التنفيذ
        - remaining: int | None — المتبقي (None = غير محدود)
        - limit: int | None — الحد الأقصى
        - current: الاستخدام الحالي
        - message: رسالة للمستخدم
        - warning: تحذير عند الاقتراب من الحد
        - near_limit: bool — هل هو قريب من الحد (80%+)
    """
    limit = get_feature_limit(tier, feature)

    if limit is None:
        return {
            "allowed": True,
            "remaining": None,
            "limit": None,
            "current": current_usage,
            "message": "استخدام غير محدود",
            "warning": None,
            "near_limit": False,
        }

    remaining = max(0, limit - current_usage)
    allowed = remaining > 0
    pct = (current_usage / limit * 100) if limit > 0 else 0
    near_limit = pct >= 80

    if allowed:
        if near_limit:
            message = f"متبقي {remaining} فقط من {limit} — رقّ خطتك للحصول على المزيد"
            warning = f"تحذير: استخدمت {pct:.0f}% من حظتك اليومية"
        else:
            message = f"متبقي {remaining} من {limit}"
            warning = None
    else:
        message = f"وصلت الحد الأقصى ({limit}). رقّ خطتك للحصول على المزيد."
        warning = None

    return {
        "allowed": allowed,
        "remaining": remaining,
        "limit": limit,
        "current": current_usage,
        "message": message,
        "warning": warning,
        "near_limit": near_limit,
    }


def get_upgrade_prompt(tier: str, feature: str) -> dict[str, str] | None:
    """الحصول على رسالة ترقية مناسبة لميزة غير متاحة."""
    config = TIER_CONFIG.get(tier)
    if not config:
        return None

    feat = config.features.get(feature)
    if not feat or feat.enabled:
        return None  # الميزة متاحة أصلاً

    # تحديد الخطة التالية
    if tier == "free":
        next_tier = "pro"
        next_name = "المحترف"
        next_price = "15 د.ك/شهر"
    elif tier == "pro":
        next_tier = "enterprise"
        next_name = "المؤسسات"
        next_price = "مخصص"
    else:
        return None  # المؤسسات هي أعلى خطة

    return {
        "current_tier": tier,
        "next_tier": next_tier,
        "next_tier_name": next_name,
        "next_price": next_price,
        "feature": feature,
        "feature_description": feat.description,
        "message": f"ميزة '{feat.description}' متاحة في الخطة {next_name} ({next_price})",
    }


def list_tiers() -> list[dict[str, Any]]:
    """قائمة بكل الخطط ومميزاتها (للعرض في صفحة الأسعار)."""
    result = []
    for tier_id, config in TIER_CONFIG.items():
        features = []
        for feat_id, feat in config.features.items():
            features.append({
                "id": feat_id,
                "enabled": feat.enabled,
                "limit": feat.limit,
                "description": feat.description,
            })
        result.append({
            "id": tier_id,
            "name": config.name,
            "name_en": config.name_en,
            "price_monthly": config.price_kwd_monthly,
            "price_yearly": config.price_kwd_yearly,
            "features": features,
        })
    return result


# ─── الدفع لكل تقرير (Pay-Per-Report) ───

PAY_PER_REPORT_PRICE = 5  # د.ك لتقرير PDF واحد

def can_use_pay_per_report(user_tier: str, reports_purchased: int) -> dict[str, Any]:
    """التحقق مما إذا كان المستخدم يمكنه شراء تقرير منفرد.

    أي مستخدم (حتى المجاني) يمكنه شراء تقارير PDF بسعر 5 د.ك لكل تقرير.
    هذا يخدم المستخدمين الذين لا يريدون اشتراكاً شهرياً.
    """
    return {
        "available": True,
        "price_kwd": PAY_PER_REPORT_PRICE,
        "reports_purchased": reports_purchased,
        "message": f"تقرير PDF بسعر {PAY_PER_REPORT_PRICE} د.ك فقط — بدون اشتراك شهري",
    }


# ─── برنامج الإحالة (Referral Program) ───

REFERRAL_REQUIRED = 3  # عدد الأصدقاء المطلوب للحصول على شهر مجاني
REFERRAL_REWARD_MONTHS = 1  # عدد الأشهر المجانية

def check_referral_status(referrals_count: int) -> dict[str, Any]:
    """التحقق من حالة برنامج الإحالة.

    كل إحالة ناجحة (صديق يسجل وينشئ حساباً) تقرب المستخدم من الحصول
    على شهر محترف مجاني. هذا يبني الثقة ويجعل النمو عضوياً.
    """
    remaining = max(0, REFERRAL_REQUIRED - referrals_count)
    eligible = remaining == 0

    if eligible:
        message = f"أحسنت! أرسلت {referrals_count} أصدقاء — تحصل على شهر محترف مجاني!"
    else:
        message = f"أرسل {remaining} أصدقاء آخرين واحصل على شهر محترف مجاني ({referrals_count}/{REFERRAL_REQUIRED})"

    return {
        "eligible": eligible,
        "referrals_count": referrals_count,
        "referrals_remaining": remaining,
        "required": REFERRAL_REQUIRED,
        "reward_months": REFERRAL_REWARD_MONTHS,
        "message": message,
    }


def get_referral_link(user_id: str) -> str:
    """إنشاء رابط إحالة فريد للمستخدم."""
    return f"https://alforaij.com/ref/{user_id}"


# ───arnings (Monthly Earnings Report) ───

def calculate_monthly_value(tier: str, searches_used: int, pdfs_used: int) -> dict[str, Any]:
    """حساب القيمة التي حصل عليها المستخدم هذا الشهر.

    يُظهر للمستخدم كم وفّر باستخدام المنصة مقارنة بالطرق التقليدية.
    هذا يبني الولاء ويجعل المستخدم يرى القيمة بوضوح.
    """
    # القيمة المقدرة للبحث الواحد (مقارنة بتوظيف باحث)
    SEARCH_VALUE_KWD = 2  # د.ك تقديرية لكل بحث
    # القيمة المقدرة للتقرير الواحد (مقارنة بكتابة يدوية)
    PDF_VALUE_KWD = 15  # د.ك تقديرية لكل تقرير

    search_value = searches_used * SEARCH_VALUE_KWD
    pdf_value = pdfs_used * PDF_VALUE_KWD
    total_value = search_value + pdf_value

    config = TIER_CONFIG.get(tier)
    price_paid = config.price_kwd_monthly if config else 0

    savings = total_value - (price_paid or 0)
    roi_pct = ((total_value / price_paid * 100) - 100) if price_paid and price_paid > 0 else 0

    return {
        "tier": tier,
        "searches_used": searches_used,
        "search_value_kwd": search_value,
        "pdfs_used": pdfs_used,
        "pdf_value_kwd": pdf_value,
        "total_value_kwd": total_value,
        "price_paid_kwd": price_paid,
        "savings_kwd": savings,
        "roi_percentage": round(roi_pct, 0),
        "message": (
            f"هذا الشهر وفّرت {savings} د.ك باستخدام المنصة"
            if savings > 0
            else f"حصلت على قيمة {total_value} د.ك من البحث والتقارير"
        ),
    }
