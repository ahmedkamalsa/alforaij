"""لوحة تحليلات متقدمة: أنماط البحث والمناطق الشائعة واتجاهات الأسعار.

تجمع البيانات من:
- search_history (سجل البحث)
- market_listings (إعلانات السوق الخارجية)
- price_trends (اتجاهات الأسعار الشهرية)
- listings (البيانات المحلية)
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


def _headers(prefer: str = "return=minimal") -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _fetch(table: str, select: str = "*", limit: int = 500, order: str = "", filters: str = "") -> list[dict[str, Any]]:
    """قراءة صفوف من Supabase بشكل آمن."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []
    params = f"select={urllib.parse.quote(select)}&limit={limit}"
    if order:
        params += f"&order={urllib.parse.quote(order)}"
    if filters:
        params += f"&{filters}"
    endpoint = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    req = urllib.request.Request(endpoint, method="GET", headers=_headers("return=representation"))
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Dashboard fetch %s failed: %s", table, exc)
        return []


# ── كاش داخلي: يُبنى مرة كل 5 دقائق ويخزّن النتيجة ──
_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 دقائق


def build_dashboard() -> dict[str, Any]:
    """بناء لوحة التحليلات الكاملة مع كاش."""
    now = datetime.utcnow()
    if _CACHE["data"] and (time.time() - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"]

    # ── 1. سجل البحث: أنماط البحث والمناطق والأنواع ──
    search_rows = _fetch("search_history", limit=200, order="created_at.desc")

    # أكثر الاستعلامات بحثًا
    query_counter: Counter = Counter()
    area_counter: Counter = Counter()
    type_counter: Counter = Counter()
    tx_counter: Counter = Counter()
    daily_searches: Counter = Counter()
    prices_collected: list[float] = []

    for row in search_rows:
        query = str(row.get("request_text") or "").strip()
        if query:
            query_counter[query[:80]] += 1

        areas = row.get("areas") or []
        if isinstance(areas, str):
            try:
                areas = json.loads(areas)
            except Exception:
                areas = [areas]
        for a in areas:
            if a:
                area_counter[str(a)] += 1

        ptype = str(row.get("property_type") or "").strip()
        if ptype:
            type_counter[ptype] += 1

        tx = str(row.get("transaction_type") or "").strip()
        if tx:
            tx_counter[tx] += 1

        created = str(row.get("created_at") or "")
        if created[:10]:
            daily_searches[created[:10]] += 1

        price = row.get("top_price")
        if price and float(price) > 0:
            prices_collected.append(float(price))

    # ── 2. إعلانات السوق: توزيع المناطق والأسعار ──
    market_rows = _fetch("market_listings", select="area,price,property_type,source,created_at", limit=200, order="created_at.desc")

    market_area_counter: Counter = Counter()
    market_source_counter: Counter = Counter()
    market_type_counter: Counter = Counter()
    market_prices: dict[str, list[float]] = {}

    for row in market_rows:
        area = str(row.get("area") or "").strip()
        if area:
            market_area_counter[area] += 1
            price = row.get("price")
            if price and float(price) > 0:
                market_prices.setdefault(area, []).append(float(price))

        source = str(row.get("source") or "").strip()
        if source:
            market_source_counter[source] += 1

        ptype = str(row.get("property_type") or "").strip()
        if ptype:
            market_type_counter[ptype] += 1

    # ── 3. اتجاهات الأسعار الشهرية ──
    price_trend_rows = _fetch("price_trends", limit=200, order="month.desc")

    price_trends: dict[str, list[dict]] = {}
    for row in price_trend_rows:
        area = str(row.get("area") or "")
        month = str(row.get("month") or "")
        if area and month:
            price_trends.setdefault(area, []).append({
                "month": month,
                "median": row.get("median_price"),
                "count": row.get("listing_count", 0),
                "property_type": row.get("property_type", ""),
                "transaction": row.get("transaction", ""),
            })

    # ── 4. حساب الإحصائيات ──

    # متوسط ووسيط الأسعار
    def _stats(values: list[float]) -> dict:
        if not values:
            return {"avg": 0, "median": 0, "min": 0, "max": 0, "count": 0}
        sorted_v = sorted(values)
        n = len(sorted_v)
        median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
        return {
            "avg": round(sum(sorted_v) / n, 1),
            "median": round(median, 1),
            "min": round(sorted_v[0], 1),
            "max": round(sorted_v[-1], 1),
            "count": n,
        }

    # أكثر المناطق شعبية (مجاني + سوق)
    combined_areas: Counter = Counter()
    combined_areas.update(area_counter)
    combined_areas.update(market_area_counter)

    # أسعار حسب المنطقة (أعلى 10 مناطق)
    area_price_stats: dict[str, dict] = {}
    for area, prices in sorted(market_prices.items(), key=lambda x: -len(x[1]))[:15]:
        area_price_stats[area] = _stats(prices)

    # آخر 30 يوم من البحث
    thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    recent_daily = {k: v for k, v in daily_searches.items() if k >= thirty_days_ago}

    # ترتيب الأيام
    daily_chart = sorted(recent_daily.items())

    result = {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "overview": {
            "totalSearches": len(search_rows),
            "totalMarketListings": len(market_rows),
            "uniqueAreas": len(combined_areas),
            "avgSearchPrice": round(sum(prices_collected) / len(prices_collected), 1) if prices_collected else 0,
            "totalSearchPriceRecords": len(prices_collected),
        },
        "searchPatterns": {
            "topQueries": [{"query": q, "count": c} for q, c in query_counter.most_common(15)],
            "topAreas": [{"area": a, "count": c} for a, c in combined_areas.most_common(15)],
            "propertyTypes": [{"type": t, "count": c} for t, c in type_counter.most_common(10)],
            "transactionTypes": [{"type": t, "count": c} for t, c in tx_counter.most_common(10)],
        },
        "marketStats": {
            "topAreas": [{"area": a, "count": c} for a, c in market_area_counter.most_common(15)],
            "topSources": [{"source": s, "count": c} for s, c in market_source_counter.most_common(10)],
            "propertyTypes": [{"type": t, "count": c} for t, c in market_type_counter.most_common(10)],
            "areaPrices": area_price_stats,
        },
        "priceTrends": {
            area: sorted(trends, key=lambda x: x["month"])
            for area, trends in sorted(price_trends.items(), key=lambda x: -len(x[1]))[:10]
        },
        "dailyActivity": {
            "dates": [d for d, _ in daily_chart],
            "searches": [c for _, c in daily_chart],
        },
        "priceOverview": _stats(prices_collected),
    }
    _CACHE["data"] = result
    _CACHE["ts"] = time.time()
    return result
