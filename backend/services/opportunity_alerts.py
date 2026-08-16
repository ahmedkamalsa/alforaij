"""خط تنبيه الفرص للمستخدمين المحفوظين (المهمة 3): فرق لقطتين → تغييرات → مطابقة.

نفس فلسفة build_whatsapp_alerts لكن للمستخدمين (saved_searches) بدل عملاء الوسيط:
1. find_changes: فرص جديدة أو انخفض سعرها بين اللقطة السابقة والحالية (الطبقة اليومية).
2. match_searches_to_change: الأبحاث المطابقة (التنبيه مفعّل + درجة >= العتبة).
3. build_alert_message: رسالة عربية جاهزة مخصصة بمنطقة/نوع/ميزانية البحث المحفوظ.
4. build_alert_rows: صف تنبيه لكل (سرّ × فرصة) بلا تكرار داخل الدفعة.
5. filter_unsent_alerts: استبعاد ما أُرسل سابقًا (منع التكرار عند التشغيل المزدوج).

التخزين والتسليم خارج هذه الوحدة: scripts/send_opportunity_alerts.py.
"""
from __future__ import annotations

from typing import Any

from backend.services.search_matching import MATCH_THRESHOLD, match_search_to_item


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def find_changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[dict[str, Any]]:
    """فرق اللقطتين: فرص جديدة (new) أو انخفض سعرها (price_drop) في الطبقة اليومية."""
    current_items = (current.get("tiers") or {}).get("daily", {}).get("items", []) or []
    previous_items: dict[str, dict[str, Any]] = {}
    if previous:
        previous_items = {
            item.get("code"): item
            for item in ((previous.get("tiers") or {}).get("daily", {}).get("items", []) or [])
        }
    changes: list[dict[str, Any]] = []
    for item in current_items:
        code = item.get("code")
        if not code:
            continue
        prev = previous_items.get(code)
        change = None
        old_price = None
        if prev is None:
            change = "new"
        elif item.get("price") and prev.get("price") and item["price"] < prev["price"]:
            change = "price_drop"
            old_price = prev.get("price")
        if not change:
            continue
        price = _num(item.get("price"))
        changes.append(
            {
                "opportunity_code": code,
                "area": item.get("area"),
                "governorate": item.get("governorate") or "",
                "transaction": item.get("transaction") or "",
                "propertyType": item.get("propertyType"),
                "price": price,
                "priceText": item.get("priceText") or (f"{price:,.0f} د.ك" if price else ""),
                "oldPrice": old_price,
                "oldPriceText": f"{old_price:,.0f} د.ك" if old_price else "",
                "change": change,
                "valuationLabel": item.get("valuationLabel") or "",
                "url": item.get("url") or "",
            }
        )
    return changes


def _search_as_dict(search: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_type": search.get("transaction_type"),
        "property_type": search.get("property_type"),
        "areas": search.get("areas") or [],
        "governorates": search.get("governorates") or [],
        "price_min": _num(search.get("price_min")),
        "price_max": _num(search.get("price_max")),
    }


def _item_as_dict(change: dict[str, Any]) -> dict[str, Any]:
    return {
        "area": change.get("area"),
        "governorate": change.get("governorate") or "",
        "propertyType": change.get("propertyType"),
        "transaction": change.get("transaction") or "",
        "price": change.get("price"),
    }


def match_searches_to_change(
    saved_searches: list[dict[str, Any]],
    change: dict[str, Any],
    *,
    threshold: float = MATCH_THRESHOLD,
) -> list[dict[str, Any]]:
    """الأبحاث المطابقة لتغيير فرصة (تنبيه مفعّل + درجة >= العتبة) — الأعلى أولًا."""
    matches: list[dict[str, Any]] = []
    item = _item_as_dict(change)
    for search in saved_searches:
        if search.get("alert_enabled") is False:
            continue
        score = match_search_to_item(_search_as_dict(search), item)
        if score >= threshold:
            matches.append({"search": search, "score": score})
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


def build_alert_message(change: dict[str, Any], search: dict[str, Any]) -> str:
    """رسالة عربية جاهزة مخصصة بالبحث المحفوظ (اسمه/منطقته/نوعه)."""
    area = change.get("area") or "المنطقة"
    price_text = change.get("priceText") or ""
    name = str(search.get("name") or "").strip()
    scope = name or "بحثك المحفوظ"
    if change.get("change") == "price_drop":
        old = change.get("oldPriceText") or "السعر السابق"
        return (
            f"مرحبًا، فرصة مطابقة لـ{scope}: انخفض سعر إعلان "
            f"{change.get('opportunity_code')} في {area} إلى {price_text} (كان {old}) — "
            f"{change.get('valuationLabel') or ''}."
        )
    return (
        f"مرحبًا، فرصة جديدة مطابقة لـ{scope}: {change.get('propertyType') or 'عقار'} "
        f"في {area} بسعر {price_text} — {change.get('valuationLabel') or ''}."
    )


def build_alert_rows(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    saved_searches: list[dict[str, Any]],
    *,
    threshold: float = MATCH_THRESHOLD,
) -> list[dict[str, Any]]:
    """كل صفوف التنبيه (سرّ × فرصة) — بلا تكرار داخل الدفعة نفسها."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for change in find_changes(previous, current):
        for match in match_searches_to_change(saved_searches, change, threshold=threshold):
            search = match["search"]
            key = (str(search.get("user_secret") or ""), str(change["opportunity_code"]))
            if not key[0] or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "user_secret": search.get("user_secret"),
                    "opportunity_code": change["opportunity_code"],
                    "area": change.get("area"),
                    "price": change.get("price"),
                    "change": change["change"],
                    "message": build_alert_message(change, search),
                    "url": change.get("url") or "",
                }
            )
    return rows


def filter_unsent_alerts(
    rows: list[dict[str, Any]],
    existing_keys: list[tuple[str, str]] | set[tuple[str, str]] | None,
) -> list[dict[str, Any]]:
    """استبعاد ما أُرسل سابقًا (منع التكرار عند التشغيل المزدوج)."""
    existing = {tuple(k) for k in (existing_keys or [])}
    return [r for r in rows if (str(r.get("user_secret") or ""), str(r.get("opportunity_code") or "")) not in existing]
