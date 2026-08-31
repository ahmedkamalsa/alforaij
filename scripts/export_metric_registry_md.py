"""توليد docs/source.md من سجل المقاييس الحي في backend.

مرجع المطورين خارج الواجهة — يُقرأ من نفس مصدر `/api/metric-registry`
(build_metric_registry في backend/services/metric_registry.py) فلا ينحرف
عن الصيغ والثوابت الفعلية في المحرك أبدًا.

الاستخدام:
    python scripts/export_metric_registry_md.py

بعد أي تغيير في ثوابت الحساب أعد توليد الملف بنفس الأمر.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.metric_registry import build_metric_registry  # noqa: E402

STATUS_LABELS = {
    "approved": "معتمد — فريق بيانات الفريج",
    "auto": "محسوب تلقائيًا من الحصاد",
}


def _cell(text: str) -> str:
    """تأمين خلية جدول: استبدال الرمز العمودي وأسطر جديدة حتى لا يكسر الجدول."""
    return str(text or "—").replace("|", "\\|").replace("\n", " ").strip() or "—"


def _rows_to_md(rows: list[dict]) -> list[str]:
    lines = [
        "| المقياس | التعريف | الصيغة | المصدر | الحالة |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        status = STATUS_LABELS.get(row.get("status"), row.get("status", ""))
        lines.append(
            "| **{name}** | {what} | {formula} | {source} | {status} |".format(
                name=_cell(row.get("name")),
                what=_cell(row.get("what")),
                formula=_cell(row.get("formula")),
                source=_cell(row.get("source")),
                status=_cell(status),
            )
        )
    return lines


def build_markdown(data: dict) -> str:
    sections = data.get("sections", [])
    total = sum(len(s.get("rows", [])) for s in sections)
    generated = str(data.get("generatedAt", "")).replace("T", " ").replace("+00:00", " UTC")

    lines = [
        "# سجل تعريفات المقاييس — مرجع المطورين",
        "",
        "> **مصدر حي**: هذا الملف مولَّد تلقائيًا من `backend/services/metric_registry.py`",
        "> (نفس البيانات التي يخدمها `/api/metric-registry` للواجهة). أي تعديل في ثوابت",
        "> الحساب داخل المحرك (`valuation.py` / `opportunities.py` / `market_analysis.py`)",
        "> يُعاد توليده هنا بنفس القيم — لا تنسخ الأرقام يدويًا.",
        "",
        f"- **آخر توليد**: {generated}",
        f"- **الأقسام**: {len(sections)}",
        f"- **إجمالي المقاييس الموثقة**: {total}",
        f"- **الحالة**: `معتمد` = قرار/قاعدة فريق بيانات الفريج · `محسوب تلقائيًا` = قيمة تُحسب من الحصاد",
        "",
        "## إعادة التوليد",
        "",
        "```bash",
        "cd alforaij-research-assistant",
        "python scripts/export_metric_registry_md.py",
        "```",
        "",
        "---",
        "",
    ]

    for index, section in enumerate(sections, start=1):
        rows = section.get("rows", [])
        lines.append(f"## {index}. {section.get('title', '')}")
        lines.append("")
        lines.append(f"_{section.get('note', '')}_")
        lines.append("")
        lines.extend(_rows_to_md(rows))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    data = build_metric_registry()
    out_path = Path(__file__).resolve().parent.parent / "docs" / "source.md"
    out_path.write_text(build_markdown(data), encoding="utf-8")
    total = sum(len(s.get("rows", [])) for s in data.get("sections", []))
    print(f"تم توليد {out_path} — {total} مقياسًا من {len(data.get('sections', []))} أقسام.")


if __name__ == "__main__":
    main()
