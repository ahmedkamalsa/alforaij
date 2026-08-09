from __future__ import annotations

import unittest
from unittest import mock

from backend.services.official_source_agent import OFFICIAL_REFERENCE_SOURCES, check_official_reference_sources


class OfficialSourceAgentTests(unittest.TestCase):
    def test_check_sources_reports_reachable_counts(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Response()):
            result = check_official_reference_sources(timeout=1)

        self.assertEqual(result["count"], len(OFFICIAL_REFERENCE_SOURCES))
        self.assertEqual(result["reachable"], len(OFFICIAL_REFERENCE_SOURCES))
        self.assertEqual(result["sources"][0]["status"], "reachable")


if __name__ == "__main__":
    unittest.main()
