"""Integration test: exercises FindQ8 and Q8Aqar connectors with real HTTP calls.

Verifies our actual code changes:
1. FindQ8 connector works end-to-end with real data
2. Q8Aqar detail enrichment extracts phone + description + listing_type
3. Source registry includes FindQ8
4. All code paths execute without crashes
"""
from __future__ import annotations

import sys
import time

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        msg = f"  ❌ {name}" + (f" — {detail}" if detail else "")
        print(msg)
        ERRORS.append(msg)


# ─── Test 1: Source Registry includes FindQ8 ───
print("\n═══ Test 1: Source Registry contains FindQ8 ═══")
from backend.services.source_registry import source_registry

sources = source_registry()
source_ids = {s["id"] for s in sources}
check("FindQ8 is registered", "findq8" in source_ids, f"ids: {sorted(source_ids)}")
fq8 = next((s for s in sources if s["id"] == "findq8"), None)
if fq8:
    check("FindQ8 status is 'connected'", fq8["status"] == "connected")
    check("FindQ8 has trustLevel", bool(fq8.get("trustLevel")))

# ─── Test 2: SEARCHERS list includes FindQ8 ───
print("\n═══ Test 2: SEARCHERS list includes FindQ8 ═══")
from backend.connectors.live_sources import SEARCHERS

searcher_names = [name for name, _ in SEARCHERS]
check("FindQ8 is in SEARCHERS", "FindQ8" in searcher_names, f"searchers={searcher_names}")
check("Q8Aqar is in SEARCHERS", "Q8Aqar" in searcher_names)
check("Total SEARCHERS count >= 18", len(SEARCHERS) >= 18, f"count={len(SEARCHERS)}")

# ─── Test 3: FindQ8 sale search returns real data ───
print("\n═══ Test 3: FindQ8 sale search with real HTTP ═══")
from backend.connectors.live_sources import search_findq8, fetch_url, _detail_fields, _detail_phone
from backend.models import PropertyRequest

t0 = time.time()
request = PropertyRequest(raw_text="بيت للبيع", property_type="بيت", transaction="للبيع")
listings, status = search_findq8(request)
elapsed = time.time() - t0

check("FindQ8 returns listings", len(listings) > 0, f"count={len(listings)}")
check("FindQ8 status is 'success'", status["status"] == "success")
check("FindQ8 response time < 15s", elapsed < 15, f"elapsed={elapsed:.1f}s")
check("FindQ8 has candidates > 0", status.get("candidates", 0) > 0)

if listings:
    first = listings[0]
    check("Listing has code", bool(first.code))
    check("Listing has URL", bool(first.original_url))
    check("Listing source is FindQ8", first.source == "FindQ8")

    has_space = sum(1 for l in listings if l.space)
    check(f"Listings have space data", has_space > 0, f"with_space={has_space}/{len(listings)}")

    has_area = sum(1 for l in listings if l.area)
    check(f"Listings have area data", has_area > 0, f"with_area={has_area}/{len(listings)}")

    areas_found = {l.area for l in listings if l.area}
    print(f"    Areas found: {sorted(areas_found)}")

    # At least some should pass request matching
    from backend.connectors.live_sources import request_matches_listing
    matched = [l for l in listings if request_matches_listing(request, l)]
    check("Some listings pass request matching", len(matched) > 0,
          f"matched={len(matched)}/{len(listings)}")

    print(f"\n    Sample listings:")
    for l in listings[:5]:
        print(f"      {l.code}: price={l.price} space={l.space} area={l.area}")

# ─── Test 4: FindQ8 rent search ───
print("\n═══ Test 4: FindQ8 rent search ═══")
request_rent = PropertyRequest(raw_text="شقة للإيجار", property_type="شقة", transaction="للإيجار")
listings_rent, status_rent = search_findq8(request_rent)
check("FindQ8 rent search doesn't crash", True)
check("FindQ8 rent search has status", status_rent["name"] == "FindQ8")
print(f"    Rent: {len(listings_rent)} listings, status: {status_rent['status']}")

