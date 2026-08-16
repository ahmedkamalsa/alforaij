"""اختبارات بوابة جاهزية واتساب في سير العمل اليومي (الوكيل).

التغطية: قرار الإرسال حسب اعتماد القوالب الثلاثة، توثيق الحالة في ملخص
التشغيل (GITHUB_STEP_SUMMARY)، وتوجيه كل نوع تغيير إلى قالبه المعتمد.
بلا شبكة: كل نداءات Meta وSupabase مُحاكاة.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.send_opportunity_alerts as sender  # noqa: E402


def _item(code: str, area: str = "السالمية", price: float = 280000) -> dict:
    return {
        "code": code,
        "area": area,
        "governorate": "محافظة حولي",
        "transaction": "للبيع",
        "propertyType": "بيت",
        "price": price,
        "priceText": f"{price:,.0f} د.ك",
        "url": f"https://example.com/{code}",
    }


def _snapshot_row(items: list[dict], at: str = "2026-08-16T03:00:00") -> dict:
    return {"generated_at": at, "tiers": {"daily": {"items": items}}, "forecast": []}


def _search(secret: str = "s1", area: str = "السالمية") -> dict:
    return {
        "id": 1,
        "user_secret": secret,
        "name": "بيت في السالمية",
        "request_text": "بيت 400م في السالمية",
        "transaction_type": "مطلوب للشراء",
        "property_type": "بيت",
        "areas": [area],
        "governorates": [],
        "price_min": 200000,
        "price_max": 350000,
        "alert_enabled": True,
    }


def _ready_report(ready: bool) -> dict:
    return {
        "configured": True,
        "ready": ready,
        "phone": {"phone": "+96555500000", "verifiedName": "الفريج", "quality": "GREEN", "wabaName": "WABA"},
        "waba": {"id": "WABA123", "source": "phone"},
        "templates": {
            "alforaij_otp": {"status": "APPROVED" if ready else "APPROVED", "id": "1"},
            "alforaij_alert": {"status": "APPROVED" if ready else "PENDING", "id": "2"},
            "alforaij_price_drop": {"status": "APPROVED" if ready else "APPROVED", "id": "3"},
        },
        "nextSteps": [] if ready else ["شغّل --create-alert (ثم انتظر الاعتماد)."],
    }


class ReadinessTests(unittest.TestCase):
    def test_not_configured_no_network(self) -> None:
        with mock.patch.dict(os.environ, {"WHATSAPP_TOKEN": "", "WHATSAPP_PHONE_ID": ""}):
            report = sender.whatsapp_readiness()
        self.assertFalse(report["configured"])
        self.assertFalse(report["ready"])
        self.assertEqual(report["reason"], "not_configured")

    def test_configured_delegates_to_check_setup(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_ID": "123", "WHATSAPP_WABA_ID": "WABA_X"},
        ), mock.patch("scripts.whatsapp_setup.check_setup", return_value={"ready": True}) as check:
            report = sender.whatsapp_readiness()
        check.assert_called_once_with("tok", "123", "WABA_X")
        self.assertTrue(report["ready"])

    def test_network_error_contained(self) -> None:
        with mock.patch.dict(os.environ, {"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_ID": "123"}):
            with mock.patch(
                "scripts.whatsapp_setup.check_setup",
                side_effect=RuntimeError("boom"),
            ):
                report = sender.whatsapp_readiness()
        self.assertTrue(report["configured"])
        self.assertFalse(report["ready"])
        self.assertEqual(report["reason"], "network_error")
        self.assertIn("boom", report["error"])


class SummaryTests(unittest.TestCase):
    def _summary_lines(self, report: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            summary_file = Path(tmp) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
                sender.write_readiness_summary(report)
            return summary_file.read_text(encoding="utf-8").splitlines()

    def test_not_configured_documented(self) -> None:
        lines = self._summary_lines({"configured": False, "ready": False, "templates": {}, "reason": "not_configured"})
        text = "\n".join(lines)
        self.assertIn("جاهزية تنبيهات واتساب", text)
        self.assertIn("غير مضبوطة", text)
        self.assertIn("الجرس", text)

    def test_not_ready_lists_template_statuses(self) -> None:
        lines = self._summary_lines(_ready_report(ready=False))
        text = "\n".join(lines)
        self.assertIn("alforaij_alert", text)
        self.assertIn("PENDING", text)
        self.assertIn("غير جاهز", text)
        self.assertIn("--create-alert", text)

    def test_ready_reported(self) -> None:
        lines = self._summary_lines(_ready_report(ready=True))
        self.assertTrue(any("✅ القوالب الثلاثة معتمدة" in line for line in lines))

    def test_prints_when_no_summary_env(self) -> None:
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                with redirect_stdout(buf):
                    sender.write_readiness_summary(_ready_report(ready=True))
        self.assertIn("القوالب الثلاثة معتمدة", buf.getvalue())


class SendPlanTests(unittest.TestCase):
    def test_new_uses_alert_template_three_params(self) -> None:
        template, params = sender._alert_send_plan(
            {"opportunity_code": "WA-1", "area": "النهضة", "price": 400000, "change": "new"}
        )
        self.assertEqual(template, "alforaij_alert")
        self.assertEqual(params, ["WA-1", "النهضة", "400,000"])

    def test_price_drop_uses_price_drop_template_four_params(self) -> None:
        template, params = sender._alert_send_plan(
            {
                "opportunity_code": "WA-2",
                "area": "النهضة",
                "price": 270000,
                "oldPrice": 300000,
                "change": "price_drop",
            }
        )
        self.assertEqual(template, "alforaij_price_drop")
        self.assertEqual(params, ["WA-2", "النهضة", "270,000", "300,000"])

    def test_price_text_fallback(self) -> None:
        self.assertEqual(sender._price_text(None), "")
        self.assertEqual(sender._price_text("غير محدد"), "غير محدد")


class MainGateTests(unittest.TestCase):
    """main() لا يُرسل واتساب دون جاهزية، ويُرسل عندها — والجرس يُكتب في الحالتين."""

    def _patch_env(self, ready: bool) -> dict:
        # الأحدث أولًا (snapshots[0] = الحالي) كما تُرجع fetch_opportunity_snapshots
        snapshots = [
            _snapshot_row([_item("OLD-1", price=300000), _item("NEW-1")], at="2026-08-17T03:00:00"),
            _snapshot_row([_item("OLD-1", price=300000)], at="2026-08-16T03:00:00"),
        ]
        return {
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "k",
            "fetch_opportunity_snapshots": mock.Mock(return_value=snapshots),
            "fetch_saved_searches": mock.Mock(return_value=[_search()]),
            "fetch_existing_alert_keys": mock.Mock(return_value=[]),
            "insert_user_alerts": mock.Mock(return_value=1),
            "fetch_user_phones": mock.Mock(return_value={"s1": "96555559950"}),
            "whatsapp_readiness": mock.Mock(return_value=_ready_report(ready)),
        }

    def test_not_ready_skips_whatsapp_but_writes_bell(self) -> None:
        with mock.patch.multiple("scripts.send_opportunity_alerts", **self._patch_env(ready=False)), mock.patch(
            "scripts.send_whatsapp_message.send_template_message", return_value={"delivery": "whatsapp"}
        ) as send:
            code = sender.main()
            self.assertEqual(code, 0)
            send.assert_not_called()
            sender.insert_user_alerts.assert_called_once()

    def test_ready_sends_whatsapp(self) -> None:
        with mock.patch.multiple("scripts.send_opportunity_alerts", **self._patch_env(ready=True)), mock.patch(
            "scripts.send_whatsapp_message.send_template_message", return_value={"delivery": "whatsapp", "messageId": "w"}
        ) as send:
            code = sender.main()
            self.assertEqual(code, 0)
            send.assert_called_once()
            self.assertEqual(send.call_args.args[0], "96555559950")
            self.assertEqual(send.call_args.args[1], "alforaij_alert")


class RowsCarryOldPriceTests(unittest.TestCase):
    def test_price_drop_row_has_old_price(self) -> None:
        from backend.services.opportunity_alerts import build_alert_rows, find_changes

        previous = {"generatedAt": "2026-08-16", "tiers": {"daily": {"items": [_item("D1", price=300000)]}}}
        current = {"generatedAt": "2026-08-17", "tiers": {"daily": {"items": [_item("D1", price=270000)]}}}
        change = find_changes(previous, current)[0]
        rows = build_alert_rows(previous, current, [_search()])
        self.assertEqual(change["change"], "price_drop")
        self.assertEqual(rows[0]["change"], "price_drop")
        self.assertEqual(rows[0]["oldPrice"], 300000)
        self.assertEqual(rows[0]["oldPriceText"], "300,000 د.ك")


if __name__ == "__main__":
    unittest.main()
