"""اختبارات الأمان — تتحقق من حماية النظام ضد سوء الاستخدام.

تختبر:
- تحقق الخطة من الخادم (server-side tier validation)
- حماية من تجاوز المعدل (rate limiting)
- تنظيف المدخلات (input sanitization)
- CSP headers
"""
from __future__ import annotations

import time
import unittest

from backend.services.security import (
    InputSanitizer,
    RateLimiter,
    SecurityMiddleware,
    TierValidator,
    get_security_headers,
)


class TierValidatorTests(unittest.TestCase):
    """اختبارات تحقق الخطة من الخادم."""

    def setUp(self):
        self.validator = TierValidator()

    def test_new_user_is_free(self) -> None:
        """المستخدم الجديد يكون في الخطة المجانية."""
        state = self.validator.get_user_state("user1")
        self.assertEqual(state.tier, "free")

    def test_set_valid_tier(self) -> None:
        """تغيير خطة صحيحة ناجح."""
        result = self.validator.set_user_tier("user1", "pro")
        self.assertTrue(result)
        state = self.validator.get_user_state("user1")
        self.assertEqual(state.tier, "pro")

    def test_set_invalid_tier(self) -> None:
        """تغيير خطة غير صحيحة يفشل."""
        result = self.validator.set_user_tier("user1", "invalid")
        self.assertFalse(result)

    def test_check_feature_allowed(self) -> None:
        """ميزة متاحة تُسمح."""
        self.validator.set_user_tier("user1", "pro")
        result = self.validator.check_feature("user1", "pdf_reports")
        self.assertTrue(result["allowed"])

    def test_check_feature_not_allowed(self) -> None:
        """ميزة غير متاحة تُرفض."""
        result = self.validator.check_feature("user1", "pdf_reports")
        self.assertFalse(result["allowed"])
        self.assertIn("upgrade_prompt", result)

    def test_check_usage_within_limit(self) -> None:
        """استخدام ضمن الحد مسموح."""
        # Free tier has limit of 20 searches
        self.validator.record_usage("user1", "search", 5)
        result = self.validator.check_usage("user1", "search")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["remaining"], 15)

    def test_record_usage(self) -> None:
        """تسجيل الاستخدام يعمل."""
        self.validator.record_usage("user1", "search", 5)
        state = self.validator.get_user_state("user1")
        self.assertEqual(state.usage["search"], 5)

    def test_usage_accumulates(self) -> None:
        """الاستخدام يتراكم."""
        self.validator.record_usage("user1", "search", 3)
        self.validator.record_usage("user1", "search", 2)
        state = self.validator.get_user_state("user1")
        self.assertEqual(state.usage["search"], 5)


class RateLimiterTests(unittest.TestCase):
    """اختبارات حماية من تجاوز المعدل."""

    def setUp(self):
        # Use max_searches=3 for easier testing
        self.limiter = RateLimiter(window_seconds=60, max_requests=60, max_searches=3)

    def test_within_limit(self) -> None:
        """طلب ضمن الحد مسموح."""
        result = self.limiter.check("user1", "search")
        self.assertTrue(result["allowed"])

    def test_at_limit(self) -> None:
        """طلبات عند الحد تُرفض."""
        for i in range(3):
            self.limiter.check("user1", "search")
        result = self.limiter.check("user1", "search")
        self.assertFalse(result["allowed"])
        self.assertIn("retry_after", result)

    def test_different_endpoints_independent(self) -> None:
        """نهايات مختلفة مستقلة."""
        for _ in range(5):
            self.limiter.check("user1", "search")
        # PDF لا يتأثر
        result = self.limiter.check("user1", "pdf")
        self.assertTrue(result["allowed"])

    def test_different_users_independent(self) -> None:
        """مستخدمون مختلفون مستقلون."""
        for _ in range(5):
            self.limiter.check("user1", "search")
        result = self.limiter.check("user2", "search")
        self.assertTrue(result["allowed"])

    def test_remaining_decreases(self) -> None:
        """المتبقي ينقص."""
        result1 = self.limiter.check("user1", "search")
        result2 = self.limiter.check("user1", "search")
        self.assertGreater(result1["remaining"], result2["remaining"])


