from __future__ import annotations

import unittest


class TestOutreachTracking(unittest.TestCase):
    """اختبارات تتبع نقرات التسويق (outreach_clicks) في Supabase."""

    def test_save_outreach_click_builds_row(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_post") as post:
            result = supabase_store.save_outreach_click({
                "clientPhone": "96555559950",
                "clientArea": "النهضة",
                "clientType": "بيت",
                "opportunityCode": "MJ-1",
                "action": "send",
                "channel": "client_send",
            })
        self.assertEqual(result["status"], "saved")
        args = post.call_args[0]
        self.assertEqual(args[0], "outreach_clicks")
        self.assertEqual(args[1][0]["client_phone"], "96555559950")
        self.assertEqual(args[1][0]["client_area"], "النهضة")
        self.assertEqual(args[1][0]["action"], "send")
        self.assertEqual(args[1][0]["channel"], "client_send")

    def test_save_outreach_click_not_configured_is_graceful(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "is_configured", return_value=False):
            result = supabase_store.save_outreach_click({"opportunityCode": "X"})
        self.assertEqual(result["status"], "not_configured")

    def test_save_outreach_click_tolerates_missing_table(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "_post", side_effect=RuntimeError("HTTP 404 relation does not exist")):
            result = supabase_store.save_outreach_click({"opportunityCode": "X"})
        self.assertEqual(result["status"], "failed")
        self.assertIn("404", result["error"])

    def test_fetch_outreach_stats_aggregates_per_client(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        rows = [
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "copy", "created_at": "2026-08-08T10:00:00"},
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "send", "created_at": "2026-08-08T11:00:00"},
            {"client_phone": "9652", "client_area": "المطلاع", "client_type": "شقة", "action": "send", "created_at": "2026-08-08T09:00:00"},
            {"client_phone": "", "client_area": "", "client_type": "", "action": "send", "created_at": "2026-08-08T08:00:00"},
        ]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=rows):
            stats = supabase_store.fetch_outreach_stats()
        self.assertTrue(stats["tableOk"])
        self.assertEqual(stats["totals"]["total"], 4)
        self.assertEqual(stats["totals"]["copies"], 1)
        self.assertEqual(stats["totals"]["sends"], 3)
        self.assertEqual(stats["totals"]["clients"], 3)  # عميلان + «غير مرتبط بعميل»
        by_phone = {c["phone"]: c for c in stats["clients"]}
        self.assertEqual(by_phone["9651"]["count"], 2)
        self.assertEqual(by_phone["9651"]["copies"], 1)
        self.assertEqual(by_phone["9651"]["sends"], 1)
        self.assertEqual(by_phone["9652"]["sends"], 1)

    def test_fetch_outreach_stats_reports_missing_table(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=False):
            stats = supabase_store.fetch_outreach_stats()
        self.assertFalse(stats["tableOk"])
        self.assertEqual(stats["clients"], [])
        self.assertEqual(stats["totals"]["total"], 0)
        self.assertEqual(stats["timeline"], [])
        self.assertEqual(stats["weekly"], [])

    @staticmethod
    def _week_start(d: str) -> str:
        from datetime import date as date_cls

        iso = date_cls.fromisoformat(d).isocalendar()
        return str(date_cls.fromisocalendar(iso[0], iso[1], 1))

    def test_fetch_outreach_stats_timeline_daily_and_weekly(self) -> None:
        from datetime import date as date_cls, timedelta
        from unittest import mock
        from backend.services import supabase_store

        today = date_cls.today()
        d1 = str(today - timedelta(days=3))
        d2 = str(today - timedelta(days=2))
        d3 = str(today - timedelta(days=9))
        rows = [
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "copy", "created_at": f"{d1}T10:00:00"},
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "send", "created_at": f"{d1}T11:00:00"},
            {"client_phone": "9652", "client_area": "المطلاع", "client_type": "شقة", "action": "send", "created_at": f"{d2}T09:00:00"},
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "copy", "created_at": f"{d3}T09:00:00"},
        ]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=rows):
            stats = supabase_store.fetch_outreach_stats()
        self.assertTrue(stats["tableOk"])
        # السلسلة اليومية مليئة 30 يومًا متصلة (بأصفار للأيام الخالية) لرسم متساوٍ
        self.assertEqual(len(stats["timeline"]), 30)
        by_date = {b["date"]: b for b in stats["timeline"]}
        self.assertEqual(by_date[d1]["copies"], 1)
        self.assertEqual(by_date[d1]["sends"], 1)
        self.assertEqual(by_date[d1]["total"], 2)
        self.assertEqual(by_date[d2]["total"], 1)
        self.assertEqual(by_date[d3]["total"], 1)
        empty_day = str(today - timedelta(days=1))
        self.assertEqual(by_date[empty_day]["total"], 0)
        # السلسلة الأسبوعية: 12 أسبوعًا متصلة، والتجميع بنفس بداية أسبوع ISO
        self.assertEqual(len(stats["weekly"]), 12)
        by_week = {b["week"]: b for b in stats["weekly"]}
        w1, w2, w3 = self._week_start(d1), self._week_start(d2), self._week_start(d3)
        # الأحداث: d1 نسخ+إرسال (2)، d2 إرسال (1)، d3 نسخ (1). التوقع يُحسب من
        # الأسابيع الفعلية لأي تاريخ (قبل اليوم: d3 قد يقع في نفس أسبوع d1)،
        # فلا يعتمد الاختبار على يوم التشغيل ولا يكسر عند حدود الأسبوع.
        expected_w1_total = 2 + (1 if w2 == w1 else 0) + (1 if w3 == w1 else 0)
        expected_w1_copies = 1 + (1 if w3 == w1 else 0)
        expected_w1_sends = 1 + (1 if w2 == w1 else 0)
        self.assertEqual(by_week[w1]["total"], expected_w1_total)
        self.assertEqual(by_week[w1]["copies"], expected_w1_copies)
        self.assertEqual(by_week[w1]["sends"], expected_w1_sends)
        expected_w3_total = 1 + (2 if w1 == w3 else 0) + (1 if w2 == w3 else 0)
        self.assertEqual(by_week[w3]["total"], expected_w3_total)

    def test_fetch_outreach_stats_computes_expected_response(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        rows = [
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "copy", "created_at": "2026-08-08T10:00:00"},
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "send", "created_at": "2026-08-08T11:00:00"},
            {"client_phone": "9651", "client_area": "النهضة", "client_type": "بيت", "action": "send", "created_at": "2026-08-08T12:00:00"},
            {"client_phone": "9652", "client_area": "المطلاع", "client_type": "شقة", "action": "send", "created_at": "2026-08-08T09:00:00"},
        ]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=rows):
            stats = supabase_store.fetch_outreach_stats()
        by_phone = {c["phone"]: c for c in stats["clients"]}
        # العميل 1: 3 نقرات (نسخ 1 + إرسال 2) → 6 + 2*9 + 1*4 = 28%، ونشط (3+ نقرات)
        self.assertEqual(by_phone["9651"]["expectedResponse"], 28)
        self.assertEqual(by_phone["9651"]["activityTier"], "متفاعل")
        # العميل 2: إرسال 1 → 6 + 9 = 15%
        self.assertEqual(by_phone["9652"]["expectedResponse"], 15)
        self.assertEqual(by_phone["9652"]["activityTier"], "جديد")
        self.assertIn("6% أساس", stats["responseMethod"])
        self.assertIn("بلا عشوائية", stats["responseMethod"])

    def test_fetch_outreach_stats_expected_response_capped_and_ranked(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        rows = [
            {"client_phone": f"965{1000 + i}", "client_area": "منطقة", "client_type": "بيت", "action": "send", "created_at": "2026-08-08T10:00:00"}
            for i in range(20)
        ]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=rows):
            stats = supabase_store.fetch_outreach_stats()
        # كل عميل بإرسال واحد → 15%، وسقف الحساب لا يُخالف (لا يوجد ما يصل إلى 85 هنا)
        self.assertEqual({c["expectedResponse"] for c in stats["clients"]}, {15})
        self.assertEqual(stats["clients"][0]["phone"], "9651000")
        # عميل واحد بنشاط هائل يُسقف عند 85%
        huge = [{"client_phone": "96599999999", "client_area": "النهضة", "client_type": "بيت", "action": "send", "created_at": "2026-08-08T10:00:00"} for _ in range(50)]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=huge):
            capped = supabase_store.fetch_outreach_stats()
        self.assertEqual(capped["clients"][0]["expectedResponse"], 85)
        self.assertEqual(capped["clients"][0]["activityTier"], "نشط جدًا")

    def test_fetch_outreach_stats_timeline_tolerates_bad_dates(self) -> None:
        from unittest import mock
        from backend.services import supabase_store

        rows = [
            {"client_phone": "9651", "action": "copy", "created_at": ""},
            {"client_phone": "9652", "action": "send", "created_at": "not-a-date"},
        ]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "outreach_table_available", return_value=True), \
             mock.patch.object(supabase_store, "_fetch_rows", return_value=rows):
            stats = supabase_store.fetch_outreach_stats()
        self.assertTrue(stats["tableOk"])
        # التواريخ السيئة لا تُسقط الإجمالي، لكنها لا تدخل السلسلة الزمنية
        self.assertEqual(stats["totals"]["total"], 2)
        self.assertEqual(len(stats["timeline"]), 30)
        self.assertEqual(sum(b["total"] for b in stats["timeline"]), 0)


if __name__ == "__main__":
    unittest.main()
