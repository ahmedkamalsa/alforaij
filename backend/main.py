from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

from backend.config import FRONTEND_DIR, HOST, PORT, AGENT_ROUTER_API_KEY
from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import enrich_listings_from_details, search_external_sources
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
from backend.models import PropertyRequest, RankedListing
from backend.services.security import SecurityMiddleware


from backend.services.ai_evaluator import generate_professional_analysis

# إعداد طبقة الأمان المركزية
_security = SecurityMiddleware()

# ذاكرة مؤقتة للفرص (تُحدَّث أول بأول): تُبنى عند أول طلب وتُعاد لفترة قصيرة
import threading as _threading
from concurrent.futures import ThreadPoolExecutor

_OPPORTUNITIES_LOCK = _threading.Lock()
_OPPORTUNITIES_CACHE: dict | None = None
_OPPORTUNITIES_PREVIOUS: dict | None = None  # اللقطة السابقة للمقارنة (تنبيهات واتساب)
_OPPORTUNITIES_CACHE_AT = 0.0
_OPPORTUNITIES_TTL_SECONDS = 300

# ---- كاش TTL عام لنقاط اللوحة والتحليلات (البيانات تتغير بالحصاد اليومي فقط،
# فإعادة الاستعلام من Supabase عند كل فتح تبويب إهدار للوقت بلا فائدة) ----
_TTL_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_CACHE_LOCK = _threading.Lock()


def _ttl_cached(key: str, ttl: float, builder):
    """يعيد قيمة من الكاش إن لم تنتهِ مدة صلاحيتها، وإلا يبنيها ويخزنها."""
    now = time.time()
    with _TTL_CACHE_LOCK:
        hit = _TTL_CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = builder()
    with _TTL_CACHE_LOCK:
        _TTL_CACHE[key] = (time.time(), value)
    return value


def _dashboard_cache_key(selected: set[str], include_local: bool) -> str | None:
    """مفتاح الكاش الذكي للوحة: اللوحة الافتراضية (كل المنصات + المحلي) مخزنة،
    وأي فلاتر مخصصة أو إقصاء للمحلي يُبنى حيًا دائمًا — فلاتر المستخدم لا تنتظر كاشًا.
    يعيد None عند الحاجة للبناء الحي (بلا كاش) ومفتاح الكاش عند التخزين."""
    if not selected and include_local:
        return "dashboard:default"
    return None


def _build_health_payload() -> dict:
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
    return {
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
    }


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
        "phone": getattr(listing, "phone", "") or "",
    }


