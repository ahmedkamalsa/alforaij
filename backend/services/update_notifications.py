from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.services.opportunities import build_opportunity_delta

ROOT = Path(__file__).resolve().parents[2]
NOTIFICATIONS_FILE = ROOT / "data" / "daily_update_notifications.json"


def _top_items(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    output = []
    for item in items[:limit]:
        output.append({
            "code": item.get("code"),
            "area": item.get("area"),
            "propertyType": item.get("propertyType"),
            "price": item.get("price"),
            "priceText": item.get("priceText"),
            "oldPrice": item.get("oldPrice"),
            "oldPriceText": item.get("oldPriceText"),
            "valuationLabel": item.get("valuationLabel"),
            "source": item.get("source"),
            "url": item.get("url"),
            "guidance": item.get("guidance"),
        })
    return output


def build_update_notifications(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    *,
    official_result: dict[str, Any] | None = None,
    data_summary: dict[str, Any] | None = None,
    candidate_platforms: dict[str, Any] | None = None,
) -> dict[str, Any]:
    delta = build_opportunity_delta(previous_snapshot, current_snapshot)
    counts = delta.get("counts") or {}
    official = official_result or {}
    tables = (data_summary or {}).get("tables") or {}
    official_transactions = tables.get("official_transactions") or {}
    official_indicators = tables.get("official_market_indicators") or {}

    # المنصات المرشحة: ملخص توفر يومي قصير (كل منصة + حالتها) ليظهر في الإشعارات
    # والحالة اليومية — ويُنبَّه عند تحوّل أي منصة إلى متاحة.
    candidates = candidate_platforms or {}
    candidate_sources = candidates.get("sources") or []
    candidate_summary = [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "kind": row.get("kind"),
            "status": row.get("status"),
            "detail": row.get("detail") or "",
        }
        for row in candidate_sources
    ]
    newly_available = [
        row["name"] for row in candidate_summary if row.get("status") == "reachable"
    ]

    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "hasPrevious": bool(delta.get("hasPrevious")),
        "counts": {
            "added": int(counts.get("added") or 0),
            "removed": int(counts.get("removed") or 0),
            "priceDrops": int(counts.get("priceDrops") or 0),
        },
        "officialTransactions": {
            "importStatus": official.get("status") or "unknown",
            "importCount": int(official.get("count") or 0),
            "storedCount": official_transactions.get("count"),
            "note": official.get("note") or "",
        },
        "officialIndicators": {
            "storedCount": official_indicators.get("count"),
            "status": official_indicators.get("status"),
        },
        "candidatePlatforms": {
            "count": candidates.get("count"),
            "reachable": candidates.get("reachable"),
            "blocked": candidates.get("blocked"),
            "discontinued": candidates.get("discontinued"),
            "sources": candidate_summary,
            "newlyAvailable": newly_available,
        },
        "top": {
            "priceDrops": _top_items(delta.get("priceDrops") or [], 3),
            "added": _top_items(delta.get("added") or [], 3),
            "removed": _top_items(delta.get("removed") or [], 3),
        },
    }


def save_update_notifications(notifications: dict[str, Any]) -> None:
    NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTIFICATIONS_FILE.write_text(json.dumps(notifications, ensure_ascii=False, indent=2), encoding="utf-8")


def load_update_notifications() -> dict[str, Any]:
    if not NOTIFICATIONS_FILE.exists():
        return {
            "generatedAt": "",
            "counts": {"added": 0, "removed": 0, "priceDrops": 0},
            "officialTransactions": {"importStatus": "not_run", "importCount": 0, "storedCount": None, "note": ""},
            "officialIndicators": {"storedCount": None, "status": "unknown"},
            "top": {"priceDrops": [], "added": [], "removed": []},
            "actions": ["شغّل التحديث اليومي أولًا لبناء ملخص الإشعارات."],
            "note": "لم يتم إنشاء ملخص تحديث يومي بعد.",
        }
    try:
        return json.loads(NOTIFICATIONS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "generatedAt": "",
            "counts": {"added": 0, "removed": 0, "priceDrops": 0},
            "officialTransactions": {"importStatus": "error", "importCount": 0, "storedCount": None, "note": str(exc)},
            "officialIndicators": {"storedCount": None, "status": "unknown"},
            "top": {"priceDrops": [], "added": [], "removed": []},
            "actions": ["تعذر قراءة ملف الإشعارات؛ أعد تشغيل التحديث اليومي."],
            "note": "ملف الإشعارات غير صالح.",
        }
