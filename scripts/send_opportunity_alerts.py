"""إرسال تنبيهات الفرص للمستخدمين المحفوظين (المهمة 3) — يعمل بعد الحصاد اليومي.

التدفق:
1. قراءة آخر لقطتين من جدول opportunities (السابقة/الحالية) عبر service_role.
2. اكتشاف التغييرات (new / price_drop) في الطبقة اليومية — نفس فرق build_whatsapp_alerts.
3. مطابقة الأبحاث المحفوظة المفعلة (المنطقة/النوع/الميزانية) عبر match_search_to_item.
4. كتابة صف تنبيه في user_alerts لكل (سرّ × فرصة) — منع التكرار بقيد unique
   + فحص مسبق (لا يُرسل نفس الزوج مرتين).
5. إن وُجدت أسرار واتساب: إرسال قالب alert_template؛ وإلا يكتفي بالجرس (الانحدار الأنيق).

الاستخدام:
    python scripts/send_opportunity_alerts.py            # لقطتان من Supabase
    python scripts/send_opportunity_alerts.py --dry-run  # دون كتابة أو إرسال
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, WHATSAPP_PHONE_ID, WHATSAPP_TOKEN  # noqa: E402
from backend.services.opportunity_alerts import (  # noqa: E402
    build_alert_rows,
    filter_unsent_alerts,
    find_changes,
)
from backend.services.supabase_store import (  # noqa: E402
    fetch_existing_alert_keys,
    fetch_opportunity_snapshots,
    fetch_saved_searches,
    fetch_user_phones,
    insert_user_alerts,
)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY غير مضبوطين — لا يمكن تشغيل التنبيهات.")
        return 1

    snapshots = fetch_opportunity_snapshots(limit=2)
    if not snapshots:
        print("لا توجد لقطات فرص في القاعدة — لا شيء للمقارنة.")
        return 0
    current = _to_snapshot(snapshots[0])
    previous = _to_snapshot(snapshots[1]) if len(snapshots) > 1 else None

    changes = find_changes(previous, current)
    if not changes:
        print(f"لا تغييرات بين اللقطتين ({len(snapshots)} لقطة) — لا تنبيهات.")
        return 0

    searches = fetch_saved_searches()
    print(f"لقطتان مقارنتان · {len(changes)} تغييرًا · {len(searches)} بحثًا محفوظًا مفعّلًا.")

    rows = build_alert_rows(previous, current, searches)
    if not rows:
        print("لا أبحاث مطابقة للتغييرات — لا تنبيهات.")
        return 0

    if not dry_run:
        existing = fetch_existing_alert_keys()
        rows = filter_unsent_alerts(rows, existing)
        if not rows:
            print("كل التغييرات نُبّه عنها سابقًا (منع التكرار) — لا شيء جديد.")
            return 0
        written = insert_user_alerts(rows)
        print(f"كُتب {written} تنبيهًا في الجرس.")
        sent = _send_whatsapp(rows)
        summary = {
            "status": "ok",
            "snapshots": len(snapshots),
            "changes": len(changes),
            "matchedRows": len(rows),
            "written": written,
            "whatsappSent": sent,
            "note": "الجسر داخل التطبيق يعمل دائمًا؛ واتساب يُرسل فقط عند ضبط أسرار Cloud API.",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"dryRun": True, "candidateRows": len(rows)}, ensure_ascii=False, indent=2))
    return 0


def _to_snapshot(row: dict) -> dict:
    """تحويل صف Supabase (tiers/forecast JSONB) إلى شكل لقطة الفرص المعتاد."""
    return {
        "generatedAt": row.get("generated_at") or "",
        "tiers": row.get("tiers") or {},
        "forecast": row.get("forecast") or [],
    }


def _send_whatsapp(rows: list[dict]) -> int:
    """إرسال قالب واتساب لكل تنبيه — صامت عند غياب الأسرار (الانحدار الأنيق)."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print(
            "WARNING: WHATSAPP_TOKEN / WHATSAPP_PHONE_ID غير مضبوطين — "
            "التنبيهات متراكمة في الجرس داخل التطبيق (لا إرسال واتساب).",
            file=sys.stderr,
        )
        return 0
    from scripts.send_whatsapp_message import send_template_message

    template = _template_name()
    sent = 0
    # كل صف يخص مستخدمًا — رقمه من جدول users (الجرس يخزن السرّ لا الهاتف)
    phones = fetch_user_phones()
    for row in rows:
        phone = phones.get(str(row.get("user_secret") or ""))
        if not phone:
            continue
        result = send_template_message(phone, template, _alert_template_params(row))
        if result:
            sent += 1
    return sent


def _alert_template_params(row: dict) -> list[str]:
    """متغيرات قالب التنبيه بالترتيب المعتمد في Meta: الرمز ثم المنطقة ثم السعر المنسق.

    الرابط مستبعد عمدًا — Meta تمنع الروابط داخل متغيرات نصوص القوالب (مؤكدة
    في وثائق القوالب الرسمية)؛ الرابط متاح داخل التطبيق في الجرس.
    """
    price = row.get("price")
    try:
        price_text = f"{int(float(price)):,}"
    except (TypeError, ValueError):
        price_text = str(price or "")
    return [
        str(row.get("opportunity_code") or ""),
        str(row.get("area") or ""),
        price_text,
    ]


def _template_name() -> str:
    import os

    return os.getenv("WHATSAPP_ALERT_TEMPLATE", "alforaij_alert")


if __name__ == "__main__":
    sys.exit(main())
