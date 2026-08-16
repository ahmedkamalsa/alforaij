"""اختبارات كسح شبه التكرار بحذر (جودة البيانات).

التغطية: تطبيع العنوان، توقيع التطابق، بوابات الدقة (هاتف/مساحة/طول عنوان)،
اختيار النظير، وقرارات الوسم. بلا شبكة — دوال نقية + محاكاة للـ REST.
"""
from __future__ import annotations

import unittest
from unittest import mock

from backend.services import listing_dedupe as dd
from backend.services import supabase_store


def _row(
    code: str,
    *,
    source: str = "4Sale",
    area: str = "السالمية",
    property_type: str = "بيت",
    price: float = 280000,
    summary: str = "بيت للبيع في السالمية قطعة 4 دورين مع حديقة",
    phone: str = "96551112233",
    space: float | None = 400,
    created_at: str = "2026-08-10T00:00:00+00:00",
) -> dict:
    return {
        "code": code,
        "source": source,
        "area": area,
        "property_type": property_type,
        "price": price,
        "summary": summary,
        "features": summary,
        "phone": phone,
        "space": space,
        "created_at": created_at,
    }


class NormalizeTests(unittest.TestCase):
    def test_arabic_variants_unified(self) -> None:
        self.assertEqual(dd.normalize_arabic("السالميه"), dd.normalize_arabic("السالمية"))
        self.assertEqual(dd.normalize_arabic("ابو حليفة"), dd.normalize_arabic("أبو حليفة"))
        self.assertEqual(dd.normalize_arabic("  بيت   للبيع،  "), "بيت للبيع")

    def test_title_lead_ignores_english_tail(self) -> None:
        # ذيل العلامات الإنجليزية قد يتغير بين الجلب — الجملة الأولى هي الثابت
        a = "بيت للبيع في السالمية قطعة 4 دورين. Abu Salmiya Salmiya Al Ahmadi"
        b = "بيت للبيع في السالمية قطعة 4 دورين."
        self.assertEqual(dd._title_lead(a), dd._title_lead(b))


