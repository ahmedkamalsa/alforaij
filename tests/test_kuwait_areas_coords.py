"""اختبارات ملف إحداثيات مناطق الكويت (static-data/kuwait-areas.json).

يغذي الخريطة التفاعلية فوق الخريطة الحرارية — التحقق يضمن:
- JSON صالح ومفاتيح فريدة بعد التطبيع (نفس قاعدة normalizeArabic في الواجهة)
- كل إحداثي داخل حدود الكويت (28.0–30.3 شمالًا، 46.0–48.6 شرقًا)
- كل منطقة مرتبطة بمحافظة معرّفة في قائمة المحافظات
- وجود مراكز المحافظات الست (سقوط آمن للمناطق غير المدرجة)
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# المصدر المرجعي في data/ (مُلتَزم) — تنسخه اللقطة الثابتة إلى static-data/ وقت النشر
COORDS_PATH = ROOT / "data" / "kuwait_areas.json"

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


if __name__ == "__main__":
    unittest.main()
