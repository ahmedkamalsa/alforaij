"""إرسال تنبيهات واتساب التلقائي عبر Meta Cloud API — بقوالب UTILITY معتمدة.

يرتبط بالوكيل اليومي: بعد بناء تنبيهات `build_whatsapp_alerts` (فرصة جديدة أو
انخفاض سعر يطابق عميلًا مسجلًا) يُرسل رسالة قالب فعلية لكل رقم عميل مطابق.

**لماذا قوالب وليست نصًا حرًا؟** الرسالة النصية الحرة تعمل فقط داخل نافذة
الرد 24 ساعة (من آخر رسالة للمستخدم). التنبيهات اليومية تصل خارج تلك النافذة
بالضرورة، ولا تسمح Meta بها إلا عبر قالب UTILITY معتمد — لذلك كل إرسال هنا
يُبنى من قالب معتمد (alforaij_alert للفرص الجديدة، alforaij_price_drop
لانخفاض السعر) بمتغيرات نصية محددة، ويتسق مع أداة إنشاء القوالب
(whatsapp_setup.py --create-alert / --create-price-drop).

مع الحفاظ على:
- **عدم تكرار**: سجل محلي `data/whatsapp_send_log.json` يمنع إعادة إرسال نفس
  (إعلان × رقم × نوع التغيير) في نفس اليوم — حتى لو أُعيد تشغيل الوكيل.
- **تتبع موحّد**: كل إرسال يُسجَّل اختياريًا في `outreach_clicks` (Supabase)
  بنفس آلية نقرات التسويق ليظهر في عدّادات التفاعل.
- **أمان التشغيل**: غياب الضبط (WHATSAPP_TOKEN / WHATSAPP_PHONE_ID) لا يكسر
  الوكيل إطلاقًا — يعيد `not_configured` مع تعليمات الإعداد الصريحة.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import (
    WHATSAPP_PHONE_ID,
    WHATSAPP_SENDER_NAME,
    WHATSAPP_TOKEN,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SEND_LOG_PATH = ROOT / "data" / "whatsapp_send_log.json"
GRAPH_API = "https://graph.facebook.com/v19.0"

# قوالب UTILITY المعتمدة — أسماؤها تطابق ما تنشئه أداة الإعداد (whatsapp_setup.py)
ALERT_TEMPLATE_NAME = "alforaij_alert"            # فرصة جديدة: {{1}} رمز {{2}} منطقة {{3}} سعر
PRICE_DROP_TEMPLATE_NAME = "alforaij_price_drop"  # انخفاض سعر: {{1}} رمز {{2}} منطقة {{3}} جديد {{4}} سابق


def _format_price(value: Any) -> str:
    """تنسيق سعر كمتغير قالب: رقم مفصول الآلاف بلا عملة — القالب يضيف «د.ك»."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if f != f or abs(f) == float("inf"):  # NaN/inf
        return ""
    return f"{f:,.0f}"


def alert_template_params(alert: dict[str, Any]) -> tuple[str, list[str]]:
    """تعيين قالب UTILITY ومتغيراته حسب نوع التغيير — دالة نقية قابلة للاختبار.

    - new:        alforaij_alert        [الرمز، المنطقة، السعر]
    - price_drop: alforaij_price_drop   [الرمز، المنطقة، السعر الجديد، السعر السابق]
    السعر يُنسَّق رقمًا بلا عملة ({{N}} د.ك داخل نص القالب)، والسقوط إلى
    priceText منزوعًا من «د.ك» عند غياب القيمة الرقمية.
    """
    code = str(alert.get("code") or "")
    area = str(alert.get("area") or "")
    price = _format_price(alert.get("price"))
    if not price:
        price = str(alert.get("priceText") or "").replace(" د.ك", "").strip()
    change = str(alert.get("change") or "")
    if change == "price_drop":
        old_price = _format_price(alert.get("oldPrice")) or "السعر السابق"
        return PRICE_DROP_TEMPLATE_NAME, [code, area, price, old_price]
    return ALERT_TEMPLATE_NAME, [code, area, price]


def is_configured() -> bool:
    """هل إرسال واتساب مفعّل؟ (توكن Meta + معرّف رقم مرسل)."""
    return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_ID)


