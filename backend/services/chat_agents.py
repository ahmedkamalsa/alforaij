from __future__ import annotations

from typing import Any

from backend.models import PropertyRequest


def _result_list(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("results") or []
    return rows if isinstance(rows, list) else []


def _source_status(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("sourceStatus") or []
    return rows if isinstance(rows, list) else []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _intent_label(request: PropertyRequest) -> str:
    if request.transaction == "مطلوب للإيجار":
        return "طلب استئجار"
    if request.transaction == "مطلوب للشراء":
        return "طلب شراء"
    if request.transaction == "للإيجار":
        return "عرض إيجار"
    if request.transaction == "للبيع":
        return "عرض بيع"
    if request.transaction:
        return request.transaction
    return "بحث عقاري"


def _region_decision(request: PropertyRequest, report: dict[str, Any]) -> dict[str, Any]:
    results = _result_list(report)
    result_areas = _unique([str(item.get("area") or "") for item in results[:10]])
    mode = "all"
    if request.areas:
        mode = "areas"
    elif request.governorates:
        mode = "governorates"
    explanation = "النطاق من نص الطلب."
    if not request.areas and not request.governorates:
        explanation = "لم تُذكر منطقة محددة؛ البحث على البيانات المتاحة."
    elif result_areas and request.areas:
        explanation = "النتائج محصورة في المنطقة المطلوبة أو توسعة معلنة عند ندرة البيانات."
    return {
        "mode": mode,
        "areas": request.areas,
        "governorates": request.governorates,
        "resultAreas": result_areas,
        "explanation": explanation,
    }


def _source_plan(report: dict[str, Any], source_mode: str | None = None) -> dict[str, Any]:
    statuses = _source_status(report)
    names = _unique([str(row.get("name") or row.get("source") or "") for row in statuses])
    active = [
        str(row.get("name") or row.get("source") or "")
        for row in statuses
        if str(row.get("status") or "").lower() in {"ok", "success", "completed", "منفذ ✓"}
    ]
    return {
        "mode": source_mode or "local",
        "sources": names,
        "activeSources": _unique(active),
        "count": len(names),
        "note": "المصادر الظاهرة هي التي شاركت في هذا التقرير.",
    }


def _data_quality(report: dict[str, Any]) -> dict[str, Any]:
    results = _result_list(report)
    warnings: list[str] = []
    missing_price = sum(1 for item in results if not item.get("price") and not item.get("priceText"))
    missing_area = sum(1 for item in results if not item.get("area"))
    missing_space = sum(1 for item in results if not item.get("space"))
    outside = sum(
        1
        for item in results
        if any("خارج المنطقة المطلوبة" in str(w) for w in (item.get("warnings") or []))
    )
    if missing_price:
        warnings.append(f"{missing_price} نتيجة بلا سعر واضح")
    if missing_area:
        warnings.append(f"{missing_area} نتيجة بلا منطقة واضحة")
    if missing_space:
        warnings.append(f"{missing_space} نتيجة بلا مساحة")
    if outside:
        warnings.append(f"{outside} نتيجة توسعة خارج النطاق")
    return {
        "warnings": warnings,
        "missing": {
            "price": missing_price,
            "area": missing_area,
            "space": missing_space,
        },
        "expandedResults": outside,
    }


def _answer(request: PropertyRequest, report: dict[str, Any], quality: dict[str, Any]) -> str:
    results = _result_list(report)
    if not results:
        scope = "، ".join(request.areas or request.governorates) or "النطاق المطلوب"
        return f"لا توجد نتائج كافية في {scope}. جرّب توسيع المنطقة أو تعديل السعر."
    top = results[0]
    area = top.get("area") or (request.areas[0] if request.areas else "منطقة غير محددة")
    price = top.get("priceText") or "سعر غير معلن"
    score = round(float(top.get("recommendationScore") or 0))
    reason = str(top.get("valuationReason") or top.get("summary") or "").strip()
    reason = reason.split(".")[0].strip() if reason else "مطابقة أعلى حسب السعر والمنطقة والمواصفات."
    note = f" تنبيه: {'؛ '.join(quality.get('warnings') or [])}." if quality.get("warnings") else ""
    return f"أفضل نتيجة في {area}: {price} بدرجة {score}/100. السبب: {reason}.{note}"


def build_chat_guidance(
    request: PropertyRequest,
    report: dict[str, Any],
    source_mode: str | None = None,
) -> dict[str, Any]:
    quality = _data_quality(report)
    return {
        "intent": {
            "label": _intent_label(request),
            "transaction": request.transaction,
            "propertyType": request.property_type,
            "budget": request.budget,
            "rentBudget": request.rent_budget,
            "area": request.min_area or request.max_area,
        },
        "regionDecision": _region_decision(request, report),
        "sourcePlan": _source_plan(report, source_mode),
        "dataQuality": quality,
        "answer": _answer(request, report, quality),
    }
