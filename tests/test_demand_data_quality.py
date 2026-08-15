"""اختبارات جودة بيانات مؤشرات الطلب: تعبئة المحافظة، تصنيف صيغ الجمع، والتفريق بين المساحة والسعر.

ثلاثة عيوب حقيقية شُخّصت في حصاد «مطلوب» 4Sale:
1. صفوف الطلب الخارجي تُخزَّن بلا محافظة رغم معرفة منطقتها → تتكدس كلها تحت «غير محددة».
2. كاشف نوع العقار يطابق المفرد فقط → صيغ الجمع الشائعة (شقق/بيوت/فلل/عماير/قسائم/اراضي)
   تسقط كلها إلى «عقارات» العام.
3. «مطلوب عقار سكني للإيجار 200م 550 د.ك» كانت تلتقط المساحة 200 سعرًا بدل الميزانية 550.

بلا شبكة (قابل للتشغيل في CI).
"""
from __future__ import annotations

import unittest

from backend.connectors.live_sources import detect_property_type, parse_price
from backend.services.market_analysis import build_demand_indicators


def _demand_row(
    area: str,
    *,
    governorate: str = "",
    transaction: str = "مطلوب للشراء",
    source: str = "4Sale",
) -> dict:
    return {
        "area": area,
        "governorate": governorate,
        "transaction": transaction,
        "source": source,
        "fetched_at": "2026-08-15T00:00:00",
    }


class DemandGovernorateFillTests(unittest.TestCase):
    """تعبئة المحافظة من المنطقة عندما تكون الخانة المخزنة فارغة (صفوف 4Sale)."""

    def test_governorate_filled_from_known_area(self) -> None:
        rows = [_demand_row("المطلاع"), _demand_row("السالمية", transaction="مطلوب للإيجار")]
        out = build_demand_indicators(rows)
        govs = {g["governorate"]: g["total"] for g in out["governorates"]}
        self.assertEqual(govs.get("محافظة الجهراء"), 1)
        self.assertEqual(govs.get("محافظة حولي"), 1)
        self.assertNotIn("غير محددة", govs)
        # بُعد المناطق يحمل المحافظة المملوءة أيضًا
        by_area = {a["area"]: a["governorate"] for a in out["areas"]}
        self.assertEqual(by_area.get("المطلاع"), "محافظة الجهراء")
        self.assertEqual(by_area.get("السالمية"), "محافظة حولي")

    def test_stored_governorate_wins_over_map(self) -> None:
        rows = [_demand_row("السالمية", governorate="محافظة الفروانية")]
        out = build_demand_indicators(rows)
        govs = {g["governorate"]: g["total"] for g in out["governorates"]}
        self.assertEqual(govs.get("محافظة الفروانية"), 1)
        self.assertNotIn("محافظة حولي", govs)

    def test_unknown_area_stays_unset(self) -> None:
        rows = [_demand_row("منطقة غير معروفة تماما")]
        out = build_demand_indicators(rows)
        govs = [g["governorate"] for g in out["governorates"]]
        self.assertEqual(govs, ["غير محددة"])

    def test_count_unchanged_by_fill(self) -> None:
        """التعبئة لا تغيّر العد: مجموع المحافظات = مجموع المناطق = عدد الطلبات."""
        rows = [_demand_row("المطلاع"), _demand_row("السالمية", transaction="مطلوب للإيجار")]
        out = build_demand_indicators(rows)
        gov_total = sum(g["total"] for g in out["governorates"])
        area_total = sum(a["total"] for a in out["areas"])
        self.assertEqual(gov_total, out["totals"]["total"])
        self.assertEqual(area_total, out["totals"]["total"])


class PluralPropertyTypeTests(unittest.TestCase):
    """صيغ الجمع الشائعة في عناوين 4Sale تُصنَّف لنوع العقار الصحيح بدل «عقارات» العام."""

    def test_plural_forms_classified(self) -> None:
        cases = {
            "مطلوب شقق تمليك": "شقة",
            "مطلوب بيوت": "بيت",
            "مطلوب فلل": "بيت",
            "مطلوب عماير": "عمارة",
            "مطلوب عمائر للشركات": "عمارة",
            "مطلوب عمارات": "عمارة",
            "مطلوب قسائم": "أرض",
            "مطلوب قسايم": "أرض",
            "مطلوب اراضي": "أرض",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(detect_property_type(text), expected)

    def test_singular_forms_unchanged(self) -> None:
        cases = {
            "مطلوب شقه": "شقة",
            "مطلوب بيت": "بيت",
            "مطلوب فيلا": "بيت",
            "مطلوب عماره": "عمارة",
            "مطلوب ارض": "أرض",
            "مطلوب قسيمه": "أرض",
            "مطلوب دوبلكس": "شقة",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(detect_property_type(text), expected)

    def test_unknown_falls_back(self) -> None:
        self.assertEqual(detect_property_type("مطلوب مخزن"), "عقارات")


class PriceVsAreaTests(unittest.TestCase):
    """المساحة لا تُلتقط سعرًا، وأسعار 4Sale الوهمية «1 د.ك» تبقى مرفوضة."""

    def test_area_not_captured_as_price(self) -> None:
        # المشكلة الأصلية: «200م» كانت تُلتقط سعرًا بدل الميزانية 550
        self.assertEqual(parse_price("مطلوب عقار سكني للإيجار 200م 550 د.ك"), 550)

    def test_area_only_no_price(self) -> None:
        self.assertIsNone(parse_price("مطلوب ارض 400م"))
        self.assertIsNone(parse_price("مطلوب شقه للايجار 200م"))

    def test_filler_price_rejected(self) -> None:
        # الأسعار الوهمية «1 د.ك» التي تملأ عناوين 4Sale تبقى مرفوضة بالحارس value > 100
        self.assertIsNone(parse_price("مطلوب شقه للايجار 1 د.ك"))

    def test_keyword_price_still_works(self) -> None:
        self.assertEqual(parse_price("مطلوب شقه للايجار 300 د.ك"), 300)
        self.assertEqual(parse_price("مطلوب فيلا للبيع 150 الف د.ك"), 150000)

    def test_bare_currency_captured(self) -> None:
        # «X د.ك» دون كلمة مفتاح تُلتقط الآن (كانت None سابقًا)
        self.assertEqual(parse_price("شقه للبيع 120,000 د.ك"), 120000)


if __name__ == "__main__":
    unittest.main()
