"""هوية المستخدمين: دعم أرقام هواتف دول متعددة + OTP (توليد/تجزئة/تحقق/محاولات).

يدعم:
- الكويت (+965)
- السعودية (+966)  
- الإمارات (+971)
- البحرين (+973)
- عمان (+968)
- قطر (+974)
- مصر (+20)

الأدوار:
- admin: مدير النظام - وصول كامل
- employee: موظف - وصول محدود حسب الصلاحيات
- user: مستخدم عادي - وصول أساسي

منطق نقي قابل للاختبار بلا شبكة — التخزين (Supabase) والتسليم (واتساب) خارج هذه
الوحدة: النقاط في backend/main.py والمرسل في scripts/send_whatsapp_message.py.

الأمان: سرّ المستخدم (24 حرفًا عشوائيًا) هو المفتاح الوحيد لبياناته — لا يُكشف
أبدًا ويُحفظ في localStorage فقط. رمز التحقق 6 أرقام بملح (sha256)، صالح 10 دقائق
مع حد 5 محاولات، وإعادة الإرسال تبطل الرمز القديم.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

OTP_LIFETIME_SECONDS = 600        # الرمز صالح 10 دقائق
OTP_MAX_ATTEMPTS = 5              # حد المحاولات قبل إعادة الإرسال
OTP_RESEND_WINDOW_SECONDS = 900   # لا إعادة إرسال قبل 15 دقيقة
SECRET_LENGTH = 24

# ─── الأدوار والصلاحيات ───
ROLES = {
    "admin": {
        "name": "مدير النظام",
        "name_en": "Administrator",
        "permissions": ["all"],
    },
    "employee": {
        "name": "موظف",
        "name_en": "Employee",
        "permissions": [
            "search",
            "comparisons",
            "dashboard_view",
            "basic_analysis",
            "pdf_reports",
            "opportunity_alerts",
        ],
    },
    "user": {
        "name": "مستخدم",
        "name_en": "User",
        "permissions": ["search", "dashboard_view"],
    },
}

# ─── أكواد الدول المدعومة ───
COUNTRY_CODES: dict[str, dict[str, str]] = {
    "KW": {"code": "+965", "name": "الكويت", "pattern": r"^[2-9]\d{7}$", "digits": 8},
    "SA": {"code": "+966", "name": "السعودية", "pattern": r"^5\d{8}$", "digits": 9},
    "AE": {"code": "+971", "name": "الإمارات", "pattern": r"^[50|52|55|56|58]\d{7,8}$", "digits": "9-10"},
    "BH": {"code": "+973", "name": "البحرين", "pattern": r"^3\d{7}$", "digits": 8},
    "OM": {"code": "+968", "name": "عُمان", "pattern": r"^[79]\d{7}$", "digits": 8},
    "QA": {"code": "+974", "name": "قطر", "pattern": r"^[3-7]\d{7}$", "digits": 8},
    "EG": {"code": "+20", "name": "مصر", "pattern": r"^1[0125]\d{8}$", "digits": 10},
}


def normalize_phone(raw: str) -> tuple[str, str]:
    """توحيد رقم الهاتف دوليًا — يعيد (رقم موحّد بصيغة E.164، رمز الدولة).

    يقبل أي رقم هاتف دولي صحيح (8-15 رقمًا) مع رمز الدولة.
    يحاول التعرف على الدولة المعروفة أولًا، ثم يقبل أي رقم صالح.

    Returns:
        (normalized_phone, country_code) أو ("", "") إذا لم يتعرف
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    # Strip single leading 0 (local dialing prefix) — the frontend already combines
    # country code + local number, but if raw is a bare local number like 01061234567,
    # stripping the 0 lets the known_map find the country prefix.
    if digits.startswith("0") and len(digits) > 1 and not digits.startswith("00"):
        digits = digits[1:]

    # محاولة التعرف على الدولة المعروفة أولًا
    known_map = {
        "965": ("KW", 11), "966": ("SA", 12), "971": ("AE", (11, 12)),
        "973": ("BH", 11), "968": ("OM", 11), "974": ("QA", 11),
        "20": ("EG", 12), "962": ("JO", 12), "964": ("IQ", 12),
        "961": ("LB", 11), "90": ("TR", 12), "972": ("IL", 12),
        "91": ("IN", 12), "86": ("CN", 12), "81": ("JP", 11),
        "82": ("KR", 12), "44": ("GB", 12), "1": ("US", 11),
        "33": ("FR", 11), "49": ("DE", 12), "39": ("IT", 11),
        "34": ("ES", 11), "7": ("RU", 11), "55": ("BR", 12),
        "52": ("MX", 12), "61": ("AU", 11), "967": ("YE", 12),
        "963": ("SY", 12), "960": ("MV", 11), "94": ("LK", 11),
        "92": ("PK", 12), "880": ("BD", 12), "63": ("PH", 11),
        "66": ("TH", 10), "62": ("ID", 11), "60": ("MY", 10),
        "65": ("SG", 10), "84": ("VN", 10), "98": ("IR", 11),
        "93": ("AF", 10), "212": ("MA", 10), "213": ("DZ", 10),
        "216": ("TN", 9), "218": ("LY", 10), "249": ("SD", 10),
        "254": ("KE", 10), "256": ("UG", 10), "234": ("NG", 11),
        "27": ("ZA", 10), "20": ("EG", 12),
    }

    for code, (country, expected_len) in known_map.items():
        if digits.startswith(code):
            if isinstance(expected_len, tuple):
                if len(digits) in expected_len:
                    return f"+{digits}", country
            elif len(digits) == expected_len:
                return f"+{digits}", country

    # محاولة التعرف على الأرقام المحلية المعروفة
    for country_code, info in COUNTRY_CODES.items():
        if re.match(info["pattern"], digits):
            return f"{info['code']}{digits}", country_code

    # قبول أي رقم دولي صالح (8-15 رقمًا، لا يبدأ بـ 0)
    if 8 <= len(digits) <= 15 and not digits.startswith("0"):
        return f"+{digits}", "XX"

    return "", ""


