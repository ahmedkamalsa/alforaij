from __future__ import annotations

from backend.models import Listing


def deal_index_score(listing: Listing, market_median: float | None) -> float | None:
    if not listing.price or not market_median:
        return None
    return round(max(0.0, min(100.0, (market_median / listing.price) * 100)), 1)
