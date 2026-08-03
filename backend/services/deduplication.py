from __future__ import annotations

from backend.models import RankedListing


def deduplicate_ranked(items: list[RankedListing]) -> list[RankedListing]:
    seen: set[tuple] = set()
    output: list[RankedListing] = []
    for item in items:
        listing = item.listing
        key = (
            listing.area,
            listing.property_type,
            listing.space or "",
            listing.price or "",
            " ".join((listing.summary or "").split()[:12]),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output

