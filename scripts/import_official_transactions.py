"""استيراد الصفقات الرسمية (تسجيل عقاري) إلى Supabase + الملف المحلي.

الاستخدام:
    python -m scripts.import_official_transactions path/to/transactions.csv
    python -m scripts.import_official_transactions path/to/transactions.json
    (أو من داخل مجلد alforaij-research-assistant: python scripts/import_official_transactions.py …)

صيغة CSV المتوقعة (رؤوس عربية أو إنجليزية):
    reference,area,property_type,transaction_type,price,space,date,original_url,source_note
    رقم الصفقة,المنطقة,نوع العقار,نوع العملية,السعر,المساحة,التاريخ,الرابط,ملاحظة

مثال سطر:
    MOJ-2026-001,خيطان,بيت,للبيع,220000,300,2026-07-15,https://…,تسجيل وزارة العدل

الصفقات تُحفظ في جدول official_transactions (upsert على reference) وفي
data/official_transactions.json كاحتياط محلي دائم حتى عند غياب Supabase.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "official_transactions.json"

FIELD_ALIASES = {
    "reference": ["reference", "رقم الصفقة", "رقم_الصفقة", "id"],
    "area": ["area", "المنطقة", "المحافظة"],
    "property_type": ["property_type", "نوع العقار", "نوع_العقار"],
    "transaction_type": ["transaction_type", "نوع العملية", "نوع_العملية"],
    "price": ["price", "السعر", "قيمة البيع"],
    "space": ["space", "المساحة"],
    "date": ["date", "التاريخ", "تاريخ الصفقة", "تاريخ_الصفقة"],
    "original_url": ["original_url", "url", "الرابط"],
    "source_note": ["source_note", "note", "ملاحظة", "المصدر"],
}


def _pick(row: dict, field: str) -> str:
    for alias in FIELD_ALIASES[field]:
        if row.get(alias) not in (None, ""):
            return str(row[alias]).strip()
    return ""


def read_file(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized = {field: _pick(row, field) for field in FIELD_ALIASES}
        if not normalized["reference"] or not normalized["area"]:
            continue
        output.append(normalized)
    return output


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    source = Path(sys.argv[1])
    if not source.exists():
        print(f"الملف غير موجود: {source}")
        sys.exit(1)
    rows = normalize(read_file(source))
    if not rows:
        print("لا توجد صفقات صالحة (كل صف يحتاج reference وarea).")
        sys.exit(1)

    # 1) الملف المحلي دائمًا
    existing: list[dict] = []
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    by_ref = {str(r.get("reference")): r for r in existing if r.get("reference")}
    for row in rows:
        by_ref[str(row["reference"])] = row
    DATA_FILE.write_text(json.dumps(list(by_ref.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ حُفظ {len(by_ref)} صفقة في data/official_transactions.json")

    # 2) Supabase (إن مضبوط)
    try:
        from backend.services.supabase_store import is_configured, save_official_transactions

        if is_configured():
            save_official_transactions(rows)
            print(f"✓ حُفظ {len(rows)} صفقة في Supabase (official_transactions)")
        else:
            print("⚠ Supabase غير مضبوط — حُفظ محليًا فقط.")
    except Exception as exc:
        print(f"⚠ فشل الحفظ في Supabase: {exc}")


if __name__ == "__main__":
    main()
