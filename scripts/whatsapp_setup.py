"""أداة إعداد وفحص واتساب (Meta Cloud API) — بلا اعتماديات (urllib فقط).

تغلق الفجوة بين الكود الجاهز والتسليم الفعلي على الهاتف: بدل فتح لوحة
Meta يدويًا، تُنشئ الأداة القالبين المعتمدين برمجيًا وتفحص جاهزية الحساب.

الاستخدام (تأكد من ضبط WHATSAPP_TOKEN و WHATSAPP_PHONE_ID أولًا):
    python scripts/whatsapp_setup.py --check                    # تقرير جاهزية كامل
    python scripts/whatsapp_setup.py --create-otp               # قالب رمز التحقق (AUTHENTICATION)
    python scripts/whatsapp_setup.py --create-alert             # قالب تنبيه الفرصة (UTILITY)
    python scripts/whatsapp_setup.py --send-test +96555512345   # إرسال رمز تجريبي فعلي لرقمك

اختياري: WHATSAPP_WABA_ID — معرّف حساب الأعمال (WhatsApp Business Account)
مباشر يُستعمل عند إنشاء القوالب وفحصها بدل استنتاجه من رقم الهاتف (يفيد
حين يكون رقم الهاتف مرتبطًا بعدة حسابات أو يتعذر حل WABA منه).

قواعد تصميم القوالب (مؤكدة من وثائق Meta الرسمية):
- قوالب التوثيق (OTP): نص ثابت تُولّده Meta تلقائيًا بكل اللغات (بما فيها
  العربية) بمتغير واحد {{1}} — لا يمكن تخصيصه، ولهذا تُنشأ عبر
  upsert_message_templates بمكوّن BODY + FOOTER + زر OTP من نوع COPY_CODE.
- الروابط ممنوعة داخل متغيرات نصوص القوالب — لذلك قالب التنبيه يحمل
  3 متغيرات فقط (الرمز/المنطقة/السعر) والرابط متاح داخل التطبيق في الجرس.

كل دوال البناء نقية وقابلة للاختبار؛ النداءات الشبكية معزولة في _graph.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

GRAPH_API_VERSION = "v19.0"
GRAPH_API = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

OTP_TEMPLATE_NAME = "alforaij_otp"
ALERT_TEMPLATE_NAME = "alforaij_alert"

# نص قالب تنبيه الفرصة — 3 متغيرات بالترتيب الذي يمرره send_opportunity_alerts:
# {{1}} رمز الفرصة · {{2}} المنطقة · {{3}} السعر (الرابط مستبعد عمدًا — قاعدة Meta).
ALERT_BODY = (
    "فرصة جديدة من منصة الفريج العقاري\n"
    "الرمز: {{1}}\n"
    "المنطقة: {{2}}\n"
    "السعر: {{3}} د.ك\n"
    "افتح المنصة لعرض التفاصيل والمصادر"
)
ALERT_FOOTER = "منصة الفريج — فرص وتقييم عقاري"


def build_otp_payload() -> dict:
    """حمولة إنشاء قالب رمز التحقق (AUTHENTICATION) بصيغة upsert_message_templates.

    النص ثابت من Meta (يُولَّد بالعربية تلقائيًا): «{{1}} هو رمز التحقق الخاص بك»
    + تحذير أمني + انتهاء بعد 10 دقائق + زر نسخ الرمز (بلا حاجة لتطبيق جوال).
    """
    return {
        "name": OTP_TEMPLATE_NAME,
        "languages": ["ar"],
        "category": "AUTHENTICATION",
        "components": [
            {"type": "BODY", "add_security_recommendation": True},
            {"type": "FOOTER", "code_expiration_minutes": 10},
            {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
        ],
    }


def build_alert_payload() -> dict:
    """حمولة إنشاء قالب تنبيه الفرصة (UTILITY) بثلاثة متغيرات نصية."""
    return {
        "name": ALERT_TEMPLATE_NAME,
        "languages": ["ar"],
        "category": "UTILITY",
        "components": [
            {"type": "BODY", "text": ALERT_BODY},
            {"type": "FOOTER", "text": ALERT_FOOTER},
        ],
    }


def _graph(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """نداء Graph API واحد — يعيد JSON أو يرمي RuntimeError مع تفاصيل Meta."""
    url = f"{GRAPH_API}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def _status_icon(status: str) -> str:
    """أيقونة حالة قالب حسب ما يرجعه Meta."""
    return {
        "APPROVED": "✅ معتمد",
        "PENDING": "⏳ قيد المراجعة",
        "IN_APPEAL": "⏳ استئناف",
        "REJECTED": "❌ مرفوض",
        "DISABLED": "⚠️ معطّل",
        "PAUSED": "⚠️ موقوف",
    }.get(status or "", f"❓ {status or 'غير معروف'}")


def fetch_waba(token: str, phone_id: str) -> dict:
    """رقم الهاتف + حساب الأعمال (WABA) من رقم الهاتف — يتحقق أيضًا من صلاحية التوكن."""
    data = _graph(
        "GET",
        f"{phone_id}?fields=display_phone_number,verified_name,quality_rating,"
        f"whatsapp_business_account{{id,name}}",
        token,
    )
    waba = data.get("whatsapp_business_account") or {}
    return {
        "phone": str(data.get("display_phone_number") or ""),
        "verifiedName": str(data.get("verified_name") or ""),
        "quality": str(data.get("quality_rating") or ""),
        "wabaId": str(waba.get("id") or ""),
        "wabaName": str(waba.get("name") or ""),
    }


def fetch_template_statuses(token: str, waba_id: str) -> dict[str, dict]:
    """حالة قالبَي المنصة من قائمة قوالب الحساب (بالاسم لا بالمعرّف)."""
    statuses: dict[str, dict] = {
        OTP_TEMPLATE_NAME: {"status": None, "id": ""},
        ALERT_TEMPLATE_NAME: {"status": None, "id": ""},
    }
    if not waba_id:
        return statuses
    data = _graph("GET", f"{waba_id}/message_templates?limit=100", token)
    for row in data.get("data") or []:
        name = str(row.get("name") or "")
        if name in statuses:
            statuses[name] = {
                "status": str(row.get("status") or ""),
                "id": str(row.get("id") or ""),
                "category": str(row.get("category") or ""),
            }
    return statuses


def check_setup(token: str, phone_id: str, waba_id: str = "") -> dict:
    """تقرير الجاهزية الكامل — يُرجع dict ويطبع التقرير (صالح للاختبار بلا شبكة).

    waba_id اختياري: عند ضبطه يُستعمل مباشرة لفحص القوالب بدل استنتاجه من
    رقم الهاتف (fetch_waba يبقى لتقرير الرقم/الجودة فقط).
    """
    configured = bool(token and phone_id)
    report: dict = {
        "configured": configured,
        "phone": {},
        "waba": {},
        "templates": {},
        "ready": False,
        "nextSteps": [],
    }
    if not configured:
        report["nextSteps"] = [
            "اضبط WHATSAPP_TOKEN و WHATSAPP_PHONE_ID في البيئة (انظر docs/whatsapp/README.md)."
        ]
        return report
    try:
        info = fetch_waba(token, phone_id)
    except RuntimeError as exc:
        report["error"] = f"تعذر الاتصال بـ Meta: {exc}"
        report["nextSteps"] = [
            "تحقق من صلاحية التوكن (System User بصلاحية whatsapp_business_messaging) "
            "ومن صحة WHATSAPP_PHONE_ID.",
        ]
        return report
    report["phone"] = info
    effective_waba = waba_id or info.get("wabaId") or ""
    report["waba"] = {"id": effective_waba, "source": "env" if waba_id else "phone"}
    statuses = fetch_template_statuses(token, effective_waba)
    report["templates"] = statuses
    otp = statuses.get(OTP_TEMPLATE_NAME, {}).get("status")
    alert = statuses.get(ALERT_TEMPLATE_NAME, {}).get("status")
    ready = effective_waba and otp == "APPROVED" and alert == "APPROVED"
    report["ready"] = bool(ready)
    next_steps: list[str] = []
    if not effective_waba:
        next_steps.append("لم يُعثر على حساب WhatsApp Business — تحقق من رقم الهاتف أو اضبط WHATSAPP_WABA_ID.")
    if otp != "APPROVED":
        next_steps.append("شغّل: python scripts/whatsapp_setup.py --create-otp (ثم انتظر الاعتماد).")
    if alert != "APPROVED":
        next_steps.append("شغّل: python scripts/whatsapp_setup.py --create-alert (ثم انتظر الاعتماد).")
    if ready:
        next_steps.append("كل شيء جاهز — جرّب إرسالًا فعليًا: --send-test +965XXXXXXXX.")
    report["nextSteps"] = next_steps
    return report


def print_report(report: dict) -> None:
    """طباعة تقرير عربي مقروء من dict الجاهزية."""
    if not report.get("configured"):
        print("❌ الأسرار غير مضبوطة — WHATSAPP_TOKEN و WHATSAPP_PHONE_ID مطلوبان.")
        print("   الخطوة التالية: docs/whatsapp/README.md")
        return
    if report.get("error"):
        print(f"❌ {report['error']}")
        for step in report.get("nextSteps", []):
            print(f"   • {step}")
        return
    phone = report.get("phone") or {}
    print("=== رقم الهاتف المرسِل ===")
    print(f"   الرقم: {phone.get('phone') or '—'}")
    print(f"   الاسم الموثق: {phone.get('verifiedName') or '—'}")
    print(f"   جودة المرسل: {phone.get('quality') or '—'}")
    print("=== حساب الأعمال (WABA) ===")
    print(f"   {phone.get('wabaName') or '—'} (معرّف: {phone.get('wabaId') or '—'})")
    print("=== القوالب ===")
    templates = report.get("templates") or {}
    for name, row in templates.items():
        status = row.get("status")
        icon = _status_icon(status) if status else "❌ غير موجود"
        print(f"   {name}: {icon}")
        if row.get("category") and row.get("category") != "None":
            print(f"      التصنيف: {row['category']}")
    print("=== الخطوات التالية ===")
    for step in report.get("nextSteps", []):
        print(f"   • {step}")
    if report.get("ready"):
        print("\n✅ النظام جاهز للإرسال الفعلي على الهاتف.")


def _upsert_template(token: str, phone_id: str, payload: dict, waba_id: str = "") -> dict:
    """إنشاء/تحديث قالب عبر upsert_message_templates — يعيد النتيجة أو يرمي السبب.

    waba_id اختياري: عند ضبطه يُستعمل مباشرة (بلا استنتاج من رقم الهاتف)،
    وإلا يُحل من fetch_waba كالسابق.
    """
    if waba_id:
        info_waba = waba_id
    else:
        info = fetch_waba(token, phone_id)
        if not info.get("wabaId"):
            raise RuntimeError("لا يمكن تحديد حساب WhatsApp Business من رقم الهاتف.")
        info_waba = info["wabaId"]
    result = _graph(
        "POST",
        f"{info_waba}/upsert_message_templates",
        token,
        payload,
    )
    rows = result.get("data") or []
    statuses = {str(row.get("language") or ""): str(row.get("status") or "") for row in rows}
    return {"wabaId": info_waba, "languages": statuses, "raw": result}


def send_test_otp(token: str, phone_id: str, to_phone: str) -> dict:
    """إرسال رمز تجريبي فعلي (قالب alforaij_otp) إلى رقم — يثبت التسليم من البداية للنهاية."""
    from scripts.send_whatsapp_message import send_template_message

    result = send_template_message(to_phone, OTP_TEMPLATE_NAME, ["123456"])
    if not result:
        raise RuntimeError(
            "فشل الإرسال — تحقق من اعتماد القالب (--check) ومن أن الرقم مسجّل في واتساب."
        )
    return result


def _env() -> tuple[str, str, str]:
    token = str(os.getenv("WHATSAPP_TOKEN", "")).strip()
    phone_id = str(os.getenv("WHATSAPP_PHONE_ID", "")).strip()
    waba_id = str(os.getenv("WHATSAPP_WABA_ID", "")).strip()
    return token, phone_id, waba_id


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 1
    token, phone_id, waba_id = _env()
    command = args[0]
    if command == "--check":
        print_report(check_setup(token, phone_id, waba_id))
        return 0 if check_setup(token, phone_id, waba_id).get("ready") else 1
    if command in ("--create-otp", "--create-alert"):
        if not token or not phone_id:
            print("❌ WHATSAPP_TOKEN و WHATSAPP_PHONE_ID مطلوبان.", file=sys.stderr)
            return 1
        payload = build_otp_payload() if command == "--create-otp" else build_alert_payload()
        print(f"إنشاء/تحديث قالب «{payload['name']}»...")
        try:
            result = _upsert_template(token, phone_id, payload, waba_id)
        except RuntimeError as exc:
            print(f"❌ فشل الإنشاء: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result["languages"], ensure_ascii=False, indent=2))
        print("القوالب من فئة AUTHENTICATION تُعتمد فورًا عادةً؛ UTILITY خلال دقائق–ساعات.")
        return 0
    if command == "--send-test":
        if len(args) < 2 or not token or not phone_id:
            print("الاستخدام: WHATSAPP_TOKEN=... WHATSAPP_PHONE_ID=... "
                  "python scripts/whatsapp_setup.py --send-test +965XXXXXXXX", file=sys.stderr)
            return 1
        print(f"إرسال رمز تجريبي إلى {args[1]}...")
        try:
            result = send_test_otp(token, phone_id, args[1])
        except RuntimeError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        print("✅ إن وصل الرمز 123456 إلى هاتفك فالتسليم الفعلي يعمل من البداية للنهاية.")
        return 0
    print(f"أمر غير معروف: {command}\n{__doc__}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
