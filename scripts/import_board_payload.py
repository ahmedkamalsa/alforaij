from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def extract_records(html_path: Path) -> list[dict]:
    text = html_path.read_text(encoding="utf-8")
    match = re.search(r'<script id="payload" type="application/json">(.*?)</script>', text, re.S)
    if not match:
        raise SystemExit(f"payload script was not found in {html_path}")
    payload = json.loads(match.group(1))
    records = payload.get("records")
    if not isinstance(records, list):
        raise SystemExit("payload.records is not a list")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Import alforaijboard embedded JSON payload.")
    parser.add_argument(
        "--html",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "vs" / "site" / "index.html",
        help="Path to alforaijboard site/index.html",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "seed_listings.json",
        help="Output records JSON path",
    )
    args = parser.parse_args()
    records = extract_records(args.html)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Imported {len(records)} records into {args.out}")


if __name__ == "__main__":
    main()
