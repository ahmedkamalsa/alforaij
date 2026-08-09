from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from backend.services.supabase_store import is_configured, save_official_transactions
from scripts.import_official_transactions import DATA_FILE, normalize


def _read_content(filename: str, content: str) -> list[dict[str, Any]]:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".json" or content.lstrip().startswith(("[", "{")):
        data = json.loads(content)
        if isinstance(data, dict):
            for key in ("rows", "transactions", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
            return []
        return data if isinstance(data, list) else []
    return list(csv.DictReader(content.splitlines()))


def _save_local(rows: list[dict[str, Any]]) -> int:
    existing: list[dict[str, Any]] = []
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    by_ref = {str(row.get("reference")): row for row in existing if row.get("reference")}
    for row in rows:
        by_ref[str(row["reference"])] = row
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(list(by_ref.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    return len(by_ref)


def import_official_transactions_content(filename: str, content: str) -> dict[str, Any]:
    if not content.strip():
        return {"status": "empty", "imported": 0, "error": "الملف فارغ."}
    try:
        rows = normalize(_read_content(filename, content))
    except Exception as exc:
        return {"status": "invalid", "imported": 0, "error": f"تعذر قراءة الملف: {exc}"}
    if not rows:
        return {
            "status": "invalid",
            "imported": 0,
            "error": "لا توجد صفقات صالحة. كل صف يحتاج reference وarea على الأقل، ويفضل price/space/date.",
        }

    local_total = _save_local(rows)
    supabase_status = "not_configured"
    if is_configured():
        try:
            save_official_transactions(rows)
            supabase_status = "saved"
        except Exception as exc:
            supabase_status = f"failed: {exc}"

    return {
        "status": "saved",
        "imported": len(rows),
        "localTotal": local_total,
        "supabase": supabase_status,
        "message": "تم استيراد الصفقات الرسمية. شغّل وكيل التحديث لإعادة بناء الفرص والتقييمات.",
    }
