from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.config import load_local_env


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


if __name__ == "__main__":
    unittest.main()
