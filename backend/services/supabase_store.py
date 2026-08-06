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


def save_source_runs(request: PropertyRequest, statuses: list[dict[str, Any]]) -> None:
    rows = []
    source_ids = {
        "الفريج": "alforaij_board",
        "OpenSooq": "opensooq_kw",
        "Mourjan": "mourjan_kw",
        "Q8Aqar": "q8aqar",
        "Sakan": "sakan",
        "Waseet": "waseet",
        "نبض عقار (NabdAqar)": "nabdaqar",
        "نبض عقار": "nabdaqar",
        "NabdAqar": "nabdaqar",
        "بوعقار / بوشملان (Bu3qar)": "bu3qar",
        "بوعقار": "bu3qar",
        "Bu3qar": "bu3qar",
    }
    for status in statuses:
        source_name = str(status.get("name") or "")
        rows.append(
            {
                "source_id": source_ids.get(source_name, source_name.lower() or None),
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
    source_ids = {
        "الفريج": "alforaij_board",
        "OpenSooq": "opensooq_kw",
        "Mourjan": "mourjan_kw",
        "Q8Aqar": "q8aqar",
        "Sakan": "sakan",
        "Waseet": "waseet",
        "نبض عقار (NabdAqar)": "nabdaqar",
        "نبض عقار": "nabdaqar",
        "NabdAqar": "nabdaqar",
        "بوعقار / بوشملان (Bu3qar)": "bu3qar",
        "بوعقار": "bu3qar",
        "Bu3qar": "bu3qar",
    }
    for item in report.get("results", []):
        source_id = source_ids.get(item.get("source"), str(item.get("source") or "").lower())
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


def persist_analysis(request: PropertyRequest, report: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    if not is_configured():
        return {"enabled": False, "status": "not_configured"}
    save_report(request, report)
    save_source_runs(request, statuses)
    save_listing_evidence(report)
    return {"enabled": True, "status": "saved"}
