"""توليد تقرير PDF عربي كامل لتقييم بيت الصليبيخات (300م، قديم، ملاصق للمسجد).

المقارنات + الوسيط + التوصيات، مع صفحة توصيات العميل وجدول «المصادر والأدلة».

    python scripts/generate_sulaibikhat_pdf.py

يولّد في reports/: تقرير-بيت-الصليبيخات.pdf
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

DEFAULT_TEXT = "بيع بيت في صليبيخات 300 متر قديم ملاصق للمسجد شارع واحد بحدود 160 الف"


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

    # توصيات العميل مبنية من نتائج التقرير الفعلية + تحليل الصفقة
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
    recs.append("مطابقة إعلان AF-100 (الصليبيخات ق2 ش1 — 300م قديم بلا سعر معلن): قد يكون هو نفس البيت المعني — اطلب رقم القطعة والمنزل الرسمي للتأكيد.")
    recs.append("تحقق من الوثيقة (حكومي أم حرة) وقيود البناء بجوار المسجد — أهم نقطة تُخصم من السعر.")
    recs.append("تقديم 160 ألف والتفاوض حتى 170-175: وسيط المنطقة لهذه الفئة (قديم/مقسوم) يقارب 190 ألفًا، فالمطلوب 180 مقبول لكنه قابل للخصم.")
    recs.append("تأكيد الرسم الرسمي للأرض عبر رابط PACI في قسم المصادر (منزل 42 — gis.paci.gov.kw) قبل إتمام أي صفقة.")
    recs.append("استشر مختص ترميم لتقدير تكلفة إعادة التأهيل — الفرق بين الـ 160 المطلوب والقيمة بعد الترميم هو هامش الصفقة الحقيقي.")

    title = "تقرير تقييم بيت — الصليبيخات (300م)"
    pdf_bytes = build_pdf(report, title=title, client_recommendations=recs)
    out_path = os.path.join(out_dir, "تقرير-بيت-الصليبيخات.pdf")
    try:
        with open(out_path, "wb") as f:
            f.write(pdf_bytes)
    except PermissionError:
        # الملف مفتوح في عارض PDF عند المستخدم — احفظ بجانبه باسم بديل بلا كسر التشغيل
        import time
        alt = os.path.join(out_dir, f"تقرير-بيت-الصليبيخات-جديد.pdf")
        with open(alt, "wb") as f:
            f.write(pdf_bytes)
        out_path = alt
        print("ملف التقرير مقفول (مفتوح في عارض) — حُفظ الاسم البديل بدلًا منه", flush=True)
    print(f"PDF saved: {out_path} ({len(pdf_bytes)} bytes)", flush=True)
    print(f"Results in report: {len(results)}", flush=True)
    print(f"Summary: {(report.get('summary') or '')[:120]}", flush=True)
    src = report.get("sourceStatus") or []
    print(f"Sources ok: {sum(1 for s in src if s.get('status') == 'success')}/{len(src)}", flush=True)


if __name__ == "__main__":
    main()
