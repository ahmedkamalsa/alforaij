"""لوحة تحكم الأدمن — تحليلات المستخدمين والأداء.

هذه الوحدة توفر:
1. إحصائيات المستخدمين النشطين (DAU/MAU)
2. خريطة حرارية للنقرات (Click Heatmap)
3. تحليل تحويل Freemium → Paid
4. تتبع مصادر TraffIC
5. أداء البحث والتقديم
6. تقارير الأداء اليومية/الأسبوعية

الاستخدام:
    from backend.services.admin_analytics import get_admin_dashboard
    dashboard = get_admin_dashboard()
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


def _headers(content_type: str = "application/json") -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": content_type,
    }


def _fetch_rows(endpoint: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []
    request = urllib.request.Request(endpoint, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        logger.warning(f"Admin fetch failed: {e}")
        return []


def _is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


# ─── 1. إحصائيات المستخدمين ───

def get_user_stats() -> dict[str, Any]:
    """إحصائيات المستخدمين: إجمالي، نشط اليوم، نشط هذا الأسبوع."""
    if not _is_configured():
        return {"total": 0, "active_today": 0, "active_week": 0, "new_today": 0}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    # إجمالي المستخدمين
    total_rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/users?select=id&limit=1&head=true")

    # المستخدمون النشطون اليوم (سجلوا OTP اليوم)
    active_today = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/users?select=id"
        f"&otp_requested_at=gte.{today}T00:00:00"
        f"&limit=1000"
    )

    # المستخدمون النشطون هذا الأسبوع
    active_week = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/users?select=id"
        f"&otp_requested_at=gte.{week_ago}T00:00:00"
        f"&limit=5000"
    )

    # مستخدمون جدد اليوم
    new_today = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/users?select=id"
        f"&created_at=gte.{today}T00:00:00"
        f"&limit=1000"
    )

    return {
        "total": len(total_rows) if total_rows else 0,
        "active_today": len(active_today),
        "active_week": len(active_week),
        "new_today": len(new_today),
        "responseMethod": "إحصائيات من جدول users في Supabase",
    }


# ─── 2. خريطة النقرات (Click Heatmap) ───

def get_click_heatmap() -> dict[str, Any]:
    """خريطة حرارية للنقرات: أي الأقسام获得更多 نقرات."""
    if not _is_configured():
        return {"sections": [], "total_clicks": 0}

    rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/outreach_clicks?select=action,channel,created_at"
        f"&order=created_at.desc&limit=2000"
    )

    if not rows:
        return {"sections": [], "total_clicks": 0}

    # تجميع حسب الإجراء
    by_action = defaultdict(int)
    by_channel = defaultdict(int)
    by_day = defaultdict(int)

    for row in rows:
        action = str(row.get("action") or "unknown")
        channel = str(row.get("channel") or "unknown")
        created = str(row.get("created_at") or "")

        by_action[action] += 1
        by_channel[channel] += 1
        if created:
            day = created[:10]
            by_day[day] += 1

    sections = [
        {"action": action, "count": count}
        for action, count in sorted(by_action.items(), key=lambda x: -x[1])
    ]

    channels = [
        {"channel": channel, "count": count}
        for channel, count in sorted(by_channel.items(), key=lambda x: -x[1])
    ]

    trend = [
        {"date": date, "count": count}
        for date, count in sorted(by_day.items(), key=lambda x: x[0])[-30:]
    ]

    return {
        "sections": sections,
        "channels": channels,
        "trend": trend,
        "total_clicks": len(rows),
    }


# ─── 3. تحليل التحويل ───

def get_conversion_funnel() -> dict[str, Any]:
    """قمع التحويل: زائر → مستخدم مجاني → مستخدم تجريبي → مستخدم محترف."""
    if not _is_configured():
        return {"funnel": [], "conversion_rate": 0}

    # المستخدمون المجانيون
    free_rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/user_tiers?select=user_id&tier=eq.free&limit=5000"
    )

    # المستخدمون التجريبيون
    trial_rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/user_tiers?select=user_id&tier=eq.trial&limit=1000"
    )

    # المستخدمون المحترفون
    pro_rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/user_tiers?select=user_id&tier=eq.pro&limit=1000"
    )

    free_count = len(free_rows)
    trial_count = len(trial_rows)
    pro_count = len(pro_rows)
    total = free_count + trial_count + pro_count

    funnel = [
        {"stage": "مجاني", "count": free_count, "pct": round(free_count / max(total, 1) * 100)},
        {"stage": "تجريبي", "count": trial_count, "pct": round(trial_count / max(total, 1) * 100)},
        {"stage": "محترف", "count": pro_count, "pct": round(pro_count / max(total, 1) * 100)},
    ]

    conversion_rate = round(pro_count / max(total, 1) * 100, 1)

    return {
        "funnel": funnel,
        "total_users": total,
        "conversion_rate": conversion_rate,
        "note": f"نسبة التحويل إلى المحترف: {conversion_rate}% — هدفنا 5% خلال 3 أشهر",
    }


# ─── 4. أداء البحث ───

def get_search_analytics() -> dict[str, Any]:
    """تحليلات البحث: أكثر الطلبات شيوعاً، مناطق الإقبال، أوقات الذروة."""
    if not _is_configured():
        return {"top_areas": [], "top_types": [], "peak_hours": []}

    # آخر 1000 طلب تحليل
    rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/analysis_log?select=request_text,created_at"
        f"&order=created_at.desc&limit=1000"
    )

    if not rows:
        return {"top_areas": [], "top_types": [], "peak_hours": []}

    area_counts = defaultdict(int)
    type_counts = defaultdict(int)
    hour_counts = defaultdict(int)

    for row in rows:
        text = str(row.get("request_text") or "").lower()
        created = str(row.get("created_at") or "")

        # استخراج المنطقة
        from backend.services.request_parser import KNOWN_AREAS, PROPERTY_TYPES
        for area in KNOWN_AREAS:
            if area in text:
                area_counts[area] += 1
                break

        # استخراج النوع
        for ptype in PROPERTY_TYPES:
            if ptype in text:
                type_counts[ptype] += 1
                break

        # استخراج الساعة
        if created:
            try:
                hour = int(created[11:13])
                hour_counts[hour] += 1
            except (ValueError, IndexError):
                pass

    return {
        "top_areas": sorted(
            [{"area": a, "count": c} for a, c in area_counts.items()],
            key=lambda x: -x["count"]
        )[:10],
        "top_types": sorted(
            [{"type": t, "count": c} for t, c in type_counts.items()],
            key=lambda x: -x["count"]
        )[:5],
        "peak_hours": sorted(
            [{"hour": h, "count": c} for h, c in hour_counts.items()],
            key=lambda x: -x["count"]
        )[:5],
        "total_searches": len(rows),
    }


# ─── 5. أداء الواتساب ───

def get_whatsapp_analytics() -> dict[str, Any]:
    """تحليلات إرسال واتساب: عدد الإرسال، النجاح، الأفضل أداءً."""
    if not _is_configured():
        return {"total_sent": 0, "success_rate": 0}

    rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/outreach_clicks?select=action,channel,status"
        f"&channel=eq.whatsapp&limit=2000"
    )

    if not rows:
        return {"total_sent": 0, "success_rate": 0}

    total = len(rows)
    sent = sum(1 for r in rows if str(r.get("status")) == "sent")
    failed = sum(1 for r in rows if str(r.get("status")) == "failed")

    return {
        "total_sent": total,
        "successful": sent,
        "failed": failed,
        "success_rate": round(sent / max(total, 1) * 100, 1),
    }


# ─── 6. لوحة التحكم الرئيسية ───

def get_admin_dashboard() -> dict[str, Any]:
    """لوحة تحكم الأدمن الشاملة: كل الإحصائيات في طلب واحد."""
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "users": get_user_stats(),
        "clicks": get_click_heatmap(),
        "conversion": get_conversion_funnel(),
        "searches": get_search_analytics(),
        "whatsapp": get_whatsapp_analytics(),
        "note": "لوحة تحكم الأدمن — إحصائيات حية من Supabase",
    }
