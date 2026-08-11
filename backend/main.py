from __future__ import annotations

import json
import logging
import mimetypes
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

from backend.config import FRONTEND_DIR, HOST, PORT, AGENT_ROUTER_API_KEY
from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import search_external_sources
from backend.services.deduplication import deduplicate_ranked
from backend.services.matching import top_matches
from backend.services.report_generator import build_report
from backend.services.request_parser import parse_request
from backend.services.source_registry import source_registry
from backend.services.supabase_store import is_configured as supabase_is_configured
from backend.services.supabase_store import (
    persist_analysis,
    save_valuation_request,
    save_client_property_request,
    supabase_data_summary,
)
from backend.services.valuation import enrich_rankings


from backend.services.ai_evaluator import generate_professional_analysis

# ذاكرة مؤقتة للفرص (تُحدَّث أول بأول): تُبنى عند أول طلب وتُعاد لفترة قصيرة
import threading as _threading

_OPPORTUNITIES_LOCK = _threading.Lock()
_OPPORTUNITIES_CACHE: dict | None = None
_OPPORTUNITIES_PREVIOUS: dict | None = None  # اللقطة السابقة للمقارنة (تنبيهات واتساب)
_OPPORTUNITIES_CACHE_AT = 0.0
_OPPORTUNITIES_TTL_SECONDS = 300

# ---- بثّ تقدم البحث الحي: يُملأ أثناء تشغيل /api/analyze ويُقرأ من الواجهة بالاقتراع ----
_ANALYZE_PROGRESS: dict[str, dict] = {}
_ANALYZE_PROGRESS_LOCK = _threading.Lock()
_ANALYZE_PROGRESS_TTL = 900  # ثوانٍ — تُنظَّف الوظائف القديمة تلقائيًا

_PROGRESS_SOURCE_LABELS = {
    "running": "جارٍ البحث",
    "success": "نجح",
    "fallback": "عبر بديل",
    "failed": "فشل",
    "no_results": "لا نتائج",
    "no_data": "لا بيانات",
    "page_reachable": "الصفحة متاحة",
}


def _progress_source_label(status: dict) -> str:
    return _PROGRESS_SOURCE_LABELS.get(str(status.get("status") or ""), str(status.get("status") or ""))


def _progress_push(job_id: str, stage: str, message: str, **data) -> None:
    """تسجيل حدث تقدم لوظيفة تحليل حية (يُهمَل إن لم يكن هناك jobId)."""
    if not job_id:
        return
    now = time.time()
    with _ANALYZE_PROGRESS_LOCK:
        for old in [
            k for k, v in _ANALYZE_PROGRESS.items()
            if now - v.get("startedAt", 0) > _ANALYZE_PROGRESS_TTL
        ]:
            _ANALYZE_PROGRESS.pop(old, None)
        job = _ANALYZE_PROGRESS.get(job_id)
        if job is None:
            job = {"jobId": job_id, "startedAt": now, "done": False, "stage": "", "events": []}
            _ANALYZE_PROGRESS[job_id] = job
        job["stage"] = stage
        job["events"].append({"t": now, "stage": stage, "message": message, **data})
        job["events"] = job["events"][-200:]
        if stage == "done":
            job["done"] = True
            job["finishedAt"] = now


def _progress_source_event(job_id: str, name: str, st: dict) -> None:
    """حدث مصدر فردي: يبثّ الحالة ويُحدّث عدّاد الإنجاز الكلي (منتهي/إجمالي)."""
    if not job_id:
        return
    _progress_push(
        job_id, "source", f"{name} — {_progress_source_label(st)} ({st.get('records', 0)} إعلان)",
        name=name, status=st.get("status"), records=st.get("records") or 0,
    )
    with _ANALYZE_PROGRESS_LOCK:
        job = _ANALYZE_PROGRESS.get(job_id)
        if job is None:
            return
        if st.get("status") == "running":
            job["totalSources"] = int(job.get("totalSources", 0)) + 1
        else:
            job["doneSources"] = int(job.get("doneSources", 0)) + 1
            # إجمالي الإعلانات المُجمّعة حتى اللحظة من المصادر المنتهية
            job["collectedRecords"] = int(job.get("collectedRecords", 0)) + int(st.get("records") or 0)


def _dashboard_record(listing) -> dict:
    return {
        "code": listing.code,
        "transaction": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "propertyType": listing.property_type,
        "detailClass": listing.detail_class,
        "price": listing.price,
        "priceText": listing.price_text,
        "space": listing.space,
        "listingMode": listing.listing_mode,
        "publishedDate": listing.published_date,
        "source": listing.source or "الفريج",
        "summary": listing.summary,
        "features": listing.features,
        "originalUrl": listing.original_url,
    }


def _area_governorate_map(listings) -> dict[str, str]:
    mapping = {}
    for row in listings:
        if row.area and row.governorate and row.area not in mapping:
            mapping[row.area] = row.governorate
    return mapping


_GOVERNORATE_ALIASES = {
    "الأحمدي": "محافظة الأحمدي",
    "احمدي": "محافظة الأحمدي",
    "الاحمدي": "محافظة الأحمدي",
    "محافظة الاحمدي": "محافظة الأحمدي",
    "حولي": "محافظة حولي",
    "الجهراء": "محافظة الجهراء",
    "العاصمة": "محافظة العاصمة",
    "الفروانية": "محافظة الفروانية",
    "مبارك الكبير": "محافظة مبارك الكبير",
}


