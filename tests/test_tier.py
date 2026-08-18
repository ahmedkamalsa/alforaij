"""اختبارات نظام الخطط (Tier System).

يختبر:
- تعريف الخطط الثلاث (free, pro, enterprise)
- تفعيل/تعطيل المميزات حسب الخطة
- حدود الاستخدام اليومية
- رسائل الترقية
- عرض الخطط لصفحة الأسعار
"""
from __future__ import annotations

import unittest

from backend.services.tier import (
    TIER_CONFIG,
    check_feature,
    check_usage,
    get_feature_limit,
    get_tier_config,
    get_upgrade_prompt,
    list_tiers,
)


class TierConfigTests(unittest.TestCase):
    """اختبارات تعريف الخطط."""

    def test_all_four_tiers_defined(self) -> None:
        """يجب أن تكون هناك أربع خطط: free, trial, pro, enterprise."""
        self.assertEqual(set(TIER_CONFIG.keys()), {"free", "trial", "pro", "enterprise"})

    def test_free_tier_is_truly_free(self) -> None:
        """الخطة المجانية يجب أن يكون سعرها 0."""
        free = TIER_CONFIG["free"]
        self.assertEqual(free.price_kwd_monthly, 0)
        self.assertEqual(free.price_kwd_yearly, 0)

    def test_pro_tier_has_price(self) -> None:
        """الخطة المحترفة لها سعر شهري وسنوي."""
        pro = TIER_CONFIG["pro"]
        self.assertEqual(pro.price_kwd_monthly, 15)
        self.assertEqual(pro.price_kwd_yearly, 144)

    def test_enterprise_tier_is_custom_pricing(self) -> None:
        """خطة المؤسسات لها سعر مخصص (None)."""
        enterprise = TIER_CONFIG["enterprise"]
        self.assertIsNone(enterprise.price_kwd_monthly)
        self.assertIsNone(enterprise.price_kwd_yearly)

    def test_all_tiers_have_names(self) -> None:
        """كل خطة لها اسم عربي وإنجليزي."""
        for tier_id, config in TIER_CONFIG.items():
            self.assertTrue(config.name, f"Tier {tier_id} missing Arabic name")
            self.assertTrue(config.name_en, f"Tier {tier_id} missing English name")


class FeatureCheckTests(unittest.TestCase):
    """اختبارات تفعيل المميزات."""

    def test_free_tier_no_pdf(self) -> None:
        """الخطة المجانية لا تدعم PDF."""
        self.assertFalse(check_feature("free", "pdf_reports"))

    def test_free_tier_has_search(self) -> None:
        """الخطة المجانية تدعم البحث."""
        self.assertTrue(check_feature("free", "search"))

    def test_pro_tier_has_pdf(self) -> None:
        """الخطة المحترفة تدعم PDF."""
        self.assertTrue(check_feature("pro", "pdf_reports"))

    def test_pro_tier_has_alerts(self) -> None:
        """الخطة المحترفة تدعم التنبيهات."""
        self.assertTrue(check_feature("pro", "opportunity_alerts"))

    def test_pro_tier_no_api(self) -> None:
        """الخطة المحترفة لا تدعم API."""
        self.assertFalse(check_feature("pro", "api_access"))

    def test_enterprise_has_all_features(self) -> None:
        """خطة المؤسسات تدعم جميع المميزات."""
        config = TIER_CONFIG["enterprise"]
        for feat_id, feat in config.features.items():
            self.assertTrue(
                feat.enabled,
                f"Enterprise tier should have {feat_id} enabled",
            )

    def test_enterprise_has_api(self) -> None:
        """خطة المؤسسات تدعم API."""
        self.assertTrue(check_feature("enterprise", "api_access"))

    def test_enterprise_has_multi_user(self) -> None:
        """خطة المؤسسات تدعم الحسابات المتعددة."""
        self.assertTrue(check_feature("enterprise", "multi_user"))

    def test_unknown_tier_has_no_features(self) -> None:
        """خطة غير معروفة لا تدعم أي ميزة."""
        self.assertFalse(check_feature("unknown", "search"))
        self.assertFalse(check_feature("unknown", "pdf_reports"))

    def test_unknown_feature_has_no_access(self) -> None:
        """ميزة غير معروفة غير متاحة في أي خطة."""
        self.assertFalse(check_feature("free", "nonexistent_feature"))
        self.assertFalse(check_feature("pro", "nonexistent_feature"))


class FeatureLimitTests(unittest.TestCase):
    """اختبارات حدود المميزات."""

    def test_free_search_limit_is_20(self) -> None:
        """حد البحث في الخطة المجانية 20."""
        self.assertEqual(get_feature_limit("free", "search"), 20)

    def test_free_comparisons_limit_is_5(self) -> None:
        """حد المقارنات في الخطة المجانية 5."""
        self.assertEqual(get_feature_limit("free", "comparisons"), 5)

    def test_pro_search_limit_is_unlimited(self) -> None:
        """بحث المحترف غير محدود."""
        self.assertIsNone(get_feature_limit("pro", "search"))

    def test_pro_comparisons_limit_is_unlimited(self) -> None:
        """مقارنات المحترف غير محدودة."""
        self.assertIsNone(get_feature_limit("pro", "comparisons"))

    def test_disabled_feature_returns_zero_limit(self) -> None:
        """ميزة معطلة تعيد حد 0."""
        self.assertEqual(get_feature_limit("free", "pdf_reports"), 0)

    def test_unknown_tier_returns_zero_limit(self) -> None:
        """خطة غير معروفة تعيد حد 0."""
        self.assertEqual(get_feature_limit("unknown", "search"), 0)


