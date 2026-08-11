from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestWhatsAppSender(unittest.TestCase):
    """اختبارات إرسال تنبيهات واتساب المجدولة (Meta Cloud API)."""

    def _configured(self) -> mock.patch:
        return mock.patch.multiple(
            "backend.services.whatsapp_sender",
            WHATSAPP_TOKEN="test-token",
            WHATSAPP_PHONE_ID="123456789",
            WHATSAPP_SENDER_NAME="فريق الفريج العقاري",
        )

    def test_normalize_meta_phone(self) -> None:
        from backend.services.whatsapp_sender import normalize_meta_phone

        # صيغ مقبولة
        self.assertEqual(normalize_meta_phone("+96555559950"), "96555559950")
        self.assertEqual(normalize_meta_phone("0096555559950"), "96555559950")
        self.assertEqual(normalize_meta_phone("96555559950"), "96555559950")
        self.assertEqual(normalize_meta_phone("55559950"), "96555559950")  # محمول كويتي
        self.assertEqual(normalize_meta_phone(55559950), "96555559950")  # رقم وليس نصًا
        # غير صالح: أرضي 7 أرقام، أجنبي، فارغ
        self.assertEqual(normalize_meta_phone("22260016"), "")
        self.assertEqual(normalize_meta_phone("+966555555555"), "")
        self.assertEqual(normalize_meta_phone(""), "")
        self.assertEqual(normalize_meta_phone(None), "")

    def test_send_message_not_configured(self) -> None:
        from backend.services.whatsapp_sender import send_whatsapp_message

        # عند غياب الضبط لا يُرسل أي شيء ولا يرمي استثناء
        result = send_whatsapp_message("96555559950", "رسالة تجريبية")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "not_configured")

    def test_send_message_success(self) -> None:
        from backend.services.whatsapp_sender import send_whatsapp_message

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"messages": [{"id": "wamid.ABC123"}]}).encode("utf-8")

        with self._configured(), mock.patch(
            "backend.services.whatsapp_sender.urllib.request.urlopen",
            return_value=FakeResponse(),
        ) as urlopen:
            result = send_whatsapp_message("+96555559950", "السلام عليكم")
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["messageId"], "wamid.ABC123")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["to"], "96555559950")
        self.assertEqual(payload["text"]["body"], "السلام عليكم")

    def test_send_message_invalid_phone(self) -> None:
        from backend.services.whatsapp_sender import send_whatsapp_message

        with self._configured():
            result = send_whatsapp_message("22260016", "رسالة")
        self.assertEqual(result["status"], "failed")

    def test_send_message_failure_reported(self) -> None:
        from backend.services.whatsapp_sender import send_whatsapp_message

        with self._configured(), mock.patch(
            "backend.services.whatsapp_sender.urllib.request.urlopen",
            side_effect=RuntimeError("HTTP 401"),
        ):
            result = send_whatsapp_message("96555559950", "رسالة")
        self.assertEqual(result["status"], "failed")
        self.assertIn("401", result["error"])

    def _alert(self, code: str, change: str = "new") -> dict:
        return {
            "code": code,
            "area": "النهضة",
            "change": change,
            "price": 400000,
            "priceText": "400,000 د.ك",
            "valuationLabel": "عادل",
            "clientArea": "النهضة",
            "clientType": "بيت",
            "phones": ["+96555559950"],
            "message": "السلام عليكم، معك [اسمك]. فرصة جديدة في النهضة بسعر 400,000 د.ك — عادل. شكرًا.",
        }

    def test_send_alerts_not_configured_never_breaks(self) -> None:
        from backend.services.whatsapp_sender import send_whatsapp_alerts

        result = send_whatsapp_alerts([self._alert("WA-1")])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["sent"], 0)
        self.assertIn("WHATSAPP_TOKEN", result["note"])

    def test_send_alerts_replaces_sender_name_and_sends(self) -> None:
        from backend.services import whatsapp_sender

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"messages": [{"id": "wamid.X"}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            whatsapp_sender.SEND_LOG_PATH = Path(tmp) / "send_log.json"
            with self._configured(), mock.patch(
                "backend.services.whatsapp_sender.urllib.request.urlopen",
                return_value=FakeResponse(),
            ) as urlopen, mock.patch(
                "backend.services.supabase_store.save_outreach_click",
                return_value={"status": "saved"},
            ) as track:
                result = whatsapp_sender.send_whatsapp_alerts([self._alert("WA-1")])
            self.assertEqual(result["status"], "sent")
            self.assertEqual(result["sent"], 1)
            self.assertEqual(result["failed"], 0)
            # اسم المرسل استُبدل في الرسالة الفعلية
            sent_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))["text"]["body"]
            self.assertNotIn("[اسمك]", sent_body)
            self.assertIn("فريق الفريج العقاري", sent_body)
            # التتبع الموحّد سُجّل
            self.assertEqual(track.call_args.args[0]["action"], "send")
            self.assertEqual(track.call_args.args[0]["channel"], "whatsapp_agent")
            self.assertEqual(track.call_args.args[0]["opportunityCode"], "WA-1")
            # السجل المحلي كُتب
            log = json.loads(whatsapp_sender.SEND_LOG_PATH.read_text(encoding="utf-8"))
            self.assertEqual(log[0]["code"], "WA-1")
            self.assertEqual(log[0]["phone"], "96555559950")
            self.assertEqual(log[0]["status"], "sent")

    def test_send_alerts_dedup_same_day(self) -> None:
        from backend.services import whatsapp_sender

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"messages": [{"id": "wamid.X"}]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            whatsapp_sender.SEND_LOG_PATH = Path(tmp) / "send_log.json"
            with self._configured(), mock.patch(
                "backend.services.whatsapp_sender.urllib.request.urlopen",
                return_value=FakeResponse(),
            ):
                first = whatsapp_sender.send_whatsapp_alerts([self._alert("WA-2")])
                second = whatsapp_sender.send_whatsapp_alerts([self._alert("WA-2")])
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["skippedDuplicates"], 1)
        self.assertEqual(second["status"], "empty")

    def test_send_alerts_failed_reported(self) -> None:
        from backend.services import whatsapp_sender

        with tempfile.TemporaryDirectory() as tmp:
            whatsapp_sender.SEND_LOG_PATH = Path(tmp) / "send_log.json"
            with self._configured(), mock.patch(
                "backend.services.whatsapp_sender.urllib.request.urlopen",
                side_effect=RuntimeError("HTTP 500"),
            ):
                result = whatsapp_sender.send_whatsapp_alerts([self._alert("WA-3")])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["sent"], 0)

    def test_send_alerts_empty(self) -> None:
        from backend.services.whatsapp_sender import send_whatsapp_alerts

        with self._configured():
            result = send_whatsapp_alerts([])
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["sent"], 0)


if __name__ == "__main__":
    unittest.main()
