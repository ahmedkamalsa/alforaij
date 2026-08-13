"""اختبارات وحدة للكاش الذكي في `backend/main.py`.

تغطي ثلاثة سلوكيات حتى لا تنكسر مستقبلًا:
1. قرار كاش اللوحة: الافتراضية (كل المنصات + المحلي) تُخزَّن، والفلاتر المخصصة
   أو إقصاء المحلي تُبنى حية دائمًا (لا كاش).
2. مساعد الكاش العام `_ttl_cached`: يبني عند أول طلب، يعيد من الكاش ضمن المدة
   بلا بناء ثانٍ، ويبني من جديد بعد انتهاء الصلاحية.
3. تسخين كاش الفرص عند الإقلاع `_warm_opportunities_cache`: يملأ الكاش من
   لقطة Supabase، ويتسامح مع فشل القاعدة بلا أن يرمي.
"""
from __future__ import annotations

import time
import unittest
from unittest import mock


class SmartCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        from backend import main

        # عزل الكاش العام حتى لا تتسرب الحالة بين الاختبارات
        main._TTL_CACHE.clear()
        main._OPPORTUNITIES_CACHE = None
        main._OPPORTUNITIES_CACHE_AT = 0.0

    def tearDown(self) -> None:
        from backend import main

        main._TTL_CACHE.clear()
        main._OPPORTUNITIES_CACHE = None
        main._OPPORTUNITIES_CACHE_AT = 0.0

    # ── قرار كاش اللوحة الذكي: الافتراضية مخزنة والفلاتر حية ────────────────
    def test_dashboard_default_is_cached(self) -> None:
        from backend.main import _dashboard_cache_key

        # لا فلاتر + المحلي مفعّل = اللوحة الافتراضية → تُخزَّن
        self.assertEqual(_dashboard_cache_key(set(), True), "dashboard:default")

    def test_dashboard_filters_are_live(self) -> None:
        from backend.main import _dashboard_cache_key

        # أي فلتر مخصص → حي دائمًا (لا كاش) حتى لا ينتظر المستخدم لقطة قديمة
        self.assertIsNone(_dashboard_cache_key({"OpenSooq"}, True))
        self.assertIsNone(_dashboard_cache_key({"الفريج"}, True))
        self.assertIsNone(_dashboard_cache_key({"Mourjan", "Q8Aqar"}, True))

    def test_dashboard_without_local_is_live(self) -> None:
        from backend.main import _dashboard_cache_key

        # إقصاء المحلي (includeLocal=0) يغير معنى اللوحة → يُبنى حيًا
        self.assertIsNone(_dashboard_cache_key(set(), False))

    # ── مساعد الكاش العام: بناء ثم كاش ثم إعادة بناء بعد الانتهاء ───────────
    def test_ttl_cached_builds_once_and_reuses_within_ttl(self) -> None:
        from backend.main import _ttl_cached

        calls = {"n": 0}

        def builder() -> dict:
            calls["n"] += 1
            return {"value": calls["n"]}

        first = _ttl_cached("key:once", 60, builder)
        second = _ttl_cached("key:once", 60, builder)
        self.assertEqual(first, {"value": 1})
        self.assertEqual(second, {"value": 1})
        # البناء جرى مرة واحدة فقط — الثاني من الكاش
        self.assertEqual(calls["n"], 1)

    def test_ttl_cached_rebuilds_after_expiry(self) -> None:
        from backend import main

        calls = {"n": 0}

        def builder() -> dict:
            calls["n"] += 1
            return {"value": calls["n"]}

        main._ttl_cached("key:expire", 60, builder)
        # محاكاة انتهاء المدة: ندفع الطابع الزمني للوراء
        entry = main._TTL_CACHE["key:expire"]
        main._TTL_CACHE["key:expire"] = (entry[0] - 61, entry[1])
        rebuilt = main._ttl_cached("key:expire", 60, builder)
        self.assertEqual(rebuilt, {"value": 2})
        self.assertEqual(calls["n"], 2)

    def test_ttl_cached_keys_are_isolated(self) -> None:
        from backend.main import _ttl_cached

        def build_a() -> dict:
            return {"a": 1}

        def build_b() -> dict:
            return {"b": 2}

        self.assertEqual(_ttl_cached("k:a", 60, build_a), {"a": 1})
        self.assertEqual(_ttl_cached("k:b", 60, build_b), {"b": 2})

    # ── تسخين كاش الفرص عند الإقلاع ─────────────────────────────────────────
    def test_warm_opportunities_cache_fills_from_supabase(self) -> None:
        from backend import main

        snapshot = {"generatedAt": "2026-08-13T06:00:00", "tiers": {"daily": {"items": []}}}
        with mock.patch("backend.services.supabase_store.fetch_latest_opportunities", return_value=snapshot):
            main._warm_opportunities_cache()
        self.assertEqual(main._OPPORTUNITIES_CACHE, snapshot)
        self.assertGreater(main._OPPORTUNITIES_CACHE_AT, 0.0)

    def test_warm_opportunities_cache_tolerates_failure(self) -> None:
        from backend import main

        with mock.patch(
            "backend.services.supabase_store.fetch_latest_opportunities",
            side_effect=Exception("supabase down"),
        ):
            # يجب ألا يرمي — يفشل بصمت ويبقى الكاش فارغًا لمسار السقوط
            main._warm_opportunities_cache()
        self.assertIsNone(main._OPPORTUNITIES_CACHE)

    def test_warm_opportunities_cache_ignores_empty_snapshot(self) -> None:
        from backend import main

        with mock.patch("backend.services.supabase_store.fetch_latest_opportunities", return_value=None):
            main._warm_opportunities_cache()
        self.assertIsNone(main._OPPORTUNITIES_CACHE)


if __name__ == "__main__":
    unittest.main()
