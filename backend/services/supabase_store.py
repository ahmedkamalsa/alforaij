from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from backend.connectors.alforaij import load_listings
from backend.models import Listing, PropertyRequest
from backend.services import market_analysis
from backend.services.source_registry import resolve_source_id

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def remote_reads_enabled() -> bool:
    if "unittest" in sys.modules and os.getenv("ALFORAIJ_TEST_ALLOW_SUPABASE") != "1":
        return False
    return is_configured()


def _headers(prefer: str = "return=minimal") -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _post(table: str, rows: list[dict[str, Any]], *, upsert: bool = False, conflict: str = "") -> None:
    if not rows or not is_configured():
        return
    query = f"?on_conflict={urllib.parse.quote(conflict)}" if upsert and conflict else ""
    endpoint = f"{SUPABASE_URL}/rest/v1/{table}{query}"
    prefer = "resolution=merge-duplicates,return=minimal" if upsert else "return=minimal"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=_headers(prefer),
    )
    # إعادة محاولة واحدة عند تعطل الكتابة الشبكي العابر (write operation timed out)
    # — الوكيل اليومي يكتب دفعات كبيرة وتُحل الشبكة المتقطعة بالتكرار بدل فشل الدورة كاملة.
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status not in {200, 201, 204}:
                    raise RuntimeError(f"Supabase returned HTTP {response.status}")
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.exception("Supabase %s write failed: HTTP %s %s", table, exc.code, detail)
            raise RuntimeError(f"Supabase {table} write failed: HTTP {exc.code} {detail}") from exc
        except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as exc:
            if attempt == 0:
                logger.warning("Supabase %s write timeout (attempt 1/2), retrying: %s", table, exc)
                time.sleep(2)
                continue
            logger.exception("Supabase %s write failed after retry", table)
            raise
        except Exception:
            logger.exception("Supabase %s write failed", table)
            raise


