from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PropertyRequest:
    raw_text: str
    intent: str = "search_and_value"
    transaction: str = ""
    property_type: str = ""
    areas: list[str] = field(default_factory=list)
    governorates: list[str] = field(default_factory=list)
    min_area: float | None = None
    max_area: float | None = None
    budget: float | None = None
    rent_budget: float | None = None
    bedrooms: int | None = None
    income: float | None = None
    condition: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    excluded_area_numbers: dict[str, float] = field(default_factory=dict)


@dataclass
class Listing:
    code: str
    transaction: str
    governorate: str
    area: str
    property_type: str
    detail_class: str
    price: float | None
    price_text: str
    space: float | None
    listing_mode: str
    summary: str
    features: str
    published_date: str
    original_url: str
    source: str = "الفريج"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedListing:
    listing: Listing
    match_score: float
    valuation_label: str
    valuation_reason: str
    confidence: float
    deal_score: float
    recommendation_score: float
    market_median: float | None
    price_ratio: float | None
    match_breakdown: list[dict[str, Any]]
    recommendation_breakdown: list[dict[str, Any]]
    number_sources: dict[str, Any]
    reasons: list[str]
    warnings: list[str]
    comparables: list[dict[str, Any]]
