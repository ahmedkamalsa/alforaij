from __future__ import annotations

from backend.services.analysis_agents import build_analysis_agent_trace
from backend.services.request_parser import parse_request


def test_analysis_agent_trace_contains_core_agents_and_ai_attempts() -> None:
    request = parse_request("بيت 400م في السالمية بحدود 250000 دينار")
    report = {
        "analysisMethod": "local",
        "aiInsights": {
            "analysisMethod": "local",
            "_ai_provider": "local",
            "_ai_model": "deterministic-fallback",
            "_ai_attempts": [{"provider": "nvidia_nim", "status": "unavailable"}],
        },
        "results": [
            {
                "code": "AF-1",
                "price": 240000,
                "recommendationScore": 84,
                "confidence": 0.82,
                "marketMedian": 270000,
                "dataQuality": {"label": "قوية"},
            }
        ],
        "limitations": ["التقييم استرشادي"],
        "demandIndicators": {"count": 3, "buyRequests": 2, "rentRequests": 1, "scope": "السالمية"},
    }
    statuses = [{"name": "الفريج", "status": "success", "records": 1}]

    trace = build_analysis_agent_trace(request, report, statuses, report["aiInsights"])

    ids = [agent["id"] for agent in trace["agents"]]
    assert ids == [
        "intent_agent",
        "source_agent",
        "quality_agent",
        "valuation_agent",
        "demand_agent",
        "report_agent",
    ]
    assert trace["ai"]["provider"] == "local"
    assert trace["ai"]["attempts"][0]["provider"] == "nvidia_nim"
    assert trace["agents"][4]["outputs"]["matchingDemand"] == 3
