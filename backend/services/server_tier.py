"""نظام الخطط_SERVER — تتبع الخطة والحد على الخادم باستخدام Supabase.

يحل محل الذاكرة المؤقتة بقاعدة بيانات حقيقية:
- جدول user_tiers: يخزن خطة كل مستخدم وกด الاستخدام
- JWT middleware: يتحقق من التوكن في كل طلب
- RLS policies: يمنع التعديل من الواجهة الأمامية مباشرة

الاستخدام في API:
    from backend.services.server_tier import authorize_request, record_usage

    result = authorize_request(request, "search")
    if not result["authorized"]:
        return json_response(handler, {"error": result["message"]}, status=403)

    # ... تنفيذ البحث ...

    record_usage(request.user_id, "search")
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from backend.services.tier import TIER_CONFIG, TierConfig, check_feature, get_feature_limit, check_usage

logger = logging.getLogger(__name__)

# ─── JWT Verification ───

_jwt_secret: str | None = None


def _get_jwt_secret() -> str:
    """الحصول على سر JWT من البيئة (Supabase JWT Secret)."""
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
        if not _jwt_secret:
            # محاولة القراءة من ملف Supabase
            try:
                supabase_dir = os.path.join(os.path.dirname(__file__), "..", "..", "supabase")
                config_path = os.path.join(supabase_dir, "config.toml")
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        for line in f:
                            if "jwt_secret" in line and "=" in line:
                                _jwt_secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
            except Exception:
                pass
    return _jwt_secret or ""


def _base64url_decode(data: str) -> bytes:
    """فك تشفير base64url."""
    # إضافة padding
    missing = len(data) % 4
    if missing:
        data += "=" * (4 - missing)
    return __import__("base64").urlsafe_b64decode(data)


def verify_jwt(token: str) -> dict[str, Any] | None:
    """التحقق من JWT token وإعادة المحتوى.

    Returns:
        payload dict إذا كان التوكن صالحاً، None إذا كان غير صالح.
    """
    if not token:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    try:
        header_b64, payload_b64, signature_b64 = parts

        # فك تشفير التوقيع
        signature = _base64url_decode(signature_b64)

        # التحقق من التوقيع باستخدام HMAC-SHA256
        secret = _get_jwt_secret()
        if not secret:
            logger.warning("JWT secret not configured")
            return None

        import hmac
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("utf-8"),
            hashlib.sha256
        ).digest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # فك تشفير المحتوى
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes)

        # التحقق من انتهاء الصلاحية
        exp = payload.get("exp")
        if exp and isinstance(exp, (int, float)):
            if time.time() > exp:
                return None

        return payload

    except Exception as e:
        logger.debug(f"JWT verification failed: {e}")
        return None


def extract_user_from_token(token: str) -> dict[str, Any] | None:
    """استخراج معلومات المستخدم من JWT token."""
    payload = verify_jwt(token)
    if not payload:
        return None

    return {
        "user_id": payload.get("sub", ""),
        "phone": payload.get("phone", ""),
        "email": payload.get("email", ""),
        "tier": payload.get("app_metadata", {}).get("tier", "free"),
        "exp": payload.get("exp"),
    }


# ─── Server-Side Tier Management ───

def _headers(content_type: str = "application/json") -> dict[str, str]:
    """headers للاتصال بـ Supabase مع service role key."""
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": content_type,
        "Prefer": "return=representation",
    }


def _fetch_user_tier(user_id: str) -> dict[str, Any] | None:
    """جلب خطة المستخدم من قاعدة البيانات."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None

    endpoint = f"{SUPABASE_URL}/rest/v1/user_tiers?user_id=eq.{user_id}&select=*"
    request = urllib.request.Request(endpoint, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            rows = json.loads(response.read().decode())
            return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"Failed to fetch user tier: {e}")
        return None


