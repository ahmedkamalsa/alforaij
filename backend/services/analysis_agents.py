from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from backend.models import PropertyRequest


def _status_counts(statuses: list[dict[str, Any]]) -> dict[str, int]:
    success = 0
    failed = 0
    partial = 0
    for item in statuses:
        status = str(item.get("status") or "").lower()
        records = int(item.get("records") or item.get("candidates") or 0)
        if status in {"success", "connected"} or records > 0:
            success += 1
        elif status in {"failed", "error"}:
            failed += 1
        else:
            partial += 1
    return {"success": success, "failed": failed, "partial": partial}


def _first_result(report: dict[str, Any]) -> dict[str, Any]:
    results = report.get("results") or []
    return results[0] if results else {}


def build_analysis_agent_trace(
    request: PropertyRequest,
    report: dict[str, Any],
    statuses: list[dict[str, Any]],
    ai_insights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic trace of the agents that contributed to the analysis."""
    top = _first_result(report)
    status_counts = _status_counts(statuses or [])
    demand = report.get("demandIndicators") or {}
    ai = ai_insights or report.get("aiInsights") or {}
    ai_attempts = ai.get("_ai_attempts") or []
    provider = ai.get("_ai_provider") or ("local" if ai.get("analysisMethod") == "local" else "")
    model = ai.get("_ai_model") or ("deterministic-fallback" if provider == "local" else "")

    agents = [
        {
            "id": "intent_agent",
            "name": "وكيل فهم الطلب",
            "status": "done",
            "summary": "حوّل نص المستخدم إلى نوع معاملة، نوع عقار، مناطق، وميزانية.",
            "outputs": {
                "transaction": request.transaction,
                "propertyType": request.property_type,
                "areas": request.areas,
                "governorates": request.governorates,
                "budget": request.budget,
            },
        },
        {
            "id": "source_agent",
            "name": "وكيل المصادر",
            "status": "done",
            "summary": "راجع المصادر التي دخلت البحث وسجل نجاحها أو فشلها.",
            "outputs": {
                "success": status_counts["success"],
                "partial": status_counts["partial"],
                "failed": status_counts["failed"],
            },
        },
        {
            "id": "quality_agent",
            "name": "وكيل جودة البيانات",
            "status": "done",
            "summary": "قيّم قوة الدليل بناء على عدد النتائج والمقارنات ونقص البيانات.",
            "outputs": {
                "resultCount": len(report.get("results") or []),
                "topDataQuality": top.get("dataQuality") or "لا توجد نتيجة عليا",
                "limitations": report.get("limitations") or [],
            },
        },
        {
            "id": "valuation_agent",
            "name": "وكيل التقييم",
            "status": "done",
            "summary": "استخدم أرقام التقييم الحتمية: سعر، وسيط مقارنات، نسبة السعر، وثقة.",
            "outputs": {
                "topCode": top.get("code"),
                "topPrice": top.get("price"),
                "topRecommendation": top.get("recommendationScore"),
                "topConfidence": top.get("confidence"),
                "marketMedian": top.get("marketMedian"),
            },
        },
        {
            "id": "demand_agent",
            "name": "وكيل طلبات المستخدمين",
            "status": "done" if demand else "skipped",
            "summary": "ربط التحليل بما يبحث عنه المستخدمون والعملاء المحتملون عند توفر البيانات.",
            "outputs": {
                "matchingDemand": demand.get("count", 0),
                "buyRequests": demand.get("buyRequests", 0),
                "rentRequests": demand.get("rentRequests", 0),
                "scope": demand.get("scope", ""),
            },
        },
        {
            "id": "report_agent",
            "name": "وكيل التقرير",
            "status": "done",
            "summary": "صاغ التقرير النهائي بالعربية مع فصل الأرقام عن التفسير.",
            "outputs": {
                "analysisMethod": report.get("analysisMethod") or ai.get("analysisMethod") or "none",
                "aiProvider": provider,
                "aiModel": model,
                "aiAttempts": ai_attempts,
            },
        },
    ]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "request": asdict(request),
        "ai": {
            "provider": provider,
            "model": model,
            "method": report.get("analysisMethod") or ai.get("analysisMethod") or "none",
            "attempts": ai_attempts,
        },
        "agents": agents,
    }