# تطبيع المكان (منطقة ← محافظة بنفس الصيغ الكنسية) مشترك في
# backend/services/request_parser.py — اللوحة وتحليلات السوق تبنيان دلاءهما منه
# نفس الخريطة المعتمدة. هنا أسماء مستعارة بنفس الأسماء الداخلية السابقة حتى لا
# تتغير بقية الاستدعاءات ولا اختبارات الخريطة.
from backend.services.request_parser import (  # noqa: E402
    GOVERNORATE_ALIASES as _GOVERNORATE_ALIASES,
    area_governorate_map as _area_governorate_map,
    dashboard_area_key as _dashboard_area_key,
    normalize_dashboard_place as _normalize_dashboard_place,
    normalize_governorate_name as _normalize_governorate_name,
)


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
        "phone": row.get("phone") or "",
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
    يُستخدم كسقوط آمن فقط عند غياب القاعدة.

    كل الجلبات الشبكية (market_listings + market_ads + صفقات الحسبة) تُشغَّل
    بالتوازي لأنها التكلفة الحقيقية للفتح البارد — تسلسلها كان يضاعف الزمن."""
    market_names = {"السوق المباشر", "بوشملان", "OpenSooq", "Mourjan", "Q8Aqar", "Sakan", "Waseet", "4Sale", "Bu3qar", "Aqarat", "NabdAqar", "Yebtah"}
    records: list[dict] = []
    known_codes: set[str] = set()

    def _accept(raw_source: str) -> bool:
        return not selected or _platform_match(raw_source, selected) or "السوق المباشر" in selected

    def _fetch_harvested() -> list[dict]:
        try:
            from backend.services.supabase_store import fetch_market_listings
            return fetch_market_listings(limit=2000) or []
        except Exception as exc:
            logger.warning("Dashboard harvested market records skipped: %s", exc)
            return []

    def _fetch_live() -> list[dict]:
        try:
            from backend.services.supabase_store import _fetch_rows, SUPABASE_URL
            return _fetch_rows(f"{SUPABASE_URL}/rest/v1/market_ads?select=*&limit=2000") or []
        except Exception as exc:
            logger.warning("Dashboard live saved market records skipped: %s", exc)
            return []

    def _fetch_transactions() -> list[dict]:
        try:
            from backend.connectors.official_data import load_transactions
            return load_transactions()
        except Exception as exc:
            logger.warning("Dashboard Alhisba reference records skipped: %s", exc)
            return []

    with ThreadPoolExecutor(max_workers=3) as _pool:
        _f_harvested = _pool.submit(_fetch_harvested)
        _f_live = _pool.submit(_fetch_live)
        _f_transactions = _pool.submit(_fetch_transactions)
        harvested = _f_harvested.result()
        live_rows = _f_live.result()
        transactions = _f_transactions.result()

    # 1) الحصاد المتراكم من market_listings (المصدر الأساسي — كل المواقع الموثقة)
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

    # 3) الفحص الحي — سقوط آمن فقط عند غياب القاعدة (أو عند طلب منصة بعينها غير محصودة)
    if not harvested and (not selected or selected & market_names):
        try:
            from backend.connectors.market_ads import search as search_market_ads
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
    # 4) صفقات الحسبة الرسمية المرجعية (جُلبت بالتوازي أعلاه)
    if not selected or _platform_match("الحسبة - الصفقات المسجلة العامة", selected):
        try:
            from backend.connectors.official_data import _transaction_listing

            for index, row in enumerate(transactions):
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
        "phone": item.get("phone") or "",
    }
    _normalize_dashboard_place(record, area_map)
    return record


def _flat_dashboard_opportunities(selected: set[str], include_local: bool, area_map: dict[str, str]) -> tuple[list[dict], dict[str, dict], dict]:
    try:
        from backend.services.supabase_store import fetch_latest_opportunities

        # إعادة استخدام لقطة الفرص الحية في الذاكرة (كاش 5 دقائق نفسه الذي تستخدمه
        # نقاط التوفيق والدلتا) بدل استعلام Supabase جديد في كل فتح للوحة — القراءة
        # فقط بلا كتابة حتى لا تتداخل مع قفل /api/opportunities.
        snapshot = _OPPORTUNITIES_CACHE
        if snapshot is None or time.time() - _OPPORTUNITIES_CACHE_AT > _OPPORTUNITIES_TTL_SECONDS:
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


def _demand_indicator_payload(listings, request, top_area: str = "") -> dict:
    """سجلات «مطلوب للشراء/للإيجار» في نطاق الطلب كمؤشر طلب بجانب النتائج.

    يقبل كائنات Listing (الفريج المحلي) وصفوفًا dict (الطلبات الخارجية المحصودة
    من market_listings مثل قسم «مطلوب» في 4Sale) — الوصول عبر _di يتسامح مع النوعين.
    النطاق: مناطق الطلب أولًا، ثم محافظاته، ثم منطقة أقرب نتيجة — حتى يرى
    العميل من يبحث في نفس المنطقة التي قيّم عقاره فيها. لا يكسر التحليل أبدًا.
    """
    from backend.services.market_analysis import is_demand_transaction
    from backend.services.request_parser import normalize_text

    def _di(item, key: str, default: Any = ""):
        return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

    demand = [item for item in listings if is_demand_transaction(str(_di(item, "transaction") or ""))]
    empty = {"count": 0, "buyRequests": 0, "rentRequests": 0, "scope": "", "items": []}
    if not demand:
        return empty
    wanted_areas = [normalize_text(area) for area in request.areas]
    wanted_govs = {normalize_text(g) for g in request.governorates}

    def _in_scope(item) -> bool:
        area = normalize_text(str(_di(item, "area") or ""))
        if wanted_areas:
            return area in wanted_areas
        if wanted_govs:
            return normalize_text(str(_di(item, "governorate") or "")) in wanted_govs
        if top_area:
            return area == normalize_text(top_area)
        return True

    matched = [item for item in demand if _in_scope(item)]
    if not matched:
        return empty
    matched.sort(key=lambda item: str(_di(item, "published_date") or ""), reverse=True)
    items = []
    for item in matched[:12]:
        raw = _di(item, "raw")
        raw = raw if isinstance(raw, dict) else {}
        items.append({
            "transaction": _di(item, "transaction"),
            "area": _di(item, "area"),
            "governorate": _di(item, "governorate"),
            "propertyType": str(_di(item, "property_type") or "") or str(_di(item, "detail_class") or ""),
            "summary": str(_di(item, "summary") or "").strip()[:160],
            "phone": str(raw.get("phone") or ""),
            "originalUrl": _di(item, "original_url"),
            "publishedDate": _di(item, "published_date"),
            "code": _di(item, "code"),
        })
    buy = sum(1 for item in matched if "شراء" in str(_di(item, "transaction")))
    rent = sum(
        1 for item in matched
        if ("إيجار" in str(_di(item, "transaction")) or "ايجار" in str(_di(item, "transaction")))
    )
    if wanted_areas:
        scope = "، ".join(request.areas[:3])
    elif wanted_govs:
        scope = "، ".join(request.governorates[:3])
    elif top_area:
        scope = top_area
    else:
        scope = "كل الكويت"
    return {"count": len(matched), "buyRequests": buy, "rentRequests": rent, "scope": scope, "items": items}


def _dashboard_summary(listings, selected_platforms: set[str] | None = None, include_local: bool = True) -> dict:
    selected_platforms = selected_platforms or set()
    area_map = _area_governorate_map(listings)
    local_records = [_dashboard_record(row) for row in listings] if include_local else []
    for record in local_records:
        _normalize_dashboard_place(record, area_map)
    if selected_platforms and "__all" not in selected_platforms and not _is_local_platform_selected(selected_platforms):
        local_records = []
    external_platforms = selected_platforms - {"الفريج", "alforaij", "Alforaij", "الفريج المحلي", "__all"}
    # شطرا اللوحة الثقيلان (سجلات السوق + لقطة الفرص) يُشغَّلان بالتوازي — كلاهما
    # يجلب من Supabase، وتسلسلهما كان يضاعف زمن الفتح البارد.
    with ThreadPoolExecutor(max_workers=2) as _pool:
        if not selected_platforms or "__all" in selected_platforms:
            _f_market = _pool.submit(_dashboard_market_records, set(), area_map)
        elif external_platforms:
            _f_market = _pool.submit(_dashboard_market_records, external_platforms, area_map)
        else:
            # فلترة محلية فقط (مثل «الفريج»): لا سجلات سوق خارجية أصلًا
            _f_market = _pool.submit(lambda: [])
        _f_opps = _pool.submit(_flat_dashboard_opportunities, selected_platforms, include_local, area_map)
        market_records = _f_market.result()
        opportunity_items, opportunities_by_code, opportunity_snapshot = _f_opps.result()
    records = local_records + market_records
    raw_count = len(records)
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
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    # رؤوس الأمان (CSP + XSS protection)
    for header, value in _security.get_headers().items():
        handler.send_header(header, value)
    handler.end_headers()
    handler.wfile.write(body)


def _iso_utc(epoch: float) -> str:
    """تحويل epoch إلى صيغة ISO معروفة لـ Supabase (timestamptz)."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_epoch(iso_value) -> float | None:
    """تحويل صيغة ISO من Supabase إلى epoch — أو None عند غياب/فشل."""
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


