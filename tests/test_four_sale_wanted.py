"""اختبارات مسّاح إعلانات «مطلوب» في 4Sale: `scan_four_sale_wanted` ومحلل الصفحة النقي.

4Sale هو المصدر الخارجي الوحيد المحصود الذي ينشر قسمًا مخصصًا لإعلانات الطلب
(«مطلوب عقار للبيع/للإيجار»). يغطي هذا الملف تصنيف المعاملة صراحةً حسب القسم،
استخراج الروابط والأكواد، وإزالة التكرار — بلا شبكة (قابل للتشغيل في CI).
"""
from __future__ import annotations

import unittest

from backend.connectors.live_sources import (
    _four_sale_wanted_from_page,
    _FOUR_SALE_WANTED_SECTIONS,
    scan_four_sale_wanted,
)

_SALE_PAGE = """
<html><body>
  <a href="/ar/listing/wanted-property-for-sale-21087248"><h2 class="t">مطلوب بيت في السالمية 400م</h2></a>
  <a href="/ar/listing/wanted-property-for-sale-21087208"><h2 class="t">مطلوب شقة في حولي</h2></a>
  <a href="/ar/listing/wanted-property-for-sale-21087194"><h2 class="t">مطلوب أرض في الفروانية</h2></a>
  <a href="/en/property/1">ليست إعلان طلب — رابط قسم</a>
  <a href="/ar/listing/wanted-property-for-sale-99999999">قصير</a>
</body></html>
"""

_RENT_PAGE = """
<html><body>
  <a href="/ar/listing/wanted-property-for-rent-21090000"><h2 class="t">مطلوب شقة للإيجار في السالمية</h2></a>
  <a href="/ar/listing/wanted-property-for-rent-21090001"><h2 class="t">مطلوب مخزن في الشويخ</h2></a>
</body></html>
"""


class FourSaleWantedParserTests(unittest.TestCase):
    def test_sale_section_forces_wanted_buy_transaction(self) -> None:
        """كل إعلانات قسم الطلب تُصنَّف «مطلوب للشراء» بغض النظر عن نص العنوان."""
        listings, candidates = _four_sale_wanted_from_page(_SALE_PAGE, "مطلوب للشراء", set(), 100)
        self.assertEqual(candidates, 4)  # 3 إعلانات + رابط قصير العنوان؛ رابط القسم ليس /ar/listing/
        self.assertEqual(len(listings), 3)  # الرابط قصير العنوان يُستبعد
        self.assertTrue(all(item.transaction == "مطلوب للشراء" for item in listings))
        codes = [item.code for item in listings]
        self.assertIn("4S-wanted-property-for-sale-21087248", codes)
        # الرابط يُكمل إلى مطلق على نطاق 4Sale
        self.assertTrue(all(item.original_url.startswith("https://www.q84sale.com/ar/listing/") for item in listings))

    def test_rent_section_forces_wanted_rent_transaction(self) -> None:
        listings, _ = _four_sale_wanted_from_page(_RENT_PAGE, "مطلوب للإيجار", set(), 100)
        self.assertEqual(len(listings), 2)
        self.assertTrue(all(item.transaction == "مطلوب للإيجار" for item in listings))
        # حتى العنوان الذي لا يذكر «إيجار» صراحةً (مخزن) يُصنَّف إيجارًا حسب القسم
        self.assertEqual(listings[1].transaction, "مطلوب للإيجار")

    def test_deduplicates_across_pages(self) -> None:
        seen: set[str] = set()
        first, _ = _four_sale_wanted_from_page(_SALE_PAGE, "مطلوب للشراء", seen, 100)
        second, _ = _four_sale_wanted_from_page(_SALE_PAGE, "مطلوب للشراء", seen, 100)
        self.assertEqual(len(first), 3)
        self.assertEqual(len(second), 0)  # نفس الأكواد — لا تكرار

    def test_max_total_caps_listings(self) -> None:
        listings, _ = _four_sale_wanted_from_page(_SALE_PAGE, "مطلوب للشراء", set(), 2)
        self.assertEqual(len(listings), 2)

    def test_sections_cover_buy_and_rent(self) -> None:
        labels = [transaction for _, transaction in _FOUR_SALE_WANTED_SECTIONS]
        self.assertIn("مطلوب للشراء", labels)
        self.assertIn("مطلوب للإيجار", labels)

    def test_scanner_importable(self) -> None:
        """الدالة العامة قابلة للاستدعاء من مسار الحصاد (لا تتحقق الشبكة هنا)."""
        self.assertTrue(callable(scan_four_sale_wanted))


if __name__ == "__main__":
    unittest.main()
