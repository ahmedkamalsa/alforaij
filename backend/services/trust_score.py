"""Trust Score — مؤشر ثقة الإعلان العقاري

يحسب درجة ثقة (0-100) لكل إعلان بناءً على:
1. عمر الإعلان (جديد = ضعيف، قديم = أقوى)
2. استقرار السعر (تكرار تغيير السعر = مشبوه)
3. تعدد المصادر (نفس العقار في عدة مواقع = موثوق)
4. توفر الصور (صور حقيقية = أقوى)
5. مصدر الإعلان (مواقع معروفة = أقوى)
6. مطابقة السعر للمتوسط (سعر منخفض جداً = مشبوه)

المصادر:
- Trustpilot (PropertyFinder 1.6/5)
- Reddit r/dubairealestate
- Awwad Real Estate Kuwait fraud guide
- FBI IC3 2025 ($275M real estate fraud)
"""

from __future__ import annotations

import time
from typing import Optional

# ── أوزان العوامل (المجموع = 100) ──
WEIGHT_AGE = 20          # عمر الإعلان
WEIGHT_PRICE_STABILITY = 25  # استقرار السعر
WEIGHT_MULTI_SOURCE = 15 # تعدد المصادر
WEIGHT_PHOTOS = 15       # توفر الصور
WEIGHT_SOURCE = 10       # مصدر الإعلان
WEIGHT_PRICE_RATIO = 15  # مطابقة السعر للمتوسط

# ── مصادر موثوقة (Boost) ──
TRUSTED_SOURCES = {
    "alforaij": 10,      # بياناتنا المحلية
    "findq8": 5,
    "4sale": 5,
    "mourjan": 5,
    "opensooq": 4,
    "kfh_reports": 8,    # تقارير رسمية
}

# ── الفئات ──
SCORE_TRUSTED = 75       # 🟢 موثق
SCORE_MODERATE = 50      # 🟡 متوسط
SCORE_LOW = 25           # 🔴 ضعيف


def calculate_trust_score(
    listing: dict,
    area_median_price: Optional[float] = None,
    price_history: Optional[list] = None,
    duplicate_count: int = 0,
) -> dict:
    """حساب درجة ثقة الإعلان.

    Args:
        listing: بيانات الإعلان (price, source, photos, created_at, area, space)
        area_median_price: متوسط سعر المتر في المنطقة
        price_history: سجل تغيرات السعر [{price, date}, ...]
        duplicate_count: عدد الإعلانات المشابهة في مواقع أخرى

    Returns:
        {score: int, grade: str, label: str, color: str, factors: [...], alerts: [...]}
    """
    now = time.time()
    factors = []
    alerts = []

    # ── 1. عمر الإعلان (20 نقطة) ──
    created = listing.get("created_at") or listing.get("date") or ""
    age_days = _age_days(created, now)
    age_score = _score_age(age_days)
    factors.append({
        "name": "عمر الإعلان",
        "score": age_score,
        "max": WEIGHT_AGE,
        "detail": f"{age_days} يوم" if age_days else "غير محدد",
    })
    if age_days == 0:
        alerts.append("⚠️ إعلان جديد جداً — تحقق من البيانات")

    # ── 2. استقرار السعر (25 نقطة) ──
    price_changes = len(price_history or []) - 1
    stability_score = _score_price_stability(price_changes)
    factors.append({
        "name": "استقرار السعر",
        "score": stability_score,
        "max": WEIGHT_PRICE_STABILITY,
        "detail": f"{price_changes} تغيير" if price_changes else "ثابت",
    })
    if price_changes >= 3:
        alerts.append(f"⚠️ تغير السعر {price_changes} مرة — قد يكون مضللاً")

    # ── 3. تعدد المصادر (15 نقطة) ──
    multi_score = _score_multi_source(duplicate_count)
    factors.append({
        "name": "تعدد المصادر",
        "score": multi_score,
        "max": WEIGHT_MULTI_SOURCE,
        "detail": f"{duplicate_count + 1} مصدر" if duplicate_count else "مصدر واحد",
    })
    if duplicate_count == 0:
        alerts.append("ℹ️ إعلان من مصدر واحد فقط")

    # ── 4. توفر الصور (15 نقطة) ──
    photos = listing.get("photos") or listing.get("images") or []
    has_photos = len(photos) > 0
    photos_score = WEIGHT_PHOTOS if has_photos else 3
    factors.append({
        "name": "الصور",
        "score": photos_score,
        "max": WEIGHT_PHOTOS,
        "detail": f"{len(photos)} صور" if photos else "بدون صور",
    })
    if not has_photos:
        alerts.append("⚠️ لا توجد صور — تحقق من وجود العقار فعلياً")

    # ── 5. مصدر الإعلان (10 نقاط) ──
    source = (listing.get("source") or "").lower()
    source_boost = TRUSTED_SOURCES.get(source, 2)
    source_score = min(source_boost, WEIGHT_SOURCE)
    factors.append({
        "name": "المصدر",
        "score": source_score,
        "max": WEIGHT_SOURCE,
        "detail": source or "غير محدد",
    })

    # ── 6. مطابقة السعر للمتوسط (15 نقطة) ──
    price = _to_float(listing.get("price") or listing.get("median_price"))
    space = _to_float(listing.get("space"))
    price_ratio_score = WEIGHT_PRICE_RATIO  # الافتراضي: مطابق
    if price and area_median_price and area_median_price > 0:
        price_ratio = price / area_median_price
        price_ratio_score, ratio_alert = _score_price_ratio(price_ratio)
        if ratio_alert:
            alerts.append(ratio_alert)
    factors.append({
        "name": "مقارنة السعر",
        "score": price_ratio_score,
        "max": WEIGHT_PRICE_RATIO,
        "detail": f"نسبة {price_ratio:.1%}" if price and area_median_price else "غير متوفر",
    })

    # ── المجموع ──
    total = sum(f["score"] for f in factors)
    total = max(0, min(100, total))

    grade, label, color = _grade(total)

    return {
        "score": total,
        "grade": grade,
        "label": label,
        "color": color,
        "factors": factors,
        "alerts": alerts,
    }


