"""اختبارات الدالة النقية لسكريبت الفحص اليومي (scripts/check_harvest_governorates.py).

تفحص check_harvest_governorates نفسها بصفوف صناعية بلا شبكة: كيف تُصنَّف
المناطق المعروفة، وكيف تُلتقط منطقة حصاد جديدة بلا إسناد مع عددها ومصادرها
وعيناتها — وهي نفس الدالة التي يشغّلها السكريبت ضد Supabase يوميًا.
"""
from __future__ import annotations

import unittest

from scripts.check_harvest_governorates import check_harvest_governorates


def _row(area: str, source: str = "OpenSooq", summary: str = "", gov: str = "") -> dict:
    return {
        "area": area,
        "governorate": gov,
        "summary": summary or f"إعلان في {area}",
        "features": "",
        "source": source,
        "original_url": f"https://example.com/{area}",
    }


class CheckHarvestGovernoratesTests(unittest.TestCase):
    def test_all_known_areas_report_ok(self) -> None:
        rows = [
            _row("السالمية"),
            _row("صباح الأحمد", source="4Sale"),
            _row("خيطان", source="Q8Aqar"),
        ]
        report = check_harvest_governorates(rows)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["rowsChecked"], 3)
        self.assertEqual(report["rowsWithArea"], 3)
        self.assertEqual(report["unresolvedAreas"], 0)
        self.assertEqual(report["unresolvedRows"], 0)
        self.assertEqual(report["areas"], [])

    def test_unknown_area_marks_failed_with_details(self) -> None:
        rows = [
            _row("منطقة حصاد جديدة وهمية", source="4Sale", summary="للبيع فيلا في منطقة الحصاد الجديدة"),
            _row("منطقة حصاد جديدة وهمية", source="OpenSooq"),
        ]
        report = check_harvest_governorates(rows)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["unresolvedAreas"], 1)
        self.assertEqual(report["unresolvedRows"], 2)
        entry = report["areas"][0]
        self.assertEqual(entry["area"], "منطقة حصاد جديدة وهمية")
        self.assertEqual(entry["count"], 2)
        self.assertEqual(entry["sources"], {"4Sale": 1, "OpenSooq": 1})
        self.assertEqual(len(entry["samples"]), 2)  # حد أقصى 3 عينات
        self.assertTrue(entry["samples"][0]["summary"])
        self.assertTrue(entry["samples"][0]["url"])

    def test_rows_without_area_are_excluded(self) -> None:
        report = check_harvest_governorates([_row(""), {"area": "", "governorate": "", "summary": "", "features": ""}])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["rowsChecked"], 2)
        self.assertEqual(report["rowsWithArea"], 0)

    def test_empty_rows_report_ok(self) -> None:
        report = check_harvest_governorates([])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["rowsChecked"], 0)
        self.assertEqual(report["areas"], [])

    def test_governorate_name_as_area_is_not_a_failure(self) -> None:
        # منطقة تحمل اسم محافظة («الجهراء» كمنطقة في خبز فتات قديم) — اللوحة تحسمها كمحافظة
        report = check_harvest_governorates([_row("الجهراء")])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["unresolvedAreas"], 0)


if __name__ == "__main__":
    unittest.main()
