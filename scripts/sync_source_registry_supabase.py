from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_local_env  # noqa: E402
from backend.services import source_registry  # noqa: E402

# تحميل .env إن لم تكن المتغيرات مضبوطة في البيئة (نفس سلوك باقي السكربتات)
load_local_env()


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    """مزامنة السجل المحلي إلى جدول source_registry الحي — واجهة CLI رقيقة.

    العمل الفعلي في backend.services.source_registry.sync_remote_registry حتى
    تستهلكه الوكيل اليومي والواجهة البرمجية بنفس المسار (لا منطق مكرر).
    """
    require_env("SUPABASE_URL")
    require_env("SUPABASE_SERVICE_ROLE_KEY")
    result = source_registry.sync_remote_registry()
    if result.get("status") != "synced":
        print(f"Sync failed: {result.get('error') or result.get('status')}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Synced {result.get('count', 0)} sources to Supabase.")
    drift = result.get("drift") or {}
    if drift.get("synced"):
        print("Registry is in sync — no drift.")
    else:
        unregistered = ", ".join(drift.get("unregisteredLocal") or []) or "none"
        print(f"Drift remaining — unregistered local ids: {unregistered}")


if __name__ == "__main__":
    main()