def normalize_meta_phone(phone: Any) -> str:
    """تطبيع رقم هاتف لصيغة Meta: 965XXXXXXXX (12 رقمًا بلا + أو 00).

    يقبل +96555559950 / 0096555559950 / 55559950 (محمول كويتي 8 أرقام) / 96555559950.
    يعيد "" لأي رقم غير صالح (أرقام أرضية أو أجنبية تُستبعد مثلًا).
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8 and digits[0] in "456789":  # محمول كويتي بدون رمز الدولة
        digits = "965" + digits
    if len(digits) == 11 and digits.startswith("965"):
        return digits
    return ""


def _load_send_log() -> list[dict[str, Any]]:
    if not SEND_LOG_PATH.exists():
        return []
    try:
        return json.loads(SEND_LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _append_send_log(entry: dict[str, Any]) -> None:
    try:
        log = _load_send_log()
        log.append(entry)
        SEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SEND_LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("whatsapp send log append failed: %s", exc)


def _already_sent(code: str, phone: str, change: str, today: str) -> bool:
    for entry in _load_send_log():
        if (
            entry.get("code") == code
            and entry.get("phone") == phone
            and entry.get("change") == change
            and str(entry.get("date") or "").startswith(today)
        ):
            return True
    return False


def send_whatsapp_template(
    phone: Any,
    template_name: str,
    params: list[str] | None = None,
) -> dict[str, Any]:
    """إرسال رسالة قالب UTILITY معتمد واحدة عبر Meta Cloud API.

    القوالب وحدها تعمل خارج نافذة الرد 24 ساعة (التنبيهات اليومية) — هذا
    بديل النص الحر القديم. يعيد {"status": "sent", "messageId": ...} عند
    النجاح، أو {"status": "failed", "error": ...} مع سبب واضح.
    """
    to = normalize_meta_phone(phone)
    if not to:
        return {"status": "failed", "error": f"رقم غير صالح لواتساب: {phone}"}
    if not is_configured():
        return {
            "status": "skipped",
            "reason": "not_configured",
            "note": "أضف WHATSAPP_TOKEN و WHATSAPP_PHONE_ID في .env لتفعيل الإرسال التلقائي.",
        }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "ar"},
        },
    }
    if params:
        payload["template"]["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]}
        ]
    request = urllib.request.Request(
        f"{GRAPH_API}/{WHATSAPP_PHONE_ID}/messages",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        message_id = ""
        messages = body.get("messages") or []
        if messages:
            message_id = str(messages[0].get("id") or "")
        return {"status": "sent", "messageId": message_id, "to": to, "template": template_name}
    except Exception as exc:
        logger.warning("WhatsApp template send failed for %s (%s): %s", to, template_name, exc)
        return {"status": "failed", "error": str(exc), "to": to, "template": template_name}


def send_whatsapp_alerts(
    alerts: list[dict[str, Any]],
    *,
    sender_name: str | None = None,
) -> dict[str, Any]:
    """إرسال تنبيهات الوكيل اليومي (جديد/انخفاض) لكل عميل مطابق — بقوالب معتمدة.

    - يختار لكل تنبيه قالب UTILITY ومتغيراته (alert_template_params): الفرص
      الجديدة عبر alforaij_alert، وانخفاض السعر عبر alforaij_price_drop —
      فيعمل خارج نافذة 24 ساعة.
    - يمنع التكرار اليومي لنفس (إعلان × رقم × نوع التغيير) عبر السجل المحلي.
    - يسجّل كل إرسال ناجح في outreach_clicks (Supabase) إن وُجد الجدول.
    - يعيد ملخصًا شفافًا: مرسل/فشل/مكرر/غير مفعّل — دون كسر الوكيل أبدًا.
    """
    if not is_configured():
        return {
            "status": "not_configured",
            "sent": 0,
            "failed": 0,
            "skippedDuplicates": 0,
            "total": 0,
            "note": "إرسال واتساب غير مفعّل — أضف WHATSAPP_TOKEN و WHATSAPP_PHONE_ID في .env (وثائق Meta Cloud API) ثم شغّل الوكيل، أو استخدم أزرار wa.me اليدوية الحالية.",
        }
    name = (sender_name or WHATSAPP_SENDER_NAME or "").strip() or "فريق الفريج العقاري"
    today = datetime.now().strftime("%Y-%m-%d")
    results: list[dict[str, Any]] = []
    sent = failed = skipped = 0
    for alert in alerts:
        code = str(alert.get("code") or "")
        change = str(alert.get("change") or "")
        template_name, params = alert_template_params(alert)
        phones = alert.get("phones") or []
        for raw_phone in phones:
            phone = normalize_meta_phone(raw_phone)
            if not phone:
                continue
            if _already_sent(code, phone, change, today):
                skipped += 1
                results.append({"code": code, "phone": phone, "status": "duplicate"})
                continue
            outcome = send_whatsapp_template(phone, template_name, params)
            entry = {
                "date": today,
                "time": datetime.now().strftime("%H:%M:%S"),
                "code": code,
                "phone": phone,
                "change": change,
                "template": template_name,
                "status": outcome.get("status"),
                "messageId": outcome.get("messageId", ""),
                "error": outcome.get("error", ""),
            }
            _append_send_log(entry)
            if outcome.get("status") == "sent":
                sent += 1
                # تتبع موحّد: نفس جدول نقرات التسويق (إرسال تلقائي للوكيل)
                try:
                    from backend.services.supabase_store import save_outreach_click
                    save_outreach_click({
                        "clientPhone": phone,
                        "clientArea": alert.get("clientArea"),
                        "clientType": alert.get("clientType"),
                        "opportunityCode": code,
                        "action": "send",
                        "channel": "whatsapp_agent",
                    })
                except Exception as exc:
                    logger.warning("outreach click tracking failed: %s", exc)
                results.append({"code": code, "phone": phone, "status": "sent"})
            else:
                failed += 1
                results.append({"code": code, "phone": phone, "status": "failed", "error": outcome.get("error", "")})

    status = "sent" if sent and not failed else ("partial" if sent else ("failed" if failed else "empty"))
    return {
        "status": status,
        "sent": sent,
        "failed": failed,
        "skippedDuplicates": skipped,
        "total": len(alerts),
        "senderName": name,
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results[:50],
    }
