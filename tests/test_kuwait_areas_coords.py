"""اختبارات ملف إحداثيات مناطق الكويت (static-data/kuwait-areas.json).

يغذي الخريطة التفاعلية فوق الخريطة الحرارية — التحقق يضمن:
- JSON صالح ومفاتيح فريدة بعد التطبيع (نفس قاعدة normalizeArabic في الواجهة)
- كل إحداثي داخل حدود الكويت (28.0–30.3 شمالًا، 46.0–48.6 شرقًا)
- كل منطقة مرتبطة بمحافظة معرّفة في قائمة المحافظات
- وجود مراكز المحافظات الست (سقوط آمن للمناطق غير المدرجة)
- **الضمانة الممتدة من test_area_governorate_map.py**: كل منطقة في ملف الإحداثيات
  مرتبطة بمحافظة معرّفة من خريطة المحافظات المعتمدة (AREA_TO_GOVERNORATE) —
  أي نقرة على الخريطة التفاعلية تقع في دلو محافظة يطابق اللوحة تمامًا،
  ولا تبقى أي منطقة من الملف «غير محددة» عند العرض، ولا يجوز أن يخالف
  حقل المحافظة في الملف إسناد الخريطة المعتمدة (محافظة واحدة فقط لكل منطقة).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# المصدر المرجعي في data/ (مُلتَزم) — تنسخه اللقطة الثابتة إلى static-data/ وقت النشر
COORDS_PATH = ROOT / "data" / "kuwait_areas.json"

from backend.main import _area_governorate_map, _normalize_dashboard_place, _normalize_governorate_name

# نفس قاعدة التطبيع في frontend/app.js normalizeArabic
def _norm(value: str) -> str:
    text = str(value or "")
    for src, dst in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(src, dst)
    text = re.sub(r"[^\u0621-\u064A\u0660-\u0669a-zA-Z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _load() -> dict:
    return json.loads(COORDS_PATH.read_text(encoding="utf-8"))


class KuwaitCoordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = _load()
        cls.areas = cls.data.get("areas") or {}
        cls.govs = cls.data.get("governorates") or {}

    def test_file_exists_and_valid_json(self) -> None:
        self.assertIn("areas", self.data)
        self.assertIn("governorates", self.data)

    def test_normalized_keys_unique(self) -> None:
        # مفاتيح فريدة ومستقرة التطبيع: البحث يتم عبر norm(اسم المنطقة) فلابد أن
        # يكون كل مفتاح بصيغته المطبعية النهائية (تشمل الأسماء المستعارة للمتغيرات)
        self.assertEqual(len(self.areas), len(set(self.areas)))
        for key in self.areas:
            self.assertTrue(key, "مفتاح فارغ")
            self.assertEqual(_norm(key), key, f"مفتاح {key!r} ليس مستقر التطبيع")

    def test_coordinates_within_kuwait_bounds(self) -> None:
        for key, entry in self.areas.items():
            self.assertGreaterEqual(entry["lat"], 28.0, key)
            self.assertLessEqual(entry["lat"], 30.3, key)
            self.assertGreaterEqual(entry["lng"], 46.0, key)
            self.assertLessEqual(entry["lng"], 48.6, key)

    def test_area_governorates_reference_defined(self) -> None:
        for key, entry in self.areas.items():
            self.assertIn(entry["governorate"], self.govs, f"{key} -> {entry['governorate']}")

    def test_all_six_governorates_have_centroids(self) -> None:
        for gov in ("محافظة العاصمة", "محافظة حولي", "محافظة الفروانية",
                    "محافظة الأحمدي", "محافظة الجهراء", "محافظة مبارك الكبير"):
            self.assertIn(gov, self.govs, gov)
            self.assertGreater(self.govs[gov]["lat"], 0, gov)

    def test_known_areas_covered(self) -> None:
        # مناطق شائعة يجب أن تكون مفهرسة (بالمفتاح المطبع)
        for name in ("السالمية", "الفروانية", "الرميثية", "الفحيحيل", "الجهراء", "مبارك الكبير"):
            self.assertIn(_norm(name), self.areas, name)

    # ── الضمانة الممتدة: كل منطقة في ملف الإحداثيات مرتبطة بمحافظة الخريطة المعتمدة ──
    def test_every_coords_area_resolves_to_governorate(self) -> None:
        """لا تبقى أي منطقة في ملف الإحداثيات «غير محددة» عند عرض اللوحة.

        تمرر كل منطقة عبر نفس المسار الذي تبنى به اللوحة دلاءها
        (_normalize_dashboard_place مع الخريطة المعتمدة فقط، بلا تعلم من البيانات)
        — فالنقر على الخريطة التفاعلية يقابل دائمًا دلو محافظة حقيقيًا.
        """
        area_map = _area_governorate_map([])
        unresolved = [
            key
            for key, entry in self.areas.items()
            if not self._resolve(entry, area_map)
        ]
        self.assertEqual(
            unresolved,
            [],
            "مناطق ملف الإحداثيات تبقى بلا محافظة في اللوحة (ستُجمَّع تحت «غير محددة»): "
            + "، ".join(unresolved),
        )

    def test_coords_governorate_agrees_with_authoritative_map(self) -> None:
        """حقل المحافظة في ملف الإحداثيات = إسناد الخريطة المعتمدة حرفيًا.

        نفس ضمانة «محافظة واحدة فقط لكل منطقة» ممتدة عبر الملفين: لو خالف
        الملفُ الخريطةَ (مثل «السلام» في الفروانية بينما الخريطة تحسمها حولي)،
        يتكسر الاختبار قبل أن تظهر النقطة على المحافظة الخطأ في الخريطة التفاعلية.
        """
        area_map = _area_governorate_map([])
        conflicts: list[str] = []
        for key, entry in self.areas.items():
            got = self._resolve(entry, area_map)
            want = _normalize_governorate_name(entry.get("governorate", ""))
            if got != want:
                conflicts.append(f"{key}: الملف→{want} والخريطة→{got}")
        self.assertEqual(
            conflicts,
            [],
            "مخالفات بين ملف الإحداثيات والخريطة المعتمدة (نقطة على محافظة خطأ في الخريطة التفاعلية): "
            + "؛ ".join(conflicts),
        )

    @staticmethod
    def _resolve(entry: dict, area_map: dict) -> str:
        record = {
            "area": entry.get("name") or "",
            "governorate": "",
            "summary": "",
            "features": "",
        }
        _normalize_dashboard_place(record, area_map)
        return str(record.get("governorate") or "")

    def test_new_residential_cities_sourced(self) -> None:
        # الأراضي السكنية الجديدة بمصادر رسمية موثقة (حقل source) — إحداثيات دقيقة
        # تمنع انحدار قيم التخمين القديمة الخاطئة (كانت تبعد 15-35 كم عن الواقع)
        expected = {
            "المطلاع": (29.49, 47.59),          # ويكيبيديا/PAHW — مدينة المطلاع السكنية
            "صباح الأحمد": (28.782, 48.064),      # OSM/Mapcarta + Wikimapia — المدينة السكنية
            "صباح الأحمد البحرية": (28.6447, 48.3419),  # GeoNames/GNS عبر Wikidata — الخيران
            "الوفرة": (28.55833, 48.04333),      # ويكيبيديا — أقصى جنوب الأحمدي
        }
        for name, (lat, lng) in expected.items():
            entry = self.areas.get(_norm(name))
            self.assertIsNotNone(entry, f"منطقة {name} غير مفهرسة")
            self.assertAlmostEqual(entry["lat"], lat, delta=0.01, msg=name)
            self.assertAlmostEqual(entry["lng"], lng, delta=0.01, msg=name)
            self.assertTrue(entry.get("source"), f"منطقة {name} بلا مصدر موثق")
        # جنوب المطلاع = المدينة السكنية نفسها (اسم شائع في الإعلانات)
        self.assertEqual(self.areas["جنوب المطلاع"]["lat"], 29.49)


if __name__ == "__main__":
    unittest.main()