class UsageCheckTests(unittest.TestCase):
    """اختبارات فحص الاستخدام."""

    def test_within_limit(self) -> None:
        """استخدام ضمن الحد مسموح."""
        result = check_usage("free", "search", 5)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["remaining"], 15)
        self.assertEqual(result["limit"], 20)

    def test_at_limit(self) -> None:
        """استخدام عند الحد (20/20) — العملية الحادية والعشرون مرفوضة."""
        result = check_usage("free", "search", 20)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], 0)

    def test_over_limit(self) -> None:
        """استخدام تجاوز الحد غير مسموح."""
        result = check_usage("free", "search", 25)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], 0)

    def test_unlimited_tier(self) -> None:
        """خطة غير محدودة تسمح دائماً."""
        result = check_usage("pro", "search", 1000)
        self.assertTrue(result["allowed"])
        self.assertIsNone(result["remaining"])
        self.assertIsNone(result["limit"])

    def test_disabled_feature(self) -> None:
        """ميزة معطلة لا تسمح أبداً."""
        result = check_usage("free", "pdf_reports", 0)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], 0)

    def test_usage_message_includes_remaining(self) -> None:
        """الرسالة تInclude المتبقي."""
        result = check_usage("free", "search", 3)
        self.assertIn("17", result["message"])

    def test_usage_message_at_limit(self) -> None:
        """الرسالة عند الحد تذكر الترقية."""
        result = check_usage("free", "search", 20)
        self.assertIn("رقّ", result["message"])


class UpgradePromptTests(unittest.TestCase):
    """اختبارات رسائل الترقية."""

    def test_free_to_pro_for_pdf(self) -> None:
        """رسالة ترقية من مجاني لمحترف عند PDF."""
        prompt = get_upgrade_prompt("free", "pdf_reports")
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["next_tier"], "pro")
        self.assertIn("15", prompt["next_price"])

    def test_free_to_pro_for_alerts(self) -> None:
        """رسالة ترقية من مجاني لمحترف عند التنبيهات."""
        prompt = get_upgrade_prompt("free", "opportunity_alerts")
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["next_tier"], "pro")

    def test_pro_to_enterprise_for_api(self) -> None:
        """رسالة ترقية من محترف لمؤسسات عند API."""
        prompt = get_upgrade_prompt("pro", "api_access")
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["next_tier"], "enterprise")

    def test_no_prompt_for_available_feature(self) -> None:
        """لا رسالة ترقية إذا كانت الميزة متاحة."""
        prompt = get_upgrade_prompt("free", "search")
        self.assertIsNone(prompt)

    def test_no_prompt_for_enterprise(self) -> None:
        """لا رسالة ترقية لخطة المؤسسات (أعلى خطة)."""
        prompt = get_upgrade_prompt("enterprise", "api_access")
        self.assertIsNone(prompt)

    def test_unknown_tier_no_prompt(self) -> None:
        """خطة غير معروفة لا تعيد رسالة ترقية."""
        prompt = get_upgrade_prompt("unknown", "pdf_reports")
        self.assertIsNone(prompt)


class ListTiersTests(unittest.TestCase):
    """اختبارات عرض الخطط لصفحة الأسعار."""

    def test_list_returns_four_tiers(self) -> None:
        """قائمة الخطط تعيد أربع خطط."""
        tiers = list_tiers()
        self.assertEqual(len(tiers), 4)

    def test_each_tier_has_required_fields(self) -> None:
        """كل خطة لها الحقول المطلوبة."""
        tiers = list_tiers()
        for tier in tiers:
            self.assertIn("id", tier)
            self.assertIn("name", tier)
            self.assertIn("name_en", tier)
            self.assertIn("price_monthly", tier)
            self.assertIn("price_yearly", tier)
            self.assertIn("features", tier)

    def test_features_have_required_fields(self) -> None:
        """كل ميزة لها الحقول المطلوبة."""
        tiers = list_tiers()
        for tier in tiers:
            for feat in tier["features"]:
                self.assertIn("id", feat)
                self.assertIn("enabled", feat)
                self.assertIn("limit", feat)
                self.assertIn("description", feat)


class TierConfigRetrievalTests(unittest.TestCase):
    """اختبارات الحصول على إعدادات الخطة."""

    def test_get_existing_tier(self) -> None:
        """الحصول على خطة موجودة."""
        config = get_tier_config("free")
        self.assertIsNotNone(config)
        self.assertEqual(config.name, "الأساسي")

    def test_get_nonexistent_tier(self) -> None:
        """الحصول على خطة غير موجودة."""
        config = get_tier_config("nonexistent")
        self.assertIsNone(config)


if __name__ == "__main__":
    unittest.main()
