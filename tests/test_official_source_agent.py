from __future__ import annotations

import unittest
from unittest import mock

from backend.services.official_source_agent import (
    OFFICIAL_REFERENCE_SOURCES,
    _CACHE,
    check_official_reference_sources,
)


class OfficialSourceAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        # عزل كاش الوحدة بين الاختبارات
        _CACHE.update(at=0.0, payload=None)

    def test_check_sources_reports_reachable_counts(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Response()):
            result = check_official_reference_sources(timeout=1, force=True)

        self.assertEqual(result["count"], len(OFFICIAL_REFERENCE_SOURCES))
        self.assertEqual(result["reachable"], len(OFFICIAL_REFERENCE_SOURCES))
        self.assertEqual(result["sources"][0]["status"], "reachable")

    def test_second_call_serves_cache_without_network(self) -> None:
        """الكاش (6 ساعات) يمنع إعادة الفحص الشبكي عند كل استدعاء."""
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Response()) as opener:
            first = check_official_reference_sources(timeout=1, force=True)
            calls_after_first = opener.call_count
            second = check_official_reference_sources(timeout=1)  # من الكاش

        self.assertIs(second, first)
        self.assertEqual(opener.call_count, calls_after_first, "الاستدعاء الثاني يجب ألا يلمس الشبكة")

    def test_force_bypasses_cache(self) -> None:
        """force=True يتجاوز الكاش ويعيد الفحص الفعلي."""
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Response()) as opener:
            check_official_reference_sources(timeout=1, force=True)
            check_official_reference_sources(timeout=1, force=True)

        # فحصان قسريان = 6 مصادر × 2
        self.assertEqual(opener.call_count, len(OFFICIAL_REFERENCE_SOURCES) * 2)


if __name__ == "__main__":
    unittest.main()