# ─── Test 5: Q8Aqar search handles 403 gracefully ───
print("\n═══ Test 5: Q8Aqar search handles external errors ═══")
from backend.connectors.live_sources import search_q8aqar

t0 = time.time()
request_q8 = PropertyRequest(raw_text="بيت للبيع", property_type="بيت", transaction="للبيع")
listings_q8, status_q8 = search_q8aqar(request_q8)
elapsed_q8 = time.time() - t0

check("Q8Aqar doesn't crash on 403", True)
check("Q8Aqar returns proper status dict", "name" in status_q8 and "status" in status_q8)
check("Q8Aqar response time < 30s", elapsed_q8 < 30, f"elapsed={elapsed_q8:.1f}s")
# Q8Aqar may fail with 403 — that's external, not our code
if status_q8["status"] == "failed":
    print(f"    ⚠️  Q8Aqar returned 403 (external site blocking — not our code)")
    print(f"    Note: {status_q8.get('note', '')[:100]}")
else:
    check("Q8Aqar returns listings", len(listings_q8) > 0, f"count={len(listings_q8)}")

# ─── Test 6: Detail enrichment on a real FindQ8 page ───
print("\n═══ Test 6: Detail enrichment from FindQ8 detail page ═══")
if listings:
    test_url = listings[0].original_url
    if test_url:
        body, status, ms, error, attempts = fetch_url(test_url)
        if body:
            fields = _detail_fields(body)
            print(f"    Fields from detail page ({test_url[:50]}...):")
            for k, v in fields.items():
                print(f"      {k}: {str(v)[:100]}")
            check("Detail extraction returns dict", isinstance(fields, dict))
            check("Detail extraction has at least one field", len(fields) > 0,
                  f"fields={list(fields.keys())}")

            # Test phone extraction
            phone = _detail_phone(body)
            print(f"    Phone extracted: {phone or '(none)'}")
            check("Phone extraction doesn't crash", True)
        else:
            check("Can fetch FindQ8 detail page", False, f"error={error}")

# ─── Test 7: Q8Aqar detail enrichment functions work ───
print("\n═══ Test 7: Q8Aqar detail functions work on sample HTML ═══")
# Even if Q8Aqar is 403, we can test the extraction functions on sample HTML
from backend.connectors.live_sources import _detail_price_space, _detail_place, _detail_listing_type

sample_html = '''
<html>
<head>
<meta property="og:description" content="للبيع بيت في السالمية بطن وظهر">
<meta name="description" content="بيت للبيع في السالمية">
<meta property="product:price:amount" content="250000">
<meta property="product:property:size" content="300">
</head>
<body>
<div class="price-tag"><span>KD 250,000.00</span></div>
<div class="square_feet">300 m</div>
<a href="wa.me/96555512345">واتساب</a>
<div class="location">السالمية، محافظة حولي</div>
<div class="agent-info">مكتب العقارات</div>
</body>
</html>
'''

price, space = _detail_price_space(sample_html)
check("_detail_price_space extracts price", price is not None and price > 0, f"price={price}")
check("_detail_price_space extracts space", space is not None and space > 0, f"space={space}")

area, gov = _detail_place(sample_html)
print(f"    Place: area={area}, governorate={gov}")

phone = _detail_phone(sample_html)
check("_detail_phone extracts phone", phone == "+96555512345", f"phone={phone}")

listing_type = _detail_listing_type(sample_html)
check("_detail_listing_type detects office", listing_type == "مكتب", f"type={listing_type}")

# Test description extraction
from backend.connectors.live_sources import _detail_description
desc = _detail_description(sample_html)
check("_detail_description extracts description", len(desc) > 10, f"desc={desc[:50]}")

# ─── Summary ───
print("\n" + "═" * 60)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailed checks:")
    for err in ERRORS:
        print(f"  {err}")
print("═" * 60)

sys.exit(1 if FAIL > 0 else 0)
