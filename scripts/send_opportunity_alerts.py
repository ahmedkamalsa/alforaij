"""إرسال تنبيهات الفرص للمستخدمين المحفوظين (المهمة 3) — يعمل بعد الحصاد اليومي.

التدفق:
1. قراءة آخر لقطتين من جدول opportunities (السابقة/الحالية) عبر service_role.
2. اكتشاف التغييرات (new / price_drop) في الطبقة اليومية — نفس فرق build_whatsapp_alerts.
3. مطابقة الأبحاث المحفوظة المفعلة (المنطقة/النوع/الميزانية) عبر match_search_to_item.
4. كتابة صف تنبيه في user_alerts لكل (سرّ × فرصة) — منع التكرار بقيد unique
   + فحص مسبق (لا يُرسل نفس الزوج مرتين).
5. بوابة الجاهزية: إن اعتُمدت القوالب الثلاثة (OTP + فرصة + انخفاض السعر) أُرسلت
   تنبيهات الوكيل عبر القوالب المعتمدة؛ وإلا تُوثَّق الحالة في ملخص التشغيل
   (GITHUB_STEP_SUMMARY في CI) ويُكتفى بالجرس — دون كسر الحصاد أبدًا.

الاستخدام:
    python scripts/send_opportunity_alerts.py            # لقطتان من Supabase
    python scripts/send_opportunity_alerts.py --dry-run  # دون كتابة أو إرسال
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL  # noqa: E402
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

    # بوابة الجاهزية: إن اعتُمدت القوالب الثلاثة (OTP + فرصة + انخفاض) يُرسل الوكيل
    # واتساب؛ وإلا تُوثَّق الحالة في ملخص التشغيل دون كسر الحصاد (الجرس يعمل دائمًا).
    readiness = whatsapp_readiness()
    write_readiness_summary(readiness)

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
        sent = _send_whatsapp(rows, readiness)
        summary = {
            "status": "ok",
            "snapshots": len(snapshots),
            "changes": len(changes),
            "matchedRows": len(rows),
            "written": written,
            "whatsappSent": sent,
            "whatsappReady": bool(readiness.get("ready")),
            "note": "الجسر داخل التطبيق يعمل دائمًا؛ واتساب يُرسل فقط عند اعتماد القوالب الثلاثة.",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        _emit(f"- التنبيهات: {written} في الجرس · واتساب: {'أُرسل ' + str(sent) if sent else 'لم يُرسل'}")
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


def _send_whatsapp(rows: list[dict], readiness: dict) -> int:
    """إرسال قالب واتساب معتمد لكل تنبيه — صامت ما لم تكتمل الجاهزية.

    البوابة: لا يُرسل شيء عند غياب الأسرار، ولا عند ضبطها دون اعتماد القوالب
    الثلاثة (Meta ترفض إرسال قالب غير معتمد). الجرس داخل التطبيق يعمل دائمًا
    بغضّ النظر — هذا الإرسال طبقة اختيارية فوقه.
    """
    if not readiness.get("configured"):
        return 0
    if not readiness.get("ready"):
        print(
            "WARNING: القوالب الثلاثة غير معتمدة بعد — تُركت التنبيهات في الجرس "
            "(لا إرسال واتساب). التفاصيل في ملخص التشغيل.",
            file=sys.stderr,
        )
        return 0
    from scripts.send_whatsapp_message import send_template_message

    sent = 0
    # كل صف يخص مستخدمًا — رقمه من جدول users (الجرس يخزن السرّ لا الهاتف)
    phones = fetch_user_phones()
    for row in rows:
        phone = phones.get(str(row.get("user_secret") or ""))
        if not phone:
            continue
        template, params = _alert_send_plan(row)
        result = send_template_message(phone, template, params)
        if result:
            sent += 1
    return sent


def _alert_send_plan(row: dict) -> tuple[str, list[str]]:
    """القالب والمتغيرات حسب نوع التغيير — كل قالب بمتغيراته المعتمدة في Meta.

    - new: alforaij_alert (الرمز، المنطقة، السعر)
    - price_drop: alforaij_price_drop (الرمز، المنطقة، السعر الجديد، السعر السابق)

    الرابط مستبعد عمدًا — Meta تمنع الروابط داخل متغيرات نصوص القوالب (مؤكدة
    في وثائق القوالب الرسمية)؛ الرابط متاح داخل التطبيق في الجرس.
    """
    price = _price_text(row.get("price"))
    if row.get("change") == "price_drop":
        return (
            os.getenv("WHATSAPP_PRICE_DROP_TEMPLATE", "alforaij_price_drop"),
            [
                str(row.get("opportunity_code") or ""),
                str(row.get("area") or ""),
                price,
                _price_text(row.get("oldPrice") or row.get("price")),
            ],
        )
    return (
        os.getenv("WHATSAPP_ALERT_TEMPLATE", "alforaij_alert"),
        [str(row.get("opportunity_code") or ""), str(row.get("area") or ""), price],
    )


def _price_text(price) -> str:
    """تنسيق السعر رقمًا بلا عملة (القالب يضيف «د.ك») — سقوط آمن للقيم الشاذة."""
    try:
        return f"{int(float(price)):,}"
    except (TypeError, ValueError):
        return str(price or "")


def _template_name() -> str:
    return os.getenv("WHATSAPP_ALERT_TEMPLATE", "alforaij_alert")


def whatsapp_readiness() -> dict:
    """تقرير جاهزية إرسال واتساب من الأسرار الحالية — بلا شبكة عند غياب التكوين.

    عند ضبط WHATSAPP_TOKEN / WHATSAPP_PHONE_ID يستدعي check_setup (فحص حي لقوالب
    Meta الثلاثة)، مع WHATSAPP_WABA_ID الاختياري إن وُجد. أي فشل شبكي يُحتوى
    ولا يكسر الحصاد: ready=False مع توثيق السبب في الملخص.
    """
    token = os.getenv("WHATSAPP_TOKEN", "").strip()
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "").strip()
    if not token or not phone_id:
        return {
            "configured": False,
            "ready": False,
            "templates": {},
            "reason": "not_configured",
            "nextSteps": ["اضبط WHATSAPP_TOKEN و WHATSAPP_PHONE_ID (انظر docs/whatsapp/README.md)."],
        }
    from scripts.whatsapp_setup import check_setup

    waba_id = os.getenv("WHATSAPP_WABA_ID", "").strip()
    try:
        return check_setup(token, phone_id, waba_id)
    except Exception as exc:  # شبكة/JSON/مهلة — لا نكسر الحصاد أبدًا
        return {
            "configured": True,
            "ready": False,
            "templates": {},
            "reason": "network_error",
            "error": str(exc),
            "nextSteps": ["تعذر الاتصال بـ Meta — سيتحقق التشغيل التالي تلقائيًا."],
        }


def _summary_path() -> str | None:
    """مسار ملخص الخطوة في GitHub Actions — أو None خارج CI (طباعة عادية)."""
    return os.getenv("GITHUB_STEP_SUMMARY") or None


def _emit(line: str) -> None:
    path = _summary_path()
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        print(line)


def write_readiness_summary(report: dict) -> None:
    """توثيق حالة جاهزية واتساب في ملخص التشغيل (أو stdout خارج CI)."""
    _emit("### جاهزية تنبيهات واتساب (الوكيل اليومي)")
    if not report.get("configured"):
        _emit("- ❌ الأسرار غير مضبوطة — WHATSAPP_TOKEN / WHATSAPP_PHONE_ID مطلوبان.")
        _emit("- التنبيهات تتراكم في الجرس داخل التطبيق (لا إرسال واتساب حتى ضبط الأسرار).")
        _emit("- الخطوة التالية: docs/whatsapp/README.md")
        return
    if report.get("error"):
        _emit(f"- ❌ تعذر الاتصال بـ Meta: {report['error']}")
        _emit("- سيتحقق التشغيل التالي تلقائيًا — الحصاد لم يتأثر.")
        return
    phone = report.get("phone") or {}
    waba = report.get("waba") or {}
    _emit(
        f"- الرقم المرسِل: {phone.get('phone') or '—'} · الاسم الموثق: "
        f"{phone.get('verifiedName') or '—'} · جودة المرسل: {phone.get('quality') or '—'}"
    )
    _emit(f"- WABA: {phone.get('wabaName') or '—'} (معرّف: {waba.get('id') or '—'})")
    for name, row in (report.get("templates") or {}).items():
        status = row.get("status") or "غير موجود"
        icon = "✅" if status == "APPROVED" else ("⏳" if status else "❌")
        _emit(f"- القالب `{name}`: {icon} {status}")
    if report.get("ready"):
        _emit("- ✅ القوالب الثلاثة معتمدة — تُرسل تنبيهات الوكيل عبر واتساب.")
    else:
        _emit("- ⏳ غير جاهز — التنبيهات تُكتب في الجرس ولا يُرسل واتساب حتى اعتماد القوالب الثلاثة.")
        for step in report.get("nextSteps", []):
            _emit(f"  - {step}")


if __name__ == "__main__":
    sys.exit(main())
