"""اختبارات Trust Score — مؤشر ثقة الإعلان العقاري.

تغطي:
- حساب الدرجة الكاملة (0-100)
- تأثير عمر الإعلان
- تأثير استقرار السعر
- تأثير تعدد المصادر
- تأثير الصور
- تأثير مصدر الإعلان
- تأثير مطابقة السعر للمتوسط
- التصنيف (trusted/moderate/low)
- التنبيهات
"""
from __future__ import annotations

import unittest

from backend.services.trust_score import (
    calculate_trust_score,
    _score_age,
    _score_price_stability,
    _score_multi_source,
    _score_price_ratio,
    _grade,
    WEIGHT_AGE,
    WEIGHT_PRICE_STABILITY,
    WEIGHT_MULTI_SOURCE,
    WEIGHT_PHOTOS,
    WEIGHT_SOURCE,
    WEIGHT_PRICE_RATIO,
)


class TrustScoreCalculationTests(unittest.TestCase):
    """اختبارات الحساب الأساسي."""

    def test_full_listing_scores_high(self) -> None:
        """إعلان كامل (قديم + ثابت + عدة مصادر + صور + مصدر موثوق) = درجة عالية."""
        result = calculate_trust_score(
            listing={
                "price": 200000,
                "source": "4sale",
                "photos": ["img1.jpg", "img2.jpg"],
                "created_at": "2025-06-01",
                "area": "الفردوس",
                "space": 400,
            },
            area_median_price=200000,
            duplicate_count=2,
        )
        self.assertGreaterEqual(result["score"], 70)
        self.assertEqual(result["grade"], "trusted")
        self.assertEqual(result["label"], "موثق")
        self.assertEqual(result["color"], "#22c55e")

    def test_new_listing_with_no_photos_scores_low(self) -> None:
        """إعلان جديد بدون صور = درجة منخفضة."""
        result = calculate_trust_score(
            listing={
                "price": 100000,
                "source": "unknown",
                "photos": [],
                "created_at": "",
                "area": "المنطقة",
                "space": 200,
            },
        )
        self.assertLessEqual(result["score"], 50)
        self.assertIn("⚠️", " ".join(result["alerts"]))

    def test_score_range_0_to_100(self) -> None:
        """الدرجة دائماً بين 0 و 100."""
        for source in ["", "4sale", "mourjan", "alforaij"]:
            result = calculate_trust_score(
                listing={"price": 100000, "source": source, "photos": []},
            )
            self.assertGreaterEqual(result["score"], 0)
            self.assertLessEqual(result["score"], 100)


class AgeScoreTests(unittest.TestCase):
    """اختبارات تأثير عمر الإعلان."""

    def test_old_listing_gets_full_score(self) -> None:
        """إعلان قديم (60+ يوم) = درجة كاملة."""
        self.assertEqual(_score_age(60), WEIGHT_AGE)
        self.assertEqual(_score_age(90), WEIGHT_AGE)

    def test_new_listing_gets_low_score(self) -> None:
        """إعلان جديد (0-3 أيام) = درجة منخفضة."""
        self.assertLessEqual(_score_age(0), 5)
        self.assertLessEqual(_score_age(1), 5)

    def test_gradual_increase(self) -> None:
        """الدرجة تزداد تدريجياً مع العمر."""
        scores = [_score_age(d) for d in [0, 7, 14, 30, 60]]
        for i in range(len(scores) - 1):
            self.assertGreaterEqual(scores[i + 1], scores[i])


class PriceStabilityTests(unittest.TestCase):
    """اختبارات استقرار السعر."""

    def test_stable_price_gets_full_score(self) -> None:
        """سعر ثابت (بدون تغيير) = درجة كاملة."""
        self.assertEqual(_score_price_stability(0), WEIGHT_PRICE_STABILITY)

    def test_many_changes_gets_low_score(self) -> None:
        """تغييرات كثيرة (5+) = درجة منخفضة."""
        self.assertLessEqual(_score_price_stability(5), 5)

    def test_gradual_decrease(self) -> None:
        """الدرجة تنقص مع زيادة التغييرات."""
        scores = [_score_price_stability(c) for c in [0, 1, 2, 4, 6]]
        for i in range(len(scores) - 1):
            self.assertGreaterEqual(scores[i], scores[i + 1])


