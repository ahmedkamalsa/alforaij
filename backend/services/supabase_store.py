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
from datetime import date, datetime, timedelta
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from backend.models import Listing, PropertyRequest

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


def _source_id_for(source_name: str) -> str:
    """معرف المصدر من السجل الرسمي بدل خريطة يدوية مكررة تُنسى عند إضافة مصدر.

    كل مصدر في source_registry يحمل name وid؛ نعتمد عليه كمصدر حقيقة وحيد حتى
    تُسجَّل المصادر الجديدة (Aqarat، 4Sale، الصفقات الرسمية...) بمعرفاتها الصحيحة
    تلقائيًا بدل سقوطها لاسم منخفض لا يطابق السجل.
    """
    try:
        from backend.services.source_registry import SOURCE_REGISTRY

        target = str(source_name or "")
        # 1) مطابقة حرفية أولًا (أسرع وأكثر أمانًا)
        for entry in SOURCE_REGISTRY:
            if str(entry.get("name") or "") == target:
                return str(entry["id"])
        # 2) مطابقة الجذر قبل القوسين: «السوق المباشر (بوشملان)» ← سجل
        #    «السوق المباشر (Supabase market_ads)» — الأسماء الحية تحمل تفاصيل
        #    المصدر الداخلي بين قوسين فلا تطابق حرفيًا اسم السجل.
        target_base = target.split(" (")[0].strip()
        if len(target_base) >= 4:
            for entry in SOURCE_REGISTRY:
                entry_base = str(entry.get("name") or "").split(" (")[0].strip()
                if entry_base and entry_base == target_base:
                    return str(entry["id"])
        # 3) اسم المصدر قد يكون اختصارًا لاسم السجل الطويل
        #    (مثل «الصفقات الرسمية» مقابل «الصفقات الرسمية / التسجيل العقاري»)
        #    لكن نمنع الاتجاه العكسي للأسماء القصيرة: اسم طوله 3 أحرف مثل «عقار»
        #    موجود داخل «بوعقار / بوشملان» و«التسجيل العقاري» فيطابق المصدر الخطأ.
        #    القاعدة: سجل الأسماء يطابق داخل الاسم المطلوب فقط، والاسم المطلوب
        #    يطابق داخل السجل بشرط ألا يكون قصيرًا جدًا (<6 أحرف).
        for entry in SOURCE_REGISTRY:
            entry_name = str(entry.get("name") or "")
            if not entry_name:
                continue
            if entry_name in target or (len(target) >= 6 and target in entry_name):
                return str(entry["id"])
    except Exception:
        pass
    return str(source_name or "").lower() or "unknown"


