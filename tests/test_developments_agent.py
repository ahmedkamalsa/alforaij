"""اختبارات وكيل اكتشاف تطورات السوق العقاري الكويتي.

تغطي: تحليل RSS/Atom، استخراج روابط HTML، فلترة الكلمات العقارية، خصم التكرار،
حدود كل مصدر، الحفظ المحلي، والتسامح مع فشل المصادر (لا يكسر التشغيل).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services import developments_agent as dev


class DevelopmentsParsingTests(unittest.TestCase):
    def test_rss_entries_parses_items_with_dates(self) -> None:
        body = (
            '<?xml version="1.0"?><rss version="2.0"><channel>'
            "<item><title>ارتفاع أسعار العقار في الكويت</title>"
            "<link>https://example.com/realestate-1</link>"
            "<pubDate>Wed, 05 Aug 2026 10:00:00 GMT</pubDate>"
            "<description>سجلت الشقق ارتفاعًا في الإيجار.</description></item>"
            "<item><title>أخبار الرياضة</title>"
            "<link>https://example.com/sports-1</link></item>"
            "</channel></rss>"
        )
        entries = dev._rss_entries(body, {"id": "x", "name": "X"})
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["title"], "ارتفاع أسعار العقار في الكويت")
        self.assertEqual(entries[0]["url"], "https://example.com/realestate-1")
        self.assertIn("Wed", entries[0]["published"])

    def test_html_entries_extracts_only_relevant_links(self) -> None:
        body = (
            "<title>صفحة العقارات الرسمية</title>"
            '<a href="/reports/quarterly.html">التقرير الربعي لسوق العقار</a>'
            '<a href="/news/sports.html">أخبار الرياضة اليوم</a>'
            '<a href="/deals/123">صفقة بيع أرض مسجلة</a>'
        )
        entries = dev._html_entries(body, {"id": "x", "name": "X", "feed": "https://example.com/"})
        titles = [entry["title"] for entry in entries]
        self.assertIn("التقرير الربعي لسوق العقار", titles)
        self.assertIn("صفقة بيع أرض مسجلة", titles)
        self.assertNotIn("أخبار الرياضة اليوم", titles)
        for entry in entries:
            self.assertTrue(entry["url"].startswith("https://example.com/"))

    def test_relevance_keywords_arabic_and_english(self) -> None:
        self.assertTrue(dev._is_relevant("شقة للبيع في السالمية"))
        self.assertTrue(dev._is_relevant("real estate market report"))
        self.assertTrue(dev._is_relevant("KFH تمويل عقاري"))
        self.assertFalse(dev._is_relevant("أخبار الطقس اليوم"))
        self.assertFalse(dev._is_relevant("المنتخب يفوز في المباراة"))

    def test_english_terms_use_word_boundaries(self) -> None:
        # «land» لا تطابق داخل island / Thailand
        self.assertFalse(dev._is_relevant("Thailand shooting"))
        self.assertFalse(dev._is_relevant("Pacific islands alarmed"))
        self.assertTrue(dev._is_relevant("land for sale in Kuwait"))

    def test_kuwait_only_requires_kuwait_context_for_english(self) -> None:
        self.assertTrue(dev._is_relevant("housing market in Kuwait", kuwait_only=True))
        self.assertFalse(dev._is_relevant("French buyers rethink housing choices", kuwait_only=True))
        # العربية كافية (مصدر كويتي = سياق كويتي غالبًا)
        self.assertTrue(dev._is_relevant("ارتفاع أسعار الشقق", kuwait_only=True))

    def test_norm_url_dedupes_tracking_and_fragments(self) -> None:
        a = dev._norm_url("https://Example.com/path/?utm_source=1#frag")
        b = dev._norm_url("https://example.com/path")
        self.assertEqual(a, b)

    @patch("backend.services.developments_agent.fetch_url")
    def test_discovery_skips_duplicates_and_applies_caps(self, mock_fetch) -> None:
        def fake_fetch(url, extra_headers=None):
            # TimesKuwait: تغذية RSS حقيقية بثمانية عناصر (الحد لكل مصدر = 3)
            if "timeskuwait" in url:
                items = "".join(
                    f"<item><title>شقة للبيع في الكويت {i}</title>"
                    f"<link>https://timeskuwait.com/a/{i}</link></item>"
                    for i in range(8)
                )
                return f"<rss><channel>{items}</channel></rss>", 200, 10.0, None, 1
            # Kuwait Times: صفحة HTML بروابط — أحدها يكرر رابط TimesKuwait (يُخصم)
            if "kuwaittimes" in url:
                return (
                    "<html><title>Kuwait real estate</title>"
                    '<a href="https://kuwaittimes.com/p1">شقة للبيع في الكويت 1</a>'
                    '<a href="https://timeskuwait.com/a/1">شقة للبيع في الكويت 1</a>'
                    '<a href="https://kuwaittimes.com/p2">بيت للبيع في الكويت</a>'
                    "</html>",
                    200, 10.0, None, 1,
                )
            return "", 0, 0.0, "net down", 2

        mock_fetch.side_effect = fake_fetch
        result = dev.discover_market_developments(max_per_source=3, max_total=10, probe_portals=False)
        # Kuwait Times (HTML): 2 فريدين · TimesKuwait (RSS): 3 بحد المصدر — الإجمالي 5
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 5)
        urls = [item["url"] for item in result["developments"]]
        self.assertEqual(len(urls), len(set(urls)))
        statuses = {row["name"]: row["status"] for row in result["sources"]}
        self.assertEqual(statuses.get("Kuwait Times"), "success")
        self.assertEqual(statuses.get("TimesKuwait"), "success")
        self.assertTrue(any(row["status"] == "failed" for row in result["sources"]))

    def test_local_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(dev, "LOCAL_FILE", Path(tmp) / "market_developments.json"):
                payload = {
                    "status": "success",
                    "fetchedAt": "2026-08-11T10:00:00",
                    "count": 1,
                    "note": "جمع 1 تطورًا",
                    "developments": [{"url": "https://x.test/1", "title": "شقة للبيع", "source": "t", "source_name": "T", "category": "سوق عقاري", "published": "", "summary": ""}],
                    "sources": [{"name": "T", "status": "success"}],
                    "portals": [{"name": "P", "status": "متاحة"}],
                }
                saved = dev.save_developments_local(payload)
                self.assertEqual(saved["status"], "saved")
                loaded = dev.load_developments_local()
                self.assertEqual(loaded["count"], 1)
                self.assertEqual(loaded["developments"][0]["title"], "شقة للبيع")
                self.assertEqual(loaded["portals"][0]["status"], "متاحة")
                self.assertEqual(loaded["generatedAt"], "2026-08-11T10:00:00")

    def test_missing_local_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(dev, "LOCAL_FILE", Path(tmp) / "nope.json"):
                loaded = dev.load_developments_local()
                self.assertEqual(loaded["count"], 0)
                self.assertEqual(loaded["developments"], [])


if __name__ == "__main__":
    unittest.main()
