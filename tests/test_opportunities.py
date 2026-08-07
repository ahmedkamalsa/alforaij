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

    def test_rentals_are_excluded_from_tiers(self) -> None:
        """عروض الإيجار مستبعدة من الفرص حتى لا تُقارن إيجارات شهرية بوسيط شراء."""
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
            summary="شقة للإيجار",
            features="",
            published_date="2026-08-01",
            original_url="https://example.com/rent1",
            source="OpenSooq",
        )
        with mock.patch("backend.services.opportunities.search_external_sources", return_value=([rental], [{"name": "OpenSooq", "status": "success", "records": 1}])):
            snapshot = opportunities.build_opportunities(include_external=True)
        codes = [
            item["code"]
            for tier in snapshot["tiers"].values()
            for item in tier["items"]
        ]
        self.assertNotIn("RENT-1", codes)
        self.assertGreaterEqual(snapshot.get("skippedRentals", 0), 1)

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
        with mock.patch("backend.services.opportunities.search_external_sources", return_value=(external, [{"name": "OpenSooq", "status": "success", "records": 1}])):
            snapshot = opportunities.build_opportunities(include_external=True)
        # الفحص عبر كل الفئات (إعلان حديث قد يتفوق عليه محليون أعلى درجة في فئة معينة)
        codes = [
            item["code"]
            for tier in snapshot["tiers"].values()
            for item in tier["items"]
        ]
        self.assertIn("EXT-1", codes)

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


if __name__ == "__main__":
    unittest.main()