def save_source_runs(request: PropertyRequest, statuses: list[dict[str, Any]]) -> None:
    rows = []
    for status in statuses:
        source_name = str(status.get("name") or "")
        rows.append(
            {
                "source_id": _source_id_for(source_name),
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
        source_id = _source_id_for(str(item.get("source") or ""))
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

    متسامح تمامًا: غياب الجدول أو تعذر الكتابة لا يكسر التشغيل اليومي — يُسجَّل السبب
    ويعود status حتى يظهر في تقرير الوكيل (خطوة persist_market_listings).
    """
    if not rows:
        return {"status": "empty", "count": 0, "error": ""}
    if not is_configured():
        return {"status": "not_configured", "count": 0, "error": ""}
    try:
        for index in range(0, len(rows), 250):
            _post("market_listings", rows[index:index + 250], upsert=True, conflict="code")
        return {"status": "saved", "count": len(rows), "error": ""}
    except RuntimeError as exc:
        logger.warning("market_listings save failed: %s", exc)
        return {"status": "failed", "count": 0, "error": str(exc)}
    except Exception:
        logger.exception("market_listings save failed")
        return {"status": "failed", "count": 0, "error": "unexpected error"}


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


def fetch_market_listings(
    area: str | None = None,
    transaction: str | None = None,
    property_type: str | None = None,
    source: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """قراءة إعلانات السوق الخارجية المحصودة من جدول market_listings.

    الفلاتر اختيارية وتُطبق في REST API لتقليل البيانات المنقولة.
    """
    if not is_configured():
        return []
    params: list[str] = [f"limit={int(limit)}"]
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


def fetch_market_analytics(limit: int = 5000) -> dict[str, Any]:
    """تحليلات الحصاد المتراكم من market_listings لكل موقع على حدة.

    تُجمَّع الصفوف (كل المواقع) في Python لأن REST لا يدعم group-by:
    - إجمالي: عدد الصفوف/المواقع/المناطق/المحافظات + آخر جلب.
    - لكل مصدر: عدد الإعلانات، خلط المعاملات، أنواع العقار، المناطق،
      وسيط السعر والمساحة (حيثما وُجدت أرقام صالحة) — أساس قياس تغطية كل موقع.
    - المناطق الأكثر تغطية (ترتيب تنازلي) لمعرفة أين تتوفر بيانات فعلية للتحليل.

    متسامح تمامًا: غياب الجدول أو تعذر القراءة يعيد حالة واضحة بدل كسر الطلب.
    """
    if not market_listings_table_available():
        return {
            "tableOk": False,
            "note": "جدول market_listings غير موجود بعد — شغّل migration 010 ثم الوكيل اليومي.",
            "totals": {"rows": 0, "sources": 0, "areas": 0, "governorates": 0, "transactions": 0, "propertyTypes": 0},
            "sources": [],
            "areas": [],
        }
    rows = _fetch_rows(f"{SUPABASE_URL}/rest/v1/market_listings?select=*&order=fetched_at.desc&limit={int(limit)}")
    if not rows:
        return {
            "tableOk": True,
            "note": "الجدول جاهز ولا توجد صفوف بعد — شغّل الوكيل اليومي (حصاد المواقع) لبدء التراكم.",
            "totals": {"rows": 0, "sources": 0, "areas": 0, "governorates": 0, "transactions": 0, "propertyTypes": 0},
            "sources": [],
            "areas": [],
        }

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return round(ordered[middle], 1)
        return round((ordered[middle - 1] + ordered[middle]) / 2, 1)

    by_source: dict[str, dict[str, Any]] = {}
    area_counts: dict[str, int] = {}
    gov_counts: dict[str, int] = {}
    trans_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    last_fetched = ""
    for row in rows:
        source = str(row.get("source") or "غير معروف").strip() or "غير معروف"
        bucket = by_source.setdefault(source, {
            "source": source,
            "count": 0,
            "transactions": {},
            "propertyTypes": set(),
            "areas": set(),
            "governorates": set(),
            "prices": [],
            "spaces": [],
            "lastFetched": "",
        })
        bucket["count"] += 1
        transaction = str(row.get("transaction") or "").strip()
        property_type = str(row.get("property_type") or "").strip()
        area = str(row.get("area") or "").strip()
        governorate = str(row.get("governorate") or "").strip()
        if transaction:
            bucket["transactions"][transaction] = bucket["transactions"].get(transaction, 0) + 1
            trans_counts[transaction] = trans_counts.get(transaction, 0) + 1
        if property_type:
            bucket["propertyTypes"].add(property_type)
            type_counts[property_type] = type_counts.get(property_type, 0) + 1
        if area:
            bucket["areas"].add(area)
            area_counts[area] = area_counts.get(area, 0) + 1
        if governorate:
            bucket["governorates"].add(governorate)
            gov_counts[governorate] = gov_counts.get(governorate, 0) + 1
        try:
            price = float(row.get("price"))
            if price and price > 0:
                bucket["prices"].append(price)
        except (TypeError, ValueError):
            pass
        try:
            space = float(row.get("space"))
            if space and space > 0:
                bucket["spaces"].append(space)
        except (TypeError, ValueError):
            pass
        fetched = str(row.get("fetched_at") or "")
        if fetched > bucket["lastFetched"]:
            bucket["lastFetched"] = fetched
        if fetched > last_fetched:
            last_fetched = fetched

    sources = []
    for bucket in by_source.values():
        sources.append({
            "source": bucket["source"],
            "count": bucket["count"],
            "transactions": bucket["transactions"],
            "propertyTypes": sorted(bucket["propertyTypes"]),
            "areas": sorted(bucket["areas"]),
            "governorates": sorted(bucket["governorates"]),
            "price": {"median": _median(bucket["prices"]), "min": min(bucket["prices"]) if bucket["prices"] else None, "max": max(bucket["prices"]) if bucket["prices"] else None},
            "space": {"median": _median(bucket["spaces"])},
            "lastFetched": bucket["lastFetched"],
        })
    sources.sort(key=lambda item: item["count"], reverse=True)
    areas = sorted(area_counts.items(), key=lambda pair: pair[1], reverse=True)[:30]
    return {
        "tableOk": True,
        "fetchedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "تحليلات الحصاد المتراكم من market_listings — كل إعلان يحمل original_url وfetched_at كدليل قابل للفتح.",
        "totals": {
            "rows": len(rows),
            "sources": len(sources),
            "areas": len(area_counts),
            "governorates": len(gov_counts),
            "transactions": trans_counts,
            "propertyTypes": type_counts,
            "lastFetched": last_fetched,
        },
        "sources": sources,
        "areas": [{"area": area, "count": count} for area, count in areas],
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