class SignatureTests(unittest.TestCase):
    def test_same_ad_different_code_same_signature(self) -> None:
        a = _row("A-1", created_at="2026-08-10T00:00:00+00:00")
        b = _row("B-2", created_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(dd.signature(a), dd.signature(b))

    def test_different_price_breaks_signature(self) -> None:
        a = _row("A-1", price=280000)
        b = _row("B-2", price=275000)
        self.assertNotEqual(dd.signature(a), dd.signature(b))

    def test_different_source_breaks_signature(self) -> None:
        a = _row("A-1", source="4Sale")
        b = _row("B-2", source="OpenSooq")
        self.assertNotEqual(dd.signature(a), dd.signature(b))

    def test_float_price_equals_int(self) -> None:
        self.assertEqual(dd.price_key(280000), dd.price_key(280000.0))


class GateTests(unittest.TestCase):
    def test_matching_group_passes(self) -> None:
        group = [_row("A-1", created_at="2026-08-10T00:00:00+00:00"), _row("B-2")]
        self.assertTrue(dd.is_duplicate_group(group))

    def test_different_phones_block_merge(self) -> None:
        # معلنان مختلفان بنفس النص والسعر — وحدتان شرعيتان (وسطاء) لا تُدمجان
        group = [_row("A-1", phone="96551112233"), _row("B-2", phone="96554445566")]
        self.assertFalse(dd.is_duplicate_group(group))

    def test_missing_phone_on_one_allows_merge(self) -> None:
        group = [_row("A-1", phone="96551112233"), _row("B-2", phone="")]
        self.assertTrue(dd.is_duplicate_group(group))

    def test_different_spaces_block_merge(self) -> None:
        group = [_row("A-1", space=400), _row("B-2", space=450)]
        self.assertFalse(dd.is_duplicate_group(group))

    def test_missing_space_allows_merge(self) -> None:
        group = [_row("A-1", space=400), _row("B-2", space=None)]
        self.assertTrue(dd.is_duplicate_group(group))

    def test_no_phone_no_space_blocked(self) -> None:
        # نص متطابق بلا هاتف وبلا مساحة — لا إثبات مستقل (قوالب المنصات مثل
        # «بيت 8 غرفة للإيجار في عبدلي» تعرض وحدات متطابقة شرعيًا) → لا دمج
        group = [
            _row("A-1", phone="", space=None, summary="بيت، 8 غرفة، للإيجار، في عبدلي، محافظة الجهراء — 80 د.ك"),
            _row("B-2", phone="", space=None, summary="بيت، 8 غرفة، للإيجار، في عبدلي، محافظة الجهراء — 80 د.ك"),
        ]
        self.assertFalse(dd.is_duplicate_group(group))

    def test_short_generic_title_blocked(self) -> None:
        # «بيت للبيع» بلا تفاصيل — عام جدًا ولا يُدمج
        group = [
            _row("A-1", summary="بيت للبيع"),
            _row("B-2", summary="بيت للبيع"),
        ]
        self.assertFalse(dd.is_duplicate_group(group))

    def test_official_rows_excluded_from_groups(self) -> None:
        # صفقتان رسميتان بنفس السعر/المساحة صفقتان حقيقيتان — لا تُدمجان أبدًا
        a = _row("OFF-ALHISBA-1-صباح الأحمد البحرية-540.0-255000.0", source="الحسبة - الصفقات المسجلة العامة",
                 area="صباح الأحمد البحرية", property_type="أرض", price=255000, space=540,
                 summary="صفقة رسمية مسجلة في صباح الأحمد البحرية (أرض)")
        b = _row("OFF-ALHISBA-2-صباح الأحمد البحرية-540.0-255000.0", source="الحسبة - الصفقات المسجلة العامة",
                 area="صباح الأحمد البحرية", property_type="أرض", price=255000, space=540,
                 summary="صفقة رسمية مسجلة في صباح الأحمد البحرية (أرض)")
        self.assertEqual(dd.build_dedupe_groups([a, b]), [])


class GroupBuildTests(unittest.TestCase):
    def test_groups_one_duplicate_pair_and_distinct(self) -> None:
        rows = [
            _row("A-1", created_at="2026-08-10T00:00:00+00:00"),
            _row("B-2"),  # نفس الإعلان برمز مختلف
            _row("C-3", area="النهضة"),  # منطقة مختلفة — إعلان مستقل
        ]
        groups = dd.build_dedupe_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)

    def test_canonical_is_earliest_created(self) -> None:
        group = [_row("B-2", created_at="2026-08-12T00:00:00+00:00"), _row("A-1", created_at="2026-08-10T00:00:00+00:00")]
        canonical = dd.group_canonical(group)
        self.assertEqual(canonical["code"], "A-1")

    def test_duplicate_marks_point_to_canonical(self) -> None:
        rows = [_row("A-1", created_at="2026-08-10T00:00:00+00:00"), _row("B-2")]
        marks = dd.duplicate_marks(dd.build_dedupe_groups(rows))
        self.assertEqual(marks, [{"code": "B-2", "duplicate_of": "A-1"}])


class StoreDedupeTests(unittest.TestCase):
    def test_dedupe_marks_and_counts(self) -> None:
        rows = [
            _row("A-1", created_at="2026-08-10T00:00:00+00:00"),
            _row("B-2"),
            _row("C-3", area="النهضة"),
        ]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "fetch_market_listings", return_value=rows), \
             mock.patch.object(supabase_store, "_patch") as patch:
            result = supabase_store.dedupe_market_listings()
        self.assertEqual(result["status"], "deduped")
        self.assertEqual(result["groups"], 1)
        self.assertEqual(result["marked"], 1)
        filters, payload = patch.call_args.args[1], patch.call_args.args[2]
        self.assertEqual(filters, {"code": "eq.B-2"})
        self.assertEqual(payload, {"status": "duplicate", "duplicate_of": "A-1"})

    def test_dedupe_not_configured(self) -> None:
        with mock.patch.object(supabase_store, "is_configured", return_value=False), \
             mock.patch.object(supabase_store, "_patch") as patch:
            result = supabase_store.dedupe_market_listings()
        self.assertEqual(result["status"], "not_configured")
        patch.assert_not_called()

    def test_dedupe_failure_contained(self) -> None:
        rows = [_row("A-1", created_at="2026-08-10T00:00:00+00:00"), _row("B-2")]
        with mock.patch.object(supabase_store, "is_configured", return_value=True), \
             mock.patch.object(supabase_store, "fetch_market_listings", return_value=rows), \
             mock.patch.object(supabase_store, "_patch", side_effect=RuntimeError("HTTP 500")):
            result = supabase_store.dedupe_market_listings()
        self.assertEqual(result["status"], "failed")
        self.assertIn("500", result["error"])


if __name__ == "__main__":
    unittest.main()