def _upsert_user_tier(user_id: str, tier: str, **extra) -> None:
    """إنشاء أو تحديث خطة المستخدم."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return

    row = {
        "user_id": user_id,
        "tier": tier,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }

    endpoint = f"{SUPABASE_URL}/rest/v1/user_tiers"
    data = json.dumps(row, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, headers={
        **_headers(),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except Exception as e:
        logger.warning(f"Failed to upsert user tier: {e}")


def _fetch_daily_usage(user_id: str, feature: str) -> int:
    """جلب عدد استخدامات اليوم للميزة."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    endpoint = (
        f"{SUPABASE_URL}/rest/v1/user_usage?"
        f"user_id=eq.{user_id}&feature=eq.{feature}&usage_date=eq.{today}&select=count"
    )
    request = urllib.request.Request(endpoint, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data[0].get("count", 0) if data else 0
    except Exception as e:
        logger.warning(f"Failed to fetch daily usage: {e}")
        return 0


def _increment_daily_usage(user_id: str, feature: str) -> None:
    """زيادة عداد الاستخدام اليومي."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "user_id": user_id,
        "feature": feature,
        "usage_date": today,
        "count": 1,
    }

    endpoint = f"{SUPABASE_URL}/rest/v1/user_usage"
    data = json.dumps(row, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, headers={
        **_headers(),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except Exception as e:
        logger.warning(f"Failed to increment usage: {e}")


# ─── Public API ───

def authorize_request(user_id: str, feature: str) -> dict[str, Any]:
    """التحقق من صلاحية المستخدم لميزة معينة.

    Returns:
        dict مع:
        - authorized: bool
        - tier: str
        - message: str
        - remaining: int | None
        - near_limit: bool
        - upgrade: dict | None (رسالة ترقية إن لم تكن الميزة متاحة)
    """
    if not user_id:
        return {
            "authorized": False,
            "tier": "anonymous",
            "message": "سجل الدخول أولاً للحصول على 20 بحث يومياً مجاناً",
            "remaining": None,
            "near_limit": False,
            "upgrade": {
                "message": "سجل برقم هاتفك الكويتي واحصل على خطة مجانية فوراً",
            },
        }

    # جلب خطة المستخدم من القاعدة
    user_tier_data = _fetch_user_tier(user_id)
    tier = "free"
    if user_tier_data:
        tier = user_tier_data.get("tier", "free")
        # التحقق من انتهاء التجربة
        trial_ends = user_tier_data.get("trial_ends_at")
        if tier == "trial" and trial_ends:
            try:
                ends_dt = datetime.fromisoformat(str(trial_ends).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > ends_dt:
                    tier = "free"
                    _upsert_user_tier(user_id, "free")
            except Exception:
                pass

    # التحقق من الميزة
    config = TIER_CONFIG.get(tier)
    if not config:
        return {
            "authorized": False,
            "tier": tier,
            "message": f"خطة غير معروفة: {tier}",
            "remaining": None,
            "near_limit": False,
            "upgrade": None,
        }

    feat = config.features.get(feature)
    if not feat or not feat.enabled:
        upgrade = None
        if tier == "free":
            upgrade = {
                "current_tier": tier,
                "next_tier": "pro",
                "next_tier_name": "المحترف",
                "next_price": "15 د.ك/شهر",
                "feature": feature,
                "feature_description": feat.description if feat else feature,
                "message": f"ميزة '{feat.description if feat else feature}' متاحة في الخطة المحترف (15 د.ك/شهر)" if feat else f"الميزة '{feature}' غير متاحة",
            }
        return {
            "authorized": False,
            "tier": tier,
            "message": feat.description if feat else f"الميزة '{feature}' غير متاحة في خطتك",
            "remaining": None,
            "near_limit": False,
            "upgrade": upgrade,
        }

    # التحقق من الحد اليومي
    limit = get_feature_limit(tier, feature)
    if limit is not None:
        current_usage = _fetch_daily_usage(user_id, feature)
        usage_check = check_usage(tier, feature, current_usage)

        if not usage_check["allowed"]:
            return {
                "authorized": False,
                "tier": tier,
                "message": usage_check["message"],
                "remaining": 0,
                "limit": limit,
                "current": current_usage,
                "near_limit": True,
                "upgrade": {
                    "current_tier": tier,
                    "next_tier": "pro",
                    "next_tier_name": "المحترف",
                    "next_price": "15 د.ك/شهر",
                    "message": "رقّ خطتك للبحث غير المحدود",
                } if tier == "free" else None,
            }

        return {
            "authorized": True,
            "tier": tier,
            "message": usage_check["message"],
            "remaining": usage_check["remaining"],
            "limit": limit,
            "current": current_usage,
            "near_limit": usage_check["near_limit"],
            "upgrade": None,
        }

    # ميزة غير محدودة
    return {
        "authorized": True,
        "tier": tier,
        "message": "استخدام غير محدود",
        "remaining": None,
        "limit": None,
        "current": 0,
        "near_limit": False,
        "upgrade": None,
    }


def record_usage(user_id: str, feature: str) -> None:
    """تسجيل استخدام ميزة."""
    if user_id:
        _increment_daily_usage(user_id, feature)


def get_user_tier(user_id: str) -> str:
    """جلب خطة المستخدم."""
    if not user_id:
        return "anonymous"

    user_tier_data = _fetch_user_tier(user_id)
    if not user_tier_data:
        return "free"

    tier = user_tier_data.get("tier", "free")

    # التحقق من انتهاء التجربة
    if tier == "trial":
        trial_ends = user_tier_data.get("trial_ends_at")
        if trial_ends:
            try:
                ends_dt = datetime.fromisoformat(str(trial_ends).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > ends_dt:
                    return "free"
            except Exception:
                pass

    return tier


def upgrade_user(user_id: str, new_tier: str) -> dict[str, Any]:
    """ترقية خطة المستخدم."""
    if new_tier not in TIER_CONFIG:
        return {"error": f"خطة غير معروفة: {new_tier}"}

    user_tier_data = _fetch_user_tier(user_id)
    old_tier = user_tier_data.get("tier", "free") if user_tier_data else "free"

    extra = {}
    if new_tier == "trial":
        from datetime import timedelta
        ends_at = datetime.now(timezone.utc) + timedelta(days=7)
        extra["trial_ends_at"] = ends_at.isoformat()

    _upsert_user_tier(user_id, new_tier, **extra)

    return {
        "status": "upgraded",
        "old_tier": old_tier,
        "new_tier": new_tier,
        "message": f"تم الترقية من {TIER_CONFIG[old_tier].name} إلى {TIER_CONFIG[new_tier].name}",
    }


def get_tier_limits(user_id: str) -> dict[str, Any]:
    """جلب حدود المستخدم الحالية مع الاستخدام اليومي."""
    tier = get_user_tier(user_id)
    config = TIER_CONFIG.get(tier)
    if not config:
        return {"tier": tier, "features": {}}

    features = {}
    for feat_id, feat in config.features.items():
        current = _fetch_daily_usage(user_id, feat_id) if feat.limit else 0
        features[feat_id] = {
            "enabled": feat.enabled,
            "limit": feat.limit,
            "current": current,
            "remaining": max(0, feat.limit - current) if feat.limit else None,
            "description": feat.description,
        }

    return {
        "tier": tier,
        "tier_name": config.name,
        "price_monthly": config.price_kwd_monthly,
        "features": features,
    }
