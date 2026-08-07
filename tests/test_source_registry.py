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


if __name__ == "__main__":
    unittest.main()
