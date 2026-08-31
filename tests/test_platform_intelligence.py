from __future__ import annotations

from backend.services.platform_intelligence import build_platform_intelligence


def test_platform_intelligence_summarizes_partner_and_official_sources() -> None:
    data = build_platform_intelligence()

    assert data["summary"]["total"] >= 20
    assert data["summary"]["partnerRequired"] >= 3
    assert data["summary"]["official"] >= 3

    sources = {source["id"]: source for source in data["sources"]}
    assert sources["propertyfinder_kw"]["bucket"] == "partner_required"
    assert sources["bayut_kw"]["bucket"] == "partner_required"
    assert sources["moj_real_estate"]["bucket"] == "official"
    assert "partner_feeds" in sources["bayut_kw"]["databaseTables"]


def test_platform_intelligence_exposes_database_quality_rules() -> None:
    data = build_platform_intelligence()
    strategy = data["databaseStrategy"]

    assert "market_listings" in strategy["coreTables"]
    assert "source_runs" in strategy["coreTables"]
    assert any("first_seen_at" in rule for rule in strategy["qualityRules"])
