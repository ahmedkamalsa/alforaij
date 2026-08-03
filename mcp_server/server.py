from __future__ import annotations

import json
import sys

from backend.connectors.alforaij import load_listings
from backend.services.deduplication import deduplicate_ranked
from backend.services.matching import top_matches
from backend.services.report_generator import build_report
from backend.services.request_parser import parse_request
from backend.services.valuation import enrich_rankings


TOOLS = [
    "parse_property_request",
    "search_properties",
    "evaluate_property",
    "compare_properties",
    "rank_properties",
    "generate_property_report",
    "get_property_sources",
    "get_valuation_evidence",
]


def analyze(text: str) -> dict:
    request = parse_request(text)
    listings = load_listings()
    ranked = top_matches(request, listings, limit=40)
    enriched = enrich_rankings(request, ranked, listings)
    return build_report(request, deduplicate_ranked(enriched)[:20], len(listings))


def handle(message: dict) -> dict:
    tool = message.get("tool")
    if tool == "parse_property_request":
        return {"request": parse_request(str(message.get("text") or "")).__dict__}
    if tool in set(TOOLS) - {"parse_property_request", "get_property_sources"}:
        return analyze(str(message.get("text") or ""))
    if tool == "get_property_sources":
        return {"sources": ["alforaij_board"], "external_sources": "not_configured"}
    return {"tools": TOOLS, "usage": {"tool": "generate_property_report", "text": "مطلوب بيت في المطلاع"}}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = handle(json.loads(line))
        except Exception as exc:  # pragma: no cover
            response = {"error": str(exc)}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