def _normalize_governorate_name(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if clean in _GOVERNORATE_ALIASES:
        return _GOVERNORATE_ALIASES[clean]
    if clean.startswith("محافظة "):
        return clean
    return clean


def _normalize_dashboard_place(record: dict, area_map: dict[str, str]) -> None:
    area = str(record.get("area") or "").strip()
    governorate = str(record.get("governorate") or "").strip()
    if governorate:
        record["governorate"] = _normalize_governorate_name(governorate)
    if not record.get("governorate") and area in area_map:
        record["governorate"] = area_map[area]
    elif not record.get("governorate") and area in _GOVERNORATE_ALIASES:
        record["governorate"] = _normalize_governorate_name(area)
        record["area"] = ""


def _platform_match(source: str, selected: set[str]) -> bool:
    if not selected:
        return True
    normalized = str(source or "")
    aliases = {
        "الفريج": {"الفريج", "alforaij", "Alforaij", "الفريج المحلي"},
        "alforaij": {"الفريج", "alforaij", "Alforaij", "الفريج المحلي"},
        "بوشملان": {"بوشملان", "Bu3qar", "بوعقار", "السوق المباشر"},
        "Bu3qar": {"بوشملان", "Bu3qar", "بوعقار"},
        "الحسبة": {"الحسبة", "Alhisba", "الحسبة - الصفقات المسجلة العامة"},
    }
    expanded: set[str] = set()
    for name in selected:
        expanded.add(name)
        expanded.update(aliases.get(name, set()))
    return any(name == normalized or name in normalized or normalized in name for name in expanded)


def _is_local_platform_selected(selected: set[str]) -> bool:
    local_names = {"الفريج", "alforaij", "Alforaij", "الفريج المحلي"}
    return bool(selected & local_names)


def _market_row_to_record(row: dict) -> dict:
    """تحويل صف market_listings (الحصاد المتراكم من كل المواقع) إلى سجل لوحة."""
    return {
        "code": str(row.get("code") or ""),
        "transaction": row.get("transaction") or "",
        "governorate": row.get("governorate") or "",
        "area": row.get("area") or "",
        "propertyType": row.get("property_type") or "",
        "detailClass": row.get("detail_class") or "خارجي",
        "price": row.get("price"),
        "priceText": row.get("price_text") or "",
        "space": row.get("space"),
        "listingMode": row.get("listing_mode") or "خارجي",
        "publishedDate": row.get("published_date") or "",
        "source": row.get("source") or "السوق الخارجي",
        "summary": row.get("summary") or "",
        "features": row.get("features") or "",
        "originalUrl": row.get("original_url") or "",
        "fetchedAt": str(row.get("fetched_at") or "")[:19],
        "harvested": True,
    }


def _market_ad_row_to_record(row: dict) -> dict:
    """تحويل صف market_ads (إعلانات حية محفوظة مثل بوشملان) إلى سجل لوحة."""
    raw_source = str(row.get("source_name") or "السوق المباشر")
    code = str(row.get("source_listing_id") or "") or str(row.get("id") or "")
    return {
        "code": f"LIVE-{raw_source}-{code}",
        "transaction": "للإيجار" if "rent" in str(row.get("source_url") or "").lower() else "للبيع",
        "governorate": "",
        "area": row.get("region") or "",
        "propertyType": row.get("property_type") or "",
        "detailClass": "خارجي مباشر",
        "price": row.get("asking_price"),
        "priceText": f"{row.get('asking_price') or ''} د.ك" if row.get("asking_price") is not None else "",
        "space": row.get("land_area_m2") or row.get("built_up_area_m2"),
        "listingMode": "خارجي مباشر",
        "publishedDate": "",
        "source": raw_source,
        "summary": row.get("title") or "",
        "features": row.get("title") or "",
        "originalUrl": row.get("source_url") or "",
        "fetchedAt": str(row.get("fetched_at") or "")[:19],
        "harvested": True,
    }


def _dashboard_market_records(selected: set[str], area_map: dict[str, str]) -> list[dict]:
    """سجلات السوق الخارجية: الحصاد المتراكم من القاعدة (market_listings) هو المصدر
    الأساسي بدل الفحص الحي الصغير — فكل إعلان موثق برابطه الأصلي ووقت جليه، وتتسق
    الأرقام مع إجمالي القاعدة. إعلانات market_ads الحية تُدمج بلا تكرار، والفحص الحي
    يُستخدم كسقوط آمن فقط عند غياب القاعدة."""
    market_names = {"السوق المباشر", "بوشملان", "OpenSooq", "Mourjan", "Q8Aqar", "Sakan", "Waseet", "4Sale", "Bu3qar", "Aqarat", "NabdAqar", "Yebtah"}
    records: list[dict] = []
    known_codes: set[str] = set()

    def _accept(raw_source: str) -> bool:
        return not selected or _platform_match(raw_source, selected) or "السوق المباشر" in selected

    # 1) الحصاد المتراكم من market_listings (المصدر الأساسي — كل المواقع الموثقة)
    harvested = []
    try:
        from backend.services.supabase_store import fetch_market_listings
        harvested = fetch_market_listings(limit=2000) or []
    except Exception as exc:
        logger.warning("Dashboard harvested market records skipped: %s", exc)
    for row in harvested:
        raw_source = str(row.get("source") or "السوق المباشر")
        if not _accept(raw_source):
            continue
        record = _market_row_to_record(row)
        _normalize_dashboard_place(record, area_map)
        records.append(record)
        if record["code"]:
            known_codes.add(record["code"])

    # 2) إعلانات market_ads الحية المحفوظة (بوشملان وغيرها) — بلا تكرار مع الحصاد
    try:
        from backend.services.supabase_store import _fetch_rows, SUPABASE_URL
        live_rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/market_ads?select=*&limit=2000") or []
        for row in live_rows:
            raw_source = str(row.get("source_name") or "السوق المباشر")
            if not _accept(raw_source):
                continue
            record = _market_ad_row_to_record(row)
            _normalize_dashboard_place(record, area_map)
            if record["code"] in known_codes:
                continue
            records.append(record)
            if record["code"]:
                known_codes.add(record["code"])
    except Exception as exc:
        logger.warning("Dashboard live saved market records skipped: %s", exc)

    # 3) الفحص الحي — سقوط آمن فقط عند غياب القاعدة (أو عند طلب منصة بعينها غير محصودة)
    if not harvested and (not selected or selected & market_names):
        try:
            from backend.connectors.market_ads import search as search_market_ads
            from backend.models import PropertyRequest

            listings, _status = search_market_ads(PropertyRequest(raw_text=""))
        except Exception as exc:
            logger.warning("Dashboard live market records skipped: %s", exc)
            listings = []
        for listing in listings:
            raw_source = str((listing.raw or {}).get("source_name") or listing.source or "السوق المباشر")
            if not _accept(raw_source):
                continue
            code = str(listing.code or "")
            if code and code in known_codes:
                continue
            record = _dashboard_record(listing)
            _normalize_dashboard_place(record, area_map)
            record["source"] = raw_source
            records.append(record)
            if code:
                known_codes.add(code)
    if not selected or _platform_match("الحسبة - الصفقات المسجلة العامة", selected):
        try:
            from backend.connectors.official_data import load_transactions, _transaction_listing

            for index, row in enumerate(load_transactions()):
                if not str(row.get("source") or "").startswith("الحسبة"):
                    continue
                listing = _transaction_listing(row, index)
                record = _dashboard_record(listing)
                _normalize_dashboard_place(record, area_map)
                record["source"] = "الحسبة - الصفقات المسجلة العامة"
                record["listingMode"] = "مرجع سعري"
                record["summary"] = "صفقة مسجلة مرجعية للمقارنة وليست إعلانًا متاحًا للبيع."
                records.append(record)
        except Exception as exc:
            logger.warning("Dashboard Alhisba reference records skipped: %s", exc)
    return records


def _record_from_opportunity(item: dict, area_map: dict[str, str]) -> dict:
    record = {
        "code": item.get("code"),
        "transaction": item.get("transaction") or ("للإيجار" if item.get("rental") else "للبيع"),
        "governorate": item.get("governorate") or "",
        "area": item.get("area") or "",
        "propertyType": item.get("propertyType") or "",
        "detailClass": item.get("propertyType") or "",
        "price": item.get("price"),
        "priceText": item.get("priceText"),
        "space": item.get("space"),
        "listingMode": item.get("listingType") or "فرصة",
        "publishedDate": item.get("publishedDate"),
        "source": item.get("source") or "فرصة محفوظة",
        "summary": item.get("summary") or item.get("valuationReason") or "",
        "features": item.get("valuationReason") or "",
        "originalUrl": item.get("url") or "",
        "recordKind": "opportunity_snapshot",
        "opportunityScore": item.get("score"),
        "opportunityLabel": item.get("valuationLabel"),
        "opportunityReason": item.get("valuationReason"),
        "opportunityComparablesCount": item.get("comparablesCount"),
        "opportunityEvidenceCount": item.get("evidenceCount"),
        "opportunityClientsCount": item.get("clientsCount"),
    }
    _normalize_dashboard_place(record, area_map)
    return record


def _flat_dashboard_opportunities(selected: set[str], include_local: bool, area_map: dict[str, str]) -> tuple[list[dict], dict[str, dict], dict]:
    try:
        from backend.services.supabase_store import fetch_latest_opportunities

        snapshot = fetch_latest_opportunities()
    except Exception as exc:
        logger.warning("Dashboard opportunities skipped: %s", exc)
        snapshot = None
    if not snapshot:
        return [], {}, {}

    by_code: dict[str, dict] = {}
    for tier in (snapshot.get("tiers") or {}).values():
        for item in tier.get("items") or []:
            code = str(item.get("code") or "")
            if not code or code in by_code:
                continue
            source = str(item.get("source") or "")
            is_local = _platform_match(source, {"الفريج"}) or source in {"الفريج", "alforaij"}
            if not include_local and is_local:
                continue
            external_selected = selected - {"الفريج", "alforaij", "Alforaij", "الفريج المحلي", "__all"}
            if selected and "__all" not in selected:
                if is_local and not _is_local_platform_selected(selected):
                    continue
                if external_selected and not _platform_match(source, external_selected):
                    continue
                if not is_local and not external_selected:
                    continue
            clean = dict(item)
            _normalize_dashboard_place(clean, area_map)
            clean["evidenceCount"] = len(clean.get("evidence") or [])
            clean["clientsCount"] = len(clean.get("clients") or [])
            by_code[code] = clean
    return list(by_code.values()), by_code, snapshot


def _dashboard_summary(listings, selected_platforms: set[str] | None = None, include_local: bool = True) -> dict:
    selected_platforms = selected_platforms or set()
    area_map = _area_governorate_map(listings)
    local_records = [_dashboard_record(row) for row in listings] if include_local else []
    for record in local_records:
        _normalize_dashboard_place(record, area_map)
    if selected_platforms and "__all" not in selected_platforms and not _is_local_platform_selected(selected_platforms):
        local_records = []
    external_platforms = selected_platforms - {"الفريج", "alforaij", "Alforaij", "الفريج المحلي", "__all"}
    if not selected_platforms or "__all" in selected_platforms:
        market_records = _dashboard_market_records(set(), area_map)
    elif external_platforms:
        market_records = _dashboard_market_records(external_platforms, area_map)
    else:
        market_records = []
    records = local_records + market_records
    raw_count = len(records)
    opportunity_items, opportunities_by_code, opportunity_snapshot = _flat_dashboard_opportunities(selected_platforms, include_local, area_map)
    existing_codes = {str(record.get("code") or "") for record in records}
    for record in records:
        opp = opportunities_by_code.get(str(record.get("code") or ""))
        if not opp:
            continue
        record["opportunityScore"] = opp.get("score")
        record["opportunityLabel"] = opp.get("valuationLabel")
        record["opportunityReason"] = opp.get("valuationReason")
        record["opportunityComparablesCount"] = opp.get("comparablesCount")
        record["opportunityEvidenceCount"] = opp.get("evidenceCount")
        record["opportunityClientsCount"] = opp.get("clientsCount")
    for opp in opportunity_items:
        code = str(opp.get("code") or "")
        if code and code not in existing_codes:
            records.append(_record_from_opportunity(opp, area_map))
            existing_codes.add(code)
    return {
        "count": len(records),
        "rawRecordCount": raw_count,
        "records": records,
        "opportunities": {
            "count": len(opportunity_items),
            "displayedCount": min(len(opportunity_items), 60),
            "totalListings": opportunity_snapshot.get("totalListings") or 0,
            "totalScored": opportunity_snapshot.get("totalScored") or len(opportunity_items),
            "generatedAt": opportunity_snapshot.get("generatedAt") or opportunity_snapshot.get("generatedDate"),
            "items": opportunity_items[:60],
            "calculation": "الفرصة = إعلان عرض بسعر صالح تم تقييمه في لقطة الفرص. تعرض اللوحة أعلى الفرص فقط، بينما totalScored يوضح إجمالي الإعلانات التي دخلت التقييم. الدرجة = 65% جاذبية السعر + 35% الثقة، والثقة مبنية على مصداقية المصدر وعدد المقارنات/الأدلة.",
        },
        "platforms": sorted({row["source"] for row in records if row["source"]}),
        "selectedPlatforms": sorted(selected_platforms),
        "options": {
            "governorates": sorted({row["governorate"] for row in records if row["governorate"]}),
            "areas": sorted({row["area"] for row in records if row["area"]}),
            "propertyTypes": sorted({row["propertyType"] for row in records if row["propertyType"]}),
            "listingModes": sorted({row["listingMode"] for row in records if row["listingMode"]}),
        },
        "metrics": [
            {"key": "movement", "label": "حركة الدلال"},
            {"key": "saleOffers", "label": "عروض للبيع"},
            {"key": "buyRequests", "label": "طلبات شراء"},
            {"key": "rentOffers", "label": "عروض الإيجار"},
            {"key": "rentRequests", "label": "طلبات الإيجار"},
        ],
    }


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _default_sale_when_unspecified(request) -> None:
    text = f"{request.raw_text or ''}"
    if request.transaction:
        return
    rental_words = ("إيجار", "ايجار", "للايجار", "للإيجار", "استأجر")
    if request.property_type and request.areas and not any(word in text for word in rental_words):
        request.transaction = "للبيع"


def _apply_filter_overrides(request, filters: dict) -> None:
    if not isinstance(filters, dict):
        return
    transaction = str(filters.get("transaction") or "").strip()
    property_type = str(filters.get("propertyType") or "").strip()
    areas = str(filters.get("areas") or filters.get("area") or "").strip()
    governorate = str(filters.get("governorate") or "").strip()
    if transaction:
        request.transaction = transaction
    if property_type:
        request.property_type = property_type
    if governorate:
        request.governorates = [part.strip() for part in re.split(r"[،,|]+", governorate) if part.strip()]
    if areas:
        request.areas = [part.strip() for part in re.split(r"[،,|]+", areas) if part.strip()]

    def number(name: str):
        value = filters.get(name)
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "").strip())
        except ValueError:
            return None

    min_area = number("minArea")
    max_area = number("maxArea")
    budget = number("budget")
    rent_budget = number("rentBudget")
    bedrooms = number("bedrooms")
    if min_area is not None:
        request.min_area = min_area
    if max_area is not None:
        request.max_area = max_area
    if budget is not None:
        request.budget = budget
    if rent_budget is not None:
        request.rent_budget = rent_budget
    if bedrooms is not None:
        request.bedrooms = int(bedrooms)


