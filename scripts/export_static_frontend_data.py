from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "static-data"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def write_json(name: str, payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")


def guarded(name: str, fn: Callable[[], dict[str, Any]], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = fn()
        if isinstance(payload, dict):
            payload.setdefault("staticSnapshot", True)
            return payload
        return {"staticSnapshot": True, "value": payload}
    except Exception as exc:
        print(f"warning: {name} failed: {exc}", file=sys.stderr)
        payload = dict(fallback or {})
        payload.update({"staticSnapshot": True, "error": str(exc)})
        return payload


def main() -> None:
    from backend.connectors.alforaij import load_listings
    from backend.services.source_registry import source_registry
    from backend.services.update_notifications import load_update_notifications
    from backend.services.daily_update_agent import load_daily_agent_status
    from backend.services.opportunities import (
        build_history_series,
        build_market_matching,
        build_opportunities,
        build_opportunity_delta,
        build_weekly_digest,
        build_whatsapp_alerts,
        _load_clients,
    )
    import backend.services.supabase_store as supabase_store
    import backend.main as app_main

    include_external = "--skip-external" not in sys.argv
    listings = load_listings()

    opportunities = guarded(
        "opportunities",
        lambda: build_opportunities(include_external=include_external),
        {"tiers": {}, "totalScored": 0, "includeExternal": include_external},
    )

    original_fetch_latest = supabase_store.fetch_latest_opportunities
    supabase_store.fetch_latest_opportunities = lambda: opportunities
    try:
        dashboard = guarded(
            "dashboard-summary",
            lambda: app_main._dashboard_summary(listings, selected_platforms=set(), include_local=True),
            {"count": len(listings), "records": [], "opportunities": {}},
        )
    finally:
        supabase_store.fetch_latest_opportunities = original_fetch_latest

    matching = guarded("market-matching", lambda: build_market_matching(opportunities), {"requests": []})
    weekly = guarded("weekly-digest", lambda: build_weekly_digest(opportunities), {"digests": [], "count": 0})
    alerts = guarded("whatsapp-alerts", lambda: build_whatsapp_alerts(None, opportunities), {"alerts": []})
    history = guarded("opportunities-history", lambda: build_history_series([opportunities]), {"series": []})
    delta = guarded("opportunity-delta", lambda: build_opportunity_delta(None, opportunities), {"added": [], "removed": []})

    # إجمالي كل المصادر في اللقطة الثابتة (مثل /api/health الحي): الفريج + حصاد المواقع
    _market_counts = supabase_store.fetch_market_listing_source_counts()
    _external_total = sum(int(s.get("count") or 0) for s in _market_counts)
    health = {
        "staticSnapshot": True,
        "status": "static",
        "records": len(listings),
        "recordsMeaning": "Static GitHub Pages snapshot generated from the backend data pipeline.",
        "totalRecords": len(listings) + _external_total,
        "localRecords": len(listings),
        "externalRecords": _external_total,
        "bySource": _market_counts,
        "supabase": False,
        "aiAnalysis": False,
        "dataSummary": {
            "listings": len(listings),
            "opportunities": opportunities.get("totalScored", 0),
            "sources": len(source_registry()),
            "externalHarvested": _external_total,
        },
    }
    clients = {"staticSnapshot": True, "clients": _load_clients()}
    outreach = {"staticSnapshot": True, "stats": {}, "note": "Outreach tracking needs the live API."}
    official = {
        "staticSnapshot": True,
        "sources": source_registry(),
        "note": "Static snapshot. Live reachability checks run in the backend daily agent.",
    }

    write_json("dashboard-summary.json", dashboard)
    write_json("opportunities.json", opportunities)
    write_json("market-matching.json", matching)
    write_json("weekly-digest.json", weekly)
    write_json("whatsapp-alerts.json", alerts)
    write_json("opportunities-history.json", history)
    write_json("opportunity-delta.json", delta)
    from backend.services.request_parser import GOVERNORATE_AREA_NAMES, KNOWN_AREAS, PROPERTY_TYPES
    write_json("sources.json", {"staticSnapshot": True, "sources": source_registry()})
    write_json("search-options.json", {
        "staticSnapshot": True,
        "areas": KNOWN_AREAS,
        "propertyTypes": list(PROPERTY_TYPES.keys()),
        "transactions": ["للبيع", "للإيجار", "مطلوب للشراء", "مطلوب للإيجار"],
        "governorates": sorted(GOVERNORATE_AREA_NAMES),
    })
    write_json("update-notifications.json", load_update_notifications() | {"staticSnapshot": True})
    write_json("daily-agent-status.json", load_daily_agent_status() | {"staticSnapshot": True})
    write_json("official-reference-sources.json", official)
    write_json("clients.json", clients)
    write_json("outreach-stats.json", outreach)
    write_json("health.json", health)

    # رابط القاعدة الحية للموقع المنشور: عندما تتوفر بيانات Supabase في بيئة البناء،
    # يُصدَّر ملف إعداد يسمح للواجهة الثابتة بالقراءة المباشرة من القاعدة (قراءة anon فقط،
    # تسمح بها سياسات RLS للجداول العامة) — فيصبح الموقع المرفوع ديناميكيًا فعليًا،
    # ويبقى السقوط للقطة إن غابت البيانات أو انقطع الاتصال.
    import os as _os
    _url = _os.getenv("SUPABASE_URL", "").rstrip("/")
    _anon = _os.getenv("SUPABASE_ANON_KEY", "")
    if _url and _anon:
        write_json("live-db.json", {
            "url": _url,
            "anonKey": _anon,
            "note": "قراءة مباشرة من قاعدة البيانات الحية عبر المفتاح العام (anon) — الجداول العامة فقط عبر RLS.",
        })
    else:
        write_json("live-db.json", {"available": False, "note": "Supabase anon key غير متاح في بيئة البناء."})


if __name__ == "__main__":
    main()