class InputSanitizerTests(unittest.TestCase):
    """اختبارات تنظيف المدخلات."""

    def test_sanitize_normal_text(self) -> None:
        """نص عادي يبقى كما هو."""
        result = InputSanitizer.sanitize_text("hello world")
        self.assertEqual(result, "hello world")

    def test_sanitize_script_tag(self) -> None:
        """وسم script يُزال."""
        result = InputSanitizer.sanitize_text('<script>alert("xss")</script>')
        self.assertNotIn("<script>", result)

    def test_sanitize_event_handler(self) -> None:
        """معالج أحداث يُزال."""
        result = InputSanitizer.sanitize_text('<img onerror="alert(1)">')
        self.assertNotIn("onerror", result)

    def test_sanitize_javascript_url(self) -> None:
        """رابط javascript يُزال."""
        result = InputSanitizer.sanitize_text('javascript:alert(1)')
        self.assertNotIn("javascript:", result)

    def test_sanitize_html_encodes(self) -> None:
        """HTML يُرمّز."""
        result = InputSanitizer.sanitize_text('<b>bold</b>')
        self.assertIn("&lt;", result)
        self.assertIn("&gt;", result)

    def test_sanitize_search_query(self) -> None:
        """استعلام البحث يُنظف."""
        result = InputSanitizer.sanitize_search_query('شقة في حولي <script>')
        self.assertNotIn("<script>", result)
        self.assertIn("شقة", result)

    def test_sanitize_long_query(self) -> None:
        """استعلام طويل يُقص."""
        long_query = "a" * 1000
        result = InputSanitizer.sanitize_search_query(long_query)
        self.assertLessEqual(len(result), 500)

    def test_validate_email_valid(self) -> None:
        """بريد صحيح يُقبل."""
        self.assertTrue(InputSanitizer.validate_email("user@example.com"))

    def test_validate_email_invalid(self) -> None:
        """بريد خاطئ يُرفض."""
        self.assertFalse(InputSanitizer.validate_email("not-an-email"))
        self.assertFalse(InputSanitizer.validate_email("@example.com"))
        self.assertFalse(InputSanitizer.validate_email("user@"))


class SecurityHeadersTests(unittest.TestCase):
    """اختبارات رؤوس الأمان."""

    def test_csp_header_exists(self) -> None:
        """ CSP header موجود."""
        headers = get_security_headers()
        self.assertIn("Content-Security-Policy", headers)

    def test_x_frame_options(self) -> None:
        """X-Frame-Options DENY."""
        headers = get_security_headers()
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_x_content_type_options(self) -> None:
        """X-Content-Type-Options nosniff."""
        headers = get_security_headers()
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_x_xss_protection(self) -> None:
        """X-X-Protection مفعّل."""
        headers = get_security_headers()
        self.assertIn("1; mode=block", headers["X-XSS-Protection"])


class SecurityMiddlewareTests(unittest.TestCase):
    """اختبارات Middleware الأمان المتكامل."""

    def setUp(self):
        self.middleware = SecurityMiddleware()

    def test_authorize_free_user_search(self) -> None:
        """مستخدم مجاني يمكنه البحث."""
        result = self.middleware.authorize("user1", "search")
        self.assertTrue(result["authorized"])

    def test_deny_pdf_for_free_user(self) -> None:
        """مستخدم مجاني لا يمكنه PDF."""
        result = self.middleware.authorize("user1", "pdf_reports")
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "tier_limit")

    def test_authorize_pro_user_pdf(self) -> None:
        """مستخدم محترف يمكنه PDF."""
        self.middleware.tier_validator.set_user_tier("user1", "pro")
        result = self.middleware.authorize("user1", "pdf_reports")
        self.assertTrue(result["authorized"])

    def test_sanitize_delegates(self) -> None:
        """ التنظيف يعمل."""
        result = self.middleware.sanitize('<script>alert(1)</script>')
        self.assertNotIn("<script>", result)

    def test_get_headers(self) -> None:
        """الرؤوس تُعاد."""
        headers = self.middleware.get_headers()
        self.assertIn("Content-Security-Policy", headers)


if __name__ == "__main__":
    unittest.main()
