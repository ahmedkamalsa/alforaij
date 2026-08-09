"""تشغيل وكيل التحديث اليومي لمستودع البيانات والتحليلات.

الاستخدام:
    python scripts/daily_data_update.py
    python scripts/daily_data_update.py --official-file data/moj_transactions.csv
    python scripts/daily_data_update.py --official-url https://example/internal/moj.csv

يمكن أيضًا ضبط:
    OFFICIAL_TRANSACTIONS_SOURCE=path_or_url
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.daily_update_agent import run_daily_update_agent  # noqa: E402


def _print(value: object) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily data update agent for Alforaij Research Assistant")
    parser.add_argument("--official-file", default="", help="CSV/JSON file with official transactions")
    parser.add_argument("--official-url", default="", help="CSV/JSON URL with official transactions")
    parser.add_argument("--skip-external", action="store_true", help="Build opportunities without live external scan")
    args = parser.parse_args()

    official_source = args.official_file or args.official_url
    result = run_daily_update_agent(
        official_source=official_source,
        include_external=not args.skip_external,
    )
    _print({
        "status": result.get("status"),
        "startedAt": result.get("startedAt"),
        "finishedAt": result.get("finishedAt"),
        "summary": result.get("summary"),
        "error": result.get("error"),
    })
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
