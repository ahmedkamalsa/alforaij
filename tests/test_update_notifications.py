from __future__ import annotations

import unittest

from backend.services.update_notifications import build_update_notifications


class UpdateNotificationsTests(unittest.TestCase):
    def test_build_update_notifications_counts_changes_and_official_status(self) -> None:
        previous = {
            "tiers": {
                "daily": {
                    "items": [
                        {"code": "A", "area": "صباح الناصر", "propertyType": "بيت", "price": 300000, "priceText": "300,000 د.ك"},
                        {"code": "B", "area": "المطلاع", "propertyType": "بيت", "price": 400000, "priceText": "400,000 د.ك"},
                    ]
                }
            }
        }
        current = {
            "tiers": {
                "daily": {
                    "items": [
                        {"code": "A", "area": "صباح الناصر", "propertyType": "بيت", "price": 280000, "priceText": "280,000 د.ك"},
                        {"code": "C", "area": "خيطان", "propertyType": "شقة", "price": 120000, "priceText": "120,000 د.ك"},
                    ]
                }
            }
        }

        result = build_update_notifications(
            previous,
            current,
            official_result={"status": "skipped", "count": 0, "note": "no file"},
            data_summary={
                "tables": {
                    "official_transactions": {"count": 0, "status": "ok"},
                    "official_market_indicators": {"count": 51, "status": "ok"},
                }
            },
        )

        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["counts"]["removed"], 1)
        self.assertEqual(result["counts"]["priceDrops"], 1)
        self.assertEqual(result["officialTransactions"]["storedCount"], 0)
        # الإشعارات تبقى أرقامًا وأدلة فقط (top بروابطها) — لا توجيهات نصية بلا قيمة
        self.assertNotIn("actions", result)
        self.assertIn("top", result)
        self.assertEqual(result["top"]["added"][0]["code"], "C")


if __name__ == "__main__":
    unittest.main()
