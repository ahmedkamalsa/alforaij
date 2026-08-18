"""طبقة الأمان — تحقق من الخادم وحماية ضد سوء الاستخدام.

**مهم:** هذا ليس بديلاً عن المصادقة الكاملة (Supabase Auth)، لكنه
يُضيف طبقة حماية على الخادم تمنع أبسط أشكال التحايل.

المكونات:
1. تحقق الخطة من الخادم (server-side tier validation)
2. حماية من تجاوز المعدل (rate limiting)
3. تنظيف المدخلات (input sanitization)
4. CSP headers for XSS protection

الاستخدام:
    from backend.services.security import SecurityMiddleware
    middleware = SecurityMiddleware()
    if not middleware.check_tier(user_id, "pdf_reports"):
        return {"error": "غير مصرح"}
"""
from __future__ import annotations

import html
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.services.tier import TIER_CONFIG, check_feature, check_usage


# ─── تحقق الخطة من الخادم ───

@dataclass
class UserTierState:
    """حالة الخطة للمستخدم (مخزنة في الذاكرة أو قاعدة البيانات)."""
    tier: str = "free"
    usage: dict[str, int] = field(default_factory=lambda: {
        "searches": 0,
        "pdfs": 0,
        "alerts": 0,
    })
    last_reset: str = ""  # YYYY-MM-DD
    referrals: int = 0
    reports_purchased: int = 0
    trial_start: str | None = None


class TierValidator:
    """تحقق من الخطة من الخادم — لا يعتمد على بيانات المتصفح.

    **القاعدة:** الخادم هو المرجع الوحيد للخطة والاستخدام.
    بيانات المتصفح (localStorage) للعرض فقط — لا تُ信赖.
    """

    def __init__(self):
        # في الإنتاج، تُخزَّن في قاعدة بيانات (Supabase)
        # هنا مخزنة في الذاكرة للتطوير
        self._users: dict[str, UserTierState] = {}

    def get_user_state(self, user_id: str) -> UserTierState:
        """الحصول على حالة المستخدم."""
        if user_id not in self._users:
            self._users[user_id] = UserTierState()
        return self._users[user_id]

    def set_user_tier(self, user_id: str, tier: str) -> bool:
        """تغيير خطة المستخدم (يتحقق من صحة الخطة)."""
        if tier not in TIER_CONFIG:
            return False
        state = self.get_user_state(user_id)
        object.__setattr__(state, 'tier', tier)
        return True

    def check_feature(self, user_id: str, feature: str) -> dict[str, Any]:
        """التحقق من ميزة معينة للمستخدم من الخادم.

        Returns:
            dict مع:
            - allowed: bool
            - tier: الخطة الحالية
            - message: رسالة للمستخدم
            - upgrade_prompt: رسالة ترقية (إذا كانت الميزة غير متاحة)
        """
        state = self.get_user_state(user_id)

        # التحقق من_trial
        if state.trial_start:
            from datetime import datetime, timedelta
            trial_start = datetime.fromisoformat(state.trial_start)
            if datetime.now() - trial_start > timedelta(days=7):
                # انتهت الفترة التجريبية
                object.__setattr__(state, 'trial_start', None)
                object.__setattr__(state, 'tier', 'free')

        # التحقق من الميزة
        if not check_feature(state.tier, feature):
            from backend.services.tier import get_upgrade_prompt
            return {
                "allowed": False,
                "tier": state.tier,
                "message": f"ميزة '{feature}' غير متاحة في الخطة {state.tier}",
                "upgrade_prompt": get_upgrade_prompt(state.tier, feature),
            }

        return {
            "allowed": True,
            "tier": state.tier,
            "message": "مسموح",
            "upgrade_prompt": None,
        }

    def check_usage(self, user_id: str, feature: str) -> dict[str, Any]:
        """التحقق من استخدام المستخدم من الخادم."""
        state = self.get_user_state(user_id)
        usage_count = state.usage.get(feature, 0)
        result = check_usage(state.tier, feature, usage_count)
        result["tier"] = state.tier
        return result

    def record_usage(self, user_id: str, feature: str, count: int = 1) -> None:
        """تسجيل استخدام المستخدم."""
        state = self.get_user_state(user_id)
        current = state.usage.get(feature, 0)
        state.usage[feature] = current + count


# ─── حماية من تجاوز المعدل (Rate Limiting) ───

@dataclass
class RateLimitEntry:
    """سجل طلب واحد."""
    timestamp: float
    count: int = 1


class RateLimiter:
    """حماية من تجاوز المعدل — يمنع الهجمات và سوء الاستخدام.

    يعمل بخوارزمية sliding window:
    - يحفظ الطلبات خلال نافذة زمنية (بضع ثوانٍ)
    - يمنع أي مُجرّب يتجاوز الحد
    - يسمح للمستخدمين العاديين بحرية行动
    """

    def __init__(
        self,
        window_seconds: int = 60,
        max_requests: int = 60,
        max_searches: int = 20,
        max_pdfs: int = 5,
    ):
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self.max_searches = max_searches
        self.max_pdfs = max_pdfs
        self._requests: dict[str, list[RateLimitEntry]] = defaultdict(list)

    def _cleanup(self, key: str) -> None:
        """إزالة الطلبات القديمة خارج النافذة."""
        cutoff = time.time() - self.window_seconds
        self._requests[key] = [
            entry for entry in self._requests[key]
            if entry.timestamp > cutoff
        ]

    def check(self, key: str, endpoint: str = "default") -> dict[str, Any]:
        """التحقق مما إذا كان الطلب مسموحاً.

        Args:
            key: معرف المستخدم أو IP
            endpoint: نوع الطلب (search, pdf, default)

        Returns:
            dict مع:
            - allowed: bool
            - remaining: المتبقي
            - retry_after: ثوانٍ للانتظار (إذا كان مرفوضاً)
        """
        full_key = f"{key}:{endpoint}"
        self._cleanup(full_key)

        entries = self._requests[full_key]
        current_count = sum(entry.count for entry in entries)

        # تحديد الحد حسب نوع الطلب
        if endpoint == "search":
            limit = self.max_searches
        elif endpoint == "pdf":
            limit = self.max_pdfs
        else:
            limit = self.max_requests

        if current_count >= limit:
            # حساب وقت الانتظار
            oldest = entries[0].timestamp if entries else time.time()
            retry_after = max(1, int(self.window_seconds - (time.time() - oldest)))
            return {
                "allowed": False,
                "remaining": 0,
                "limit": limit,
                "retry_after": retry_after,
                "message": f"太快! انتظر {retry_after} ثانية",
            }

        # تسجيل الطلب
        self._requests[full_key].append(RateLimitEntry(timestamp=time.time()))

        return {
            "allowed": True,
            "remaining": limit - current_count - 1,
            "limit": limit,
            "retry_after": 0,
            "message": f"متبقي {limit - current_count - 1}",
        }


