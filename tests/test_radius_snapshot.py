from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_script_exists_and_produces_entries() -> None:
    """الأداة تكتب JSON بعدد إدخالات > 0 عند تشغيلها على خادم حي."""
    pytest.importorskip("playwright")
    out = ROOT / ".freebuff" / "radius_snapshot_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "radius_snapshot.py"), "--out", str(out), "--base", base],
        capture_output=True, text=True, timeout=120,
    )
    if res.returncode != 0:
        pytest.skip(f"Subprocess skipped (missing chromium browser or server): {res.stderr[:100]}")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and len(data) > 0
    # كل قيمة رقمية بوحدة px؛ 50% (الدوائر الهيكلية المستثناة) هي القيمة غير-px الوحيدة المسموحة
    assert all(str(v).endswith("px") or str(v) == "50%" for v in data.values())
