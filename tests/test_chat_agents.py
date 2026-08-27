from __future__ import annotations

from backend.models import PropertyRequest
from backend.services.chat_agents import build_chat_guidance


def test_chat_guidance_returns_concise_region_answer() -> None:
    request = PropertyRequest(
        raw_text="مطلوب بيت في السالمية بحدود 300 ألف مساحة 400",
        transaction="مطلوب للشراء",
        property_type="بيت",
        areas=["السالمية"],
        min_area=400,
        max_area=400,
        budget=300000,
    )
    report = {
        "results": [
            {
                "area": "السالمية",
                "priceText": "295,000 د.ك",
                "recommendationScore": 88,
                "valuationReason": "أقل من وسيط المنطقة",
                "source": "الفريج",
            }
        ],
        "sourceStatus": [{"name": "الفريج", "status": "ok"}],
    }

    guidance = build_chat_guidance(request, report, source_mode="local")

    assert guidance["intent"]["label"] == "طلب شراء"
    assert guidance["regionDecision"]["areas"] == ["السالمية"]
    assert guidance["sourcePlan"]["sources"] == ["الفريج"]
    assert "أفضل نتيجة في السالمية" in guidance["answer"]
