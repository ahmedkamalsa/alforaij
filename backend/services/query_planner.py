from __future__ import annotations

from backend.models import PropertyRequest


def planned_sources(request: PropertyRequest) -> list[str]:
    sources = ["alforaij_board"]
    if request.intent in {"valuation", "search_and_value"}:
        sources.append("official_transactions_planned")
    return sources
