from __future__ import annotations

from backend.models import Listing, PropertyRequest


def search(request: PropertyRequest) -> list[Listing]:
    """Placeholder for CSV/JSON feeds from partner brokers."""
    return []