# ─── تنظيف المدخلات (Input Sanitization) ───

class InputSanitizer:
    """تنظيف المدخلات من السكريبتات الخبيثة والحقن.

    **القاعدة:** كل مدخل من المستخدم يجب أن يمر عبر هذا التنظيف
    قبل أي معالجة أو عرض.
    """

    # أنماط خبيثة شائعة
    MALICIOUS_PATTERNS = [
        re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),
        re.compile(r'data:text/html', re.IGNORECASE),
        re.compile(r'vbscript:', re.IGNORECASE),
    ]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """تنظيف نص من السكريبتات الخبيثة."""
        if not isinstance(text, str):
            return str(text)

        # إزالة أنماط خبيثة
        cleaned = text
        for pattern in cls.MALICIOUS_PATTERNS:
            cleaned = pattern.sub('', cleaned)

        # HTML encode
        cleaned = html.escape(cleaned)

        return cleaned.strip()

    @classmethod
    def sanitize_html(cls, html_content: str) -> str:
        """تنظيف محتوى HTML (للعرض فقط)."""
        if not isinstance(html_content, str):
            return str(html_content)

        # إزالة السكريبتات
        cleaned = cls.sanitize_text(html_content)

        # إزالة attributes خبيثة
        cleaned = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', '', cleaned, flags=re.IGNORECASE)

        return cleaned

    @classmethod
    def sanitize_search_query(cls, query: str) -> str:
        """تنظيف استعلام البحث."""
        if not isinstance(query, str):
            return ""

        # إزالة أحرف خبيثة
        cleaned = query.strip()

        # الحد من الطول
        if len(cleaned) > 500:
            cleaned = cleaned[:500]

        # تنظيف من السكريبتات
        cleaned = cls.sanitize_text(cleaned)

        return cleaned

    @classmethod
    def validate_email(cls, email: str) -> bool:
        """التحقق من صحة البريد الإلكتروني."""
        if not isinstance(email, str):
            return False

        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))


# ─── CSP Headers ───

CSP_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://*.supabase.co; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def get_security_headers() -> dict[str, str]:
    """الحصول على رؤوس الأمان للرد."""
    return CSP_HEADERS.copy()


# ─── Middleware الرئيسي ───

class SecurityMiddleware:
    """طبقة الأمان المتكاملة — تجمع كل المكونات.

    الاستخدام في main.py:
        middleware = SecurityMiddleware()

        # في كل API endpoint:
        if not middleware.authorize(user_id, "search"):
            return {"error": "غير مصرح"}

        # تسجيل الاستخدام بعد النجاح:
        middleware.record_usage(user_id, "search")
    """

    def __init__(self):
        self.tier_validator = TierValidator()
        self.rate_limiter = RateLimiter()
        self.sanitizer = InputSanitizer()

    def authorize(self, user_id: str, feature: str) -> dict[str, Any]:
        """التحقق من صلاحية المستخدم لميزة معينة.

        هذا هو الدالة الرئيسية التي يجب استدعاؤها في كل API endpoint.
        """
        # 1. التحقق من rate limit
        rate_check = self.rate_limiter.check(user_id, feature)
        if not rate_check["allowed"]:
            return {
                "authorized": False,
                "reason": "rate_limit",
                "message": rate_check["message"],
                "retry_after": rate_check["retry_after"],
            }

        # 2. التحقق من الخطة
        tier_check = self.tier_validator.check_feature(user_id, feature)
        if not tier_check["allowed"]:
            return {
                "authorized": False,
                "reason": "tier_limit",
                "message": tier_check["message"],
                "upgrade_prompt": tier_check["upgrade_prompt"],
            }

        # 3. التحقق من الاستخدام
        usage_check = self.tier_validator.check_usage(user_id, feature)
        if not usage_check["allowed"]:
            return {
                "authorized": False,
                "reason": "usage_limit",
                "message": usage_check["message"],
                "remaining": 0,
                "limit": usage_check["limit"],
            }

        return {
            "authorized": True,
            "tier": tier_check["tier"],
            "remaining": usage_check["remaining"],
            "message": "مصرح",
        }

    def record_usage(self, user_id: str, feature: str, count: int = 1) -> None:
        """تسجيل استخدام المستخدم بعد نجاح الطلب."""
        self.tier_validator.record_usage(user_id, feature, count)

    def sanitize(self, text: str) -> str:
        """تنظيف مدخلات المستخدم."""
        return self.sanitizer.sanitize_text(text)

    def get_headers(self) -> dict[str, str]:
        """الحصول على رؤوس الأمان."""
        return get_security_headers()
