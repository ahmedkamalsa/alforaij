"""اختبار ضمانة الحصاد الفعلي: كل منطقة تظهر في بيانات market_listings تُحل إلى محافظة في اللوحة.

نفس ضمانة test_area_governorate_map.py وtest_kuwait_areas_coords.py ممتدة إلى
البيانات الفعلية: أي منطقة في الحصاد المتراكم (الفريج المحلي + المواقع الخارجية)
لا تعرفها الخريطة المعتمدة تكسر الاختبار قبل أن تتكدس تحت «غير محددة» في اللوحة.

ثلاثة مصادر بنفس الضمانة، والفحص دائمًا بالخريطة المعتمدة وحدها
(_area_governorate_map([]) — بلا تعلم من البيانات) لأن التعلم شبكة أمان،
والضمانة الحقيقية أن الخريطة تغطي كل ما يصل فعلًا:
1. بيانات الفريج المحلية (data/seed_listings.json) — تعمل دائمًا دون شبكة.
2. لقطة الحصاد المتراكم (frontend/static-data/dashboard-summary.json) — إن وُجدت.
3. market_listings الحية من Supabase — تفعيلها صريح في وضع الاختبار عبر
   ALFORAIJ_TEST_ALLOW_SUPABASE=1 (مفتاح أمان المشروع: الاختبارات لا تلمس القاعدة
   افتراضيًا، انظر remote_reads_enabled في supabase_store)، وتُتخطى بدونه.

والضمانة ممتدة أيضًا لمسار تحليلات السوق (MarketAnalysisGovernorateTests): دلاء
المحافظات في التحليلات تبني من نفس خريطة اللوحة المعتمدة — فلا «محافظة الاحمدي»
بلا همزة بجانب «محافظة الأحمدي»، ولا انقسام دلو المحافظة نفسها بين صيغة قصيرة
وأخرى كاملة كما كان يحدث في market-insights (الأحمدي + محافظة الأحمدي معًا).
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from typing import Any

from backend.connectors.alforaij import load_listings
from backend.main import _area_governorate_map, _normalize_dashboard_place

ROOT = Path(__file__).resolve().parents[1]
# لقطة الحصاد المتراكم كما تراه اللوحة — تُصدَّر دوريًا إلى static-data/
SNAPSHOT_PATH = ROOT / "frontend" / "static-data" / "dashboard-summary.json"


def _to_record(row: Any) -> dict[str, str]:
    """صف الحصاد (كائن Listing أو dict) → سجل بالشكل الذي تتوقعه اللوحة."""
    if hasattr(row, "area"):
        return {
            "area": str(row.area or "").strip(),
            "governorate": str(row.governorate or "").strip(),
            "summary": str(row.summary or ""),
            "features": str(row.features or ""),
        }
    return {
        "area": str(row.get("area") or "").strip(),
        "governorate": str(row.get("governorate") or "").strip(),
        "summary": str(row.get("summary") or ""),
        "features": str(row.get("features") or ""),
    }


def _unresolved_areas(rows: list[Any]) -> list[str]:
    """المناطق التي تحمل اسمًا لكنها تبقى بلا محافظة بعد تطبيع اللوحة.

    الخريطة المعتمدة وحدها (بلا تعلم من السجلات) — فلو اعتمدنا التعلم لغطى
    الاختبارُ أيَّ فجوة، والضمانة المطلوبة أن الخريطة تكفي وحدها.
    """
    area_map = _area_governorate_map([])
    unresolved: list[str] = []
    for row in rows:
        record = _to_record(row)
        if not record["area"]:
            continue  # «بلا موقع» — لا منطقة أصلًا، خارج نطاق هذه الضمانة
        _normalize_dashboard_place(record, area_map)
        if not record.get("governorate"):
            unresolved.append(record["area"])
    return unresolved


def _live_market_rows() -> list[dict[str, Any]]:
    from backend.services.supabase_store import fetch_market_listings

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = fetch_market_listings(limit=1000, offset=offset) or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


# المحافظات الست الكنسية + «غير محددة» — القيم الوحيدة المسموحة لدلاء التحليلات
CANONICAL_ANALYSIS_BUCKETS = {
    "غير محددة",
    "محافظة العاصمة",
    "محافظة حولي",
    "محافظة الفروانية",
    "محافظة الأحمدي",
    "محافظة الجهراء",
    "محافظة مبارك الكبير",
}


def _analysis_issues(rows: list[Any]) -> tuple[list[str], list[str]]:
    """مشكلات مسار التحليل: (مناطق بلا محافظة، دلاء محافظات غير كنسية).

    يمرر الصفوف عبر نفس قمع التحليل (normalize_dashboard_place مع keep_governorate_area
    ثم build_demand_indicators / build_market_insights) ويفحص مخرجات الدلاء الفعلية.
    """
    from backend.services.market_analysis import build_demand_indicators, build_market_insights
    from backend.services.request_parser import area_governorate_map, normalize_dashboard_place

    area_map = area_governorate_map([])
    normalized: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for row in rows:
        record = _to_record(row)
        if not record["area"]:
            continue
        normalize_dashboard_place(record, area_map, keep_governorate_area=True)
        if not record.get("governorate"):
            unresolved.append(record["area"])
            continue
        record["transaction"] = str(row.get("transaction") if isinstance(row, dict) else getattr(row, "transaction", "") or "")
        record["price"] = row.get("price") if isinstance(row, dict) else getattr(row, "price", None)
        record["space"] = row.get("space") if isinstance(row, dict) else getattr(row, "space", None)
        record["fetched_at"] = str(
            (row.get("fetched_at") if isinstance(row, dict) else "")
            or (row.get("publishedDate") if isinstance(row, dict) else getattr(row, "published_date", "") or "")
            or ""
        )
        normalized.append(record)

    demand = build_demand_indicators(normalized)
    insights = build_market_insights(normalized)
    buckets: set[str] = set()
    buckets.update(g["governorate"] for g in demand.get("governorates", []))
    buckets.update(g["governorate"] for g in insights.get("governorates", []))
    buckets.update(a.get("governorate") for a in insights.get("areas", []) if a.get("governorate"))
    non_canonical = sorted(buckets - CANONICAL_ANALYSIS_BUCKETS)
    return unresolved, non_canonical


class MarketAnalysisGovernorateTests(unittest.TestCase):
    """ضمانة مسار تحليلات السوق: دلاء المحافظات من نفس خريطة اللوحة المعتمدة.

    تكشف انحرافين كانا موجودين: «محافظة الاحمدي» بلا همزة في market-demand
    (تطبيع همزات يدوي مختلف عن اللوحة)، ودلاء منقسمة في market-insights
    (الأحمدي + محافظة الأحمدي كدلوين منفصلين) — وكلاهما الآن صيغ كنسية موحدة.
    """

    def _assert_analysis_clean(self, rows: list[Any], source_label: str) -> None:
        unresolved, non_canonical = _analysis_issues(rows)
        counts: dict[str, int] = {}
        for area in unresolved:
            counts[area] = counts.get(area, 0) + 1
        self.assertEqual(
            unresolved,
            [],
            f"مناطق من {source_label} تبقى بلا محافظة في مسار تحليلات السوق: "
            + "، ".join(f"{a} ×{n}" for a, n in sorted(counts.items(), key=lambda kv: -kv[1])),
        )
        self.assertEqual(
            non_canonical,
            [],
            f"دلاء محافظات غير كنسية في تحليلات {source_label} (يجب أن تبني من خريطة اللوحة): "
            + "، ".join(non_canonical),
        )

    def test_local_seed_analysis_buckets_canonical(self) -> None:
        listings = load_listings()
        self.assertGreaterEqual(len(listings), 1)
        self._assert_analysis_clean(listings, "بيانات الفريج المحلية")

    def test_market_snapshot_analysis_buckets_canonical(self) -> None:
        if not SNAPSHOT_PATH.exists():
            self.skipTest("لقطة dashboard-summary.json غير موجودة")
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = data.get("records") or []
        if not rows:
            self.skipTest("لقطة dashboard-summary.json فارغة")
        self._assert_analysis_clean(rows, "لقطة الحصاد المتراكم")

    def test_live_analysis_buckets_canonical(self) -> None:
        if os.getenv("ALFORAIJ_TEST_ALLOW_SUPABASE") != "1":
            self.skipTest(
                "الفحص الحي معطّل في وضع الاختبار — شغّل مع ALFORAIJ_TEST_ALLOW_SUPABASE=1"
            )
        try:
            rows = _live_market_rows()
        except Exception as exc:
            self.skipTest(f"market_listings الحية غير متاحة: {type(exc).__name__}: {exc}")
        if not rows:
            self.skipTest("market_listings الحية فارغة أو غير مهيأة")
        self._assert_analysis_clean(rows, "market_listings الحية")


class MarketHarvestGovernorateTests(unittest.TestCase):
    def _assert_all_areas_resolve(self, rows: list[Any], source_label: str) -> None:
        unresolved = _unresolved_areas(rows)
        counts: dict[str, int] = {}
        for area in unresolved:
            counts[area] = counts.get(area, 0) + 1
        self.assertEqual(
            unresolved,
            [],
            f"مناطق من {source_label} تبقى بلا محافظة في اللوحة (الخريطة المعتمدة لا تغطيها): "
            + "، ".join(f"{area} ×{n}" for area, n in sorted(counts.items(), key=lambda kv: -kv[1])),
        )

    def test_local_seed_areas_resolve(self) -> None:
        """بيانات الفريج المحلية (خط الأساس) — تعمل دائمًا دون شبكة."""
        listings = load_listings()
        self.assertGreaterEqual(len(listings), 1)
        self._assert_all_areas_resolve(listings, "بيانات الفريج المحلية")

    def test_market_snapshot_areas_resolve(self) -> None:
        """لقطة الحصاد المتراكم (market_listings كما تراه اللوحة وقت التصدير)."""
        if not SNAPSHOT_PATH.exists():
            self.skipTest("لقطة dashboard-summary.json غير موجودة")
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = data.get("records") or []
        if not rows:
            self.skipTest("لقطة dashboard-summary.json فارغة")
        self._assert_all_areas_resolve(rows, "لقطة الحصاد المتراكم")

    def test_live_market_listings_areas_resolve(self) -> None:
        """market_listings الحية من Supabase — القاعدة الفعلية كما يقرؤها الخادم.

        تُتخطى عند غياب إعدادات القاعدة أو انقطاع الشبكة (لا تربط الاختبارات
        بالشبكة إجباريًا)، وتُفحص بالكامل عبر الترقيم الصفحاتي.
        """
        if os.getenv("ALFORAIJ_TEST_ALLOW_SUPABASE") != "1":
            self.skipTest(
                "market_listings الحية معطّلة في وضع الاختبار — شغّل مع "
                "ALFORAIJ_TEST_ALLOW_SUPABASE=1 لتفعيل الفحص الحي"
            )
        try:
            rows = _live_market_rows()
        except Exception as exc:  # شبكة/مهلة/أذونات — تُتخطى ولا تكسر المجموعة
            self.skipTest(f"market_listings الحية غير متاحة: {type(exc).__name__}: {exc}")
        if not rows:
            self.skipTest("market_listings الحية فارغة أو غير مهيأة")
        self._assert_all_areas_resolve(rows, "market_listings الحية")


if __name__ == "__main__":
    unittest.main()
