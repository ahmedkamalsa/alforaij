"""تقييم بيت صليبيخات (300م، قديم، ملاصق للمسجد، شارع واحد — مطلوب 160-180 ألف) عبر المسار الكامل."""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.request_parser import parse_request
from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import search_external_sources
from backend.services.matching import top_matches
from backend.services.valuation import enrich_rankings
from backend.services.deduplication import deduplicate_ranked
from backend.services.report_generator import build_report
from backend.main import _default_sale_when_unspecified, _filter_listings_by_explicit_location

TEXT = "بيع بيت في صليبيخات 300 متر قديم ملاصق للمسجد شارع واحد بحدود 160 الف"


def main() -> None:
    request = parse_request(TEXT)
    _default_sale_when_unspecified(request)
    print("=== REQUEST ===", flush=True)
    print(json.dumps({
        "transaction": request.transaction,
        "property_type": request.property_type,
        "areas": request.areas,
        "governorates": request.governorates,
        "budget": request.budget,
        "min_area": request.min_area,
        "max_area": request.max_area,
    }, ensure_ascii=False), flush=True)

    listings = load_listings()
    local_count = len(listings)
    external_listings, external_statuses = search_external_sources(request)
    listings.extend(external_listings)
    if request.governorates and not request.areas:
        allowed = set(request.governorates)
        listings = [i for i in listings if i.governorate in allowed]
    listings = _filter_listings_by_explicit_location(listings, request, {})
    ranked = top_matches(request, listings, limit=100)
    enriched = enrich_rankings(request, ranked, listings)
    deduped = deduplicate_ranked(enriched)[:30]

    print(f"\n=== RESULTS: {len(deduped)} ===", flush=True)
    for i, item in enumerate(deduped, start=1):
        print(json.dumps({
            "code": item.listing.code,
            "title": (item.listing.summary or "")[:80],
            "area": item.listing.area,
            "governorate": item.listing.governorate,
            "price": item.listing.price,
            "space": item.listing.space,
            "source": item.listing.source,
            "match": round(item.match_score, 2),
            "rec": round(item.recommendation_score),
            "conf": round(item.confidence, 2),
            "label": item.valuation_label,
            "reason": item.valuation_reason[:120],
            "market_median": item.market_median,
            "url": item.listing.original_url,
        }, ensure_ascii=False), flush=True)

    report = build_report(request, deduped, local_count, external_statuses, {}, include_local_source=True)
    print("\n=== SUMMARY ===", flush=True)
    print(report.get("summary", "")[:600], flush=True)
    print("\n=== SOURCES ===", flush=True)
    for s in external_statuses:
        print(json.dumps({"name": s.get("name"), "status": s.get("status"), "records": s.get("records"),
                          "note": (s.get("note") or "")[:100]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
