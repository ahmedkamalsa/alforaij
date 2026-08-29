"""اختبارات Smart Alerts — تنبيهات ذكية للسعر والفرص الجديدة.

تغطي:
- كشف انخفاضات الأسعار
- كشف الإعلانات الجديدة
- منع التكرار
- بناء التنبيهات للمستخدم
- التنسيق للدفع
"""
from __future__ import annotations

import unittest

from backend.services.smart_alerts import (
    detect_price_drops,
    detect_new_listings,
    should_alert,
    build_user_alerts,
    format_alert_for_push,
    _alert_title,
)


class PriceDropDetectionTests(unittest.TestCase):
    """اختبارات كشف انخفاضات الأسعار."""

    def test_detects_price_below_median(self) -> None:
        """يكتشف السعر الأقل من المتوسط."""
        listings = [
            {"code": "A1", "area": "الفردوس", "price": 150000},
            {"code": "A2", "area": "الفردوس", "price": 250000},
        ]
        medians = {"الفردوس": 250000}
        alerts = detect_price_drops(listings, medians, threshold_pct=10)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["code"], "A1")
        self.assertEqual(alerts[0]["type"], "price_near_median")

    def test_ignores_price_near_median(self) -> None:
        """يتجاهل السعر القريب من المتوسط."""
        listings = [{"code": "B1", "area": "المنطقة", "price": 230000}]
        medians = {"المنطقة": 250000}
        alerts = detect_price_drops(listings, medians, threshold_pct=10)
        self.assertEqual(len(alerts), 0)  # 8% فقط — أقل من 10%

    def test_no_median_no_alert(self) -> None:
        """بدون متوسط = لا تنبيه."""
        listings = [{"code": "C1", "area": "منطقة جديدة", "price": 100000}]
        alerts = detect_price_drops(listings, {})
        self.assertEqual(len(alerts), 0)

    def test_severity_high_for_20pct_drop(self) -> None:
        """انخفاض 20%+ = خطورة عالية."""
        listings = [{"code": "D1", "area": "منطقة", "price": 100000}]
        medians = {"منطقة": 150000}  # 33% أقل
        alerts = detect_price_drops(listings, medians, threshold_pct=10)
        self.assertEqual(alerts[0]["severity"], "high")


class NewListingDetectionTests(unittest.TestCase):
    """اختبارات كشف الإعلانات الجديدة."""

    def test_detects_new_listing(self) -> None:
        """يكتشف الإعلان الجديد."""
        current = {"X1", "X2", "X3"}
        previous = {"X1", "X2"}
        listings_map = {"X3": {"code": "X3", "area": "المنطقة", "price": 100000, "priceText": "100,000 د.ك"}}
        alerts = detect_new_listings(current, previous, listings_map)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["code"], "X3")
        self.assertEqual(alerts[0]["type"], "new_listing")

    def test_no_new_listings(self) -> None:
        """لا تنبيهات إذا لم تتغير القائمة."""
        current = {"X1", "X2"}
        previous = {"X1", "X2"}
        alerts = detect_new_listings(current, previous, {})
        self.assertEqual(len(alerts), 0)


class AlertThrottlingTests(unittest.TestCase):
    """اختبارات منع التكرار."""

    def test_first_alert_always_allowed(self) -> None:
        """أول تنبيه دائماً مسموح."""
        self.assertTrue(should_alert(None))

    def test_throttle_after_recent_alert(self) -> None:
        """يمنع التنبيه بعد تنبيه حديث."""
        import time
        recent = time.time() - 3600  # قبل ساعة
        self.assertFalse(should_alert(recent, min_interval_hours=6))

    def test_allow_after_interval(self) -> None:
        """يسمح بعد المهلة."""
        import time
        old = time.time() - 7 * 3600  # قبل 7 ساعات
        self.assertTrue(should_alert(old, min_interval_hours=6))


class BuildUserAlertsTests(unittest.TestCase):
    """اختبارات بناء التنبيهات للمستخدم."""

    def test_builds_alerts_for_user(self) -> None:
        """يبني تنبيهات للمستخدم."""
        searches = [{"user_secret": "s1", "areas": ["الفردوس"], "alert_enabled": True}]  # Not used in current impl but kept for reference
        listings = [{"code": "Z1", "area": "الفردوس", "price": 100000}]
        medians = {"الفردوس": 150000}
        alerts = build_user_alerts("s1", searches, listings, medians)
        self.assertGreater(len(alerts), 0)

    def test_sorted_by_severity(self) -> None:
        """التنبيهات مرتبة حسب الأولوية."""
        listings = [
            {"code": "S1", "area": "أ", "price": 50000},
            {"code": "S2", "area": "ب", "price": 100000},
        ]
        medians = {"أ": 100000, "ب": 120000}
        alerts = build_user_alerts("s1", [], listings, medians)
        severities = [a.get("severity") for a in alerts]
        # high comes before medium/info
        for i in range(len(severities) - 1):
            order = {"high": 0, "medium": 1, "info": 2}
            self.assertLessEqual(order.get(severities[i], 2), order.get(severities[i + 1], 2))


class PushFormattingTests(unittest.TestCase):
    """اختبارات التنسيق للدفع."""

    def test_format_price_drop(self) -> None:
        alert = {"type": "price_drop", "message": "سعر أقل", "code": "X1", "area": "منطقة", "price": 100000}
        result = format_alert_for_push(alert)
        self.assertEqual(result["title"], "📉 انخفاض السعر")
        self.assertEqual(result["body"], "سعر أقل")

    def test_format_new_listing(self) -> None:
        alert = {"type": "new_listing", "message": "فرصة جديدة", "code": "Y1"}
        result = format_alert_for_push(alert)
        self.assertEqual(result["title"], "🏢 فرصة جديدة")

    def test_alert_title_fallback(self) -> None:
        self.assertEqual(_alert_title("unknown"), "🔔 تنبيه الفريج")
        self.assertEqual(_alert_title(None), "🔔 تنبيه الفريج")


if __name__ == "__main__":
    unittest.main()