def _age_days(created_str: str, now: float) -> int:
    """حساب عمر الإعلان بالأيام."""
    if not created_str:
        return 0
    try:
        from datetime import datetime
        # محاولة تنسيقات متعددة
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(created_str[:19], fmt)
                return max(0, int((now - dt.timestamp()) / 86400))
            except ValueError:
                continue
        # محاولة epoch
        ts = float(created_str)
        return max(0, int((now - ts) / 86400))
    except Exception:
        return 0


def _score_age(days: int) -> int:
    """إعادة تقييم عمر الإعلان (0-20).
    الإعلانات القديمة (30+ يوم) أقوى — ثبتت صحتها.
    الإعلانات الجديدة (0-3 يوم) أضعف — قد تكون مزيفة.
    """
    if days >= 60:
        return WEIGHT_AGE  # عادي — ثابت
    elif days >= 30:
        return 18
    elif days >= 14:
        return 15
    elif days >= 7:
        return 12
    elif days >= 3:
        return 8
    else:
        return 3  # جديد جداً


def _score_price_stability(changes: int) -> int:
    """إعادة تقييم استقرار السعر (0-25).
    عدم تغيير السعر = موثوق.
    تغيير كثير = مشبوه (Bait pricing).
    """
    if changes == 0:
        return WEIGHT_PRICE_STABILITY  # ثابت — ممتاز
    elif changes == 1:
        return 22
    elif changes == 2:
        return 18
    elif changes <= 4:
        return 10
    else:
        return 3  # تغيير كثير — مشبوه


def _score_multi_source(duplicates: int) -> int:
    """إعادة تقييم تعدد المصادر (0-15).
    ظهور العقار في عدة مواقع = موثوق.
    """
    if duplicates >= 3:
        return WEIGHT_MULTI_SOURCE
    elif duplicates == 2:
        return 12
    elif duplicates == 1:
        return 8
    else:
        return 3  # مصدر واحد


def _score_price_ratio(ratio: float) -> tuple[int, Optional[str]]:
    """إعادة تقييم نسبة السعر للمتوسط (0-15).
    ratio < 0.7 = سعر منخفض جداً (مشبوه)
    ratio > 1.5 = سعر مرتفع جداً
    """
    if 0.8 <= ratio <= 1.2:
        return WEIGHT_PRICE_RATIO, None  # مطابق — ممتاز
    elif 0.7 <= ratio < 0.8 or 1.2 < ratio <= 1.3:
        return 12, None  # قريب
    elif 0.5 <= ratio < 0.7:
        return 5, f"⚠️ سعر منخفض {ratio:.0%} عن المتوسط — قد يكون مضللاً"
    elif ratio < 0.5:
        return 2, f"🔴 سعر منخفض جداً ({ratio:.0%} من المتوسط) — مشبوه جداً"
    elif 1.3 < ratio <= 1.5:
        return 8, f"ℹ️ سعر مرتفع {ratio:.0%} عن المتوسط"
    else:
        return 3, f"⚠️ سعر مرتفع جداً ({ratio:.0%} من المتوسط)"


def _grade(score: int) -> tuple[str, str, str]:
    """تحويل الرقم إلى فئة."""
    if score >= SCORE_TRUSTED:
        return "trusted", "موثق", "#22c55e"  # أخضر
    elif score >= SCORE_MODERATE:
        return "moderate", "متوسط", "#f59e0b"  # أصفر
    else:
        return "low", "مشبوه", "#ef4444"  # أحمر


def _to_float(val) -> Optional[float]:
    """تحويل آمن لرقم."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
