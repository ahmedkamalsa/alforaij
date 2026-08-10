"""مقارنة أسعار إيجار المكاتب في مناطق متعددة — نفس مسار /api/analyze في المعالجة."""
import sys, os, json, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.request_parser import parse_request
from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import search_external_sources
from backend.services.matching import top_matches
from backend.services.valuation import enrich_rankings
from backend.services.deduplication import deduplicate_ranked
from backend.main import _default_sale_when_unspecified, _filter_listings_by_explicit_location

AREAS = ["السالمية", "الجابرية", "الشويخ"]

def run_search(raw_text: str) -> dict:
    request = parse_request(raw_text)
    _default_sale_when_unspecified(request)
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
    deduped = deduplicate_ranked(enriched)[:50]
    ok_sources = [s.get("name") or s.get("source") for s in external_statuses
                  if s.get("status") == "ok" or s.get("ok")]
    return {
        "request": request,
        "local_count": local_count,
        "external_ok": ok_sources,
        "results": deduped,
    }

def main() -> None:
    all_out = {}
    for area in AREAS:
        text = f"ايجار مكتب في {area} بحدود ٢٠٠"
        t0 = time.time()
        print(f"=== بحث: {text} ===", flush=True)
        out = run_search(text)
        req = out["request"]
        print(f"  فهم: عملية={req.transaction} نوع={req.property_type} مناطق={req.areas} محافظات={req.governorates} ميزانية={req.budget}", flush=True)
        print(f"  محلي={out['local_count']} مصادر خارجية ناجحة={len(out['external_ok'])} مدة={time.time()-t0:.0f}s", flush=True)
        rows = []
        for r in out["results"]:
            l = r.listing
            rows.append({
                "title": l.summary[:90],
                "transaction": l.transaction,
                "area": l.area,
                "governorate": l.governorate,
                "price": l.price,
                "price_text": l.price_text,
                "space": l.space,
                "source": l.source,
                "url": l.original_url,
                "label": r.valuation_label,
                "deal": round(r.deal_score, 2),
                "conf": round(r.confidence, 2),
                "match": round(r.match_score, 2),
                "market_median": r.market_median,
            })
        print(f"  نتائج مرتبة: {len(rows)}", flush=True)
        for i, row in enumerate(rows[:12], 1):
            print(f"   {i}. [{row['source']}] {row['title']} | {row['price_text']} | {row['area']}/{row['governorate']} | {row['label']} | deal={row['deal']}", flush=True)
        all_out[area] = {"request": {
            "transaction": req.transaction, "property_type": req.property_type,
            "areas": req.areas, "governorates": req.governorates, "budget": req.budget,
        }, "local_count": out["local_count"], "external_ok": out["external_ok"], "rows": rows}
        with open("data/office_area_compare.json", "w", encoding="utf-8") as f:
            json.dump(all_out, f, ensure_ascii=False, indent=2)
    print("== تم حفظ data/office_area_compare.json ==", flush=True)

if __name__ == "__main__":
    main()
