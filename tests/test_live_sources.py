from __future__ import annotations

import unittest

from backend.connectors.live_sources import first_area_meta, listing_from_text
from backend.services.request_parser import parse_request


class LiveSourceParsingTests(unittest.TestCase):
    def test_external_house_sale_small_price_is_treated_as_thousands(self) -> None:
        listing = listing_from_text(
            source="OpenSooq",
            code="OS-test",
            url="https://example.test",
            title="\u0644\u0644\u0628\u064a\u0639 \u0641\u064a\u0644\u0627 \u0641\u064a \u0627\u0644\u0645\u0637\u0644\u0627\u0639",
            description="\u0627\u0644\u0633\u0639\u0631 320",
            price=320,
            transaction="\u0644\u0644\u0628\u064a\u0639",
            fallback_type="\u0628\u064a\u062a",
        )

        self.assertEqual(listing.price, 320000)
        self.assertIn("\u0639\u0648\u0645\u0644 \u0643\u0623\u0644\u0641", listing.raw["priceSource"])

    def test_rental_implausible_price_is_excluded_from_valuation(self) -> None:
        """\u0625\u064a\u062c\u0627\u0631 \u0634\u0647\u0631\u064a \u0648\u0647\u0645\u064a (\u0645\u062b\u0644 \u00ab1\u00bb \u0623\u0648 \u00ab20\u00bb \u0643\u0639\u0646\u0627\u0635\u0631 \u0646\u0627\u0626\u0628\u0629) \u064a\u0633\u062a\u0628\u0639\u062f \u0645\u0646 \u0627\u0644\u062a\u0642\u064a\u064a\u0645 \u062d\u062a\u0649 \u0644\u0627 \u062a\u0638\u0647\u0631 \u0641\u0631\u0635\u0629 \u0648\u0647\u0645\u064a\u0629."""
        fake = listing_from_text(
            source="OpenSooq",
            code="OS-fake-price",
            url="https://example.test/1",
            title="\u0644\u0644\u0625\u064a\u062c\u0627\u0631 \u0645\u0643\u062a\u0628 \u0641\u064a \u062d\u0648\u0644\u064a",
            description="\u0645\u0643\u062a\u0628 \u062a\u062c\u0627\u0631\u064a",
            price=1.0,
            transaction="\u0644\u0644\u0625\u064a\u062c\u0627\u0631",
            fallback_type="\u062a\u062c\u0627\u0631\u064a",
        )
        self.assertIsNone(fake.price)
        self.assertIn("\u0644\u0645 \u064a\u062f\u062e\u0644 \u0641\u064a \u0627\u0644\u062a\u0642\u064a\u064a\u0645", fake.raw["priceSource"])
        self.assertTrue(fake.raw["dataWarnings"])

        # \u0625\u064a\u062c\u0627\u0631 \u0648\u0627\u0642\u0639\u064a (200 \u062f.\u0643) \u064a\u0628\u0642\u064a \u0643\u0645\u0627 \u0647\u0648
        real = listing_from_text(
            source="OpenSooq",
            code="OS-real-price",
            url="https://example.test/2",
            title="\u0645\u0643\u062a\u0628 \u0644\u0644\u0627\u064a\u062c\u0627\u0631 \u0628\u062d\u0648\u0644\u064a",
            description="\u0627\u0644\u0625\u064a\u062c\u0627\u0631 200 \u062f\u064a\u0646\u0627\u0631",
            price=None,
            transaction="\u0644\u0644\u0625\u064a\u062c\u0627\u0631",
            fallback_type="\u062a\u062c\u0627\u0631\u064a",
        )
        self.assertEqual(real.price, 200.0)

    def test_bnaid_al_qar_routes_to_real_source_slugs(self) -> None:
        request = parse_request(
            "\u0634\u0642\u0629 \u0644\u0644\u0628\u064a\u0639 \u0641\u064a "
            "\u0628\u0646\u064a\u062f \u0627\u0644\u0642\u0627\u0631"
        )

        self.assertEqual(first_area_meta(request)["q8aqar"], "bnaid-al-qar")
        self.assertEqual(first_area_meta(request)["sakan_city"], "bnaid-al-qar")

    def test_governorate_word_does_not_override_specific_area_slug(self) -> None:
        request = parse_request("للبيع بيت في صباح الناصر محافظة الفروانية المساحة 400م السعر 280 ألف")

        self.assertEqual(request.areas, ["صباح الناصر"])
        self.assertIn("الفروانية", request.governorates)
        self.assertEqual(first_area_meta(request)["q8aqar"], "sabah-al-naser")
        self.assertEqual(first_area_meta(request)["sakan_city"], "sabah-al-naser")

    # ------------------------------------------------------------------
    # توسيع Q8Aqar (قراءة صفحات التفاصيل) + Sakan المضمّن + منصات التوسعة
    # ------------------------------------------------------------------
    def test_detail_price_space_extracts_from_jsonld_and_meta(self) -> None:
        from backend.connectors.live_sources import _detail_price_space

        body = (
            '<meta property="product:price:amount" content="225,000">'
            '<meta property="product:property:size" content="300">'
            "<script type=\"application/ld+json\">"
            '{"@type": "RealEstateListing", "price": 220000, "floorSize": 290}'
            "</script>"
        )
        price, space = _detail_price_space(body)
        self.assertEqual(price, 225000)
        self.assertEqual(space, 300)

    def test_detail_price_space_falls_back_to_text(self) -> None:
        from backend.connectors.live_sources import _detail_price_space

        body = "<h1>بيت للبيع في خيطان السعر 220 الف مساحة 300 م</h1>"
        price, space = _detail_price_space(body)
        self.assertEqual(price, 220000)
        self.assertEqual(space, 300)

    def test_sakan_embedded_extraction(self) -> None:
        from backend.connectors.live_sources import _extract_sakan_embedded

        body = (
            "<script>window.__DATA__ = {"
            '"listings": [{"title": "House for sale in Khaitan", '
            '"url": "/en/detail/khaitan-house-1", "price": 220000, "area": 300}]'
            "};</script>"
        )
        items = _extract_sakan_embedded(body)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 220000)
        self.assertIn("/en/", items[0]["url"])

    def test_sakan_search_is_tolerant_and_keeps_availability(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        with mock.patch.object(live_sources, "fetch_url", return_value=("", 0, 1.0, "net down", 4)):
            listings, status = live_sources.search_sakan(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["attempts"], 4)

    def test_new_marketplaces_tolerate_failures(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        for searcher in (live_sources.search_aqarat, live_sources.search_four_sale):
            with mock.patch.object(live_sources, "fetch_url", return_value=("", 0, 1.0, "net down", 4)):
                listings, status = searcher(request)
            self.assertEqual(listings, [])
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["attempts"], 4)

    def test_four_sale_falls_back_to_opensooq_on_failure(self) -> None:
        """عند تعذر الوصول إلى 4Sale يُجرَّب المصدر البديل OpenSooq بنفس الشروط مع إفصاح شفاف."""
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        opensooq_body = (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props": {"pageProps": {"items": ['
            '{"id": 123, "title": "بيت للبيع في خيطان", '
            '"post_url": "/en/property/khaitan-house-123", "cat1_code": "RealEstate-1", '
            '"cat2_code": "House", "price_amount": 220000, '
            '"masked_description": "بيت للبيع في خيطان مساحة 300 م"}'
            "]}}}</script>"
        )

        def fake_fetch(url, extra_headers=None):
            if "4sale.com" in url:
                return ("", 0, 100.0, "getaddrinfo failed", 4)
            if "opensooq.com" in url:
                return (opensooq_body, 200, 150.0, None, 1)
            return ("", 0, 1.0, "unexpected url", 1)

        with mock.patch.object(live_sources, "fetch_url", side_effect=fake_fetch):
            listings, status = live_sources.search_four_sale(request)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source, "OpenSooq")
        self.assertEqual(listings[0].raw.get("fallbackFor"), "4Sale")
        self.assertEqual(status["status"], "fallback")
        self.assertEqual(status["records"], 1)
        self.assertEqual(status["attempts"], 4)  # محاولات 4Sale الفاشلة
        self.assertIn("getaddrinfo failed", status["note"])
        self.assertIn("OpenSooq", status["note"])

    def test_four_sale_fallback_failure_is_transparent(self) -> None:
        """عند فشل 4Sale والبديل معًا تُبقى الحالة failed مع سبب الموقعين."""
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        with mock.patch.object(live_sources, "fetch_url", return_value=("", 0, 1.0, "net down", 4)):
            listings, status = live_sources.search_four_sale(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "failed")
        self.assertIn("net down", status["note"])
        self.assertIn("OpenSooq", status["note"])
        self.assertEqual(status["attempts"], 4)

    def test_is_transient_error_classification(self) -> None:
        """الأخطاء العابرة (DNS/مهلة/قطع) تُصنف صحيحًا مقابل الأخطاء الحقيقية (403)."""
        import socket
        import urllib.error
        from backend.connectors import live_sources

        self.assertTrue(live_sources._is_transient_error(socket.gaierror(-2, "getaddrinfo failed")))
        self.assertTrue(live_sources._is_transient_error(TimeoutError("timed out")))
        self.assertTrue(live_sources._is_transient_error(ConnectionResetError("reset")))
        self.assertTrue(live_sources._is_transient_error(urllib.error.URLError(socket.gaierror(-2, "dns"))))
        self.assertFalse(live_sources._is_transient_error(
            urllib.error.HTTPError("url", 403, "Forbidden", None, None)
        ))
        self.assertFalse(live_sources._is_transient_error(ValueError("other")))

    def test_fetch_url_retries_transient_errors_until_success(self) -> None:
        """خطأ DNS عابر لا يوقف الجلب: تُعاد المحاولة وتنجح."""
        import socket
        import urllib.request
        from unittest import mock
        from backend.connectors import live_sources

        calls = {"n": 0}

        class FakeResponse:
            status = 200
            headers = {}

            def read(self):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout):
            calls["n"] += 1
            if calls["n"] < 3:
                raise socket.gaierror(-2, "getaddrinfo failed")
            return FakeResponse()

        url = "https://retry-transient.example.test/x"
        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            body, status_code, ms, error, attempts = live_sources.fetch_url(url)
        self.assertEqual(body, "ok")
        self.assertIsNone(error)
        self.assertEqual(calls["n"], 3)  # نجحت في المحاولة الثالثة العابرة
        self.assertEqual(attempts, 3)  # عدد المحاولات الفعلية يُسجَّل

    def test_fetch_url_limits_retries_for_http_errors(self) -> None:
        """الخطأ الحقيقي (403) لا يُعاد أكثر من الحد القياسي (محاولتان)."""
        import urllib.error
        import urllib.request
        from unittest import mock
        from backend.connectors import live_sources

        calls = {"n": 0}

        def fake_urlopen(request, timeout):
            calls["n"] += 1
            raise urllib.error.HTTPError("url", 403, "Forbidden", None, None)

        url = "https://http-error.example.test/x"
        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            body, status_code, ms, error, attempts = live_sources.fetch_url(url)
        self.assertEqual(body, "")
        self.assertIn("403", error or "")
        self.assertEqual(calls["n"], 2)  # محاولتان فقط للخطأ الحقيقي
        self.assertEqual(attempts, 2)

    def test_log_source_run_debounces_periodic_repeats(self) -> None:
        """الفحص الدوري لا يكرر نفس رسالة المصدر داخل النافذة، ويُسجل مرة بعدها مع عدّ المكرر."""
        import time as real_time
        from unittest import mock
        from backend.connectors import live_sources

        status = {
            "name": "4Sale",
            "status": "failed",
            "responseMs": 120.5,
            "attempts": 4,
            "records": 0,
            "note": "getaddrinfo failed",
        }
        live_sources._SOURCE_LOG_MEM.clear()  # بداية نظيفة حتى لا تتأثر باختبارات أخرى
        clock = {"now": 1000.0}
        with mock.patch.object(live_sources.time, "time", side_effect=lambda: clock["now"]):
            with self.assertLogs("backend.connectors.live_sources", level="INFO") as cm:
                live_sources.log_source_run(status)
                live_sources.log_source_run(status)
                live_sources.log_source_run(status)
            # داخل النافذة: سطر واحد فقط (الثاني والثالث مكرران لم يُسجلا)
            self.assertEqual(len(cm.records), 1)
            self.assertIn("getaddrinfo failed", cm.records[0].getMessage())
            self.assertIn("محاولات 4", cm.records[0].getMessage())  # عدد المحاولات الفعلية

            clock["now"] += 400  # انتهت نافذة 300 ثانية
            with self.assertLogs("backend.connectors.live_sources", level="INFO") as cm2:
                live_sources.log_source_run(status)
            self.assertEqual(len(cm2.records), 1)
            self.assertIn("كرر نفسه 2 مرة", cm2.records[0].getMessage())

    def test_broad_combo_requests_cover_types_and_transactions(self) -> None:
        """المسح المركّب يغطي بيت/شقة/أرض × بيع/إيجار (6 تركيبات) بدل طلب فارغ واحد."""
        from backend.connectors.live_sources import BROAD_COMBOS, broad_combo_requests

        requests = broad_combo_requests()
        self.assertEqual(len(requests), 6)
        self.assertEqual(len(BROAD_COMBOS), 6)
        pairs = {(r.property_type, r.transaction) for r in requests}
        self.assertEqual(pairs, {
            ("بيت", "للبيع"), ("شقة", "للبيع"), ("أرض", "للبيع"),
            ("بيت", "للإيجار"), ("شقة", "للإيجار"), ("أرض", "للإيجار"),
        })
        for r in requests:
            self.assertEqual(r.raw_text, "")

    def test_search_combo_sources_dedupes_and_aggregates(self) -> None:
        """الدمج عبر التركيبات يزيل التكرار بالكود ويعيد حالة مجمّعة واحدة لكل مصدر."""
        from unittest import mock
        from backend.connectors import live_sources
        from backend.models import Listing

        def make(code, source):
            return Listing(
                code=code, transaction="للبيع", governorate="", area="السالمية",
                property_type="بيت", detail_class="", price=250000,
                price_text="250,000 د.ك", space=400, listing_mode="",
                summary="بيت للبيع", features="", published_date="",
                original_url=f"https://example.test/{code}", source=source,
            )

        q8_house = make("Q8-1", "Q8Aqar")
        q8_land = make("Q8-2", "Q8Aqar")
        os_house = make("OS-1", "OpenSooq")

        def q8_fake(request):
            items = {"بيت": [q8_house], "شقة": [q8_land], "أرض": [q8_land]}
            return items.get(request.property_type, []), {
                "name": "Q8Aqar", "status": "success",
                "records": len(items.get(request.property_type, [])),
                "candidates": 5, "responseMs": 10, "note": "ok",
            }

        def os_fake(request):
            items = {"بيت": [os_house]}
            return items.get(request.property_type, []), {
                "name": "OpenSooq", "status": "success",
                "records": len(items.get(request.property_type, [])),
                "candidates": 3, "responseMs": 12, "note": "ok",
            }

        with mock.patch.object(live_sources, "SEARCHERS", [("Q8Aqar", q8_fake), ("OpenSooq", os_fake)]):
            listings, statuses = live_sources.search_combo_sources(
                live_sources.broad_combo_requests(), ["Q8Aqar", "OpenSooq"]
            )
        codes = [listing.code for listing in listings]
        self.assertIn("Q8-1", codes)
        self.assertIn("Q8-2", codes)
        self.assertIn("OS-1", codes)
        # نفس الكود ظهر في تركيبات متعددة (بيت بيع + بيت إيجار) → دُمج مرة واحدة
        self.assertEqual(codes.count("Q8-1"), 1)
        self.assertEqual(len(listings), 3)
        # حالة مجمّعة لكل مصدر بعدد النتائج الفريدة
        self.assertEqual(len(statuses), 2)
        by_name = {s["name"]: s for s in statuses}
        self.assertEqual(by_name["Q8Aqar"]["records"], 2)
        self.assertEqual(by_name["OpenSooq"]["records"], 1)
        self.assertEqual(by_name["Q8Aqar"]["status"], "success")
        self.assertIn("إعلانًا فريدًا", by_name["Q8Aqar"]["note"])

    def test_search_combo_sources_tolerates_combo_failures(self) -> None:
        """فشل تركيبة واحدة لا يكسر المسح: تُسجَّل الحالة وتستمر بقية التركيبات."""
        from unittest import mock
        from backend.connectors import live_sources
        from backend.models import Listing

        def make(code):
            return Listing(
                code=code, transaction="للبيع", governorate="", area="السالمية",
                property_type="بيت", detail_class="", price=250000,
                price_text="250,000 د.ك", space=400, listing_mode="",
                summary="بيت للبيع", features="", published_date="",
                original_url=f"https://example.test/{code}", source="Q8Aqar",
            )

        def fake_search(request):
            if request.transaction == "للإيجار":
                raise ConnectionError("net down")
            return [make("Q8-9")], {"name": "X", "status": "success", "records": 1, "candidates": 2, "responseMs": 5, "note": "وجدنا إعلانًا"}

        with mock.patch.object(live_sources, "SEARCHERS", [("Q8Aqar", fake_search)]):
            listings, statuses = live_sources.search_combo_sources(
                live_sources.broad_combo_requests(), ["Q8Aqar"]
            )
        # نتائج البيع الثلاث نجت، وفشل الإيجارات الثلاث سُجّل دون كسر المسح
        self.assertEqual([listing.code for listing in listings], ["Q8-9"])
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["status"], "success")
        self.assertEqual(statuses[0]["records"], 1)
        self.assertIn("3 نجحت", statuses[0]["note"])
        self.assertIn("3 فشلت", statuses[0]["note"])

    def test_official_transactions_searcher_is_wired(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        names = [name for name, _fn in live_sources.SEARCHERS]
        self.assertIn("الصفقات الرسمية", names)
        self.assertIn("Aqarat", names)
        self.assertIn("4Sale", names)
        request = parse_request("بيت للبيع في خيطان")
        with mock.patch("backend.connectors.official_data.load_transactions", return_value=[]):
            listings, status = live_sources.search_official_transactions(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "no_data")

    # ------------------------------------------------------------------
    # Yebtah — بيانات ItemList منظمة مع تعريب المنطقة/المحافظة
    # ------------------------------------------------------------------
    def _yebtah_body(self, *items: tuple[str, str]) -> str:
        elements = ",".join(
            '{"@type": "ListItem", "position": %d, "url": "https://yebtah.com/en/property/%s", "name": "%s"}'
            % (index + 1, code, name.replace('"', "'"))
            for index, (code, name) in enumerate(items)
        )
        return (
            '<script type="application/ld+json">'
            '{"@type": "ItemList", "itemListElement": [' + elements + "]}</script>"
        )

    def test_yebtah_parses_itemlist_and_arabizes_place(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        body = self._yebtah_body(
            ("abc123", "6-Bed Villa For Sale in Salmiya, Hawalli - 350,000 KWD"),
            ("def456", "3-Bed Apartment For Rent in Qurtuba, Al Asimah - 420 KWD"),
        )
        with mock.patch.object(live_sources, "fetch_url", return_value=(body, 200, 100.0, None, 1)):
            listings, status = live_sources.search_yebtah(parse_request(""))
        self.assertEqual(status["status"], "success")
        self.assertEqual(len(listings), 2)
        sale = next(item for item in listings if item.code == "YEB-abc123")
        self.assertEqual(sale.transaction, "للبيع")
        self.assertEqual(sale.property_type, "بيت")
        self.assertEqual(sale.area, "السالمية")
        self.assertEqual(sale.governorate, "محافظة حولي")
        self.assertEqual(sale.price, 350000)
        self.assertIn("yebtah.com/en/property/abc123", sale.original_url)
        rent = next(item for item in listings if item.code == "YEB-def456")
        self.assertEqual(rent.transaction, "للإيجار")
        self.assertEqual(rent.property_type, "شقة")
        self.assertEqual(rent.area, "قرطبة")
        self.assertEqual(rent.governorate, "محافظة العاصمة")
        self.assertEqual(rent.price, 420)

    def test_yebtah_broad_scan_keeps_both_sale_and_rent(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        sale_body = self._yebtah_body(("s1", "6-Bed Villa For Sale in Salmiya, Hawalli - 350,000 KWD"))
        rent_body = self._yebtah_body(("r1", "3-Bed Apartment For Rent in Qurtuba, Al Asimah - 420 KWD"))

        def fake_fetch(url, extra_headers=None):
            if "for_rent" in url:
                return (rent_body, 200, 50.0, None, 1)
            return (sale_body, 200, 50.0, None, 1)

        with mock.patch.object(live_sources, "fetch_url", side_effect=fake_fetch):
            listings, status = live_sources.search_yebtah(parse_request(""))
        transactions = {item.transaction for item in listings}
        self.assertEqual(transactions, {"للبيع", "للإيجار"})
        self.assertEqual(status["records"], 2)

    def test_yebtah_filters_rent_when_sale_requested(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        body = self._yebtah_body(
            ("r1", "3-Bed Apartment For Rent in Qurtuba, Al Asimah - 420 KWD"),
        )
        request = parse_request("شقة للبيع في قرطبة")
        with mock.patch.object(live_sources, "fetch_url", return_value=(body, 200, 50.0, None, 1)):
            listings, status = live_sources.search_yebtah(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "no_results")

    def test_yebtah_tolerates_network_failures(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        request = parse_request("بيت للبيع في خيطان")
        with mock.patch.object(live_sources, "fetch_url", return_value=("", 0, 1.0, "net down", 4)):
            listings, status = live_sources.search_yebtah(request)
        self.assertEqual(listings, [])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["attempts"], 4)

    def test_yebtah_is_wired_into_searchers_and_mechanisms(self) -> None:
        from backend.connectors import live_sources

        names = [name for name, _fn in live_sources.SEARCHERS]
        self.assertIn("Yebtah", names)
        mechanism = live_sources.source_mechanism("Yebtah")
        self.assertIn("ItemList", mechanism["method"])
        self.assertIn("yebtah.com", mechanism["endpoint"])

    def test_search_external_sources_can_run_one_selected_source(self) -> None:
        from unittest import mock
        from backend.connectors import live_sources

        def fake_a(request):
            return [], {"name": "A", "status": "success", "records": 0, "candidates": 0}

        def fake_b(request):
            return [], {"name": "B", "status": "success", "records": 0, "candidates": 0}

        with mock.patch.object(live_sources, "SEARCHERS", [("A", fake_a), ("B", fake_b)]):
            _listings, statuses = live_sources.search_external_sources(parse_request("بيت في المطلاع"), ["B"])

        self.assertEqual([status["name"] for status in statuses], ["B"])


if __name__ == "__main__":
    unittest.main()
