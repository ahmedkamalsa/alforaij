from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from backend.models import Listing, PropertyRequest


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


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
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in {200, 201, 204}:
                raise RuntimeError(f"Supabase returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase {table} write failed: HTTP {exc.code} {detail}") from exc


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
        # 2) اسم المصدر قد يكون اختصارًا لاسم السجل الطويل
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


def fetch_official_transactions() -> list[dict[str, Any]]:
    """قراءة كل الصفقات الرسمية (أحدث أولًا)."""
    if not is_configured():
        return []
    endpoint = f"{SUPABASE_URL}/rest/v1/official_transactions?select=*&order=date.desc.nullslast&limit=2000"
    request = urllib.request.Request(endpoint, method="GET", headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return []


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
    if not is_configured():
        return []
    endpoint = f"{SUPABASE_URL}/rest/v1/client_leads?select=*&order=created_at.desc"
    request = urllib.request.Request(endpoint, method="GET", headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return []


def fetch_opportunity_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    """قراءة لقطات الفرص التاريخية (أحدث أولًا) لأرشفة الأداء وتتبع التغيرات."""
    if not is_configured():
        return []
    endpoint = f"{SUPABASE_URL}/rest/v1/opportunities?select=*&order=generated_at.desc&limit={int(limit)}"
    request = urllib.request.Request(endpoint, method="GET", headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return []


def fetch_latest_opportunities() -> dict[str, Any] | None:
    """قراءة آخر لقطة فرص محفوظة (أحدث generated_at) — احتياط عند برودة الكاش أو فشل البناء."""
    if not is_configured():
        return None
    endpoint = f"{SUPABASE_URL}/rest/v1/opportunities?select=*&order=generated_at.desc&limit=1"
    request = urllib.request.Request(endpoint, method="GET", headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
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


def persist_analysis(request: PropertyRequest, report: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    if not is_configured():
        return {"enabled": False, "status": "not_configured"}
    save_report(request, report)
    save_source_runs(request, statuses)
    save_listing_evidence(report)
    return {"enabled": True, "status": "saved"}
