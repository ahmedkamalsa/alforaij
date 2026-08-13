from __future__ import annotations

import unittest


class TestOpportunities(unittest.TestCase):
    """اختبارات خدمة أفضل الفرص والتوقعات."""

    def _build(self):
        from backend.services.opportunities import build_opportunities

        # وضع محلي فقط (بدون اتصال حي بالمصادر الخارجية) للحفاظ على سرعة وحتمية الاختبار
        return build_opportunities(include_external=False)

    def test_build_opportunities_structure(self) -> None:
        snapshot = self._build()
        self.assertIn("tiers", snapshot)
        self.assertIn("forecast", snapshot)
        self.assertIn("generatedAt", snapshot)
        for key in ("daily", "weekly", "monthly", "yearly"):
            self.assertIn(key, snapshot["tiers"])
            tier = snapshot["tiers"][key]
            self.assertIn("items", tier)
            self.assertIn("label", tier)

    def test_opportunity_items_have_evidence_and_no_randomness(self) -> None:
        snapshot = self._build()
        items = snapshot["tiers"]["yearly"]["items"]
        if items:
            first = items[0]
            # كل فرصة تحمل مصدرًا وأدلة وثقة وسبب تقييم
            self.assertIn("source", first)
            self.assertIn("confidence", first)
            self.assertIn("score", first)
            self.assertIn("evidence", first)
            self.assertIn("valuationReason", first)
            self.assertIn("comparablesCount", first)

    def test_confidence_is_deterministic(self) -> None:
        a = self._build()
        b = self._build()
        self.assertEqual(a["tiers"]["yearly"], b["tiers"]["yearly"])
        self.assertEqual(a["forecast"], b["forecast"])

    def test_forecast_has_expected_fields(self) -> None:
        forecast = self._build()["forecast"]
        for item in forecast:
            self.assertIn("area", item)
            self.assertIn("direction", item)
            self.assertIn("expectedPricePerSqm", item)
            self.assertIn("sourceKind", item)

    def test_external_sources_merge_is_tolerant(self) -> None:
        """فشل المصادر الخارجية يجب ألا يكسر بناء الفرص (مسار متسامح مع الأخطاء)."""
        from unittest import mock
        from backend.services import opportunities

        with mock.patch("backend.services.opportunities.search_external_sources", side_effect=RuntimeError("net down")):
            snapshot = opportunities.build_opportunities(include_external=True)
        self.assertIn("tiers", snapshot)
        self.assertTrue(snapshot["includeExternal"])
        # مع فشل المصادر، تبقى البيانات المحلية أساس الفرص
        self.assertGreaterEqual(snapshot["totalScored"], 1)

    def test_rent_offers_enter_tiers_with_rental_line(self) -> None:
        """عروض الإيجار تدخل الفرص الآن بخط حسابها المميز (إيجار شهري/سنوي/عائد) دون خلط بوسيط البيع."""
        from unittest import mock
        from backend.models import Listing
        from backend.services import opportunities

        rental = Listing(
            code="RENT-1",
            transaction="للإيجار",
            governorate="حولي",
            area="السالمية",
            property_type="شقة",
            detail_class="",
            price=450,
            price_text="450 د.ك/شهر",
            space=80,
            listing_mode="",
            summary="شقة للإيجار في السالمية",
            features="",
            published_date="2026-08-01",
            original_url="https://example.com/rent1",
            source="OpenSooq",
        )
        with mock.patch("backend.services.opportunities.search_external_sources", return_value=([rental], [{"name": "OpenSooq", "status": "success", "records": 1}])), \
             mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), \
             mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), \
             mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
            snapshot = opportunities.build_opportunities(include_external=True)
        items = [
            item
            for tier in snapshot["tiers"].values()
            for item in tier["items"]
        ]
        found = next((item for item in items if item["code"] == "RENT-1"), None)
        self.assertIsNotNone(found, "عرض الإيجار يجب أن يدخل الفئات")
        self.assertTrue(found["rental"])
        # الخط الإيجاري: إيجار سنوي = شهري × 12، ولا يظهر كوسيط بيع بمئات الآلاف
        self.assertEqual(found["annualRent"], 5400)
        self.assertTrue(found["marketMedian"] is None or found["marketMedian"] < 1000)
        # لا يُربط العملاء (ميزانيات الشراء) بعروض الإيجار
        self.assertEqual(found.get("clients") or [], [])
        # العدادات الجديدة موجودة
        self.assertGreaterEqual(snapshot["rentalCount"], 1)

    def test_client_match_includes_potential_profit_kwd(self) -> None:
        from backend.services.opportunities import match_clients_for_listing

        clients = [{
            "area": "صباح الناصر",
            "type": "بيت",
            "price": "450000",
            "phones": "55559950",
            "source": "supabase",
        }]

        matched = match_clients_for_listing(clients, "صباح الناصر", "بيت", 280000)

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["clientBudget"], 450000)
        self.assertEqual(matched[0]["potentialProfitKwd"], 170000)
        self.assertIn("ميزانية العميل", matched[0]["profitReason"])
        self.assertEqual(matched[0]["source"], "supabase")

        other_area = dict(clients[0], area="النهضة")
        self.assertEqual(match_clients_for_listing([other_area], "صباح الناصر", "بيت", 280000), [])

    def test_demand_listing_becomes_client_with_source(self) -> None:
        from backend.models import Listing
        from backend.services.opportunities import clients_from_demand_listings

        demand = Listing(
            code="OS-D1",
            transaction="مطلوب للشراء",
            governorate="",
            area="صباح الناصر",
            property_type="بيت",
            detail_class="",
            price=350000,
            price_text="350,000 د.ك",
            space=400,
            listing_mode="",
            summary="مطلوب بيت في صباح الناصر للتواصل 55559950",
            features="",
            published_date="",
            original_url="https://example.test",
            source="OpenSooq",
        )

        clients = clients_from_demand_listings([demand])

        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["area"], "صباح الناصر")
        self.assertEqual(clients[0]["source"], "OpenSooq")
        self.assertIn("55559950", clients[0]["phones"])

    def test_demand_listings_are_excluded_from_tiers(self) -> None:
        """طلبات «مطلوب للشراء / مطلوب للإيجار» إشارات طلب وليست فرصًا للمستخدم — تُستبعد."""
        from unittest import mock
        from backend.models import Listing
        from backend.services import opportunities

        demand = Listing(
            code="WANT-1",
            transaction="مطلوب للإيجار",
            governorate="حولي",
            area="السالمية",
            property_type="شقة",
            detail_class="",
            price=450,
            price_text="450 د.ك/شهر",
            space=80,
            listing_mode="",
            summary="ابي شقة للإيجار",
            features="",
            published_date="2026-08-01",
            original_url="https://example.com/want1",
            source="OpenSooq",
        )
        with mock.patch("backend.services.opportunities.search_external_sources", return_value=([demand], [{"name": "OpenSooq", "status": "success", "records": 1}])), \
             mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), \
             mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), \
             mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
            snapshot = opportunities.build_opportunities(include_external=True)
        codes = [
            item["code"]
            for tier in snapshot["tiers"].values()
            for item in tier["items"]
        ]
        self.assertNotIn("WANT-1", codes)
        self.assertGreaterEqual(snapshot["skippedDemandCount"], 1)

    def test_external_listings_enter_tiers(self) -> None:
        """إعلان خارجي بسعر معلوم يجب أن يدخل في الفئات عند توفر المصادر."""
        from unittest import mock
        from backend.models import Listing
        from backend.services import opportunities

        external = [
            Listing(
                code="EXT-1",
                transaction="للبيع",
                governorate="حولي",
                area="السالمية",
                property_type="بيت",
                detail_class="",
                price=500000,
                price_text="500,000 د.ك",
                space=400,
                listing_mode="",
                summary="بيت للبيع في السالمية",
                features="",
                published_date="2026-08-01",
                original_url="https://example.com/ext1",
                source="OpenSooq",
            )
        ]
        with mock.patch("backend.services.opportunities.search_external_sources", return_value=(external, [{"name": "OpenSooq", "status": "success", "records": 1}])), \
             mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), \
             mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), \
             mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
            snapshot = opportunities.build_opportunities(include_external=True)
        # الفحص عبر كل الفئات (إعلان حديث قد يتفوق عليه محليون أعلى درجة في فئة معينة)
        codes = [
            item["code"]
            for tier in snapshot["tiers"].values()
            for item in tier["items"]
        ]
        self.assertIn("EXT-1", codes)

    def test_external_listing_without_date_enters_daily_tier(self) -> None:
        """الإعلان الخارجي الحي بلا تاريخ نشر يُعتبر حديثًا (يوم 0) فيدخل الفئة اليومية
        — بذلك تظهر كل منصات المواقع/التطبيقات في الصفحة الرئيسية وليس الفريج فقط."""
        from unittest import mock
        from backend.models import Listing
        from backend.services import opportunities

        external = Listing(
            code="EXT-LIVE",
            transaction="للبيع",
            governorate="حولي",
            area="السالمية",
            property_type="بيت",
            detail_class="",
            price=450000,
            price_text="450,000 د.ك",
            space=400,
            listing_mode="",
            summary="بيت للبيع في السالمية",
            features="",
            published_date="",  # المسح الحي لا يحمل تاريخ نشر
            original_url="https://example.com/ext-live",
            source="Mourjan",
        )
        with mock.patch(
            "backend.services.opportunities.search_external_sources",
            return_value=([external], [{"name": "Mourjan", "status": "success", "records": 1}]),
        ), mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
            snapshot = opportunities.build_opportunities(include_external=True)
        daily_items = snapshot["tiers"]["daily"]["items"]
        daily_codes = [item["code"] for item in daily_items]
        self.assertIn("EXT-LIVE", daily_codes)
        found = next(item for item in daily_items if item["code"] == "EXT-LIVE")
        self.assertEqual(found["daysAgo"], 0)
        self.assertEqual(found["source"], "Mourjan")

    def test_unreal_prices_are_excluded_from_opportunities(self) -> None:
        """الأسعار غير المنطقية (فشل استخراج من صفحة المصدر) لا تلوث أفضل الفرص — تُستبعد مع العدّ."""
        from unittest import mock
        from backend.models import Listing
        from backend.services import opportunities

        def make(code, price, transaction):
            return Listing(
                code=code, transaction=transaction, governorate="حولي", area="السالمية",
                property_type="شقة", detail_class="", price=price,
                price_text=f"{price} د.ك", space=80, listing_mode="",
                summary="شقة", features="", published_date="2026-08-01",
                original_url=f"https://example.com/{code}", source="OpenSooq",
            )

        external = [
            make("OS-BAD-RENT", 2.0, "للإيجار"),
            make("OS-BAD-SALE", 500.0, "للبيع"),
            make("OS-GOOD", 250000.0, "للبيع"),
        ]
        with mock.patch(
            "backend.services.opportunities.search_external_sources",
            return_value=(external, [{"name": "OpenSooq", "status": "success", "records": 3}]),
        ), mock.patch("backend.services.opportunities.search_combo_sources", return_value=([], [])), mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
            snapshot = opportunities.build_opportunities(include_external=True)
        codes = [item["code"] for tier in snapshot["tiers"].values() for item in tier["items"]]
        self.assertIn("OS-GOOD", codes)
        self.assertNotIn("OS-BAD-RENT", codes)
        self.assertNotIn("OS-BAD-SALE", codes)
        self.assertGreaterEqual(snapshot["skippedUnrealCount"], 2)

    def test_broad_combo_expansion_merges_dedupes_and_contributes(self) -> None:
        """المسح المركّب (Q8Aqar/OpenSooq) يُدمج إعلانات فريدة بلا تكرار، ويسهم في قائمة المصادر."""
        from unittest import mock
        from backend.models import Listing
        from backend.services import opportunities

        combo_rental = Listing(
            code="OS-777",
            transaction="للإيجار",
            governorate="حولي",
            area="السالمية",
            property_type="شقة",
            detail_class="",
            price=450,
            price_text="450 د.ك/شهر",
            space=80,
            listing_mode="",
            summary="شقة للإيجار في السالمية",
            features="",
            published_date="",  # حي بلا تاريخ → يوم 0 فيدخل اليومية
            original_url="https://example.com/os777",
            source="OpenSooq",
        )
        with mock.patch(
            "backend.services.opportunities.search_external_sources",
            return_value=([], [{"name": "Mourjan", "status": "success", "records": 0}]),
        ), mock.patch(
            "backend.services.opportunities.search_combo_sources",
            return_value=([combo_rental], [
                {"name": "Q8Aqar", "status": "success", "records": 0},
                {"name": "OpenSooq", "status": "success", "records": 1},
            ]),
        ), mock.patch("backend.services.opportunities.scan_opensooq_inventory", return_value=([], {"name": "OpenSooq (جرد كامل)", "status": "no_results", "records": 0})), mock.patch("backend.services.opportunities.enrich_listings_from_details", return_value={"enriched": 0, "read": 0, "status": "no_candidates", "note": "mocked"}):
            snapshot = opportunities.build_opportunities(include_external=True)
        daily_codes = [item["code"] for item in snapshot["tiers"]["daily"]["items"]]
        self.assertIn("OS-777", daily_codes, "إعلان المسح المركّب يجب أن يدخل الفئة اليومية")
        # المصادر المسهمة لا تتكرر رغم ورود حالة كل مصدر مرة لكل تركيب
        self.assertEqual(snapshot["contributingSources"].count("OpenSooq"), 1)
        self.assertIn("Q8Aqar", snapshot["contributingSources"])
        self.assertGreaterEqual(snapshot["rentalCount"], 1)

    # ------------------------------------------------------------------
    # تنبيهات واتساب + أرشفة الأداء + تطبيع الأرقام
    # ------------------------------------------------------------------
    def test_normalize_phone_handles_kuwaiti_and_egyptian(self) -> None:
        from backend.services.opportunities import normalize_phone

        # رقم كويتي محلي (8 أرقام)
        self.assertEqual(normalize_phone("55559950"), "96555559950")
        # رقم كويتي مكتمل بـ +965
        self.assertEqual(normalize_phone("+96555559950"), "96555559950")
        # رقم مصري محمول 01xxxxxxxxx → +20
        self.assertEqual(normalize_phone("01064955051"), "201064955051")
        # 00 بداية دولية
        self.assertEqual(normalize_phone("0096555559950"), "96555559950")
        # فارغ
        self.assertEqual(normalize_phone(""), "")

    def test_build_whatsapp_alerts_detects_new_and_price_drop(self) -> None:
        from backend.services.opportunities import build_whatsapp_alerts

        def item(code, price, area="النهضة", clients=None):
            return {
                "code": code,
                "area": area,
                "price": price,
                "priceText": f"{price:,.0f} د.ك",
                "valuationLabel": "عادل",
                "propertyType": "بيت",
                "url": f"https://example.com/{code}",
                "clients": clients or [{"area": "النهضة", "type": "بيت", "phones": "55559950|01064955051", "matchScore": 70}],
            }

        previous = {"generatedAt": "2026-08-01T10:00:00", "tiers": {"daily": {"items": [item("A", 500000), item("B", 450000)]}}}
        current = {"generatedAt": "2026-08-02T10:00:00", "tiers": {"daily": {"items": [item("A", 480000), item("C", 400000)]}}}
        result = build_whatsapp_alerts(previous, current)

        self.assertIn("alerts", result)
        self.assertGreaterEqual(result["count"], 1)
        kinds = {a["code"]: a["change"] for a in result["alerts"]}
        # A انخفض سعره، C فرصة جديدة
        self.assertEqual(kinds.get("A"), "price_drop")
        self.assertEqual(kinds.get("C"), "new")
        # كل تنبيه يحمل wa.me ورسالة جاهزة وأرقام مطابقة
        alert = result["alerts"][0]
        self.assertTrue(any(link.startswith("https://wa.me/") for link in alert["waLinks"]))
        self.assertTrue(alert["message"])
        self.assertIn("55559950", "|".join(alert["phones"]))

    def test_build_whatsapp_alerts_skips_unchanged(self) -> None:
        from backend.services.opportunities import build_whatsapp_alerts

        snapshot = {
            "generatedAt": "2026-08-01T10:00:00",
            "tiers": {"daily": {"items": [{"code": "X", "price": 100, "priceText": "100 د.ك", "clients": [{"phones": "55559950", "matchScore": 50}]}]}},
        }
        result = build_whatsapp_alerts(snapshot, snapshot)
        self.assertEqual(result["count"], 0)

    def test_build_history_series(self) -> None:
        from backend.services.opportunities import build_history_series

        snapshots = [
            {"generated_at": "2026-08-01T10:00:00", "forecast": [{"area": "النهضة", "expectedPricePerSqm": 1000.0}]},
            {"generated_at": "2026-08-02T10:00:00", "forecast": [{"area": "النهضة", "expectedPricePerSqm": 1100.0}]},
        ]
        result = build_history_series(snapshots)
        self.assertEqual(result["snapshotCount"], 2)
        self.assertEqual(len(result["dates"]), 2)
        self.assertGreaterEqual(len(result["series"]), 1)
        entry = next(e for e in result["series"] if e["area"] == "النهضة")
        self.assertEqual(entry["points"][0]["value"], 1000.0)
        self.assertEqual(entry["points"][-1]["value"], 1100.0)
        self.assertEqual(entry["direction"], "صاعد")

    def test_client_score_parses_comma_formatted_price(self) -> None:
        """أسعار Supabase المنسقة بفواصل (350,000) يجب ألا تكسر مطابقة السعر."""
        from backend.services.opportunities import _client_score

        score, reasons = _client_score(
            {"area": "النهضة", "type": "بيت", "price": "350,000"},
            "النهضة",
            "بيت",
            350000,
        )
        self.assertEqual(score, 100.0)
        self.assertIn("السعر ضمن نطاق العميل", reasons)

    def test_append_csv_client(self) -> None:
        """إضافة عميل محلي يكتب صفًا جديدًا ويُكمل مفتاحًا برقم الهاتف."""
        import tempfile
        from pathlib import Path
        from unittest import mock
        from backend.services import opportunities

        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "potential_leads.csv"
            fake_path.write_text("code,area,type,price,space,publishedDate,url,phones,message\r\n", encoding="utf-8")
            with mock.patch.object(opportunities, "CLIENTS_PATH", fake_path):
                result = opportunities.append_csv_client({"phone": "01064955051", "area": "النهضة", "note": "بحث عن بيت"})
                self.assertEqual(result["status"], "added")
                # التكرار يرفض (موجود مسبقًا)
                again = opportunities.append_csv_client({"phone": "01064955051"})
                self.assertEqual(again["status"], "exists")
                rows = opportunities._load_csv_clients()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["phones"], "01064955051")
    def test_unrealistic_prices_are_excluded_from_opportunities(self) -> None:
        """أسعار نائبة/وهمية (9,999 بيع، 70 إيجار) لا تدخل الفرص، والسعر الواقعي يبقى."""
        from backend.models import Listing
        from backend.services.opportunities import _score_listings

        def make(code: str, tx: str, price: float, source: str = "OpenSooq") -> Listing:
            return Listing(
                code=code,
                transaction=tx,
                governorate="",
                area="حولي",
                property_type="بيت",
                detail_class="",
                price=price,
                price_text=str(price),
                space=300,
                listing_mode="",
                summary="x",
                features="",
                published_date="",
                original_url="",
                source=source,
            )

        listings = [
            make("FAKE-SALE", "للبيع", 9999),
            make("FAKE-RENT", "للإيجار", 70),
            make("REAL-SALE", "للبيع", 41000, source="الفريج"),
        ]
        scored, _skipped_demand, skipped_unreal = _score_listings(listings, [])
        codes = [item["code"] for item in scored]
        self.assertNotIn("FAKE-SALE", codes)
        self.assertNotIn("FAKE-RENT", codes)
        self.assertIn("REAL-SALE", codes)
        self.assertGreaterEqual(skipped_unreal, 2)

    def test_budget_extracted_from_demand_text(self) -> None:
        """ميزانية طلب الشراء تُستخرج من النص (بحدود/حدود/ألف) وتُتجاهل أرقام الهواتف."""
        from backend.services.opportunities import _extract_budget_from_text

        self.assertEqual(_extract_budget_from_text("بيت حكومية حدود 300 الف"), 300000.0)
        self.assertEqual(_extract_budget_from_text("بحدود 180 الى 200 الف"), 190000.0)
        self.assertEqual(_extract_budget_from_text("ميزانية 250 الف دينار"), 250000.0)
        # رقم الهاتف ليس ميزانية
        self.assertIsNone(_extract_budget_from_text("مطلوب شراء بيت 📱 55559950 | 41060118"))
        # نص بلا ميزانية
        self.assertIsNone(_extract_budget_from_text("مطلوب بيت في المطلاع 3 ادوار"))

    def test_demand_listings_become_clients_with_phones(self) -> None:
        """إعلان طلب شراء (مطلوب + شراء + هاتف) يتحول لعميل برقم هاتف قابل للتواصل."""
        from backend.models import Listing
        from backend.services.opportunities import clients_from_demand_listings

        demand = Listing(
            code="AF-285",
            transaction="مطلوب للشراء",
            governorate="",
            area="صباح السالم",
            property_type="بيت",
            detail_class="",
            price=None,
            price_text="",
            space=None,
            listing_mode="",
            summary="مطلوب شراء بيت في صباح السالم بحدود 300 الف 📱 55559950",
            features="",
            published_date="",
            original_url="",
            source="الفريج",
        )
        clients = clients_from_demand_listings([demand])
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["area"], "صباح السالم")
        self.assertEqual(clients[0]["price"], "300,000")
        self.assertIn("55559950", clients[0]["phones"])

    def test_has_realistic_price_shared_filter(self) -> None:
        """الدالة المشتركة ترفض الأسعار الوهمية وتمرّر الرسمي/الطلبات/بلا سعر."""
        from backend.models import Listing
        from backend.services.opportunities import has_realistic_price, MIN_SALE_PRICE, MIN_RENT_PRICE

        def make(price, tx="للبيع", mode="") -> Listing:
            return Listing(
                code="X", transaction=tx, governorate="", area="", property_type="بيت",
                detail_class="", price=price, price_text="", space=None,
                listing_mode=mode, summary="", features="", published_date="",
                original_url="", source="test",
            )

        # أسعار وهمية من OpenSooq — مرفوضة
        self.assertFalse(has_realistic_price(make(9_999)))
        self.assertFalse(has_realistic_price(make(5_000)))
        self.assertFalse(has_realistic_price(make(17_000)))
        self.assertFalse(has_realistic_price(make(70, "للإيجار")))
        # حدود واقعية مقبولة
        self.assertTrue(has_realistic_price(make(MIN_SALE_PRICE)))
        self.assertTrue(has_realistic_price(make(MIN_RENT_PRICE, "للإيجار")))
        self.assertTrue(has_realistic_price(make(350_000)))
        # بلا سعر (طلبات شراء/إيجار) — يمرّ لخدمة العملاء
        self.assertTrue(has_realistic_price(make(None)))
        # المؤشرات الرسمية (سعر المتر المرجعي) — يمرّ للبحث والتقييم
        self.assertTrue(has_realistic_price(make(600, "", "رسمي")))
        # طلب «مطلوب» — يمرّ
        self.assertTrue(has_realistic_price(make(300_000, "مطلوب للشراء")))


if __name__ == "__main__":
    unittest.main()
