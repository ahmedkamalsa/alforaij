"""مرسل رسائل قالب عبر WhatsApp Cloud API (Meta) — بلا اعتماديات (urllib فقط).

يُستخدم لإرسال رمز التحقق (otp_template) وتنبيهات الفرص (alert_template).

الانحدار الأنيق: عند غياب WHATSAPP_TOKEN أو WHATSAPP_PHONE_ID يطبع تحذيرًا
ويعيد None — المتصل يعرض الرمز على الشاشة أو يكتفي بالجرس داخل التطبيق،
فلا تنكسر أي رحلة بسبب عدم ضبط أسرار واتساب.

الاستخدام:
    from scripts.send_whatsapp_message import send_template_message
    send_template_message("+96555512345", "otp_template", ["123456"])

أو سطرًا:
    WHATSAPP_TOKEN=... WHATSAPP_PHONE_ID=... python scripts/send_whatsapp_message.py +96555512345 otp_template 123456
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

GRAPH_API_VERSION = "v19.0"


def _config() -> tuple[str, str]:
    token = str(os.getenv("WHATSAPP_TOKEN", "")).strip()
    phone_id = str(os.getenv("WHATSAPP_PHONE_ID", "")).strip()
    return token, phone_id


def send_template_message(
    to_phone: str,
    template_name: str,
    params: list[str] | None = None,
    language: str = "ar",
) -> dict | None:
    """إرسال رسالة قالب معتمدة — يعيد استجابة Meta أو None عند غياب الأسرار.

    params تُمرَّر كمتغيرات نصية لقالب النص (بالترتيب نفسه المحدد في Meta).
    أي فشل شبكي يُبتلع ويعيد None (التطبيق يعتمد قنوات الانحدار، لا ينهار).
    """
    token, phone_id = _config()
    if not token or not phone_id:
        print(
            "WARNING: WHATSAPP_TOKEN / WHATSAPP_PHONE_ID غير مضبوطين — "
            f"تخطي إرسال «{template_name}» إلى {to_phone} (انحدار أنيق).",
            file=sys.stderr,
        )
        return None

    body: dict = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }
    if params:
        body["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in params],
            }
        ]

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_id}/messages"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        return {"delivery": "whatsapp", "messageId": payload.get("messages", [{}])[0].get("id")}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        detail = ""
        if isinstance(exc, urllib.error.HTTPError):
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        print(f"WARNING: فشل إرسال واتساب «{template_name}»: {exc} {detail}", file=sys.stderr)
        return None


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 1
    to_phone, template_name = args[0], args[1]
    params = args[2:]
    result = send_template_message(to_phone, template_name, params)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