class MultiSourceTests(unittest.TestCase):
    """اختبارات تعدد المصادر."""

    def test_multiple_sources_gets_full_score(self) -> None:
        """3+ مصادر = درجة كاملة."""
        self.assertEqual(_score_multi_source(3), WEIGHT_MULTI_SOURCE)
        self.assertEqual(_score_multi_source(5), WEIGHT_MULTI_SOURCE)

    def test_single_source_gets_low_score(self) -> None:
        """مصدر واحد = درجة منخفضة."""
        self.assertLessEqual(_score_multi_source(0), 5)


class PriceRatioTests(unittest.TestCase):
    """اختبارات مطابقة السعر."""

    def test_matching_price_gets_full_score(self) -> None:
        """سعر مطابق للمتوسط (0.8-1.2) = درجة كاملة."""
        score, alert = _score_price_ratio(1.0)
        self.assertEqual(score, WEIGHT_PRICE_RATIO)
        self.assertIsNone(alert)

    def test_very_low_price_alert(self) -> None:
        """سعر منخفض جداً (<0.5) = تنبيه."""
        score, alert = _score_price_ratio(0.4)
        self.assertLessEqual(score, 3)
        self.assertIn("مشبوه", alert or "")

    def test_high_price_warning(self) -> None:
        """سعر مرتفع جداً (>1.5) = تنبيه."""
        score, alert = _score_price_ratio(1.8)
        self.assertLessEqual(score, 5)
        self.assertIn("مرتفع", alert or "")


class GradeTests(unittest.TestCase):
    """اختبارات التصنيف."""

    def test_trusted_grade(self) -> None:
        grade, label, color = _grade(80)
        self.assertEqual(grade, "trusted")
        self.assertEqual(label, "موثق")

    def test_moderate_grade(self) -> None:
        grade, label, color = _grade(60)
        self.assertEqual(grade, "moderate")
        self.assertEqual(label, "متوسط")

    def test_low_grade(self) -> None:
        grade, label, color = _grade(20)
        self.assertEqual(grade, "low")
        self.assertEqual(label, "مشبوه")


class AlertTests(unittest.TestCase):
    """اختبارات التنبيهات."""

    def test_new_listing_alert(self) -> None:
        """إعلان جديد = تنبيه."""
        result = calculate_trust_score(
            listing={"price": 100000, "source": "", "photos": [], "created_at": ""},
        )
        self.assertTrue(any("جديد" in a for a in result["alerts"]))

    def test_unstable_price_alert(self) -> None:
        """سعر غير مستقر = تنبيه."""
        result = calculate_trust_score(
            listing={"price": 100000, "source": "", "photos": []},
            price_history=[{"price": 100000}, {"price": 90000}, {"price": 80000}, {"price": 70000}, {"price": 60000}],
        )
        self.assertTrue(any("تغير" in a for a in result["alerts"]))

    def test_no_photos_alert(self) -> None:
        """بدون صور = تنبيه."""
        result = calculate_trust_score(
            listing={"price": 100000, "source": "", "photos": []},
        )
        self.assertTrue(any("صور" in a for a in result["alerts"]))

    def test_suspicious_low_price_alert(self) -> None:
        """سعر منخفض جداً عن المتوسط = تنبيه."""
        result = calculate_trust_score(
            listing={"price": 50000, "source": "", "photos": ["img.jpg"]},
            area_median_price=200000,
        )
        self.assertTrue(any("منخفض" in a or "مشبوه" in a for a in result["alerts"]))


if __name__ == "__main__":
    unittest.main()