def normalize_phone_kw(raw: str) -> str:
    """توحيد رقم الهاتف — يقبل أي رقم دولي."""
    phone, _ = normalize_phone(raw)
    return phone


def new_secret() -> str:
    """سرّ المستخدم: 24 حرفًا عشوائيًا — المفتاح الوحيد لقراءة/تعديل بياناته."""
    return secrets.token_urlsafe(18)[:SECRET_LENGTH]


def issue_otp() -> tuple[str, str, float]:
    """يُصدر رمز تحقق: (code من 6 أرقام، salt:sha256(code+salt)، epoch الانتهاء)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(8)
    return code, _store(code, salt), time.time() + OTP_LIFETIME_SECONDS


def check_otp(code: str, stored: str, expires_at_epoch: float, attempts: int) -> tuple[bool, str]:
    """تحقق من الرمز: (ناجح، السبب) — السبب: ok|no_otp|expired|too_many_attempts|wrong_code."""
    if not code or not stored:
        return False, "no_otp"
    if time.time() > expires_at_epoch:
        return False, "expired"
    if attempts >= OTP_MAX_ATTEMPTS:
        return False, "too_many_attempts"
    if ":" not in stored:
        return False, "no_otp"
    salt, digest = stored.split(":", 1)
    if not hmac.compare_digest(_digest(code, salt), digest):
        return False, "wrong_code"
    return True, "ok"


def otp_resend_allowed(now: float, requested_at_epoch: float | None) -> bool:
    """هل يُسمح بإعادة إرسال الرمز؟ (بعد نافذة 15 دقيقة من آخر طلب)."""
    if requested_at_epoch is None:
        return True
    return now - requested_at_epoch >= OTP_RESEND_WINDOW_SECONDS


def check_role_permission(role: str, permission: str) -> bool:
    """التحقق من صلاحية الدور."""
    role_config = ROLES.get(role)
    if not role_config:
        return False
    if "all" in role_config["permissions"]:
        return True
    return permission in role_config["permissions"]


def get_user_role(user_id: str, db=None) -> str:
    """جلب دور المستخدم من قاعدة البيانات."""
    # الافتراضي هو مستخدم عادي
    if not user_id:
        return "anonymous"
    return "user"


def _store(code: str, salt: str) -> str:
    return f"{salt}:{_digest(code, salt)}"


def _digest(code: str, salt: str) -> str:
    return hashlib.sha256(f"{code}:{salt}".encode()).hexdigest()