_OTP_ERROR_TEXT = {
    "no_otp": "أرسل رمز التحقق أولًا",
    "expired": "انتهت صلاحية الرمز — أعد إرسال رمز جديد",
    "too_many_attempts": "تجاوزت عدد المحاولات — أعد إرسال الرمز",
    "wrong_code": "الرمز غير صحيح — حاول مجددًا",
}


def _otp_error_text(reason: str) -> str:
    return _OTP_ERROR_TEXT.get(reason, "تعذر التحقق من الرمز")


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
            # كاش 120 ثانية: الفحص يستعلم ~13 جدولًا في Supabase (3-6 ثوانٍ) والمعلومات
            # تتغير بالحصاد اليومي فقط — تكراره في كل تحميل صفحة إهدار.
            json_response(self, _ttl_cached("health", 120, _build_health_payload))
            return
        if path == "/api/google-client-id":
            # إرجاع Google Client ID للواجهة — يُقرأ من متغير البيئة أو .env
            client_id = os.getenv("GOOGLE_CLIENT_ID", "")
            json_response(self, {"client_id": client_id})
            return
        if path == "/api/analytics" and self.command == "GET":
            # قراءة إحصائيات التتبع للداشبورد
            log_path = os.path.join(os.path.dirname(__file__), "..", "analytics.jsonl")
            events = []
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                events.append(json.loads(line))
                except Exception:
                    pass
            # تحليل بسيط
            from collections import Counter
            clicks = Counter()
            searches = Counter()
            pages = Counter()
            for ev in events:
                if ev.get("event") == "click":
                    clicks[ev.get("data", {}).get("label", "unknown")] += 1
                elif ev.get("event") == "search":
                    searches[ev.get("data", {}).get("query", "unknown")] += 1
                elif ev.get("event") == "pageview":
                    pages[ev.get("data", {}).get("page", "/")] += 1
            json_response(self, {
                "total": len(events),
                "topClicks": clicks.most_common(20),
                "topSearches": searches.most_common(20),
                "topPages": pages.most_common(20),
            })
            return
        # ── لوحة تحليلات متقدمة: أنماط البحث والمناطق الشائعة واتجاهات الأسعار ──
        if path == "/api/analytics-dashboard":
            try:
                from backend.services.analytics_dashboard import build_dashboard
                dashboard = build_dashboard()
                json_response(self, dashboard)
            except Exception as dash_err:
                logger.warning("Analytics dashboard failed: %s", dash_err)
                json_response(self, {"error": str(dash_err)}, status=500)
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
                # كاش 5 دقائق: تجميع 5000 صف من market_listings ثقيل (~1.8 ثانية بارد)
                # والبيانات تتغير بالحصاد اليومي فقط — أُضيف بنفس نمط market-insights.
                json_response(self, _ttl_cached("market-analytics", 300, fetch_market_analytics))
            except Exception as exc:
                logger.exception("Market analytics failed")
                json_response(self, {"error": "Market analytics failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/market-insights":
            # تحليلات السوق (الموجة 1): عائد الإيجار واتجاه سعر المتر لكل منطقة
            from backend.services.supabase_store import fetch_market_insights
            try:
                # كاش 5 دقائق: تجميع 8000 صف من market_listings ثقيل — يُعاد فقط عند انتهاء الصلاحية
                json_response(self, _ttl_cached("market-insights", 300, fetch_market_insights))
            except Exception as exc:
                logger.exception("Market insights failed")
                json_response(self, {"error": "Market insights failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/market-demand":
            # مؤشرات الطلب: عدّ طلبات الشراء/الإيجار لكل منطقة ومحافظة + اتجاه شهري
            from backend.services.supabase_store import fetch_demand_indicators
            try:
                json_response(self, _ttl_cached("market-demand", 300, fetch_demand_indicators))
            except Exception as exc:
                logger.exception("Market demand failed")
                json_response(self, {"error": "Market demand failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/metric-registry":
            # سجل تعريفات المقاييس الموثق — كل رقم يظهر في المنصة بصيغته ومصدره
            # ومعتمده. الصيغ الرقمية مبنية من ثوابت المحرك الفعلية (لا نصوص منسوخة)،
            # فيتزامن السجل تلقائيًا مع أي تغيير في منطق الحساب.
            from backend.services.metric_registry import build_metric_registry
            try:
                json_response(self, build_metric_registry())
            except Exception as exc:
                logger.exception("Metric registry failed")
                json_response(self, {"error": "Metric registry failed", "detail": str(exc)}, status=500)
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

            def _build_dashboard():
                return _dashboard_summary(load_listings(), selected_platforms=selected, include_local=include_local)

            # كاش ذكي حسب الفلاتر: الافتراضية مخزنة 90 ثانية، والفلاتر المخصصة حية
            # دائمًا (انظر _dashboard_cache_key — القرار مُختبر باختبار وحدة).
            cache_key = _dashboard_cache_key(selected, include_local)
            if cache_key:
                json_response(self, _ttl_cached(cache_key, 90, _build_dashboard))
            else:
                json_response(self, _build_dashboard())
            return
        if path == "/api/platform-dates":
            # بداية الحصاد لكل منصة: عدد الإعلانات + أول يوم جلب + أقدم تاريخ نشر
            from scripts.export_static_frontend_data import build_platform_dates
            json_response(self, _ttl_cached("platform-dates", 900, lambda: build_platform_dates(load_listings())))
            return
        if path == "/api/update-notifications":
            from backend.services.update_notifications import load_update_notifications
            json_response(self, load_update_notifications())
            return
        if path == "/api/developments":
            # تطورات السوق من وكيل الاكتشاف اليومي: الملف المحلي أولًا (سريع وبلا
            # قاعدة)، وإلا أحدث ما حُفظ في market_developments (Supabase).
            from backend.services.developments_agent import load_developments_local
            from backend.services.supabase_store import fetch_market_developments
            local = load_developments_local()
            if local.get("developments"):
                json_response(self, local)
                return
            try:
                rows = fetch_market_developments(limit=100)
                json_response(self, {"generatedAt": "", "count": len(rows), "developments": rows})
            except Exception as exc:
                logger.warning("Developments fetch failed: %s", exc)
                json_response(self, {"generatedAt": "", "count": 0, "developments": [], "error": str(exc)})
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
            # كاش 5 دقائق — المفتاح يشمل المنطقة المطلوبة.
            cache_key = f"price-trends:{area or '*'}"
            json_response(self, _ttl_cached(cache_key, 300, lambda: {"rows": fetch_price_trends(area=area or None, limit=2000), "tableOk": True}))
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
        if path == "/api/live-db":
            # إعداد القاعدة الحية للواجهة (المفتاح العام anon): على الموقع المنشور الثابت
            # تُقرأ من static-data/live-db.json عبر fetchStaticJson، وعلى خادم API تُقدَّم
            # حيًا من البيئة — فلا 404 في نسخة نظيفة (درس فحص الجوال) وتعمل الميزتان.
            from backend.config import SUPABASE_ANON_KEY, SUPABASE_URL
            json_response(
                self,
                {
                    "url": SUPABASE_URL,
                    "anonKey": SUPABASE_ANON_KEY,
                    "note": "قراءة مباشرة من القاعدة الحية عبر المفتاح العام (anon) — الجداول العامة فقط عبر RLS.",
                },
            )
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
        text = _security.sanitize(str(payload.get("text") or ""))
        if path == "/api/parse":
            json_response(self, {"request": parse_request(text).__dict__})
            return
        if path == "/api/whatsapp/parse":
            # تحليل رسالة واتساب مُ Forwarded — يستخرج التفاصيل تلقائيًا
            from backend.services.whatsapp_parser import analyze_whatsapp_message, analyze_bulk_messages
            sender = _security.sanitize(str(payload.get("sender") or ""))
            phone = str(payload.get("phone") or "")
            raw = str(payload.get("text") or "")
            bulk = bool(payload.get("bulk"))
            if bulk:
                messages = analyze_bulk_messages(raw)
                json_response(self, {
                    "count": len(messages),
                    "messages": [
                        {
                            "rawText": msg.raw_text[:200],
                            "sender": msg.sender,
                            "phone": msg.phone,
                            "propertyType": msg.property_type,
                            "transaction": msg.transaction,
                            "area": msg.area,
                            "governorate": msg.governorate,
                            "price": msg.price,
                            "priceText": msg.price_text,
                            "space": msg.space,
                            "bedrooms": msg.bedrooms,
                            "features": msg.features,
                            "sellerType": msg.seller_type,
                            "summary": msg.summary,
                            "isPropertyListing": msg.is_property_listing,
                            "confidence": msg.confidence,
                        }
                        for msg in messages
                    ],
                })
            else:
                msg = analyze_whatsapp_message(raw, sender=sender, phone=phone)
                json_response(self, {
                    "rawText": msg.raw_text[:200],
                    "sender": msg.sender,
                    "phone": msg.phone,
                    "propertyType": msg.property_type,
                    "transaction": msg.transaction,
                    "area": msg.area,
                    "governorate": msg.governorate,
                    "price": msg.price,
                    "priceText": msg.price_text,
                    "space": msg.space,
                    "bedrooms": msg.bedrooms,
                    "features": msg.features,
                    "sellerType": msg.seller_type,
                    "summary": msg.summary,
                    "isPropertyListing": msg.is_property_listing,
                    "confidence": msg.confidence,
                })
            return
        if path == "/api/register":
            # تسجيل مستخدم مجاني: توحيد الهاتف الكويتي + إصدار OTP (6 أرقام/10 دقائق)
            # + نافذة 15 دقيقة بين إعادة الإرسال. التسليم واتساب (قالب) أو انحدار أنيق:
            # الرمز على الشاشة مرة واحدة (delivery: on_screen) عند غياب أسرار واتساب.
            from backend.services.accounts import (
                OTP_RESEND_WINDOW_SECONDS,
                issue_otp,
                normalize_phone,
                otp_resend_allowed,
                COUNTRY_CODES,
            )
            from backend.services.supabase_store import fetch_user, upsert_user
            from scripts.send_whatsapp_message import send_template_message

            phone, country_code = normalize_phone(payload.get("phone") or "")
            if not phone:
                supported = ", ".join([f"{c['name']} ({c['code']})" for c in COUNTRY_CODES.values()])
                json_response(
                    self,
                    {"error": "invalid_phone", "detail": f"أدخل رقم هاتف صحيح — الدول المدعومة: {supported}"},
                    status=400,
                )
                return
            now = time.time()
            user = fetch_user(phone)
            requested_at = _parse_epoch(user.get("otp_requested_at")) if user else None
            if user and not otp_resend_allowed(now, requested_at):
                remaining_min = max(1, int((OTP_RESEND_WINDOW_SECONDS - (now - (requested_at or 0))) // 60))
                json_response(
                    self,
                    {"error": "rate_limited", "detail": f"أعد المحاولة بعد {remaining_min} دقيقة"},
                    status=429,
                )
                return
            code, stored, expires = issue_otp()
            upsert_user(
                {
                    "phone": phone,
                    "otp_hash": stored,
                    "otp_expires_at": _iso_utc(expires),
                    "otp_attempts": 0,
                    "otp_requested_at": _iso_utc(now),
                }
            )
            template = os.getenv("WHATSAPP_OTP_TEMPLATE", "alforaij_otp")
            delivery = send_template_message(phone, template, [code])
            if delivery:
                json_response(self, {"status": "ok", "delivery": "whatsapp"})
            else:
                json_response(
                    self,
                    {
                        "status": "ok",
                        "delivery": "on_screen",
                        "code": code,
                        "expires_in_seconds": 600,
                    },
                )
            return
        if path == "/api/verify-otp":
            # التحقق من الرمز: يصحح المحاولات/الانتهاء، ويُنشئ سرّ المستخدم (24 حرفًا)
            # إن لم يكن موجودًا ويرجعه — المفتاح الوحيد لبياناته في المهام التالية.
            from backend.services.accounts import check_otp, new_secret, normalize_phone
            from backend.services.supabase_store import fetch_user, patch_user

            phone, _ = normalize_phone(payload.get("phone") or "")
            code = str(payload.get("code") or "").strip()
            if not phone or not code:
                json_response(self, {"error": "missing_fields", "detail": "أدخل الهاتف والرمز"}, status=400)
                return
            user = fetch_user(phone)
            if not user or not user.get("otp_hash"):
                json_response(self, {"error": "no_otp", "detail": "أرسل رمز التحقق أولًا"}, status=400)
                return
            ok, reason = check_otp(
                code,
                user.get("otp_hash") or "",
                _parse_epoch(user.get("otp_expires_at")) or 0,
                int(user.get("otp_attempts") or 0),
            )
            if not ok:
                if reason == "wrong_code":
                    patch_user(phone, {"otp_attempts": int(user.get("otp_attempts") or 0) + 1})
                json_response(self, {"error": reason, "detail": _otp_error_text(reason)}, status=400)
                return
            secret = user.get("secret") or new_secret()
            patch_user(
                phone,
                {
                    "verified": True,
                    "secret": secret,
                    "otp_hash": None,
                    "otp_expires_at": None,
                    "otp_attempts": 0,
                },
            )
            json_response(self, {"status": "ok", "secret": secret, "phone": phone})
            return
        if path == "/api/google-login":
            from backend.services.accounts import new_secret
            from backend.services.supabase_store import fetch_user, upsert_user, patch_user
            credential = payload.get("credential") or ""
            if not credential:
                json_response(self, {"error": "missing_credential", "detail": "لم يتم إرسال بيانات Google"}, status=400)
                return
            # Decode Google Identity Services JWT payload
            try:
                parts = credential.split(".")
                if len(parts) != 3:
                    raise ValueError("Invalid JWT format")
                b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                idinfo = json.loads(base64.urlsafe_b64decode(b64))
            except Exception as e:
                logger.warning("Google credential decode failed: %s", e)
                json_response(self, {"error": "invalid_credential", "detail": "بيانات Google غير صالحة"}, status=400)
                return
            if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
                json_response(self, {"error": "invalid_issuer"}, status=400)
                return
            google_sub = idinfo.get("sub") or ""
            if not google_sub:
                json_response(self, {"error": "no_sub", "detail": "لا يوجد معرّف Google"}, status=400)
                return
            phone_key = f"google:{google_sub}"
            resp = {"status": "ok", "phone": idinfo.get("email", ""),
                    "name": idinfo.get("name", ""), "avatar": idinfo.get("picture", ""),
                    "provider": "google"}
            user = None
            try:
                user = fetch_user(phone_key)
            except Exception as fetch_err:
                logger.warning("Google login fetch_user failed: %s", fetch_err)
            if user and user.get("secret"):
                json_response(self, {**resp, "secret": user["secret"]})
                return
            secret = new_secret()
            try:
                upsert_user({"phone": phone_key, "secret": secret, "verified": True})
            except Exception as upsert_err:
                logger.warning("Google login upsert_user failed: %s", upsert_err)
            try:
                patch_user(phone_key, {"google_email": resp["phone"], "google_name": resp["name"], "google_picture": resp["avatar"]})
            except Exception:
                pass
            json_response(self, {**resp, "secret": secret})
            return
        if path == "/api/analytics":
            # استقبال بيانات التتبع من الواجهة
            try:
                if isinstance(payload, list) and payload:
                    log_path = os.path.join(os.path.dirname(__file__), "..", "analytics.jsonl")
                    with open(log_path, "a", encoding="utf-8") as f:
                        for ev in payload:
                            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                json_response(self, {"ok": True, "count": len(payload) if isinstance(payload, list) else 0})
            except Exception as e:
                json_response(self, {"ok": False, "error": str(e)}, status=400)
            return
        if path == "/api/analyze":
            job_id = str(payload.get("jobId") or "")
            _progress_push(job_id, "parse", "تحليل الطلب وفهم النية والمنطقة والنوع")
            # فحص صلاحية البحث على الخادم (Server-side tier check)
            from backend.services.server_tier import authorize_request, record_usage, extract_user_from_token
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            user_id = user["user_id"] if user else ""
            # بديل: قبول user_secret من جسم الطلب (الواجهة الأمامية ترسله مباشرة)
            if not user_id:
                from backend.services.supabase_store import fetch_user_by_secret
                _secret = str(payload.get("user_secret") or "").strip()
                if _secret:
                    _u = fetch_user_by_secret(_secret)
                    if _u:
                        user_id = _u.get("phone") or _secret[:8]
            _source_mode = str(payload.get("sourceMode") or "local").strip()
            # البحث المحلي مسموح بدون تسجيل — البحث الخارجي يتطلب حساب
            if _source_mode != "local":
                auth_result = authorize_request(user_id, "search")
                if not auth_result["authorized"]:
                    json_response(self, {
                        "error": "tier_limit",
                        "message": auth_result["message"],
                        "tier": auth_result["tier"],
                        "upgrade": auth_result.get("upgrade"),
                    }, status=403)
                    return
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
                # الفريج المحلي يُحمَّل دائمًا (رخيص من الملف) لأن مؤشر الطلب بجانب
                # النتائج يعتمد على سجلات «مطلوب» المحلية حتى لو كان المصدر المختار خارجيًا.
                local_demand_source = load_listings()
                listings = local_demand_source if use_local else []
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
                    # وكيل إكمال التفاصيل: الإعلانات القادمة من صفحات القوائم كثيرًا ما تنقصها
                    # السعر أو المساحة أو المنطقة — يقرأ صفحة التفاصيل لكل إعلان ناقص ويكمّلها
                    # قبل فلتر الأسعار والمطابقة بالفلاتر (حتى لا يُسقط إعلان صالح بسبب بيانات ناقصة).
                    _enrich = enrich_listings_from_details(external_listings)
                    if _enrich.get("enriched"):
                        _progress_push(job_id, "enrich", _enrich["note"])
                        external_statuses.append({
                            "name": "وكيل إكمال التفاصيل",
                            "status": _enrich.get("status"),
                            "records": _enrich.get("enriched", 0),
                            "candidates": _enrich.get("read", 0),
                            "note": _enrich.get("note", ""),
                            "fetchMethod": "صفحات التفاصيل (بالموازاة)",
                            "endpoint": "روابط إعلانات المصادر الخارجية",
                            # وكيل معالجة داخلي — شفاف في تفاصيل المصادر لكنه ليس
                            # مصدرًا حقيقيًا فلا يظهر في شريط «مصادر هذه النتائج».
                            "kind": "internal",
                        })
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
                _fast = bool(payload.get("fast"))
                if _fast:
                    # ── الوضع السريع: نتائج فورية بدون تقييم مقارن (أقل من ثانية) ──
                    ranked = top_matches(request, listings, limit=10)
                    deduped = []
                    for t in ranked:
                        listing_obj, score, reasons, warnings, match_breakdown = t
                        deduped.append(RankedListing(
                            listing=listing_obj, match_score=round(score, 1),
                            valuation_label="", valuation_reason="",
                            confidence=0.0, deal_score=0, recommendation_score=round(score, 1),
                            market_median=None, price_ratio=None,
                            match_breakdown=match_breakdown, recommendation_breakdown={},
                            number_sources={}, reasons=reasons, warnings=warnings, comparables=[],
                        ))
                    _progress_push(job_id, "score", f"急速: {len(deduped)} نتيجة")
                else:
                    _rank_limit = 100
                    ranked = top_matches(request, listings, limit=_rank_limit)
                    enriched = enrich_rankings(request, ranked, listings)
                    deduped = deduplicate_ranked(enriched)[:50]
                    _progress_push(job_id, "score", f"تقييم المطابقة والترتيب: {len(deduped)} نتيجة نهائية")

                # ── الوضع السريع (fast mode) للمساعد العقاري: يتخطى التصنيف والتحليل والعملاء ──
                if _fast:
                    _progress_push(job_id, "report", "بناء التقرير السريع")
                    ai_insights = {}
                    report = build_report(
                        request, deduped, local_count, external_statuses, ai_insights,
                        include_local_source=use_local,
                    )
                else:
                    # تصنيف تلقائي للنتائج: يصنف كل إعلان حسب 7 فئات
                    _progress_push(job_id, "classify", "تصنيف النتائج تلقائيًا حسب الفئات")
                    try:
                        from backend.services.listing_classifier import get_classifier
                        classifier = get_classifier()
                        for result in deduped:
                            _l = result.listing
                            _raw = _l.raw if hasattr(_l, 'raw') and isinstance(_l.raw, dict) else {}
                            listing_dict = {
                                "id": _raw.get("id", _l.code),
                                "title": _raw.get("title", _l.summary[:60] if _l.summary else ""),
                                "description": _raw.get("description", _l.summary),
                                "price": _l.price or _raw.get("price", 0),
                                "space": _l.space or _raw.get("space", 0),
                                "area": _l.area or _raw.get("area", ""),
                                "governorate": _l.governorate or _raw.get("governorate", ""),
                                "propertyType": _l.property_type or _raw.get("propertyType", ""),
                                "transaction": _l.transaction or _raw.get("transaction", ""),
                                "listingMode": _l.listing_mode or _raw.get("listingMode", ""),
                                "source": _l.source or _raw.get("source", ""),
                                "opportunityScore": _raw.get("opportunityScore", 0),
                                "movement": _raw.get("movement", 0),
                                "evidenceCount": _raw.get("evidenceCount", 0),
                            }
                            classification = classifier.classify_listing(listing_dict)
                            _raw["classification"] = {
                                "propertyType": classification.classifications.get("property_type", ""),
                                "investmentLevel": classification.classifications.get("investment_level", ""),
                                "priority": classification.classifications.get("priority", ""),
                                "dealType": classification.classifications.get("deal_type", ""),
                                "dataSource": classification.classifications.get("data_source", ""),
                                "trustLevel": classification.classifications.get("trust_level", ""),
                                "targetAudience": classification.classifications.get("target_audience", ""),
                                "overallScore": classification.overall_score,
                                "tags": classification.tags,
                            }
                        _progress_push(job_id, "classify", f"تم تصنيف {len(deduped)} إعلانًا")
                    except Exception as classify_error:
                        logger.warning("Classification failed: %s", classify_error)

                    # Fetch AI professional analysis
                    _progress_push(job_id, "report", "بناء التقرير والتحليل الاحترافي (قد يستغرق ثوانٍ)")
                    ai_insights = generate_professional_analysis(request, deduped, external_statuses)
                    
                    report = build_report(
                        request, deduped, local_count, external_statuses, ai_insights,
                        include_local_source=use_local,
                    )
                    try:
                        from backend.services.chat_agents import build_chat_guidance
                        report["chatGuidance"] = build_chat_guidance(request, report, source_mode=source_mode)
                    except Exception as chat_guidance_error:
                        logger.warning("Chat guidance failed: %s", chat_guidance_error)

                    # ربط العملاء المحتملين بنتائج التحليل
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

                if not _fast:
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
                                score=round((getattr(deduped[0], "confidence", 0) or 0) * 100) if deduped else None,
                                lang="ar",
                            )
                    except Exception as ve:
                        logger.warning("Could not save valuation request: %s", ve)

                # مؤشر الطلب بجانب النتائج: من يبحث عن شراء/إيجار في نفس المنطقة
                if not _fast:
                    try:
                        top_area = deduped[0].listing.area if deduped else ""
                        demand_source = list(local_demand_source)
                        if supabase_is_configured():
                            from backend.services.supabase_store import fetch_external_demand_rows
                            demand_source.extend(fetch_external_demand_rows())
                        report["demandIndicators"] = _demand_indicator_payload(demand_source, request, top_area)
                    except Exception as demand_error:
                        logger.warning("Demand indicators failed: %s", demand_error)
                        report["demandIndicators"] = {"count": 0, "buyRequests": 0, "rentRequests": 0, "scope": "", "items": []}

                _progress_push(job_id, "done", f"اكتمل التقرير — {len(deduped)} نتيجة", results=len(deduped))
                # تسجيل الاستخدام بعد البحث الناجح
                if not _fast:
                    try:
                        record_usage(user_id, "search")
                    except Exception:
                        pass
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
        if path == "/api/tier/status":
            # حالة خطتك الحالية: الخطة والاستخدام اليومي والحدود المتبقية
            from backend.services.server_tier import get_tier_limits, extract_user_from_token
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            user_id = user["user_id"] if user else ""
            json_response(self, get_tier_limits(user_id))
            return
        if path == "/api/tier/upgrade":
            # ترقية الخطة: يتطلب JWT صالح
            from backend.services.server_tier import upgrade_user, extract_user_from_token
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            if not user:
                json_response(self, {"error": "غير مصرح — سجّل الدخول أولاً"}, status=401)
                return
            new_tier = str(payload.get("tier") or "")
            if not new_tier:
                json_response(self, {"error": "حدد الخطة الجديدة"}, status=400)
                return
            result = upgrade_user(user["user_id"], new_tier)
            json_response(self, result, status=200 if "error" not in result else 400)
            return
        if path == "/api/tier/authorize":
            # فحص صلاحية ميزة: يتطلب JWT أو يُعيد حالة "مجاني" للمستخدمين غير المسجلين
            from backend.services.server_tier import authorize_request, extract_user_from_token
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            user_id = user["user_id"] if user else ""
            feature = str(payload.get("feature") or "search")
            result = authorize_request(user_id, feature)
            json_response(self, result)
            return
        if path == "/api/tier/pricing":
            # عرض الخطط والأسعار (للصفحة العامة)
            from backend.services.tier import list_tiers
            json_response(self, {"tiers": list_tiers()})
            return
        if path == "/api/admin/dashboard":
            # لوحة تحكم الأدمن: إحصائيات شاملة (يتطلب صلاحية admin)
            from backend.services.admin_analytics import get_admin_dashboard
            from backend.services.server_tier import extract_user_from_token
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            if not user or user.get("tier") not in ("pro", "enterprise"):
                json_response(self, {"error": "يتطلب صلاحية Pro أو Enterprise"}, status=403)
                return
            json_response(self, get_admin_dashboard())
            return
        if path == "/api/invest/calculate":
            # حاسبة العائد الاستثماري
            from backend.services.investment_calculator import calculate_roi
            buy_price = float(payload.get("buy_price") or 0)
            monthly_rent = float(payload.get("monthly_rent") or 0)
            renovation = float(payload.get("renovation") or 0)
            if buy_price <= 0 or monthly_rent <= 0:
                json_response(self, {"error": "أدخل سعر الشراء والإيجار الشهري"}, status=400)
                return
            result = calculate_roi(buy_price, monthly_rent, renovation)
            json_response(self, result)
            return
        if path == "/api/invest/mortgage":
            # حاسبة التمويل العقاري
            from backend.services.investment_calculator import calculate_mortgage
            price = float(payload.get("price") or 0)
            down_pct = float(payload.get("down_payment_pct") or 20)
            rate = float(payload.get("interest_rate") or 5.5)
            years = int(payload.get("years") or 20)
            rent = float(payload.get("monthly_rent") or 0)
            if price <= 0:
                json_response(self, {"error": "أدخل سعر العقار"}, status=400)
                return
            result = calculate_mortgage(price, down_pct, rate, years, rent)
            json_response(self, result)
            return
        if path == "/api/invest/compare":
            # مقارنة أحياء
            from backend.services.investment_calculator import compare_neighborhoods
            areas = payload.get("areas") or []
            if not areas:
                json_response(self, {"error": "حدد مناطق للمقارنة"}, status=400)
                return
            result = compare_neighborhoods(areas)
            json_response(self, result)
            return
        if path == "/api/invest/forecast":
            # توقع العائد المستقبلي
            from backend.services.investment_calculator import forecast_return
            price = float(payload.get("buy_price") or 0)
            rent = float(payload.get("monthly_rent") or 0)
            years = int(payload.get("years") or 5)
            rent_growth = float(payload.get("rent_growth") or 3)
            price_growth = float(payload.get("price_growth") or 4)
            if price <= 0 or rent <= 0:
                json_response(self, {"error": "أدخل سعر الشراء والإيجار"}, status=400)
                return
            result = forecast_return(price, rent, years, rent_growth, price_growth)
            json_response(self, result)
            return
        
        # ══════════════════════════════════════════════════════════════════
        # نظام التصنيفات الذكية
        # ══════════════════════════════════════════════════════════════════
        if path == "/api/classifiers":
            # جلب جميع المصنفات
            from backend.services.listing_classifier import get_classifier
            classifier = get_classifier()
            json_response(self, {"classifiers": classifier.get_classifiers()})
            return
        if path == "/api/classifiers/add":
            # إضافة مصنف جديد
            from backend.services.listing_classifier import get_classifier, Classifier, ClassificationCategory
            classifier = get_classifier()
            new_class = Classifier(
                id=payload.get("id", ""),
                name=payload.get("name", ""),
                name_en=payload.get("name_en", ""),
                category=ClassificationCategory(payload.get("category", "property_type")),
                description=payload.get("description", ""),
                values=payload.get("values", [])
            )
            if classifier.add_classifier(new_class):
                json_response(self, {"success": True, "message": "تمت الإضافة"})
            else:
                json_response(self, {"error": "الحد الأقصى 10 مصنفات"}, status=400)
            return
        if path == "/api/classifiers/remove":
            # حذف مصنف
            from backend.services.listing_classifier import get_classifier
            classifier = get_classifier()
            cid = payload.get("id", "")
            if classifier.remove_classifier(cid):
                json_response(self, {"success": True})
            else:
                json_response(self, {"error": "المصنف غير موجود"}, status=404)
            return
        if path == "/api/classify":
            # تصنيف إعلان أو مجموعة إعلانات
            from backend.services.listing_classifier import get_classifier
            classifier = get_classifier()
            listings = payload.get("listings", [])
            if not listings:
                json_response(self, {"error": "حدد إعلانات للتصنيف"}, status=400)
                return
            results = classifier.classify_batch(listings)
            from dataclasses import asdict
            json_response(self, {
                "results": [asdict(r) for r in results],
                "count": len(results)
            })
            return
        if path == "/api/classify/stats":
            # إحصائيات التصنيف
            from backend.services.listing_classifier import get_classifier
            classifier = get_classifier()
            json_response(self, classifier.get_statistics())
            return
        if path == "/api/classify/export":
            # تصدير التصنيفات
            from backend.services.listing_classifier import get_classifier
            classifier = get_classifier()
            json_response(self, {"classifications": classifier.export_classifications()})
            return
        
        # ─── إدارة الأدوار والصلاحيات ───
        if path == "/api/roles":
            # جلب قائمة الأدوار والصلاحيات
            from backend.services.accounts import ROLES
            json_response(self, {"roles": ROLES})
            return
        if path == "/api/user/role":
            # جلب/تحديث دور المستخدم
            from backend.services.accounts import ROLES, check_role_permission
            from backend.services.supabase_store import fetch_user, patch_user
            phone_raw = payload.get("phone") or self.headers.get("X-User-Phone", "")
            role = payload.get("role") or ""
            if phone_raw:
                phone, _ = normalize_phone(phone_raw)
                user = fetch_user(phone)
                if role and role in ROLES:
                    patch_user(phone, {"role": role})
                    json_response(self, {"status": "ok", "role": role})
                else:
                    user_role = (user or {}).get("role", "user")
                    json_response(self, {"role": user_role, "permissions": ROLES.get(user_role, {}).get("permissions", [])})
            else:
                json_response(self, {"error": "missing_phone"}, status=400)
            return
        if path == "/api/user/role/check":
            # التحقق من صلاحية معينة
            from backend.services.accounts import ROLES, check_role_permission
            from backend.services.supabase_store import fetch_user
            phone_raw = payload.get("phone") or self.headers.get("X-User-Phone", "")
            permission = payload.get("permission") or ""
            if phone_raw and permission:
                phone, _ = normalize_phone(phone_raw)
                user = fetch_user(phone)
                user_role = (user or {}).get("role", "user")
                allowed = check_role_permission(user_role, permission)
                json_response(self, {"allowed": allowed, "role": user_role, "permission": permission})
            else:
                json_response(self, {"error": "missing_fields"}, status=400)
            return

        # ─── إدارة الخطط والأسعار ───
        if path == "/api/tiers":
            # جلب قائمة الخطط والأسعار
            from backend.services.tier import list_tiers
            json_response(self, {"tiers": list_tiers()})
            return
        if path == "/api/tier/current":
            # جلب خطة المستخدم الحالية
            from backend.services.server_tier import get_user_tier, get_tier_limits
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            user_id = user["user_id"] if user else ""
            if user_id:
                tier_limits = get_tier_limits(user_id)
                json_response(self, tier_limits)
            else:
                json_response(self, {"tier": "anonymous", "features": {}})
            return
        if path == "/api/tier/upgrade":
            # ترقية خطة المستخدم
            from backend.services.server_tier import upgrade_user
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            user = extract_user_from_token(token)
            user_id = user["user_id"] if user else ""
            new_tier = payload.get("tier") or ""
            if user_id and new_tier:
                result = upgrade_user(user_id, new_tier)
                json_response(self, result)
            else:
                json_response(self, {"error": "missing_user_or_tier"}, status=400)
            return

        json_response(self, {"error": "Unknown endpoint"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return


def _warm_opportunities_cache() -> None:
    """تسخين كاش الفرص عند الإقلاع في خيط خلفي: يقرأ آخر لقطة محفوظة من Supabase
    فيكون أول طلب لتبويب «أفضل الفرص» (ولقطة الفرص في اللوحة) فوريًا بدل دفع
    ~0.8 ثانية لقراءة القاعدة. لا يبطئ الإقلاع ولا يكسر التشغيل عند غياب القاعدة."""
    try:
        from backend.services.supabase_store import fetch_latest_opportunities
        snapshot = fetch_latest_opportunities()
        if snapshot:
            global _OPPORTUNITIES_CACHE, _OPPORTUNITIES_CACHE_AT
            _OPPORTUNITIES_CACHE = snapshot
            _OPPORTUNITIES_CACHE_AT = time.time()
    except Exception as exc:
        logger.warning("Startup opportunities warm skipped: %s", exc)


def main() -> None:
    # تسخين خلفي بلا انتظار: الخادم يبدأ فورًا والكاش يمتلئ في نفس اللحظات الأولى
    _threading.Thread(target=_warm_opportunities_cache, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logger.info("Alforaij Research Assistant running on http://%s:%s", HOST, PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
