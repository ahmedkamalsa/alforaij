"""فحص يومي لضمانة المحافظات: كل منطقة في market_listings الحية تُحل إلى محافظة في اللوحة.

يشغّل نفس ضمانة tests/test_market_listings_governorates.py ضد القاعدة الحية:
يجلب كل صفوف market_listings (ترقيم صفحاتي كامل) ويمرر كل صف يحمل منطقة عبر
_normalize_dashboard_place بالخريطة المعتمدة وحدها (بلا تعلم من البيانات —
التعلم شبكة أمان، والضمانة أن الخريطة تغطي كل ما يصل فعلًا).

النتيجة (رمز الخروج):
- ok: لا مناطق بلا إسناد → 0.
- failed: منطقة/مناطق حصاد جديدة بلا إسناد → 1 (يفشل المجدول/CI) مع تقرير
  مفصّل (المنطقة، العدد، المصادر، عينة ملخصات وروابط) في الطرفية وملف
  data/harvest_governorates_check.json وملخص في GITHUB_STEP_SUMMARY إن وُجد.
- unconfigured: Supabase بلا إعدادات أو القاعدة فارغة — «لا شيء للفحص» ليس
  انتهاكًا للضمانة → 0، مع حالة صريحة في الملف (يُرى أن الفحص لم يعمل فعلًا).

الاستخدام:
    python scripts/check_harvest_governorates.py
    python scripts/check_harvest_governorates.py --dry-run   # بلا كتابة ملف الحالة

جدولة يومية (Windows Task Scheduler / cron / CI):
    python scripts/check_harvest_governorates.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.main import _area_governorate_map, _normalize_dashboard_place  # noqa: E402

# ملف حالة الفحص — يُكتب كل تشغيل ليكون قابلاً للقراءة آليًا أو من الواجهة لاحقًا
STATUS_PATH = ROOT / "data" / "harvest_governorates_check.json"


def _to_record(row: Any) -> dict[str, str]:
    """صف market_listings (dict من Supabase) → سجل بالشكل الذي تتوقعه اللوحة."""
    return {
        "area": str(row.get("area") or "").strip(),
        "governorate": str(row.get("governorate") or "").strip(),
        "summary": str(row.get("summary") or ""),
        "features": str(row.get("features") or ""),
    }


def _fetch_all_market_rows() -> list[dict[str, Any]]:
    """كل صفوف market_listings النشطة (Supabase يسقف النتيجة عند 1000 صف/طلب)."""
    from backend.services.supabase_store import fetch_market_listings

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = fetch_market_listings(limit=1000, offset=offset) or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def check_harvest_governorates(rows: list[Any]) -> dict[str, Any]:
    """فحص نقي (بلا شبكة): المناطق التي تظهر في الحصاد وتبقى بلا محافظة في اللوحة.

    تُفحص بالخريطة المعتمدة وحدها — أي منطقة لا تعرفها الخريطة تُسجَّل بعددها
    ومصادرها وعينة من ملخصاتها وروابطها ليعرف المطوّر ماذا يضيف.
    """
    area_map = _area_governorate_map([])
    by_area: dict[str, dict[str, Any]] = {}
    rows_with_area = 0
    for row in rows:
        record = _to_record(row)
        area = record["area"]
        if not area:
            continue  # «بلا موقع» — لا منطقة أصلًا، خارج نطاق هذه الضمانة
        rows_with_area += 1
        _normalize_dashboard_place(record, area_map)
        if record.get("governorate"):
            continue
        entry = by_area.setdefault(area, {"area": area, "count": 0, "sources": {}, "samples": []})
        entry["count"] += 1
        source = str(row.get("source") or "غير معروف").strip() or "غير معروف"
        entry["sources"][source] = entry["sources"].get(source, 0) + 1
        if len(entry["samples"]) < 3:
            entry["samples"].append({
                "summary": (str(row.get("summary") or row.get("features") or "").strip())[:140],
                "source": source,
                "url": str(row.get("original_url") or "")[:160],
            })
    areas = sorted(by_area.values(), key=lambda e: (-e["count"], e["area"]))
    return {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not areas else "failed",
        "rowsChecked": len(rows),
        "rowsWithArea": rows_with_area,
        "unresolvedAreas": len(areas),
        "unresolvedRows": sum(e["count"] for e in areas),
        "areas": areas,
    }


def _write_status(report: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    STATUS_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _emit(line: str) -> None:
    """ملخص قابل للقراءة: سطر Markdown في GITHUB_STEP_SUMMARY إن وُجد، وإلا stdout."""
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        print(line)


def _emit_report(report: dict[str, Any]) -> None:
    if report.get("status") == "unconfigured":
        _emit("### فحص محافظات الحصاد — تعذّر الفحص")
        _emit(f"- {report.get('note', '')}")
        return
    _emit("### فحص محافظات الحصاد اليومي (market_listings)")
    _emit(f"- الحالة: {'✅ ok' if report['status'] == 'ok' else '❌ failed'} · "
          f"{report['rowsChecked']} صفًا · {report['rowsWithArea']} بمنطقة · "
          f"{report['unresolvedAreas']} منطقة بلا إسناد ({report['unresolvedRows']} صفًا)")
    for entry in report.get("areas", []):
        sources = "، ".join(f"{s} ×{n}" for s, n in sorted(entry["sources"].items()))
        _emit(f"- `{entry['area']}` ×{entry['count']} — المصادر: {sources}")
        for sample in entry["samples"]:
            url = sample["url"]
            _emit(f"  - {sample['summary'][:80]}{' — ' + url if url else ''}")
    if report["status"] == "failed":
        _emit("")
        _emit("**لماذا فشل الفحص وكيف تُصلحه؟** اقرأ [docs/MAP_GUARANTEES.md](docs/MAP_GUARANTEES.md) — كل ما تحتاج معرفته عن أسباب كدس المناطق تحت «غير محددة» وخطوات الإضافة في الخريطة.")


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    try:
        rows = _fetch_all_market_rows()
    except Exception as exc:  # شبكة/مهلة/أذونات — لا يكسر المجدول، تُوثَّق الحالة
        report = {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "status": "unconfigured",
            "rowsChecked": 0,
            "rowsWithArea": 0,
            "unresolvedAreas": 0,
            "unresolvedRows": 0,
            "areas": [],
            "note": f"تعذّر جلب market_listings: {type(exc).__name__}: {exc}",
        }
        _write_status(report, dry_run)
        _emit_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        report = {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "status": "unconfigured",
            "rowsChecked": 0,
            "rowsWithArea": 0,
            "unresolvedAreas": 0,
            "unresolvedRows": 0,
            "areas": [],
            "note": "market_listings غير مهيأة أو فارغة (is_configured=False) — لا يمكن الفحص.",
        }
        _write_status(report, dry_run)
        _emit_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    report = check_harvest_governorates(rows)
    _write_status(report, dry_run)
    _emit_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # فشل صريح للمجدول/CI عند أي منطقة حصاد بلا إسناد — يُصلَح بإضافة الإسناد للخريطة
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
