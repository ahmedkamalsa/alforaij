"""توليد تقريري PDF (إنجليزي + عربي بتوصيات العميل) من أي بحث.

أمر واحد لتحديث التقرير بعد كل بحث:
    python scripts/generate_office_pdf.py "نص البحث"
    python scripts/generate_office_pdf.py                       # البحث الافتراضي (مكاتب حولي/العاصمة)

يولّد في reports/:
    office-rent-hawally-capital.pdf      — النسخة الأساسية
    تقرير-مكاتب-حولي-العاصمة.pdf         — عنوان عربي + صفحة توصيات العميل
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.request_parser import parse_request
from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import search_external_sources
from backend.services.matching import top_matches
from backend.services.valuation import enrich_rankings
from backend.services.deduplication import deduplicate_ranked
from backend.services.report_generator import build_report
from backend.services.pdf_report import build_pdf
from backend.main import _default_sale_when_unspecified, _filter_listings_by_explicit_location

DEFAULT_TEXT = "يبي ايجار مكتب بالعاصمة او حولي شي رخيص بحدود ٢٠٠"


def main() -> None:
    text = " ".join(sys.argv[1:]).strip() or DEFAULT_TEXT
    print(f"بحث: {text}", flush=True)

    request = parse_request(text)
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

    try:
        from backend.services.ai_evaluator import generate_professional_analysis
        ai_insights = generate_professional_analysis(request, deduped, external_statuses)
    except Exception as exc:
        print(f"AI insights fallback: {exc}", flush=True)
        ai_insights = {}

    report = build_report(
        request,
        deduped,
        local_count,
        external_statuses,
        ai_insights,
        include_local_source=True,
    )

    out_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(out_dir, exist_ok=True)

    # ---- النسخة الأولى: اسم إنجليزي (افتراضي) ----
    pdf_bytes = build_pdf(report)
    out_path = os.path.join(out_dir, "office-rent-hawally-capital.pdf")
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"PDF saved: {out_path} ({len(pdf_bytes)} bytes)", flush=True)

    # ---- النسخة الثانية: عنوان عربي + اسم ملف عربي + صفحة توصيات العميل ----
    # التوصيات تُبنى من نتائج التقرير (قواميس) وليس من كائنات RankedListing
    results = report.get("results") or []
    recs = []
    for i, item in enumerate(results[:5], start=1):
        area = item.get("area") or "غير محددة"
        price = item.get("priceText") or f"{item.get('price')} د.ك"
        url = item.get("originalUrl") or ""
        line = f"الإعلان {item.get('code') or i} في {area} — {price}"
        if url:
            line += f" — الرابط: {url}"
        recs.append(line)
    recs.append("تواصل فورًا مع أصحاب الإعلانات الأعلى توصية قبل انتهاء العروض (المكاتب الرخيصة تُستأجر بسرعة).")
    recs.append("اطلب معاينة فعلية للمكتب وطابق المساحة والتجهيزات المذكورة قبل دفع أي تأمين.")
    recs.append("تفاوض على سعر الإيجار مستندًا إلى وسيط المقارنات في المنطقة المذكور بجدول التقرير.")
    recs.append("راجع العقد: مدة الإيجار، بند التجديد، وتكلفة الخدمات/الصيانة قبل التوقيع.")

    # اسم ثابت حتى يبقى رابط المدير مستقرًا بعد كل تحديث
    title = "تقرير تقييم إيجار المكاتب — حولي والعاصمة"
    pdf2 = build_pdf(report, title=title, client_recommendations=recs)
    out2 = os.path.join(out_dir, "تقرير-مكاتب-حولي-العاصمة.pdf")
    with open(out2, "wb") as f:
        f.write(pdf2)
    print(f"PDF v2 saved: {out2} ({len(pdf2)} bytes)", flush=True)
    print(f"Results in report: {len(results)}", flush=True)
    print(f"Summary: {(report.get('summary') or '')[:120]}", flush=True)
    src = report.get("sourceStatus") or []
    print(f"Sources ok: {sum(1 for s in src if s.get('status') == 'success')}/{len(src)}", flush=True)


if __name__ == "__main__":
    main()
