from __future__ import annotations

from backend.models import Listing
from backend.services.valuation import comparable_pool


def find_comparables(target: Listing, listings: list[Listing]) -> list[Listing]:
    return comparable_pool(target, listings)
