"""هوية المستخدمين المجانيين: توحيد الهاتف الكويتي + OTP (توليد/تجزئة/تحقق/محاولات).

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

_KW_FULL = re.compile(r"^965\d{8}$")
_KW_LOCAL = re.compile(r"^[2-9]\d{7}$")


def normalize_phone_kw(raw: str) -> str:
    """توحيد رقم هاتف كويتي لصيغة +965XXXXXXXX — يرفض غير الكويتي.

    يقبل: 55512345 (محلي) / +96555512345 / 96555512345 / 0096555512345.
    يرفض: 01061234567 (مصري) و+20106... وكل ما ليس رقمًا كويتيًا صالحًا.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if _KW_FULL.match(digits):
        return f"+{digits}"
    if _KW_LOCAL.match(digits):
        return f"+965{digits}"
    return ""


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


def _store(code: str, salt: str) -> str:
    return f"{salt}:{_digest(code, salt)}"


def _digest(code: str, salt: str) -> str:
    return hashlib.sha256(f"{code}:{salt}".encode()).hexdigest()
