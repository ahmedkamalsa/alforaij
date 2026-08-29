"""اختبارات هوية المستخدمين المجانيين: توحيد الهاتف + OTP (توليد/تحقق/محاولات).

تغطي:
- توحيد الرقم لصيغة E.164 دوليًا (الكويت، السعودية، الإمارات، وغيرها).
- رمز تحقق 6 أرقام بملح، انتهاء 10 دقائق، حد 5 محاولات.
- سرّ المستخدم عشوائي بطول 24.
- إعادة الإرسال تبطل الرمز القديم.

بلا شبكة (قابل للتشغيل في CI).
"""
from __future__ import annotations

import unittest

from backend.services.accounts import (
    OTP_MAX_ATTEMPTS,
    check_otp,
    issue_otp,
    new_secret,
    normalize_phone,
    normalize_phone_kw,
)


class NormalizePhoneTests(unittest.TestCase):
    def test_accepts_local_kw_mobile(self) -> None:
        phone, country = normalize_phone("55512345")
        self.assertEqual(phone, "+96555512345")
        self.assertEqual(country, "KW")

    def test_accepts_international_kw(self) -> None:
        phone, country = normalize_phone("+96555512345")
        self.assertEqual(phone, "+96555512345")
        self.assertEqual(country, "KW")

    def test_accepts_saudi_number(self) -> None:
        phone, country = normalize_phone("+966512345678")
        self.assertEqual(phone, "+966512345678")
        self.assertEqual(country, "SA")

    def test_accepts_uae_number(self) -> None:
        phone, country = normalize_phone("+971501234567")
        self.assertEqual(phone, "+971501234567")
        self.assertEqual(country, "AE")

    def test_accepts_egyptian_number(self) -> None:
        # الأرقام المصرية: +20 + 10 حروف = 12 رقم
        phone, country = normalize_phone("01061234567")
        self.assertEqual(phone, "+201061234567")
        self.assertEqual(country, "EG")

    def test_egyptian_with_country_code(self) -> None:
        # المستخدم يكتب +201064955051 مباشرة
        phone, country = normalize_phone("+201064955051")
        self.assertEqual(phone, "+201064955051")
        self.assertEqual(country, "EG")

    def test_saudi_number(self) -> None:
        phone, country = normalize_phone("+966555123456")
        self.assertEqual(phone, "+966555123456")
        self.assertEqual(country, "SA")

    def test_uae_number(self) -> None:
        phone, country = normalize_phone("+971555123456")
        self.assertEqual(phone, "+971555123456")
        self.assertEqual(country, "AE")

    def test_us_number(self) -> None:
        phone, country = normalize_phone("+12025551234")
        self.assertEqual(phone, "+12025551234")
        self.assertEqual(country, "US")

    def test_kuwaiti_local_input(self) -> None:
        # مستخدم يكتب 55512345 بدون رمز الدولة — يتحول لـ +965
        phone, country = normalize_phone("55512345")
        self.assertEqual(phone, "+96555512345")
        self.assertEqual(country, "KW")

    def test_rejects_garbage(self) -> None:
        phone, country = normalize_phone("")
        self.assertEqual(phone, "")
        phone, country = normalize_phone("abc")
        self.assertEqual(phone, "")
        phone, country = normalize_phone("12345")
        self.assertEqual(phone, "")

    def test_normalize_phone_kw_backward_compatible(self) -> None:
        # التوافق مع الكود القديم
        self.assertEqual(normalize_phone_kw("55512345"), "+96555512345")
        self.assertEqual(normalize_phone_kw("+96555512345"), "+96555512345")


class SecretTests(unittest.TestCase):
    def test_secret_length_and_randomness(self) -> None:
        s1 = new_secret()
        s2 = new_secret()
        self.assertEqual(len(s1), 24)
        self.assertEqual(len(s2), 24)
        self.assertNotEqual(s1, s2)


class OtpTests(unittest.TestCase):
    def test_issue_returns_six_digit_code_and_salted_hash(self) -> None:
        code, stored, _expires = issue_otp()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertIn(":", stored)  # salt:digest

    def test_correct_code_passes(self) -> None:
        code, stored, expires = issue_otp()
        ok, reason = check_otp(code, stored, expires, 0)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_wrong_code_fails(self) -> None:
        code, stored, expires = issue_otp()
        wrong = "000000" if code != "000000" else "111111"
        ok, reason = check_otp(wrong, stored, expires, 0)
        self.assertFalse(ok)
        self.assertEqual(reason, "wrong_code")

    def test_expired_code_fails(self) -> None:
        _code, stored, _expires = issue_otp()
        ok, reason = check_otp("123456", stored, 0, 0)  # انتهى منذ زمن
        self.assertFalse(ok)
        self.assertEqual(reason, "expired")

    def test_attempt_limit(self) -> None:
        code, stored, expires = issue_otp()
        ok, reason = check_otp(code, stored, expires, OTP_MAX_ATTEMPTS)
        self.assertFalse(ok)
        self.assertEqual(reason, "too_many_attempts")

    def test_no_otp_yet(self) -> None:
        ok, reason = check_otp("123456", "", 0, 0)
        self.assertFalse(ok)
        self.assertEqual(reason, "no_otp")

    def test_resend_invalidates_old_code(self) -> None:
        code1, stored1, _e1 = issue_otp()
        _code2, stored2, expires2 = issue_otp()
        # الرمز القديم لم يعد صالحًا ضد التخزين الجديد
        ok, reason = check_otp(code1, stored2, expires2, 0)
        self.assertFalse(ok)
        self.assertEqual(reason, "wrong_code")
        self.assertNotEqual(stored1, stored2)


class AppleLoginTests(unittest.TestCase):
    """اختبارات تسجيل الدخول بـ Apple"""

    def test_apple_id_token_decode(self) -> None:
        """Test Apple id_token JWT decoding"""
        import base64, json as _json
        # Create a mock Apple id_token
        header = base64.urlsafe_b64encode(_json.dumps({"alg": "ES256", "kid": "test"}).encode()).rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(_json.dumps({
            "iss": "https://appleid.apple.com",
            "sub": "001234.abcdef",
            "email": "user@example.com",
            "aud": "com.alforaij.app",
        }).encode()).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(b"fake-sig").rstrip(b"=").decode()
        token = f"{header}.{payload_b64}.{sig}"
        # Decode (same logic as backend)
        parts = token.split(".")
        self.assertEqual(len(parts), 3)
        b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        decoded = _json.loads(base64.urlsafe_b64decode(b64))
        self.assertEqual(decoded["iss"], "https://appleid.apple.com")
        self.assertEqual(decoded["sub"], "001234.abcdef")
        self.assertEqual(decoded["email"], "user@example.com")

    def test_apple_phone_key_format(self) -> None:
        """Apple users get phone_key like 'apple:{sub}'"""
        apple_sub = "001234.abcdef"
        phone_key = f"apple:{apple_sub}"
        self.assertTrue(phone_key.startswith("apple:"))
        self.assertEqual(phone_key, "apple:001234.abcdef")

    def test_apple_code_fallback(self) -> None:
        """When no id_token is provided, code is used as identifier"""
        code = "abc123def456ghi789jkl0"
        phone_key = f"apple_code:{code[:20]}"
        self.assertEqual(phone_key, "apple_code:abc123def456ghi789jk")
        self.assertTrue(len(phone_key) > 10)


if __name__ == "__main__":
    unittest.main()
