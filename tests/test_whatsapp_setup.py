"""اختبارات أداة إعداد واتساب (Meta Cloud API): بنية القوالب + تقرير الجاهزية + متغيرات الإرسال.

بلا شبكة: دوال البناء نقية، وتقرير الجاهزية يُبنى من استجابات Graph وهمية.
تضمن أن:
- قالب OTP بفئة AUTHENTICATION بنص Meta الثابت (زر COPY_CODE + تحذير أمني + انتهاء 10 دقائق).
- قالب التنبيه بفئة UTILITY بثلاثة متغيرات بالضبط وبلا أي رابط (قاعدة Meta).
- إرسال التنبيه يمرر 3 متغيرات بالترتيب: الرمز ثم المنطقة ثم السعر المنسق.
"""
from __future__ import annotations

import unittest
from unittest import mock

from scripts.send_opportunity_alerts import _alert_template_params
from scripts.whatsapp_setup import (
    ALERT_TEMPLATE_NAME,
    OTP_TEMPLATE_NAME,
    build_alert_payload,
    build_otp_payload,
    check_setup,
    fetch_template_statuses,
)


class TestTemplatePayloads(unittest.TestCase):
    """بنية الحمولات التي تُرسل إلى upsert_message_templates."""

    def test_otp_payload_structure(self) -> None:
        payload = build_otp_payload()
        self.assertEqual(payload["name"], OTP_TEMPLATE_NAME)
        self.assertEqual(payload["category"], "AUTHENTICATION")
        self.assertEqual(payload["languages"], ["ar"])
        components = {c["type"]: c for c in payload["components"]}
        # نص القالب ثابت من Meta — لا نص مخصص (بخلاف القوالب العادية)
        self.assertNotIn("text", components["BODY"])
        self.assertTrue(components["BODY"].get("add_security_recommendation"))
        self.assertEqual(components["FOOTER"]["code_expiration_minutes"], 10)
        buttons = components["BUTTONS"]["buttons"]
        self.assertEqual(buttons, [{"type": "OTP", "otp_type": "COPY_CODE"}])

    def test_alert_payload_three_variables_no_url(self) -> None:
        payload = build_alert_payload()
        self.assertEqual(payload["name"], ALERT_TEMPLATE_NAME)
        self.assertEqual(payload["category"], "UTILITY")
        self.assertEqual(payload["languages"], ["ar"])
        components = {c["type"]: c for c in payload["components"]}
        body = components["BODY"]["text"]
        # ثلاثة متغيرات بالضبط بالترتيب المتفق عليه: رمز/منطقة/سعر
        self.assertEqual(body.count("{{"), 3)
        self.assertLess(body.index("{{1}}"), body.index("{{2}}"))
        self.assertLess(body.index("{{2}}"), body.index("{{3}}"))
        # قاعدة Meta: لا روابط في نصوص القوالب
        self.assertNotIn("http", body)
        self.assertNotIn("http", components["FOOTER"]["text"])


class TestCheckReport(unittest.TestCase):
    """تقرير الجاهزية من استجابات وهمية — لا شبكة."""

    def _mock_graph(self, waba_id: str = "WABA123", templates: list[dict] | None = None) -> mock.patch:
        templates = templates or []

        def fake_graph(method: str, path: str, token: str, body: dict | None = None) -> dict:
            if "message_templates" in path and "upsert" not in path:
                return {"data": templates}
            if "fields=display_phone_number" in path:
                return {
                    "display_phone_number": "96555550000",
                    "verified_name": "الفريج العقاري",
                    "quality_rating": "HIGH",
                    "whatsapp_business_account": {"id": waba_id, "name": "Alforaij"},
                }
            raise AssertionError(f"unexpected path: {path}")

        return mock.patch("scripts.whatsapp_setup._graph", side_effect=fake_graph)

    def test_not_configured(self) -> None:
        report = check_setup("", "")
        self.assertFalse(report["configured"])
        self.assertFalse(report["ready"])
        self.assertTrue(report["nextSteps"])

    def test_not_ready_when_templates_missing(self) -> None:
        with self._mock_graph():
            report = check_setup("tok", "123")
        self.assertFalse(report["ready"])
        self.assertEqual(report["phone"]["wabaId"], "WABA123")
        self.assertEqual(report["templates"][OTP_TEMPLATE_NAME]["status"], None)
        # خطوة إنشاء القالبين في التوصيات
        joined = "\n".join(report["nextSteps"])
        self.assertIn("--create-otp", joined)
        self.assertIn("--create-alert", joined)

    def test_ready_when_both_approved(self) -> None:
        with self._mock_graph(templates=[
            {"name": OTP_TEMPLATE_NAME, "status": "APPROVED", "id": "t1", "category": "AUTHENTICATION"},
            {"name": ALERT_TEMPLATE_NAME, "status": "APPROVED", "id": "t2", "category": "UTILITY"},
        ]):
            report = check_setup("tok", "123")
        self.assertTrue(report["ready"])
        self.assertIn("--send-test", "\n".join(report["nextSteps"]))

    def test_network_error_reported(self) -> None:
        with mock.patch(
            "scripts.whatsapp_setup._graph",
            side_effect=RuntimeError("HTTP 401: invalid token"),
        ):
            report = check_setup("bad-token", "123")
        self.assertFalse(report["ready"])
        self.assertIn("401", report["error"])

    def test_fetch_template_statuses_names_only(self) -> None:
        with mock.patch(
            "scripts.whatsapp_setup._graph",
            return_value={"data": [
                {"name": "unrelated", "status": "APPROVED"},
                {"name": ALERT_TEMPLATE_NAME, "status": "PENDING"},
            ]},
        ):
            statuses = fetch_template_statuses("tok", "WABA")
        self.assertEqual(statuses[OTP_TEMPLATE_NAME]["status"], None)
        self.assertEqual(statuses[ALERT_TEMPLATE_NAME]["status"], "PENDING")


class TestAlertParams(unittest.TestCase):
    """متغيرات الإرسال الفعلية لقالب التنبيه — تطابق النص المعتمد في Meta."""

    def test_three_params_in_order(self) -> None:
        params = _alert_template_params(
            {"opportunity_code": "BU3-7211", "area": "القصور", "price": 300000}
        )
        self.assertEqual(params, ["BU3-7211", "القصور", "300,000"])

    def test_no_url_ever(self) -> None:
        params = _alert_template_params(
            {"opportunity_code": "X-1", "area": "النهضة", "price": 100, "url": "https://example.com/x"}
        )
        self.assertEqual(len(params), 3)
        self.assertNotIn("http", "\n".join(params))

    def test_bad_price_falls_back_to_raw(self) -> None:
        params = _alert_template_params({"opportunity_code": "X-1", "area": "", "price": None})
        self.assertEqual(params, ["X-1", "", ""])


if __name__ == "__main__":
    unittest.main()