def _filter_listings_by_explicit_location(listings: list, request, filters: dict) -> list:
    if not isinstance(filters, dict):
        return listings
    area_filter = str(filters.get("areas") or filters.get("area") or "").strip()
    governorate_filter = str(filters.get("governorate") or "").strip()
    if area_filter and request.areas:
        allowed = set(request.areas)
        return [item for item in listings if item.area in allowed]
    if governorate_filter and request.governorates:
        allowed_govs = set(request.governorates)
        return [item for item in listings if item.governorate in allowed_govs]
    return listings


def _profit_opportunities(report: dict) -> dict:
    rows = []
    seen: set[tuple[str, str]] = set()
    sources = [
        *list(report.get("results") or []),
        *list((report.get("similarExternal") or {}).get("items") or []),
    ]
    for item in sources:
        for client in item.get("clients") or []:
            profit = client.get("potentialProfitKwd")
            if profit is None or profit <= 0:
                continue
            key = (str(item.get("code") or ""), str(client.get("phones") or ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "listingCode": item.get("code"),
                "listingSource": item.get("source"),
                "area": item.get("area"),
                "propertyType": item.get("propertyType") or item.get("detailClass"),
                "listingPrice": item.get("price"),
                "listingPriceText": item.get("priceText"),
                "clientSource": client.get("source"),
                "clientBudget": client.get("clientBudget"),
                "potentialProfitKwd": profit,
                "matchScore": client.get("matchScore"),
                "phones": client.get("phones"),
                "reason": client.get("profitReason"),
                "url": item.get("originalUrl") or item.get("url"),
            })
    rows.sort(key=lambda row: (row.get("potentialProfitKwd") or 0, row.get("matchScore") or 0), reverse=True)
    return {
        "count": len(rows),
        "totalPotentialProfitKwd": round(sum(row.get("potentialProfitKwd") or 0 for row in rows), 0),
        "note": (
            "هذه فرص مكسب مؤكدة حسابيًا: إعلان بيع + عميل/طلب شراء مطابق لنفس المنطقة + فرق إيجابي بين ميزانية العميل وسعر الإعلان."
            if rows
            else "لا توجد فرصة مكسب مؤكدة لنفس المنطقة الآن. أضف/استورد طلبات شراء لنفس المنطقة أو فعّل مصادر طلب شراء خارجية قابلة للقراءة."
        ),
        "items": rows[:10],
    }


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            # الإجمالي عبر كل المصادر: الفريج المحلي + حصاد المواقع الخارجية (market_listings)
            # + إعلانات السوق الحية (market_ads) — لا نكتفي بعدد الفريج المحلي وحده.
            listings = load_listings()
            data_summary = supabase_data_summary(len(listings))
            tables = (data_summary or {}).get("tables") or {}
            market_harvested = int((tables.get("market_listings") or {}).get("count") or 0)
            market_live = int((tables.get("market_ads") or {}).get("count") or 0)
            external_total = market_harvested + market_live
            by_source: list[dict] = []
            try:
                from backend.services.supabase_store import fetch_market_listing_source_counts
                by_source = fetch_market_listing_source_counts() or []
            except Exception as exc:
                logger.warning("Health bySource failed: %s", exc)
            json_response(self, {
                "status": "ok",
                "records": len(listings),
                "recordsMeaning": "إعلانات الفريج المحلية المحملة كخط أساس.",
                "totalRecords": len(listings) + external_total,
                "localRecords": len(listings),
                "externalRecords": external_total,
                "bySource": by_source,
                "supabase": supabase_is_configured(),
                "dataSummary": data_summary,
                "aiAnalysis": bool(AGENT_ROUTER_API_KEY),
            })
            return
        if path == "/api/sources":
            json_response(self, {"sources": source_registry()})
            return
        if path == "/api/search-options":
            # قوائم الاختيار الرسمية لحقول «اكتب أو اختر» في الخيارات المتقدمة
            # (نفس قوائم المحلل بالضبط حتى يطابق الاختيار المكتوب النية المفهومة)
            from backend.services.request_parser import GOVERNORATE_AREA_NAMES, KNOWN_AREAS, PROPERTY_TYPES
            json_response(self, {
                "areas": KNOWN_AREAS,
                "propertyTypes": list(PROPERTY_TYPES.keys()),
                "transactions": ["للبيع", "للإيجار", "مطلوب للشراء", "مطلوب للإيجار"],
                "governorates": sorted(GOVERNORATE_AREA_NAMES),
            })
            return
        if path == "/api/analyze/progress":
            # تقدم البحث الحي: الواجهة تقترع كل ~0.7 ثانية أثناء تشغيل POST /api/analyze
            params = parse_qs(urlparse(self.path).query)
            job_id = (params.get("job") or [""])[0]
            with _ANALYZE_PROGRESS_LOCK:
                job = _ANALYZE_PROGRESS.get(job_id)
            if job is None:
                json_response(self, {"error": "unknown job"}, status=404)
                return
            json_response(self, job)
            return
        if path == "/api/market-analytics":
            # تحليلات الحصاد المتراكم: كل موقع على حدة (عدد/مناطق/أسعار) من market_listings
            from backend.services.supabase_store import fetch_market_analytics
            try:
                json_response(self, fetch_market_analytics())
            except Exception as exc:
                logger.exception("Market analytics failed")
                json_response(self, {"error": "Market analytics failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/market-insights":
            # تحليلات السوق (الموجة 1): عائد الإيجار واتجاه سعر المتر لكل منطقة
            from backend.services.supabase_store import fetch_market_insights
            try:
                json_response(self, fetch_market_insights())
            except Exception as exc:
                logger.exception("Market insights failed")
                json_response(self, {"error": "Market insights failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/dashboard/summary":
            params = parse_qs(urlparse(self.path).query)
            selected = {
                item.strip()
                for raw in params.get("platform", [])
                for item in raw.split(",")
                if item.strip()
            }
            include_local = params.get("includeLocal", ["1"])[0] != "0"
            json_response(self, _dashboard_summary(load_listings(), selected_platforms=selected, include_local=include_local))
            return
        if path == "/api/update-notifications":
            from backend.services.update_notifications import load_update_notifications
            json_response(self, load_update_notifications())
            return
        if path == "/api/daily-agent/status":
            from backend.services.daily_update_agent import load_daily_agent_status
            json_response(self, load_daily_agent_status())
            return
        if path == "/api/official-reference-sources":
            from backend.services.official_source_agent import check_official_reference_sources
            json_response(self, check_official_reference_sources(timeout=8))
            return
        if path == "/api/opportunities":
            import time
            from backend.services.opportunities import build_opportunities
            from backend.services.supabase_store import fetch_latest_opportunities, save_opportunities

            params = parse_qs(urlparse(self.path).query)
            force_refresh = params.get("refresh", ["0"])[0] == "1"
            now = time.time()
            global _OPPORTUNITIES_CACHE, _OPPORTUNITIES_CACHE_AT, _OPPORTUNITIES_PREVIOUS
            stale = _OPPORTUNITIES_CACHE is None or now - _OPPORTUNITIES_CACHE_AT > _OPPORTUNITIES_TTL_SECONDS
            if not stale and not force_refresh:
                json_response(self, _OPPORTUNITIES_CACHE)
                return
            if not force_refresh:
                fallback = fetch_latest_opportunities()
                if fallback:
                    _OPPORTUNITIES_CACHE = fallback
                    _OPPORTUNITIES_CACHE_AT = time.time()
                    json_response(self, fallback)
                    return
            with _OPPORTUNITIES_LOCK:
                try:
                    # الصفحة تعتمد على الفرص الفعلية من كل المواقع: يُفحص المصادر الخارجية
                    # في كل إعادة بناء (كل 5 دقائق) حتى لا تقتصر الفرص على الفريج المحلي.
                    include_external = True
                    snapshot = build_opportunities(include_external=include_external)
                    if _OPPORTUNITIES_CACHE is not None and snapshot.get("generatedAt") != _OPPORTUNITIES_CACHE.get("generatedAt"):
                        _OPPORTUNITIES_PREVIOUS = _OPPORTUNITIES_CACHE
                    _OPPORTUNITIES_CACHE = snapshot
                    _OPPORTUNITIES_CACHE_AT = time.time()
                    try:
                        save_opportunities(snapshot)
                    except Exception as exc:
                        logger.warning("Supabase opportunities save skipped: %s", exc)
                except Exception as exc:
                    logger.exception("Opportunities build failed")
                    # احتياط: عرض آخر لقطة محفوظة في Supabase بدل فشل الطلب
                    fallback = fetch_latest_opportunities()
                    if fallback:
                        _OPPORTUNITIES_CACHE = fallback
                        _OPPORTUNITIES_CACHE_AT = time.time()
                        json_response(self, fallback)
                        return
                    json_response(self, {"error": "Opportunities build failed", "detail": str(exc)}, status=500)
                    return
            json_response(self, _OPPORTUNITIES_CACHE)
            return
        if path == "/api/opportunities/history":
            # أرشفة وتتبع أداء الفرص عبر اللقطات المحفوظة في Supabase (أقدم → أحدث)
            from backend.services.opportunities import build_history_series
            from backend.services.supabase_store import fetch_opportunity_snapshots
            try:
                snapshots = fetch_opportunity_snapshots(limit=100)
                snapshots.reverse()  # أقدم أولًا كما يتوقع build_history_series
                json_response(self, build_history_series(snapshots))
            except Exception as exc:
                logger.exception("Opportunities history build failed")
                json_response(self, {"error": "History build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/price-trends":
            # اتجاهات الأسعار الشهرية من جدول price_trends (يُملأ يوميًا من الحصاد)
            # — وسيط سعر المتر لكل منطقة/نوع عبر الأشهر لتغذية الرسوم الزمنية.
            from backend.services.supabase_store import fetch_price_trends
            params = parse_qs(urlparse(self.path).query)
            area = (params.get("area") or [""])[0]
            json_response(self, {
                "rows": fetch_price_trends(area=area or None, limit=2000),
                "tableOk": True,
            })
            return
        if path == "/api/market-matching":
            # العرض والطلب: التوفيق العملي بين طلبات «مطلوب للشراء/للإيجار» وأفضل الفرص المقيّمة
            from backend.services.opportunities import build_market_matching, build_opportunities
            from backend.services.supabase_store import fetch_latest_opportunities
            try:
                snapshot = _OPPORTUNITIES_CACHE
                if snapshot is None:
                    snapshot = fetch_latest_opportunities()
                if snapshot is None:
                    snapshot = build_opportunities(include_external=True)
                json_response(self, build_market_matching(snapshot))
            except Exception as exc:
                logger.exception("Market matching build failed")
                json_response(self, {"error": "Market matching build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/opportunity-delta":
            # ما الجديد وما حذف وما انخفض سعره بين آخر لقطتين + إرشاد التعامل مع كل حالة
            from backend.services.opportunities import build_opportunity_delta, build_opportunities
            try:
                current = _OPPORTUNITIES_CACHE
                previous = _OPPORTUNITIES_PREVIOUS
                if current is None:
                    current = build_opportunities(include_external=True)
                json_response(self, build_opportunity_delta(previous, current))
            except Exception as exc:
                logger.exception("Opportunity delta build failed")
                json_response(self, {"error": "Opportunity delta build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/weekly-digest":
            # الموجز الأسبوعي: أفضل 10 فرص بيع لكل عميل محتمل مع رسالة واتساب جاهزة
            from backend.services.opportunities import build_opportunities, build_weekly_digest
            try:
                snapshot = _OPPORTUNITIES_CACHE
                if snapshot is None:
                    snapshot = build_opportunities(include_external=True)
                json_response(self, build_weekly_digest(snapshot))
            except Exception as exc:
                logger.exception("Weekly digest build failed")
                json_response(self, {"error": "Weekly digest build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/whatsapp-alerts":
            # تنبيهات واتساب: مقارنة آخر لقطتين (الحالية مقابل السابقة) لكل عميل مطابق
            from backend.services.opportunities import build_whatsapp_alerts
            from backend.services.supabase_store import fetch_opportunity_snapshots

            def _generated(snap):
                # اللقطات في الذاكرة تستخدم generatedAt، وصفوف Supabase تستخدم generated_at
                return snap.get("generatedAt") or snap.get("generated_at") or ""

            try:
                snapshots = fetch_opportunity_snapshots(limit=3)
                previous = _OPPORTUNITIES_PREVIOUS
                current = _OPPORTUNITIES_CACHE
                if snapshots:
                    newest = snapshots[0]
                    current = current or newest
                    if len(snapshots) >= 2 and (not previous or _generated(previous) == _generated(current)):
                        previous = snapshots[1]
                json_response(self, build_whatsapp_alerts(previous, current or {}))
            except Exception as exc:
                logger.exception("WhatsApp alerts build failed")
                json_response(self, {"error": "WhatsApp alerts build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/outreach/stats":
            # عدّادات تفاعل العملاء مع فرص التسويق (نسخ/إرسال) من جدول outreach_clicks
            from backend.services.supabase_store import fetch_outreach_stats
            try:
                json_response(self, fetch_outreach_stats())
            except Exception as exc:
                logger.exception("Outreach stats failed")
                json_response(self, {"error": "Outreach stats failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/clients":
            # قائمة العملاء المحتملين: ملف CSV + قاعدة Supabase مدمجة + روابط واتساب جاهزة
            from backend.services.opportunities import _load_clients, normalize_phone
            try:
                clients = _load_clients()
                for client in clients:
                    wa_links = []
                    for part in re.split(r"[|،,]+", str(client.get("phones") or "")):
                        normalized = normalize_phone(part)
                        if normalized:
                            wa_links.append(f"https://wa.me/{normalized}")
                    client["waLinks"] = wa_links
                json_response(self, {"count": len(clients), "clients": clients})
            except Exception as exc:
                json_response(self, {"error": "Clients load failed", "detail": str(exc)}, status=500)
            return
        if path == "/":
            path = "/index.html"
        file_path = (FRONTEND_DIR / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(FRONTEND_DIR.resolve())) or not file_path.exists():
            self.send_error(404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        # منع المتصفح من استخدام نسخة قديمة مخزنة من ملفات الواجهة
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "Invalid JSON"}, status=400)
            return
        path = urlparse(self.path).path
        text = str(payload.get("text") or "")
        if path == "/api/parse":
            json_response(self, {"request": parse_request(text).__dict__})
            return
        if path == "/api/analyze":
            job_id = str(payload.get("jobId") or "")
            _progress_push(job_id, "parse", "تحليل الطلب وفهم النية والمنطقة والنوع")
            try:
                request = parse_request(text)
                if payload.get("mode") in {"search", "valuation", "search_and_value"}:
                    request.intent = str(payload["mode"])
                filter_overrides = payload.get("filters") or {}
                _apply_filter_overrides(request, filter_overrides)
                _default_sale_when_unspecified(request)
                source_mode = str(payload.get("sourceMode") or "local").strip()
                selected_source = str(payload.get("selectedSource") or "").strip()
                selected_sources_payload = payload.get("selectedSources") or []
                if isinstance(selected_sources_payload, str):
                    selected_sources_payload = [selected_sources_payload]
                selected_sources_payload = [
                    str(name).strip() for name in selected_sources_payload
                    if str(name or "").strip()
                ]
                use_local = bool(payload.get("includeLocal", source_mode in {"local", "all"}))
                use_external = source_mode in {"all", "source", "custom"} and bool(payload.get("includeExternal", True))
                listings = load_listings() if use_local else []
                local_count = len(listings)
                _progress_push(job_id, "local", f"تحميل {local_count} إعلانًا محليًا من قاعدة الفريج")
                external_statuses = []
                if use_external:
                    selected_sources = selected_sources_payload or ([selected_source] if source_mode == "source" and selected_source else None)
                    _progress_push(job_id, "external", "بدء فحص المصادر الخارجية بالتوازي")
                    external_listings, external_statuses = search_external_sources(
                        request,
                        selected_sources=selected_sources,
                        # name موحّد من مفتاح السجل في بدء وانتهاء كل مصدر (بعض الحالات النهائية
                        # تحمل اسمًا مختلفًا للعرض) — حتى يعرض العميل صفًا واحدًا لكل مصدر.
                        progress_cb=lambda name, st: _progress_source_event(job_id, name, st),
                    )
                    # فلتر الأسعار الواقعية: الأسعار النائبة/الوهمية من صفحات المصادر
                    # (9,999 / 5,000 د.ك بيع، 70 د.ك إيجار) لا تدخل نتائج البحث والتقييم.
                    from backend.services.opportunities import has_realistic_price
                    _before = len(external_listings)
                    external_listings = [item for item in external_listings if has_realistic_price(item)]
                    _dropped = _before - len(external_listings)
                    if _dropped:
                        logger.info("analyze: استبعاد %d إعلانًا خارجيًا بأسعار غير واقعية", _dropped)
                    _progress_push(job_id, "score", f"تم جمع {len(external_listings)} إعلانًا خارجيًا — مرشح الآن للأسعار والمطابقة")
                    listings.extend(external_listings)
                if request.governorates and not request.areas:
                    allowed_governorates = set(request.governorates)
                    listings = [
                        item for item in listings
                        if item.governorate in allowed_governorates
                    ]
                listings = _filter_listings_by_explicit_location(listings, request, filter_overrides)
                ranked = top_matches(request, listings, limit=100)
                enriched = enrich_rankings(request, ranked, listings)
                deduped = deduplicate_ranked(enriched)[:50]
                _progress_push(job_id, "score", f"تقييم المطابقة والترتيب: {len(deduped)} نتيجة نهائية")

                # Fetch AI professional analysis
                _progress_push(job_id, "report", "بناء التقرير والتحليل الاحترافي (قد يستغرق ثوانٍ)")
                ai_insights = generate_professional_analysis(request, deduped, external_statuses)
                
                report = build_report(
                    request,
                    deduped,
                    local_count,
                    external_statuses,
                    ai_insights,
                    include_local_source=use_local,
                )

                # ربط العملاء المحتملين بنتائج التحليل: ما دام العرض بيعًا، يُعرض من يبحث عن شراء
                # في نفس المنطقة/النوع/النطاق السعري (من ملف العملاء + Supabase) — الإيجار يُستثنى.
                try:
                    from backend.services.opportunities import _load_clients, clients_from_demand_listings, match_clients_for_listing
                    analyze_clients = _load_clients() + clients_from_demand_listings(listings)
                    for result in report.get("results", []):
                        if result.get("rental"):
                            result["clients"] = []
                            continue
                        result["clients"] = match_clients_for_listing(
                            analyze_clients,
                            str(result.get("area") or ""),
                            str(result.get("propertyType") or result.get("detailClass") or ""),
                            result.get("price"),
                        )
                    for result in (report.get("similarExternal") or {}).get("items", []):
                        result["clients"] = match_clients_for_listing(
                            analyze_clients,
                            str(result.get("area") or ""),
                            str(result.get("propertyType") or ""),
                            result.get("price"),
                        )
                    report["profitOpportunities"] = _profit_opportunities(report)
                except Exception as clients_error:
                    logger.warning("Clients attach failed: %s", clients_error)
                    report["profitOpportunities"] = _profit_opportunities(report)

                try:
                    report["persistence"] = persist_analysis(request, report, report["sourceStatus"])
                except Exception as persist_error:
                    report["persistence"] = {
                        "enabled": supabase_is_configured(),
                        "status": "failed",
                        "error": str(persist_error),
                    }

                # حفظ طلب التقييم في user_valuation_requests (يظهر فورًا في لوحة العرض)
                try:
                    if supabase_is_configured() and request.areas:
                        fair_value = report.get("valuation", {}).get("fairValue") or report.get("fairValue")
                        valuation_result = report.get("valuation") or {}
                        save_valuation_request(
                            region=request.areas[0],
                            property_type=request.property_type or "",
                            land_area_m2=request.min_area or request.max_area,
                            offered_price=request.budget,
                            fair_value_estimated=fair_value or valuation_result.get("marketValue"),
                            # الثقة كسر بين 0 و1 → تحويلها إلى نسبة مئوية صحيحة لعمود score (integer)
                            score=round((getattr(deduped[0], "confidence", 0) or 0) * 100) if deduped else None,
                            lang="ar",
                        )
                except Exception as ve:
                    logger.warning("Could not save valuation request: %s", ve)

                _progress_push(job_id, "done", f"اكتمل التقرير — {len(deduped)} نتيجة", results=len(deduped))
                json_response(self, report)
            except Exception as exc:
                logger.exception("Analysis failed")
                json_response(self, {"error": "Analysis failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/report-pdf":
            try:
                from backend.services.pdf_report import build_pdf
                pdf_bytes = build_pdf(payload.get("report") or {})
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="alforaij-report.pdf"')
                self.send_header("Content-Length", str(len(pdf_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.end_headers()
                self.wfile.write(pdf_bytes)
            except Exception as exc:
                logger.exception("PDF generation failed")
                json_response(self, {"error": "PDF generation failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/outreach-click":
            # تتبع نقرات التسويق (نسخ/إرسال فرصة أو عميل) → يُسجَّل في outreach_clicks
            from backend.services.supabase_store import save_outreach_click
            try:
                result = save_outreach_click({
                    "clientPhone": payload.get("clientPhone"),
                    "clientArea": payload.get("clientArea"),
                    "clientType": payload.get("clientType"),
                    "opportunityCode": payload.get("opportunityCode"),
                    "action": payload.get("action"),
                    "channel": payload.get("channel"),
                })
                json_response(self, result)
            except Exception as exc:
                logger.warning("Outreach click save failed: %s", exc)
                json_response(self, {"status": "failed", "error": str(exc)})
            return
        if path == "/api/clients":
            # إضافة/تحديث عميل محتمل: يُحفظ في Supabase (إن مضبوط) + الملف المحلي دائمًا
            from backend.services.opportunities import append_csv_client
            from backend.services.supabase_store import save_client as supabase_save_client
            try:
                result = append_csv_client(payload)
                supabase_status = "skipped"
                if supabase_is_configured():
                    try:
                        supabase_save_client(payload)
                        supabase_status = "saved"
                        # سينك مع client_property_requests للوحة العرض
                        try:
                            save_client_property_request(
                                phone=str(payload.get("phone") or ""),
                                request_text=str(payload.get("note") or ""),
                                transaction_type="للبيع",
                                property_type=payload.get("type") or "",
                                regions=[payload.get("area", "")] if payload.get("area") else None,
                                max_budget=payload.get("price"),
                            )
                        except Exception:
                            pass
                    except Exception as exc:
                        supabase_status = f"failed: {exc}"
                json_response(self, {"status": result.get("status"), "code": result.get("code"), "supabase": supabase_status})
            except Exception as exc:
                json_response(self, {"error": "Client save failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/daily-agent/run":
            from backend.services.daily_update_agent import run_daily_update_agent
            try:
                result = run_daily_update_agent(
                    official_source=str(payload.get("officialSource") or ""),
                    include_external=bool(payload.get("includeExternal", True)),
                )
                json_response(self, result, status=200 if result.get("status") != "failed" else 500)
            except Exception as exc:
                logger.exception("Daily agent run failed")
                json_response(self, {"status": "failed", "error": str(exc)}, status=500)
            return
        if path == "/api/official-transactions/import":
            from backend.services.official_import import import_official_transactions_content
            try:
                result = import_official_transactions_content(
                    str(payload.get("filename") or "official_transactions.csv"),
                    str(payload.get("content") or ""),
                )
                json_response(self, result, status=200 if result.get("status") == "saved" else 400)
            except Exception as exc:
                logger.exception("Official transactions import failed")
                json_response(self, {"status": "failed", "error": str(exc)}, status=500)
            return
        json_response(self, {"error": "Unknown endpoint"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logger.info("Alforaij Research Assistant running on http://%s:%s", HOST, PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
