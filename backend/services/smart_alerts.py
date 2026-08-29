"""Smart Alerts — تنبيهات ذكية للسعر والفرص الجديدة.

يُكمل نظام opportunity_alerts الموجود by adding:
1. Real-time price drop detection (مقارنة السعر الحالي بالمتوسط)
2. New listing alerts (إعلانات جديدة تطابق البحث المحفوظ)
3. User subscription management (اشتراك إلغاء اشتراك)
4. Alert history and read status

المصادر:
- Bayut: "Push notifications for price drops on saved properties" — Oliva
- Zillow: "Price drop alerts" — Real Estate Skills
- Research: USER_PROBLEMS_RESEARCH.md — problem #8
"""
from __future__ import annotations

import time
from typing import Optional

# ── أنواع التنبيهات ──
ALERT_TYPES = {
    "price_drop": "انخفاض السعر",
    "new_listing": "فرصة جديدة",
    "price_near_median": "سعر أقل من المتوسط",
}

# ── مهلة الحد الأدنى بين التنبيهات (ساعات) ──
MIN_ALERT_INTERVAL_HOURS = 6


def detect_price_drops(
    current_listings: list[dict],
    area_medians: dict[str, float],
    threshold_pct: float = 10.0,
) -> list[dict]:
    """كشف الانخفاضات السعرية.
    
    Args:
        current_listings: الإعلانات الحالية
        area_medians: متوسط السعر لكل منطقة {area: median}
        threshold_pct: الحد الأدنى للانخفاض (10% افتراضياً)
    
    Returns:
        قائمة بالانخفاضات المكتشفة
    """
    alerts = []
    for listing in current_listings:
        price = _to_float(listing.get("price"))
        area = listing.get("area") or ""
        if not price or not area:
            continue
        median = area_medians.get(area)
        if not median or median <= 0:
            continue
        pct_below = ((median - price) / median) * 100
        if pct_below >= threshold_pct:
            alerts.append({
                "type": "price_near_median",
                "code": listing.get("code") or "",
                "area": area,
                "price": price,
                "median": median,
                "pct_below": round(pct_below, 1),
                "message": f"سعر {listing.get('code', '')} في {area} أقل بـ{pct_below:.0f}% من المتوسط ({price:,.0f} مقابل {median:,.0f} د.ك)",
                "severity": "high" if pct_below >= 20 else "medium",
            })
    return alerts


def detect_new_listings(
    current_codes: set[str],
    previous_codes: set[str],
    listings_map: dict[str, dict],
) -> list[dict]:
    """كشف الإعلانات الجديدة.
    
    Args:
        current_codes: أكواد الإعلانات الحالية
        previous_codes: أكواد الإعلانات السابقة
        listings_map: بيانات الإعلانات {code: listing_data}
    
    Returns:
        قائمة بالإعلانات الجديدة
    """
    new_codes = current_codes - previous_codes
    alerts = []
    for code in new_codes:
        listing = listings_map.get(code, {})
        alerts.append({
            "type": "new_listing",
            "code": code,
            "area": listing.get("area") or "",
            "price": _to_float(listing.get("price")),
            "priceText": listing.get("priceText") or "",
            "propertyType": listing.get("propertyType") or "",
            "message": f"إعلان جديد: {code} في {listing.get('area', 'المنطقة')} — {listing.get('priceText', '')}",
            "severity": "info",
        })
    return alerts


def should_alert(
    last_alert_time: Optional[float],
    min_interval_hours: float = MIN_ALERT_INTERVAL_HOURS,
) -> bool:
    """هل يجب إرسال تنبيه الآن؟ (منع التكرار)."""
    if not last_alert_time:
        return True
    elapsed_hours = (time.time() - last_alert_time) / 3600
    return elapsed_hours >= min_interval_hours


def build_user_alerts(
    user_secret: str,
    saved_searches: list[dict],
    current_listings: list[dict],
    area_medians: dict[str, float],
    previous_codes: Optional[set[str]] = None,
) -> list[dict]:
    """بناء كل التنبيهات للمستخدم.
    
    Args:
        user_secret: سر المستخدم
        saved_searches: الأبحاث المحفوظة للمستخدم
        current_listings: الإعلانات الحالية المطابقة
        area_medians: متوسطات الأسعار
        previous_codes: أكواد الإعلانات السابقة (للكشف عن الجديدة)
    
    Returns:
        قائمة بالتنبيهات مرتبة حسب الأولوية
    """
    alerts = []
    
    # 1. تنبيهات انخفاض السعر
    price_drops = detect_price_drops(current_listings, area_medians)
    alerts.extend(price_drops)
    
    # 2. تنبيهات الإعلانات الجديدة
    if previous_codes is not None:
        current_codes = {l.get("code") for l in current_listings if l.get("code")}
        listings_map = {l.get("code"): l for l in current_listings if l.get("code")}
        new_listings = detect_new_listings(current_codes, previous_codes, listings_map)
        alerts.extend(new_listings)
    
    # ترتيب حسب الأولوية (عالي أولاً)
    severity_order = {"high": 0, "medium": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a.get("severity", "info"), 2))
    
    return alerts


def format_alert_for_push(alert: dict) -> dict:
    """تنسيق التنبيه للإرسال كـ push notification."""
    return {
        "title": _alert_title(alert.get("type")),
        "body": alert.get("message", ""),
        "data": {
            "type": alert.get("type"),
            "code": alert.get("code"),
            "area": alert.get("area"),
            "price": alert.get("price"),
        },
    }


def _alert_title(alert_type: Optional[str]) -> str:
    """عنوان التنبيه حسب النوع."""
    titles = {
        "price_drop": "📉 انخفاض السعر",
        "new_listing": "🏢 فرصة جديدة",
        "price_near_median": "💰 سعر أقل من المتوسط",
    }
    return titles.get(alert_type, "🔔 تنبيه الفريج")


def _to_float(val) -> Optional[float]:
    """تحويل آمن لرقم."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
