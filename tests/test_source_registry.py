from __future__ import annotations

import json
import time
import unittest
from unittest import mock

from backend.services import source_registry as registry_module
from backend.services.source_registry import (
    SOURCE_REGISTRY,
    match_source_id,
    remote_registry_ids,
    resolve_source_id,
    source_registry,
)


class SourceRegistryResolutionTests(unittest.TestCase):
    """حل معرف المصدر: المطابقة من السجل المحلي ثم التحقق من قيد FK الحي."""

    def test_derived_from_registry_for_new_sources(self) -> None:
        """المصادر الجديدة تُسجَّل بمعرفاتها الصحيحة من السجل لا بأسماء منخفضة."""
        self.assertEqual(match_source_id("Aqarat"), "aqarat")
        self.assertEqual(match_source_id("4Sale"), "four_sale")
        self.assertEqual(match_source_id("الصفقات الرسمية"), "official_transactions")

    def test_short_name_does_not_false_match(self) -> None:
        """اسم قصير مثل «عقار» لا يُلتقط داخل «بوعقار» أو «التسجيل العقاري»."""
        short_id = match_source_id("عقار")
        self.assertNotEqual(short_id, "bu3qar")
        self.assertNotEqual(short_id, "official_transactions")

    def test_matches_live_connector_names(self) -> None:
        """أسماء الموصلات الحية تُسجَّل بمعرفات سجل صحيحة — لا كسر للمفتاح الأجنبي.

        الانحدار: كانت 4 أسماء حية (PropertyFinder/Bayut/Bu3qar/الحسبة) تسقط
        لمعرفات غير موجودة في source_registry فيفشل قيد FK ويوقف حفظ الدفعة كاملة
        (كل بحث = «فشل الحفظ»).
        """
        registry_ids = {str(e["id"]) for e in SOURCE_REGISTRY}
        live_names = [
            "الفريج", "OpenSooq", "Mourjan", "Q8Aqar", "Sakan", "Waseet",
            "NabdAqar", "Bu3qar / بوشملان", "Aqarat", "4Sale", "Yebtah",
            "PropertyFinder", "Aqarmap", "Bayut", "الحسبة - صفقات عامة",
            "السوق المباشر", "مؤشرات رسمية", "الصفقات الرسمية",
        ]
        for name in live_names:
            with self.subTest(name=name):
                self.assertIn(match_source_id(name), registry_ids)

    def test_unknown_falls_back_to_registry_entry(self) -> None:
        """مصدر غير معروف لا يُرسل معرفًا خارج السجل — يسقط لسلة توسعة معروفة."""
        registry_ids = {str(e["id"]) for e in SOURCE_REGISTRY}
        self.assertIn(match_source_id("منصة مستقبلية غير موجودة بعد"), registry_ids)

    def test_keeps_local_mapping_when_remote_unavailable(self) -> None:
        """عند تعذر قراءة الجدول الحي (اختبارات/شبكة) يبقى المعرف المحلي بلا تغيير."""
        with mock.patch.object(registry_module, "remote_registry_ids", return_value=None):
            self.assertEqual(resolve_source_id("PropertyFinder"), "propertyfinder_kw")
            self.assertEqual(resolve_source_id("Mourjan"), "mourjan_kw")

    def test_unregistered_remotely_buckets_safely(self) -> None:
        """المصدر غير المسجل في الجدول الحي يُسقط لسلة آمنة لا تكسر قيد FK.

        الانحدار: PropertyFinder/Bayut/Aqarmap تُطابق معرفات محلية
        (propertyfinder_kw/bayut_kw/aqarmap_kw) غير موجودة في جدول
        source_registry الحي في Supabase (الجدول يتخلف عن الملف المحلي حتى
        تُشغَّل مزامنة السجل). إرسالها إلى source_runs يفشل القيد الأجنبي
        (HTTP 409) فيتوقف حفظ الدفعة كاملة — كل بحث = «فشل الحفظ».
        التحقق من الجدول الحي يبقي الدفعة صالحة ويحفظ السجلات في سلة
        other_marketplaces المعروفة.
        """
        # جدول حي "تخلف": كل المعرفات المحلية عدا الثلاثة غير المسجلة
        remote_ids = {
            str(e["id"]) for e in SOURCE_REGISTRY if e["id"] not in {"propertyfinder_kw", "bayut_kw", "aqarmap_kw"}
        }
        with mock.patch.object(registry_module, "remote_registry_ids", return_value=remote_ids):
            self.assertEqual(resolve_source_id("PropertyFinder"), "other_marketplaces")
            self.assertEqual(resolve_source_id("Bayut"), "other_marketplaces")
            self.assertEqual(resolve_source_id("Aqarmap"), "other_marketplaces")
            # المصدر المسجل يبقى على معرفه الصحيح
            self.assertEqual(resolve_source_id("Mourjan"), "mourjan_kw")
            self.assertEqual(resolve_source_id("Bu3qar / بوشملان"), "bu3qar")

    def test_drift_report_lists_unregistered_local_ids(self) -> None:
        """تقرير الانجراف يكشف المصادر المحلية غير المسجلة في الجدول الحي."""
        remote_ids = {str(e["id"]) for e in SOURCE_REGISTRY} - {"propertyfinder_kw", "bayut_kw", "aqarmap_kw", "e_gov_kw_portal"}
        with mock.patch.object(registry_module, "remote_registry_ids", return_value=remote_ids):
            report = registry_module.drift_report()
        self.assertTrue(report["available"])
        self.assertFalse(report["synced"])
        self.assertEqual(
            report["unregisteredLocal"],
            ["aqarmap_kw", "bayut_kw", "e_gov_kw_portal", "propertyfinder_kw"],
        )
        self.assertEqual(report["remoteOnly"], [])

    def test_drift_report_reports_unavailable_without_remote(self) -> None:
        """تعذر قراءة الجدول الحي يظهر كحالة واضحة لا خطأ."""
        with mock.patch.object(registry_module, "remote_registry_ids", return_value=None):
            report = registry_module.drift_report()
        self.assertFalse(report["available"])

    def test_sync_remote_registry_upserts_every_local_source(self) -> None:
        """المزامنة ترفع كل إدخال محلي (upsert على id) وتعيد ملخصًا بالانجراف."""
        with mock.patch.object(registry_module, "_remote_reads_enabled", return_value=True), \
            mock.patch.object(registry_module.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 204
            result = registry_module.sync_remote_registry()
        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["count"], len(SOURCE_REGISTRY))
        self.assertIn("drift", result)

    def test_sync_remote_registry_failed_reports_error(self) -> None:
        """فشل الشبكة أثناء المزامنة يُسجَّل كفشل ولا يُرمى استثناء."""
        with mock.patch.object(registry_module, "_remote_reads_enabled", return_value=True), \
            mock.patch.object(registry_module.urllib.request, "urlopen", side_effect=OSError("offline")):
            result = registry_module.sync_remote_registry()
        self.assertEqual(result["status"], "failed")
        self.assertIn("offline", result["error"])

    def test_sync_remote_registry_invalidates_stale_cache(self) -> None:
        """بعد نجاح المزامنة يُبطل كاش المعرفات القديم فيقرأ التقرير والتحقق الجدول الحي.

        الانحدار: كان كاش الـ60 ثانية يبقى على مجموعة ما قبل المزامنة، فيقرأ
        تقرير الانجراف داخل نتيجة المزامنة نفسها معرفات قديمة («غير مسجلة» رغم
        أنها سُجلت للتو)، ويستمر الحفظ في إسقاط المصادر المسجلة حديثًا لسلة
        other_marketplaces حتى انتهاء مدة الكاش.
        """
        stale = {"old_ids_only"}
        registry_module._remote_ids_cache = stale
        registry_module._remote_ids_fetched_at = time.time()
        body = json.dumps([{"id": e["id"]} for e in SOURCE_REGISTRY]).encode("utf-8")
        try:
            with mock.patch.object(registry_module, "_remote_reads_enabled", return_value=True), \
                mock.patch.object(registry_module.urllib.request, "urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.status = 200
                urlopen.return_value.__enter__.return_value.read.return_value = body
                result = registry_module.sync_remote_registry()
            self.assertEqual(result["status"], "synced")
            self.assertEqual(result["count"], len(SOURCE_REGISTRY))
            # الانجراف محسوب من الجدول الحي بعد المزامنة، لا من الكاش القديم
            self.assertTrue(result["drift"]["synced"])
            # الكاش أُعيد بناؤه من الجدول الحي (المجموعة الكاملة) لا من القديم
            self.assertEqual(
                registry_module._remote_ids_cache,
                {str(e["id"]) for e in SOURCE_REGISTRY},
            )
        finally:
            registry_module._remote_ids_cache = None
            registry_module._remote_ids_fetched_at = 0.0


class SourceRegistryTests(unittest.TestCase):
    def test_registry_marks_scored_and_non_scored_sources(self) -> None:
        sources = {source["id"]: source for source in source_registry()}

        self.assertEqual(sources["opensooq_kw"]["status"], "live_scored")
        self.assertEqual(sources["mourjan_kw"]["status"], "live_scored")
        # الخطة المستقبلية نُفّذت: Q8Aqar يقرأ صفحات التفاصيل، وSakan يحاول الحالة المضمّنة
        self.assertEqual(sources["q8aqar"]["status"], "live_scored")
        self.assertEqual(sources["sakan"]["status"], "live_conditional")
        self.assertIn("لا يدخل في الدرجة", sources["sakan"]["scoringPolicy"])
        # الصفقات الرسمية أصبحت موصلًا متصلًا (أعلى مرجع في التقييم)
        self.assertEqual(sources["official_transactions"]["status"], "connected")

    def test_candidate_platforms_are_registered(self) -> None:
        """المنصات المرشحة الخمس أُدرجت في قاعدة المصادر بسياساتها وحالاتها."""
        sources = {source["id"]: source for source in source_registry()}

        expected = {
            "propertyfinder_kw": "live_blocked",
            "aqarmap_kw": "discontinued",
            "bayut_kw": "live_blocked",
            "e_gov_kw_portal": "official_service",
            "paci_kuwait_finder": "geo_verification",
        }
        for source_id, status in expected.items():
            self.assertIn(source_id, sources, f"missing source {source_id}")
            self.assertEqual(sources[source_id]["status"], status)
            # كل مصدر مرشح يجب أن يحمل سياسات التقييم والأدلة كباقي المصادر
            for field in ("scoringPolicy", "evidencePolicy", "trustLevel", "role"):
                self.assertTrue(sources[source_id].get(field), f"{source_id} missing {field}")


if __name__ == "__main__":
    unittest.main()
