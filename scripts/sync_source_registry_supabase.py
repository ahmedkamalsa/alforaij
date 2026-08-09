from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_local_env  # noqa: E402
from backend.services.source_registry import source_registry  # noqa: E402

# تحميل .env إن لم تكن المتغيرات مضبوطة في البيئة (نفس سلوك باقي السكربتات)
load_local_env()


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    url = require_env("SUPABASE_URL").rstrip("/")
    key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    endpoint = f"{url}/rest/v1/source_registry?on_conflict=id"
    rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "connection": row["connection"],
            "role": row["role"],
            "trust_level": row["trustLevel"],
            "scoring_policy": row["scoringPolicy"],
            "evidence_policy": row["evidencePolicy"],
            "status": row["status"],
        }
        for row in source_registry()
    ]
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in {200, 201, 204}:
            raise SystemExit(f"Supabase returned HTTP {response.status}")
    print(f"Synced {len(rows)} sources to Supabase.")


if __name__ == "__main__":
    main()
