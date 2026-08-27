"""أدوات خادم MCP لمنصة الفريج — خدمات backend حية بدون اعتماديات خارجية.

كل أداة تعرّف: الاسم، الوصف، مخطط الإدخال (JSON Schema)، المعالج.
المعالجات تستخدم خدمات backend الموجودة فعليًا (نفس خط أنابيب المنصة):
`parse_request` → `top_matches` → `enrich_rankings` → `build_report`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# إتاحة استيراد backend عند التشغيل من أي دليل: جذر المشروع = والد مجلد mcp_server
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.connectors.alforaij import load_listings, load_payload
from backend.services.deduplication import deduplicate_ranked
from backend.services.matching import score_listing, top_matches
from backend.services.opportunities import build_opportunities
from backend.services.report_generator import build_report, ranked_to_dict
from backend.services.request_parser import parse_request, normalize_text
from backend.services.source_registry import source_registry
from backend.services.valuation import comparable_pool, enrich_rankings, price_label

from protocol import JsonRpcError, INVALID_PARAMS


# ── أدوات تحقق المدخلات ────────────────────────────────────────────────

def _require_string(params: dict[str, Any], key: str, min_len: int = 1) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' is required and must be a non-empty string")
    return value.strip()


def _opt_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' must be a string")
    return value.strip()


def _opt_int(params: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = params.get(key, default)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' must be a number")
    number = int(value)
    if number < low or number > high:
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' must be between {low} and {high}")
    return number


def _opt_float(params: dict[str, Any], key: str) -> float | None:
    value = params.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' must be a number")
    return float(value)


def _opt_bool(params: dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' must be a boolean")
    if not isinstance(value, bool):
        raise JsonRpcError(INVALID_PARAMS, f"Parameter '{key}' must be a boolean")
    return value


def _fmt(value: float | None) -> str:
    if value is None:
        return "غير معلن"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} مليون د.ك"
    if value >= 1_000:
        return f"{value / 1_000:.1f} ألف د.ك"
    return f"{value:,.0f} د.ك"


# ── سلاسل مساعدة مشتركة ────────────────────────────────────────────────

def _listing_summary(listing: Any) -> dict[str, Any]:
    """ملخص مدمج لإعلان واحد — حقل للمخرجات الآلية (JSON)."""
    return {
        "code": listing.code,
        "transaction": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "propertyType": listing.property_type,
        "price": listing.price,
        "priceText": listing.price_text or _fmt(listing.price),
        "space": listing.space,
        "listingMode": listing.listing_mode,
        "publishedDate": listing.published_date,
        "originalUrl": listing.original_url,
        "summary": (listing.summary or "")[:180],
    }


def _ranked_rows(enriched: list[Any]) -> list[dict[str, Any]]:
    return [ranked_to_dict(item) for item in enriched]


def _pagination(total: int, limit: int, offset: int) -> dict[str, Any]:
    return {
        "total": total,
        "count": min(limit, max(0, total - offset)),
        "offset": offset,
        "hasMore": offset + limit < total,
        "nextOffset": offset + limit if offset + limit < total else None,
    }


def _request_from_listing(listing: Any):
    """طلب افتراضي مبني من خصائص الإعلان — يستخدم عند تقييم إعلان بلا نص طلب."""
    from backend.models import PropertyRequest

    return PropertyRequest(
        raw_text="",
        transaction=listing.transaction,
        property_type=listing.property_type,
        areas=[listing.area] if listing.area else [],
        governorates=[listing.governorate] if listing.governorate else [],
    )


def _evaluate_code(code: str, request_text: str) -> dict[str, Any]:
    """تقييم إعلان واحد بكوده عبر نفس خط أنابيب المنصة (مقارنات + حكم سعر + تمويل)."""
    listings = load_listings()
    target = next((item for item in listings if item.code and item.code.lower() == code.lower()), None)
    if target is None:
        sample = ", ".join(item.code for item in listings[:5] if item.code) or "لا توجد إعلانات"
        raise JsonRpcError(
            INVALID_PARAMS,
            f"لا يوجد إعلان بالكود «{code}» في البيانات الحالية. أكواد متاحة كمثال: {sample}",
        )
    request = parse_request(request_text) if request_text else _request_from_listing(target)
    ranked = top_matches(request, listings, limit=60, min_results=3)
    enriched = enrich_rankings(request, ranked, listings)
    item = next((e for e in enriched if e.listing.code.lower() == code.lower()), None)
    if item is not None:
        return {"code": code, "inRankedResults": True, "result": ranked_to_dict(item)}

    # الإعلان خارج قائمة المطابقة العليا — تقييم مباشر بمقارناته وحكم السعر
    score, reasons, warnings, breakdown = score_listing(request, target)
    comps = comparable_pool(target, listings, request)
    valuation = price_label(target, comps)
    return {
        "code": code,
        "inRankedResults": False,
        "result": {
            "code": target.code,
            "area": target.area,
            "governorate": target.governorate,
            "transaction": target.transaction,
            "priceText": target.price_text or _fmt(target.price),
            "space": target.space,
            "originalUrl": target.original_url,
            "matchScore": round(score, 1),
            "matchReasons": reasons,
            "warnings": warnings,
            "matchBreakdown": breakdown,
            "valuationLabel": valuation.label,
            "valuationReason": valuation.reason,
            "confidence": valuation.confidence,
            "dealScore": valuation.deal_score,
            "marketMedian": valuation.market_median,
            "priceRatio": valuation.price_ratio,
            "comparablesCount": len(comps),
            "evidence": valuation.evidence,
        },
    }


# ── الأدوات ─────────────────────────────────────────────────────────────

def _parse_request_tool(params: dict[str, Any]) -> str:
    text = _require_string(params, "text")
    request = parse_request(text)
    payload = {
        "rawText": text,
        "intent": request.intent,
        "transaction": request.transaction,
        "propertyType": request.property_type,
        "areas": request.areas,
        "governorates": request.governorates,
        "minArea": request.min_area,
        "maxArea": request.max_area,
        "budget": request.budget,
        "rentBudget": request.rent_budget,
        "bedrooms": request.bedrooms,
        "income": request.income,
        "incomePeriod": request.income_period,
        "condition": request.condition,
        "features": request.features,
        "siteFeatures": request.site_features,
    }
    return json.dumps({"request": payload}, ensure_ascii=False, indent=2)


def _search_tool(params: dict[str, Any]) -> str:
    transaction = _opt_string(params, "transaction")
    area = _opt_string(params, "area")
    governorate = _opt_string(params, "governorate")
    property_type = _opt_string(params, "property_type")
    min_price = _opt_float(params, "min_price")
    max_price = _opt_float(params, "max_price")
    min_space = _opt_float(params, "min_space")
    limit = _opt_int(params, "limit", 20, 1, 50)
    offset = _opt_int(params, "offset", 0, 0, 10000)
    fmt = _opt_string(params, "format") or "markdown"

    rows: list[Any] = []
    for listing in load_listings():
        if transaction and normalize_text(listing.transaction) != normalize_text(transaction):
            continue
        if area and normalize_text(listing.area) != normalize_text(area):
            continue
        if governorate and normalize_text(listing.governorate) != normalize_text(governorate):
            continue
        if property_type and normalize_text(listing.property_type) != normalize_text(property_type):
            continue
        if min_price is not None and (listing.price is None or listing.price < min_price):
            continue
        if max_price is not None and (listing.price is None or listing.price > max_price):
            continue
        if min_space is not None and (listing.space is None or listing.space < min_space):
            continue
        rows.append(listing)

    total = len(rows)
    page = rows[offset : offset + limit]
    items = [_listing_summary(item) for item in page]

    if fmt == "json":
        return json.dumps({"items": items, **_pagination(total, limit, offset)}, ensure_ascii=False, indent=2)

    lines = [f"# نتائج البحث في بيانات الفريج", ""]
    if not items:
        lines.append("لا توجد إعلانات تطابق الفلاتر المحددة.")
        lines.append("نصيحة: جرّب إزالة بعض الفلاتر أو استخدم `alforaij_rank_properties` بنص طلب طبيعي.")
    for item in items:
        type_suffix = f" ({item['propertyType']})" if item["propertyType"] else ""
        gov_suffix = f"، {item['governorate']}" if item["governorate"] else ""
        space_text = f"{item['space']} م²" if item["space"] else "غير مذكورة"
        lines.append(f"## {item['code']} — {item['transaction']}{type_suffix}")
        lines.append(f"- **الموقع**: {item['area']}{gov_suffix}")
        lines.append(f"- **السعر**: {item['priceText']}")
        lines.append(f"- **المساحة**: {space_text}")
        if item["summary"]:
            lines.append(f"- **الوصف**: {item['summary'][:120]}")
        if item["originalUrl"]:
            lines.append(f"- **الرابط**: {item['originalUrl']}")
        lines.append("")
    lines.append(f"*عرض {len(page)} من {total} إعلان (offset={offset}).*")
    return "\n".join(lines)


def _rank_tool(params: dict[str, Any]) -> str:
    text = _require_string(params, "text")
    limit = _opt_int(params, "limit", 10, 1, 20)
    fmt = _opt_string(params, "format") or "markdown"

    request = parse_request(text)
    listings = load_listings()
    ranked = top_matches(request, listings, limit=limit, min_results=3)
    enriched = deduplicate_ranked(enrich_rankings(request, ranked, listings))[:limit]
    items = _ranked_rows(enriched)

    if fmt == "json":
        return json.dumps(
            {
                "request": {
                    "areas": request.areas,
                    "governorates": request.governorates,
                    "transaction": request.transaction,
                    "propertyType": request.property_type,
                    "budget": request.budget,
                },
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [f"# نتائج مرتبة حسب درجة التوصية", ""]
    if not items:
        lines.append("لم يتم العثور على نتائج ضمن بيانات الفريج لهذا الطلب.")
    for item in items:
        lines.append(
            f"## {item['code']} — {item['area']} — {item['priceText']}"
        )
        lines.append(
            f"- **التوصية**: {item['recommendationScore']}/100 · **الثقة**: {int(item['confidence'] * 100)}% · "
            f"**فرصة**: {item['dealScore']}/100"
        )
        lines.append(f"- **حكم السعر**: {item['valuationLabel']} — {item['valuationReason'][:120]}")
        if item.get("reasons"):
            lines.append(f"- **أسباب المطابقة**: {'؛ '.join(item['reasons'][:3])}")
        if item.get("warnings"):
            lines.append(f"- **تحذيرات**: {'؛ '.join(item['warnings'][:2])}")
        if item.get("originalUrl"):
            lines.append(f"- **الرابط**: {item['originalUrl']}")
        lines.append("")
    return "\n".join(lines)


def _evaluate_tool(params: dict[str, Any]) -> str:
    code = _require_string(params, "code")
    request_text = _opt_string(params, "request_text")
    fmt = _opt_string(params, "format") or "json"
    payload = _evaluate_code(code, request_text)
    if fmt == "markdown":
        result = payload["result"]
        governorate = result.get("governorate", "")
        governorate_suffix = f"({governorate})" if governorate else ""
        lines = [
            f"# تقييم الإعلان {code}",
            "",
            f"- **الموقع**: {result.get('area', '')} {governorate_suffix}",
            f"- **السعر**: {result.get('priceText', 'غير معلن')}",
            f"- **حكم السعر**: {result.get('valuationLabel', '—')}",
            f"- **السبب**: {result.get('valuationReason', '—')}",
            f"- **الثقة**: {int(result.get('confidence', 0) * 100)}%",
            f"- **الرابط**: {result.get('originalUrl', '')}",
        ]
        return "\n".join(lines)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _compare_tool(params: dict[str, Any]) -> str:
    codes = params.get("codes")
    if not isinstance(codes, list) or not codes:
        raise JsonRpcError(INVALID_PARAMS, "Parameter 'codes' is required and must be a non-empty array of listing codes")
    codes = [str(code).strip() for code in codes if str(code).strip()]
    if not 2 <= len(codes) <= 10:
        raise JsonRpcError(INVALID_PARAMS, "Provide between 2 and 10 listing codes to compare")
    request_text = _opt_string(params, "request_text")
    fmt = _opt_string(params, "format") or "markdown"

    evaluated = []
    for code in codes:
        payload = _evaluate_code(code, request_text)
        evaluated.append(payload)

    if fmt == "json":
        return json.dumps({"comparison": evaluated}, ensure_ascii=False, indent=2)

    lines = ["# مقارنة الإعلانات", ""]
    for payload in evaluated:
        result = payload["result"]
        code = result.get("code", "")
        area = result.get("area", "")
        price_text = result.get("priceText", "غير معلن")
        space_value = result.get("space")
        space_text = f"{space_value} م²" if space_value else "غير مذكورة"
        lines.append(f"## {code} — {area} — {price_text}")
        lines.append(f"- **حكم السعر**: {result.get('valuationLabel', '—')}")
        lines.append(f"- **المساحة**: {space_text}")
        lines.append(f"- **الثقة**: {int(result.get('confidence', 0) * 100)}%")
        lines.append("")
    return "\n".join(lines)


def _report_tool(params: dict[str, Any]) -> str:
    text = _require_string(params, "text")
    fmt = _opt_string(params, "format") or "markdown"

    request = parse_request(text)
    listings = load_listings()
    ranked = top_matches(request, listings, limit=40, min_results=3)
    enriched = enrich_rankings(request, ranked, listings)
    report = build_report(request, deduplicate_ranked(enriched)[:20], len(listings), [])

    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)

    lines = [
        "# تقرير البحث والتقييم",
        "",
        f"**الملخص**: {report.get('summary', '')}",
        "",
        f"**نطاق البحث**: {report.get('scope', '')}",
        "",
        "## النتائج المرتبة",
        "",
    ]
    for item in report.get("items", []) or []:
        code = item.get("code", "")
        area = item.get("area", "")
        price_text = item.get("priceText", "")
        rec = item.get("recommendationScore", "")
        label = item.get("valuationLabel", "")
        lines.append(f"### {code} — {area} — {price_text}")
        lines.append(f"- **التوصية**: {rec}/100 · **حكم السعر**: {label}")
        lines.append("")
    return "\n".join(lines)


def _sources_tool(params: dict[str, Any]) -> str:
    fmt = _opt_string(params, "format") or "markdown"
    registry = source_registry()
    payload = load_payload()
    records = payload.get("records", [])
    governorates: dict[str, int] = {}
    transactions: dict[str, int] = {}
    for row in records:
        governorates[str(row.get("governorate") or "غير محددة")] = governorates.get(str(row.get("governorate") or "غير محددة"), 0) + 1
        transactions[str(row.get("transaction") or "غير محددة")] = transactions.get(str(row.get("transaction") or "غير محددة"), 0) + 1

    data = {
        "totalRecords": len(records),
        "governorates": governorates,
        "transactions": transactions,
        "sources": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "category": item.get("category"),
                "status": item.get("status"),
                "role": item.get("role"),
            }
            for item in registry
        ],
    }

    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)

    lines = [
        "# مصادر البيانات وحالة التغطية",
        "",
        f"**إجمالي السجلات المحلية**: {len(records)}",
        "",
        "## التوزيع حسب المحافظة",
        "",
    ]
    for governorate, count in sorted(governorates.items(), key=lambda pair: -pair[1]):
        lines.append(f"- {governorate}: {count}")
    lines += ["", "## المصادر المسجلة", ""]
    for source in data["sources"]:
        lines.append(f"- **{source['name']}** ({source['category']}): {source['status']} — {source['role']}")
    return "\n".join(lines)


def _opportunities_tool(params: dict[str, Any]) -> str:
    limit_per_tier = _opt_int(params, "limit_per_tier", 30, 1, 50)
    include_external = _opt_bool(params, "include_external", False)
    fmt = _opt_string(params, "format") or "markdown"

    try:
        snapshot = build_opportunities(
            limit_per_tier=limit_per_tier,
            include_external=include_external,
            return_external=False,
        )
    except Exception as exc:  # المصادر الحية قد تفشل شبكيًا
        raise JsonRpcError(
            INVALID_PARAMS,
            f"تعذر بناء لقطة الفرص: {type(exc).__name__}: {exc} — جرّب include_external=false",
        ) from exc

    # تلخيص اللقطة إلى حقول خفيفة تناسب السياق
    tiers = snapshot.get("tiers", {})
    summary = {
        "tiers": {
            tier_name: {
                "label": tier.get("label"),
                "count": len(tier.get("items") or []),
            }
            for tier_name, tier in (tiers or {}).items()
        },
        "sourceStatuses": snapshot.get("sourceStatuses", []),
    }
    items = []
    for tier in (tiers or {}).values():
        for item in (tier.get("items") or [])[:limit_per_tier]:
            items.append(
                {
                    "code": item.get("code"),
                    "area": item.get("area"),
                    "governorate": item.get("governorate"),
                    "priceText": item.get("priceText"),
                    "opportunityScore": item.get("opportunityScore"),
                    "source": item.get("source"),
                    "reason": (item.get("opportunityReason") or "")[:140],
                    "originalUrl": item.get("originalUrl"),
                }
            )

    if fmt == "json":
        return json.dumps({"summary": summary, "items": items}, ensure_ascii=False, indent=2)

    lines = ["# فرص المكسب الحالية", "", f"**المصادر**: {len(snapshot.get('sourceStatuses', []))} منصة ساهمت", ""]
    for tier_name, tier_summary in summary["tiers"].items():
        lines.append(f"## {tier_summary['label']} — {tier_summary['count']} فرصة")
    lines.append("")
    for item in items[:20]:
        lines.append(
            f"- **{item['code']}** — {item['area']} — {item['priceText']}"
            f" (فرصة {item['opportunityScore']}/100)"
        )
    return "\n".join(lines)


def _answer_chat_query_tool(params: dict[str, Any]) -> str:
    text = _require_string(params, "text")
    include_external = _opt_bool(params, "include_external", False)
    include_local = _opt_bool(params, "include_local", True)
    default_source_mode = "all" if include_external and include_local else ("external" if include_external else "local")
    source_mode = _opt_string(params, "source_mode") or default_source_mode
    fmt = _opt_string(params, "format") or "json"

    request = parse_request(text)
    listings = load_listings() if include_local else []
    local_count = len(listings)
    source_statuses: list[dict[str, Any]] = []
    external_warning = ""

    if include_external:
        try:
            from backend.connectors.live_sources import search_external_sources

            external_listings, source_statuses = search_external_sources(request)
            listings.extend(external_listings)
        except Exception as exc:
            external_warning = f"تعذر فحص المصادر الخارجية: {type(exc).__name__}: {exc}"
            source_statuses.append({
                "name": "المصادر الخارجية",
                "status": "failed",
                "note": external_warning,
            })

    ranked = top_matches(request, listings, limit=40, min_results=3)
    enriched = deduplicate_ranked(enrich_rankings(request, ranked, listings))[:20]
    report = build_report(
        request,
        enriched,
        local_count,
        source_statuses,
        include_local_source=include_local,
    )
    from backend.services.chat_agents import build_chat_guidance

    guidance = build_chat_guidance(request, report, source_mode=source_mode)
    report["chatGuidance"] = guidance
    results = report.get("results") or []
    top_evidence = []
    if results:
        top = results[0]
        top_evidence = top.get("evidence") or top.get("comparables") or []

    payload = {
        "intent": guidance["intent"],
        "regionDecision": guidance["regionDecision"],
        "sourcePlan": guidance["sourcePlan"],
        "answer": guidance["answer"],
        "results": results[:10],
        "warnings": (guidance.get("dataQuality") or {}).get("warnings") or ([] if not external_warning else [external_warning]),
        "evidence": top_evidence,
    }

    if fmt == "markdown":
        lines = ["# إجابة الشات", "", guidance["answer"], ""]
        if payload["results"]:
            lines.append("## أفضل النتائج")
            for item in payload["results"][:5]:
                lines.append(f"- {item.get('code')} — {item.get('area')} — {item.get('priceText')} — {round(float(item.get('recommendationScore') or 0))}/100")
        if payload["warnings"]:
            lines += ["", "## تنبيهات"]
            lines.extend(f"- {warning}" for warning in payload["warnings"])
        return "\n".join(lines)
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ── سجل الأدوات ─────────────────────────────────────────────────────────

ANNOTATIONS_READONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

TOOLS: dict[str, dict[str, Any]] = {
    "alforaij_parse_request": {
        "name": "alforaij_parse_request",
        "description": (
            "يفسّر طلب عقاري بلغة طبيعية (عربي/إنجليزي) إلى حقول منظمة: نوع العملية، نوع العقار، "
            "المناطق، المحافظات، حدود المساحة والميزانية، عدد الغرف، الدخل الإيجاري، والمواصفات. "
            "مثال: «مطلوب بيت في المطلاع مساحة 400 بموازنة 300 ألف» → areas=['المطلاع']، min_area=400، budget=300000."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "نص الطلب العقاري كما يكتبه المستخدم (مثال: مطلوب شقة للبيع في السالمية)",
                }
            },
            "required": ["text"],
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _parse_request_tool,
    },
    "alforaij_search_properties": {
        "name": "alforaij_search_properties",
        "description": (
            "يبحث في إعلانات الفريج المحلية بفلاتر منظمة (العملية/المنطقة/المحافظة/نوع العقار/نطاق سعر/مساحة) "
            "مع ترقيم. يعيد ملخصًا لكل إعلان: الكود، الموقع، السعر، المساحة، الوصف المختصر والرابط الأصلي. "
            "النصيحة: لمطابقة ذكية بنص طلب طبيعي استخدم alforaij_rank_properties."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "transaction": {"type": "string", "description": "نوع العملية (للبيع / للإيجار / مطلوب للشراء ...)"},
                "area": {"type": "string", "description": "المنطقة (مثال: المطلاع، السالمية)"},
                "governorate": {"type": "string", "description": "المحافظة (مثال: الجهراء، حولي)"},
                "property_type": {"type": "string", "description": "نوع العقار (بيت، شقة، أرض، مخزن...)"},
                "min_price": {"type": "number", "description": "الحد الأدنى للسعر بالدينار الكويتي"},
                "max_price": {"type": "number", "description": "الحد الأقصى للسعر بالدينار الكويتي"},
                "min_space": {"type": "number", "description": "الحد الأدنى للمساحة بالمتر المربع"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _search_tool,
    },
    "alforaij_rank_properties": {
        "name": "alforaij_rank_properties",
        "description": (
            "يرتب الإعلانات حسب درجة التوصية لطلب طبيعي — نفس خوارزمية المنصة: مطابقة صارمة أولًا ثم توسعة "
            "محافظة ثم استرشادية عند ندرة النتائج، مع تقييم سعر كل نتيجة (مقارنات + أدلة) ودرجة فرصة وثقة. "
            "مثال: «مطلوب بيت في المطلاع مساحة 400»."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "نص الطلب العقاري الكامل"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["text"],
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _rank_tool,
    },
    "alforaij_evaluate_property": {
        "name": "alforaij_evaluate_property",
        "description": (
            "يقيم إعلانًا واحدًا بكوده (AF-314 مثلًا): حكم السعر (سعر عادل/مبالغ/أقل من السوق)، السبب، عدد المقارنات "
            "والأدلة، درجة الثقة، التمويل، العائد الإيجاري إن وُجد. request_text اختياري لتوجيه نطاق المقارنات."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "كود الإعلان (مثال: AF-314)"},
                "request_text": {"type": "string", "description": "اختياري — نص الطلب لتوجيه نطاق المقارنات"},
                "format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
            },
            "required": ["code"],
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _evaluate_tool,
    },
    "alforaij_compare_properties": {
        "name": "alforaij_compare_properties",
        "description": (
            "يقارن من 2 إلى 10 إعلانات جنبًا إلى جنب: حكم السعر، المساحة، الثقة، درجة الفرصة — عبر نفس خط "
            "أنابيب التقييم. مثال: codes=['AF-314', 'AF-315', 'AF-320']."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 10,
                    "description": "أكواد الإعلانات للمقارنة",
                },
                "request_text": {"type": "string", "description": "اختياري — نص الطلب لتوجيه نطاق المقارنات"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["codes"],
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _compare_tool,
    },
    "alforaij_generate_report": {
        "name": "alforaij_generate_report",
        "description": (
            "يولّد تقرير البحث والتقييم الكامل لطلب طبيعي: الملخص، النطاق، النتائج المرتبة بأدلة ومقارنات "
            "وتحذيرات — بنفس شكل تقرير المنصة النهائي. مثال: «مطلوب بيت في المطلاع مساحة 400»."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "نص الطلب العقاري"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["text"],
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _report_tool,
    },
    "alforaij_list_sources": {
        "name": "alforaij_list_sources",
        "description": (
            "يعيد حالة مصادر البيانات: عدد السجلات المحلية، توزيعها حسب المحافظة ونوع العملية، والمصادر "
            "المسجلة (الفريج المحلي، OpenSooq، Mourjan، Q8Aqar...) بحالة اتصالها ودورها في التقييم."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"}
            },
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _sources_tool,
    },
    "alforaij_get_opportunities": {
        "name": "alforaij_get_opportunities",
        "description": (
            "يعيد لقطة فرص المكسب الحالية: فئات زمنية (جديدة/حديثة/قائمة) مع عدد الفرص، وكل فرصة بدرجتها "
            "ومصدرها وسببها ورابطها. include_external=true يدمج إعلانات الأسواق الخارجية الحية (يتطلب شبكة)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit_per_tier": {"type": "integer", "minimum": 1, "maximum": 50, "default": 30},
                "include_external": {
                    "type": "boolean",
                    "default": False,
                    "description": "دمج الإعلانات الحية من المصادر الخارجية (يتطلب شبكة)",
                },
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _opportunities_tool,
    },
    "alforaij_answer_chat_query": {
        "name": "alforaij_answer_chat_query",
        "description": (
            "يجيب على سؤال شات عقاري بجواب مختصر مع النية والنطاق وخطة المصادر وجودة البيانات. "
            "يعيد نفس بنية وكلاء الشات في المنصة: intent وregionDecision وsourcePlan وanswer وresults وwarnings وevidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "نص سؤال المستخدم أو طلبه العقاري"},
                "include_external": {"type": "boolean", "default": False, "description": "محاولة فحص المصادر الخارجية الحية"},
                "include_local": {"type": "boolean", "default": True, "description": "استخدام بيانات الفريج المحلية"},
                "source_mode": {"type": "string", "description": "local / all / source / custom"},
                "format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
            },
            "required": ["text"],
        },
        "annotations": ANNOTATIONS_READONLY,
        "handler": _answer_chat_query_tool,
    },
}
