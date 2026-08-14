from __future__ import annotations

import unittest

from backend.services.source_registry import source_registry


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
