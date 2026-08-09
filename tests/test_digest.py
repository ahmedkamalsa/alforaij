from __future__ import annotations

import unittest


def _item(code: str, area: str, ptype: str, price: float, score: float, rental: bool = False) -> dict:
    return {
        "code": code,
        "area": area,
        "propertyType": ptype,
        "transaction": "للإيجار" if rental else "للبيع",
        "rental": rental,
        "price": price,
        "priceText": f"{price:,.0f} د.ك",
        "score": score,
        "valuationLabel": "لقطة ممتازة" if score > 80 else "عادلة",
        "evidence": [{"source": "Mourjan", "code": code, "price": price}],
        "url": f"https://example.com/{code}",
    }


_SNAPSHOT = {
    "tiers": {
        "daily": {"items": [
            _item("MJ-1", "النهضة", "بيت", 260000, 93),
            _item("MJ-2", "النهضة", "بيت", 300000, 85),
            _item("OS-3", "المطلاع", "بيت", 310000, 80),
            _item("R-1", "النهضة", "شقة", 450, 70, rental=True),
        ]},
        "yearly": {"items": [
            _item("MJ-4", "النهضة", "بيت", 350000, 75),
            _item("MJ-5", "حولي", "بيت", 420000, 88),
            _item("OS-6", "المطلاع", "بيت", 400000, 60),
        ]},
    }
}

_CLIENTS = [
    {"area": "النهضة", "type": "بيت", "price": "350,000", "phones": "55559950"},
    {"area": "المطلاع", "type": "بيت", "price": "400,000", "phones": "+96555551234"},
    {"area": "النهضة", "type": "شقة", "price": "200,000", "phones": ""},  # بلا هاتف → يُتجاهل
]


class TestWeeklyDigest(unittest.TestCase):
    """اختبارات الموجز الأسبوعي: أفضل 10 فرص لكل عميل محتمل مع رسالة واتساب جاهزة."""

    def _build(self, clients=None, snapshot=None):
        from unittest import mock
        from backend.services import opportunities

        with mock.patch("backend.services.opportunities._load_clients", return_value=clients if clients is not None else _CLIENTS):
            return opportunities.build_weekly_digest(snapshot if snapshot is not None else _SNAPSHOT)

    def test_digest_structure(self) -> None:
        digest = self._build()
        self.assertIn("generatedAt", digest)
        self.assertIn("note", digest)
        self.assertEqual(digest["count"], 2)  # عميلان فقط (الثالث بلا هاتف)
        for entry in digest["digests"]:
            self.assertIn("client", entry)
            self.assertIn("phones", entry)
            self.assertIn("message", entry)
            self.assertIn("opportunities", entry)
            self.assertGreaterEqual(entry["matchCount"], 1)

    def test_digest_excludes_rentals_and_prefers_area(self) -> None:
        digest = self._build()
        nahda = next(entry for entry in digest["digests"] if entry["client"]["area"] == "النهضة")
        codes = [item["code"] for item in nahda["opportunities"]]
        # الإيجار مستبعد دائمًا: ميزانية شراء لا تُقارن بإيجار شهري
        self.assertNotIn("R-1", codes)
        # فرص نفس المنطقة (درجة 100) تأتي أولًا بترتيب درجة الفرصة
        self.assertEqual(codes[:3], ["MJ-1", "MJ-2", "MJ-4"])
        # البيت خارج المنطقة (حولي/المطلاع) يبقى مطابقًا عبر النوع وتقارب السعر لكن بترتيب أدنى
        self.assertIn("MJ-5", codes)
        self.assertIn("OS-3", codes)

    def test_digest_sorts_by_match_then_score(self) -> None:
        digest = self._build()
        nahda = next(entry for entry in digest["digests"] if entry["client"]["area"] == "النهضة")
        codes = [item["code"] for item in nahda["opportunities"]]
        # أعلى درجة فرصة أولًا (MJ-1 = 93 ثم MJ-2 = 85 ثم MJ-4 = 75)، ثم خارج المنطقة بدرجة الفرصة
        self.assertEqual(codes[0], "MJ-1")
        self.assertEqual(codes[-1], "OS-6")

    def test_message_includes_client_context_and_evidence(self) -> None:
        digest = self._build()
        nahda = next(entry for entry in digest["digests"] if entry["client"]["area"] == "النهضة")
        self.assertIn("السلام عليكم", nahda["message"])
        self.assertIn("النهضة", nahda["message"])
        self.assertIn("بيت", nahda["message"])
        self.assertIn("MJ-1", nahda["message"])
        self.assertIn("ميزانية 350,000 د.ك", nahda["message"])
        self.assertIn("Mourjan", nahda["message"])  # مصدر الأدلة
        self.assertIn("https://example.com/MJ-1", nahda["message"])  # رابط الإعلان
        self.assertIn("[اسمك]", nahda["message"])

    def test_phones_normalized_in_wa_links(self) -> None:
        digest = self._build()
        nahda = next(entry for entry in digest["digests"] if entry["client"]["area"] == "النهضة")
        self.assertEqual(nahda["phones"], ["+96555559950"])
        muthala = next(entry for entry in digest["digests"] if entry["client"]["area"] == "المطلاع")
        self.assertEqual(muthala["phones"], ["+96555551234"])

    def test_top_n_limit(self) -> None:
        from unittest import mock
        from backend.services import opportunities

        # 12 فرصة في نفس المنطقة/النوع لعميل واحد
        snapshot = {"tiers": {"yearly": {"items": [
            _item(f"X-{i}", "النهضة", "بيت", 200000 + i, 50 + i) for i in range(12)
        ]}}}
        with mock.patch("backend.services.opportunities._load_clients", return_value=[_CLIENTS[0]]):
            digest = opportunities.build_weekly_digest(snapshot)
        self.assertEqual(digest["count"], 1)
        self.assertEqual(digest["digests"][0]["matchCount"], 10)

    def test_empty_snapshot_is_graceful(self) -> None:
        digest = self._build(snapshot={"tiers": {}})
        self.assertEqual(digest["count"], 0)
        self.assertEqual(digest["digests"], [])

    def test_no_clients_is_graceful(self) -> None:
        digest = self._build(clients=[])
        self.assertEqual(digest["count"], 0)


if __name__ == "__main__":
    unittest.main()
