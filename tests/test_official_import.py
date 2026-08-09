from __future__ import annotations

import unittest
from unittest import mock

from backend.services.official_import import import_official_transactions_content


class OfficialImportTests(unittest.TestCase):
    def test_import_csv_content_normalizes_and_saves(self) -> None:
        content = "reference,area,property_type,price,space,date\nMOJ-1,المطلاع,بيت,350000,400,2026-08-01\n"

        with mock.patch("backend.services.official_import._save_local", return_value=1) as save_local, \
            mock.patch("backend.services.official_import.is_configured", return_value=True), \
            mock.patch("backend.services.official_import.save_official_transactions") as save_remote:
            result = import_official_transactions_content("moj.csv", content)

        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["imported"], 1)
        save_local.assert_called_once()
        save_remote.assert_called_once()


if __name__ == "__main__":
    unittest.main()