def _patch(table: str, filters: dict[str, str], payload: dict[str, Any]) -> None:
    """تحديث صفوف حسب فلاتر REST (مثل status=neq.stale&last_seen_at=lt.ISO)."""
    if not is_configured():
        return
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in filters.items())
    endpoint = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="PATCH",
        headers=_headers("count=exact"),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in {200, 204}:
                raise RuntimeError(f"Supabase PATCH {table} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.exception("Supabase %s update failed: HTTP %s %s", table, exc.code, detail)
        raise RuntimeError(f"Supabase {table} update failed: HTTP {exc.code} {detail}") from exc
    except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as exc:
        logger.exception("Supabase %s update failed", table)
        raise
def listing_row(listing: Listing) -> dict[str, Any]:
    published_date = listing.published_date or None
    return {
        "code": listing.code,
        "source": listing.source,
        "transaction_type": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "property_type": listing.property_type,
        "detail_class": listing.detail_class,
        "price": listing.price,
        "price_text": listing.price_text,
        "space": listing.space,
        "listing_mode": listing.listing_mode,
        "summary": listing.summary,
        "features": listing.features,
        "published_date": published_date,
        "original_url": listing.original_url,
        "raw": listing.raw,
    }


def save_listings(listings: list[Listing]) -> None:
    rows = [listing_row(listing) for listing in listings if listing.code]
    for index in range(0, len(rows), 250):
        _post("listings", rows[index:index + 250], upsert=True, conflict="code")


def save_report(request: PropertyRequest, report: dict[str, Any]) -> None:
    _post(
        "saved_reports",
        [
            {
                "request_text": request.raw_text,
                "extracted_request": asdict(request),
                "report": report,
            }
        ],
    )


def save_search_history(request: PropertyRequest, report: dict[str, Any], statuses: list[dict[str, Any]]) -> None:
    """حفظ سجل بحث عملي مستقل عن التقرير الكامل.

    الجدول اختياري: لو لم تُطبّق migration بعد لا نكسر التحليل، لأن saved_reports
    يظل يحفظ التقرير الكامل. الغرض من search_history هو بناء مؤشرات الاستخدام
    لاحقًا: أكثر المناطق طلبًا، أكثر الأنواع بحثًا، أفضل نتيجة لكل طلب، وحالة المصادر.
    """
    results = report.get("results") or []
    top = results[0] if results else {}
    source_summary = [
        {
            "name": status.get("name"),
            "status": status.get("status"),
            "records": status.get("records"),
            "candidates": status.get("candidates"),
            "trust": status.get("trust"),
        }
        for status in statuses
    ]
    try:
        _post(
            "search_history",
            [
                {
                    "request_text": request.raw_text,
                    "transaction_type": request.transaction,
                    "property_type": request.property_type,
                    "areas": request.areas,
                    "governorates": request.governorates,
                    "result_count": len(results),
                    "top_code": top.get("code"),
                    "top_source": top.get("source"),
                    "top_area": top.get("area"),
                    "top_price": top.get("price"),
                    "top_recommendation": top.get("recommendationScore"),
                    "top_data_quality": top.get("dataQuality"),
                    "source_summary": source_summary,
                    "report_summary": report.get("summary"),
                }
            ],
        )
    except RuntimeError as exc:
        logger.warning("search_history save skipped: %s", exc)


def save_source_runs(request: PropertyRequest, statuses: list[dict[str, Any]]) -> None:
    rows = []
    for status in statuses:
        source_name = str(status.get("name") or "")
        rows.append(
            {
                "source_id": resolve_source_id(source_name),
                "request_text": request.raw_text,
                "request_json": asdict(request),
                "status": status.get("status") or "unknown",
                "records_found": int(status.get("candidates") or status.get("records") or 0),
                "records_scored": int(status.get("records") or 0),
                "response_ms": status.get("responseMs"),
                "source_url": status.get("url"),
                "note": status.get("note"),
                "error": status.get("error"),
            }
        )
    _post("source_runs", rows)


def save_listing_evidence(report: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for item in report.get("results", []):
        source_id = resolve_source_id(str(item.get("source") or ""))
        number_sources = item.get("numberSources") or {}
        for field_name, source in number_sources.items():
            if not isinstance(source, dict):
                continue
            rows.append(
                {
                    "listing_code": item.get("code"),
                    "source_id": source_id,
                    "evidence_type": "field_source",
                    "evidence_url": item.get("originalUrl"),
                    "field_name": field_name,
                    "field_value": str(source.get("display") or source.get("value") or ""),
                    "confidence": item.get("confidence"),
                    "raw": source,
                }
            )
    for index in range(0, len(rows), 250):
        _post("listing_evidence", rows[index:index + 250])


def _parse_price(value: Any) -> float | None:
    """تحويل السعر إلى رقم حقيقي (الواجهة ترسله كنص من input)."""
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def save_official_transactions(rows: list[dict[str, Any]]) -> None:
    """حفظ/تحديث صفقات رسمية في جدول official_transactions (upsert على reference)."""
    if not is_configured():
        return
    cleaned = []
    for row in rows:
        reference = row.get("reference") or row.get("رقم الصفقة") or ""
        if not reference:
            continue
        price = row.get("price") or row.get("السعر")
        space = row.get("space") or row.get("المساحة")
        cleaned.append(
            {
                "reference": str(reference),
                "area": row.get("area") or row.get("المنطقة") or "",
                "property_type": row.get("property_type") or row.get("نوع العقار") or "",
                "transaction_type": row.get("transaction_type") or "للبيع",
                "price": _parse_price(price),
                "space": _parse_price(space),
                "date": row.get("date") or row.get("التاريخ") or None,
                "original_url": row.get("original_url") or row.get("url") or "",
                "source_note": row.get("source_note") or row.get("ملاحظة") or "",
            }
        )
    for index in range(0, len(cleaned), 250):
        _post("official_transactions", cleaned[index:index + 250], upsert=True, conflict="reference")


def _fetch_rows(endpoint: str) -> list[dict[str, Any]]:
    """قراءة صفوف من Supabase بأمان: يعيد [] عند غياب الضبط أو أي فشل (لا يكسر التحليل)."""
    if not remote_reads_enabled():
        return []
    request = urllib.request.Request(endpoint, method="GET", headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Supabase read failed: %s", exc)
    return []


def _table_count(table: str) -> dict[str, Any]:
    """عدد صفوف جدول Supabase بدون تحميل البيانات.

    يعيد حالة واضحة بدل كسر التطبيق عند غياب جدول اختياري أو عدم اكتمال السكيما.
    """
    if not is_configured():
        return {"available": False, "count": None, "status": "not_configured"}
    endpoint = f"{SUPABASE_URL}/rest/v1/{table}?select=id&limit=1"
    request = urllib.request.Request(endpoint, method="GET", headers=_headers("count=exact"))
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            content_range = response.headers.get("Content-Range", "")
            total = None
            if "/" in content_range:
                raw_total = content_range.rsplit("/", 1)[-1]
                if raw_total.isdigit():
                    total = int(raw_total)
            return {"available": True, "count": total, "status": "ok"}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "available": False,
            "count": None,
            "status": f"http_{exc.code}",
            "detail": detail[:240],
        }
    except Exception as exc:
        return {"available": False, "count": None, "status": "failed", "detail": str(exc)[:240]}


def supabase_data_summary(local_records: int = 0) -> dict[str, Any]:
    """خريطة مختصرة لمصادر البيانات الفعلية والمخططة داخل Supabase."""
    tables = {
        "listings": "إعلانات الفريج/المصادر المحفوظة",
        "market_listings": "إعلانات السوق الخارجية المحصودة من كل المواقع",
        "price_trends": "اتجاهات الأسعار الشهرية (وسيط لكل منطقة/نوع)",
        "market_ads": "إعلانات السوق الحية من المواقع/لوحات العرض",
        "official_transactions": "صفقات رسمية مستوردة",
        "official_market_indicators": "مؤشرات سعرية رسمية/مرجعية",
        "saved_reports": "تقارير بحث وتقييم محفوظة",
        "source_runs": "سجل تشغيل المصادر",
        "listing_evidence": "دليل كل رقم داخل النتائج",
        "client_leads": "عملاء محتملون",
        "client_property_requests": "طلبات عملاء من لوحة العرض",
        "opportunities": "لقطات فرص محفوظة",
        "search_history": "سجل بحث مختصر",
    }
    details = {
        table: {"label": label, **_table_count(table)}
        for table, label in tables.items()
    }
    return {
        "configured": is_configured(),
        "localAlforaijRecords": local_records,
        "tables": details,
        "note": (
            "قاعدة البيانات هدفها تجميع كل المصادر. رقم الفريج المحلي هو خط أساس فقط؛ "
            "المصادر الخارجية والرسمية تدخل عندما توجد صفوف منظمة في جداولها أو في أدلة التقرير."
        ),
    }


def fetch_official_transactions() -> list[dict[str, Any]]:
    """قراءة كل الصفقات الرسمية (أحدث أولًا)."""
    return _fetch_rows(f"{SUPABASE_URL}/rest/v1/official_transactions?select=*&order=date.desc.nullslast&limit=2000")


def save_client(client: dict[str, Any]) -> None:
    """حفظ/تحديث عميل محتمل في جدول client_leads (upsert على رقم الهاتف)."""
    if not is_configured():
        return
    _post(
        "client_leads",
        [
            {
                "phone": str(client.get("phone") or client.get("phones") or ""),
                "area": client.get("area") or "",
                "type": client.get("type") or "",
                "price": _parse_price(client.get("price")),
                "note": client.get("note") or "",
            }
        ],
        upsert=True,
        conflict="phone",
    )


def fetch_clients() -> list[dict[str, Any]]:
    """قراءة كل العملاء المحتملين من Supabase (أحدث أولًا)."""
    return _fetch_rows(f"{SUPABASE_URL}/rest/v1/client_leads?select=*&order=created_at.desc")


def fetch_opportunity_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    """قراءة لقطات الفرص التاريخية (أحدث أولًا) لأرشفة الأداء وتتبع التغيرات."""
    return _fetch_rows(f"{SUPABASE_URL}/rest/v1/opportunities?select=*&order=generated_at.desc&limit={int(limit)}")


def fetch_latest_opportunities() -> dict[str, Any] | None:
    """قراءة آخر لقطة فرص محفوظة (أحدث generated_at) — احتياط عند برودة الكاش أو فشل البناء."""
    rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/opportunities?select=*&order=generated_at.desc&limit=1")
    if not rows:
        return None
    row = rows[0]
    tiers = row.get("tiers") or {}
    forecast = row.get("forecast") or []
    if not tiers and not forecast:
        return None
    return {
        "generatedAt": row.get("generated_at") or "",
        "generatedDate": (row.get("generated_at") or "").replace("T", " ")[:16],
        "totalListings": row.get("total_listings") or 0,
        "totalScored": row.get("total_scored") or 0,
        "tiers": tiers,
        "forecast": forecast,
        "note": row.get("note") or "",
        "fromSupabase": True,
    }


def save_opportunities(snapshot: dict[str, Any]) -> None:
    """حفظ لقطة الفرص اليومية (تحديث أول بأول) في جدول opportunities."""
    if not is_configured():
        return
    # snapshot_date يحمل طابعًا زمنيًا كاملًا حتى يحتفظ التاريخ بكل تحديث (أول بأول)
    _post(
        "opportunities",
        [
            {
                "snapshot_date": str(snapshot.get("generatedAt") or snapshot.get("generatedDate") or ""),
                "generated_at": snapshot.get("generatedAt") or "",
                "total_listings": int(snapshot.get("totalListings") or 0),
                "total_scored": int(snapshot.get("totalScored") or 0),
                "tiers": snapshot.get("tiers") or {},
                "forecast": snapshot.get("forecast") or [],
                "note": snapshot.get("officialDataNote") or "",
            }
        ],
        upsert=True,
        conflict="snapshot_date",
    )



# ─── market_ads (البيانات الحية من لوحة العرض) ─────────────────────


def fetch_market_ads(
    transaction: str | None = None,
    property_type: str | None = None,
    region: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """قراءة الإعلانات الحية من جدول market_ads (لوحة العرض) مع فلاتر اختيارية.

    الفلاتر تُطبق في REST API لتقليل حجم البيانات المنقولة. المنطقة تُقارن
    كـ `ilike.*{region}*` للبحث المرن (العربية والإنجليزية).
    """
    if not is_configured():
        return []
    params: list[str] = [f"limit={int(limit)}"]
    if transaction:
        # نحدد نوع العملية بتصفية listing_status (السوق المباشر كلها active)
        params.append("listing_status=eq.active")
    if property_type:
        pt_map = {"بيت": "private_residential", "شقة": "apartment", "أرض": "land", "عمارة": "building"}
        mapped = pt_map.get(property_type, property_type)
        encoded_pt = urllib.parse.quote(mapped)
        params.append(f"or=(property_type.eq.{encoded_pt},property_type.ilike.*{encoded_pt}*)")
    if region:
        # ترميز المنطقة (عربية/إنجليزية) في كل موضع — إدراجها خامًا يكسر urllib بخطأ ascii
        encoded_region = urllib.parse.quote(region)
        params.append(f"or=(region.ilike.*{encoded_region}*,title.ilike.*{encoded_region}*)")
    params.append("order=fetched_at.desc")
    endpoint = f"{SUPABASE_URL}/rest/v1/market_ads?{'&'.join(params)}"
    return _fetch_rows(endpoint)


def save_market_ads(rows: list[dict[str, Any]]) -> None:
    """حفظ إعلانات جديدة في market_ads (upsert على source_listing_id)."""
    _post("market_ads", rows, upsert=True, conflict="source_listing_id")


def save_market_listings(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """حفظ إعلانات السوق الخارجية المحصودة في جدول market_listings (upsert على code).

    كل إعلان يظهر في الحصاد يُختم بـ last_seen_at=now() و status=active — فيردّ
    الإعلان الذي عاد بعد كسح سابق إلى النشط تلقائيًا (الكسح يوسم stale فقط).
    متسامح تمامًا: غياب الجدول أو تعذر الكتابة لا يكسر التشغيل اليومي — يُسجَّل السبب
    ويعود status حتى يظهر في تقرير الوكيل (خطوة persist_market_listings).
    """
    if not rows:
        return {"status": "empty", "count": 0, "error": ""}
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    now_iso = datetime.now(timezone.utc).isoformat()
    stamped = [{**row, "last_seen_at": now_iso, "status": "active"} for row in rows]
    try:
        for index in range(0, len(stamped), 250):
            _post("market_listings", stamped[index:index + 250], upsert=True, conflict="code")
        return {"status": "saved", "count": len(stamped), "error": ""}
    except RuntimeError as exc:
        logger.warning("market_listings save failed: %s", exc)
        return {"status": "failed", "count": 0, "error": str(exc)}
    except Exception:
        logger.exception("market_listings save failed")
        return {"status": "failed", "count": 0, "error": "unexpected error"}


def record_listing_price_history(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """تسجيل سعر كل إعلان عند ظهوره في الحصاد (سجل سعر العقار، append-only).

    يكتب صفًا واحدًا لكل إعلان يحمل سعرًا صالحًا — خط زمني يتراكم يوميًا عبر
    الوكيل (بعد persist_market_listings). الصفوف المتكررة داخل الدفعة نفسها
    (نفس code) تُطوى على آخرها، والصفوف بلا كود أو بلا سعر تُتجاهل. متسامح
    تمامًا كبقية الحفظ: غياب الجدول أو تعذر الكتابة يُسجَّل ولا يكسر اليومي.
    """
    if not rows:
        return {"status": "empty", "count": 0, "error": ""}
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    now_iso = datetime.now(timezone.utc).isoformat()
    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "").strip()
        if not code or code == "STATIC":
            continue
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if not price or price <= 0:
            continue
        by_code[code] = {
            "code": code,
            "source": row.get("source"),
            "area": row.get("area"),
            "property_type": row.get("property_type"),
            "transaction": row.get("transaction"),
            "price": price,
            "price_text": row.get("price_text"),
            "seen_at": now_iso,
        }
    clean = list(by_code.values())
    if not clean:
        return {"status": "empty", "count": 0, "error": ""}
    try:
        for index in range(0, len(clean), 250):
            _post("listing_price_observations", clean[index:index + 250])
        return {"status": "saved", "count": len(clean), "error": ""}
    except RuntimeError as exc:
        logger.warning("listing_price_history save failed: %s", exc)
        return {"status": "failed", "count": 0, "error": str(exc)}
    except Exception:
        logger.exception("listing_price_history save failed")
        return {"status": "failed", "count": 0, "error": "unexpected error"}


def _stale_cutoff(days: int) -> str:
    """حد الكسح: الآن ناقص days — بصيغة ISO توقيت عالمي (تُقارن مع timestamptz)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def mark_stale_market_listings(days: int = 14) -> dict[str, Any]:
    """كسح الإعلانات القديمة: يوسم stale كل صف لم يُرَ منذ days يومًا.

    لا يحذف شيئًا — يبقى الصف في قاعدة المعرفة للتاريخ/التقييم، لكن اللوحة
    والفرص والمؤشرات تقرأ active فقط. يَعود active تلقائيًا عند ظهور الإعلان
    مجددًا في حصاد لاحق (ختم save_market_listings). متسامح تمامًا مثل بقية
    الحفظ: الفشل يُسجَّل ولا يكسر التشغيل اليومي.
    """
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    cutoff = _stale_cutoff(days)
    try:
        _patch(
            "market_listings",
            {"status": "neq.stale", "last_seen_at": f"lt.{cutoff}"},
            {"status": "stale"},
        )
        return {"status": "swept", "days": days, "cutoff": cutoff, "error": "", "count": None}
    except RuntimeError as exc:
        logger.warning("market_listings stale sweep failed: %s", exc)
        return {"status": "failed", "days": days, "error": str(exc)}
    except Exception:
        logger.exception("market_listings stale sweep failed")
        return {"status": "failed", "days": days, "error": "unexpected error"}


# ─── price_trends (اتجاهات الأسعار الشهرية من الحصاد) ────────────────


def save_price_trends(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """حفظ/تحديث اتجاهات الأسعار الشهرية في جدول price_trends (upsert على الخلية).

    كل صف وسيط شهري لخلية (منطقة × نوع × شهر × معاملة). المفتاح المركّب
    (area, property_type, month, transaction) يجعل إعادة التشغيل في الشهر نفسه
    تحديثًا لا تكرارًا. متسامح تمامًا: غياب الجدول أو تعذر الكتابة يُسجَّل السبب
    ولا يكسر التشغيل اليومي.
    """
    if not rows:
        return {"status": "empty", "count": 0, "error": ""}
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    try:
        for index in range(0, len(rows), 250):
            _post("price_trends", rows[index:index + 250], upsert=True, conflict="area,property_type,month,transaction")
        return {"status": "saved", "count": len(rows), "error": ""}
    except RuntimeError as exc:
        logger.warning("price_trends save failed: %s", exc)
        return {"status": "failed", "count": 0, "error": str(exc)}
    except Exception:
        logger.exception("price_trends save failed")
        return {"status": "failed", "count": 0, "error": "unexpected error"}


# ─── market_developments (تطورات السوق من وكيل الاكتشاف) ────────────────


def save_market_developments(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """حفظ تطورات السوق المكتشفة في جدول market_developments (upsert على url).

    متسامح تمامًا كبقية الحفظ: غياب الجدول أو تعذر الكتابة يُسجَّل السبب ولا
    يكسر التشغيل اليومي — التطورات تبقى متاحة محليًا عبر data/market_developments.json.
    """
    if not rows:
        return {"status": "empty", "count": 0, "error": ""}
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    try:
        for index in range(0, len(rows), 250):
            _post("market_developments", rows[index:index + 250], upsert=True, conflict="url")
        return {"status": "saved", "count": len(rows), "error": ""}
    except RuntimeError as exc:
        logger.warning("market_developments save failed: %s", exc)
        return {"status": "failed", "count": 0, "error": str(exc)}
    except Exception:
        logger.exception("market_developments save failed")
        return {"status": "failed", "count": 0, "error": "unexpected error"}


def fetch_market_developments(limit: int = 100) -> list[dict[str, Any]]:
    """أحدث تطورات السوق من market_developments (الأحدث أولًا)."""
    if not is_configured():
        return []
    endpoint = f"{SUPABASE_URL}/rest/v1/market_developments?select=*&order=fetched_at.desc&limit={int(limit)}"
    return _fetch_rows(endpoint)


def price_trends_table_available() -> bool:
    """هل جدول price_trends موجود فعلًا؟ (فحص خفيف دون كشف الأخطاء)."""
    if not is_configured():
        return False
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/price_trends?select=id&limit=1",
        method="GET",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception:
        return False


def fetch_price_trends(
    area: str | None = None,
    property_type: str | None = None,
    transaction: str | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """قراءة اتجاهات الأسعار الشهرية (أحدث شهر أولًا) مع فلاتر اختيارية.

    تُستخدم لتغذية الرسوم الزمنية في تبويب الأداء: وسيط سعر المتر لكل منطقة
    عبر الأشهر. متسامح تمامًا: غياب الجدول أو فشل القراءة يعيد [].
    """
    if not price_trends_table_available():
        return []
    params: list[str] = [f"limit={int(limit)}"]
    if area:
        params.append(f"area=ilike.*{urllib.parse.quote(area)}*")
    if property_type:
        params.append(f"property_type=ilike.*{urllib.parse.quote(property_type)}*")
    if transaction:
        params.append(f"transaction=ilike.*{urllib.parse.quote(transaction)}*")
    params.append("order=month.desc")
    return _fetch_rows(f"{SUPABASE_URL}/rest/v1/price_trends?{'&'.join(params)}")


def market_listings_table_available() -> bool:
    """هل جدول market_listings موجود فعلًا؟ (فحص خفيف دون كشف الأخطاء)."""
    if not is_configured():
        return False
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/market_listings?select=code&limit=1",
        method="GET",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception:
        return False


def dedupe_market_listings(min_title_len: int = 12) -> dict[str, Any]:
    """كسح شبه التكرار بحذر: يوسم duplicate كل إعلان مطابق (مصدر+منطقة+نوع+سعر+
    عنوان مطبع) لنظيره المحتفظ به — مع بوابات دقة (هاتف/مساحة/طول عنوان).

    لا يحذف شيئًا: يضبط status=duplicate و duplicate_of على غير النظير فقط،
    ويبقى التاريخ كاملًا. متسامح تمامًا مثل بقية الحفظ: أي فشل يُسجَّل ولا يكسر
    التشغيل اليومي.
    """
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    try:
        # ترقيم صفحات كامل (Supabase يسقف عند 1000 صف/طلب) — يشمل كل النشط
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = fetch_market_listings(limit=1000, offset=offset) or []
            rows.extend(page)
            if len(page) < 1000:
                break
            offset += 1000
        if not rows:
            return {"status": "deduped", "groups": 0, "marked": 0, "error": ""}
        from backend.services.listing_dedupe import build_dedupe_groups, duplicate_marks

        groups = build_dedupe_groups(rows, min_title_len=min_title_len)
        marks = duplicate_marks(groups)
        marked = 0
        for mark in marks:
            _patch(
                "market_listings",
                {"code": f"eq.{mark['code']}"},
                {"status": "duplicate", "duplicate_of": mark["duplicate_of"]},
            )
            marked += 1
        return {"status": "deduped", "groups": len(groups), "marked": marked, "error": ""}
    except RuntimeError as exc:
        logger.warning("market_listings dedupe failed: %s", exc)
        return {"status": "failed", "error": str(exc)}
    except Exception:
        logger.exception("market_listings dedupe failed")
        return {"status": "failed", "error": "unexpected error"}


def fetch_market_listings(
    area: str | None = None,
    transaction: str | None = None,
    property_type: str | None = None,
    source: str | None = None,
    limit: int = 500,
    status: str | None = "active",
    offset: int = 0,
) -> list[dict[str, Any]]:
    """قراءة إعلانات السوق الخارجية المحصودة من جدول market_listings.

    الفلاتر اختيارية وتُطبق في REST API لتقليل البيانات المنقولة.
    الافتراضي status='active' يستبعد الإعلانات المباعة/المنتهية (stale) من
    اللوحة والفرص؛ مرِّر status=None لقراءة كامل قاعدة المعرفة.
    offset يسمح بترقيم الصفحات (Supabase يسقف النتيجة عند 1000 صف/طلب).
    """
    if not is_configured():
        return []
    params: list[str] = [f"limit={int(limit)}"]
    if offset:
        params.append(f"offset={int(offset)}")
    if status:
        params.append(f"status=eq.{urllib.parse.quote(status)}")
    if area:
        params.append(f"area=ilike.*{urllib.parse.quote(area)}*")
    if transaction:
        params.append(f"transaction=ilike.*{urllib.parse.quote(transaction)}*")
    if property_type:
        params.append(f"property_type=ilike.*{urllib.parse.quote(property_type)}*")
    if source:
        params.append(f"source=ilike.*{urllib.parse.quote(source)}*")
    params.append("order=fetched_at.desc")
    endpoint = f"{SUPABASE_URL}/rest/v1/market_listings?{'&'.join(params)}"
    return _fetch_rows(endpoint)


def fetch_demand_indicators(limit: int = 8000) -> dict[str, Any]:
    """مؤشرات الطلب: عدّ طلبات الشراء/الإيجار (من الفريج المحلي) لكل منطقة + اتجاه.

    غلاف رفيع فوق build_demand_indicators — متسامح: بلا طلبات يعيد عدّادات
    صفرية مع tableOk: False حتى تُعرض الواجهة رسالة واضحة.
    """
    rows = _analysis_rows(limit, "market_listings")
    built = market_analysis.build_demand_indicators(rows)
    return {
        "tableOk": built["totals"]["total"] > 0,
        "fetchedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "طلبات الشراء والإيجار من إعلانات «مطلوب» المحلية (الفريج) والمحصودة من المنصات الخارجية (مثل قسم «مطلوب» في 4Sale) — ميزانية الطلب ليست سعر عرض، لذا تُعدّ هنا ولا تدخل وسيطات السوق.",
        **built,
    }


def fetch_external_demand_rows(limit: int = 3000) -> list[dict[str, Any]]:
    """سجلات «مطلوب» المحصودة من المنصات الخارجية (market_listings) كصفوف.

    تُدمج مع طلبات الفريج المحلية في مؤشر الطلب بجانب نتائج التقييم حتى يعكس
    المؤشر كل المنصات لا الفريج فقط (4Sale ينشر قسم «مطلوب عقار»).
    متسامح: غياب الجدول أو فشل القراءة يعيد [] بدل كسر الطلب.
    """
    if not market_listings_table_available():
        return []
    try:
        rows = _fetch_rows(
            f"{SUPABASE_URL}/rest/v1/market_listings?select=*&order=fetched_at.desc&limit={int(limit)}"
        ) or []
        return [r for r in rows if market_analysis.is_demand_transaction(str(r.get("transaction") or ""))]
    except Exception as exc:
        logger.warning("External demand rows failed: %s", exc)
        return []


def fetch_market_listing_source_counts(limit: int = 5000) -> list[dict[str, Any]]:
    """عدّاد لكل موقع من market_listings (العمود source فقط — استعلام خفيف).

    يعيد قائمة مرتبة تنازليًا [{source, count}, ...] ليُعرض توزيع إعلانات المواقع
    في ترويسة الموقع. متسامح تمامًا: غياب الجدول أو فشل القراءة يعيد [] بدل كسر الطلب.
    """
    if not market_listings_table_available():
        return []
    try:
        rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/market_listings?select=source&limit={int(limit)}")
    except Exception as exc:
        logger.warning("Market listing source counts failed: %s", exc)
        return []
    counts: dict[str, int] = {}
    for row in rows or []:
        src = str(row.get("source") or "غير محدد").strip() or "غير محدد"
        counts[src] = counts.get(src, 0) + 1
    return [
        {"source": src, "count": n}
        for src, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]


def _analysis_rows(limit: int, table: str) -> list[dict[str, Any]]:
    """صفوف التحليل = حصاد القاعدة (إن توفرت) + الفريج المحلي — عرضًا وطلبًا.

    الفريج المحلي (لوحة الإعلانات المحلية) يحمل طلبات الشراء والإيجار التي لا
    توجد في حصاد المواقع الخارجية؛ دمجهما في لقطة واحدة يجعل التحليل يرى كامل
    السوق. متسامح: فشل أي من المصدرين لا يمنع الآخر.
    """
    rows: list[dict[str, Any]] = []
    # نفس تطبيع اللوحة المعتمد (backend/services/request_parser.normalize_dashboard_place):
    # سدّ المنطقة الناقصة أو المُلتقطة خطأً كاسم محافظة من نص الإعلان، ثم المحافظة
    # من الخريطة الدقيقة (AREA_TO_GOVERNORATE) بالصيغ الكنسية — حتى تبنى تحليلات
    # السوق دلاءها من نفس خريطة اللوحة تمامًا (لا «محافظة الاحمدي» بلا همزة بجانب
    # «محافظة الأحمدي»، ولا دلو المحافظة نفسها منقسمة بين صيغة قصيرة وأخرى كاملة).
    from backend.services.request_parser import area_governorate_map, normalize_dashboard_place
    area_map = area_governorate_map([])
    if market_listings_table_available():
        # active فقط: الإعلانات المباعة/المنتهية (stale) لا تدخل المؤشرات ولا الوسيطات
        endpoint = f"{SUPABASE_URL}/rest/v1/{table}?select=*&status=eq.active&order=fetched_at.desc&limit={int(limit)}"
        rows = _fetch_rows(endpoint) or []
        for row in rows:
            # keep_governorate_area: تحليلات السوق تحتاج اسم المنطقة للبقاء حتى لو
            # كان اسم محافظة («حولي» كمنطقة) — إحصائيات لكل منطقة بخلاف اللوحة.
            normalize_dashboard_place(row, area_map, keep_governorate_area=True)
    try:
        local_rows = market_analysis.local_listings_to_rows(load_listings())
        for row in local_rows:
            normalize_dashboard_place(row, area_map, keep_governorate_area=True)
        rows.extend(local_rows)
    except Exception as exc:
        logger.warning("Market analysis local rows failed: %s", exc)
    return rows


def fetch_market_analytics(limit: int = 5000) -> dict[str, Any]:
    """تحليلات الحصاد المتراكم من market_listings + الفريج المحلي لكل موقع.

    غلاف رفيع: يجلب الصفوف من القاعدة والفريج المحلي، ثم يفوض التجميع للوحدة
    النقية market_analysis.build_market_analytics (تُختبر بقوائم عادية).
    متسامح تمامًا: غياب كلا المصدرين يعيد حالة واضحة بدل كسر الطلب.
    """
    empty = {
        "tableOk": False,
        "note": "لا توجد بيانات بعد — شغّل الوكيل اليومي (حصاد المواقع) أو انتظر لوحة الفريج المحلية.",
        "totals": {"rows": 0, "sources": 0, "areas": 0, "governorates": 0, "transactions": 0, "propertyTypes": 0, "demand": {"buyRequests": 0, "rentRequests": 0}},
        "sources": [],
        "areas": [],
    }
    rows = _analysis_rows(limit, "market_listings")
    if not rows:
        return empty
    built = market_analysis.build_market_analytics(rows)
    return {
        "tableOk": True,
        "fetchedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "تحليلات الحصاد المتراكم من market_listings + الفريج المحلي (عرضًا وطلبًا) — كل إعلان يحمل original_url كدليل قابل للفتح.",
        **built,
    }


def fetch_market_insights(limit: int = 8000) -> dict[str, Any]:
    """تحليلات السوق الموجة 1: عائد الإيجار واتجاه سعر المتر لكل منطقة.

    غلاف رفيع: يجلب الصفوف من القاعدة والفريج المحلي، ثم يفوض التجميع للوحدة
    النقية market_analysis.build_market_insights (تُختبر بقوائم عادية).
    متسامح تمامًا: غياب كلا المصدرين يعيد حالة واضحة بدل كسر الطلب.
    """
    empty = {
        "tableOk": False,
        "note": "لا توجد بيانات بعد — شغّل الوكيل اليومي (حصاد المواقع) أو انتظر لوحة الفريج المحلية.",
        "areas": [],
        "series": [],
        "governorates": [],
    }
    rows = _analysis_rows(limit, "market_listings")
    if not rows:
        return empty
    built = market_analysis.build_market_insights(rows)
    return {
        "tableOk": True,
        "fetchedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "عائد الإيجار = (وسيط الإيجار × 12) ÷ وسيط سعر البيع من الحصاد المتراكم + الفريج المحلي (عرضًا وطلبًا) بعد استبعاد القيم الشاذة (3×IQR).",
        **built,
    }


def fetch_official_indicators(region: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """قراءة مؤشرات السوق الرسمية (أسعار المتر المرجعية) من جدول official_market_indicators.

    يعيد المؤشر الأحدث لكل منطقة (مرتب بـ updated_at نازلًا).
    """
    if not is_configured():
        return []
    if region:
        where = f"?region=ilike.*{urllib.parse.quote(region)}*&order=updated_at.desc&limit={int(limit)}"
    else:
        where = f"?order=updated_at.desc&limit={int(limit)}"
    return _fetch_rows(f"{SUPABASE_URL}/rest/v1/official_market_indicators{where}")


def save_valuation_request(
    region: str,
    property_type: str,
    land_area_m2: float | None,
    offered_price: float | None,
    fair_value_estimated: float | None,
    score: int | None = None,
    lang: str = "ar",
) -> None:
    """حفظ طلب تقييم في جدول user_valuation_requests (يظهر فورًا في لوحة العرض)."""
    if not is_configured():
        return
    _post(
        "user_valuation_requests",
        [
            {
                "region": region,
                "property_type": property_type,
                "land_area_m2": land_area_m2,
                "offered_price": offered_price,
                "fair_value_estimated": fair_value_estimated,
                "score": score or 0,
                "lang": lang,
            }
        ],
    )


def save_client_property_request(
    phone: str,
    request_text: str,
    transaction_type: str = "للبيع",
    property_type: str | None = None,
    regions: list[str] | None = None,
    min_budget: float | None = None,
    max_budget: float | None = None,
    min_area_m2: float | None = None,
    max_area_m2: float | None = None,
) -> None:
    """حفظ طلب عميل في client_property_requests (يظهر في لوحة العرض)."""
    if not is_configured():
        return
    _post(
        "client_property_requests",
        [
            {
                "source_channel": "app",
                "requester_phone": phone,
                "request_text": request_text,
                "extracted_intent": {},
                "transaction_type": transaction_type,
                "property_type": property_type or "",
                "regions": regions or [],
                "min_budget": min_budget,
                "max_budget": max_budget,
                "min_area_m2": min_area_m2,
                "max_area_m2": max_area_m2,
                "confidence_score": 0,
                "status": "new",
            }
        ],
    )


def fetch_client_property_requests(limit: int = 100) -> list[dict[str, Any]]:
    """قراءة طلبات العملاء من لوحة العرض (أحدث أولًا)."""
    if not is_configured():
        return []
    return _fetch_rows(f"{SUPABASE_URL}/rest/v1/client_property_requests?select=*&order=created_at.desc&limit={int(limit)}")


# ─── outreach_clicks (تتبع نقرات التسويق: نسخ/إرسال فرصة أو عميل) ────────────


def save_outreach_click(click: dict[str, Any]) -> dict[str, Any]:
    """تسجيل نقرة تسويق (نسخ ملخص / إرسال واتساب لفرصة أو عميل) في جدول outreach_clicks.

    متسامح تمامًا: غياب الضبط أو غياب الجدول لا يكسر الواجهة — تُسجَّل الحالة
    والسبب حتى تعرف الواجهة متى تعرض تعليمات إنشاء الجدول.
    """
    if not is_configured():
        return {"status": "not_configured"}
    row = {
        "client_phone": str(click.get("clientPhone") or ""),
        "client_area": str(click.get("clientArea") or ""),
        "client_type": str(click.get("clientType") or ""),
        "opportunity_code": str(click.get("opportunityCode") or ""),
        "action": str(click.get("action") or "copy"),
        "channel": str(click.get("channel") or ""),
    }
    try:
        _post("outreach_clicks", [row])
        return {"status": "saved"}
    except RuntimeError as exc:
        logger.warning("outreach_clicks save failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def outreach_table_available() -> bool:
    """هل جدول outreach_clicks موجود فعلًا في Supabase؟ (فحص خفيف دون إخفاء الخطأ)."""
    if not is_configured():
        return False
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/outreach_clicks?select=id&limit=1",
        method="GET",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception:
        return False


def _click_bucket_date(created_at: Any) -> date | None:
    """تاريخ اليوم من created_at (أول 10 أحرف ISO) أو None عند تعذر التحليل."""
    try:
        return datetime.strptime(str(created_at or "")[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def fetch_outreach_stats(limit: int = 1000) -> dict[str, Any]:
    """عدّادات تفاعل العملاء: تجميع نقرات outreach_clicks لكل عميل + سلسلة زمنية.

    يعيد الإجمالي (نقرات/نسخ/إرسال) + قائمة عملاء مرتّبة بالأكثر تفاعلًا،
    + سلسلة يومية (آخر 30 يومًا بأصفار للأيام الخالية) وأسبوعية (آخر 12 أسبوعًا ISO)،
    مع tableOk حتى تعرف الواجهة متى تعرض تعليمات إنشاء الجدول.
    """
    empty = {
        "tableOk": False,
        "totals": {"total": 0, "copies": 0, "sends": 0, "clients": 0},
        "clients": [],
        "timeline": [],
        "weekly": [],
        "responseMethod": "نسبة الرد المتوقعة = 6% أساس + 9% لكل إرسال + 4% لكل نسخ (سقف 85%) — تقدير حتمي من التفاعل المقاس بلا عشوائية.",
    }
    if not outreach_table_available():
        return empty
    rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/outreach_clicks?select=*&order=created_at.desc&limit={int(limit)}")
    by_client: dict[str, dict[str, Any]] = {}
    day_buckets: dict[str, dict[str, Any]] = {}
    week_buckets: dict[str, dict[str, Any]] = {}
    totals = {"total": 0, "copies": 0, "sends": 0, "clients": 0}
    for row in rows:
        phone = str(row.get("client_phone") or "").strip()
        action = str(row.get("action") or "copy")
        key = phone or "__generic__"
        bucket = by_client.setdefault(key, {
            "phone": phone,
            "area": str(row.get("client_area") or ""),
            "type": str(row.get("client_type") or ""),
            "count": 0,
            "copies": 0,
            "sends": 0,
            "lastAt": str(row.get("created_at") or ""),
        })
        bucket["count"] += 1
        totals["total"] += 1
        if action == "send":
            bucket["sends"] += 1
            totals["sends"] += 1
        else:
            bucket["copies"] += 1
            totals["copies"] += 1
        created = str(row.get("created_at") or "")
        if created > bucket["lastAt"]:
            bucket["lastAt"] = created
        # السلسلة الزمنية: تجميع يومي + أسبوعي (بداية أسبوع ISO = الاثنين)
        day = _click_bucket_date(created)
        if day:
            iso = day.isocalendar()
            week_start = date.fromisocalendar(iso[0], iso[1], 1)
            dkey = str(day)
            wkey = str(week_start)
            db = day_buckets.setdefault(dkey, {"date": dkey, "copies": 0, "sends": 0, "total": 0})
            wb = week_buckets.setdefault(wkey, {"week": wkey, "copies": 0, "sends": 0, "total": 0})
            db["total"] += 1
            wb["total"] += 1
            if action == "send":
                db["sends"] += 1
                wb["sends"] += 1
            else:
                db["copies"] += 1
                wb["copies"] += 1
    # سلسلة يومية متصلة: آخر 30 يومًا بما فيها الأيام الخالية (صفر) لرسم متساوٍ
    today = date.today()
    timeline = []
    for i in range(29, -1, -1):
        dkey = str(today - timedelta(days=i))
        timeline.append(day_buckets.get(dkey, {"date": dkey, "copies": 0, "sends": 0, "total": 0}))
    # سلسلة أسبوعية متصلة: آخر 12 أسبوعًا ISO (الاثنين بداية الأسبوع)
    weekly = []
    for i in range(11, -1, -1):
        d = today - timedelta(weeks=i)
        iso = d.isocalendar()
        wkey = str(date.fromisocalendar(iso[0], iso[1], 1))
        weekly.append(week_buckets.get(wkey, {"week": wkey, "copies": 0, "sends": 0, "total": 0}))
    clients = sorted(by_client.values(), key=lambda c: (c["count"], c["lastAt"]), reverse=True)
    # نسبة الرد المتوقعة: تقدير حتمي شفاف من التفاعل المُقاس (كل إرسال إشارة أقوى من كل نسخ)،
    # بسقف 85% لأن الاستجابة الحقيقية لا تُضمن أبدًا. بلا أي عشوائية.
    for c in clients:
        c["expectedResponse"] = min(85, round(6 + (c["sends"] or 0) * 9 + (c["copies"] or 0) * 4))
        c["activityTier"] = (
            "نشط جدًا" if c["count"] >= 15
            else "نشط" if c["count"] >= 8
            else "متفاعل" if c["count"] >= 3
            else "جديد"
        )
    totals["clients"] = len(clients)
    return {
        "tableOk": True,
        "totals": totals,
        "clients": clients,
        "timeline": timeline,
        "weekly": weekly,
        "responseMethod": "نسبة الرد المتوقعة = 6% أساس + 9% لكل إرسال + 4% لكل نسخ (سقف 85%) — تقدير حتمي من التفاعل المقاس بلا عشوائية.",
    }


def persist_analysis(request: PropertyRequest, report: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    if not is_configured():
        return {"enabled": False, "status": "not_configured"}
    save_report(request, report)
    save_search_history(request, report, statuses)
    save_source_runs(request, statuses)
    save_listing_evidence(report)
    return {"enabled": True, "status": "saved"}


# ---------------------------------------------------------------------------
# حسابات المستخدمين المجانيين (المهمة 1): تسجيل/تحقق OTP عبر خادم API
# ---------------------------------------------------------------------------
def fetch_user(phone: str) -> dict[str, Any] | None:
    """قراءة مستخدم برقمه الموحّد (+965XXXXXXXX) — أو None عند غيابه/فشل الاتصال."""
    rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/users?phone=eq.{urllib.parse.quote(phone)}&select=*")
    return rows[0] if rows else None


def upsert_user(row: dict[str, Any]) -> None:
    """إنشاء مستخدم جديد (أو إعادة إرسال الرمز) — upsert على رقم الهاتف."""
    _post("users", [row], upsert=True, conflict="phone")


def patch_user(phone: str, fields: dict[str, Any]) -> None:
    """تحديث حقول مستخدم (التحقق/المحاولات/السرّ) — عبر PATCH على رقم الهاتف."""
    if not fields or not is_configured():
        return
    endpoint = f"{SUPABASE_URL}/rest/v1/users?phone=eq.{urllib.parse.quote(phone)}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(fields, ensure_ascii=False).encode("utf-8"),
        method="PATCH",
        headers=_headers("return=representation"),
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in {200, 204}:
                raise RuntimeError(f"Supabase returned HTTP {response.status}")
    except Exception as exc:
        logger.warning("Supabase users patch failed: %s", exc)


# ---------------------------------------------------------------------------
# تنبيهات الفرص للمستخدمين (المهمة 3): جلب الأبحاث المحفوظة + كتابة صفوف التنبيه
# ---------------------------------------------------------------------------
def fetch_saved_searches() -> list[dict[str, Any]]:
    """قراءة الأبحاث المحفوظة مع التنبيه المفعل (alert_enabled=true) — للسكربت اليومي."""
    return _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/saved_searches?select=*&alert_enabled=eq.true"
    )


def fetch_existing_alert_keys() -> list[tuple[str, str]]:
    """كل أزواج (سرّ، فرصة) المنبّهة سابقًا — لمنع التكرار عند التشغيل المزدوج."""
    rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/user_alerts?select=user_secret,opportunity_code")
    return [(str(r.get("user_secret") or ""), str(r.get("opportunity_code") or "")) for r in rows]


def insert_user_alerts(rows: list[dict[str, Any]]) -> int:
    """كتابة صفوف تنبيه جديدة (upsert على سرّ×فرصة — لا تكرار)."""
    if not rows or not is_configured():
        return 0
    _post(
        "user_alerts",
        rows,
        upsert=True,
        conflict="user_secret,opportunity_code",
    )
    return len(rows)


def fetch_user_phones() -> dict[str, str]:
    """خريطة secret → phone لجميع المستخدمين (للتسليم عبر واتساب في سكربت التنبيهات)."""
    rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/users?select=secret,phone")
    return {str(r.get("secret") or ""): str(r.get("phone") or "") for r in rows if r.get("secret")}
