from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.config import load_local_env, resolve_log_level


class ConfigTests(unittest.TestCase):
    def test_load_local_env_does_not_override_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("ALFORAIJ_TEST_VALUE=from-file\n", encoding="utf-8")
            os.environ["ALFORAIJ_TEST_VALUE"] = "existing"

            load_local_env(env_path)

            self.assertEqual(os.environ["ALFORAIJ_TEST_VALUE"], "existing")

    def test_load_local_env_reads_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("ALFORAIJ_TEMP_VALUE=ok\n", encoding="utf-8")
            os.environ.pop("ALFORAIJ_TEMP_VALUE", None)

            load_local_env(env_path)

            self.assertEqual(os.environ["ALFORAIJ_TEMP_VALUE"], "ok")

    def test_resolve_log_level_defaults_to_info(self) -> None:
        # بدون متغير بيئة: المستوى الافتراضي INFO مهما كان سياق التشغيل
        self.assertEqual(resolve_log_level(None), logging.INFO)
        self.assertEqual(resolve_log_level(""), logging.INFO)

    def test_resolve_log_level_reads_environment(self) -> None:
        # المستوى يُقرأ من ALFORAIJ_LOG_LEVEL ويُحوَّل لثابت logging صالح
        with mock.patch.dict(os.environ, {"ALFORAIJ_LOG_LEVEL": "debug"}):
            self.assertEqual(resolve_log_level(os.getenv("ALFORAIJ_LOG_LEVEL")), logging.DEBUG)
        with mock.patch.dict(os.environ, {"ALFORAIJ_LOG_LEVEL": "WARNING"}):
            self.assertEqual(resolve_log_level(os.getenv("ALFORAIJ_LOG_LEVEL")), logging.WARNING)

    def test_resolve_log_level_falls_back_on_invalid_value(self) -> None:
        # أي قيمة غير مدعومة تسقط آمنًا إلى INFO بدل كسر التطبيق
        with mock.patch.dict(os.environ, {"ALFORAIJ_LOG_LEVEL": "VERBOSE"}):
            self.assertEqual(resolve_log_level(os.getenv("ALFORAIJ_LOG_LEVEL")), logging.INFO)


if __name__ == "__main__":
    unittest.main()
