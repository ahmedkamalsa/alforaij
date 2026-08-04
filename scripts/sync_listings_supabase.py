from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.connectors.alforaij import load_listings  # noqa: E402
from backend.services.supabase_store import is_configured, save_listings  # noqa: E402


def main() -> None:
    if not is_configured():
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before syncing listings.")
    listings = load_listings()
    save_listings(listings)
    print(f"Synced {len(listings)} listings to Supabase.")


if __name__ == "__main__":
    main()
