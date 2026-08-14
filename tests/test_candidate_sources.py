from __future__ import annotations

import unittest
from unittest import mock

from backend.connectors.live_sources import (
    _CANDIDATE_MEMO,
    search_aqarmap,
    search_bayut,
    search_propertyfinder,
)
from backend.services.official_source_agent import CANDIDATE_PLATFORMS
from backend.services.request_parser import parse_request


class CandidateConnectorTests(unittest.TestCase):
    """المنصات المرشحة تُبلغ حالتها الحقيقية بشفافية بدل ادعاء نجاح وهمي."""

    def setUp(self) -> None:
        _CANDIDATE_MEMO.clear()
        self.request = parse_request("شقة للبيع في السالمية")

    def test_propertyfinder_reports_blocked_on_timeout(self) -> None:
        """انقطاع الشبكة (مهلة) يعيد حالة blocked ويحفظها في سجل الحجب."""
        with mock.patch(
            "backend.connectors.live_sources.fetch_url",
            return_value=("", 0, 18000.0, "timed out", 4),
        ) as fetch:
            listings, status = search_propertyfinder(self.request)

        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "blocked")
        self.assertIn("غير متاح", status["note"])
        self.assertIn("timed out", status["note"])

    def test_block_memo_skips_second_attempt(self) -> None:
        """داخل نافذة الحجب لا يُعاد الجلب — الاستدعاء الثاني فوري (محاولة واحدة)."""
        with mock.patch(
            "backend.connectors.live_sources.fetch_url",
            return_value=("", 0, 18000.0, "timed out", 4),
        ) as fetch:
            search_propertyfinder(self.request)
            search_propertyfinder(self.request)

        self.assertEqual(fetch.call_count, 1)

    def test_aqarmap_reports_discontinued_on_egypt_portal(self) -> None:
        """عودة بوابة أخرى (مصر) تُصنَّف discontinued ولا تُلتقط بياناتها ككويتية."""
        egypt_body = (
            '<html><head><title>عقارماب مصر • ابحث عن عقارات للبيع وللإيجار</title></head>'
            "<body>بحث عقاري مصري</body></html>"
        )
        with mock.patch(
            "backend.connectors.live_sources.fetch_url",
            return_value=(egypt_body, 200, 1500.0, None, 1),
        ):
            listings, status = search_aqarmap(self.request)

        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "discontinued")
        self.assertIn("مصر", status["note"])

    def test_aqarmap_parses_kuwait_listings_when_available(self) -> None:
        """عند إعادة تفعيل النسخة الكويتية يستخرج الموصل إعلانات JSON-LD فعلية."""
        kuwait_body = (
            '<html><head><title>عقارماب الكويت</title></head><body>'
            '<script type="application/ld+json">'
            '{"@type":"Product","name":"شقة للبيع في السالمية 120م",'
            '"url":"https://aqarmap.com/kw/for-sale/kuwait/12345",'
            '"description":"شقة في السالمية مساحة 120 متر",'
            '"offers":{"price":"95000"}}'
            "</script></body></html>"
        )
        with mock.patch(
            "backend.connectors.live_sources.fetch_url",
            return_value=(kuwait_body, 200, 1500.0, None, 1),
        ):
            listings, status = search_aqarmap(self.request)

        self.assertEqual(status["status"], "success")
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source, "Aqarmap")
        self.assertEqual(listings[0].price, 95000.0)
        self.assertEqual(listings[0].area, "السالمية")

    def test_bayut_reports_blocked_on_captcha(self) -> None:
        """صفحة التحدي (captcha) تُسجَّل blocked ولا تُحتسب أي نتائج."""
        captcha_body = (
            "<html><body>"
            '<script src="https://hb.captcha.bayut.com/"></script>'
            "Please verify you are a human</body></html>"
        )
        with mock.patch(
            "backend.connectors.live_sources.fetch_url",
            return_value=(captcha_body, 200, 800.0, None, 1),
        ):
            listings, status = search_bayut(self.request)

        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "blocked")
        self.assertIn("captcha", status["note"])

    def test_candidate_platforms_are_probed_daily(self) -> None:
        """الفاحص اليومي يغطي المنصات الخمس بهويتها ودورها وحالتها القابلة للتمثيل JSON."""
        ids = {row["id"] for row in CANDIDATE_PLATFORMS}
        self.assertEqual(
            ids,
            {
                "propertyfinder_kw",
                "aqarmap_kw",
                "bayut_kw",
                "e_gov_kw_portal",
                "paci_kuwait_finder",
            },
        )
        for row in CANDIDATE_PLATFORMS:
            for field in ("id", "name", "url", "kind", "role"):
                self.assertTrue(row.get(field), f"{row.get('id')} missing {field}")

    def test_aqarmap_validator_detects_egypt_portal(self) -> None:
        """فاحص المحتوى اليومي يصنّف بوابة مصر على أنها discontinued لا reachable."""
        aqarmap = next(row for row in CANDIDATE_PLATFORMS if row["id"] == "aqarmap_kw")
        validate = aqarmap["validate"]
        result = validate("<title>عقارماب مصر</title>")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "discontinued")
        self.assertIsNone(validate("<title>عقارماب الكويت</title>"))


if __name__ == "__main__":
    unittest.main()
