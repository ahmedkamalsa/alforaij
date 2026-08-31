"""اختبارات خريطة «منطقة ← محافظة» (AREA_TO_GOVERNORATE) في اللوحة.

الضمانتان اللتان يفرضهما هذا الملف:
1. **محافظة واحدة فقط لكل منطقة** — بعد تطبيع الأسماء (همزات/تاء مربوطة/مسافات/إنجليزي)،
   لا يجوز أن تُسند المنطقة نفسها لمحافظتين مختلفتين (خيطان في الفروانية فقط،
   صباح الأحمد في الأحمدي فقط...). أي كتابتين لنفس المنطقة (عربي بلا مسافات أو
   إنجليزي) يجب أن تؤديان لنفس المحافظة.
2. **لا تبقى منطقة معروفة «غير محددة»** — كل منطقة في قوائم المعرفة (KNOWN_AREAS
   وأسماء AREA_ALIASES) يجب أن تُحل إلى محافظة في اللوحة عبر `_normalize_dashboard_place`
   حتى بدون تعلم من البيانات المحلية — فلو ظهرت منطقة جديدة في نص إعلان ولم تُسند،
   يتكسر الاختبار قبل أن تتكدس تحت «غير محددة».
"""
from __future__ import annotations

import re
import unittest

from backend.main import _area_governorate_map, _normalize_dashboard_place, _normalize_governorate_name
from backend.services.request_parser import (
    AREA_ALIASES,
    AREA_TO_GOVERNORATE,
    GOVERNORATE_AREA_NAMES,
    KNOWN_AREAS,
)

# تطبيع عربي: همزات/تاء مربوطة/ألف — نفس قاعدة التطبيع في المحرك والواجهة
_ARABIC = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})

# المحافظات الست الكنسونية كما تُطبع في اللوحة
CANONICAL_GOVERNORATES = {
    "محافظة العاصمة",
    "محافظة حولي",
    "محافظة الفروانية",
    "محافظة الأحمدي",
    "محافظة الجهراء",
    "محافظة مبارك الكبير",
}


def _norm_area(value: str) -> str:
    """تطبيع اسم منطقة للاختبار: عربي بلا مسافات/شرطات بعد توحيد الهمزات،
    إنجليزي بأحرف صغيرة بلا علامات — حتى تُقارن «عبد الله» و«عبدالله»
    و«Salmiya» و«salmiya» كمفتاح واحد (أصرّ من مفتاح اللوحة)."""
    text = str(value or "").strip()
    if re.match(r"^[A-Za-z]", text):
        return re.sub(r"[^a-z0-9]", "", text.lower())
    return re.sub(r"[\s\-_]", "", text.translate(_ARABIC))


def _norm_gov(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("محافظة "):
        text = text[len("محافظة "):]
    return re.sub(r"[\s\-_]", "", text.translate(_ARABIC))


# أسماء المحافظات الست كمناطق (حولي، الجهراء...) — تعاملها اللوحة كمنطقة=محافظة
# عبر _GOVERNORATE_ALIASES وليست بحاجة لخريطة منطقة←محافظة
_GOV_NAMES_AS_AREA = {_norm_area(name) for name in GOVERNORATE_AREA_NAMES}


class AreaGovernorateMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # المنطقة الطبيعية ← مجموعة المحافظات المسندة إليها في الخريطة
        cls.by_area: dict[str, set[str]] = {}
        for area, gov in AREA_TO_GOVERNORATE.items():
            cls.by_area.setdefault(_norm_area(area), set()).add(_norm_gov(gov))
        # كل المناطق المعروفة: القائمة الثابتة + المدمجة من البيانات المحلية + أسماء المرادفات
        cls.known_areas = list(dict.fromkeys([*KNOWN_AREAS, *AREA_ALIASES.keys()]))

    # ── الضمانة 1: محافظة واحدة فقط لكل منطقة ────────────────────────────────
    def test_every_area_in_exactly_one_governorate(self) -> None:
        conflicts = {area: govs for area, govs in self.by_area.items() if len(govs) > 1}
        self.assertEqual(
            conflicts,
            {},
            "مناطق تُسند لمحافظتين مختلفتين بكتابات متعددة — الخريطة يجب أن تكون حاسمة: "
            + ", ".join(f"{area} → {sorted(govs)}" for area, govs in sorted(conflicts.items())),
        )

    def test_every_governorate_value_is_one_of_the_six(self) -> None:
        bad = {
            gov
            for gov in set(AREA_TO_GOVERNORATE.values())
            if _normalize_governorate_name(gov) not in CANONICAL_GOVERNORATES
        }
        self.assertEqual(
            bad,
            set(),
            "قيم محافظات غير معروفة في الخريطة (ستُطبع كما هي في اللوحة): "
            + ", ".join(sorted(bad)),
        )

    # ── الضمانة 2: لا تبقى منطقة معروفة «غير محددة» ──────────────────────────
    def test_every_known_area_is_covered_by_the_map(self) -> None:
        missing = [
            area
            for area in self.known_areas
            if _norm_area(area) not in self.by_area and _norm_area(area) not in _GOV_NAMES_AS_AREA
        ]
        self.assertEqual(
            missing,
            [],
            "مناطق معروفة بلا إسناد محافظة في AREA_TO_GOVERNORATE — ستتكدس تحت «غير محددة» في اللوحة: "
            + "، ".join(missing),
        )

    def test_no_known_area_stays_undetermined_in_dashboard(self) -> None:
        # بدون تعلم من البيانات المحلية (قائمة فارغة) — الخريطة المعتمدة وحدها يجب أن تكفي
        area_map = _area_governorate_map([])
        unresolved: list[str] = []
        for area in self.known_areas:
            record = {"area": area, "governorate": "", "summary": "", "features": ""}
            _normalize_dashboard_place(record, area_map)
            if not record.get("governorate"):
                unresolved.append(area)
        self.assertEqual(
            unresolved,
            [],
            "مناطق معروفة تبقى بلا محافظة في اللوحة حتى بعد تطبيع اللوحة: " + "، ".join(unresolved),
        )

    def test_every_map_key_resolves_in_dashboard(self) -> None:
        # كل مفتاح في الخريطة نفسها (عربيًا وإنجليزيًا) يجب أن يُحل عند العرض
        area_map = _area_governorate_map([])
        unresolved: list[str] = []
        for area in AREA_TO_GOVERNORATE:
            record = {"area": area, "governorate": "", "summary": "", "features": ""}
            _normalize_dashboard_place(record, area_map)
            if not record.get("governorate"):
                unresolved.append(area)
        self.assertEqual(
            unresolved,
            [],
            "مفاتيح AREA_TO_GOVERNORATE نفسها لا تُحل إلى محافظة في اللوحة: " + "، ".join(unresolved),
        )


if __name__ == "__main__":
    unittest.main()
